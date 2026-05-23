---
id: "bccf62b4b3cc"
type: lesson_learned
summary: "fabric-engineer: retries — Agent"
tags: [fabric-engineer, retries, Agent, lesson_learned]
confidence: 0.000
created_at: 2026-05-13T23:56:28.819736+00:00
updated_at: 2026-05-14T01:43:16.896801+00:00
source_session: "cli-5ac5b91f"
superseded_by: "a1cef97a6905"
metadata_json: '{"agent": "fabric-engineer", "trigger": "retries", "task_type": "Agent", "tool_name": "Agent", "platform": "local", "cost_usd": 0.000535}'
---

## O que aconteceu
Agente `fabric-engineer` entrou em loop de retentativas (>3) sem progresso após execuções sequenciais de `TodoWrite` e `Write` para arquivos de PRD/specs do projeto `poc_itausa_fabric_medallion_docx`.

## Causa raiz
Padrão de escrita em disco (`Write`) intercalado com atualizações de todo-list (`TodoWrite`) sem verificação de estado entre ciclos; possível race condition ou falha silenciosa na escrita que não foi capturada antes da próxima iteração.

## Padrão para evitar
Sempre validar retorno de `Write` (checksum ou existência do arquivo) antes de chamar `TodoWrite`; nunca incrementar todo-list sem confirmação de estado da operação de I/O anterior.