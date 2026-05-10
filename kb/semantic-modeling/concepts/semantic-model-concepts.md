# Semantic Model — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Star schema para BI, granularidade, relacionamentos, SCD2, naming conventions

---

## Fundação: Star Schema

```
┌─────────────────────────────────────────────┐
│          FACT TABLE (Fatos)                 │
│          fact_vendas                        │
│  ┌──────────────────────────────────────┐  │
│  │ sk_cliente (FK→dim_cliente)          │  │
│  │ sk_produto (FK→dim_produto)          │  │
│  │ sk_data (FK→dim_data)                │  │
│  │ MEASURES: quantidade, valor, desconto│  │
│  └──────────────────────────────────────┘  │
│         ↑                 ↑           ↑     │
├─────────┼─────────────────┼───────────┤    │
│ dim_cliente    dim_produto         dim_data │
└─────────────────────────────────────────────┘
```

---

## Regras de Fact Tables

| Conteúdo | Permitido | Exemplo |
|---------|-----------|---------|
| Foreign Keys | Sim (ocultos) | sk_cliente, sk_data |
| Measures numéricas | Sim | quantidade, valor, desconto |
| Atributos descritivos | Não | nome_cliente (vai em dim_) |
| Degenerate dimensions | Sim (com cautela) | numero_nfe, numero_pedido |

---

## Regras de Dimension Tables

| Conteúdo | Obrigatório |
|---------|-------------|
| Surrogate Key (PK BIGINT) | Sim — nunca expor ao usuário |
| Natural Key (nk_*) | Recomendado |
| Atributos descritivos | Sim — expostos no BI |
| SCD2 flags (is_ativo, data_inicio/fim) | Quando há histórico |

---

## Granularidade das Fact Tables

| Granularidade | Exemplo | Quando usar |
|--------------|---------|-------------|
| **Transação** | 1 linha por item de pedido | Análise detalhada |
| **Dia** | 1 linha por dia por cliente | Análise diária |
| **Mês** | 1 linha por mês por região | Relatório mensal |

**Recomendação:** Usar granularidade mais fina (transação) no Lakehouse; agregações no Semantic Model.

---

## Relacionamentos: Apenas Many-to-One

| Tipo | Permitido | Motivo |
|------|-----------|--------|
| Many-to-One (Fact → Dim) | Sim | Filtros automáticos corretos |
| One-to-Many | Não | Quebra contexto de filtro |
| Many-to-Many | Não | Filtrar por cliente não isola produtos únicos |

**Solução para Many-to-Many:** Criar tabela bridge no Lakehouse.

---

## Role-Playing Dimensions

Quando uma dimensão se relaciona com a fato de múltiplas formas (ex: datas múltiplas):

```
fact_vendas tem 3 datas:
  sk_data_venda → dim_data_venda (cópia lógica de dim_data)
  sk_data_entrega → dim_data_entrega (cópia lógica de dim_data)
  sk_data_faturamento → dim_data_faturamento (cópia lógica de dim_data)
```

No BI, criar 3 cópias lógicas apontando para a mesma tabela física.

---

## SCD2 no Semantic Layer

Quando dim_* tem histórico (múltiplas versões de um registro):
- Filtrar `is_ativo = TRUE` no Semantic Model para expor apenas versão atual
- Usar relacionamento INATIVO para análises históricas (USERELATIONSHIP em DAX)

---

## Naming Conventions

| Tipo | Padrão | Exemplo |
|------|--------|---------|
| Tabela Fato | `fact_*` | `fact_vendas`, `fact_eventos` |
| Tabela Dimensão | `dim_*` | `dim_cliente`, `dim_produto` |
| Coluna (atributo) | `tabela_atributo` | `cliente_nome`, `produto_categoria` |
| Medida | `Total *`, `Avg *`, `Count *` | `Total Vendas`, `Avg Desconto` |
| PK Técnica (oculta) | `sk_*` | `sk_cliente` (hidden) |
| Foreign Key (oculta) | `sk_*` | `sk_cliente` em fact (hidden) |

---

## Relacionamentos Ativos vs Inativos

| Tipo | Comportamento | Quando usar |
|------|--------------|-------------|
| **Ativo** | Filtros propagam automaticamente | Relacionamento principal |
| **Inativo** | Requer USERELATIONSHIP em DAX | Múltiplas datas, role-playing dims |
