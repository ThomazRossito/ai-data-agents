# Catálogo de Conversão HiveQL/Impala → Databricks SQL

> Catálogo normativo para conversão de **DML/query HiveQL**, **Impala SQL**, e código não-SQL do
> ecossistema Hadoop (**Pig Latin**, **MapReduce Java**) para Databricks SQL/PySpark. Irmão de
> `kb/hadoop-migration/concepts/hive-ddl-conversion.md` (DDL/tipos/particionamento — ler primeiro para
> contexto de namespace e nomenclatura Lakebridge/Remorph) e complementar a
> `kb/sql-patterns/concepts/tsql-conversion-catalog.md` (mesmo padrão de catálogo, origem SQL Server;
> reaproveitar §4 SQL Scripting e §2.2 `RELY` daquele arquivo quando aplicável aqui) e a
> `kb/sql-patterns/concepts/dialect-concepts.md` (mapeamento genérico Spark SQL/T-SQL/KQL). Consultar
> SEMPRE antes de converter HiveQL/Pig/MapReduce. NÃO inventar mapeamentos — construto sem exemplo no
> curso está marcado explicitamente em §13 "Lacunas do Curso".

**Domínio:** sql-patterns — Conversão HiveQL/Impala → Databricks SQL (Migração)
**Fonte:** Curso "Hadoop Migration" — `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`
(seção principal, 2 páginas), complementado por `00 - Foundations/0.3 Lecture - Architecture and
Feature Mapping.md` (feature mapping/complexidade)
**Agentes:** migration-expert, databricks-engineer

**Nomenclatura:** ver `kb/hadoop-migration/concepts/hive-ddl-conversion.md` — nota de nomenclatura
(curso chama de "Remorph"; nome atual do produto é **Lakebridge**, que incorpora tecnologia
**BladeBridge**). Usar sempre "Lakebridge" neste arquivo.

---

## 1. Onde HiveQL e Databricks SQL Alinham

**Spark SQL foi construído com compatibilidade Hive como objetivo central de design.** A vasta
maioria do DML HiveQL transfere direto, sem alteração:

| Construto | HiveQL | Databricks SQL | Compatibilidade |
|---|---|---|---|
| `SELECT`/`WHERE`/`GROUP BY`/`ORDER BY` | SQL padrão | SQL padrão | Idêntico |
| `JOIN` (todos os tipos) | `INNER`, `LEFT`, `RIGHT`, `FULL`, `CROSS` | Igual | Idêntico |
| Subqueries | Suportado | Suportado | Idêntico |
| CTEs (`WITH`) | Suportado (Hive 0.13+) | Suportado | Idêntico |
| `UNION` / `UNION ALL` | Suportado | Suportado | Idêntico |
| `CASE WHEN` | Suportado | Suportado | Idêntico |
| `HAVING` | Suportado | Suportado | Idêntico |
| Window functions | `ROW_NUMBER()`, `RANK()`, `LAG()`, `LEAD()` etc. | Igual | Idêntico |
| `LATERAL VIEW EXPLODE` | Suportado | Suportado (+ `EXPLODE` direto no `SELECT`, sem `LATERAL VIEW`) | Idêntico + extensão |
| `INSERT INTO` / `INSERT OVERWRITE` | Suportado | Suportado (com semântica Delta) | Idêntico |
| Funções de agregação | `SUM`, `AVG`, `COUNT`, `MAX`, `MIN` etc. | Igual | Idêntico |

```sql
-- Databricks: EXPLODE pode ser usado direto no SELECT (sem LATERAL VIEW)
SELECT c.customer_id, EXPLODE(c.tags) AS tag FROM customers c;
-- Ambas as formas funcionam no Databricks — LATERAL VIEW EXPLODE (Hive) e EXPLODE direto
```

> **Regra prática:** se uma query usa só construtos SQL padrão (a maioria das queries de data
> warehouse), ela roda no Databricks **sem modificação**. Concentrar esforço de conversão nos
> construtos Hive-específicos (§2-4) e no código não-SQL (Pig/MapReduce, §5-6).

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "1. Where HiveQL and Databricks
SQL Align".

---

## 2. Construtos Hive que Exigem Reescrita

### 2.1 TRANSFORM / MAP / REDUCE

Fazem *pipe* de dado através de scripts externos (Python/shell). **Sem equivalente direto** em
Databricks SQL — devem ser reescritos como UDF ou lógica PySpark.

