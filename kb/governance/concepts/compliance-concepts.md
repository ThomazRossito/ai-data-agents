# Compliance e LGPD — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** LGPD, bases legais, DPIA, notificação de violações

---

## LGPD: Bases Legais para Tratamento

| Base Legal | Quando Usar | Exemplos |
|-----------|-------------|---------|
| **Consentimento** | Dado explícito e documentado | Newsletter, marketing |
| **Contrato** | Necessário para contrato | Dados de compra, entrega |
| **Obrigação Legal** | Requerido por lei | Fiscal, trabalhista |
| **Legítimo Interesse** | Interesse equilibrado | Analytics anonimizados |
| **Proteção do Titular** | Emergência | Dados de saúde |
| **Pesquisa** | Fins acadêmicos | Estudos anonimizados |

---

## Mapeamento de Dados (Data Mapping)

Documento obrigatório para cada sistema com PII:

| Campo | Exemplo |
|-------|---------|
| **Sistema** | CRM |
| **Tipo de Dado** | Nome, CPF, Email |
| **Base Legal** | Contrato |
| **Retenção** | 5 anos |
| **Compartilhamento** | Nenhum |
| **Responsável** | Data Privacy Officer |

---

## Direitos dos Titulares LGPD

| Direito | Prazo para Resposta | Ação |
|---------|--------------------|----|
| **Acesso** | 15 dias | Fornecer relatório dos dados |
| **Correção** | 15 dias | Atualizar dado incorreto |
| **Exclusão** | 15 dias | Erasure (ver patterns/) |
| **Portabilidade** | 15 dias | Exportar dados em formato aberto |
| **Oposição** | Imediato | Parar tratamento |
| **Revogação** | Imediato | Parar processamento |

---

## DPIA: Quando É Obrigatório

DPIA (Data Protection Impact Assessment) é obrigatório quando:
- Processamento em larga escala de dados sensíveis
- Uso de novos produtos/tecnologias de risco
- Monitoramento sistemático de indivíduos

---

## Breach Notification (Violação de Dados)

| Prazo | Ação |
|-------|------|
| **Imediato** | Detectar e conter o incidente |
| **72 horas** | Notificar ANPD (se impacto significativo) |
| **Prazo razoável** | Notificar titulares afetados |

---

## Retenção de Dados

| Tipo | Retenção | Base Legal |
|------|----------|-----------|
| **Dados comerciais** | 5 anos | Código Civil |
| **Dados fiscais** | 5 anos | Lei Tributária |
| **Dados trabalhistas** | 20 anos | CLT |
| **Dados de saúde** | 20 anos | CFM |
| **Dados de crianças** | Até revogação do consentimento | LGPD Art. 14 |
