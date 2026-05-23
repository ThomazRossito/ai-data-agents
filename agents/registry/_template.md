---
name: agent-name
description: |
  Descrição do agente. Use para: [casos de uso]. Invoque quando: [condições de trigger].

  Example 1:
  - Context: User wants to do X
  - user: "Faça X"
  - assistant: "Vou delegar para agent-name."

  Example 2:
  - Context: User asks about Y
  - user: "Como faço Y?"
  - assistant: "agent-name vai te ajudar com Y."

model: kimi-k2.6  # modelo único da família K2.6 — thinking ligado/desligado via parâmetro
tools: [Read, Grep, Glob, Write]
mcp_servers: []
kb_domains: []
skill_domains: []
tier: T1

# stop_conditions: lista de strings descrevendo SITUAÇÕES em que o agente
# deve parar e sinalizar escalação. O Supervisor lê isso para evitar pedir
# o impossível ao agente errado.
stop_conditions:
  - "Tarefa fora do domínio do agente — escalar para [outro-agente]"

# escalation_rules: estruturado para o Supervisor consumir programaticamente
# em Step 3.5 do supervisor_prompt. Cada regra mapeia um trigger textual
# a um agente-alvo, com a razão da escalação.
escalation_rules:
  - trigger: "Descrição curta do trigger"
    target: "agente-alvo"
    reason: "Por que escalar (uma frase)"

# permission_mode: bypassPermissions  # descomente para agentes que fazem writes em sistemas externos (OneLake, SQL, APIs)
---
# Agent Name

## Identidade e Papel

Você é o **Agent Name**, especialista em [domínio].

---

## Protocolo KB-First — Obrigatório

Antes de qualquer ação, consulte as Knowledge Bases relevantes.

### Mapa KB + Skills por Tipo de Tarefa

| Tipo de Tarefa | KB a Ler Primeiro | Skill Operacional (se necessário) |
|----------------|-------------------|-----------------------------------|
| [tarefa]       | `kb/dominio/index.md` | `skills/skill.md `             |

---

## Capacidades Técnicas

[Descreva as capacidades técnicas do agente]

---

## Ferramentas MCP Disponíveis

[Liste as ferramentas MCP disponíveis]

---

## Protocolo de Trabalho

[Descreva o protocolo passo a passo]

---

## Formato de Resposta

```
[Defina o formato de resposta esperado]
```

---

## Restrições

1. [Restrição 1]
2. [Restrição 2]

---

## Campos do Frontmatter

| Campo         | Obrigatório | Descrição                                                                 |
|---------------|-------------|---------------------------------------------------------------------------|
| `name`        | Sim         | Identificador único do agente (kebab-case)                                |
| `description` | Sim         | Descrição para o Supervisor usar no roteamento                            |
| `model`       | Sim         | Modelo Moonshot Kimi: `kimi-k2.6` (modelo único da família K2.6 — thinking via parâmetro) |
| `tools`       | Sim         | Lista de tools. Aliases: `databricks_all`, `databricks_readonly`, `fabric_all`, `fabric_readonly`, `fabric_rti_all`, `fabric_rti_readonly` |
| `mcp_servers` | Não         | Lista de MCP servers: `databricks`, `fabric`, `fabric_community`, `fabric_rti` |
| `kb_domains`  | Não         | Domínios de KB do agente. Quando `INJECT_KB_INDEX=true` (padrão), o loader injeta o `index.md` de cada domínio no prompt do agente automaticamente |
| `tier`        | Não         | Tier de complexidade: `T0` (conversacional puro, Haiku), `T1` (core), `T2` (especializado), `T3` (conversacional com tools). Consumido pelo loader para model routing quando `TIER_MODEL_MAP` está configurado no `.env` |
| `stop_conditions` | Não    | Lista de strings — quando o agente deve PARAR e escalar (referenciar o agente-alvo no texto). Lido pelo agente como parte do prompt. |
| `escalation_rules` | Não   | Lista de dicts `{trigger, target, reason}`. Consumido pelo Supervisor em Step 3.5 (`SUPERVISOR_SYSTEM_PROMPT`) para automatizar a escalação sem intervenção do usuário. |
