#!/usr/bin/env python3
"""
hive_generate.py — Gerador DETERMINÍSTICO Hive DDL → Databricks/Delta (dono: agente
`hadoop-to-databricks`). Mesmo padrão de `ssas_generate.py`/`sqlserver_generate.py`:
correto-por-construção, com gates que falham o build. NÃO escreva o DDL à mão.

Base normativa: `kb/hadoop-migration/concepts/hive-ddl-conversion.md` (curso oficial
Databricks Hadoop→Databricks, 03 - Execute / 3.1). Mapa de tipos = Apache Hive Language
Manual (verificado: Hive FLOAT = 32-bit single → Delta FLOAT; DOUBLE = 64-bit → DOUBLE;
NÃO usar o "FLOAT é 64-bit" que aparece no arquivo 4.1 do curso — é resíduo do template
SQL Server, incorreto).

Entrada: arquivo .sql com um ou mais `CREATE [EXTERNAL] TABLE` do Hive (ex.: saída de
`beeline -e "SHOW CREATE TABLE ..."`).

Saída (em <outdir>/):
  01_ddl_delta.sql        — CREATE TABLE Delta (tipos mapeados, CLUSTER BY de partição+bucket,
                            COMMENT do tipo Hive; SerDe/STORED AS/TBLPROPERTIES/LOCATION removidos)
  02_type_flags.md        — colunas que exigem revisão (uniontype, tipos desconhecidos)
  03_reconcile_spec.json  — spec pronto p/ scripts/reconcile_generate.py

Uso: python scripts/hive_generate.py <hive_ddl.sql> <outdir>
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

# ── Mapa de tipos Hive → Delta (Apache Hive Language Manual) ──────────────────
_PRIM = {
    "tinyint": ("TINYINT", None), "smallint": ("SMALLINT", None),
    "int": ("INT", None), "integer": ("INT", None), "bigint": ("BIGINT", None),
    "boolean": ("BOOLEAN", None),
    "float": ("FLOAT", None),      # Hive FLOAT = 32-bit single (NÃO é 64-bit)
    "double": ("DOUBLE", None), "double precision": ("DOUBLE", None),
    "string": ("STRING", None), "binary": ("BINARY", None),
    "date": ("DATE", None), "timestamp": ("TIMESTAMP", None),
    "interval": ("STRING", "Hive INTERVAL — revisar (sem tipo direto)"),
}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower() or "col"


def bq(name: str) -> str:
    return "`" + str(name).replace("`", "``") + "`"


def sq(name: str) -> str:
    return "'" + str(name).replace("'", "''") + "'"


def map_type(hive_type: str) -> tuple[str, str | None]:
    """Tipo Hive (com params/complexos) → (tipo Delta, flag|None)."""
    t = (hive_type or "").strip()
    low = t.lower()
    # complexos: array/map/struct são compatíveis (Spark é superset) — passa quase igual
    if low.startswith("array<") or low.startswith("map<") or low.startswith("struct<"):
        return (t.upper().replace("STRING", "STRING"), None)  # mantém a definição
    if low.startswith("uniontype<"):
        return ("STRING", "UNIONTYPE sem equivalente → STRUCT+tag ou STRING (redesign)")
    # varchar(n)/char(n) → STRING
    if low.startswith("varchar") or low.startswith("char"):
        return ("STRING", None)
    # decimal(p,s)/numeric(p,s)
    m = re.match(r"(decimal|numeric)\s*\(([^)]*)\)", low)
    if m:
        return (f"DECIMAL({m.group(2).replace(' ', '')})", None)
    if low in ("decimal", "numeric"):
        return ("DECIMAL(10,0)", None)
    base = re.match(r"([a-z_ ]+)", low)
    base = base.group(1).strip() if base else low
    if base in _PRIM:
        return _PRIM[base]
    return ("STRING", f"tipo Hive desconhecido '{hive_type}' → STRING (fallback — revisar)")


def _split_top_commas(s: str) -> list[str]:
    """Divide por vírgulas de nível superior (respeita <> e () de tipos complexos)."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _parse_cols(coldef: str) -> list[dict]:
    """Parseia a lista de colunas de dentro do primeiro parêntese do CREATE TABLE."""
    cols = []
    for raw in _split_top_commas(coldef):
        raw = raw.strip()
        if not raw:
            continue
        # nome  tipo  [COMMENT '...']
        m = re.match(r"`?([A-Za-z_][\w]*)`?\s+(.+?)(?:\s+COMMENT\s+'(?:[^']*)')?\s*$", raw, re.S)
        if not m:
            continue
        cols.append({"name": m.group(1), "type": m.group(2).strip()})
    return cols


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