| HiveQL | Equivalente Databricks | Nota |
|---|---|---|
| `SELECT TRANSFORM(col1, col2) USING 'python script.py'` | UDF Python ou PySpark `mapInPandas` | Reescrever o script externo como UDF registrada |
| `MAP col1, col2 USING 'mapper.py'` | PySpark `map`/`mapPartitions` | Converter lógica do mapper para PySpark |
| `REDUCE col1, col2 USING 'reducer.py'` | PySpark `groupBy().applyInPandas()` | Converter lógica do reducer para operação agrupada PySpark |

```sql
-- Hive: pipe de dado através de script Python externo
SELECT TRANSFORM(customer_id, first_name, last_name)
USING 'python /scripts/normalize_names.py'
AS (customer_id INT, normalized_name STRING)
FROM customers;
```

```python
# Databricks: reescrito como UDF Python
from pyspark.sql.functions import udf, col
from pyspark.sql.types import StringType

@udf(returnType=StringType())
def normalize_name(first_name, last_name):
    return f"{first_name.strip().title()} {last_name.strip().title()}"

result = spark.table("customers").select(
    col("customer_id"),
    normalize_name(col("first_name"), col("last_name")).alias("normalized_name")
)
```

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "TRANSFORM / MAP / REDUCE
Clauses".

### 2.2 REFLECT() / JAVA_METHOD() e Colunas Virtuais

| HiveQL | Databricks | Nota |
|---|---|---|
| `REFLECT()` (reflection Java) | **Não suportado** | Reescrever como UDF Python |
| `JAVA_METHOD()` | **Não suportado** | Reescrever como UDF Python, ou registrar o JAR Java (§6) |
| `INPUT__FILE__NAME` (coluna virtual) | `_metadata.file_path` | Usar coluna de metadata do Delta |
| `BLOCK__OFFSET__INSIDE__FILE` (coluna virtual) | `_metadata.file_block_start` | Usar coluna de metadata do Delta |

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seções "11. HiveQL Function
Compatibility Reference" e "3. SerDe-Dependent Queries" (tabela "Key Mapping").

### 2.3 Queries Dependentes de SerDe

| Padrão HiveQL | Tratamento Databricks |
|---|---|
| `ROW FORMAT DELIMITED` em `CREATE TABLE` | Remover — só afeta DDL, não query (ver `hive-ddl-conversion.md` §2) |
| Query que depende de parsing específico de SerDe | Garantir que o dado já foi carregado corretamente no Delta — ler com o SerDe original, então escrever em Delta |
| `INPUTFORMAT`/`OUTPUTFORMAT` referenciados em query | Remover — não aplicável ao Delta |
| `STORED AS TEXTFILE` com delimitador custom | Usar `read_files` com opções de formato — conversão pontual durante a migração de dado |

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "3. SerDe-Dependent Queries".

---

## 3. Impala SQL → Databricks SQL

Impala é ANSI-compliant e próximo tanto de HiveQL quanto de Spark SQL — a maioria das queries Impala
transfere com mudanças mínimas.

| Feature Impala | Tratamento Databricks | Nota |
|---|---|---|
| `COMPUTE STATS` / `COMPUTE INCREMENTAL STATS` | `ANALYZE TABLE ... COMPUTE STATISTICS` | Sintaxe diferente, mesmo propósito |
| `INVALIDATE METADATA` / `REFRESH` | **Remover** | Unity Catalog gerencia metadata automaticamente |
| `STRAIGHT_JOIN` (hint) | **Remover** | Otimizador Catalyst decide a ordem de join |
| `/* +SHUFFLE */` (hint) | `/*+ SHUFFLE_HASH(t) */` | Sintaxe de hint diferente |
| **`KUDU` (referências de tabela)** | **Delta tables** | Kudu não tem equivalente no Databricks — redesenhar como tabela Delta |
| Funções específicas do Impala (`fnv_hash`, `now()`) | `hash()`, `current_timestamp()` | Pequenas diferenças de nome de função |
| **`UPSERT INTO` (Kudu)** | **`MERGE INTO`** | `MERGE` do Delta oferece semântica mais rica |

