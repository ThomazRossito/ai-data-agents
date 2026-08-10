# KB: Workflows Colaborativos Multi-Agente

> **O que é:** Padrões de encadeamento automático entre agentes especialistas.
> Em vez de delegações isoladas, o Supervisor orquestra **workflows** onde a saída
> de um agente alimenta automaticamente o próximo.
>
> **Inspiração:** DOMA Party Mode — "multiple agents working in concert on a shared
> objective, with defined handoff points."

---

## 1. Conceito: Workflow vs Delegação Simples

| Aspecto | Delegação Simples | Workflow Colaborativo |
|---------|-------------------|----------------------|
| **Estrutura** | Supervisor → Agente → Resultado | Supervisor → Agente A → Agente B → ... → Resultado |
| **Handoff** | Manual (Supervisor roteia cada etapa) | Automático (Supervisor encadeia outputs) |
| **Quando usar** | Tarefas single-domain | Tarefas cross-domain ou multi-etapa |
| **Spec** | Opcional | Obrigatório (usar template de `templates/`) |

---

## 2. Workflows Pré-Definidos

### WF-01: Pipeline End-to-End (Bronze → Gold → Consumo)

```
┌──────────────────────┐    ┌──────────────────┐    ┌────────────────────┐    ┌─────────────────┐
│ databricks-engineer  │───→│ data-quality-    │───→│ fabric-engineer    │───→│ governance-     │
│                      │    │ steward          │    │                    │    │ auditor         │
│ Cria pipeline SDP    │    │ Define           │    │ Modelo semântico + │    │ Auditoria de    │
│ completo (B→S→G)     │    │ expectations +   │    │ DAX / Metric Views │    │ linhagem e PII  │
│                      │    │ profiling        │    │ sobre Gold         │    │                 │
└──────────────────────┘    └──────────────────┘    └────────────────────┘    └─────────────────┘
```

**Trigger:** Usuário solicita pipeline completo com consumo analítico.
**Spec:** `templates/pipeline-spec.md`
**Handoff points:**
1. databricks-engineer entrega DDL + código do pipeline → data-quality-steward recebe as tabelas para validar
2. data-quality-steward confirma expectations → fabric-engineer recebe tabelas Gold validadas
3. fabric-engineer entrega modelo → governance-auditor valida linhagem e PII

**Prompt de delegação do Supervisor para cada agente:**
```
Agente: [nome]
Workflow: WF-01 Pipeline End-to-End
Etapa: [N] de [Total]
Spec: output/specs/[nome_spec].md
Contexto da etapa anterior: [resumo do output do agente anterior]
Sua tarefa: [descrição específica]
Restrições constitucionais: [regras relevantes de kb/constitution.md]
```

---

### WF-02: Star Schema Design + Implementação

```
┌──────────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│ databricks-engineer  │───→│ databricks-engineer  │───→│ data-quality-      │
│                      │    │ (2ª etapa)           │    │ steward            │
│ DDL dims + facts     │    │ Pipeline SDP         │    │ Expectations +     │
│ (Gold) — schema      │    │ para popular         │    │ validação FK       │
└──────────────────────┘    └──────────────────────┘    └────────────────────┘
                                                                  │
                                                                  ▼
                                                        ┌─────────────────┐
                                                        │ fabric-engineer  │
                                                        │                  │
                                                        │ Modelo semântico │
                                                        │ + DAX measures   │
                                                        └─────────────────┘
```

**Trigger:** Usuário solicita design de Star Schema / camada Gold.
**Spec:** `templates/star-schema-spec.md`
**Handoff points:**
1. databricks-engineer entrega DDL → databricks-engineer implementa pipeline de carga (context chain)
2. databricks-engineer entrega pipeline → data-quality-steward valida integridade referencial
3. data-quality-steward confirma qualidade → fabric-engineer cria modelo de consumo

---

### WF-03: Migração Cross-Platform