def parse_hive_ddl(text: str) -> list[dict]:
    """Extrai tabelas de um script com CREATE [EXTERNAL] TABLE do Hive."""
    tables = []
    for m in re.finditer(r"CREATE\s+(?:EXTERNAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                         r"`?([\w.]+)`?\s*\(", text, re.IGNORECASE):
        name = m.group(1)
        coldef, end = _extract_paren_block(text, m.end() - 1)
        tail = text[end:end + 2000]  # resto do statement (partition/cluster/stored/tblproperties)
        cols = _parse_cols(coldef)
        part = re.search(r"PARTITIONED\s+BY\s*\(([^)]*)\)", tail, re.IGNORECASE)
        part_cols = []
        part_typed: dict[str, str] = {}  # coluna de partição É tipada no Hive (ex.: order_year INT)
        if part:
            for c in _split_top_commas(part.group(1)):
                mm = re.match(r"`?([A-Za-z_]\w*)`?\s+(.+)$", c.strip())
                if mm:
                    part_cols.append(mm.group(1))
                    part_typed[mm.group(1)] = mm.group(2).strip()
                else:
                    mm2 = re.match(r"`?([A-Za-z_]\w*)`?", c.strip())
                    if mm2:
                        part_cols.append(mm2.group(1))
                        part_typed[mm2.group(1)] = "string"
        buck = re.search(r"CLUSTERED\s+BY\s*\(([^)]*)\)", tail, re.IGNORECASE)
        buck_cols = []
        if buck:
            for c in _split_top_commas(buck.group(1)):
                mm = re.match(r"`?([A-Za-z_]\w*)`?", c.strip())
                if mm:
                    buck_cols.append(mm.group(1))
        tables.append({"name": name, "cols": cols + [{"name": p, "type": part_typed.get(p, "string"), "part": True}
                                                      for p in part_cols
                                                      if p not in {c["name"] for c in cols}],
                       "part_cols": part_cols, "buck_cols": buck_cols})
    return tables


def generate(text: str, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    tables = parse_hive_ddl(text)
    ddl, flags, recon, unknown = [], ["# Colunas que exigem revisão manual (Hive→Databricks)\n"], [], []

    for t in tables:
        name = t["name"]
        gold = f"catalog.gold.{norm(name)}"
        lines, num_exact, num_float, dates = [], [], [], []
        colnames = {}
        for c in t["cols"]:
            delta, flag = map_type(c["type"])
            phys = norm(c["name"])
            colnames[c["name"]] = phys
            lines.append(f"  {bq(phys)} {delta} COMMENT {sq(c['type'])}")
            if flag:
                flags.append(f"- `{name}`.`{c['name']}` ({c['type']}) → {flag}")
                if "desconhecido" in flag:
                    unknown.append(f"{name}.{c['name']}:{c['type']}")
            b = re.match(r"([a-z_]+)", c["type"].lower())
            b = b.group(1) if b else ""
            if b in ("tinyint", "smallint", "int", "integer", "bigint", "decimal", "numeric"):
                num_exact.append(phys)
            elif b in ("float", "double"):
                num_float.append(phys)
            elif b in ("date", "timestamp"):
                dates.append(phys)
        # CLUSTER BY = partição + bucket (Liquid Clustering), deduplicado
        cluster = [colnames.get(c, norm(c)) for c in (t["part_cols"] + t["buck_cols"])]
        cluster = list(dict.fromkeys(cluster))
        ct = f"CREATE TABLE IF NOT EXISTS {gold} (\n" + ",\n".join(lines) + "\n) USING DELTA"
        if cluster:
            ct += f"\nCLUSTER BY ({', '.join(bq(c) for c in cluster)})"
        ct += ";"
        ddl.append(ct)
        recon.append({"source": name, "target": gold, "keys": cluster[:2],
                      "numeric_exact": num_exact, "numeric_float": num_float, "dates": dates})

    open(os.path.join(outdir, "01_ddl_delta.sql"), "w", encoding="utf-8").write("\n\n".join(ddl))
    open(os.path.join(outdir, "02_type_flags.md"), "w", encoding="utf-8").write("\n".join(flags))
    open(os.path.join(outdir, "03_reconcile_spec.json"), "w", encoding="utf-8").write(
        json.dumps({"float_tolerance_pct": 0.0001, "source_dialect": "hive", "tables": recon},
                   ensure_ascii=False, indent=1)
    )

    # ── GATES ──
    ddl_txt = "\n".join(ddl)
    stripped = re.search(r"STORED AS|ROW FORMAT|TBLPROPERTIES|SERDE|LOCATION\s+'", ddl_txt, re.IGNORECASE)
    bad_space = re.findall(r"[^`(]\b([A-Za-z_]+ [A-Za-z_]+)\b (INT|STRING|BIGINT|TIMESTAMP|DECIMAL|BOOLEAN|DOUBLE|FLOAT|DATE)", ddl_txt)
    return {"tables": len(tables), "flags": len(flags) - 1, "unknown": unknown,
            "gate_serde_leak": bool(stripped), "gate_unquoted": len(bad_space)}


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: python scripts/hive_generate.py <hive_ddl.sql> <outdir>", file=sys.stderr)
        return 2
    text = open(sys.argv[1], encoding="utf-8").read()
    rep = generate(text, sys.argv[2])
    print(f"tabelas: {rep['tables']} | colunas flagadas: {rep['flags']} | tipos desconhecidos: {len(rep['unknown'])}")
    print(f"[gate] SerDe/STORED AS/LOCATION vazando no DDL Delta: {rep['gate_serde_leak']} (deve ser False)")
    print(f"[gate] identificador sem backtick: {rep['gate_unquoted']} (deve ser 0)")
    if rep["gate_serde_leak"] or rep["gate_unquoted"] or rep["unknown"]:
        if rep["unknown"]:
            print(f"[gate] tipos Hive desconhecidos: {rep['unknown']}", file=sys.stderr)
        print("FALHA nos gates — NÃO reporte 'concluído'.", file=sys.stderr)
        return 1
    print(f"OK — artefatos em {sys.argv[2]}/ (01_ddl_delta.sql, 02_type_flags.md, 03_reconcile_spec.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
