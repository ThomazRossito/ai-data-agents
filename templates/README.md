# Templates — Spec-First

> **O que é:** Templates de especificação estruturada que o Supervisor gera e preenche
> **antes** de iniciar delegação de tarefas complexas. Inspirado no padrão Spec-First
> do AgentSpec — "define before you build."

## Quando Usar

O Supervisor deve gerar um spec preenchido (baseado no template relevante) quando:

1. A tarefa envolve **3+ agentes** ou **2+ plataformas**
2. A tarefa cria **infraestrutura nova** (pipelines, tabelas, modelos semânticos)
3. O usuário solicita explicitamente um plano detalhado (`/plan`)
4. O Clarity Checkpoint (Passo 0.5) indica complexidade alta

## Templates Disponíveis

| Template | Quando Usar | Agentes Envolvidos |
|----------|-------------|-------------------|
| `pipeline-spec.md` | Criação/migração de pipelines ETL/ELT | databricks-engineer, fabric-engineer, data-quality-steward |
| `star-schema-spec.md` | Design de camada Gold com Star Schema | databricks-engineer, fabric-engineer |
| `cross-platform-spec.md` | Operações Fabric ↔ Databricks | databricks-engineer, fabric-engineer + agentes de qualidade |

## Fluxo Spec-First

```
Passo 0 (KB-First) → Passo 0.5 (Clarity) → Passo 0.9 (Spec-First)
                                                 ↓
                                        Gerar spec preenchido
                                                 ↓
                                        Apresentar ao usuário (Passo 2)
                                                 ↓
                                        Delegação com referência ao spec
```

O spec é salvo em `output/specs/` e referenciado no prompt de delegação de cada agente.

---

## Máquina de Estados (Onda 2.1)

Desde set/2026 todo `*-spec.md` carrega frontmatter YAML e o spec deixa de ser
documento solto: vira objeto com ciclo de vida, gerido por
[`data_agents/spec/`](../data_agents/spec/).

```
rascunho → investigado → pronto → em-execucao → em-revisao → concluido
                                       ↑____________|
                                    (máx. 3 voltas, depois escala)

qualquer não-final → rascunho | cancelado     ← só o humano
```

`rascunho → concluido` **não existe**. Transição fora da tabela levanta
`TransicaoInvalida` — não é campo de texto livre.

### Por que isso apareceu

O `logs/audit.jsonl` deste repositório registra **6 escritas de spec para 3
specs reais**. O Supervisor regenerava do zero porque não tinha como saber que
já havia trabalho em andamento — e o nome do arquivo derivava no caminho
(`spec_ssas_comercial_brf.md` → `spec_ssas_brf_comercial.md`), de modo que nem
procurando dava para reencontrar.

### As duas regras que importam

**`spec_id` nunca muda.** É a identidade. `find_by_id()` procura por ele
*dentro* do arquivo; o nome do arquivo é cosmético. Renomeie à vontade — o
spec continua sendo achado.

**`<intencao-congelada>` pertence a você.** Agentes leem e trabalham dentro do
bloco; não o reescrevem. `save()` compara com o disco e levanta
`IntencaoCongeladaViolada` se um agente tentar. Se a intenção mudou de verdade,
quem edita é você, e o spec volta a `rascunho`.

### Uso

```python
from data_agents.spec import SpecStatus, Trilha
from data_agents.spec.store import criar, find_by_id, transicionar

spec = find_by_id("migracao-ssas-brf")     # None se não existir
if spec is None:
    spec = criar("Migração SSAS BRF", trilha=Trilha.PLATAFORMA)

transicionar(spec, SpecStatus.INVESTIGADO)  # valida antes de gravar
```

O `status` é o que permite ao Supervisor **continuar** em vez de recomeçar, e
ao `/resume` retomar sem reler o transcript inteiro.
