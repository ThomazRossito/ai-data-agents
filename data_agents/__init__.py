"""AI Data Agents — Sistema Multi-Agentes para Engenharia, Qualidade e Governança
de Dados em Databricks + Microsoft Fabric.

Phase 7 refactor: este é o pacote namespace raiz que consolida agents, config,
hooks, commands, memory, compression, workflow, utils, mcp_servers, evals, ui,
visualization e monitoring sob um único namespace `data_agents.*`.

Antes da Fase 7, esses módulos eram pastas top-level (`from agents.X import Y`).
A partir de v3.0.0, todos os imports são `from data_agents.agents.X import Y`.

Ver CHANGELOG.md "Phase 7 migration" para o sed de migração se você tem código
externo que depende destes módulos.
"""

__version__ = "3.0.0-rc1"
