# Análise de Árvore de Tasks — Metodologia (Domínio-Agnóstica)

> Ao contrário de `foundry-agent-platform.md` e `multi-agent-patterns.md` (que dependem
> de fatos sobre um produto específico em evolução rápida), esta metodologia **não
> depende de nenhuma plataforma, API ou produto**. É estável e reaproveitável em qualquer
> contexto onde exista uma árvore/hierarquia de tasks parent/child (backlog de produto,
> WBS de projeto, plano de sprint, especificação de agentes que decompõe um objetivo em
> sub-tasks, etc.).

---

## 1. Modelagem como DAG

Toda árvore de tasks parent/child é, estruturalmente, um **grafo acíclico dirigido
(DAG)**: nós = tasks, arestas = relações de dependência ou de decomposição
(parent→child). Antes de qualquer análise de qualidade ou sugestão de melhoria, modele a
árvore explicitamente como DAG:

1. **Liste todos os nós** (tasks) com seu id, parent declarado (se houver) e dependências
   explícitas declaradas (task X depende de task Y).
2. **Construa as arestas** — tanto as de decomposição (parent→child) quanto as de
   dependência (blocked-by).
3. **Detecte ciclos** — uma task que, seguindo a cadeia de dependências, acaba
   dependendo de si mesma. Ciclos são sempre um bug estrutural — nunca ignore, sempre
   reporte antes de prosseguir com qualquer scoring.
4. **Detecte órfãos** — tasks sem parent nem child quando a estrutura geral sugere que
   deveriam ter (ex.: uma task de implementação "solta" que não pertence a nenhuma
   feature/epic).
5. **Calcule o caminho crítico** — a sequência de tasks dependentes que determina a
   duração mínima total, considerando as dependências declaradas (não apenas a
   hierarquia parent/child).

---

## 2. As 5 Dimensões de Análise (com Score)

Cada task (ou sub-árvore) é avaliada nas 5 dimensões abaixo. Recomenda-se escala 0-5 por
dimensão (mesma convenção de scoring 0-5 usada em outros agentes deste projeto, ex.
Complexity Scoring Matrix dos agentes de migração e Maturidade Data Mesh) para manter
consistência visual entre relatórios, mas a escala pode ser adaptada ao contexto do
usuário se ele já tiver uma convenção própria — pergunte antes de assumir.

| Dimensão | O que avalia | Sinal de problema (score baixo) |
|---|---|---|
| **Completude** | A task tem todas as informações necessárias para ser executada sem retrabalho de descoberta? | Falta contexto, critério de aceite, ou dados de entrada necessários |
| **Clareza** | O objetivo da task é inequívoco? Duas pessoas/agentes diferentes chegariam à mesma interpretação? | Linguagem vaga, escopo implícito, jargão não definido |
| **Risco** | Qual a chance de a task falhar, ser bloqueada, ou gerar retrabalho downstream? | Dependência externa incerta, tecnologia não validada, decisão pendente de terceiros |
| **Granularidade** | A task está no tamanho certo — nem grande demais (deveria ser split) nem trivial demais (deveria ser merged)? | Task estimada em "semanas" sem decomposição, ou várias micro-tasks que deveriam ser uma só |
| **Alinhamento** | A task contribui claramente para o objetivo da task-pai / do épico / do objetivo de negócio declarado? | Task existe mas não se conecta a nenhum objetivo maior — candidata a rescope ou remoção |

**Regra:** nunca produza um score agregado único sem mostrar o breakdown por dimensão —
um score "3/5" sem contexto não ajuda ninguém a agir.

---

## 3. Operações de Melhoria

Com base no scoring e na análise do DAG, cada problema encontrado mapeia para uma
operação de melhoria concreta:

| Operação | Quando aplicar | Exemplo de gatilho |
|---|---|---|
| **Split** | Task grande demais (baixa granularidade) ou que mistura múltiplas responsabilidades | "Implementar toda a feature X" sem decomposição em sub-tasks executáveis |
| **Merge** | Múltiplas tasks triviais/redundantes que deveriam ser uma só | 5 sub-tasks de "ajustar cor do botão", "ajustar tamanho do botão", etc. |
| **Reorder** | Dependência mal sequenciada — uma task está posicionada antes de sua dependência real estar pronta | Task de "testar API" antes de "implementar API" no DAG |
| **Rescope** | Escopo ambíguo, inflado, ou que mistura coisas que deveriam ser tasks separadas | Task que inclui "e também revisar toda a arquitetura" como afterthought |
| **Reassign** | Task atribuída a um owner/domínio que não é o especialista correto | Task de governança atribuída a um agente/time de engenharia pura |
| **Add-acceptance-criteria** | Task sem critério objetivo de "pronto" | Task descrita apenas como "melhorar performance" sem métrica-alvo |

---

## 4. Validação de Cada Sugestão

**Nenhuma sugestão de melhoria é aplicada sem validação explícita.** Cada sugestão recebe
um veredito:

- **APPROVE** — a mudança não quebra nenhuma dependência existente e resolve o problema
  identificado sem introduzir um novo.
- **REJECT** — a mudança quebraria uma dependência real do DAG, contradiz uma regra de
  negócio declarada pelo usuário, ou o "problema" identificado é, na verdade, intencional
  (ex.: uma task realmente grande que o usuário confirma que deve permanecer unificada).
- **CONDITIONALLY_APPROVE** — a mudança é recomendada, mas depende de uma confirmação ou
  ajuste adicional antes de ser segura (ex.: "split aprovado, mas a nova sub-task B
  precisa de um novo critério de aceite antes de ser executável").

Sempre declare a razão do veredito — nunca apenas o rótulo.

---

## 5. Governança da Análise

- **Modo advisory / read-only por padrão.** O agente que aplica esta metodologia
  **sugere** mudanças; ele não deve escrever de volta em um sistema de tracking externo
  (Jira, Azure DevOps, ADO Boards, etc.) sem confirmação humana explícita — mesmo
  princípio da Constituição §2.2 deste projeto (documento-always + aprovação antes de
  ação irreversível).
- **Audit trail.** Toda análise produzida (scores, sugestões, vereditos) deve ser
  salva como documento — nunca apenas comunicada verbalmente/efêmera — para que a decisão
  seja rastreável depois.
- **PII scrubbing.** Descrições de tasks frequentemente contêm nomes de clientes, dados
  de contrato, ou informação sensível de negócio. Antes de incluir qualquer excerto
  literal de uma task no relatório final, avalie se há PII/dado sensível — se houver,
  escale para `governance-auditor` antes de prosseguir (mesma regra de todos os agentes
  deste projeto sob a Constituição S6).
