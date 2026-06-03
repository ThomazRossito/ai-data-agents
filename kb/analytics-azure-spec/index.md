---
domain: analytics-azure-spec
updated_at: 2026-06-03
agents: [azure-analytics-auditor]
---

# Knowledge Base — Analytics on Microsoft Azure Specialization (Audit)

> Fonte de verdade operacional do agente **azure-analytics-auditor**. Consultar SEMPRE
> antes de auditar qualquer documento. NÃO inventar requisitos: todo veredito de controle
> deve sair literalmente desta KB.

## 1. Fonte e Vigência

| Item | Valor |
|---|---|
| Checklist | Analytics on Microsoft Azure Specialization — Program guide, audit checklist, and FAQ |
| Versão | **V2.8.1** |
| Vigência | **1 Jan – 30 Jun 2026** |
| Auditor oficial | ISSI (Information Systems Solutions Inc.) |
| Página oficial | `https://partner.microsoft.com/partnership/specialization/analytics-on-microsoft-azure` |
| Escopo deste agente | **Módulo B — Analytics on Microsoft Azure specialization workload** |
| Fora de escopo | Módulo A (Azure Essentials Cloud Foundation) — mencionar e escalar se solicitado |

> O audit completo cobre Módulo A **e** B (estimativa: 8h). Este agente foca o **Módulo B**.
> Se o usuário pedir avaliação de Módulo A, sinalize que está fora de escopo e oriente.

## 2. Estrutura do Módulo B (4 fases, 7 controles)

| Fase | Controle | Resumo do requisito | Clientes | Janela |
|---|---|---|---|---|
| 1.0 Assess | **1.1 Analytics Portfolio Assessment** | Avaliação de estado atual e requisitos (negócio, landscape, performance, personas, skilling, dados, rede, segurança, DR) | 3 únicos | 24 meses |
| 2.0 Design & PoC/Pilot | **2.1 Solution Design** | Design da solução analytics (roles, fontes, ingestão, storage, encryption, segurança, analytics service, BI, DevOps, ALZ) | 3 únicos | 24 meses |
| 2.0 | **2.2 Azure Well-Architected Review** | Review usando Core WAR, exportar 2 dos 5 pilares | 3 (nome do cliente) | 12 meses |
| 2.0 | **2.3 Proof of Concept ou Pilot** | 3 PoCs/pilots completos validando o design | 3 | 24 meses |
| 3.0 Deployment | **3.1 Deployment** | Solução em produção baseada em design aprovado | 3 únicos | 24 meses |
| 4.0 Review & Release | **4.1 Service Validation & Testing** | Validação de deployment + sign-off do cliente | 3 únicos | 24 meses |
| 4.0 | **4.2 Post-deployment Documentation** | Documentação pós-deploy + SOPs | 3 únicos | 24 meses |

> **Analytics Service aceito** (controles 2.1, 2.3, 3.1): Azure Synapse Analytics **OU**
> Azure Databricks **OU** Microsoft Fabric **OU** Dedicated SQL Pool (ex-SQL Data Warehouse).
> Basta UM — não é exigido demonstrar todos.

Detalhe completo de cada controle: `kb/analytics-azure-spec/concepts/module-b-controls.md`
Regras de evidência, glossário e contagem de clientes: `kb/analytics-azure-spec/concepts/evidence-rules.md`

## 3. Princípios de Evidência (do checklist — invioláveis)

1. **Evidência deve ser verificável, customer-specific e reproduzível.** Resumos/excertos só valem se rastreáveis ao artefato fonte.
2. **Projeto válido = concluído e em produção** com Go-Live e sign-off documentado do cliente. Design-only, em andamento ou interno **não** qualifica.
3. **PoC/Pilot** só conta como projeto completo se tiver data de conclusão + aceite do cliente documentado.
4. **Sign-off verbal/ não documentado é insuficiente.**
5. **PowerPoint** é aceito como visão geral, mas **excertos não são evidência** — documentos-fonte precisam existir.
6. **Timeframe é medido a partir da data do audit** (ex: "últimos 24 meses").