```
┌──────────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│ databricks-engineer  │───→│ databricks-engineer  │───→│ fabric-engineer    │
│                      │    │ (2ª etapa)           │    │                    │
│ Estratégia +         │    │ Conversão de         │    │ Adaptação de       │
│ inventário de schema │    │ dialeto DDL          │    │ artefatos Fabric   │
└──────────────────────┘    └──────────────────────┘    └────────────────────┘
                                                                  │
                                              ┌───────────────────┤
                                              ▼                   ▼
                                      ┌──────────────┐ ┌─────────────────┐
                                      │ data-quality-│ │ governance-     │
                                      │ steward      │ │ auditor         │
                                      │ Validação    │ │ Linhagem +      │
                                      │ pós-carga    │ │ PII cross-plat  │
                                      └──────────────┘ └─────────────────┘
```

**Trigger:** Usuário solicita migração Databricks ↔ Fabric.
**Spec:** `templates/cross-platform-spec.md`
**Handoff points:**
1. databricks-engineer faz inventário de schema e define estratégia → converte DDL para dialeto destino
2. databricks-engineer entrega DDL convertido → fabric-engineer adapta artefatos para Fabric
3. fabric-engineer conclui adaptação → data-quality-steward e governance-auditor trabalham **em paralelo**

---

### WF-04: Auditoria Completa de Governança

```
┌─────────────────┐    ┌──────────────────┐
│ governance-     │───→│ data-quality-    │
│ auditor         │    │ steward          │
│                 │    │                  │
│ Inventário de   │    │ Profiling das    │
│ acessos + PII + │    │ tabelas críticas │
│ linhagem        │    │ + drift check    │
└─────────────────┘    └──────────────────┘
        │
        ▼ (consolidação pelo Supervisor)
   Relatório Final de Governança
```

**Trigger:** Usuário solicita auditoria ou relatório de governança.
**Handoff points:**
1. governance-auditor faz inventário completo → identifica tabelas críticas para profiling
2. data-quality-steward faz profiling das tabelas identificadas (em paralelo com auditoria)
3. Supervisor consolida ambos os relatórios em documento único

---

### WF-05: Migração Relacional → Nuvem (SQL Server / PostgreSQL → Databricks/Fabric)

```
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│ migration-      │───→│ databricks-engineer  │───→│ databricks-engineer  │
│ expert          │    │                      │    │ (3ª etapa)           │
│                 │    │ Adapta DDL para      │    │ Gera notebooks       │
│ Assessment +    │    │ Delta/Lakehouse      │    │ de carga Bronze      │
│ inventário DDL  │    │ + tipos              │    │ → Silver → Gold      │
└─────────────────┘    └──────────────────────┘    └──────────────────────┘
                                                              │
                                    ┌─────────────────────────┤ (paralelo)
                                    ▼                         ▼
                    ┌──────────────────────┐   ┌──────────────────────┐
                    │ data-quality-        │   │ governance-auditor   │
                    │ steward              │   │                      │
                    │                      │   │ Linhagem + PII +     │
                    │ Validação de dados   │   │ compliance LGPD      │
                    │ migrados + testes DQ │   │ pós-migração         │
                    └──────────────────────┘   └──────────────────────┘
                                    │
                                    ▼ (consolidação pelo Supervisor)
                          Relatório de Migração Completo
```

**Trigger:** Usuário solicita migração de SQL Server ou PostgreSQL para Databricks ou Microsoft Fabric.

> **Roteamento por tipo de origem (atualizado 2026-08-02):** este WF-05 via `migration-expert` é o caminho **genérico** (schema/DDL; também PostgreSQL e destino Fabric). Prefira o especialista dedicado quando aplicável: SQL Server **completo → Databricks** (dados + objetos T-SQL + CDC + reconciliação + cutover) → **`sqlserver-to-databricks`** (`/sqlserver`); pacotes **SSIS `.dtsx`** → **`ssis-to-databricks`** (`/ssis`); modelos **SSAS `.bim/.vpax`** → **`ssas-to-databricks`** (`/ssas`). Os especialistas rodam geradores determinísticos (`scripts/sqlserver_generate.py`, `ssas_generate.py`, `reconcile_generate.py`) e o gate de aprovação humana (Step 0.6A).

