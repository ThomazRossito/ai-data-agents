#!/usr/bin/env python3
"""
ssas_generate.py — Gerador DETERMINÍSTICO e AGNÓSTICO de artefatos Databricks a
partir de um modelo tabular SSAS (.bim / TMSL JSON).

Papel (fronteira do especialista ssas-to-databricks, decidida em 2026-07-26):
  AUTO-GERA (correto-por-construção, dirigido pelos metadados do modelo):
    - CREATE TABLE (schema-only) por tabela, com mapa SSAS dataType → tipo Delta
    - Metric Views das medidas SIMPLES (SUM/COUNT/DISTINCTCOUNT/MIN/MAX/AVERAGE de
      1 coluna e DIVIDE de 2 medidas simples), usando o **sourceColumn** físico e
      backtick em TODO identificador
    - Joins das Metric Views derivados dos relacionamentos ativos
    - Scaffold de RLS a partir dos roles/tablePermissions
  FLAGA (não converte — exige reescrita humana/especialista):
    - Medidas complexas (CALCULATE/VAR/FILTER/SUMMARIZE/SWITCH/time-intelligence…)
    - Medidas simples cuja coluna NÃO resolve p/ um sourceColumn real
  DELEGA (fora do escopo — é de outro especialista):
    - Ingestão ETL (fonte → Bronze→Silver→Gold) → databricks-engineer

Por que agnóstico: nada é hardcoded ao negócio. Tudo vem do .bim (nomes, tipos,
sourceColumn, relacionamentos, roles). O mesmo script serve empresa 1, 2 … N.

Correto-por-construção: o gerador só emite referência de coluna que EXISTE como
sourceColumn no modelo; e faz backtick em todo identificador. Ao final roda gates
de sanidade e sai com código != 0 se algum falhar (nunca "conclui" com SQL quebrado).

Uso:
    python scripts/ssas_generate.py <caminho .bim ou diretório> <dir_saída>
"""

from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys
import unicodedata

# ── Mapa fixo SSAS/TMSL dataType → tipo Delta (agnóstico) ─────────────────────
DELTA_TYPE = {
    "string": "STRING",
    "int64": "BIGINT",
    "double": "DOUBLE",
    "dateTime": "TIMESTAMP",
    "decimal": "DECIMAL(38,4)",
    "boolean": "BOOLEAN",
    "binary": "BINARY",
    "automatic": "STRING",  # fallback — revisar
}

# Aggregações de 1 coluna consideradas conversão SIMPLES e segura.
_RE_AGG = re.compile(
    r"^\s*(SUM|COUNT|COUNTA|COUNTROWS|DISTINCTCOUNT|MIN|MAX|AVERAGE)"
    r"\s*\(\s*'?([^'\[\]]+?)'?\s*\[([^\]]+)\]\s*\)\s*$",
    re.IGNORECASE,
)
# DIVIDE de duas medidas ([A],[B]) → try_divide(MEASURE(A), MEASURE(B)).
_RE_DIV = re.compile(r"^\s*DIVIDE\s*\(\s*\[([^\]]+)\]\s*,\s*\[([^\]]+)\]\s*\)\s*$", re.IGNORECASE)
# Palavras que marcam DAX complexo (não convertível às cegas).
_RE_COMPLEX = re.compile(
    r"\b(CALCULATE|CALCULATETABLE|FILTER|VAR\s|DATEADD|SAMEPERIODLASTYEAR|TOTALYTD|"
    r"TOTALMTD|DATESYTD|PARALLELPERIOD|ALLEXCEPT|ALL\s*\(|EARLIER|RANKX|TOPN|"
    r"SUMMARIZE|GENERATE|USERELATIONSHIP|SWITCH)\b",
    re.IGNORECASE,
)


