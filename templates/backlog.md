# Backlog de Requisitos — {{NOME_DO_PROJETO}}

> **Template Business Analyst:** Gerado automaticamente pelo agente `business-analyst`
> a partir de transcrição de reunião ou documento de briefing.
> Campos marcados com `[PREENCHER]` devem ser completados pelo agente.
> Use `/plan <caminho_deste_arquivo>` para gerar o PRD e SPEC.

---

## 1. Metadados da Reunião

| Campo | Valor |
|-------|-------|
| **Projeto** | [PREENCHER] |
| **Data da Reunião** | [PREENCHER ou "Não informado"] |
| **Fonte do Documento** | [Transcript / Briefing / E-mail / Notas] |
| **Gerado em** | [DATA DE GERAÇÃO] |

---

## 2. Participantes e Stakeholders

| Nome / Papel | Área | Responsabilidades Mencionadas |
|-------------|------|-------------------------------|
| [PREENCHER] | [PREENCHER] | [PREENCHER] |

---

## 3. Contexto e Objetivo do Projeto

> Descreva em 2-4 frases o problema de negócio ou oportunidade identificada,
> e o que o projeto deve resolver.

[PREENCHER]

---

## 4. Decisões Tomadas na Reunião

| # | Decisão | Responsável | Impacto |
|---|---------|-------------|---------|
| 1 | [PREENCHER] | [PREENCHER] | [Técnico / Negócio / Prazo] |

---

## 5. Backlog Priorizado

### 🔴 P0 — Críticos (máximo 3 itens)
> Bloqueiam outras tarefas, impacto em produção ou deadline imediato.

| ID | Descrição | Domínio Técnico | Agente Responsável | Dependências | Critério de Aceite |
|----|-----------|-----------------|-------------------|--------------|-------------------|
| P0-01 | [PREENCHER] | [pipeline-design / sql / spark / etc.] | [agente] | [Nenhuma / ID] | [PREENCHER] |

---

### 🟡 P1 — Importantes
> Essenciais para o objetivo, entrega nesta sprint ou ciclo.

| ID | Descrição | Domínio Técnico | Agente Responsável | Dependências | Critério de Aceite |
|----|-----------|-----------------|-------------------|--------------|-------------------|
| P1-01 | [PREENCHER] | [PREENCHER] | [PREENCHER] | [PREENCHER] | [PREENCHER] |

---

### 🟢 P2 — Desejáveis
> Melhorias e funcionalidades adicionais. Podem ser adiados.

| ID | Descrição | Domínio Técnico | Agente Responsável | Dependências | Critério de Aceite |
|----|-----------|-----------------|-------------------|--------------|-------------------|
| P2-01 | [PREENCHER] | [PREENCHER] | [PREENCHER] | [PREENCHER] | [PREENCHER] |

---

## 6. Domínios Técnicos Identificados

| Domínio | Evidência no Documento | Plataforma |
|---------|----------------------|-----------|
| [pipeline-design / sql-patterns / spark-patterns / data-quality / governance / semantic-modeling / databricks / fabric] | [Trecho ou resumo] | [Databricks / Fabric / Cross-Platform] |

---

## 7. Restrições e Dependências Externas

| Tipo | Descrição | Impacto nos Itens |
|------|-----------|------------------|
| Prazo | [PREENCHER ou "Não mencionado"] | [IDs afetados] |
| Técnica | [PREENCHER ou "Nenhuma identificada"] | [IDs afetados] |
| Acesso/Permissão | [PREENCHER ou "Nenhuma identificada"] | [IDs afetados] |
| Dependência Externa | [PREENCHER ou "Nenhuma identificada"] | [IDs afetados] |

---

## 8. Perguntas em Aberto

> Itens que precisam de resposta antes de iniciar a execução técnica.
> Devem ser resolvidos antes de usar `/plan`.

| # | Pergunta | Para Quem | Impacto se Não Respondida |
|---|----------|-----------|--------------------------|
| 1 | [PREENCHER] | [Stakeholder / Time técnico] | [Bloqueia P0-01 / Atrasa P1-02 / etc.] |

---

## 9. Resumo Executivo para `/plan`

> Parágrafo único e técnico pronto para ser usado como input direto do comando `/plan`.
> Deve mencionar: objetivo, plataforma(s), domínios técnicos, itens P0 e restrições relevantes.

[PREENCHER — gerado automaticamente pelo business-analyst]

---

## 10. Checklist de Qualidade do Backlog

- [ ] Todos os itens P0 têm critério de aceite definido
- [ ] Nenhum item P0 tem dependência externa não resolvida
- [ ] Domínio técnico mapeado para todos os itens
- [ ] Agente responsável identificado para todos os itens
- [ ] Perguntas em aberto documentadas
- [ ] Resumo para `/plan` gerado (Seção 9)
- [ ] Máximo de 3 itens P0 respeitado
