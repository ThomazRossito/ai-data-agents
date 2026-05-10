"""
Testes para hooks/checkpoint.py.

Cobre:
  - save_checkpoint(): criação do arquivo JSON com campos corretos
  - load_checkpoint(): leitura, arquivo ausente, JSON inválido
  - clear_checkpoint(): remoção do arquivo e caso inexistente
  - build_resume_prompt(): formatação do prompt de retomada
  - _scan_output_files(): varredura de diretório de output
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings(tmp_path: Path):
    """Retorna um mock de settings apontando para tmp_path."""
    audit_log = tmp_path / "logs" / "audit.log"
    mock = MagicMock()
    mock.audit_log_path = str(audit_log)
    mock.max_budget_usd = 5.0
    mock.default_model = "claude-opus-4-6"
    return mock


# ---------------------------------------------------------------------------
# save_checkpoint
# ---------------------------------------------------------------------------


class TestSaveCheckpoint:
    """Testes para save_checkpoint()."""

    def test_save_creates_file(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            with patch("hooks.checkpoint.CHECKPOINT_PATH", tmp_path / "logs" / "checkpoint.json"):
                from hooks.checkpoint import save_checkpoint

                path = save_checkpoint("meu prompt", "budget_exceeded", cost_usd=1.5, turns=10)
                assert path.exists()

    def test_save_returns_checkpoint_path(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            cp_path = tmp_path / "logs" / "checkpoint.json"
            with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
                from hooks.checkpoint import save_checkpoint

                result = save_checkpoint("prompt", "user_reset")
                assert result == cp_path

    def test_save_content_fields(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            cp_path = tmp_path / "logs" / "checkpoint.json"
            with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
                from hooks.checkpoint import save_checkpoint

                save_checkpoint(
                    "último prompt",
                    "budget_exceeded",
                    cost_usd=2.5,
                    turns=7,
                    output_files=["output/file.md"],
                )
                data = json.loads(cp_path.read_text(encoding="utf-8"))

        assert data["reason"] == "budget_exceeded"
        assert data["last_prompt"] == "último prompt"
        assert data["cost_usd"] == 2.5
        assert data["turns"] == 7
        assert data["output_files"] == ["output/file.md"]
        assert "timestamp" in data

    def test_save_truncates_prompt_at_500(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            cp_path = tmp_path / "logs" / "checkpoint.json"
            with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
                from hooks.checkpoint import save_checkpoint

                long_prompt = "x" * 600
                save_checkpoint(long_prompt, "idle_timeout")
                data = json.loads(cp_path.read_text(encoding="utf-8"))

        assert len(data["last_prompt"]) == 500

    def test_save_calls_scan_when_output_files_none(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            cp_path = tmp_path / "logs" / "checkpoint.json"
            with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
                with patch(
                    "hooks.checkpoint._scan_output_files", return_value=["a.md"]
                ) as mock_scan:
                    from hooks.checkpoint import save_checkpoint

                    save_checkpoint("p", "user_reset")
                    mock_scan.assert_called_once()

    def test_save_does_not_call_scan_when_output_files_provided(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            cp_path = tmp_path / "logs" / "checkpoint.json"
            with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
                with patch("hooks.checkpoint._scan_output_files") as mock_scan:
                    from hooks.checkpoint import save_checkpoint

                    save_checkpoint("p", "user_reset", output_files=["already.md"])
                    mock_scan.assert_not_called()

    def test_save_handles_oserror_gracefully(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            cp_path = tmp_path / "logs" / "checkpoint.json"
            with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
                with patch("builtins.open", side_effect=OSError("disk full")):
                    with patch("os.makedirs"):
                        from hooks.checkpoint import save_checkpoint

                        # Não deve lançar exceção
                        result = save_checkpoint("p", "budget_exceeded")
                        assert result == cp_path


# ---------------------------------------------------------------------------
# load_checkpoint
# ---------------------------------------------------------------------------


class TestLoadCheckpoint:
    """Testes para load_checkpoint()."""

    def test_load_returns_none_when_no_file(self, tmp_path):
        cp_path = tmp_path / "checkpoint.json"
        with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
            from hooks.checkpoint import load_checkpoint

            assert load_checkpoint() is None

    def test_load_returns_data_when_file_exists(self, tmp_path):
        cp_path = tmp_path / "checkpoint.json"
        data = {"reason": "user_reset", "last_prompt": "oi", "cost_usd": 0.5}
        cp_path.write_text(json.dumps(data), encoding="utf-8")
        with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
            from hooks.checkpoint import load_checkpoint

            result = load_checkpoint()
        assert result == data

    def test_load_returns_none_on_invalid_json(self, tmp_path):
        cp_path = tmp_path / "checkpoint.json"
        cp_path.write_text("não é json", encoding="utf-8")
        with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
            from hooks.checkpoint import load_checkpoint

            result = load_checkpoint()
        assert result is None

    def test_load_returns_none_on_oserror(self, tmp_path):
        cp_path = tmp_path / "checkpoint.json"
        cp_path.write_text("{}", encoding="utf-8")
        with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
            with patch("builtins.open", side_effect=OSError("permission denied")):
                from hooks.checkpoint import load_checkpoint

                result = load_checkpoint()
        assert result is None


# ---------------------------------------------------------------------------
# clear_checkpoint
# ---------------------------------------------------------------------------


class TestClearCheckpoint:
    """Testes para clear_checkpoint()."""

    def test_clear_removes_existing_file(self, tmp_path):
        cp_path = tmp_path / "checkpoint.json"
        cp_path.write_text("{}", encoding="utf-8")
        with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
            from hooks.checkpoint import clear_checkpoint

            clear_checkpoint()
        assert not cp_path.exists()

    def test_clear_does_nothing_when_no_file(self, tmp_path):
        cp_path = tmp_path / "checkpoint.json"
        with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
            from hooks.checkpoint import clear_checkpoint

            # Não deve lançar exceção
            clear_checkpoint()

    def test_clear_handles_oserror_gracefully(self, tmp_path):
        cp_path = tmp_path / "checkpoint.json"
        cp_path.write_text("{}", encoding="utf-8")
        with patch("hooks.checkpoint.CHECKPOINT_PATH", cp_path):
            with patch("os.remove", side_effect=OSError("busy")):
                from hooks.checkpoint import clear_checkpoint

                # Não deve lançar exceção
                clear_checkpoint()


# ---------------------------------------------------------------------------
# build_resume_prompt
# ---------------------------------------------------------------------------


class TestBuildResumePrompt:
    """Testes para build_resume_prompt()."""

    def _make_checkpoint(self, **overrides):
        base = {
            "reason": "budget_exceeded",
            "last_prompt": "analisar vendas",
            "cost_usd": 1.23,
            "turns": 5,
            "output_files": [],
            "timestamp": "2026-04-09T22:00:00+00:00",
        }
        base.update(overrides)
        return base

    def test_prompt_contains_reason_text(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(reason="budget_exceeded"))
        assert "orçamento" in prompt.lower()

    def test_prompt_contains_user_reset_text(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(reason="user_reset"))
        assert "resetou" in prompt.lower()

    def test_prompt_contains_idle_timeout_text(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(reason="idle_timeout"))
        assert "inatividade" in prompt.lower()

    def test_prompt_contains_unknown_reason_as_is(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(reason="mystery_event"))
        assert "mystery_event" in prompt

    def test_prompt_contains_cost(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(cost_usd=3.1415))
        assert "3.1415" in prompt

    def test_prompt_contains_turns(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(turns=42))
        assert "42" in prompt

    def test_prompt_contains_last_prompt(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(last_prompt="analisar vendas Q1"))
        assert "analisar vendas Q1" in prompt

    def test_prompt_lists_output_files(self):
        from hooks.checkpoint import build_resume_prompt

        files = ["output/report.md", "output/data.csv"]
        prompt = build_resume_prompt(self._make_checkpoint(output_files=files))
        assert "output/report.md" in prompt
        assert "output/data.csv" in prompt

    def test_prompt_limits_files_to_20(self):
        from hooks.checkpoint import build_resume_prompt

        files = [f"output/file_{i}.md" for i in range(30)]
        prompt = build_resume_prompt(self._make_checkpoint(output_files=files))
        # Os últimos 10 (file_20 a file_29) não devem aparecer
        assert "file_20" not in prompt

    def test_prompt_without_output_files(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint(output_files=[]))
        assert "Arquivos gerados" not in prompt

    def test_prompt_contains_instruction(self):
        from hooks.checkpoint import build_resume_prompt

        prompt = build_resume_prompt(self._make_checkpoint())
        assert "Instrução" in prompt


# ---------------------------------------------------------------------------
# _scan_output_files
# ---------------------------------------------------------------------------


class TestScanOutputFiles:
    """Testes para _scan_output_files()."""

    def test_scan_returns_empty_when_no_output_dir(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            from hooks.checkpoint import _scan_output_files

            result = _scan_output_files()
        assert result == []

    def test_scan_returns_files(self, tmp_path):
        # Estrutura: tmp_path/logs/audit.log (para settings)
        #            tmp_path/output/report.md
        (tmp_path / "output").mkdir()
        (tmp_path / "output" / "report.md").write_text("conteúdo")

        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            from hooks.checkpoint import _scan_output_files

            result = _scan_output_files()
        assert any("report.md" in f for f in result)

    def test_scan_skips_hidden_files(self, tmp_path):
        (tmp_path / "output").mkdir()
        (tmp_path / "output" / ".hidden").write_text("oculto")
        (tmp_path / "output" / "visible.md").write_text("visível")

        mock_settings = _make_mock_settings(tmp_path)
        with patch("hooks.checkpoint.settings", mock_settings):
            from hooks.checkpoint import _scan_output_files

            result = _scan_output_files()
        assert not any(".hidden" in f for f in result)
        assert any("visible.md" in f for f in result)