```sql
-- Impala (Kudu) → Databricks (Delta): UPSERT vira MERGE
MERGE INTO target_table AS tgt
USING source_data AS src
ON tgt.id = src.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

> Impala foi desenhado para SQL interativo sobre dado Hadoop, papel similar ao SQL Warehouse do
> Databricks. Concentrar esforço de conversão nas operações específicas de Kudu e nos comandos de
> metadata do Impala — o resto da sintaxe SQL é altamente compatível.

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "7. Impala SQL Conversion".

---

## 4. Hive UDF → Databricks

UDFs Hive escritas em Java seguem um de dois caminhos de migração, dependendo de complexidade e
requisito de performance:

| Tipo de UDF Hive | Opções Databricks | Recomendação |
|---|---|---|
| `UDF` simples (row-level, retorno único) | Registrar JAR Java, ou reescrever como UDF SQL/Python | Reescrever como UDF SQL se a lógica for simples |
| `GenericUDF` (tipos complexos, args variáveis) | Registrar JAR Java, ou reescrever como UDF Python | Manter Java se for performance-crítico |
| `UDAF` (agregação) | Registrar JAR Java, ou usar agregações built-in | Substituir por função built-in quando possível |
| `UDTF` (table-generating, ex.: `EXPLODE`) | A maioria tem equivalente built-in | Usar `EXPLODE`, `POSEXPLODE`, `INLINE` built-in |

**Caminho 1 — Registrar o JAR existente** (manter código Java como está; melhor para UDFs complexas
ou performance-críticas onde reescrever não se justifica):

```sql
-- Upload do JAR para um Volume do Unity Catalog, depois registrar como função
CREATE FUNCTION my_catalog.my_schema.custom_hash
AS 'com.company.hive.udf.CustomHashUDF'
USING JAR '/Volumes/my_catalog/my_schema/jars/custom-udf-1.0.jar';

SELECT custom_hash(customer_id) AS hashed_id FROM bronze.customers;
```

**Caminho 2 — Reescrever como UDF SQL ou Python** — melhor para UDFs simples row-level, e nos casos
em que já existe uma função built-in equivalente no Databricks.

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "6. Hive UDF Conversion".

---

## 5. Pig Latin → PySpark/Spark SQL (redesign — Lakebridge NÃO cobre)

Apache Pig usa uma linguagem procedural de data flow (Pig Latin). **Sem equivalente direto** no
Databricks — scripts Pig devem ser reescritos como PySpark ou Spark SQL. Operações Pig mapeiam
naturalmente para operações de DataFrame.

| Pig Latin | Equivalente PySpark | Equivalente Spark SQL |
|---|---|---|
| `LOAD 'path' USING PigStorage(',')` | `spark.read.csv('path')` | `read_files('path', format => 'csv')` |
| `FILTER rel BY condition` | `df.filter(condition)` | `WHERE condition` |
| `FOREACH rel GENERATE expr` | `df.select(expr)` | `SELECT expr` |
| `GROUP rel BY key` | `df.groupBy('key')` | `GROUP BY key` |
| `JOIN a BY key, b BY key` | `a.join(b, 'key')` | `JOIN ... ON key` |
| `ORDER rel BY col` | `df.orderBy('col')` | `ORDER BY col` |
| `DISTINCT rel` | `df.distinct()` | `SELECT DISTINCT` |
| `LIMIT rel N` | `df.limit(N)` | `LIMIT N` |
| `STORE rel INTO 'path'` | `df.write.save('path')` | `INSERT INTO` ou `CREATE TABLE AS SELECT` |
| `FLATTEN(bag)` | `explode(col)` | `EXPLODE(col)` |
| `SPLIT rel INTO a IF cond, b IF cond` | Múltiplos `df.filter()` | Múltiplos `SELECT ... WHERE` |
| `COGROUP a BY key, b BY key` | `a.join(b, 'key', 'full_outer')` | `FULL OUTER JOIN` |

### Exemplo completo — Pipeline ETL

```
-- Pig Latin (origem)
raw_orders = LOAD '/data/orders' USING PigStorage('|')
    AS (order_id:int, customer_id:int, amount:double, order_date:chararray);
valid_orders = FILTER raw_orders BY amount > 0;
customers = LOAD '/data/customers' USING PigStorage('|')
    AS (customer_id:int, name:chararray, region:chararray);
joined = JOIN valid_orders BY customer_id, customers BY customer_id;
by_region = GROUP joined BY region;
region_totals = FOREACH by_region GENERATE
    group AS region,
    SUM(joined.amount) AS total_revenue,
    COUNT(joined.order_id) AS order_count;
ordered = ORDER region_totals BY total_revenue DESC;
STORE ordered INTO '/output/region_revenue' USING PigStorage(',');
```

```sql
-- Databricks SQL (destino) — o pipeline inteiro cabe em uma única query
SELECT
    c.region,
    SUM(o.amount) AS total_revenue,
    COUNT(o.order_id) AS order_count
FROM bronze.orders o
JOIN bronze.customers c ON o.customer_id = c.customer_id
WHERE o.amount > 0
GROUP BY c.region
ORDER BY total_revenue DESC;
```

```python
# PySpark (alternativa, mesmo pipeline)
from pyspark.sql.functions import sum, count, col

orders = spark.table("bronze.orders")
customers = spark.table("bronze.customers")