**Handoff points:**
1. migration-expert faz assessment completo via `migration_source` MCP → extrai DDL, views, procedures, estatísticas
2. databricks-engineer recebe o inventário e adapta DDL para Delta Lake (Databricks) ou Lakehouse (Fabric), mapeando tipos
3. databricks-engineer recebe o DDL adaptado e gera notebooks PySpark para carga Bronze → Silver → Gold
4. data-quality-steward e governance-auditor trabalham **em paralelo** após a carga inicial
5. Supervisor consolida o relatório final com status de cada objeto migrado e resultados de DQ

---

## 3. Regras de Orquestração de Workflows

### 3.1 Princípios

| # | Regra |
|---|-------|
| W1 | Todo workflow **deve** ter um spec preenchido antes de iniciar (Passo 0.9). |
| W2 | O Supervisor **deve** apresentar o plano do workflow ao usuário antes de iniciar delegação. |
| W3 | Cada agente no workflow recebe o **contexto da etapa anterior** no prompt de delegação. |
| W4 | Se um agente falhar, o workflow **pausa** — o Supervisor propõe correção antes de continuar. |
| W5 | Agentes em etapas **independentes** podem ser executados em paralelo (ex: WF-03 etapa 4). |
| W6 | O Supervisor **nunca** pula etapas do workflow. A ordem de handoff é determinística. |
| W7 | Resultados de cada etapa são salvos em `output/` para rastreabilidade. |
| W8 | **Workflow Context Cache**: antes do primeiro agente, o Supervisor compila `output/workflow-context/{wf_id}-context.md` com spec + regras constitucionais + sequência de handoff. Todos os agentes do workflow lêem este arquivo. |

### 3.2 Formato de Handoff

Ao delegar para o próximo agente no workflow, o Supervisor deve incluir:

```markdown
## Contexto do Workflow

- **Workflow:** [WF-XX] [Nome]
- **Spec:** `output/specs/[nome].md`
- **Etapa atual:** [N] de [Total]
- **Resultado da etapa anterior ([nome-agente]):**
  [Resumo conciso do output — máximo 500 palavras]
- **Sua tarefa nesta etapa:**
  [Descrição específica do que este agente deve fazer]
- **Restrições constitucionais aplicáveis:**
  [Lista das regras de kb/constitution.md relevantes para esta etapa]
```

### 3.3 Detecção Automática de Workflow

O Supervisor deve detectar automaticamente quando um workflow pré-definido se aplica:

| Palavras-chave na Requisição | Workflow Sugerido |
|------------------------------|-------------------|
| "pipeline completo", "end-to-end", "bronze até gold" | WF-01 |
| "star schema", "camada gold", "dimensional" | WF-02 |
| "migrar", "mover para fabric", "cross-platform" | WF-03 |
| "auditoria", "governança completa", "relatório de compliance" | WF-04 |
| "migrar sql server", "migrar postgres", "migração relacional", "banco relacional para databricks/fabric" | WF-05 |

Quando detectado, o Supervisor deve:
1. Informar o usuário qual workflow será utilizado
2. Apresentar o plano de etapas e agentes
3. Solicitar aprovação antes de iniciar

---

### WF-06: Schema → Implementation (DDL-first, Seed/Script dependente)

```
┌──────────────────────┐    ┌─────────────────────────────┐    ┌──────────────────┐
│ databricks-engineer  │───→│  Workflow Context Cache      │───→│  python-expert   │
│                      │    │  output/workflow-context/    │    │                  │
│ Cria DDL completo    │    │  wf06-context.md             │    │ Lê o DDL antes   │
│ (schema)             │    │  (contém schema completo)    │    │ de gerar scripts │
│                      │    └─────────────────────────────┘    │ seed/config/etc. │
└──────────────────────┘                                        └──────────────────┘
```

**Trigger:** Usuário solicita schema + script/código que opera sobre esse schema
(seed, gerador de dados, migration script, API layer, ORM, testes de integração, etc).

**Regra fundamental:** O python-expert (ou qualquer agente de implementação) **jamais**
pode ser executado em paralelo com o databricks-engineer quando seu output depende do schema.
O DDL é o contrato — deve existir antes de qualquer código que o consuma.

**Spec:** não requer template — o DDL gerado pelo databricks-engineer é o próprio contrato.

