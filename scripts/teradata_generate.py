#!/usr/bin/env python3
"""
teradata_generate.py — Gerador DETERMINÍSTICO Teradata DDL → Databricks/Delta (dono:
agente `teradata-to-databricks`). Mesmo padrão de `hive_generate.py`/`sqlserver_generate.py`:
correto-por-construção, com gates que FALHAM o build. NÃO escreva o DDL à mão.

Base normativa: `kb/teradata-migration/concepts/ddl-conversion.md` + digest auditado do curso
oficial "Delivery Expert for Teradata Migration" (fase 3.1). Mapa de tipos = códigos reais de
`DBC.ColumnsV` (Teradata Language Reference), NÃO a tabela de tipos do curso — que está
CONTAMINADA com Snowflake (VARIANT/OBJECT/TIMESTAMP_NTZ como se fossem tipos Teradata).

Entrada: arquivo .sql com um ou mais `CREATE [SET|MULTISET] TABLE` do Teradata (ex.: saída de
`SHOW TABLE db.tabela;`).

Saída (em <outdir>/):
  01_ddl_delta.sql        — CREATE TABLE Delta (tipos mapeados, CLUSTER BY do PRIMARY INDEX/PPI,
                            COMMENT do tipo Teradata; FALLBACK/JOURNAL/CHECKSUM/MAP/CASESPECIFIC removidos)
  02_type_flags.md        — colunas que exigem revisão (PERIOD/INTERVAL/JSON/XML, tipos desconhecidos)
                            + AVISO de SET TABLE (dedup obrigatório na ingestão)
  03_reconcile_spec.json  — spec pronto p/ scripts/reconcile_generate.py (source_dialect=teradata)

GATE ESPECIAL (anti-contaminação Snowflake): se o DDL de ENTRADA contiver tokens que são do
Snowflake e NÃO do Teradata (VARIANT/OBJECT como tipo, ARRAY_AGG/OBJECT_AGG/IFF/EQUAL_NULL,
LATERAL FLATTEN, METADATA$*, RUNTIME_VERSION/HANDLER, dataset TB_101/RAW_POS), o build FALHA —
a "fonte Teradata" provavelmente não é Teradata genuína.

Uso: python scripts/teradata_generate.py <teradata_ddl.sql> <outdir>
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

# ── Mapa de tipos Teradata → Delta (códigos DBC.ColumnsV / Teradata Language Reference) ──────
# (tipo_base_lower) -> (tipo Delta, flag|None)
_PRIM = {
    "byteint": ("TINYINT", None),          # 1 byte, -128..127 → TINYINT
    "smallint": ("SMALLINT", None),
    "integer": ("INT", None), "int": ("INT", None),
    "bigint": ("BIGINT", None),
    "float": ("DOUBLE", None), "real": ("DOUBLE", None),   # Teradata FLOAT/REAL = 64-bit IEEE → DOUBLE
    "double precision": ("DOUBLE", None), "double": ("DOUBLE", None),
    "date": ("DATE", None),
    "byte": ("BINARY", None), "varbyte": ("BINARY", None), "blob": ("BINARY", None),
    "clob": ("STRING", None), "json": ("STRING", "Teradata JSON → STRING (ou VARIANT em DBR 15.3+; revisar)"),
    "xml": ("STRING", "Teradata XML → STRING (revisar)"),
    "boolean": ("BOOLEAN", None),          # só Vantage recente; verificar na origem
    "st_geometry": ("STRING", "ST_GEOMETRY → STRING (WKT via ST_AsText) ou GEOGRAPHY em DBR 17.1+"),
    "geometry": ("STRING", "GEOMETRY → STRING (WKT) ou tipo geo nativo (revisar)"),
}

# Tokens que são do SNOWFLAKE e NÃO do Teradata — se aparecerem na ENTRADA "Teradata", é contaminação.
_SNOWFLAKE_TOKENS = [
    r"\bVARIANT\b", r"\bOBJECT\b", r"\bARRAY_AGG\b", r"\bARRAY_UNIQUE_AGG\b", r"\bOBJECT_AGG\b",
    r"\bIFF\s*\(", r"\bEQUAL_NULL\b", r"LATERAL\s+FLATTEN", r"METADATA\$", r"RUNTIME_VERSION",
    r"\bHANDLER\s*=", r"\bTB_101\b", r"\bRAW_POS\b", r"TIMESTAMP_NTZ", r"TIMESTAMP_LTZ", r"TIMESTAMP_TZ",
]

# Opções de tabela / atributos de coluna Teradata que devem ser REMOVIDOS no Delta.
_TABLE_OPTS = re.compile(
    r",?\s*\b("
    r"FALLBACK|NO\s+FALLBACK|NO\s+BEFORE\s+JOURNAL|NO\s+AFTER\s+JOURNAL|"
    r"DUAL\s+BEFORE\s+JOURNAL|DUAL\s+AFTER\s+JOURNAL|WITH\s+JOURNAL\s+TABLE\s*=\s*\S+|"
    r"CHECKSUM\s*=\s*\w+|DEFAULT\s+MERGEBLOCKRATIO|NO\s+MERGEBLOCKRATIO|MERGEBLOCKRATIO\s*=\s*\d+|"
    r"MAP\s*=\s*\w+|BLOCKCOMPRESSION\s*=\s*\w+|FREESPACE\s*=\s*\d+\s*PERCENT?"
    r")\b",
    re.IGNORECASE,
)


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower() or "col"


def bq(name: str) -> str:
    return "`" + str(name).replace("`", "``") + "`"


def sq(name: str) -> str:
    return "'" + str(name).replace("'", "''") + "'"


def map_type(td_type: str) -> tuple[str, str | None]:
    """Tipo Teradata (com params) → (tipo Delta, flag|None)."""
    t = (td_type or "").strip()
    low = t.lower()
    # DECIMAL/NUMERIC/NUMBER(p,s)
    m = re.match(r"(decimal|numeric|number)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", low)
    if m:
        return (f"DECIMAL({m.group(2)},{m.group(3)})", None)
    m = re.match(r"(decimal|numeric|number)\s*\(\s*(\d+)\s*\)", low)
    if m:
        return (f"DECIMAL({m.group(2)},0)", None)
    if low in ("decimal", "numeric"):
        return ("DECIMAL(38,0)", None)
    if low == "number":
        return ("DECIMAL(38,0)", "Teradata NUMBER sem precisão → DECIMAL(38,0) (revisar escala real)")
    # CHAR/VARCHAR/CHARACTER/GRAPHIC → STRING
    if re.match(r"(varchar|char|character|long\s+varchar|graphic|vargraphic|long\s+vargraphic)\b", low):
        return ("STRING", None)
    # TIMESTAMP(n) [WITH TIME ZONE]
    if re.match(r"timestamp\b", low):
        if "with time zone" in low:
            return ("TIMESTAMP", None)          # com fuso → TIMESTAMP (com fuso, instante)
        return ("TIMESTAMP_NTZ", None)          # Teradata TIMESTAMP é sem fuso → TIMESTAMP_NTZ
    # TIME(n) [WITH TIME ZONE] — sem tipo nativo direto
    if re.match(r"time\b", low):
        return ("STRING", "Teradata TIME → STRING 'HH:MM:SS(.ffffff)' (Spark não tem TIME nativo)")
    # PERIOD(...)
    if low.startswith("period"):
        return ("STRING", "Teradata PERIOD → STRUCT<start,end> ou STRING (sem tipo direto; usar EXPAND ON na origem)")
    # INTERVAL ...
    if low.startswith("interval"):
        return ("STRING", "Teradata INTERVAL → STRING ou decompor em BIGINT de segundos/meses (sem tipo direto)")
    # ARRAY / VARRAY (Vantage)
    if low.startswith("array") or low.startswith("varray"):
        return ("STRING", "Teradata ARRAY/VARRAY → ARRAY<type> ou STRING (revisar o tipo do elemento)")
    # base de uma palavra (ou duas, ex.: double precision)
    base2 = re.match(r"([a-z_]+\s+[a-z_]+)", low)
    if base2 and base2.group(1) in _PRIM:
        return _PRIM[base2.group(1)]
    base = re.match(r"([a-z_]+)", low)
    base = base.group(1) if base else low
    if base in _PRIM:
        return _PRIM[base]
    return ("STRING", f"tipo Teradata desconhecido '{td_type}' → STRING (fallback — revisar)")


def _split_top_commas(s: str) -> list[str]:
    """Divide por vírgulas de nível superior (respeita parênteses de tipos com params)."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _extract_paren_block(s: str, start: int) -> tuple[str, int]:
    """Extrai o conteúdo do parêntese balanceado que começa em s[start]=='('."""
    depth, i = 0, start
    while i < len(s):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return s[start + 1:i], i
        i += 1
    return s[start + 1:], len(s)


