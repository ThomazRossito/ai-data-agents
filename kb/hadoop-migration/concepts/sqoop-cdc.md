# Sqoop e CDC Hadoop → Ingestão Incremental Databricks

> Escopo: conversão de ingestão incremental (Sqoop) e Change Data Capture Hadoop para os mecanismos
> incrementais do Databricks (Auto Loader, `MERGE`, `AUTO CDC`, Change Data Feed). Fonte normativa:
> curso oficial Databricks *"Hadoop Migration"*, `03 - Execute/3.3 Lecture - Incremental Sync and
> CDC` (mapeamento e `MERGE`) + `03 - Execute/3.2 Lecture - Data Migration and Ingestion` (qualidade
> de dado herdada do Sqoop). Fonte de verdade operacional de um futuro agente `hadoop-to-databricks`
> (ver auditoria `audits/2026-08-02-curso-hadoop-migration-vs-ai-data-agents.md`, item H5).
>
> **Fato verificado (web, ago/2026):** Hadoop **não tem um mecanismo de CDC nativo único** —
> diferente do SQL Server, que tem CDC/Change Tracking nativo (`sp_cdc_enable_table`, etc. — ver
> resíduo de contaminação abaixo). A sintaxe completa de `AUTO CDC` (SQL + Python, SCD Type 1/2) **já
> está documentada** em `kb/spark-patterns/patterns/lakeflow-patterns.md` — este arquivo **não
> duplica** essa sintaxe; cobre o que é específico de Hadoop: o mapa de origem→mecanismo, a sintaxe
> Sqoop, o `MERGE` manual de SCD1, e os problemas de qualidade herdados do Sqoop.
>
> **Aviso de proveniência:** nenhum exemplo deste arquivo usa `sp_cdc_*`, `msdb`, `.dtsx` ou
> connection strings SQL Server — só os trechos Hadoop-válidos de 3.2/3.3 (Sqoop, Kafka Connect
> a partir de RDBMS upstream, Hive ACID, `AUTO CDC`).

**Domínio:** Sqoop incremental, CDC Hadoop sem mecanismo único, MERGE SCD1, AUTO CDC (ponteiro), qualidade de dado Sqoop

---

## 1. Por que Hadoop não tem um CDC único

Hadoop não tem um mecanismo de CDC nativo único como algumas plataformas RDBMS. Em vez disso, o sync
incremental é obtido por padrões diferentes dependendo da origem de dado e da arquitetura do
pipeline: Sqoop incremental, Kafka Connect/Debezium a partir de um RDBMS upstream, transaction logs
do Hive ACID, ou watermarks de timestamp (fonte: 3.3, §1 "Incremental Sync Concept Mapping"). **A
primeira pergunta ao converter CDC Hadoop não é "qual sintaxe usar" — é "qual é o mecanismo de
detecção de mudança real na origem"**, porque cada um mapeia para um mecanismo Databricks diferente.

---

## 2. Mapa de conversão — origem Hadoop → mecanismo Databricks

| Hadoop | Databricks | Propósito |
|---|---|---|
| Sqoop `--incremental append` | Auto Loader (chegada de arquivo) | Append de registros novos com base em chave crescente |
| Sqoop `--incremental lastmodified` | `MERGE` com watermark de timestamp | Upsert de registros modificados desde o último sync |
| Kafka Connect CDC (Debezium) | Auto Loader + `AUTO CDC` | Stream de mudanças do RDBMS via Kafka até Delta |
| Hive ACID transaction logs | Change Data Feed / `MERGE` | Rastrear mudanças linha-a-linha em tabelas transacionais |
| Coluna timestamp/watermark | `MERGE` com condição `modified_date > last_sync` | Detecção incremental simples |
| Oozie coordinator (agendado) | Lakeflow Jobs (agendado) | Orquestrar as execuções de sync incremental — ver `concepts/oozie-orchestration.md` |
| N/A (sem equivalente Hadoop) | `AUTO CDC` | CDC declarativo com tratamento de eventos fora de ordem |

(fonte: 3.3, §1 "Hadoop to Databricks CDC Mapping")

---

## 3. Sqoop incremental — sintaxe e conversão

```bash
# Sqoop incremental append - adiciona linhas novas com base em ID crescente
sqoop import \
  --connect jdbc:mysql://source-db:3306/production \
  --table orders \
  --target-dir /data/staging/orders \
  --incremental append \
  --check-column order_id \
  --last-value 50000

# Sqoop incremental lastmodified - upsert com base em timestamp
sqoop import \
  --connect jdbc:mysql://source-db:3306/production \
  --table customers \
  --target-dir /data/staging/customers \
  --incremental lastmodified \
  --check-column modified_date \
  --last-value "2024-01-01 00:00:00" \
  --merge-key customer_id
```

(fonte: 3.3, §2 "Pattern A: Sqoop Incremental Import")

