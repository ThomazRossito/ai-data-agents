"""
Parser de frontmatter YAML para arquivos Markdown.

Centraliza a lógica de parsing compartilhada entre `agents/loader.py`,
`memory/store.py`, e os 5 linters estruturais em `scripts/lint_*.py`.

Implementação
-------------
Esta versão usa `pyyaml` (já dependência declarada em pyproject.toml) com
`yaml.safe_load` em vez do parser linha-por-linha custom anterior. Razões:

  - Suporta YAML 1.1 completo: listas multilinha (`- item`), dicts aninhados,
    block scalars (`>-`, `|`, `|-`), datas, e tipos numéricos corretos.
  - Resolve bugs reais identificados durante a Phase 3 lint:
      * `databricks-dbsql` / `databricks-execution-compute` usavam `description: >-`
        (folded scalar válido YAML). O parser custom interpretava `>-` literal
        (2 chars) em vez do conteúdo concatenado.
      * `agentspec`-style `escalation_rules` (lista de dicts) é impossível
        de expressar no parser linha-por-linha.
  - Habilita o frontmatter rico da Phase 5 (stop_conditions, escalation_rules,
    examples) sem hacks JSON-em-string.

Backward compatibility
----------------------
A assinatura `parse_yaml_frontmatter(content) -> tuple[dict, str]` é
preservada. Comportamento esperado pelos consumers:

  - Frontmatter ausente / mal-formado → ValueError (igual a antes)
  - Campos string → retornados como str
  - Campos numéricos → retornados como int/float (antes também)
  - Listas inline `[a, b]` → list (antes também)
  - Listas multi-line `- a\n- b` → list (novo: antes virava nothing)
  - Dicts `{key: val}` ou `key:\n  sub: val` → dict (novo)
  - Booleanos: `true`/`false` (YAML 1.2 style)
  - **Strings ambíguas que parecem booleano** (`yes`, `no`, `on`, `off`) são
    forçadas a permanecer string via `BaseLoader` customizado nas listas.
    Isso evita pegadinha do YAML 1.1 onde `country: NO` viraria `False`.

Tipo de retorno
---------------
Por compatibilidade com os call sites existentes que esperam dict[str, Any],
mantemos `Any` como tipo dos valores. Consumers devem fazer isinstance checks
quando precisarem garantia de tipo.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

logger = logging.getLogger("data_agents.utils.frontmatter")

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


class _SafeLoaderNoBoolAlias(yaml.SafeLoader):
    """SafeLoader subclass that does NOT interpret YAML 1.1 boolean aliases
    (yes/no/on/off/y/n) as booleans.

    YAML 1.1 (which PyYAML uses by default) treats values like:
        country: NO
        status: yes
        feature: on
    as booleans. This causes silent data loss in real-world frontmatter where
    these strings are intended as string values (e.g. country codes, status
    keywords, on/off labels).

    YAML 1.2 fixed this by restricting booleans to `true`/`false` only. We
    backport that behavior here by removing the bool aliases from the
    implicit resolver list.
    """


# Remove the YAML 1.1 bool resolver from our loader so 'yes'/'no'/'on'/'off'
# remain strings. `true`/`false` (and their cased variants) keep working
# because pyyaml registers them via the same regex; we re-register only the
# strict 1.2-style booleans.
def _install_strict_bool_resolver() -> None:
    """Remove YAML 1.1 bool aliases (yes/no/on/off) and keep only true/false."""
    # Drop bool resolver entirely from the implicit resolvers map
    for ch in list("yYnNtTfFoO"):
        if ch in _SafeLoaderNoBoolAlias.yaml_implicit_resolvers:
            _SafeLoaderNoBoolAlias.yaml_implicit_resolvers[ch] = [
                (tag, regex)
                for tag, regex in _SafeLoaderNoBoolAlias.yaml_implicit_resolvers[ch]
                if tag != "tag:yaml.org,2002:bool"
            ]
    # Re-register strict true/false only
    _SafeLoaderNoBoolAlias.add_implicit_resolver(
        "tag:yaml.org,2002:bool",
        re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
        list("tTfF"),
    )


_install_strict_bool_resolver()


def parse_yaml_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extracts YAML frontmatter and Markdown body from a string.

    Args:
        content: Full file contents including the leading `--- ... ---` block.

    Returns:
        Tuple `(metadata, body)` where `metadata` is the parsed YAML mapping
        (always a dict) and `body` is everything after the closing `---`.

    Raises:
        ValueError: If the frontmatter delimiters are missing or malformed,
                    or if the YAML block does not parse to a mapping.
    """
    if not isinstance(content, str):
        raise ValueError(f"content must be str, got {type(content).__name__}")

    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        raise ValueError("Arquivo sem frontmatter YAML válido (esperado: --- ... ---)")

    yaml_block = match.group(1)
    body = match.group(2).lstrip("\n")

    try:
        # nosec B506 — _SafeLoaderNoBoolAlias herda de SafeLoader (não instancia
        # objetos arbitrários); apenas desliga 'yes/no/on/off' como booleanos.
        parsed = yaml.load(yaml_block, Loader=_SafeLoaderNoBoolAlias)  # nosec B506
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter YAML inválido: {exc}") from exc

    if parsed is None:
        # Empty frontmatter block (e.g. `---\n\n---`) — return empty dict
        return {}, body

    if not isinstance(parsed, dict):
        raise ValueError(
            f"frontmatter deve ser um mapeamento YAML (dict), got {type(parsed).__name__}"
        )

    return parsed, body
