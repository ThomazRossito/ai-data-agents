#!/usr/bin/env python3
"""
[DEPRECATED 2026-08-02] Artefato HARDCODED ao cliente BRF Comercial — NÃO reutilizar.
Substituído pelo gerador genérico e testado `scripts/ssas_generate.py` (parse buffer-safe de
qualquer .bim/.vpax + DDL + Metric Views + reconciliação, com 3 gates). Mantido só como
referência histórica.

Parser do modelo tabular SSAS (.bim) para extrair inventário completo.
Salva JSON estruturado em .../output/migracao_brf_comercial_inventario.json
"""

import json
from pathlib import Path

BIM_PATH = Path(
    "/Users/thomaz_rossito/Projects/ai-data-agents/inputs/prj_brf/ssis_arquivo_bim/Comercial.bim"
)
OUT_DIR = Path("/Users/thomaz_rossito/Projects/ai-data-agents/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "migracao_brf_comercial_inventario.json"


def main():
    print(f"Lendo {BIM_PATH} ...")
    with open(BIM_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    model = data.get("model", {})

    # 1. Data Sources
    data_sources = []
    for ds in model.get("dataSources", []):
        data_sources.append(
            {
                "name": ds.get("name"),
                "type": ds.get("type"),
                "protocol": ds.get("connectionDetails", {}).get("protocol"),
                "server": ds.get("connectionDetails", {}).get("address", {}).get("server"),
                "database": ds.get("connectionDetails", {}).get("address", {}).get("database"),
                "authentication_kind": ds.get("credential", {}).get("AuthenticationKind"),
                "username": ds.get("credential", {}).get("Username"),
                "encrypt_connection": ds.get("credential", {}).get("EncryptConnection"),
                "command_timeout": ds.get("options", {}).get("commandTimeout"),
            }
        )

    # 2. Tables
    tables = []
    for tbl in model.get("tables", []):
        t = {
            "name": tbl.get("name"),
            "isHidden": tbl.get("isHidden", False),
            "description": tbl.get("description", ""),
            "columns": [],
            "measures": [],
            "hierarchies": [],
            "partitions": [],
        }
        for col in tbl.get("columns", []):
            t["columns"].append(
                {
                    "name": col.get("name"),
                    "dataType": col.get("dataType"),
                    "isHidden": col.get("isHidden", False),
                    "sourceColumn": col.get("sourceColumn"),
                    "description": col.get("description", ""),
                    "sortByColumn": col.get("sortByColumn"),
                }
            )
        for m in tbl.get("measures", []):
            t["measures"].append(
                {
                    "name": m.get("name"),
                    "expression": m.get("expression", ""),
                    "formatString": m.get("formatString", ""),
                    "displayFolder": m.get("displayFolder", ""),
                    "description": m.get("description", ""),
                    "isHidden": m.get("isHidden", False),
                }
            )
        for h in tbl.get("hierarchies", []):
            levels = []
            for lvl in h.get("levels", []):
                levels.append(
                    {
                        "name": lvl.get("name"),
                        "ordinal": lvl.get("ordinal"),
                        "column": lvl.get("column"),
                    }
                )
            t["hierarchies"].append(
                {
                    "name": h.get("name"),
                    "levels": levels,
                    "isHidden": h.get("isHidden", False),
                }
            )
        for p in tbl.get("partitions", []):
            src = p.get("source", {})
            t["partitions"].append(
                {
                    "name": p.get("name"),
                    "type": src.get("type"),
                    "expression": "\n".join(src.get("expression", []))
                    if isinstance(src.get("expression"), list)
                    else src.get("expression", ""),
                }
            )
        tables.append(t)

    # 3. Relationships
    relationships = []
    for rel in model.get("relationships", []):
        relationships.append(
            {
                "name": rel.get("name"),
                "fromTable": rel.get("fromTable"),
                "fromColumn": rel.get("fromColumn"),
                "toTable": rel.get("toTable"),
                "toColumn": rel.get("toColumn"),
                "isActive": rel.get("isActive", True),
                "crossFilteringBehavior": rel.get("crossFilteringBehavior", "singleDirection"),
            }
        )

    # 4. Roles
    roles = []
    for role in model.get("roles", []):
        r = {
            "name": role.get("name"),
            "description": role.get("description", ""),
            "members": [m.get("memberName", m.get("memberId")) for m in role.get("members", [])],
            "tablePermissions": [],
        }
        for tp in role.get("tablePermissions", []):
            r["tablePermissions"].append(
                {
                    "table": tp.get("name"),
                    "filter": tp.get("filter", ""),
                    "metadataPermission": tp.get("metadataPermission", "read"),
                }
            )
        roles.append(r)

    # 5. Perspectives
    perspectives = []
    for persp in model.get("perspectives", []):
        perspectives.append(
            {
                "name": persp.get("name"),
                "tables": [t.get("name") for t in persp.get("tables", [])],
            }
        )

    # 6. KPIs (measures marcadas como KPIs via annotations ou propriedades específicas?)
    # No TOM/JSON 1500, KPIs costumam estar em measures com property "kpi" ou anotação. Vamos verificar.
    kpis = []
    for tbl in model.get("tables", []):
        for m in tbl.get("measures", []):
            if m.get("kpi"):
                kpis.append(
                    {
                        "table": tbl.get("name"),
                        "name": m.get("name"),
                        "targetExpression": m.get("kpi", {}).get("targetExpression", ""),
                        "statusExpression": m.get("kpi", {}).get("statusExpression", ""),
                        "trendExpression": m.get("kpi", {}).get("trendExpression", ""),
                    }
                )

    # 7. Translations
    translations = []
    for tr in model.get("translations", []):
        translations.append(
            {
                "language": tr.get("language"),
                "name": tr.get("name"),
            }
        )

    # 8. Cultures
    cultures = []
    for c in model.get("cultures", []):
        cultures.append(
            {
                "name": c.get("name"),
                "linguisticMetadata": c.get("linguisticMetadata", {}),
            }
        )

    result = {
        "model_name": model.get("name"),
        "compatibilityLevel": data.get("compatibilityLevel"),
        "culture": model.get("culture"),
        "discourageImplicitMeasures": model.get("discourageImplicitMeasures"),
        "dataSources": data_sources,
        "tables": tables,
        "relationships": relationships,
        "roles": roles,
        "perspectives": perspectives,
        "kpis": kpis,
        "translations": translations,
        "cultures": cultures,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Inventário salvo em {OUT_JSON}")
    print("Resumo:")
    print(f"  DataSources: {len(data_sources)}")
    print(f"  Tables: {len(tables)}")
    print(f"  Relationships: {len(relationships)}")
    print(f"  Roles: {len(roles)}")
    print(f"  Perspectives: {len(perspectives)}")
    print(f"  KPIs: {len(kpis)}")
    print(f"  Translations: {len(translations)}")
    print(f"  Cultures: {len(cultures)}")
    total_measures = sum(len(t["measures"]) for t in tables)
    total_hierarchies = sum(len(t["hierarchies"]) for t in tables)
    print(f"  Measures: {total_measures}")
    print(f"  Hierarchies: {total_hierarchies}")


if __name__ == "__main__":
    main()