| Sqoop | Equivalente Databricks |
|---|---|
| `--incremental append` + `--check-column` | Auto Loader (arquivo novo = registro novo) |
| `--incremental lastmodified` + `--check-column` | `MERGE` com condição de watermark (`modified_date > last_sync`) |
| `--merge-key` | `MERGE INTO ... ON <key>` |
| `--last-value` (checkpoint) | Checkpoint do Auto Loader, ou tabela de controle de watermark |
| Hive `INSERT OVERWRITE` de partição (padrão de reload usado com Sqoop) | `MERGE` para updates granulares linha-a-linha (menos I/O que reescrever a partição inteira) |

(fonte: 3.3, §3 "Key Mapping")

---

## 4. MERGE — SCD Type 1 (upsert simples)

Para SCD Type 1 (sobrescreve o registro, sem histórico) — o caso mais comum em dimensões que não
exigem auditoria. O dado incremental chega tipicamente via Auto Loader a partir de tópicos Kafka ou
de arquivos incrementais em cloud storage, com uma coluna `_operation`
(`INSERT`/`UPDATE`/`DELETE`):

```sql
MERGE INTO silver.customer_dim AS target
USING bronze.customer_incremental AS source
ON target.customer_id = source.customer_id

WHEN MATCHED AND source._operation = 'DELETE' THEN
    DELETE

WHEN MATCHED THEN UPDATE SET
    target.first_name = source.first_name,
    target.last_name  = source.last_name,
    target.city       = source.city,
    target.email      = source.email,
    target.updated_at = current_timestamp()

WHEN NOT MATCHED AND source._operation != 'DELETE' THEN INSERT (
    customer_id, first_name, last_name, city, email, created_at, updated_at
) VALUES (
    source.customer_id, source.first_name, source.last_name,
    source.city, source.email, current_timestamp(), current_timestamp()
);
```

(fonte: 3.3, §3 "Databricks: Delta MERGE (SCD Type 1)")

