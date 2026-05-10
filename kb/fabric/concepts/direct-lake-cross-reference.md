# Direct Lake (Fabric) — Cross-Reference

> Este arquivo contém conteúdo específico do Fabric. A fonte canônica está em:
> `kb/semantic-modeling/concepts/direct-lake-canonical.md`

**Domínio:** Direct Lake no contexto de Fabric Lakehouse e Power BI

---

## Direct Lake no Contexto do Fabric

Direct Lake permite Power BI consultar tabelas Gold diretamente no Lakehouse Fabric (sem import/cache):

| Propriedade | Vantagem | Limitação |
|-------------|----------|-----------|
| **Latência** | Real-time (< 1s) | Sem cache local |
| **Armazenamento** | Zero (no Power BI) | Depende OneLake availability |
| **Transformação** | Spark SQL transparente | Regras estritas de schema |
| **Custo** | Pay-as-you-go (queries) | Sem compactação BI |

---

## Regras Específicas do Lakehouse Fabric

### 1. Tabelas Gold devem ser escritas com V-Order
Veja `kb/semantic-modeling/concepts/direct-lake-canonical.md` para detalhes de implementação.

### 2. CLUSTER BY, nunca PARTITION BY em tabelas Gold
`PARTITION BY` causa fallback automático para Import Mode no Fabric.

### 3. Schema star schema obrigatório
Many-to-One relationships only (Fact → Dimensions).

---

## Fallback Triggers (Fabric-Específico)

| Trigger | Sintoma | Fix |
|---------|---------|-----|
| V-Order ausente | "Direct Lake not available" | Reescrever com V-Order |
| PARTITION BY | Fallback silencioso | Remover partições, usar CLUSTER BY |
| Cardinalidade > 2B | Timeout em Direct Lake | Arquivar dados antigos |
| TIMESTAMP (date col) | Schema validation fail | Converter para DATE |
| Coluna BINARY | Type mismatch | Remover coluna ou converter |

**Debug:** Verifique `DAX Studio` → "Direct Lake" checkbox para confirmar status.

---

## TMDL via REST API (Fabric)

Direct Lake requer definição TMDL (Tabular Model Definition Language) atualizada via REST:

```http
GET /workspaces/{workspace-id}/items/{model-id}/getDefinition
PATCH /workspaces/{workspace-id}/items/{model-id}/updateDefinition
GET /workspaces/{workspace-id}/operations/{operationId}  ← Polling LRO
```

---

## Para Detalhes Completos

Consulte: `kb/semantic-modeling/concepts/direct-lake-canonical.md`