## 4. Rubrica de Veredito — DOIS EIXOS (determinística)

> **Regra de ouro:** separe **cobertura de evidência** (qualidade do que existe) de **contagem de
> clientes** (requisito ISSI de 3). O nº de clientes NUNCA rebaixa a cobertura — são reportados
> separadamente. Isso permite auditar 1 cliente hoje sem que tudo vire "não atendido".

**Eixo A — Cobertura de evidência** (avaliada APENAS sobre o(s) cliente(s) em escopo, ignorando contagem):

O veredito é **computado por subitem**, não por impressão geral (garante determinismo):
1. Liste os subitens obrigatórios do controle (ver `concepts/module-b-controls.md`).
2. Para cada subitem: `covered` = existe evidência **localizável** que o **demonstra** (não apenas menciona o tópico).
3. Aplique a fórmula fixa:

| Cobertura | Critério EXATO |
|---|---|
| ✅ **Completa** | `covered == total` de subitens obrigatórios **E** formalização exigida presente (ex.: sign-off no 4.1, SOW no 3.1). |
| 🟡 **Parcial** | `0 < covered < total` **OU** subitens cobertos mas falta formalização (sign-off/SOW/export). Liste cobertos vs faltantes. |
| ❌ **Ausente** | `covered == 0` — **ZERO** evidência rastreável do controle. Use SÓ quando nada toca o tema. |
| ⚠️ **Needs Review** | Evidência existe mas ilegível/ambígua/não extraível mesmo após OCR. Nunca assumir. |

> **Fronteira 🟡 vs ❌ (anti-oscilação):** se QUALQUER subitem tem evidência → no mínimo 🟡. ❌ é
> reservado para "nenhuma menção rastreável". Tema tocado de forma informal/incompleta = **🟡, nunca ❌**.

**Eixo B — Clientes únicos:** conte clientes nominais distintos com evidência. Reporte `x/3`
(ISSI exige 3, salvo controle com nº próprio). É um **gate separado**, informativo.

**Status ISSI (audit-ready) por controle** = ✅ apenas se Cobertura ✅ Completa **E** clientes ≥ exigido.
Caso contrário, indique o que falta em cada eixo (cobertura e/ou +N clientes).

## 4.1 Modo de escopo de cliente

- **Default (multi-cliente / ISSI):** reporte os dois eixos; Status ISSI exige 3 clientes.
- **Modo cliente único** (usuário diz "só o cliente X", "estamos com 1 cliente", ou só há 1 cliente
  nos insumos): o **foco do veredito é o Eixo A** (cobertura para aquele cliente). O Eixo B é mostrado
  como lacuna conhecida e esperada (`Clientes: 1/3 — faltam 2 para o ISSI`), **sem rebaixar** a cobertura.
  Assim o usuário enxerga o quão completo está o dossiê do cliente atual.

Mapa de inferência **recurso (screenshot) → subitem de controle**: `concepts/resource-control-map.md`.
Rubrica detalhada e exemplos: `concepts/verdict-rubric.md`.

## 5. Regras do Agente (resumo — detalhe no prompt)

- **Grounding absoluto:** só marque ✅ se a evidência estiver de fato localizada num documento. Cite `arquivo › página/aba/slide › trecho`. Nunca presuma.
- **Falha amigável:** em ❌/🟡 explique em linguagem clara o que falta, qual documentação é aceita, quantos clientes e qual janela — sempre orientando o próximo passo.
- **Multi-formato:** PDF, DOCX, XLSX, PPTX, CSV, TXT/MD **e imagens PNG/JPG (via OCR, incluindo PDFs escaneados)**. Screenshots do Azure Portal são evidência de primeira classe — OCR é padrão. Extrair com rastreabilidade de localização (página/aba/slide), marcando texto de OCR com `(OCR)`.
- **Idioma:** seguir o idioma do usuário (PT-BR/EN). Nomes oficiais de controles e produtos permanecem em inglês.
