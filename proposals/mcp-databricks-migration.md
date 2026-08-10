# Plano de migração: MCP Databricks → servidor do ai-dev-kit

**Status:** plano (requer ambiente Databricks para executar/testar). **Não aplicado.**
Origem: auditoria 2026-07-26 (achado A1/A2). Decisão delegada ao Claude → **recomendação: adotar o servidor do ai-dev-kit**, porque todo o codebase (docstring, `DATABRICKS_MCP_TOOLS`, subsets aibi/serving/compute, capacidades dos agentes) já foi escrito para ele.

## Contexto (o que já foi feito nesta sessão)

O estado do código foi tornado **honesto** (sem mudança funcional):
- `data_agents/mcp_servers/databricks/server_config.py` — docstring agora declara que o pacote instalado é o **markov-kernel (comunidade)**, não o oficial, e que a tool-list foi escrita para o servidor do ai-dev-kit.
- `.claude/CLAUDE.md` — as 2 menções a "MCP oficial Databricks" foram corrigidas.

Falta a **resolução funcional** — este plano.

## Por que não foi aplicado automaticamente

Trocar o servidor MCP muda o **runtime** (o processo que os agentes chamam) e:
1. o servidor do ai-dev-kit **não está no PyPI** → precisa ser vendorizado ou instalado editável;
2. só dá pra validar contra um **workspace Databricks real** (SQL warehouse, jobs, Unity Catalog);
3. o projeto acabou de passar por um ciclo doloroso de CI — shipar troca de runtime sem teste seria irresponsável.

## Passos (executar com acesso ao Databricks)

1. **Obter o servidor** — do repo `databricks-solutions/ai-dev-kit`:
   - `databricks-mcp-server/` (módulo `databricks_mcp_server`, FastMCP, tools `manage_*`)
   - `databricks-tools-core/` (biblioteca de funções que as tools embrulham)
   Vendorizar em `data_agents/mcp_servers/databricks/vendor/` **ou** instalar editável.

2. **Ajustar dependências** (`pyproject.toml`):
   - Remover/atualizar `databricks-mcp-server>=0.4.4` (que resolve para o pacote markov).
   - Adicionar `fastmcp>=3.2.4,<4` (dep do servidor do ai-dev-kit) + `databricks-tools-core`.
   - Rodar o `pip-audit` do CI depois (o `--ignore-vuln` já tratado no ci.yml permanece válido).

3. **Repontar `run_server.py`** — hoje importa `databricks_mcp.*` (markov). Trocar para
   `from databricks_mcp_server.server import mcp` (ou o entrypoint do ai-dev-kit).
   Revisar o path do log (`databricks_mcp.log` vs. o do novo servidor).

4. **Reconciliar `DATABRICKS_MCP_TOOLS`** — rodar `databricks-mcp-server --list-tools`
   no servidor do ai-dev-kit e alinhar a lista aos nomes reais (`manage_jobs`, `manage_genie`,
   `ask_genie`, `manage_ka`, `manage_mas`, `manage_pipeline`, `manage_dashboard`,
   `manage_serving_endpoint`, `manage_vs_index`, `query_vs_index`, `manage_lakebase_*`,
   `execute_sql`, `execute_sql_multi`, `execute_code`, `get_table_stats_and_schema`…).
   Atualizar os subsets derivados (`_AIBI_`, `_SERVING_`, `_COMPUTE_`, `_READONLY_`).

5. **Validar**:
   - `make health-databricks` (conexão real).
   - `make lint && make type-check && make test` (o `test_mcp_configs.py` valida o formato;
     ajustar se assertar nomes de tools).
   - Um smoke real: um agente `databricks-engineer` chamando `execute_sql` + `ask_genie`.

## Alternativa (se NÃO quiser as capacidades do ai-dev-kit)

Opção (a) do relatório: **assumir o pacote markov**. Encolher `DATABRICKS_MCP_TOOLS`
para as ~20 tools granulares reais do markov (`list_/create_/run_` de clusters, jobs,
workspace, Unity Catalog, `execute_sql`), remover os subsets aibi/serving/pipelines/compute
e ajustar os agentes que os referenciam + testes. **Perde** Genie(via este MCP)/KA/MAS/
pipelines/dashboards. Genie continua coberto pelo MCP customizado `databricks_genie`.

## Verificação da fonte (markov = comunidade)

- PyPI `databricks-mcp-server` 0.4.4: autor Olivier Debeuf De Rijcker / markov-kernel, MIT — https://pypi.org/project/databricks-mcp-server/ · https://github.com/markov-kernel/databricks-mcp
- ai-dev-kit (Field Engineering): https://github.com/databricks-solutions/ai-dev-kit
- Canal oficial (alternativa de longo prazo): `databricks aitools install` — https://github.com/databricks/databricks-agent-skills
