# read-sizing-spreadsheet

Skill FinOps que converte uma **planilha de sizing** (Excel T-shirt band, estilo
"# / Assumption / Value used in estimate / Basis / Notes") em um **cenário de
custo estruturado** para os agents `databricks-cost-calculator` e
`azure-cost-calculator`.

## Por que existe

Quando o cliente já entrega um sizing em planilha, redigitar tudo em linguagem
natural é lento e propenso a erro. Esta skill lê a planilha e monta o cenário
automaticamente — **sem inventar valores**. Campos que não podem ser derivados com
confiança vão para `needs_confirmation` e o agent pergunta ao usuário.

## Arquivos

| Arquivo | O que é |
|---|---|
| `SKILL.md` | Playbook lido pelo agent na 1ª chamada da sessão |
| `parse_sizing.py` | Parser + interpretador (pure Python, só depende de `openpyxl`) |
| `tests/test_parse_sizing.py` | 6 testes (constroem uma planilha Seatrium-like em memória) |
| `README.md` | Este arquivo |

## Como usar

> ⚠️ O diretório tem hífen — não é importável como módulo. Rode como **script**:

```bash
python3 skills/finops/read-sizing-spreadsheet/parse_sizing.py "/caminho/para/sizing.xlsx"
```

Saída: JSON com `scenario` (region, num_envs, storage_gb, workloads, excluded,
`needs_confirmation`). Se `needs_confirmation` não estiver vazio, PARE e pergunte
ao usuário — nunca chute.

Para uso em código Python, importe por path com `importlib` (ver SKILL.md, Forma 2).

## Como testar

```bash
# standalone (sem pytest / sem .env)
python3 skills/finops/read-sizing-spreadsheet/tests/test_parse_sizing.py

# ou via pytest
pytest skills/finops/read-sizing-spreadsheet/tests/test_parse_sizing.py -q

# smoke test manual contra uma planilha real
python3 skills/finops/read-sizing-spreadsheet/parse_sizing.py "/caminho/sizing.xlsx"
```

Saída esperada do smoke test (exemplo Seatrium): `region=southeastasia`,
`num_envs=4`, `storage_gb=50000`, `num_sql_users=70`, `genie=5000 q/mo`,
8 workloads, 6 exclusões, `needs_confirmation=[]`.

## Dependências

- `openpyxl` (já no projeto). Nada mais.

## Robustez conhecida

- Detecção de header ignora linhas de prosa que contenham a palavra "assumptions"
  (exige múltiplas colunas-sinal + presença de coluna "Value").
- Storage prefere figura explícita em GB ("50,000 GB") sobre bandas em TB ("10-100 TB").
- Região mapeada por keywords (Singapore → southeastasia, Brazil → brazilsouth, ...).

## Encadeamento

A saída alimenta o workflow **WF-07 (Greenfield Cost Estimate)** — ver
`kb/collaboration-workflows.md`. O `num_envs` dispara a replicação da infra Azure
por ambiente no `azure-cost-calculator`.
