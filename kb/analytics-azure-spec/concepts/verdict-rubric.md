# Rubrica Determinística de Veredito (procedimento reproduzível)

> Objetivo: o **mesmo conjunto de insumos sempre produz o mesmo veredito**. Nada de "impressão geral".
> O veredito é calculado por uma checklist de subitens + uma fórmula fixa.

## Procedimento (executar igual em toda auditoria)

Para CADA controle do Módulo B:

1. **Carregue os subitens obrigatórios** do controle (`concepts/module-b-controls.md`).
2. **Monte a checklist `covered[subitem] ∈ {sim, não}`.** `sim` somente se houver evidência
   **localizável** (arquivo › local › trecho) que **demonstra** o subitem. Use o
   `concepts/resource-control-map.md` para creditar screenshots de recursos.
   - "Demonstra" ≠ "menciona". Citar a palavra "encryption" sem mostrar o mecanismo/recurso = `não`.
   - Screenshot que prova existência do recurso exigido pelo subitem = `sim` (parcial conta como `sim`
     para o subitem, mas pode manter o controle em 🟡 se outro subitem exigir profundidade).
3. **Verifique formalização exigida** (quando o controle pede): sign-off do cliente (4.1),
   Signed SOW (3.1), export do Core WAR com 2 pilares (2.2). Marque `formal_ok ∈ {sim, não}`.
4. **Compute a Cobertura (Eixo A)** com a fórmula fixa:
   - `covered == total` **e** `formal_ok == sim` → ✅ **Completa**
   - `covered == 0` → ❌ **Ausente**
   - caso contrário (`0 < covered < total`, ou `covered == total` mas `formal_ok == não`) → 🟡 **Parcial**
   - evidência presente mas ilegível/ambígua mesmo após OCR → ⚠️ **Needs Review**
5. **Conte clientes únicos (Eixo B):** nº de clientes nominais distintos com evidência → `x / exigido`.
6. **Status ISSI:** ✅ só se Cobertura ✅ **e** clientes ≥ exigido. Senão, descreva a lacuna por eixo.

## Fronteira 🟡 vs ❌ (elimina oscilação entre execuções)

- ❌ **Ausente** é um estado FORTE: significa que **nenhum** subitem tem evidência rastreável.
- Se **um único** subitem tem evidência → o controle é **no mínimo 🟡**.
- Nunca rebaixe para ❌ por falta de formalização ou de clientes — isso é 🟡 (cobertura) + nota de gate.

## Exemplos canônicos (para reproduzir vereditos)

- **1.1 Assessment** com business need + estado atual/futuro + baseline de performance + personas
  (grupos de acesso), mas sem Skilling Plan e sem Assessment Report formal →
  `covered` parcial → **🟡 Parcial** (NÃO ❌, porque há subitens demonstrados).
- **2.1 Solution Design** com ADF+Databricks+Kafka, ADLS Gen2, Power BI, Key Vault, Service Principals,
  Azure DevOps, mas sem ALZ conceitual formal nem RBAC row/column → muitos subitens `sim`, alguns `não`
  → **🟡 Parcial** (Encryption conta via Key Vault; ALZ/row-level faltam).
- **2.2 WAR** sem nenhum export do Core WAR → `covered == 0` → **❌ Ausente**.
- **4.1 Validation** com performance + Data Quality Framework, mas sem sign-off documentado →
  subitens cobertos mas `formal_ok == não` → **🟡 Parcial**.

## Como reportar (dois eixos sempre visíveis)

Para cada controle, o relatório mostra:
`Cobertura: <✅/🟡/❌/⚠️> · Clientes: x/3 · Status ISSI: <✅ / falta cobertura / faltam N clientes>`
+ "Subitens cobertos: [...] | Faltando: [...]" + evidências citadas + próximo passo acionável.