**Handoff points:**
1. databricks-engineer gera DDL completo com todos os nomes de colunas, tipos e constraints
2. Supervisor lê o DDL e compila `output/workflow-context/wf06-context.md` com:
   - Lista de tabelas e colunas exatas (extraída do DDL)
   - Tipos de dados e constraints relevantes
   - Nomes de sequences/triggers gerados
3. python-expert recebe o contexto e lê o DDL antes de escrever qualquer INSERT/SELECT

**Prompt de delegação do Supervisor para o python-expert (etapa 2):**
```
Workflow: WF-06 Schema → Implementation
Etapa: 2 de 2
Contexto do schema: output/workflow-context/wf06-context.md

OBRIGATÓRIO: Leia o arquivo acima com Read() ANTES de escrever qualquer código.
Use EXATAMENTE os nomes de colunas, tabelas e tipos definidos no DDL.
Não inferir nomes — o contrato já está definido.

Sua tarefa: [descrição do script]
```

**Por que esse workflow existe:**
Sem ele, o Supervisor tende a paralelizar databricks-engineer + python-expert — o que é
otimização correta para tarefas independentes, mas catastrófico quando o script
depende do schema. Os dois agentes fazem escolhas razoáveis isoladamente
(`unit_cost` vs `cost_price`) mas divergem porque nunca compartilharam o contrato.

---

### WF-07: Greenfield Cost Estimate (Databricks compute + Azure infra + storage)

```
┌───────────────────────────┐   ┌──────────────────────────┐
│ read-sizing-spreadsheet   │   │  (se houver planilha de   │
│ (skill)                   │──→│   sizing como input)      │
└───────────────────────────┘   └──────────────────────────┘
              │ cenário estruturado (num_envs, region, workloads...)
              ▼
   ┌──────────────────────────────────────────────────────────┐
   │                  EXECUÇÃO EM PARALELO (W5)                 │
   ├──────────────────────────────┬───────────────────────────┤
   │ databricks-cost-calculator   │  azure-cost-calculator     │
   │ • Databricks compute × N env │  • Azure infra × N env      │
   │ • Storage ADLS Gen2          │  • vNet, NAT, PEP, Log, KV  │
   │ • Genie / FM API / AI Search │  • Firewall, Defender,      │
   │ • region-aware DBU rates     │    Bastion, egress          │
   └──────────────────────────────┴───────────────────────────┘
              │                              │
              └──────────────┬───────────────┘
                             ▼
              ┌──────────────────────────────────────┐
              │  Consolidação DETERMINÍSTICA          │
              │  scripts/greenfield_consolidate.py    │
              │  (lê os 2 JSONs → XLSX, <1s)          │
              └──────────────────────────────────────┘
```

**Trigger:** estimativa de custo para um deploy **greenfield** (do zero) com
múltiplos ambientes, OU quando o usuário fornece uma planilha de sizing. A marca
registrada é: "quanto custa montar a plataforma toda", não "quanto custa este job".

**Regra fundamental (por que este workflow existe):**
O `databricks-cost-calculator` sozinho cobre apenas compute + storage Databricks.
Num greenfield, a infra Azure de SUPORTE (vNet, NAT, Private Endpoints, Log
Analytics, Key Vault, Firewall, Defender, Bastion) representa **35-45% do custo
total** e não é Databricks — é do escopo do `azure-cost-calculator`. Sem
orquestração, essa camada fica invisível e a estimativa sai ~4× menor que a real.

**Spec:** consultar KB `azure-infra-for-databricks` para o sizing enterprise de
referência por ambiente. Se houver planilha, usar a skill `read-sizing-spreadsheet`.

**Handoff points:**
1. (opcional) skill `read-sizing-spreadsheet` parseia a planilha → cenário
2. Supervisor compila `output/workflow-context/wf07-context.md` com num_envs,
   region, workloads, exclusões
3. databricks-cost-calculator e azure-cost-calculator rodam EM PARALELO (etapas
   independentes) lendo o mesmo contexto. Cada um GRAVA um JSON de cenário:
   `<projeto>/scenario_used.json` e `<projeto>/azure_infra_scenario_used.json`
   (ambos com bloco `totals.monthly_usd`).
