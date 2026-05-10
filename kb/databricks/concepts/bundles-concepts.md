# Bundles (DABs) — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** DABs, CI/CD, multi-environment, path resolution

---

## O Que São DABs?

DABs (Declarative Automation Bundles, v0.279.0+) são **declaração pura** de recursos Databricks (jobs, pipelines, dashboards, apps). Nenhum Terraform — native engine apenas.

---

## Estrutura de Projeto

```
project/
├── databricks.yml          # Config principal + targets
├── resources/              # Definições de recursos
│   ├── jobs.yml
│   ├── pipelines.yml
│   └── dashboards.yml
└── src/                    # Código/arquivos
    ├── notebooks/
    ├── dashboards/
    └── app/
```

---

## Path Resolution — Regra Crítica

**Paths dependem da localização do arquivo:**

| Arquivo | Path Format | Exemplo |
|---------|----------|---------|
| `resources/*.yml` | `../src/...` | `../src/dashboards/file.json` |
| `databricks.yml` | `./src/...` | `./src/dashboards/file.json` |
| `resources/nested/job.yml` | `../../src/...` | `../../src/notebooks/etl.py` |

**Por quê:** `resources/jobs.yml` está 1 nível abaixo da raiz → usa `../` para subir.

**Erro mais comum:** `./src/` em `resources/*.yml` — procura em `./resources/src/` (não existe).

---

## Tipos de Recursos

| Recurso | Propósito | Versão Mínima |
|---------|-----------|---------------|
| `jobs` | Orquestração multi-task | 0.279.0+ |
| `pipelines` | SDP/DLT declarativos | 0.279.0+ |
| `dashboards` | AI/BI dashboards | 0.279.0+ |
| `sql_alerts` | Alertas SQL | 0.279.0+ |
| `apps` | Dash/Streamlit apps | 0.279.0+ |

---

## Permissões por Tipo de Recurso

| Recurso | Níveis Disponíveis |
|---------|-------------------|
| **Jobs** | `CAN_VIEW`, `CAN_MANAGE_RUN`, `CAN_MANAGE` |
| **Dashboards** | `CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` |
| **Pipelines** | `CAN_VIEW`, `CAN_MANAGE` |
| **SQL Queries** | `CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE` |
| **Volumes** | Use `grants`, não `permissions` |

**Regra:** Grupo "admins" nunca em `permissions` — tem acesso total automaticamente.

---

## Versões e Gotchas

| Gotcha | Versão | Solução |
|--------|--------|---------|
| `dataset_catalog` / `dataset_schema` em dashboards | >= 0.281.0 | Atualizar CLI ou omitir |
| Apps não aceitam env vars em `databricks.yml` | todas | Env vars em `src/app/app.yaml` |
| Apps requerem `bundle run` após deploy | todas | `databricks bundle run app_key -t dev` |
| Alert schema v2 difere de Jobs | todas | Ver documentação específica de Alerts |

---

## Troubleshooting

| Erro | Causa | Solução |
|------|-------|--------|
| `file not found` | Path incorreto | Use `../src/` em resources/*.yml |
| `Cannot find profile X` | Profile não existe | `databricks configure --profile prod` |
| `undefined references` | Variable não definida | Adicionar default em `variables:` |
| `App not starting` | Deploy sem `bundle run` | `databricks bundle run app_key -t dev` |
| `Permission denied on admins` | Tentativa modificar "admins" | Remover "admins" de permissions |

---

## Checklist Implementação

- [ ] Path resolution validado (../src/ em resources/, ./src/ em databricks.yml)
- [ ] Targets dev/prod definidos em databricks.yml
- [ ] Variáveis catalog/schema parametrizadas
- [ ] Profiles configurados (.databrickscfg)
- [ ] Jobs com retry policy e schedule
- [ ] Dashboards com dataset_catalog/dataset_schema (CLI >= 0.281.0)
- [ ] Apps com env vars em app.yaml
- [ ] Permissions corretas por tipo de recurso
- [ ] Grupo "admins" NUNCA em permissions
- [ ] `bundle validate` passa sem erros
- [ ] `bundle plan` revisto antes deploy
