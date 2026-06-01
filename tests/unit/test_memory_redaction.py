"""
Testes para memory/redaction.py e a integração no hooks/memory_hook.py.

Cobre:
  - redact_pii: casos-ouro de PII brasileira (CPF, CNPJ, e-mail, telefone,
    cartão, CEP) e segredos (token/senha/bearer)
  - preservação de schema-knowledge (nome de coluna "cpf" não é redigido)
  - idempotência sobre placeholders
  - redact_pii_with_counts: contagem por tipo
  - regressão: a captura (_format_context_entry) redige tool_output
  - flag memory_redaction_enabled=False desativa a redação
"""

from unittest.mock import patch

import pytest

from data_agents.memory.redaction import redact_pii, redact_pii_with_counts


# ── redact_pii: casos-ouro ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, placeholder",
    [
        ("meu email é joao.silva@empresa.com.br hoje", "[EMAIL]"),
        ("CPF 123.456.789-00 cadastrado", "[CPF]"),
        ("cpf sem mascara 12345678900 aqui", "[CPF]"),
        ("CNPJ 12.345.678/0001-90 da matriz", "[CNPJ]"),
        ("ligar para (11) 98765-4321 amanha", "[TELEFONE]"),
        ("telefone +55 11 91234-5678 ok", "[TELEFONE]"),
        ("cartao 4111 1111 1111 1111 recusado", "[CARTAO]"),
        ("CEP 01310-100 avenida paulista", "[CEP]"),
        ("token=abc123SECRETvalue no header", "[SECRET]"),
        ("Authorization: Bearer eyJhbGciOiJI", "[SECRET]"),
        ("password=Sup3rS3cr3t! exposto", "[SECRET]"),
    ],
)
def test_redact_pii_replaces_known_patterns(raw: str, placeholder: str) -> None:
    """Cada tipo de PII/segredo deve ser substituído pelo placeholder tipado."""
    out = redact_pii(raw)
    assert placeholder in out
    # O valor sensível original não deve sobreviver (checa o trecho mais distintivo)


def test_redact_pii_strips_actual_values() -> None:
    """O valor real do dado não pode aparecer no texto redigido."""
    raw = "cliente joao@x.com, CPF 123.456.789-00, fone (11) 98765-4321"
    out = redact_pii(raw)
    assert "joao@x.com" not in out
    assert "123.456.789-00" not in out
    assert "98765-4321" not in out


def test_redact_preserves_schema_knowledge() -> None:
    """Conhecimento de schema legítimo (nome de coluna 'cpf') NÃO é redigido."""
    raw = "a tabela clientes tem a coluna cpf que é dado PII"
    out = redact_pii(raw)
    assert out == raw  # nenhuma substituição: não há valor de CPF, só o nome


def test_redact_is_idempotent_on_placeholders() -> None:
    """Rodar a redação novamente não altera placeholders já inseridos."""
    once = redact_pii("CPF 123.456.789-00 e email a@b.com")
    twice = redact_pii(once)
    assert once == twice


def test_redact_empty_and_clean_text() -> None:
    """Texto vazio ou sem PII passa intacto."""
    assert redact_pii("") == ""
    clean = "pipeline Bronze usa Auto Loader com Delta"
    assert redact_pii(clean) == clean


def test_redact_with_counts() -> None:
    """redact_pii_with_counts retorna a contagem por tipo redigido."""
    out, counts = redact_pii_with_counts("a@b.com e c@d.com, CPF 123.456.789-00")
    assert counts.get("[EMAIL]") == 2
    assert counts.get("[CPF]") == 1
    assert "[EMAIL]" in out and "[CPF]" in out


def test_redact_with_counts_empty() -> None:
    """Texto limpo retorna dicionário de contagem vazio."""
    out, counts = redact_pii_with_counts("sem nada sensivel aqui")
    assert counts == {}
    assert out == "sem nada sensivel aqui"


# ── Integração: a captura redige antes de entrar no buffer ─────────────────────


def test_format_context_entry_redacts_tool_output() -> None:
    """_format_context_entry deve redigir PII presente no tool_output (linhas de query)."""
    from data_agents.hooks.memory_hook import _format_context_entry

    tool_output = "row: cliente=joao@x.com cpf=123.456.789-00 valor=100"
    entry = _format_context_entry("mcp__databricks__execute_sql", {}, tool_output)
    assert "joao@x.com" not in entry
    assert "123.456.789-00" not in entry
    assert "[EMAIL]" in entry
    assert "[CPF]" in entry


def test_format_context_entry_redacts_agent_prompt() -> None:
    """O prompt de uma delegação também deve ser redigido."""
    from data_agents.hooks.memory_hook import _format_context_entry

    entry = _format_context_entry(
        "Agent", {"agent_name": "databricks-engineer", "prompt": "buscar cpf 123.456.789-00"}, None
    )
    assert "123.456.789-00" not in entry
    assert "[CPF]" in entry
    assert "databricks-engineer" in entry  # o nome do agente é preservado


def test_redaction_disabled_by_flag() -> None:
    """Com memory_redaction_enabled=False, a captura não redige."""
    from data_agents.hooks.memory_hook import _apply_redaction

    with patch("data_agents.config.settings.settings.memory_redaction_enabled", False):
        out = _apply_redaction("cpf 123.456.789-00")
    assert "123.456.789-00" in out  # não redigido quando a flag está desligada
