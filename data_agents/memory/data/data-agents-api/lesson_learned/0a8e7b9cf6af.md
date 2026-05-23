---
id: "0a8e7b9cf6af"
type: lesson_learned
summary: "fabric-engineer: retries — Agent"
tags: [fabric-engineer, retries, Agent, lesson_learned]
confidence: 0.000
created_at: 2026-05-14T02:19:09.878652+00:00
updated_at: 2026-05-14T08:20:37.474016+00:00
source_session: "cli-e0dc04b9"
superseded_by: "d386f38b5fff"
metadata_json: '{"agent": "fabric-engineer", "trigger": "retries", "task_type": "Agent", "tool_name": "Agent", "platform": "local", "cost_usd": 0.00084}'
---

## O que aconteceu
Agent `fabric-engineer` travou em loop de retentativas (>3) após falha no `mcp__fabric_notebook__fabric_notebook_create`: célula de code foi enviada incompleta (`print('vi`) e o agente não validou o payload antes de reenviar.

## Causa raiz
O agente truncou o conteúdo da célula no prompt da tool e, sem validação de sintaxe/integridade do campo `code`, repetiu chamadas sem corrigir o dado quebrado.

## Padrão para evitar
Sempre validar que células de código no `mcp__fabric_notebook__fabric_notebook_create` terminam com sintaxe completa antes de executar; nunca reenviar o mesmo payload truncado em retentativas — abortar e sinalizar para revisão manual se `code` estiver malformado.