---
id: "8fdaaf1df9f4"
type: lesson_learned
summary: "fabric-engineer: retries — Agent"
tags: [fabric-engineer, retries, Agent, lesson_learned]
confidence: 0.000
created_at: 2026-05-13T23:32:00.942203+00:00
updated_at: 2026-05-14T01:43:16.900155+00:00
source_session: "cli-5ac5b91f"
superseded_by: "a1cef97a6905"
metadata_json: '{"agent": "fabric-engineer", "trigger": "retries", "task_type": "Agent", "tool_name": "Agent", "platform": "local", "cost_usd": 0.000819}'
---

## O que aconteceu
Agente `fabric-engineer` entrou em loop de retentativas (>3) após sequência de `TodoWrite`/`Write` sem progresso visível na sessão; tool `Agent` não reportou erro explícito, mas estagnou em escrita de artefatos de documentação (`prd_poc_itausa_fabric_medallion_docx.md`, `spec_poc_itausa_fabric_medallion_docx.md`).

## Causa raiz
Causa raiz indeterminada — monitorar reincidência. Possíveis fatores: (a) dependência de todo-list interna sem verificação de estado real, (b) `Write` sobrepondo arquivos sem leitura prévia causando divergência de contexto, ou (c) agente orquestrador (`Agent`) não propagando sinal de progresso para o `fabric-engineer`.

## Padrão para evitar
Sempre verificar `read` do artefato antes de `Write` quando o agente executar >1 ciclo de escrita; nunca acumular `TodoWrite` sem marcar itens concluídos após tool `Write` bem-sucedida; abortar e escalar após 2 retentativas idênticas em agentes orquestrados por `Agent`.