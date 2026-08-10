---
domain: task-architecture
updated_at: 2026-08-09
agents: [task-architect]
mcp_validated: "not-applicable — no MCP dataset; methodology is domain-agnostic and does not depend on live platform docs"
---

# KB: Análise e Otimização de Árvores de Tasks — Índice

**Domínio:** Metodologia **agnóstica de plataforma** de análise/otimização de árvores de
tasks parent/child (backlog de produto, WBS de projeto, plano de sprint, decomposição de
objetivo em sub-tasks de qualquer sistema — Jira, Azure DevOps, Asana, ou qualquer árvore
de tasks textual/estruturada).
**Agentes:** task-architect

> **Nota histórica:** este domínio foi extraído em 2026-08-09 de `kb/agent-architecture/`
> (hoje `kb/foundry/`), onde vivia acoplado ao agente de design de agentes Microsoft
> Foundry. A extração corrige um nome "mentiroso": a metodologia de análise de tasks nunca
> dependeu de Foundry nem de nenhuma plataforma de agentes — é estável e reaproveitável em
> qualquer contexto de gestão de tasks. Ver `kb/foundry/index.md` para o domínio irmão
> (Microsoft Foundry) que permaneceu sob o agente `foundry-engineer`.

---

## Conteúdo Disponível

### Conceitos (`concepts/`)

| Arquivo | Conteúdo |
|---|---|
| `concepts/task-tree-analysis.md` | Metodologia domínio-agnóstica de análise de árvore de tasks parent/child: modelagem DAG (ciclos, órfãos, caminho crítico), scoring em 5 dimensões (completude, clareza, risco, granularidade, alinhamento), operações de melhoria (split/merge/reorder/rescope/reassign/add-acceptance-criteria), validação (APPROVE/REJECT/CONDITIONALLY_APPROVE), e governança advisory read-only |

---

## Por Que Esta Metodologia É Estável (ao contrário de `kb/foundry/`)

Diferente do domínio `kb/foundry/` (produto em evolução ativa, GA/preview shifts
constantes), esta metodologia **não depende de nenhuma API, SDK, ou produto específico**.
Modelar uma árvore de tasks como DAG, pontuar 5 dimensões, e validar operações de melhoria
são práticas estáveis de gestão de projetos/produto — reaproveite livremente sem a mesma
disciplina de reconfirmação via context7/tavily que se aplica a `kb/foundry/`.

**A única verificação obrigatória** é de contexto, não de fato de produto: nunca assuma
uma dependência entre tasks que não foi declarada explicitamente pelo usuário ou pela
fonte de dados (Jira/ADO/planilha/texto livre).

---

## Regras de Negócio — Análise de Árvore de Tasks

- Toda árvore de tasks é modelada como DAG antes de qualquer sugestão de melhoria.
- Ciclos e tasks órfãs são bugs estruturais — sempre reportados antes de scoring.
- As 5 dimensões (completude, clareza, risco, granularidade, alinhamento) são pontuadas
  por task/sub-árvore, nunca de forma agregada e opaca.
- Toda sugestão de melhoria passa por validação explícita: APPROVE / REJECT /
  CONDITIONALLY_APPROVE contra regras de negócio declaradas e as dependências reais do
  DAG.
- Modo advisory/read-only por padrão: o agente sugere, não aplica mudanças
  automaticamente em sistemas de tracking externos (Jira, Azure DevOps, etc.) sem
  confirmação humana.
- PII em descrições de tasks (nomes de clientes, dados pessoais em exemplos) é
  escalada para `governance-auditor` antes de incluir no relatório.
- Este agente é **independente de plataforma de dados/agentes** — nunca é confundido com
  `foundry-engineer` (Microsoft Foundry) nem com qualquer agente de engenharia
  Databricks/Fabric. Serve qualquer backlog/árvore de tasks, de qualquer sistema.