**Para SCD Type 2 (histórico) ou pipelines de CDC de produção, não escreva o `MERGE` de 2 passos
manual (`UPDATE` de expiração + `INSERT` de nova versão) — use `AUTO CDC` com `STORED AS SCD TYPE 2`**,
documentado em `kb/spark-patterns/patterns/lakeflow-patterns.md`, reforçado pela regra **R4** de
`kb/spark-patterns/concepts/sdp-rules.md` ("Para SCD2, sempre AUTO CDC — nunca LAG/LEAD/ROW_NUMBER
manual"). O curso mostra o 2-passo manual (`UPDATE ... SET valid_to/is_current` + `INSERT`) como o
que o Hive ACID fazia manualmente (fonte: 3.3, §4) — é o padrão **legado** que `AUTO CDC` substitui,
não o padrão-alvo Databricks.

---

## 5. Tratamento de deletes

| Abordagem | Tratamento do delete | Caso de uso |
|---|---|---|
| `MERGE ... WHEN MATCHED ... THEN DELETE` | Hard delete no destino | SCD Type 1, sem trilha de auditoria |
| `AUTO CDC` com `APPLY AS DELETE WHEN` | Configurável por tipo de SCD | Pipelines Lakeflow SDP |
| SCD Type 1 + `apply_as_deletes` | Hard delete | Dimensões sem necessidade de histórico |
| SCD Type 2 + `apply_as_deletes` | Soft delete (end-dated) | Trilha de auditoria completa exigida |

(fonte: 3.3, §7 "Handling Deletes")

---

## 6. Sequenciamento (`SEQUENCE BY`)

`AUTO CDC` trata eventos fora de ordem automaticamente via `SEQUENCE BY` — mas a coluna precisa ser um
tipo ordenável, monotonicamente crescente:

- Valores `NULL` na coluna de sequência **não são suportados**.
- Deve existir **uma única atualização distinta por chave em cada valor de sequência**.

(fonte: 3.3, §7, aviso de sequenciamento) — sintaxe completa de `SEQUENCE BY`/`KEYS`/`STORED AS SCD
TYPE` em `kb/spark-patterns/patterns/lakeflow-patterns.md`.

---

## 7. Problemas herdados do Sqoop (qualidade de dado)

Tabelas Hive originalmente importadas via Sqoop a partir de um RDBMS costumam carregar problemas de
qualidade que precisam ser resolvidos **durante** a migração/ingestão incremental:

| Problema | Descrição | Resolução |
|---|---|---|
| **Tipos codificados como string** | Sqoop importa `DATE`, `TIMESTAMP`, `BOOLEAN` como `STRING` | `CAST` para o tipo correto durante a ingestão Delta |
| **Representação de NULL** | Sqoop usa a string literal `"null"` ou `"\N"` para NULLs | Substituir por `NULL` real durante a ingestão (`NULLIF`/`CASE`) |
| **Conflito de delimitador** | Imports Sqoop baseados em CSV podem ter delimitadores não escapados em campos de texto | Usar a versão ORC/Parquet se existir, ou limpar durante a ingestão |
| **Artefatos de import incremental** | Múltiplos batches de import podem ter registros sobrepostos ou duplicados | Deduplicar por chave de linha durante o `MERGE` Delta |

(fonte: 3.2, "Handling Sqoop-Imported Data") — **sempre preferir a versão ORC/Parquet** ao texto do
mesmo import Sqoop quando ambas existirem: preservam tipos com mais precisão e comprimem melhor;
imports baseados em texto exigem mais limpeza na ingestão (3.2, tip box). Esta tabela cobre o
problema no **nível de valor** (dado já carregado); para o mesmo problema no **nível de DDL/tipo**
(coluna Hive `STRING` que deveria ser `DATE`/`BOOLEAN`/`DECIMAL` desde a origem RDBMS), ver
`concepts/hive-ddl-conversion.md` §1.3 ("Tipos de Origem RDBMS via Sqoop").

> **Considere substituir o Sqoop inteiro por Lakeflow Connect.** Se o cluster Hadoop atuava como
> intermediário para dados de um RDBMS (via Sqoop), avalie substituir todo o pipeline Sqoop por
> **Lakeflow Connect**, que ingere diretamente do RDBMS para tabelas Delta, sem passar pelo Hadoop —
> elimina a camada Sqoop e simplifica a arquitetura (fonte: 3.2, info box). JDBC direto (com secret
> scope) é fallback apenas quando Lakeflow Connect não cobrir a origem.

---

## 8. Monitoramento de CDC

| Métrica | Descrição | Exemplo de SLA |
|---|---|---|
| **Event Lag** | Tempo entre a mudança na origem e a atualização no destino | < 5 minutos |
| **Throughput** | Registros processados por segundo | > 10.000 rps |
| **Error Rate** | Operações de merge com falha | < 0.01% |
| **Sequence Gaps** | Eventos ausentes ou fora de ordem | 0 |
| **Checkpoint Lag** | Offset atrás do disponível mais recente | < 1.000 registros |

(fonte: 3.3, §8 "Monitoring CDC Events and Logs")

---

## 9. Reconciliação do delta de CDC

Reaproveitar `kb/migration/concepts/reconciliation.md` (7 parity checks + regra das 2 fases) para o
delta capturado por qualquer um dos mecanismos acima. **Atenção:** o Lakebridge Reconciler documenta
`data_source` para Snowflake/Oracle/SQL Server/Synapse — **Hive não está na lista** documentada nem
verificada oficialmente até o momento desta KB. Para origem Hadoop/Hive, reconciliar via SQL agregado
manual (`COUNT`/`SUM`/`MIN`/`MAX`, hash MD5, `EXCEPT`) — mesma técnica de `reconciliation.md` §6.2 —
em vez de assumir suporte do Lakebridge Reconciler para Hive.

---

## Anti-Padrões Locais (HD-C — CDC)

| Código | Anti-padrão | Correção |
|---|---|---|
| HD-C01 | Manter datas/booleanos como `STRING` (herdado do Sqoop) rio abaixo na Silver/Gold | `CAST` para o tipo correto na ingestão Bronze→Silver — §7 |
| HD-C02 | Tratar a string literal `"null"`/`"\N"` como valor de negócio válido | Normalizar para `NULL` real na ingestão — §7 |
| HD-C03 | Escrever SCD Type 2 manual com `LAG`/`ROW_NUMBER` no Databricks | `AUTO CDC` com `STORED AS SCD TYPE 2` (regra R4, `sdp-rules.md`) — §4 |
| HD-C04 | Usar `_batch_id`/run id como coluna de `SEQUENCE BY` | `SEQUENCE BY` exige coluna temporal monotônica (`updated_at`, `_commit_timestamp`) — §6 |
| HD-C05 | Assumir que existe UM mecanismo de CDC Hadoop a mapear | Identificar a origem real por tabela (Sqoop/Kafka/Hive ACID/watermark) antes de escolher o mecanismo-alvo — §1-2 |
| HD-C06 | Configurar Lakebridge Reconciler com `data_source` para Hive | Não documentado/suportado — usar SQL agregado manual — §9 |

---

## Referências

- Curso Databricks — *Hadoop Migration* — `03 - Execute/3.3 Lecture - Incremental Sync and CDC`
- Curso Databricks — *Hadoop Migration* — `03 - Execute/3.2 Lecture - Data Migration and Ingestion` ("Handling Sqoop-Imported Data")
- `kb/spark-patterns/patterns/lakeflow-patterns.md` (sintaxe completa `AUTO CDC` SQL + Python, SCD Type 1/2)
- `kb/spark-patterns/concepts/sdp-rules.md` (regra R4 — AUTO CDC obrigatório para SCD2)
- `kb/migration/concepts/reconciliation.md` (7 parity checks, 2 fases, Lakebridge Reconciler)
- `concepts/hive-ddl-conversion.md` · `concepts/hdfs-ingestion.md` · `concepts/oozie-orchestration.md` (irmãos deste domínio)
- [Delta `MERGE INTO`](https://docs.databricks.com/en/delta/merge.html)
- [`AUTO CDC` for Pipelines](https://docs.databricks.com/en/delta-live-tables/cdc.html)
- [Change Data Feed](https://docs.databricks.com/en/delta/delta-change-data-feed.html)
- [Apache Sqoop Documentation](https://sqoop.apache.org/docs/1.4.7/SqoopUserGuide.html)
- [Debezium CDC Connector](https://debezium.io/documentation/)