def norm(name: str) -> str:
    """snake_case determinístico, sem acento, seguro p/ SQL (mesmo assim usamos backtick)."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower() or "col"


def bq(name: str) -> str:
    """Backtick-quote — torna QUALQUER identificador válido no Databricks."""
    return "`" + str(name).replace("`", "``") + "`"


def sq(name: str) -> str:
    """Single-quote seguro p/ COMMENT (escapa aspas simples)."""
    return "'" + str(name).replace("'", "''") + "'"


def _expr(raw) -> str:
    return ("\n".join(raw) if isinstance(raw, list) else (raw or "")).strip()


def parse_bim(path: str) -> dict:
    """Parse buffer-safe do .bim; mantém o sourceColumn (nome físico) e o expr COMPLETO."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    model = data.get("model", {})
    tables = []
    for t in model.get("tables", []):
        cols = [
            {
                "name": c.get("name"),
                "src": c.get("sourceColumn") or c.get("name"),
                "dtype": c.get("dataType"),
            }
            for c in t.get("columns", [])
        ]
        meas = [
            {"name": m.get("name"), "expr": _expr(m.get("expression"))}
            for m in t.get("measures", [])
        ]
        p0 = (t.get("partitions") or [{}])[0].get("source", {})
        mfrom = re.search(
            r"FROM\s+\[?([A-Za-z0-9_]+)\]?\.\[?([A-Za-z0-9_]+)\]?",
            _expr(p0.get("expression")),
            re.IGNORECASE,
        )
        tables.append(
            {
                "name": t.get("name"),
                "cols": cols,
                "meas": meas,
                "src_table": f"{mfrom.group(1)}.{mfrom.group(2)}" if mfrom else None,
            }
        )
    rels = [
        {
            "ft": r.get("fromTable"),
            "fc": r.get("fromColumn"),
            "tt": r.get("toTable"),
            "tc": r.get("toColumn"),
            "active": r.get("isActive", True),
        }
        for r in model.get("relationships", [])
    ]
    roles = [
        {
            "name": ro.get("name"),
            "perms": [
                {"t": tp.get("name"), "f": _expr(tp.get("filter"))}
                for tp in ro.get("tablePermissions", [])
            ],
        }
        for ro in model.get("roles", [])
    ]
    return {"model": model.get("name") or "model", "tables": tables, "rels": rels, "roles": roles}