result = (orders
    .filter(col("amount") > 0)
    .join(customers, "customer_id")
    .groupBy("region")
    .agg(sum("amount").alias("total_revenue"), count("order_id").alias("order_count"))
    .orderBy(col("total_revenue").desc())
)
result.write.saveAsTable("silver.region_revenue")
```

> **Princípio de conversão:** Pig Latin é procedural — cada linha produz uma relação intermediária.
> Em Spark SQL, o pipeline inteiro frequentemente cabe em uma única query. Para lógica mais complexa,
> a API DataFrame do PySpark reproduz a abordagem passo-a-passo do Pig, com o benefício adicional de
> otimização via Catalyst.

> **🔴 Lakebridge NÃO transpila Pig Latin.** Confirmado tanto pelo curso (`0.3`, feature mapping,
> marcado 🔴 "rewrite required; no automated transpilation for Pig Latin") quanto pela descrição de
> escopo do produto (§ nomenclatura, topo deste arquivo) — é sempre reescrita manual completa.

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "4. Pig Latin Conversion";
`00 - Foundations/0.3 Lecture - Architecture and Feature Mapping.md`, tabela "Feature Mapping: Hadoop
to Databricks" (linha "Pig scripts").

---

## 6. MapReduce Java → PySpark (redesign — Lakebridge NÃO cobre)

Código MapReduce Java exige **reescrita completa**. O mapeamento conceitual é direto — funções map
viram transformações, funções reduce viram agregações — mas a estrutura do código muda inteiramente.

| Conceito MapReduce | Equivalente PySpark | Descrição |
|---|---|---|
| `Mapper.map()` | `df.select()`, `df.withColumn()`, `df.flatMap()` | Transformações row-level |
| `Reducer.reduce()` | `df.groupBy().agg()` | Agregações e sumarizações |
| `Combiner` | Automático via `agg()` | Agregação parcial pré-shuffle, o Spark faz sozinho |
| `Partitioner` | `df.repartition()` | Controla distribuição de dado |
| `InputFormat` | `spark.read.format(...)` | Leitura de fonte de dado |
| `OutputFormat` | `df.write.format(...)` | Escrita de sink de dado |
| `Configuration` | `SparkConf` / `spark.conf` | Configuração de runtime |
| `Counter` | Spark Accumulator | Contadores distribuídos |
| `Writable` customizado | Tipos Python/Scala padrão | Serialização gerenciada pelo Spark |

### Exemplo — Word Count

```java
// MapReduce Java (origem)
public class WordCountMapper extends Mapper<LongWritable, Text, Text, IntWritable> {
    public void map(LongWritable key, Text value, Context context) throws IOException, InterruptedException {
        StringTokenizer itr = new StringTokenizer(value.toString());
        while (itr.hasMoreTokens()) {
            context.write(new Text(itr.nextToken()), new IntWritable(1));
        }
    }
}
public class WordCountReducer extends Reducer<Text, IntWritable, Text, IntWritable> {
    public void reduce(Text key, Iterable<IntWritable> values, Context context) throws IOException, InterruptedException {
        int sum = 0;
        for (IntWritable val : values) sum += val.get();
        context.write(key, new IntWritable(sum));
    }
}
```

```python
# PySpark (destino)
from pyspark.sql.functions import explode, split, count

words = (spark.read.text("/data/input")
    .select(explode(split("value", "\\s+")).alias("word"))
    .groupBy("word")
    .agg(count("*").alias("word_count"))
    .orderBy("word_count", ascending=False)
)
words.write.saveAsTable("silver.word_counts")
```

```sql
-- Ou em Spark SQL puro
SELECT word, COUNT(*) AS word_count
FROM (SELECT EXPLODE(SPLIT(value, '\\s+')) AS word FROM read_files('/data/input', format => 'text'))
GROUP BY word
ORDER BY word_count DESC;
```

### Exemplo — Secondary Sort (chave composta)

Em MapReduce, secondary sort exige `WritableComparable`/`Partitioner` customizados. Em PySpark, é
uma window function simples:

```python
from pyspark.sql.functions import row_number, col
from pyspark.sql.window import Window

