#!/usr/bin/env python3
"""
reconcile_generate.py — Gerador DETERMINÍSTICO de SQL de reconciliação origem×destino
para migração SQL Server → Databricks (dono: agente `data-quality-steward`).

Base normativa: `kb/migration/concepts/reconciliation.md` (curso oficial Databricks,
04 - Activate / 4.1 Testing & Data Validation, 4.3 Cutover). NÃO escreva o SQL de
reconciliação à mão — rode este gerador (mesmo padrão de `ssas_generate.py`, com gates).

O que emite (correto-por-construção, a partir de um spec JSON de pares de tabela):
  - `reconcile_source.sql`  — T-SQL para rodar no SQL Server (origem)
  - `reconcile_target.sql`  — Databricks SQL para rodar na Gold (destino)
  - `reconcile_report.md`   — o que comparar, tolerâncias e a matriz de rollback

Os 7 parity checks (kb): record count, sum/aggregation, null count, distinct count,
min/max bounds, string checksum (amostra por hash de linha) — comparados manualmente
entre os dois lados. Tolerância: DECIMAL/MONEY exato; FLOAT/DOUBLE relativo (default 0.0001%).

Spec JSON (exemplo):
{
  "float_tolerance_pct": 0.0001,
  "tables": [
    {"source": "dbo.FactInternetSales", "target": "catalog.gold.fact_internet_sales",
     "keys": ["SalesOrderNumber","SalesOrderLineNumber"],
     "numeric_exact": ["OrderQuantity"], "numeric_float": ["UnitPrice","SalesAmount"],
     "dates": ["OrderDate"], "hash_cols": ["SalesOrderNumber","SalesAmount","OrderDate"]}
  ]
}

Uso: python scripts/reconcile_generate.py <spec.json> <dir_saída>
"""

from __future__ import annotations

import json
import os
import sys

# ── quoting por dialeto ───────────────────────────────────────────────────────
def ss(col: str) -> str:
    """Identificador SQL Server: [col]."""
    return "[" + str(col).replace("]", "]]") + "]"


def db(col: str) -> str:
    """Identificador Databricks: `col`."""
    return "`" + str(col).replace("`", "``") + "`"


def dq(col: str) -> str:
    """Identificador ANSI (Teradata/PostgreSQL): "col"."""
    return '"' + str(col).replace('"', '""') + '"'


def _checks_for(t: dict, side: str, float_tol: float, src_dialect: str = "tsql") -> list[str]:
    """Blocos de check para um lado. `src_dialect` define o dialeto da ORIGEM:
    tsql/mssql → colchetes + HASHBYTES + TOP; teradata → aspas-duplas + hash comentado;
    hive/spark/databricks → backtick + md5 + LIMIT. (O destino é sempre Databricks/backtick.)"""
    src_d = str(src_dialect).lower()
    if side == "source":
        dialect = ("tsql" if src_d in ("tsql", "mssql", "sqlserver")
                   else "teradata" if src_d in ("teradata", "td")
                   else "spark")
    else:
        dialect = "spark"
    is_tsql_src = dialect == "tsql"
    q = ss if dialect == "tsql" else dq if dialect == "teradata" else db
    tbl = t["source"] if side == "source" else t["target"]
    keys = t.get("keys", [])
    num_exact = t.get("numeric_exact", [])
    num_float = t.get("numeric_float", [])
    dates = t.get("dates", [])
    hash_cols = t.get("hash_cols", []) or (keys + num_exact + num_float)
    label = t["source"]
    out = [f"-- ===== {label} ({side}) ====="]

    # 1. record count
    out.append(f"SELECT '{label}' AS tabela, 'count' AS check_, COUNT(*) AS v FROM {tbl};")

    # 2. sum (exato + float) — um SELECT com todas as somas
    sums = [f"SUM({q(c)}) AS {q('sum_' + c)}" for c in (num_exact + num_float)]
    if sums:
        out.append(f"SELECT {', '.join(sums)} FROM {tbl};   -- sum (exato: {num_exact} | float±{float_tol}%: {num_float})")

    # 3. null counts (keys + numéricos) — portável nos dois dialetos
    nn = list(dict.fromkeys(keys + num_exact + num_float))  # dedup: chave numérica não repete
    if nn:
        parts = [f"SUM(CASE WHEN {q(c)} IS NULL THEN 1 ELSE 0 END) AS {q('nulls_' + c)}" for c in nn]
        out.append(f"SELECT {', '.join(parts)} FROM {tbl};   -- null counts")

    # 4. distinct das keys
    for k in keys:
        out.append(f"SELECT COUNT(DISTINCT {q(k)}) AS {q('distinct_' + k)} FROM {tbl};")

    # 5. min/max de datas
    for d in dates:
        out.append(f"SELECT MIN({q(d)}) AS {q('min_' + d)}, MAX({q(d)}) AS {q('max_' + d)} FROM {tbl};")

    # 6. string checksum (amostra por hash de linha) — best-effort (normalização difere;
    #    ver kb/migration/concepts/reconciliation.md). Ordena por key para amostra estável.
    if hash_cols and keys:
        key_list = ", ".join(q(k) for k in keys)
        if is_tsql_src:
            concat = " + '|' + ".join(f"ISNULL(CONVERT(NVARCHAR(MAX), {q(c)}), '')" for c in hash_cols)
            out.append(
                f"SELECT TOP 1000 {key_list}, CONVERT(CHAR(32), HASHBYTES('MD5', {concat}), 2) AS row_hash\n"
                f"FROM {tbl} ORDER BY {key_list};   -- amostra de hash (T-SQL / origem SQL Server)"
            )
        elif dialect == "teradata":
            # Teradata não tem MD5 nativo em toda versão (HASHROW não é comparável ao md5 do Spark).
            # Row-hash cross-platform fica como best-effort: use uma UDF MD5 na origem OU compare só
            # os agregados acima (count/sum/null/distinct/min-max), que são portáveis e confiáveis.
            cols_csv = ", ".join(q(c) for c in hash_cols)
            out.append(
                f"-- amostra de hash de linha PULADA no lado Teradata (MD5 não é nativo em toda versão).\n"
                f"--   Opção A: criar UDF MD5 na origem e concatenar {cols_csv} com '|'.\n"
                f"--   Opção B (recomendado): confiar nos agregados acima; hashear só o lado Databricks p/ auditoria interna.\n"
                f"-- SELECT TOP 1000 {key_list} FROM {tbl} ORDER BY {key_list};"
            )
        else:
            # hive/spark/databricks: MESMO md5(concat_ws) nos dois lados → comparável de verdade
            concat = ", ".join(f"COALESCE(CAST({q(c)} AS STRING), '')" for c in hash_cols)
            out.append(
                f"SELECT {key_list}, md5(concat_ws('|', {concat})) AS row_hash\n"
                f"FROM {tbl} ORDER BY {key_list} LIMIT 1000;   -- amostra de hash (Spark/Hive)"
            )
    out.append("")
    return out


