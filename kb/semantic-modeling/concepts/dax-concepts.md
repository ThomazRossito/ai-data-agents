# DAX — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Contexto de filtro, funções DAX, convenções de nomes, gotchas

---

## Dois Tipos de Contexto

| Contexto | Onde | O que faz |
|----------|------|-----------|
| **Row Context** | Colunas calculadas | Executa para cada linha da tabela |
| **Filter Context** | Medidas | Agrega respeitando filtros aplicados |

**Regra:** Preferir medidas (filter context) sobre colunas calculadas (row context).

---

## Funções Fundamentais

| Função | Propósito | Quando usar |
|--------|-----------|-------------|
| **CALCULATE** | Modifica contexto de filtro | Filtros explícitos, time intelligence |
| **DIVIDE** | Divisão segura sem erro | Toda divisão — nunca `/` diretamente |
| **SUMX / AVERAGEX** | Iteração linha-por-linha | Cálculos que não cabem em SUM/AVG simples |
| **VAR / RETURN** | Variáveis locais | Legibilidade + evitar re-computação |
| **ALL / ALLEXCEPT** | Remove filtros | Percentual do total, comparações |
| **FILTER** | Filtra tabela por condição complexa | Com RELATED, condições compostas |

---

## Time Intelligence: Funções de Data

| Função | Calcula |
|--------|---------|
| `DATESBETWEEN` | Range entre datas |
| `DATESYTD` | Acumulado desde início do ano |
| `DATESQTD` | Acumulado desde início do trimestre |
| `DATEADD(..., -1, MONTH)` | Período anterior |
| `DATEADD(..., -1, YEAR)` | Mesmo período ano anterior |

**Pré-requisito:** Tabela `dim_data` com coluna DATE marcada como "Date Table" no Semantic Model.

---

## Naming Conventions para Medidas

| Tipo | Prefixo | Exemplo |
|------|---------|---------|
| **Sum** | `Total *` | `Total Sales`, `Total Quantity` |
| **Average** | `Avg *` | `Avg Sale`, `Avg Price` |
| **Count** | `Count *` | `Count Orders`, `Count Clients` |
| **Percentage** | `* %` | `Sales %`, `Growth %` |
| **Ratio** | `* Ratio` | `Profit Ratio`, `Conversion Ratio` |

---

## ALL vs ALLEXCEPT

| Função | Remove | Mantém |
|--------|--------|--------|
| `ALL(tabela)` | Todos os filtros da tabela | Nada |
| `ALL(coluna)` | Filtros de uma coluna | Outros filtros |
| `ALLEXCEPT(tabela, col1, col2)` | Todos exceto col1 e col2 | col1, col2 |

---

## FILTER vs Filtro em CALCULATE

| Abordagem | Performance | Quando usar |
|-----------|-------------|-------------|
| Filtro direto em CALCULATE | Rápido | Filtros simples por coluna |
| FILTER (row by row) | Mais lento | Condições complexas, RELATED |

---

## Gotchas

| Gotcha | Solução |
|--------|---------|
| Divisão por zero (#DIV/0!) | Usar DIVIDE() com default value |
| SUMX em coluna calculada = lento | Usar medida ao invés de coluna |
| RELATED() retorna múltiplos valores | Usar VALUES() ou SUMMARIZE() antes |
| Filter context não se aplica | Verificar relacionamentos ativos |
| Variables redeclaram contexto | VAR dentro de CALCULATE cria novo contexto |