window = Window.partitionBy("category").orderBy(col("revenue").desc())
ranked = (spark.table("bronze.products")
    .withColumn("rank", row_number().over(window))
    .filter(col("rank") <= 3)  # top 3 por categoria
)
```

```sql
-- Equivalente Spark SQL
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY category ORDER BY revenue DESC) AS rank
    FROM bronze.products
) WHERE rank <= 3;
```

> **🔴 Lakebridge NÃO transpila MapReduce Java.** Mesmo tratamento do Pig Latin (§5) — reescrita
> manual completa; a maioria dos padrões vira operação simples de DataFrame.

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "5. MapReduce Java Conversion".

---

## 7. Hive Scripts, Shell Scripts e Lógica Procedural (HPL/SQL)

Hive tem suporte procedural limitado (HPL/SQL, adicionado na Hive 3.x). Na maioria dos ambientes
Hadoop, a lógica procedural que em um RDBMS estaria em stored procedures vive em:

- Shell scripts (bash) chamados de Oozie shell actions
- Scripts Python chamados de Oozie shell actions
- Scripts Hive (`.hql`) com múltiplos statements
- Procedures HPL/SQL (só Hive 3.x)
- Scripts `spark-submit` com lógica embutida

### Exemplo — Script Hive com Lógica Procedural

```sql
-- Hive: daily_etl.hql (chamado via Oozie ou cron: hive -f daily_etl.hql)
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET mapreduce.job.reduces=10;

-- Passo 1: staging da landing zone
INSERT OVERWRITE TABLE staging.orders
PARTITION (load_date)
SELECT *, '${hiveconf:RUN_DATE}' AS load_date
FROM raw.orders_landing
WHERE order_date = '${hiveconf:RUN_DATE}';

-- Passo 2: merge no destino
INSERT OVERWRITE TABLE silver.orders
PARTITION (order_year, order_month)
SELECT o.*, YEAR(o.order_date) AS order_year, MONTH(o.order_date) AS order_month
FROM staging.orders o;
```

```sql
-- Databricks SQL — mesmo ETL, sem SET e sem INSERT OVERWRITE dinâmico
-- Delta lida com partição/CLUSTER BY automaticamente; MERGE garante idempotência
MERGE INTO silver.orders AS target
USING (
    SELECT *, current_date() AS load_date
    FROM bronze.orders_landing
    WHERE order_date = :run_date
) AS source
ON target.order_id = source.order_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

**Critério de decisão** (mesmo framework de `tsql-conversion-catalog.md` §4, aplicado aqui a HPL/SQL
e scripts `.hql` multi-statement): corpo primariamente `SELECT`/DML com controle de fluxo simples →
**Databricks SQL Scripting** (DBR 16+: `DECLARE`/`IF`/`WHILE`/`FOR`/`EXCEPTION`); lógica com chamadas
a serviços externos, shell/Python scripts orquestrados via Oozie, ou dynamic SQL → **notebook Python**
empacotado como task de **Lakeflow Jobs**.

Variáveis Hive (`${hiveconf:VAR}`) → parâmetros de widget do notebook, ou sintaxe `:variable` em SQL
Scripting/Databricks SQL.

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seções "8. Hive Stored Procedures and
Shell Scripts" e callout "Where Hadoop Procedural Logic Lives".

---

## 8. Configuração Hive (`SET`) — Remover

Scripts Hive usam `SET` extensivamente para configurar comportamento de execução. A maioria **não é
necessária** no Databricks — Spark/Photon otimizam automaticamente.

| `SET` Hive | Por que não é necessário no Databricks |
|---|---|
| `SET hive.exec.dynamic.partition=true` | Particionamento dinâmico está sempre habilitado |
| `SET hive.exec.dynamic.partition.mode=nonstrict` | Modo non-strict é o default |
| `SET mapreduce.job.reduces=N` | Spark determina paralelismo automaticamente |
| `SET hive.execution.engine=tez` | Spark/Photon é o execution engine |
| `SET hive.vectorized.execution.enabled=true` | Photon já fornece execução vetorizada |
| `SET hive.auto.convert.join=true` | Broadcast joins do Spark são automáticos |
| `SET hive.mapjoin.smalltable.filesize=N` | `spark.sql.autoBroadcastJoinThreshold` substitui isso |
| `SET hive.optimize.sort.dynamic.partition=true` | Spark otimiza partição automaticamente |
| `SET hive.merge.mapfiles=true` | Rodar `OPTIMIZE` após escritas, em vez disso |

```sql
-- Nos raros casos em que configuração Spark é de fato necessária:
SET spark.sql.shuffle.partitions = 200;
SET spark.sql.adaptive.enabled = true;              -- já habilitado por default
SET spark.databricks.photon.enabled = true;         -- já habilitado por default em clusters Photon
```

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "9. Hive Configuration and SET
Variables".

---

## 9. Referência de Compatibilidade de Funções HiveQL

A maioria das funções HiveQL está disponível em Databricks SQL com mesmo nome/comportamento. As que
diferem:

