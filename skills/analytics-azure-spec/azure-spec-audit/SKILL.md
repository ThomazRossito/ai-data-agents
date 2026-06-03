---
name: azure-spec-audit
description: "Playbook operacional do agente azure-analytics-auditor: extrair texto com rastreabilidade de localização (página/aba/slide) de PDF, DOCX, XLSX, PPTX, CSV/TXT/MD e auditar cada documento contra os 7 controles do Módulo B da Analytics on Microsoft Azure Specialization, produzindo coverage matrix com veredito e citação de evidência."
updated_at: 2026-06-03
source: kb/analytics-azure-spec (index + concepts/module-b-controls + concepts/evidence-rules)
agent: azure-analytics-auditor
domain: analytics-azure-spec
---

# Skill — Auditoria da Analytics on Microsoft Azure Specialization (Módulo B)

> **Uso:** leia este playbook na primeira chamada da sessão. Ele define COMO extrair conteúdo
> dos documentos com rastreabilidade e COMO mapear cada trecho aos controles do Módulo B.
> A fonte normativa dos controles é a KB `kb/analytics-azure-spec/` — este skill é o "como fazer".

## Princípio fundamental: grounding com localização

Toda afirmação de "evidência encontrada" precisa apontar `arquivo › localização › trecho`. Para isso
a extração precisa preservar **número de página / aba / slide / linha**. Nunca audite a partir de
memória ou suposição — sempre extraia e cite.

## Passo 0 — Inventário do input

Liste os arquivos do diretório de input do usuário e classifique por extensão. Trate como auditáveis:
`.pdf .docx .xlsx .xls .pptx .csv .txt .md`. Para extensões não suportadas (ex: `.msg`, imagens),
registre como ⚠️ Needs Review e siga.

```bash
find "<INPUT_DIR>" -type f \( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.xlsx' \
  -o -iname '*.xls' -o -iname '*.pptx' -o -iname '*.csv' -o -iname '*.txt' -o -iname '*.md' \) | sort
```

## Passo 1 — Extração por formato (com localização)

Instale dependências uma vez por sessão (sandbox): `pip install pdfplumber python-docx openpyxl python-pptx --break-system-packages -q`

**PDF (texto por página):**
```python
import pdfplumber
with pdfplumber.open(path) as pdf:
    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        # guarde (page=i, text) para rastrear "p. i"
```

**DOCX (parágrafos + headings + tabelas):**
```python
from docx import Document
doc = Document(path)
for p in doc.paragraphs:
    # p.style.name identifica Heading 1/2... → use como "seção"
    ...
for t in doc.tables:
    for row in t.rows:
        ...  # texto de células
```

**XLSX (por aba + célula):**
```python
import openpyxl
wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                ... # rastrear ws.title + cell.coordinate
```

**PPTX (por slide + shape):**
```python
from pptx import Presentation
prs = Presentation(path)
for i, slide in enumerate(prs.slides, 1):
    for shape in slide.shapes:
        if shape.has_text_frame:
            ... # rastrear "slide i"
```

**CSV/TXT/MD:** leitura direta; rastrear por número de linha. (Para PDF escaneado sem texto,
sinalize ⚠️ Needs Review — OCR está fora do escopo padrão; ofereça rodar OCR só se o usuário pedir.)

> Dica de eficiência: gere um índice JSON intermediário `{arquivo: [{loc, texto}]}` e faça a busca
> por palavras-chave dos controles em cima dele — evita reprocessar e mantém a citação exata.

## Passo 2 — Mapa de palavras-chave por controle (busca dirigida)

Use como gatilho de busca; a confirmação é semântica (o trecho precisa DEMONSTRAR, não só mencionar).

| Controle | Palavras-chave/sinais a procurar |
|---|---|
| 1.1 Assessment | assessment, current state, business need, personas, skilling plan, data sources, networking, SLA, DR, DMA report |
| 2.1 Solution Design | solution design, architecture diagram, ingestion (Data Factory/Databricks/Fabric/Synapse), storage (Data Lake/Lakehouse/Blob), encryption/TDE/Key Vault, RBAC, landing zone, Power BI/Tableau, DevOps/Git |
| 2.2 Well-Architected | Well-Architected Review, WAR, pillars (Reliability, Security, Cost, Operational Excellence, Performance), pilar export |
| 2.3 PoC/Pilot | proof of concept, PoC, pilot, success criteria, results, test plan |
| 3.1 Deployment | production deployment, SOW, HLD, LLD, as-built, project plan, go-live |
| 4.1 Service Validation | testing, performance validation, UAT, sign-off, acceptance |
| 4.2 Post-deployment | runbook, SOP, standard operating procedure, post-deployment, handover, BAU |

## Passo 3 — Validar cada evidência (filtro de qualidade)

Aplique o checklist de `kb/analytics-azure-spec/concepts/evidence-rules.md`:
cobertura do subitem, cliente nominal, janela (12/24m), produção+sign-off (quando exigido),
rastreabilidade, analytics service presente (quando exigido). Conte clientes únicos (alvo: 3).

## Passo 4 — Atribuir veredito por controle

✅ Met · 🟡 Partially Met · ❌ Not Found · ⚠️ Needs Review (rubrica no `index.md` §4).
Para 🟡/❌ sempre escreva orientação acionável (o que falta, documentação aceita, nº de clientes, janela).

## Passo 5 — Relatório (salvar 2 arquivos)

Gere em `output/azure-spec-audit/<slug>/` (slug = nome do cliente/lote em snake_case; sem nome →
`<YYYYMMDD>_audit`):

- `audit_report.md` — legível: sumário executivo + coverage matrix + detalhe por controle (evidência citada OU gap orientado) + lista de documentos analisados.
- `findings.json` — machine-readable: `[{control, verdict, evidence:[{file, location, excerpt, customer, date}], gaps:[...], unique_customers:N}]`.

### Esqueleto do audit_report.md

```markdown
# Auditoria — Analytics on Microsoft Azure Specialization (Módulo B, V2.8.1)

**Lote/Cliente:** <slug>  ·  **Data da auditoria:** <ISO>  ·  **Documentos analisados:** <N>

## Sumário de Cobertura
| Controle | Veredito | Clientes únicos | Janela OK | Lacuna principal |
|---|---|---|---|---|
| 1.1 Assessment | ✅/🟡/❌ | x/3 | sim/não | ... |
| ... | | | | |

**Prontidão geral:** <X de 7 controles atendidos>. Veredito: Pronto / Quase pronto / Não pronto.

## Detalhe por Controle
### 1.1 Analytics Portfolio Assessment — <veredito>
- Evidência: `arquivo.pdf › p.4 › "Assessment Report — Cliente ACME..."`
- Subitens cobertos: ... / Faltando: ...
- (se gap) Para atender: forneça <documentação aceita> de 3 clientes únicos nos últimos 24 meses.
...

## Documentos analisados
- arquivo1.pdf (31 p.) — relevante a 1.1, 2.1
- ...
```

## Anti-patterns (fortes)

❌ Marcar ✅ sem citar arquivo+localização+trecho.
❌ Inferir cliente, data ou sign-off que não está no documento.
❌ Tratar menção de um tópico como demonstração do controle.
❌ Inventar requisito que não está na KB (a KB é a fonte; V2.8.1).
❌ Rodar OCR ou ferramenta pesada sem o usuário pedir.
❌ Relatório "tudo reprovado" sem orientação — todo gap precisa de próximo passo amigável.
