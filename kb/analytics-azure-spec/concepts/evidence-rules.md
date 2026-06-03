# Regras de Evidência, Glossário e Contagem de Clientes

> Critérios que determinam se um documento "conta" como evidência válida. O agente aplica
> estes filtros ANTES de marcar um controle como ✅ Met.

## Glossário (definições oficiais do checklist)

| Termo | Definição | Implicação para auditoria |
|---|---|---|
| **Project** | Engajamento executado, deployado em produção e formalmente concluído. | Design-only, em andamento ou interno **não** qualifica. |
| **Completed Project** | Solução em produção (go-live) **e** sign-off/aceite formal documentado. | Procurar prova de go-live + aceite. |
| **Go-Live** | Data em que a solução entra em operação em produção. | Test/lab/pilot só conta se formalmente transicionado para produção. |
| **Proof of Concept (PoC)** | Engajamento de escopo limitado para validar viabilidade. | Só conta como projeto completo se tiver conclusão documentada + aceite. |
| **Pilot** | Deployment controlado pré-produção. | Qualifica só com data de conclusão documentada + sign-off. |
| **Customer Case Study / Example** | Projeto concluído usado como evidência. | O mesmo projeto pode ser reusado entre controles se cumprir os requisitos. |
| **Customer Sign-Off** | Confirmação documentada de que a solução atendeu os requisitos acordados. | Confirmação verbal / não documentada é **insuficiente**. |
| **Timeframe** | Ex: "nos últimos 12/24 meses" — medido a partir da **data do audit**. | Verificar datas dos documentos contra a janela. |
| **Greenfield Project** | Novo deployment, não baseado em migração. | Aceitável só onde explicitamente permitido; ainda exige conclusão + sign-off. |
| **Evidence** | Verificável, customer-specific e reproduzível. | Resumos/excertos só valem se rastreáveis ao artefato fonte. |

## Matriz de Contagem de Clientes e Janela (Módulo B)

| Controle | Clientes únicos | Janela | Observação especial |
|---|---|---|---|
| 1.1 Analytics Portfolio Assessment | 3 | 24 meses | todos os subitens do assessment por cliente |
| 2.1 Solution Design | 3 | 24 meses | nota Fabric ALZ: 10 constraints se sem Identity/Networking |
| 2.2 Well-Architected Review | 3 (com nome do cliente) | 12 meses | 2 dos 5 pilares exportados, Core WAR |
| 2.3 PoC/Pilot | 3 | 24 meses | propósito + critérios de sucesso + resultados |
| 3.1 Deployment | 3 | 24 meses | ≥2 itens da lista, sequência design→produção |
| 4.1 Service Validation & Testing | 3 | 24 meses | exige sign-off do cliente; pode reusar clientes do 3.1 |
| 4.2 Post-deployment Documentation | 3 | 24 meses | inclui SOPs |

> **Regra padrão:** salvo indicação contrária, o parceiro deve mostrar pelo menos **3 clientes
> únicos** com deployments recentes nos **últimos 24 meses**. O mesmo cliente/case study pode ser
> reusado entre controles. Módulos A e B podem usar os mesmos clientes.

## Checklist de Validação de uma Evidência (aplicar por documento × controle)

1. **Cobertura:** o documento cobre o(s) subitem(ns) exigido(s) do controle? (não basta mencionar o tópico — precisa demonstrar)
2. **Customer-specific:** há um cliente nominal identificável? (genérico/template sem cliente = fraco)
3. **Janela temporal:** há data e ela cai dentro de 12/24 meses da data do audit?
4. **Produção + sign-off:** quando exigido (3.1, 4.1), há prova de go-live e aceite documentado?
5. **Rastreabilidade:** a evidência aponta para artefato-fonte (não só um excerto de PowerPoint)?
6. **Analytics service:** quando exigido (2.1, 2.3, 3.1), há ao menos UM de Synapse/Databricks/Fabric/Dedicated SQL Pool?

Se 1–6 OK para ≥3 clientes → ✅ Met. Se parcial → 🟡 Partially Met (liste o que falta).
Se nada → ❌ Not Found. Se ilegível/ambíguo → ⚠️ Needs Review.

## Como reportar localização (rastreabilidade)

Sempre que marcar ✅/🟡, citar onde a evidência foi encontrada no formato:

- PDF: `arquivo.pdf › p. <N> › "<trecho curto>"`
- DOCX: `arquivo.docx › seção/heading "<título>" › "<trecho>"`
- XLSX: `arquivo.xlsx › aba "<sheet>" › célula/intervalo <ref> › "<valor>"`
- PPTX: `arquivo.pptx › slide <N> › "<trecho>"`
- CSV/TXT/MD: `arquivo › linha <N> › "<trecho>"`