| Função HiveQL | Equivalente Databricks SQL | Nota |
|---|---|---|
| `unix_timestamp()` (sem args) | `unix_timestamp()` | Igual — epoch atual |
| `from_unixtime(epoch, format)` | `from_unixtime(epoch, format)` | Sintaxe igual |
| `to_date(string)` | `to_date(string)` | Sintaxe igual |
| `date_add(date, days)` | `date_add(date, days)` | Sintaxe igual |
| `datediff(end, start)` | `datediff(end, start)` | Sintaxe igual |
| `NVL(expr, default)` | `NVL(expr, default)` ou `COALESCE` | Ambos suportados |
| `IF(condition, true, false)` | `IF(condition, true, false)` | Sintaxe igual |
| `COALESCE(a, b, c)` | `COALESCE(a, b, c)` | Sintaxe igual |
| `CONCAT_WS(sep, a, b)` | `CONCAT_WS(sep, a, b)` | Sintaxe igual |
| `COLLECT_SET()` / `COLLECT_LIST()` | Igual | Sintaxe igual |
| `SORT_ARRAY()` | Igual | Sintaxe igual |
| `SIZE(array)` | Igual | Sintaxe igual |
| `XPATH()` / `XPATH_STRING()` | Igual | Sintaxe igual |
| `GET_JSON_OBJECT(json, path)` | Igual, ou operador `:` | Databricks também suporta JSON path via `:` |
| `RLIKE` (regex) | Igual | Sintaxe igual |
| **`REFLECT()`** (reflection Java) | **Não suportado** | Reescrever como UDF Python |
| **`JAVA_METHOD()`** | **Não suportado** | Reescrever como UDF Python, ou registrar JAR |

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "11. HiveQL Function
Compatibility Reference".

---

## 10. HBase → Delta Lake (redesign — gap documental do curso)

| Feature Hadoop | Equivalente Databricks | Complexidade |
|---|---|---|
| HBase (NoSQL, wide-column store) | Delta Lake | 🔴 Modelo de dado fundamentalmente diferente; padrões de leitura/escrita aleatória exigem redesign |