def generate(model: dict, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    prefix = norm(model["model"])

    def gold(tbl: str) -> str:
        return f"catalog.gold.{prefix}_{norm(tbl)}"

    tbls = {t["name"]: t for t in model["tables"]}
    colsrc = {(t["name"], c["name"]): norm(c["src"]) for t in model["tables"] for c in t["cols"]}

    # 1) CREATE TABLE (schema-only) — só tabelas com colunas físicas.
    ddl = []
    for t in model["tables"]:
        if not t["cols"]:
            continue
        lines = [
            f"  {bq(norm(c['src']))} {DELTA_TYPE.get(c['dtype'], 'STRING')} COMMENT {sq(c['name'])}"
            for c in t["cols"]
        ]
        ddl.append(
            f"CREATE TABLE IF NOT EXISTS {gold(t['name'])} (\n"
            + ",\n".join(lines)
            + "\n) USING DELTA;"
        )

    # 2) Metric Views das medidas simples.
    mv = collections.defaultdict(list)  # fact -> [(measure, sql_expr)]
    m_fact = {}  # measure -> fact (p/ resolver DIVIDE)
    flagged = []  # (measure, motivo)
    for t in model["tables"]:
        for meas in t["meas"]:
            e, nm = meas["expr"], meas["name"]
            g = _RE_AGG.match(e)
            if g and g.group(2) in tbls and (g.group(2), g.group(3)) in colsrc:
                fact = g.group(2)
                mv[fact].append(
                    (nm, f"{g.group(1).upper()}(source.{bq(colsrc[(fact, g.group(3))])})")
                )
                m_fact[nm] = fact
            elif _RE_COMPLEX.search(e):
                flagged.append((nm, "DAX complexo"))
            else:
                flagged.append((nm, "não resolvida p/ coluna física"))
    # DIVIDE de duas medidas simples do mesmo fato.
    for t in model["tables"]:
        for meas in t["meas"]:
            g = _RE_DIV.match(meas["expr"])
            if g and m_fact.get(g.group(1)) and m_fact.get(g.group(1)) == m_fact.get(g.group(2)):
                fact = m_fact[g.group(1)]
                mv[fact].append(
                    (
                        meas["name"],
                        f"try_divide(MEASURE({bq(g.group(1))}), MEASURE({bq(g.group(2))}))",
                    )
                )
                flagged = [(n, r) for (n, r) in flagged if n != meas["name"]]

    def mv_yaml(fact: str, items: list) -> str:
        joins = []
        for r in model["rels"]:
            if (
                r["ft"] == fact
                and r["active"]
                and (fact, r["fc"]) in colsrc
                and (r["tt"], r["tc"]) in colsrc
            ):
                dn = norm(r["tt"])
                joins.append(
                    f"    - name: {dn}\n      source: {gold(r['tt'])}\n"
                    f"      on: source.{bq(colsrc[(fact, r['fc'])])} = {dn}.{bq(colsrc[(r['tt'], r['tc'])])}"
                )
        meas_y = "\n".join(f"    - name: {bq(n)}\n      expr: {ex}" for n, ex in items)
        j = ("  joins:\n" + "\n".join(joins) + "\n") if joins else ""
        view = f"catalog.gold.mv_{prefix}_{norm(fact)}"
        return (
            f"CREATE OR REPLACE VIEW {view}\nWITH METRICS LANGUAGE YAML AS $$\n"
            f"  version: 1.1\n  source: {gold(fact)}\n{j}  measures:\n{meas_y}\n$$;"
        )

    mvs = [mv_yaml(f, items) for f, items in mv.items()]

    # 3) RLS scaffold — template por role (revisão humana obrigatória do mapeamento e-mail→UPN).
    rls = ["-- RLS scaffold (revisar: mapear e-mail SSAS USERNAME() → current_user() do Entra ID)"]
    for r in model["roles"]:
        tabs = (
            ", ".join(sorted({p["t"] for p in r["perms"] if p.get("t")}))
            or "(sem tablePermissions)"
        )
        rls.append(f"-- Role '{r['name']}': {len(r['perms'])} filtro(s) sobre {tabs}")

    # 4) Flagged (complexas) — documento honesto.
    cats = collections.Counter(r for _, r in flagged)
    flag_md = ["# Medidas NÃO convertidas — reescrita manual/especialista\n"]
    flag_md.append(f"Total flagadas: {len(flagged)}\n")
    for c, n in cats.most_common():
        flag_md.append(f"- {c}: {n}")
    flag_md.append("\n| Medida | Motivo |\n|---|---|")
    for nm, r in sorted(flagged):
        flag_md.append(f"| {nm} | {r} |")

    # 5) Reconciliação origem×destino — queries determinísticas (EXECUTAR no ambiente; sem dados aqui).
    recon = [
        "-- Reconciliação origem×destino — rode em CADA lado e compare (somas: tolerância ±0.01%).",
        "-- Origem = fonte (ex.: Synapse, nomes de coluna de origem); Destino = Gold Delta (abaixo).",
        "-- ⚠️ Medida legada agregada (VertiPaq) × grão atômico Gold: 1:1 pode não bater no grão.\n",
    ]
    for t in model["tables"]:
        if not t["cols"]:
            continue
        g = gold(t["name"])
        src_hint = (
            f"   -- origem: SELECT COUNT(*) FROM {t['src_table']};" if t.get("src_table") else ""
        )
        recon.append(f"-- === {t['name']} ===")
        recon.append(f"SELECT COUNT(*) AS n FROM {g};{src_hint}")
        nums = [c for c in t["cols"] if c["dtype"] in ("double", "decimal")]
        if nums and ("fat" in norm(t["name"]) or t["meas"]):
            sums = ", ".join(
                f"SUM({bq(norm(c['src']))}) AS {bq('sum_' + norm(c['src']))}" for c in nums[:8]
            )
            recon.append(f"SELECT {sums} FROM {g};")
        dates = [c for c in t["cols"] if c["dtype"] == "dateTime"]
        if dates:
            mm = ", ".join(
                f"MIN({bq(norm(c['src']))}) AS {bq('min_' + norm(c['src']))}, "
                f"MAX({bq(norm(c['src']))}) AS {bq('max_' + norm(c['src']))}"
                for c in dates[:3]
            )
            recon.append(f"SELECT {mm} FROM {g};")
        recon.append("")

    # ── grava ──
    open(os.path.join(outdir, "01_ddl_gold.sql"), "w", encoding="utf-8").write("\n\n".join(ddl))
    open(os.path.join(outdir, "02_metric_views_simples.sql"), "w", encoding="utf-8").write(
        "\n\n".join(mvs)
    )
    open(os.path.join(outdir, "04_rls_scaffold.sql"), "w", encoding="utf-8").write("\n".join(rls))
    open(os.path.join(outdir, "03_medidas_flagadas.md"), "w", encoding="utf-8").write(
        "\n".join(flag_md)
    )
    open(os.path.join(outdir, "05_reconciliation.sql"), "w", encoding="utf-8").write(
        "\n".join(recon)
    )

    # ── GATES de sanidade (correto-por-construção) ──
    mv_txt = "\n\n".join(mvs)
    bad_space = re.findall(r"source\.[A-Za-z]+ [A-Za-z]", mv_txt)  # coluna c/ espaço SEM backtick
    srcs = set(re.findall(r"source: (catalog\.gold\.[a-z0-9_]+)", mv_txt))
    ddl_tables = set(
        re.findall(r"CREATE TABLE IF NOT EXISTS (catalog\.gold\.[a-z0-9_]+)", "\n\n".join(ddl))
    )
    missing = srcs - ddl_tables

    # Gate anti-drift: TODA coluna referenciada numa Metric View (source.`x` ou dim.`x`)
    # tem de existir como coluna no CREATE TABLE da tabela correspondente. Foi ESTE o bug
    # que o gerador hand-rolado do agente introduziu (MV prefixava a coluna, DDL não).
    gold_cols = {
        gold(t["name"]): {norm(c["src"]) for c in t["cols"]} for t in model["tables"] if t["cols"]
    }
    col_mismatch = []
    for block in mvs:
        sm = re.search(r"source: (catalog\.gold\.[a-z0-9_]+)", block)
        if not sm:
            continue
        alias2tab = {"source": sm.group(1)}
        for jm in re.finditer(r"- name: (\w+)\n\s+source: (catalog\.gold\.[a-z0-9_]+)", block):
            alias2tab[jm.group(1)] = jm.group(2)
        for rm in re.finditer(r"(\w+)\.`([a-z0-9_]+)`", block):  # MEASURE(`x`) não casa (sem '.')
            tab = alias2tab.get(rm.group(1))
            if tab and rm.group(2) not in gold_cols.get(tab, set()):
                col_mismatch.append(f"{rm.group(1)}.{rm.group(2)}")

    return {
        "ddl": len(ddl),
        "mvs": len(mvs),
        "converted": sum(len(v) for v in mv.values()),
        "flagged": len(flagged),
        "gate_unquoted_space": len(bad_space),
        "gate_mv_without_table": len(missing),
        "gate_mv_col_not_in_ddl": len(col_mismatch),
        "missing_tables": sorted(missing),
        "col_mismatch": sorted(set(col_mismatch))[:12],
    }


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: python scripts/ssas_generate.py <.bim ou dir> <dir_saída>", file=sys.stderr)
        return 2
    src, outdir = sys.argv[1], sys.argv[2]
    bims = [src] if src.endswith(".bim") else glob.glob(f"{src}/**/*.bim", recursive=True)
    if not bims:
        print(f"nenhum .bim encontrado em {src}", file=sys.stderr)
        return 2
    model = parse_bim(bims[0])
    rep = generate(model, outdir)
    print(
        f"CREATE TABLE: {rep['ddl']} | Metric Views: {rep['mvs']} "
        f"| medidas simples convertidas: {rep['converted']} | flagadas: {rep['flagged']}"
    )
    print(
        f"[gate] identificador com espaço sem backtick: {rep['gate_unquoted_space']} (deve ser 0)"
    )
    print(f"[gate] MV sem CREATE TABLE correspondente: {rep['gate_mv_without_table']} (deve ser 0)")
    print(
        f"[gate] coluna de MV que não existe no DDL: {rep['gate_mv_col_not_in_ddl']} (deve ser 0)"
    )
    if rep["gate_unquoted_space"] or rep["gate_mv_without_table"] or rep["gate_mv_col_not_in_ddl"]:
        print("FALHA nos gates — NÃO reporte 'concluído'.", file=sys.stderr)
        if rep["missing_tables"]:
            print("  tabelas faltando:", rep["missing_tables"], file=sys.stderr)
        if rep["col_mismatch"]:
            print("  colunas de MV fora do DDL:", rep["col_mismatch"], file=sys.stderr)
        return 1
    print(
        f"OK — artefatos em {outdir}/ (01_ddl_gold.sql, 02_metric_views_simples.sql, "
        f"03_medidas_flagadas.md, 04_rls_scaffold.sql, 05_reconciliation.sql)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
