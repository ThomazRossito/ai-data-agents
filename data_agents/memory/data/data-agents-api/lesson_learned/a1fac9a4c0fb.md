---
id: "a1fac9a4c0fb"
type: lesson_learned
summary: "fabric-engineer: retries — Agent"
tags: [fabric-engineer, retries, Agent, lesson_learned]
confidence: 0.000
created_at: 2026-05-14T10:56:11.851453+00:00
updated_at: 2026-05-15T12:33:59.546761+00:00
source_session: "cli-5edf454a"
superseded_by: "8bea93bbeca0"
metadata_json: '{"agent": "fabric-engineer", "trigger": "retries", "task_type": "Agent", "tool_name": "Agent", "platform": "local", "cost_usd": 0.000891}'
---

## O que aconteceu
Agente `fabric-engineer` entrou em loop de retentativas (>3) ao delegar para sub-agente via tool `Agent` durante execução da PoC Itaúsa no Microsoft Fabric, sem produzir progresso entre ciclos.

## Causa raiz
Sub-agente recebeu contexto truncado (prompt cortado em `"Artefatos existentes (NÃO"`) e workspace ID fixo, mas sem lista completa de artefatos disponíveis, causando falha repetida na resolução de dependências do pipeline `fabric_pipeline_run`.

## Padrão para evitar
Sempre validar que o contexto injetado no prompt do `Agent` não excede o limite de tokens da tool — truncamento silencioso elimina informação crítica; para workspaces Fabric, sempre anexar lista materializada de artefatos (lakehouses/notebooks) via `fabric_notebook__list_items` antes de orquestrar sub-agentes.