**⚠️ Lacuna documental confirmada:** o curso **não desenvolve um padrão de conversão HBase → Delta**.
A única menção é uma linha na tabela de artefatos legados de exemplo (`0.3`, "Sample Legacy
Artifacts"): `hbase-sample-ddl.txt` → "Delta Lake (with schema redesign)" — sem exemplo de DDL, sem
estratégia de row-key, sem tratamento de wide-column/column-family. **Não inventar aqui** um padrão de
conversão que o curso não fornece. Tratamento recomendado: escalar para desenho de arquitetura
dedicado (schema redesign caso a caso, considerando padrão de acesso real — scans vs point lookups —
antes de definir a modelagem Delta), não como transpilação mecânica.

Cite: `00 - Foundations/0.3 Lecture - Architecture and Feature Mapping.md`, tabela "Feature Mapping:
Hadoop to Databricks" (linha "HBase (NoSQL)") e tabela "Sample Legacy Artifacts".

---

## 11. Automação com Lakebridge

Lakebridge (chamado "Remorph" no texto do curso — ver nota de nomenclatura no topo) automatiza
transpilação SQL a partir de múltiplos dialetos de origem.

| Capability | O que o Lakebridge Faz |
|---|---|
| HiveQL → Databricks SQL | Transpila `SELECT`, `INSERT`, `MERGE`, views e DDL |
| Mapeamento de função | Mapeia funções Hive-específicas para equivalentes Databricks |
| Conversão de tipo | Converte tipos Hive para tipos Databricks em DDL (ver `hive-ddl-conversion.md` §1) |
| Remoção de SerDe | Retira `ROW FORMAT`, `STORED AS`, `SERDE` do DDL |
| Relatório | Gera relatório de conversão mostrando o que mudou e o que precisa revisão manual |

```bash
# Instalar
pip install databricks-labs-remorph   # nome de pacote histórico — produto atual é Lakebridge

# Transpilar scripts HiveQL para Databricks SQL
remorph transpile \
  --source hive \
  --input-sql /path/to/hive_scripts/ \
  --output-folder /path/to/databricks_sql/ \
  --catalog-name my_catalog \
  --schema-name my_schema
```

> Fontes de origem suportadas pelo transpilador segundo o curso: **Hive** (DDL+DML completo),
> Presto/Trino, Snowflake, T-SQL, Teradata, Netezza. **Confirmado (fato dado, não re-verificado
> arquivo a arquivo neste catálogo):** Lakebridge cobre Hive/HiveQL e Impala SQL via tecnologia
> BladeBridge — **não cobre Pig Latin nem MapReduce Java** (§5, §6), que exigem sempre reescrita
> manual completa.

**Sempre revisar a saída do Lakebridge:**
- Funções marcadas como "unsupported" que precisam de conversão manual
- Cláusulas `TRANSFORM`/`MAP`/`REDUCE` flagadas para reescrita manual
- Referências a UDF customizada que precisam de registro ou reescrita
- Statements `SET` removidos (confirmar que eram de fato desnecessários)
- **Sempre validar contra dado de teste** — transpilação automatizada converte sintaxe, não valida
  lógica de negócio; rodar as queries transpiladas e comparar resultado com a saída original do Hive
  antes de promover a produção

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seções "12. Automated Conversion with
Remorph" e callout "Always validate transpiled output".

---

## 12. Classificação de Esforço (referência rápida)

| Tipo de Código | Esforço de Migração | Abordagem |
|---|---|---|
| Queries HiveQL | Baixo — a maioria roda como está | Lakebridge para conversão automatizada de edge cases |
| Impala SQL | Baixo | Pequenas mudanças de nome de função e remoção de hints |
| Hive Java UDFs | Baixo a Médio | Registrar JAR no Databricks ou reescrever como UDF Python/SQL |
| Shell/Python scripts (orquestração) | Médio | Converter para notebook tasks em Lakeflow Jobs |
| Hive `SET` variables | Baixo | Remover a maioria; substituir poucas por configuração Spark |
| HPL/SQL procedures | Médio | Reescrever como Databricks SQL Scripting (§7) |
| **Pig Latin** | **Alto — reescrita completa** | Converter para Spark SQL ou PySpark DataFrame (§5) |
| **MapReduce Java** | **Alto — reescrita completa** | Converter para PySpark; maioria vira operação simples de DataFrame (§6) |
| **HBase workloads** | **Alto — redesign arquitetural** | Sem padrão mecânico; modelagem Delta caso a caso (§10) |

Cite: `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`, seção "Summary".

---

## 13. Lacunas do Curso (marcado como incerto — verificar doc oficial antes de codificar)

O corpus do curso (`3.1`, `3.4`, `0.3`, `0.4`) **não cobre** os itens abaixo com profundidade
suficiente para virar regra normativa. Registrado aqui como lacuna explícita, não como fato
verificado — qualquer agente que precise desses construtos deve checar a documentação oficial do
Databricks antes de gerar código.

| Item | O que o curso diz (se algo) | Lacuna |
|---|---|---|
| **`MSCK REPAIR TABLE`** | Nenhuma menção em todo o corpus lido (`3.1`, `3.4`, `0.3`, `0.4`) | Hive usa `MSCK REPAIR TABLE` para sincronizar partições descobertas no HDFS com o Metastore após novos diretórios serem adicionados fora do Hive. Delta Lake não descobre partição via listagem de diretório (mantém o próprio transaction log), então o conceito não tem aplicação direta em tabela Delta gerenciada — mas **isso não está confirmado pelo curso**, é inferência de arquitetura. Verificar a doc oficial do Spark SQL (`ALTER TABLE ... RECOVER PARTITIONS`, aplicável a tabelas não-Delta) antes de assumir qualquer equivalência |
| **Particionamento dinâmico (semântica)** | O curso só remove os `SET` que habilitam modo dinâmico no Hive (§8) — não explica a semântica equivalente no lado Spark/Delta | Hive tem `hive.exec.dynamic.partition.mode=strict\|nonstrict`; Spark tem `spark.sql.sources.partitionOverwriteMode=static\|dynamic` para `INSERT OVERWRITE` em tabelas particionadas — **comportamento e nomes de modo não são idênticos**. Não assumir equivalência 1:1 sem testar. Para tabelas com Liquid Clustering (`CLUSTER BY`, o padrão recomendado nesta KB), a questão nem se aplica — usar `MERGE`/`INSERT` normal (ver exemplo em §7) |
| **`DISTRIBUTE BY` / `SORT BY`** | Mencionado só como uma linha em `0.2`/`0.3`: "`SORT BY`/`DISTRIBUTE BY` -> repartitioning" (ou, em `0.2`, "-> standard `ORDER BY`/repartitioning") — sem exemplo de sintaxe | HiveQL `DISTRIBUTE BY col` distribui linhas entre reducers por coluna (sem ordenar globalmente); `SORT BY col` ordena dentro de cada reducer (não globalmente, ao contrário de `ORDER BY`); `CLUSTER BY col` em HiveQL é atalho para `DISTRIBUTE BY col SORT BY col`. Tradução geralmente proposta: `DISTRIBUTE BY` → `df.repartition(col)`; `SORT BY` → `df.sortWithinPartitions(col)`; **mas isso é conhecimento geral de Spark, não citado pelo curso** — validar contra a documentação oficial antes de codificar como regra |

> **⚠️ Colisão de nome — não confundir:** HiveQL `CLUSTER BY` (DML, atalho de
> `DISTRIBUTE BY x SORT BY x`, controla distribuição entre reducers em tempo de query) **não é o
> mesmo construto** que o `CLUSTER BY` do Delta Lake documentado em
> `kb/hadoop-migration/concepts/hive-ddl-conversion.md` §3 (DDL, propriedade física da tabela —
> Liquid Clustering). Mesma palavra-chave, dois construtos completamente diferentes, em dois
> contextos (query HiveQL vs DDL Delta). Nenhum dos dois arquivos do curso alerta para essa colisão
> explicitamente — é uma leitura cruzada entre `3.1`/`3.4` e o vocabulário geral de HiveQL. Sinalizar
> essa diferença ao usuário sempre que o termo `CLUSTER BY` aparecer em uma conversão para evitar
> confusão sobre qual dos dois construtos está em jogo.

---

## Checklist de Conversão SQL/Código

- [ ] Queries HiveQL testadas em Databricks SQL — a maioria roda sem alteração (§1)
- [ ] `TRANSFORM`/`MAP`/`REDUCE` reescritos como UDF ou PySpark (§2.1)
- [ ] `REFLECT()`/`JAVA_METHOD()` reescritos como UDF (§2.2)
- [ ] Colunas virtuais (`INPUT__FILE__NAME` etc.) trocadas por `_metadata.*` (§2.2)
- [ ] Sintaxe/hints/funções Impala atualizados; `Kudu` → `Delta` com `UPSERT`→`MERGE` (§3)
- [ ] UDFs Java Hive classificadas: registrar JAR vs reescrever (§4)
- [ ] **Pig Latin totalmente reescrito** como Spark SQL ou PySpark — sem transpilação automática (§5)
- [ ] **MapReduce Java totalmente reescrito** como PySpark — sem transpilação automática (§6)
- [ ] Scripts `.hql`/HPL/SQL/shell classificados: SQL Scripting vs notebook Python + Lakeflow Jobs (§7)
- [ ] `SET` do Hive removidos ou substituídos por configuração Spark equivalente (§8)
- [ ] Variáveis Hive (`${hiveconf:VAR}`) substituídas por parâmetros de widget/`:variable` (§7)
- [ ] Workloads **HBase** escalados para desenho de arquitetura — sem conversão mecânica (§10)
- [ ] Lakebridge usado para transpilação em massa de HiveQL/Impala — nunca para Pig/MapReduce (§11)
- [ ] Toda query transpilada validada contra dado de teste antes de produção (§11)
- [ ] Itens de §13 (MSCK, partição dinâmica, DISTRIBUTE/SORT BY) verificados contra doc oficial antes
      de virar código gerado — não tratar como regra do curso

---

## Referências

- Curso "Hadoop Migration" — `03 - Execute/3.4 Lecture - SQL and Code Conversion.md`
- Curso "Hadoop Migration" — `00 - Foundations/0.3 Lecture - Architecture and Feature Mapping.md`
- Curso "Hadoop Migration" — `00 - Foundations/0.2 Lecture - Migration Maturity Model.md` (menção a
  `SORT BY`/`DISTRIBUTE BY`, ver §13)
- Ver também: `kb/hadoop-migration/concepts/hive-ddl-conversion.md` (DDL/tipos/particionamento —
  inclusive a colisão de nome `CLUSTER BY` descrita em §13 deste arquivo)
- Ver também: `kb/sql-patterns/concepts/tsql-conversion-catalog.md` (mesmo padrão de catálogo, origem
  SQL Server; §4 SQL Scripting e §2.2 `RELY` reaproveitáveis)
- Ver também: `kb/sql-patterns/concepts/dialect-concepts.md` (mapeamento genérico Spark SQL/T-SQL/KQL)
- Ver também: `audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md` (achados H3, H7, H11)
- [Databricks SQL Language Reference](https://docs.databricks.com/en/sql/language-manual/index.html)
- [Spark SQL Built-in Functions](https://docs.databricks.com/en/sql/language-manual/sql-ref-functions-builtin.html)
- [PySpark DataFrame API](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/index.html)
- [Apache Hive Language Manual](https://cwiki.apache.org/confluence/display/Hive/LanguageManual)
- [Apache Pig Latin Reference](https://pig.apache.org/docs/latest/basic.html)
- [Introducing Lakebridge (Databricks Blog, jun/2025)](https://www.databricks.com/blog/introducing-lakebridge-free-open-data-migration-databricks-sql)
- [Lakebridge (GitHub)](https://github.com/databrickslabs/lakebridge)
