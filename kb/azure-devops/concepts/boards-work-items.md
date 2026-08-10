# Azure Boards — Hierarquia de Work Items

## Processos e hierarquia

O processo do projeto (**Agile**, **Scrum**, **Basic**, ou **CMMI**) determina os tipos de work
item disponíveis e a hierarquia esperada.

### Agile
```
Epic → Feature → User Story → Task
                              └─ Bug (pode ser filho de User Story ou standalone)
```

### Scrum
```
Epic → Feature → Product Backlog Item (PBI) → Task
                                              └─ Bug
```

Antes de criar work items, confirme o processo com `wit_get_work_item_type` (retorna os campos e
regras do tipo) ou pergunte ao usuário se não for óbvio pelo projeto.

## Criando a hierarquia

1. Criar o nível mais alto primeiro: `wit_create_work_item` com `workItemType: "Epic"`.
2. Criar filhos com link automático: `wit_add_child_work_items` (parentId, workItemType, items) —
   evita o passo separado de `wit_work_items_link`.
3. Para linkar work items já existentes (não criados juntos): `wit_work_items_link` com o tipo de
   link (`System.LinkTypes.Hierarchy-Forward` para parent→child).
4. Ligar artefatos de código: `wit_add_artifact_link` (commit/build/PR) ou
   `wit_link_work_item_to_pull_request` (atalho direto para PR).

## Iterations (Sprints)

- `work_list_iterations` — todas as iterations do projeto.
- `work_create_iterations` — criar novas.
- `work_assign_iterations` — atribuir a um time específico.
- `work_get_team_capacity` / `work_update_team_capacity` — capacidade de sprint por membro.
- `wit_get_work_items_for_iteration` — work items de uma iteration específica.

## Consultas (WIQL)

`wit_query_by_wiql` executa uma query em **Work Item Query Language** (dialeto SQL-like):

```sql
SELECT [System.Id], [System.Title], [System.State]
FROM WorkItems
WHERE [System.WorkItemType] = 'User Story'
  AND [System.State] <> 'Closed'
ORDER BY [Microsoft.VSTS.Common.Priority] ASC
```

Alternativas: `wit_my_work_items` (atalho para "meus work items"), `wit_list_backlogs` +
`wit_list_backlog_work_items` (backlog por time/categoria).

## Quando NÃO analisar a árvore aqui

Extrair a árvore de work items (via `wit_query_by_wiql` + `wit_get_work_items_batch_by_ids`) é
responsabilidade deste agente. **Avaliar a qualidade estrutural** dessa árvore — ciclos, órfãos,
caminho crítico, 5 dimensões (completude, clareza, risco, granularidade, alinhamento), propor
split/merge/reorder — é responsabilidade do `task-architect` (agnóstico de plataforma). Extraia os
dados e encaminhe.
