# Streaming — Conceitos

> Conceitos e definições. Para padrões de implementação, veja patterns/.

**Domínio:** Trigger modes, checkpoints, watermarks, stream-static vs stream-stream joins

---

## Trigger Modes

| Mode | Comportamento | Quando usar |
|------|--------------|-------------|
| **availableNow** | Processa tudo disponível, para | Pipelines batch (jobcluster diário) |
| **processingTime** | Microbatch a cada N segundos | Streams contínuos (latência 10-60s) |
| **continuous** | Sub-segundo (experimental) | Raramente — não suportado para joins/agregações |

---

## Checkpoint: Regras Críticas

| Regra | Consequência da violação |
|-------|-------------------------|
| Nunca deletar checkpoint | Stream recomeça do zero, reprocessa tudo |
| Checkpoint isolado por stream | Não compartilhar entre streams diferentes |
| Checkpoint em local persistente | Não em /tmp efêmero |

---

## Auto Loader: Schema Evolution Modes

| Mode | Comportamento |
|------|--------------|
| `addNewColumns` | Adiciona novas colunas automaticamente (recomendado) |
| `failOnNewColumns` | Falha se aparecer nova coluna |
| `none` | Ignora novas colunas |

---

## Watermark: Late Data

Watermark define quanto tempo o stream aceita dados atrasados antes de descartar.

```
withWatermark("event_time", "1 hour")
```

**Sem watermark:** Dados atrasados nunca são descartados (estado cresce indefinidamente).
**Com watermark:** Após o threshold, dados atrasados são descartados.

---

## Stream-Static vs Stream-Stream Joins

| Tipo | Performance | Overhead | Quando usar |
|------|-------------|----------|-------------|
| **Stream-Static** | Mais eficiente | Baixo | Enriquecer stream com tabela Gold/dim |
| **Stream-Stream** | Mais custoso | State management | Join entre dois tópicos Kafka |

**Regra:** Preferir Stream-Static sempre que possível (carregar dim_ como estática).

---

## Operações Stateful

| Operação | O que mantém em estado | Uso |
|----------|----------------------|-----|
| `dropDuplicates` com watermark | IDs de eventos vistos | Deduplicação em janela |
| `groupBy` + agregação | Resultados parciais por chave | Agregações por período |
| `mapGroupsWithState` | Estado customizado por grupo | Histórico de transações por usuário |

---

## foreachBatch: Padrão de Custom Sink

`foreachBatch` executa uma função Python para cada microbatch.

**Regra:** A função deve ser idempotente (pode ser chamada 2x em caso de falha).
**Use para:** Escrever em múltiplos destinos, lógica customizada, notificações.