def generate(spec: dict, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    tables = spec.get("tables", [])
    float_tol = spec.get("float_tolerance_pct", 0.0001)
    src_dialect = spec.get("source_dialect", "tsql")
    _sd = str(src_dialect).lower()
    src_label = ("SQL Server / T-SQL" if _sd in ("tsql", "mssql", "sqlserver")
                 else "Teradata (aspas-duplas ANSI)" if _sd in ("teradata", "td")
                 else f"{src_dialect} (HiveQL/Spark SQL — backtick)")

    src, tgt = [
        f"-- Reconciliação — LADO ORIGEM ({src_label}). Rode na fonte AINDA em BAU (baseline).",
        "-- Base: kb/migration/concepts/reconciliation.md\n",
    ], [
        "-- Reconciliação — LADO DESTINO (Databricks SQL / Gold).",
        "-- Base: kb/migration/concepts/reconciliation.md\n",
    ]
    for t in tables:
        src += _checks_for(t, "source", float_tol, src_dialect)
        tgt += _checks_for(t, "target", float_tol, src_dialect)

    report = [
        "# Reconciliação origem×destino — como comparar\n",
        "> Gerado por `scripts/reconcile_generate.py`. Rode `reconcile_source.sql` na origem "
        "(SQL Server, **ainda em BAU** = baseline) e `reconcile_target.sql` no destino (Gold), e compare.\n",
        "## Regra das 2 fases (obrigatória)",
        "1. Reconcilie o **snapshot histórico** e **aprove** ANTES de ligar o CDC.",
        "2. Depois, reconcilie **só o delta CDC**. Rodar junto mascara a causa raiz do mismatch.\n",
        "## Tolerâncias",
        f"- `DECIMAL`/`MONEY`: **exato**. `FLOAT`/`DOUBLE`: relativo (**±{float_tol}%**).",
        "- Contagens (count/distinct/null): exato. Datas min/max: exato.\n",
        "## Matriz de rollback (numérica)",
        "| Discrepância | Ação |",
        "|---|---|",
        "| < 0.01% | OK — seguir |",
        "| 0.01–1% | Pausar e investigar |",
        "| > 1% | **Rollback imediato** |",
        "| Falha crítica de dashboard | Rollback imediato |",
        "| Degradação de performance > 50% | Rollback se não resolver em 1h |\n",
        f"## Tabelas reconciliadas ({len(tables)})",
    ]
    for t in tables:
        report.append(f"- `{t['source']}` → `{t['target']}` (keys: {', '.join(t.get('keys', []))})")

    open(os.path.join(outdir, "reconcile_source.sql"), "w", encoding="utf-8").write("\n".join(src))
    open(os.path.join(outdir, "reconcile_target.sql"), "w", encoding="utf-8").write("\n".join(tgt))
    open(os.path.join(outdir, "reconcile_report.md"), "w", encoding="utf-8").write("\n".join(report))

    # ── GATES ──
    missing_keys = [t.get("source", "?") for t in tables if not t.get("keys")]
    no_target = [t.get("source", "?") for t in tables if not t.get("target")]
    return {
        "tables": len(tables),
        "gate_missing_keys": missing_keys,
        "gate_missing_target": no_target,
    }


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: python scripts/reconcile_generate.py <spec.json> <dir_saída>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    rep = generate(spec, sys.argv[2])
    print(f"tabelas: {rep['tables']} → reconcile_source.sql + reconcile_target.sql + reconcile_report.md")
    if rep["gate_missing_keys"]:
        # keys são opcionais: sem elas só perdemos distinct-por-chave e hash-por-linha;
        # count/sum/null/min-max continuam válidos. Aviso, não falha.
        print(
            f"[aviso] tabelas SEM keys — só count/sum/null/min-max (sem distinct/hash por chave): "
            f"{rep['gate_missing_keys']}",
            file=sys.stderr,
        )
    if rep["gate_missing_target"]:
        print(f"[gate] tabelas SEM 'target': {rep['gate_missing_target']}", file=sys.stderr)
        print("FALHA nos gates — corrija o spec.", file=sys.stderr)
        return 1
    print(f"OK — artefatos em {sys.argv[2]}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