def _strip_col_attrs(defn: str) -> tuple[str, bool]:
    """Remove atributos Teradata da definição de coluna; retorna (def_limpa, not_null)."""
    s = defn
    not_null = bool(re.search(r"\bNOT\s+NULL\b", s, re.IGNORECASE))
    s = re.sub(r"\bNOT\s+NULL\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCHARACTER\s+SET\s+\w+", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(NOT\s+)?CASESPECIFIC\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bUPPERCASE\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCOMPRESS\s*\([^)]*\)", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCOMPRESS\b(\s+'[^']*'|\s+[-\w.]+)?", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bFORMAT\s+'[^']*'", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bTITLE\s+'[^']*'", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNAMED\s+\w+", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bDEFAULT\s+('[^']*'|[-\w.():]+)", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGENERATED\s+(ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY(\s*\([^)]*\))?", " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip().rstrip(","), not_null


def _parse_cols(coldef: str) -> list[dict]:
    cols = []
    for raw in _split_top_commas(coldef):
        raw = raw.strip()
        if not raw:
            continue
        clean, not_null = _strip_col_attrs(raw)
        m = re.match(r'[`"]?([A-Za-z_][\w$]*)[`"]?\s+(.+)$', clean, re.S)
        if not m:
            continue
        cols.append({"name": m.group(1), "type": m.group(2).strip(), "not_null": not_null})
    return cols


def _index_cols(clause: str, keyword: str) -> list[str]:
    m = re.search(keyword + r"\s*\(([^)]*)\)", clause, re.IGNORECASE)
    if not m:
        return []
    out = []
    for c in _split_top_commas(m.group(1)):
        mm = re.match(r'[`"]?([A-Za-z_][\w$]*)[`"]?', c.strip())
        if mm:
            out.append(mm.group(1))
    return out


def parse_teradata_ddl(text: str) -> list[dict]:
    tables = []
    for m in re.finditer(
        r"CREATE\s+(?:(SET|MULTISET)\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([\w.$]+)[`\"]?",
        text, re.IGNORECASE,
    ):
        set_kind = (m.group(1) or "MULTISET").upper()
        name = m.group(2)
        paren = text.find("(", m.end())
        if paren == -1:
            continue
        coldef, end = _extract_paren_block(text, paren)
        semi = text.find(";", end + 1)   # limitar ao statement atual (não invadir o próximo CREATE)
        tail = text[end + 1: semi if semi != -1 else len(text)]
        cols = _parse_cols(coldef)
        # PRIMARY INDEX / UNIQUE PRIMARY INDEX
        unique_pi = bool(re.search(r"UNIQUE\s+PRIMARY\s+INDEX", tail, re.IGNORECASE))
        pi_cols = _index_cols(tail, r"PRIMARY\s+INDEX")
        # PARTITION BY RANGE_N/CASE_N (PPI) → colunas de partição
        part_cols: list[str] = []
        for pm in re.finditer(r"(?:RANGE_N|CASE_N)\s*\(\s*[`\"]?([A-Za-z_][\w$]*)", tail, re.IGNORECASE):
            if pm.group(1) not in part_cols:
                part_cols.append(pm.group(1))
        tables.append({
            "name": name, "set_kind": set_kind, "cols": cols,
            "pi_cols": pi_cols, "unique_pi": unique_pi, "part_cols": part_cols,
        })
    return tables


def generate(text: str, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    tables = parse_teradata_ddl(text)
    ddl, flags, recon, unknown = [], ["# Colunas/objetos que exigem revisão manual (Teradata→Databricks)\n"], [], []
    set_tables = []

    for t in tables:
        name = t["name"]
        gold = f"catalog.gold.{norm(name)}"
        lines, num_exact, num_float, dates = [], [], [], []
        colnames = {}
        for c in t["cols"]:
            delta, flag = map_type(c["type"])
            phys = norm(c["name"])
            colnames[c["name"]] = phys
            nn = " NOT NULL" if c["not_null"] else ""
            lines.append(f"  {bq(phys)} {delta}{nn} COMMENT {sq(c['type'])}")
            if flag:
                flags.append(f"- `{name}`.`{c['name']}` ({c['type']}) → {flag}")
                if "desconhecido" in flag:
                    unknown.append(f"{name}.{c['name']}:{c['type']}")
            b = re.match(r"([a-z_]+)", c["type"].lower())
            b = b.group(1) if b else ""
            if b in ("byteint", "smallint", "integer", "int", "bigint", "decimal", "numeric", "number"):
                num_exact.append(phys)
            elif b in ("float", "real", "double"):
                num_float.append(phys)
            elif b in ("date", "timestamp"):
                dates.append(phys)
        # CLUSTER BY = PRIMARY INDEX + colunas de PPI, deduplicado
        cluster = [colnames.get(c, norm(c)) for c in (t["pi_cols"] + t["part_cols"])]
        cluster = list(dict.fromkeys(cluster))
        body = ",\n".join(lines)
        # UNIQUE PRIMARY INDEX → PK RELY (informativo, habilita otimização; não é enforced)
        if t["unique_pi"] and t["pi_cols"]:
            pk_cols = ", ".join(bq(colnames.get(c, norm(c))) for c in t["pi_cols"])
            body += f",\n  CONSTRAINT {bq('pk_' + norm(name))} PRIMARY KEY ({pk_cols}) RELY"
        ct = f"CREATE TABLE IF NOT EXISTS {gold} (\n{body}\n) USING DELTA"
        if cluster:
            ct += f"\nCLUSTER BY ({', '.join(bq(c) for c in cluster)})"
        if t["set_kind"] == "SET":
            ct = ("-- ⚠️ ATENÇÃO: origem era SET TABLE (Teradata rejeita duplicatas exatas de linha).\n"
                  "-- O Delta NÃO tem análogo de SET table → a ingestão DEVE deduplicar explicitamente\n"
                  "--   (ROW_NUMBER() ... QUALIFY = 1  ou  MERGE), ou o resultado pode conter duplicatas.\n"
                  + ct)
            set_tables.append(name)
        ct += ";"
        ddl.append(ct)
        recon.append({"source": name, "target": gold, "keys": [colnames.get(c, norm(c)) for c in t["pi_cols"]][:2],
                      "numeric_exact": num_exact, "numeric_float": num_float, "dates": dates})

    if set_tables:
        flags.insert(1, f"\n## ⚠️ Tabelas SET (dedup obrigatório na ingestão): {', '.join(set_tables)}\n")

    open(os.path.join(outdir, "01_ddl_delta.sql"), "w", encoding="utf-8").write("\n\n".join(ddl))
    open(os.path.join(outdir, "02_type_flags.md"), "w", encoding="utf-8").write("\n".join(flags))
    open(os.path.join(outdir, "03_reconcile_spec.json"), "w", encoding="utf-8").write(
        json.dumps({"float_tolerance_pct": 0.0001, "source_dialect": "teradata", "tables": recon},
                   ensure_ascii=False, indent=1)
    )

    # ── GATES ──
    # (1) anti-contaminação Snowflake na ENTRADA
    snow = sorted({re.sub(r"[\\\b()=]", "", tok).strip()
                   for pat in _SNOWFLAKE_TOKENS
                   for tok in re.findall(pat, text, re.IGNORECASE)} - {""})
    snow_hits = [pat for pat in _SNOWFLAKE_TOKENS if re.search(pat, text, re.IGNORECASE)]
    # (2) opções Teradata vazando no DDL Delta de saída
    ddl_txt = "\n".join(ddl)
    leak = re.search(
        r"\b(FALLBACK|BEFORE\s+JOURNAL|AFTER\s+JOURNAL|CHECKSUM\s*=|MERGEBLOCKRATIO|MAP\s*=\s*TD_MAP|CASESPECIFIC|CHARACTER\s+SET)\b",
        ddl_txt, re.IGNORECASE,
    )
    # (3) identificadores sem backtick
    bad = re.findall(r"[^`(]\b([A-Za-z_]+ [A-Za-z_]+)\b (INT|STRING|BIGINT|TIMESTAMP|TIMESTAMP_NTZ|DECIMAL|BOOLEAN|DOUBLE|TINYINT|SMALLINT|DATE|BINARY)", ddl_txt)
    return {
        "tables": len(tables), "flags": len(flags) - 1, "unknown": unknown,
        "set_tables": set_tables, "snowflake_hits": len(snow_hits), "snowflake_tokens": snow,
        "gate_option_leak": bool(leak), "gate_unquoted": len(bad),
    }


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: python scripts/teradata_generate.py <teradata_ddl.sql> <outdir>", file=sys.stderr)
        return 2
    text = open(sys.argv[1], encoding="utf-8").read()
    rep = generate(text, sys.argv[2])
    print(f"tabelas: {rep['tables']} | colunas flagadas: {rep['flags']} | tipos desconhecidos: {len(rep['unknown'])}")
    if rep["set_tables"]:
        print(f"[info] tabelas SET (dedup obrigatório): {rep['set_tables']}")
    print(f"[gate] contaminação Snowflake na ENTRADA: {rep['snowflake_hits']} (deve ser 0)")
    print(f"[gate] opção Teradata vazando no DDL Delta: {rep['gate_option_leak']} (deve ser False)")
    print(f"[gate] identificador sem backtick: {rep['gate_unquoted']} (deve ser 0)")
    fail = rep["snowflake_hits"] or rep["gate_option_leak"] or rep["gate_unquoted"] or rep["unknown"]
    if fail:
        if rep["snowflake_hits"]:
            print(f"[gate] tokens Snowflake detectados (a 'fonte Teradata' pode NÃO ser Teradata): {rep['snowflake_tokens']}", file=sys.stderr)
        if rep["unknown"]:
            print(f"[gate] tipos Teradata desconhecidos: {rep['unknown']}", file=sys.stderr)
        print("FALHA nos gates — NÃO reporte 'concluído'.", file=sys.stderr)
        return 1
    print(f"OK — artefatos em {sys.argv[2]}/ (01_ddl_delta.sql, 02_type_flags.md, 03_reconcile_spec.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
