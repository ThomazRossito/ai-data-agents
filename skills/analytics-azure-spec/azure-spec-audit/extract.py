#!/usr/bin/env python3
"""
Extrator buffer-safe e paralelo para o agente azure-analytics-auditor.

Uso:
    python extract.py <INPUT_DIR> <WORK_DIR> [--workers N] [--lang por+eng] [--max-pages 60]

O que faz (robusto para lotes grandes):
  - Varre INPUT_DIR e classifica: pptx, xlsx, docx, pdf (texto), pdf-imagem, imagens.
  - DEDUP por hash de conteúdo (md5): arquivos idênticos são processados uma vez (os demais
    viram alias no manifesto, sem reprocessar).
  - Texto nativo (pptx/xlsx/docx/pdf-com-texto) extraído direto (rápido).
  - PDF-imagem e imagens (png/jpg/...) via OCR em PARALELO (ProcessPoolExecutor, 1 tarefa por
    página/imagem). dpi adaptativo (arquivo grande => dpi menor) e downscale de pixmaps enormes.
  - Escrita INCREMENTAL: cada arquivo vira um part em WORK_DIR/parts/<id>.json assim que termina
    (progresso visível, resistente a crash). No fim consolida WORK_DIR/flat_index.json + manifest.json.
  - BUFFER-SAFE: trunca o texto por unidade (~3000 chars) e nunca imprime conteúdo grande no stdout
    (só linhas curtas de progresso). Saídas pequenas => não estoura o max_buffer do SDK.
  - Fallback de idioma do tesseract (por+eng -> eng) e, se tesseract ausente, tenta rapidocr.

Dependências: pdfplumber pymupdf python-pptx openpyxl python-docx pytesseract pillow
              (opcional fallback: rapidocr-onnxruntime)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Evita oversubscription: cada worker usa 1 thread de OCR (paralelismo é por processo).
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

UNIT_TRUNC = 3000          # chars máximos por unidade (slide/página/aba) no índice
IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}

# ---------- OCR helpers (executados em processos worker) ----------

def _ocr_pil(img, lang: str) -> str:
    """OCR de uma imagem PIL com fallback de idioma e de engine."""
    try:
        import pytesseract
        try:
            return pytesseract.image_to_string(img, lang=lang).strip()
        except Exception:
            return pytesseract.image_to_string(img, lang="eng").strip()
    except Exception:
        # Fallback puro-pip se tesseract não existir
        try:
            import numpy as np
            from rapidocr_onnxruntime import RapidOCR
            ocr = RapidOCR()
            res, _ = ocr(np.array(img.convert("RGB")))
            return "\n".join(l[1] for l in (res or [])).strip()
        except Exception as e:
            return f"[OCR indisponível: {e}]"


def _downscale(img, max_px: int = 2200):
    w, h = img.size
    if max(w, h) > max_px:
        scale = max_px / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)))
    return img


def ocr_image_file(path: str, lang: str) -> list[dict]:
    from PIL import Image
    try:
        img = _downscale(Image.open(path))
        return [{"loc": "(OCR)", "text": _ocr_pil(img, lang)[:UNIT_TRUNC]}]
    except Exception as e:
        return [{"loc": "(OCR)", "text": f"[erro: {e}]"}]


def ocr_pdf_file(path: str, dpi: int, lang: str, max_pages: int) -> list[dict]:
    """Abre o PDF UMA vez e OCR de todas as páginas (evita reabrir arquivo grande por página)."""
    import io
    import fitz
    from PIL import Image
    out = []
    try:
        doc = fitz.open(path)
        for pg in range(min(doc.page_count, max_pages)):
            try:
                pix = doc[pg].get_pixmap(dpi=dpi)
                img = _downscale(Image.open(io.BytesIO(pix.tobytes("png"))))
                out.append({"loc": f"p.{pg + 1} (OCR)", "text": _ocr_pil(img, lang)[:UNIT_TRUNC]})
            except Exception as e:
                out.append({"loc": f"p.{pg + 1} (OCR)", "text": f"[erro: {e}]"})
    except Exception as e:
        out.append({"loc": "(OCR)", "text": f"[erro ao abrir: {e}]"})
    return out


# ---------- Extração de texto nativo (processo principal, rápido) ----------

def extract_pptx(path):
    from pptx import Presentation
    units = []
    prs = Presentation(path)
    for i, sl in enumerate(prs.slides, 1):
        t = []
        for sh in sl.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                t.append(sh.text_frame.text.strip())
            if sh.has_table:
                for r in sh.table.rows:
                    t.append(" | ".join(c.text for c in r.cells))
        units.append({"loc": f"slide {i}", "text": "\n".join(t)[:UNIT_TRUNC]})
    return units


def extract_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    units = []
    for ws in wb.worksheets:
        rows, n = [], 0
        for r in ws.iter_rows(values_only=True):
            vals = [str(c) for c in r if c is not None]
            if vals:
                rows.append(" | ".join(vals)); n += 1
            if n >= 30:
                break
        units.append({"loc": f"aba {ws.title}", "text": "\n".join(rows)[:UNIT_TRUNC]})
    return units


def extract_docx(path):
    from docx import Document
    doc = Document(path)
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    units = [{"loc": "corpo", "text": "\n".join(paras)[:UNIT_TRUNC]}]
    return units


def pdf_native_text(path):
    import pdfplumber
    units, total = [], 0
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for i, p in enumerate(pdf.pages, 1):
            tx = (p.extract_text() or "").strip()
            total += len(tx)
            units.append({"loc": f"p.{i}", "text": tx[:UNIT_TRUNC]})
    return units, total, n


def pdf_page_count(path):
    import fitz
    d = fitz.open(path)
    return d.page_count


# ---------- Orquestração ----------

def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def safe_id(rel):
    return "".join(c if c.isalnum() else "_" for c in rel)[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir")
    ap.add_argument("work_dir")
    ap.add_argument("--workers", type=int, default=min(os.cpu_count() or 4, 8))
    ap.add_argument("--lang", default="eng",
                    help="idioma tesseract; use 'por+eng' p/ maior fidelidade PT (mais lento)")
    ap.add_argument("--max-pages", type=int, default=60)
    args = ap.parse_args()

    in_dir = Path(args.input_dir)
    work = Path(args.work_dir)
    parts = work / "parts"
    parts.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in sorted(in_dir.rglob("*"))
        if p.is_file() and p.name not in SKIP_NAMES and not any(part == "_work" for part in p.parts)
    ]

    # Dedup por hash
    seen: dict[str, str] = {}
    manifest = {}
    unique = []
    for p in files:
        rel = str(p.relative_to(in_dir))
        try:
            h = md5(p)
        except Exception as e:
            manifest[rel] = {"status": "erro", "error": str(e)}
            continue
        if h in seen:
            manifest[rel] = {"status": "duplicado_de", "alias_de": seen[h]}
            continue
        seen[h] = rel
        unique.append((p, rel))
        manifest[rel] = {"status": "pendente", "size_mb": round(p.stat().st_size / 1048576, 2)}

    print(f"[extract] {len(files)} arquivos | {len(unique)} únicos | "
          f"{len(files) - len(unique)} duplicados | workers={args.workers}", flush=True)

    # 1) Texto nativo (rápido, sequencial) + monta tarefas de OCR
    ocr_tasks = []   # (rel, kind, args...)
    file_units: dict[str, list] = {}
    file_type: dict[str, str] = {}

    for p, rel in unique:
        ext = p.suffix.lower()
        try:
            if ext == ".pptx":
                file_units[rel] = extract_pptx(str(p)); file_type[rel] = "pptx"
            elif ext in (".xlsx", ".xls"):
                file_units[rel] = extract_xlsx(str(p)); file_type[rel] = "xlsx"
            elif ext == ".docx":
                file_units[rel] = extract_docx(str(p)); file_type[rel] = "docx"
            elif ext in (".txt", ".md", ".csv"):
                file_units[rel] = [{"loc": "arquivo", "text": p.read_text(errors="ignore")[:UNIT_TRUNC]}]
                file_type[rel] = "text"
            elif ext == ".pdf":
                units, total, npages = pdf_native_text(str(p))
                if total > 200:
                    file_units[rel] = units; file_type[rel] = "pdf_texto"
                else:  # PDF-imagem -> OCR paralelo (1 tarefa por arquivo, abre 1x)
                    file_type[rel] = "pdf_ocr"; file_units[rel] = []
                    size_mb = p.stat().st_size / 1048576
                    dpi = 100 if size_mb > 10 else 130
                    ocr_tasks.append(("pdf", rel, str(p), dpi))
            elif ext in IMG_EXT:
                file_type[rel] = "imagem"; file_units[rel] = []
                ocr_tasks.append(("image", rel, str(p), 0))
            else:
                file_type[rel] = "ignorado"; file_units[rel] = []
                manifest[rel]["status"] = "ignorado"
        except Exception as e:
            file_type[rel] = "erro"; file_units[rel] = []
            manifest[rel]["status"] = "erro"; manifest[rel]["error"] = str(e)

    # grava parts dos que já terminaram (texto nativo)
    def write_part(rel):
        pid = safe_id(rel)
        (parts / f"{pid}.json").write_text(
            json.dumps({"file": rel, "type": file_type.get(rel), "units": file_units.get(rel, [])},
                       ensure_ascii=False), encoding="utf-8")

    for rel in list(file_units):
        if file_type.get(rel) not in ("pdf_ocr", "imagem"):
            write_part(rel); manifest[rel]["status"] = "ok"

    # 2) OCR em paralelo (1 tarefa por arquivo; abre o PDF uma única vez)
    print(f"[extract] OCR: {len(ocr_tasks)} arquivos (PDF-imagem/imagens) em paralelo...", flush=True)
    done = 0
    if ocr_tasks:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {}
            for t in ocr_tasks:
                kind, rel, path, dpi = t
                if kind == "pdf":
                    futs[ex.submit(ocr_pdf_file, path, dpi, args.lang, args.max_pages)] = rel
                else:
                    futs[ex.submit(ocr_image_file, path, args.lang)] = rel
            for fut in as_completed(futs):
                rel = futs[fut]
                try:
                    units = fut.result()
                except Exception as e:
                    units = [{"loc": "(OCR)", "text": f"[erro: {e}]"}]
                file_units[rel] = units
                done += 1
                print(f"[extract] OCR {done}/{len(ocr_tasks)} :: {rel[:50]} ({len(units)} un.)", flush=True)
                write_part(rel); manifest[rel]["status"] = "ok"  # incremental

    # 3) Consolida índice achatado (pequeno) + manifesto
    flat = []
    for rel in sorted(file_units):
        units = sorted(file_units[rel], key=lambda u: u["loc"])
        chars = sum(len(u["text"]) for u in units)
        flat.append({"file": rel, "type": file_type.get(rel), "chars": chars,
                     "units": units})
        manifest.setdefault(rel, {})["chars"] = chars
    (work / "flat_index.json").write_text(json.dumps(flat, ensure_ascii=False), encoding="utf-8")
    (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                        encoding="utf-8")

    n_ok = sum(1 for v in manifest.values() if v.get("status") == "ok")
    n_dup = sum(1 for v in manifest.values() if v.get("status") == "duplicado_de")
    print(f"[extract] DONE: {n_ok} processados, {n_dup} duplicados pulados. "
          f"Índice: {work}/flat_index.json (use grep/Bash, NÃO Read se grande).", flush=True)


if __name__ == "__main__":
    main()