4. Consolidação é DETERMINÍSTICA — NÃO peça ao python-expert para "montar o XLSX"
   do zero (isso é não-determinístico e já causou hang num Read ambíguo). Em vez
   disso, rode UM comando fixo:
   ```bash
   python3 scripts/greenfield_consolidate.py \
     --databricks <projeto>/scenario_used.json \
     --azure      <projeto>/azure_infra_scenario_used.json \
     --out        <projeto>/greenfield_cost_consolidated.xlsx
   ```
   O script lê os dois JSONs (já com todos os ambientes somados — NÃO re-multiplica
   por env) e grava um XLSX com Summary + breakdown Databricks + breakdown Azure +
   projeção Y2/Y3. É rápido (<1s) e idempotente.

**REGRA anti-hang:** a etapa 4 é um `Bash` de um comando, seguido de UM `Read`
opcional só para confirmar que o arquivo existe (nunca `Read` no binário .xlsx
inteiro — apenas checar existência via `ls`). Não reprocessar, não reler em loop.

**Prompt de delegação do Supervisor (etapa paralela, azure-cost-calculator):**
```
Workflow: WF-07 Greenfield Cost Estimate
Etapa: 1b de 2 (paralela com 1a databricks-cost-calculator)
Contexto: output/workflow-context/wf07-context.md
KB obrigatória: kb/azure-infra-for-databricks/index.md

Sua tarefa: modelar a infra Azure de suporte para {num_envs} workspaces
Databricks em {region}. Um stack de rede por ambiente + shared services.
Confirme premissas ambíguas com o usuário (NUNCA chutar Firewall/Defender ON/OFF).
```

**Regra crítica de escopo:** databricks-cost-calculator NÃO deve tentar modelar
vNet/NAT/PEP/etc. (fora do seu escopo). azure-cost-calculator NÃO deve modelar
DBU/compute Databricks. Cada um no seu, o business-analyst soma.

---

## 3.3 Detecção Automática de Workflow

O Supervisor deve detectar automaticamente quando um workflow pré-definido se aplica:

| Palavras-chave na Requisição | Workflow Sugerido |
|------------------------------|-------------------|
| "pipeline completo", "end-to-end", "bronze até gold" | WF-01 |
| "star schema", "camada gold", "dimensional" | WF-02 |
| "migrar", "mover para fabric", "cross-platform" | WF-03 |
| "auditoria", "governança completa", "relatório de compliance" | WF-04 |
| "migrar sql server", "migrar postgres", "migração relacional", "banco relacional para databricks/fabric" | WF-05 |
| "schema e script", "ddl e seed", "criar tabelas e popular", "criar schema e gerar dados", "poc", "fase 1", "lakebase e python", "schema + implementação", "criar banco e script" | WF-06 |
| "greenfield", "do zero", "implementação nova", "custo da plataforma toda", "N ambientes", "planilha de sizing", "estimativa completa de custo", "custo de infra + databricks" | WF-07 |

**Regra de detecção de dependência de artefato (independente de palavras-chave):**

Antes de paralelizar qualquer delegação, o Supervisor deve verificar:
> "O agente B precisa ler ou operar sobre um arquivo/schema que o agente A vai produzir?"

Se a resposta for **sim** → **sequenciar obrigatoriamente**, nunca paralelizar.
Exemplos de dependência de artefato:
- databricks-engineer gera DDL → python-expert gera script que faz INSERT nessas tabelas
- databricks-engineer gera pipeline → data-quality-steward valida as tabelas produzidas
- migration-expert extrai DDL → databricks-engineer converte o DDL extraído

Quando detectado, o Supervisor deve:
1. Informar o usuário qual workflow será utilizado
2. Apresentar o plano de etapas e agentes
3. Solicitar aprovação antes de iniciar

---

## 4. Criando Novos Workflows

Para adicionar um novo workflow:

1. Documente o workflow neste arquivo seguindo o formato dos WF-01 a WF-05
2. Defina: trigger, spec template (se novo), sequência de agentes, handoff points
3. Adicione as palavras-chave de detecção na tabela §3.3
4. Se necessário, crie um novo template em `templates/`
5. Atualize o supervisor prompt com a referência ao novo workflow
