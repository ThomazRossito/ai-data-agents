# Lakehouse Fabric — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** OneLake, Delta Lake, Medallion, V-Order, enable_schemas

---

## OneLake: Armazenamento Unificado

OneLake é o armazenamento cloud nativo do Fabric, acessível via ABFSS:

```
abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse.Lakehouse/
```

- Um OneLake por tenant, multi-workspaces
- Suporta shortcuts para zero-copy access
- Integração nativa com Spark, SQL, Power BI

---

## Formato Delta Lake (Padrão)

| Aspecto | Recomendação | Detalhes |
|---------|--------------|----------|
| **Compressão** | Snappy (padrão) | Balança taxa/velocidade |
| **Write Mode** | `overwrite` com `mergeSchema` | Permite evolução de schema |
| **Particionamento** | Por `year`, `month`, ou `date` (Gold) | Evite excesso de partições (<1000) |
| **Formato** | Parquet (.parquet) | Compressão colunar nativa |

**Gotcha:** Não crie partições dinâmicas em Bronze — use apenas em Silver/Gold após transformação.

---

## Organização Medallion

| Camada | Dados | Retenção | Transformações |
|--------|-------|----------|----------------|
| **Bronze** | Cópia 1:1 dos dados brutos | 30-90 dias | Nenhuma |
| **Silver** | Limpos, deduplicados, PII aplicado | 1-2 anos | Limpeza, joins iniciais |
| **Gold** | Otimizados para consumo (BI, ML) | 3+ anos (compliance) | Agregações, V-Order |

---

## V-Order: Leitura Otimizada

V-Order é **obrigatório para Direct Lake no Power BI**:

| Propriedade | Impacto |
|-------------|--------|
| **Bytes** | ~5-10% compressão extra |
| **Encoding** | Ordinal (Order-preserving) |
| **Scan Time** | -40 a -60% em queries |

---

## enable_schemas: Multi-Schema Lakehouses

Lakehouses com `enable_schemas=True` permitem organizar tables logicamente:

```
MainLakehouse.default.customer_bronze      (schema=default)
MainLakehouse.analytics.sales_gold         (schema=analytics)
MainLakehouse.governance.audit_logs        (schema=governance)
```

**Benefício:** Isolamento lógico sem criar múltiplos lakehouses.

---

## Tables vs Files

| Aspecto | Tables | Files |
|---------|--------|-------|
| **Formato** | Delta Lake (.parquet) | Parquet, CSV, JSON |
| **Transações** | ACID completo | Nenhum (immutable) |
| **Consultas** | SQL/Spark nativo | Requer leitura explícita |
| **Uso Ideal** | Dados estruturados, BI | Raw files, archives |
| **Caminho** | `/Tables/` | `/Files/` |

---

## Managed vs Unmanaged Tables

| Propriedade | Managed | Unmanaged |
|-------------|---------|-----------|
| **Storage** | Dentro do Lakehouse (ABFSS) | Referência a path externo |
| **Ownership** | Fabric (delete table = delete data) | Usuário (delete table = keep data) |
| **Recomendação** | Padrão em Fabric | Use shortcuts ao invés |

---

## Checklist de Implementação

- [ ] Criar lakehouse com `enable_schemas=True`
- [ ] Estruturar diretórios: `Bronze/`, `Silver/`, `Gold/`
- [ ] Aplicar V-Order em todas as tabelas Gold
- [ ] Configurar retention policies (30d Bronze, 1y Silver, 3y Gold)
- [ ] Validar ABFSS paths acessíveis por Spark jobs
- [ ] Testar Direct Lake connection após v-order
- [ ] Documentar lineage no OneLake Catalog
