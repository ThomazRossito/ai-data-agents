---
name: task-architect
description: "Playbook operacional para o task-architect: passos para analisar uma árvore de tasks parent/child (DAG, 5 dimensões, operações de melhoria), checklist de validação (APPROVE/REJECT/CONDITIONALLY_APPROVE), checklist de governança advisory/read-only. Agnóstico de plataforma — serve qualquer backlog Jira/ADO/Asana/texto livre. Leia ANTES de produzir qualquer relatório de análise de tasks."
---

# Skill: Task Architect — Playbook Operacional

<!-- type: concept -->
## Quando Usar Este Playbook

| Pedido do usuário | Uso |
|---|---|
| "Analisa minha árvore de tasks" / "Onde tem problema nesse backlog?" | §1 — Passos de Análise de Árvore de Tasks |
| "Faz um refinamento desse backlog de sprint" / WBS / decomposição de tarefas | §1, mesmos passos |
| Qualquer análise de tasks, sempre | §2 — Checklist de Governança + §3 — Checklist de Validação |
| "Desenha um sistema multi-agente" / Microsoft Foundry | **Fora de escopo** — delegar para `foundry-engineer`, ver `skills/foundry/foundry-engineer/SKILL.md` |

---

<!-- type: pattern -->
## §1 — Passos de Análise de Árvore de Tasks

Leia `kb/task-architecture/concepts/task-tree-analysis.md` para a metodologia completa
antes de aplicar estes passos.

1. **Extraia a árvore.** Peça (ou receba) a lista de tasks com: id, título, parent_id
   (se houver), lista de dependências explícitas (`blocked_by`), descrição, e critério de
   aceite (se houver). Nunca invente uma dependência que não foi declarada. Aceite
   qualquer formato de origem (export Jira/ADO, planilha, texto livre) — a metodologia é
   agnóstica da fonte.
2. **Construa o DAG e rode as checagens estruturais:**
   - Ciclo: existe uma cadeia `A depende de B depende de ... depende de A`?
   - Órfã: task sem parent nem child nem dependência declarada, quando o resto da árvore
     sugere que deveria ter uma?
   - Caminho crítico: qual sequência de dependências determina a duração mínima?
   Reporte esses achados **antes** de prosseguir para o scoring — são bugs estruturais,
   não questões de qualidade.
3. **Pontue cada task nas 5 dimensões** (completude, clareza, risco, granularidade,
   alinhamento), escala 0-5, com uma frase de evidência por dimensão — nunca um número
   sem justificativa.
4. **Para cada task com score baixo em alguma dimensão, proponha uma operação**
   (split/merge/reorder/rescope/reassign/add-acceptance-criteria) — mapa completo em
   `kb/task-architecture/concepts/task-tree-analysis.md` §3.
5. **Valide cada sugestão contra o DAG real** — rode mentalmente (ou explicitamente, se
   a árvore for grande, considere usar `Write` para persistir uma tabela intermediária em
   `output/`) "se eu aplicar esta mudança, alguma dependência declarada quebra?". Marque
   APPROVE / REJECT / CONDITIONALLY_APPROVE com a razão.
6. **Produza o relatório final** seguindo o formato de resposta do agente (ver
   `data_agents/agents/registry/task-architect.md` §Formato de Resposta).

### Exemplo de Tabela de Scoring

| Task ID | Completude | Clareza | Risco | Granularidade | Alinhamento | Observação |
|---|---|---|---|---|---|---|
| T-014 | 2/5 | 4/5 | 3/5 | 1/5 | 5/5 | Falta critério de aceite; escopo grande demais — candidata a split |

---

<!-- type: constraint -->
## §2 — Checklist de Governança (rodar sempre)

- [ ] Nenhum dado pessoal real (nome de cliente, CPF, e-mail, etc.) foi incluído
  literalmente no relatório sem passar por `governance-auditor` primeiro.
- [ ] A análise opera em modo advisory/read-only por padrão — qualquer escrita
  automática em sistema externo (Jira, ADO) exige aprovação humana explícita antes de
  ser especificada como automática.
- [ ] Existe audit trail declarado — onde o relatório fica salvo para revisão posterior.
- [ ] O relatório final foi salvo em `output/specs/` ou `output/architecture/` (nunca
  apenas comunicado no chat), quando o pedido exigia um artefato reutilizável.

---

<!-- type: constraint -->
## §3 — Checklist de Validação de Sugestões (obrigatório para cada operação proposta)

Antes de listar qualquer sugestão de melhoria no relatório final, confirme:

- [ ] A sugestão foi checada contra TODAS as dependências declaradas da task, não apenas
  as óbvias.
- [ ] O veredito (APPROVE/REJECT/CONDITIONALLY_APPROVE) vem acompanhado de uma razão —
  nunca apenas o rótulo.
- [ ] Se CONDITIONALLY_APPROVE: a condição específica que falta está explícita (ex.:
  "split aprovado, mas a nova sub-task B precisa de critério de aceite antes de ser
  executável").
- [ ] Se REJECT: o motivo declara exatamente qual dependência quebraria, ou qual regra de
  negócio do usuário a sugestão contradiz.
- [ ] Nenhuma sugestão foi tratada como já aplicada — este agente é advisory, a decisão
  final é sempre humana.
