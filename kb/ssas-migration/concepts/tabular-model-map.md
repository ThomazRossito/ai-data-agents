# Modelo Tabular (SSAS) → Físico + Semântico (Databricks)

> Tabelas + relacionamentos + hierarquias do modelo tabular → **tabelas Delta/Unity Catalog** (star
> schema na Gold) + **Databricks Metric Views** (camada semântica). Sem 1:1 SQL: o modelo é desmontado.

## Tabelas → Delta / Unity Catalog (camada física)

| Construto SSAS | Equivalente Databricks | Observações |
|---|---|---|
| **Tabela (dimensão)** `Dim*` | `dim_*` Delta na Gold (view ou tabela materializada) | Colunas visíveis = atributos; colunas ocultas = SKs/chaves de join |
| **Tabela (fato)** `Fat*`/`Fact*` | `fact_*` Delta na Gold (grão atômico) | Preservar chaves naturais + SKs para join com dims |
| **Partição** (`source.expression`) | Query de ingestão Bronze | `Value.NativeQuery` = SQL direto; expressão M = reescrever no pipeline |
| **`sourceColumn` / renome** | `SELECT src AS alias` na view Silver/Gold | Materializar renome no pipeline, não no consumo |
| **Coluna calculada (DAX)** | Coluna derivada em PySpark/SQL na Silver | **⚠️** se depende de row context/medidas (ver `dax-mapping.md`) |
| **Hierarquia** (Ano→Mês→Dia) | Colunas de nível ordenadas (`sortByColumn` → `ORDER BY`) + drill no dashboard/Genie | Sem objeto "hierarquia" no UC; expor via colunas |

> **Pipeline pesado é do `databricks-engineer`; DDL/schema de origem é do `migration-expert`.** Aqui você
> gera o **schema Gold** (CREATE TABLE schema-only, que é o **contrato**) — não a ingestão de produção que o popula.

## Geração DETERMINÍSTICA (agnóstica ao negócio) — regras normativas

O GENERATE **não** escreve SQL à mão (drifta p/ nome de exibição + esquece backtick → não parseia). Um
gerador único e agnóstico — `scripts/ssas_generate.py` — emite o mecânico a partir dos metadados do `.bim`.
Regras que ele implementa, válidas p/ QUALQUER modelo/empresa:

**Mapa fixo de tipos (SSAS/TMSL `dataType` → Delta):**

| SSAS | Delta | | SSAS | Delta |
|---|---|---|---|---|
| `string` | `STRING` | | `dateTime` | `TIMESTAMP` |
| `int64` | `BIGINT` | | `decimal` | `DECIMAL(38,4)` |
| `double` | `DOUBLE` | | `boolean` / `binary` | `BOOLEAN` / `BINARY` |
| `automatic` / desconhecido | `STRING` (fallback — revisar) | | | |

**Nomes (determinístico, sem hardcode de negócio):**

- Tabela Gold = `catalog.gold.<norm(model_name)>_<norm(table)>`; Metric View = `catalog.gold.mv_<norm(model)>_<norm(fact)>`.
- Coluna = `norm(sourceColumn)` — o nome **FÍSICO**, NUNCA o display name (com espaço). `norm()` = minúsculo, sem acento, não-alfanumérico→`_`.
- **Backtick em TODO identificador** (coluna, medida, tabela) — garante SQL válido mesmo com espaço/acento.

**Medida simples → `measure` da Metric View (só o que é seguro):**

- `AGG('Tabela'[Coluna])`, `AGG ∈ {SUM,COUNT,COUNTA,COUNTROWS,DISTINCTCOUNT,MIN,MAX,AVERAGE}` → `` AGG(source.`norm(sourceColumn)`) ``, **somente se a coluna resolve** p/ um `sourceColumn` real.
- `DIVIDE([MedidaA],[MedidaB])` (ambas simples, mesmo fato) → `` try_divide(MEASURE(`MedidaA`), MEASURE(`MedidaB`)) ``.
- Qualquer outra (CALCULATE/VAR/FILTER/SUMMARIZE/SWITCH/time-intel, ou coluna que não resolve) → **flagada, não convertida**.

**Gates (correto-por-construção):** o gerador sai com código ≠ 0 se (a) houver identificador com espaço sem
backtick, ou (b) alguma Metric View referenciar `source:` sem `CREATE TABLE` correspondente. Gate vermelho ⇒ nunca reportar "concluído".

## Relacionamentos → joins do star schema / Metric View

| SSAS | Databricks |
|---|---|
| `relationship` (fromTable.fromColumn → toTable.toColumn) | `JOIN` fato↔dim na view Gold e/ou `joins` da Metric View |
| `isActive: false` (relacionamento inativo) | Documentar; requer join explícito por caso de uso (equivalente a USERELATIONSHIP) — **⚠️** |
| `crossFilteringBehavior: bothDirections` | Filtro bidirecional — **⚠️** revisão (semântica diferente em SQL) |
| Cardinalidade (1:many / many:many) | many:many → tabela ponte; validar antes de materializar |

## Camada semântica → Databricks Metric Views

**Metric Views** (Databricks, 2025) definem a camada semântica em YAML governado por Unity Catalog:
`source` (star schema Gold), `dimensions`, `measures` e joins. É a substituição direta do modelo tabular.

```yaml
# resources/metric_views.yml (empacotado em DAB) — exemplo de referência
version: 0.1
source: catalog.gold.fact_venda_realizada
joins:
  - name: dim_tempo
    source: catalog.gold.dim_tempo
    on: source.data = dim_tempo.data
dimensions:
  - name: ano_mes
    expr: dim_tempo.ano_mes
measures:
  - name: faturamento_total
    expr: SUM(source.faturamento_real)     # medida DAX simples → SQL
```

| Construto SSAS | Alvo semântico Databricks |
|---|---|
| Medida DAX simples (SUM/COUNT/DIVIDE) | `measure` da Metric View (expressão SQL) — ver `dax-mapping.md` |
| Medida DAX complexa (CALCULATE/time-intel) | **⚠️** documentar reescrita — não há `CREATE MEASURE` em SQL |
| `displayFolder` das medidas | Agrupamento lógico (documentar; sem folder nativo) |
| `formatString` | `format` na Metric View / no dashboard |
| Implicit measures desabilitadas | Métricas explícitas em Metric View (governadas) |

## Consumo → AI/BI Dashboards + Genie Spaces

| Consumo SSAS | Alvo Databricks | Quando |
|---|---|---|
| Relatórios fixos (Power BI live) | **AI/BI Dashboard** sobre a Gold / Metric Views | Consumidores de relatório |
| Exploração ad-hoc | **Genie Space** (NLQ) sobre a Gold / Metric Views | Analistas self-service |
| Perspectives (subset por persona) | Views por persona **ou** páginas de dashboard | ⚠️ sem objeto nativo |

Ambos herdam a RLS das views/tabelas subjacentes (ver `rls-and-security.md`).

## Reconciliação (origem×destino)

Contagem por tabela; `SUM` das medidas-chave (±0.01%); `DISTINCTCOUNT` das dimensões; `MIN/MAX` de datas;
top-N medidas comparadas SSAS (DAX) × Databricks (SQL). Se a medida legada era agregada (VertiPaq) e a
Gold é grão atômico, avisar que 1:1 não bate no grão. DQ estatística avançada → `data-quality-steward`.
