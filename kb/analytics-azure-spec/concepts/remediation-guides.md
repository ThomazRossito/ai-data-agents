# Guias de Remediação — Como Fechar Cada Gap (Módulo B)

> Quando um controle fica 🟡 Parcial ou ❌ Ausente, o agente não para no diagnóstico: ele entrega o
> **caminho para fechar a lacuna**. Esta KB traz, por controle, o "como fazer" + **templates prontos**
> que o agente pode emitir. Tudo ancorado na documentação aceita do checklist V2.8.1 (não inventar).

## Princípios da remediação
- Aponte a **documentação aceita oficial** do controle (de `module-b-controls.md`) como alvo.
- Para evidência que **existe mas é informal** (🟡), oriente **retro-documentar** (formalizar o que já foi feito) — geralmente mais barato que refazer.
- Diferencie **lacuna de cobertura** (falta evidência/subitem) de **lacuna de clientes** (precisa de +N clientes).
- Dê esforço estimado e quem tipicamente executa.

---

## Por controle — como fechar

### 1.1 Analytics Portfolio Assessment
- **Alvo:** Assessment Report por cliente cobrindo os 9 subitens (business need, app landscape, performance, personas, skilling, data needs, networking, security/compliance, availability/DR).
- **Ação:** consolidar o material disperso (decks, wiki) em **um Assessment Report** estruturado por cliente. Adicionar o **Skilling Plan** (template "Develop a skilling plan for cloud-scale analytics" do CAF).
- **Aceito:** Assessment Checklist, Templates, Questionnaires, Project Plans, Skilling Plans, DMA Reports.

### 2.1 Solution Design
- **Alvo:** documento(s) de Solution Design cobrindo os 11 subitens, incluindo **ALZ** (constraints analytics), **Encryption methodology** (não só o recurso Key Vault — descrever TDE/CMK/Key Vault) e **Security** (row/column/object level, não só RBAC de plataforma).
- **Ação:** complementar os diagramas existentes com: data migration approach formal, desenho ALZ (identity/network/resource org), e metodologia de encryption + data security.
- **Aceito:** Project plans, Functional specs, Architectural diagrams, Automated tooling reports, Physical/logical diagrams.

### 2.2 Azure Well-Architected Review (gap típico: ❌)
- **Alvo:** export do **Core Well-Architected Review** com **2 dos 5 pilares**, por cliente, nos últimos 12 meses, com o nome do cliente visível.
- **Ação (how-to):**
  1. Acesse o Azure Well-Architected Review (assessment) no portal de assessments da Microsoft.
  2. Crie uma avaliação para a workload do cliente; escolha **2 pilares** (sugestão comum: Security + Cost Optimization, ou Reliability + Performance Efficiency).
  3. Responda o questionário com base no design real da workload.
  4. **Exporte o resultado (PDF/CSV)** com o nome do cliente identificável.
  5. Repita para 3 clientes (gate ISSI).
- **Esforço típico:** 2–4h por workload. Reviews podem ser antes/durante/depois do deploy.

### 2.3 Proof of Concept / Pilot
- **Alvo:** documento de PoC/pilot por cliente com propósito, dores, **critérios de sucesso**, benefícios e **resultados** + **aceite do cliente**.
- **Ação:** retro-documentar PoCs que já viraram produção (ex.: FastJob) usando o template abaixo; coletar aceite formal.
- **Aceito:** PoC Architecture Diagrams, Test Plans and Results, Implementation Documentation, Monitoring Tool Report.

### 3.1 Deployment
- **Alvo:** ≥2 de {Signed SOW, Solution design docs, Project plan/sequence, Architecture diagrams, HLD/LLD, As-built} por cliente, cobrindo design→produção.
- **Ação:** localizar/assinar o **SOW**; produzir **HLD/LLD** e **as-built** (pode derivar da wiki/onboarding existente).
- **Aceito:** ver lista acima (o controle exige no mínimo 2 itens).

### 4.1 Service Validation & Testing
- **Alvo:** documentação de teste/validação de performance + **sign-off documentado do cliente**.
- **Ação:** formalizar os resultados de performance/Data Quality já existentes num **Test Plan + Results** e obter **sign-off** (template abaixo).

### 4.2 Post-deployment Documentation
- **Alvo:** documentação pós-deploy + **SOPs/runbooks** de BAU com cenários "how-to".
- **Ação:** transformar a wiki/onboarding e os guias de fluxo em **SOPs rotulados** (template abaixo).

---

## Templates prontos (o agente pode emitir preenchendo os campos)

### SOW (Statement of Work) — esqueleto mínimo
```
Cliente: <nome> · Fornecedor: <parceiro> · Data de assinatura: <data> · Vigência: <início–fim>
1. Escopo do projeto (analytics): <...>
2. Entregáveis e marcos: <...>
3. Plataforma/serviços Azure: <Synapse|Databricks|Fabric|Dedicated SQL Pool> + ADF/ADLS/Power BI/...
4. Responsabilidades (cliente x fornecedor): <...>
5. Critérios de aceite: <...>
6. Assinaturas: <cliente> ___  <fornecedor> ___
```

### Customer Sign-Off (aceite formal) — esqueleto
```
Projeto: <nome> · Cliente: <nome> · Go-live: <data>
Confirmamos que a solução entregue atende aos requisitos acordados:
- Requisitos atendidos: <lista>
- Testes/validação de performance: <referência ao Test Plan & Results>
- Observações/ressalvas: <...>
Aprovado por (cliente): <nome, cargo> ___  Data: ___
```

### SOP / Runbook (BAU) — esqueleto
```
Procedimento: <nome> · Serviço/Workload: <...> · Dono (squad): <...> · Última revisão: <data>
1. Objetivo / quando usar
2. Pré-requisitos e acessos (grupos/Service Principals)
3. Passo-a-passo (how-to) <numerado>
4. Monitoramento e alertas (Azure Monitor/Log Analytics)
5. Troubleshooting comum / rollback
6. Escalonamento e contatos
```

### Assessment Report (1.1) — seções mínimas
```
Cliente: <nome> · Data: <últimos 24m>
1. Business need (dores, end-user needs, budget, governance/compliance)
2. Application landscape (infra atual/greenfield, BI SaaS)
3. Performance benchmarks
4. User personas (papéis e acessos)
5. Skilling plan (top skills, learning paths/certificações)
6. Data needs (tipo/volume/frequência, fontes/destino, classificação/risco)
7. Networking
8. Security & compliance
9. Availability/resiliency/DR (SLAs, escalabilidade)
```

### PoC/Pilot Doc (2.3) — seções mínimas
```
Cliente: <nome> · Período: <últimos 24m> · Produto: <Synapse|Databricks|Fabric|Dedicated SQL Pool>
1. Propósito e dores do cliente
2. Critérios de sucesso (mensuráveis)
3. Escopo e arquitetura do PoC
4. Resultados (métricas vs critérios) — ex.: custo −X%, tempo −Y%
5. Decisão (go/no-go) e aceite do cliente
```

### Skilling Plan (1.1 / Módulo A 3.2) — seções mínimas
```
Cliente: <nome>
1. Papéis técnicos-alvo (IT Admin, Governance, Ops, Security, Data Eng/Analyst)
2. Skills necessárias por papel
3. Recursos de capacitação (Microsoft Learn paths, certificações)
4. Cronograma e responsáveis
```
