#!/usr/bin/env python3
"""
sqlserver_generate.py — Gerador DETERMINÍSTICO SQL Server → Databricks (dono: agente
`sqlserver-to-databricks`). Mesmo padrão de `ssas_generate.py`: correto-por-construção,
com gates que falham o build. NÃO escreva o DDL à mão.

Base normativa: `kb/migration/index.md` + `kb/sql-patterns/concepts/tsql-conversion-catalog.md`
(curso oficial Databricks, 03 - Execute / 3.1 Schema & DDL Conversion). Mapa de tipos verificado.

Entrada: JSON de schema (exportável do `migration_source` MCP / `information_schema`):
{
  "model": "AdventureWorks",
  "tables": [
    {"schema":"dbo","name":"FactInternetSales",
     "columns":[
       {"name":"SalesOrderNumber","type":"nvarchar(20)","nullable":false},
       {"name":"OrderQuantity","type":"int","nullable":true},
       {"name":"SalesAmount","type":"money","nullable":true},
       {"name":"OrderDate","type":"datetime2","nullable":true},
       {"name":"rowguid","type":"uniqueidentifier","nullable":true},
       {"name":"SalesKey","type":"bigint","nullable":false,"identity":true}],
     "primary_key":["SalesOrderNumber"]}
  ]
}

Saída (em <outdir>/):
  01_ddl_databricks.sql   — CREATE TABLE Gold (tipos Databricks, IDENTITY, PK RELY, COMMENT do tipo SS)
  02_type_flags.md        — colunas que exigem revisão manual (uniqueidentifier, geography, ...)
  03_reconcile_spec.json  — spec pronto p/ scripts/reconcile_generate.py (keys=PK, numéricos, datas)

Uso: python scripts/sqlserver_generate.py <schema.json> <outdir>
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

# ── Mapa de tipos SQL Server → Delta (verificado: curso 3.1 + web ago/2026) ───
# valor: (tipo_delta, flag_revisão_manual_ou_None)
_SIMPLE = {
    "int": ("INT", None),
    "integer": ("INT", None),
    "bigint": ("BIGINT", None),
    "smallint": ("SMALLINT", None),
    "tinyint": (
        "SMALLINT",
        "TINYINT do SQL Server é 0-255 (unsigned); Databricks TINYINT é signed -128..127 → use SMALLINT",
    ),
    "bit": ("BOOLEAN", None),
    "boolean": ("BOOLEAN", None),
    "float": ("DOUBLE", None),
    "real": ("FLOAT", None),
    "money": ("DECIMAL(19,4)", None),
    "smallmoney": ("DECIMAL(10,4)", None),
    "date": ("DATE", None),
    "datetime": ("TIMESTAMP", None),
    "datetime2": ("TIMESTAMP", None),
    "smalldatetime": ("TIMESTAMP", None),
    "datetimeoffset": ("STRING", "sem tz-aware nativo — STRING ou TIMESTAMP + coluna de offset"),
    "time": ("STRING", "sem TIME nativo — STRING 'HH:MM:SS'"),
    "char": ("STRING", None),
    "nchar": ("STRING", None),
    "varchar": ("STRING", None),
    "nvarchar": ("STRING", None),
    "text": ("STRING", "deprecated"),
    "ntext": ("STRING", "deprecated"),
    "binary": ("BINARY", None),
    "varbinary": ("BINARY", None),
    "image": ("BINARY", "deprecated"),
    "uniqueidentifier": ("STRING", "GUID → STRING(36); novos valores via uuid()"),
    "xml": ("STRING", "parse via XPath / funções JSON"),
    "hierarchyid": ("STRING", "reimplementar hierarquia com recursive CTE"),
    "geography": ("STRING", "WKT/GeoJSON + funções H3"),
    "geometry": ("STRING", "WKT/GeoJSON + funções H3"),
    "sql_variant": ("STRING", "inspecionar uso real; considerar VARIANT"),
    "rowversion": ("BIGINT", "NÃO é data — contador de versão; considerar dropar"),
    "timestamp": ("BIGINT", "SQL Server 'timestamp' = rowversion (NÃO é data) — dropar ou BIGINT"),
}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower() or "col"


def bq(name: str) -> str:
    return "`" + str(name).replace("`", "``") + "`"


def sq(name: str) -> str:
    return "'" + str(name).replace("'", "''") + "'"


def map_type(ss_type: str) -> tuple[str, str | None]:
    """SQL Server type (com params) → (tipo Delta, flag|None)."""
    t = (ss_type or "").strip().lower()
    base = re.match(r"([a-z_]+)", t)
    base = base.group(1) if base else t
    params = re.search(r"\(([^)]*)\)", t)
    # decimal/numeric preservam precisão
    if base in ("decimal", "numeric"):
        p = params.group(1) if params else "38,0"
        return (f"DECIMAL({p})", None)
    if base in _SIMPLE:
        return _SIMPLE[base]
    return ("STRING", f"tipo SQL Server desconhecido '{ss_type}' → STRING (fallback — revisar)")


def generate(schema: dict, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    prefix = norm(schema.get("model") or "sqlserver")

    def gold(sch: str, name: str) -> str:
        return f"catalog.gold.{prefix}_{norm(name)}"

    ddl, flags, recon_tables = [], ["# Colunas que exigem revisão manual\n"], []
    unknown = []

    for t in schema.get("tables", []):
        sch, name = t.get("schema", "dbo"), t.get("name", "table")
        cols = t.get("columns", [])
        pk = t.get("primary_key", []) or []
        lines, num_exact, num_float, dates = [], [], [], []
        for c in cols:
            cn, ctype = c.get("name"), c.get("type", "")
            delta, flag = map_type(ctype)
            col_def = f"  {bq(norm(cn))} {delta}"
            if c.get("identity"):
                col_def += " GENERATED BY DEFAULT AS IDENTITY"  # BY DEFAULT na carga; trocar p/ ALWAYS pós-migração
            if not c.get("nullable", True):
                col_def += " NOT NULL"
            col_def += f" COMMENT {sq(ctype)}"
            lines.append(col_def)
            if flag:
                flags.append(f"- `{sch}.{name}`.`{cn}` ({ctype}) → {flag}")
                if "desconhecido" in flag:
                    unknown.append(f"{sch}.{name}.{cn}:{ctype}")
            # classificar p/ reconciliação
            base = re.match(r"([a-z_]+)", ctype.lower())
            base = base.group(1) if base else ""
            if base in (
                "int",
                "integer",
                "bigint",
                "smallint",
                "tinyint",
                "decimal",
                "numeric",
                "money",
                "smallmoney",
            ):
                num_exact.append(norm(cn))
            elif base in ("float", "real"):
                num_float.append(norm(cn))
            elif base in ("date", "datetime", "datetime2", "smalldatetime"):
                dates.append(norm(cn))
        ct = f"CREATE TABLE IF NOT EXISTS {gold(sch, name)} (\n" + ",\n".join(lines)
        if pk:
            ct += f",\n  CONSTRAINT {bq('pk_' + norm(name))} PRIMARY KEY ({', '.join(bq(norm(k)) for k in pk)}) RELY"
        ct += "\n) USING DELTA;"
        ddl.append(ct)
        recon_tables.append(
            {
                "source": f"{sch}.{name}",
                "target": gold(sch, name),
                "keys": [norm(k) for k in pk],
                "numeric_exact": num_exact,
                "numeric_float": num_float,
                "dates": dates,
            }
        )

    open(os.path.join(outdir, "01_ddl_databricks.sql"), "w", encoding="utf-8").write(
        "\n\n".join(ddl)
    )
    open(os.path.join(outdir, "02_type_flags.md"), "w", encoding="utf-8").write("\n".join(flags))
    open(os.path.join(outdir, "03_reconcile_spec.json"), "w", encoding="utf-8").write(
        json.dumps(
            {"float_tolerance_pct": 0.0001, "source_dialect": "mssql", "tables": recon_tables},
            ensure_ascii=False,
            indent=1,
        )
    )

    # ── GATES ──
    no_pk = [
        f"{t['source']}" for t, rt in zip(schema.get("tables", []), recon_tables) if not rt["keys"]
    ]
    # gate anti-drift: toda coluna com espaço no DDL tem de estar em backtick (nunca deve falhar aqui)
    ddl_txt = "\n".join(ddl)
    bad = re.findall(
        r"[^`\w]([A-Za-z_]+ [A-Za-z_]+) (INT|STRING|BIGINT|TIMESTAMP|DECIMAL|BOOLEAN|DOUBLE|DATE)",
        ddl_txt,
    )
    return {
        "tables": len(ddl),
        "flags": len(flags) - 1,
        "unknown_types": unknown,
        "no_pk": no_pk,
        "gate_unquoted": len(bad),
    }


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: python scripts/sqlserver_generate.py <schema.json> <outdir>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        schema = json.load(f)
    rep = generate(schema, sys.argv[2])
    print(
        f"tabelas: {rep['tables']} | colunas flagadas (revisão): {rep['flags']} | tipos desconhecidos: {len(rep['unknown_types'])}"
    )
    print(f"[gate] identificador sem backtick no DDL: {rep['gate_unquoted']} (deve ser 0)")
    if rep["no_pk"]:
        print(
            f"[aviso] tabelas SEM primary key (reconciliação por chave limitada): {rep['no_pk']}",
            file=sys.stderr,
        )
    if rep["gate_unquoted"] or rep["unknown_types"]:
        if rep["unknown_types"]:
            print(
                f"[gate] tipos desconhecidos (revisar o mapa): {rep['unknown_types']}",
                file=sys.stderr,
            )
        print("FALHA nos gates — NÃO reporte 'concluído'.", file=sys.stderr)
        return 1
    print(
        f"OK — artefatos em {sys.argv[2]}/ (01_ddl_databricks.sql, 02_type_flags.md, 03_reconcile_spec.json)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
