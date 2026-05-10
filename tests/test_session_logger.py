"""
Testes para hooks/session_logger.py.

Cobre:
  - log_session_result(): gravação de métricas em JSONL
  - load_session_history(): leitura, arquivo ausente, linhas malformadas
  - get_session_summary(): agregação de métricas por data
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result_message(cost=1.5, turns=5, duration_ms=3000):
    msg = MagicMock()
    msg.total_cost_usd = cost
    msg.num_turns = turns
    msg.duration_ms = duration_ms
    return msg


def _make_mock_settings(tmp_path: Path):
    audit_log = tmp_path / "logs" / "audit.log"
    mock = MagicMock()
    mock.audit_log_path = str(audit_log)
    return mock


# ---------------------------------------------------------------------------
# log_session_result
# ---------------------------------------------------------------------------


class TestLogSessionResult:
    """Testes para log_session_result()."""

    def test_creates_log_file(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(_make_result_message())
        assert sessions_path.exists()

    def test_log_entry_has_expected_fields(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(
                    _make_result_message(cost=2.0, turns=4, duration_ms=5000),
                    prompt_preview="analisar vendas",
                    session_type="interactive",
                )

        entry = json.loads(sessions_path.read_text().strip())
        assert entry["total_cost_usd"] == 2.0
        assert entry["num_turns"] == 4
        assert entry["duration_ms"] == 5000
        assert entry["prompt_preview"] == "analisar vendas"
        assert entry["session_type"] == "interactive"
        assert "timestamp" in entry

    def test_log_appends_multiple_entries(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(_make_result_message(cost=1.0))
                log_session_result(_make_result_message(cost=2.0))

        lines = [ln for ln in sessions_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_log_truncates_prompt_at_100(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(_make_result_message(), prompt_preview="x" * 200)

        entry = json.loads(sessions_path.read_text().strip())
        assert len(entry["prompt_preview"]) == 100

    def test_log_computes_cost_per_turn(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(_make_result_message(cost=2.0, turns=4))

        entry = json.loads(sessions_path.read_text().strip())
        assert entry["cost_per_turn"] == round(2.0 / 4, 6)

    def test_log_cost_per_turn_none_when_zero_turns(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(_make_result_message(turns=0))

        entry = json.loads(sessions_path.read_text().strip())
        assert entry["cost_per_turn"] is None

    def test_log_handles_oserror_gracefully(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                with patch("builtins.open", side_effect=OSError("disk full")):
                    with patch("os.makedirs"):
                        from hooks.session_logger import log_session_result

                        # Não deve lançar exceção
                        log_session_result(_make_result_message())

    def test_log_handles_none_attributes_gracefully(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        msg = MagicMock()
        msg.total_cost_usd = None
        msg.num_turns = None
        msg.duration_ms = None
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(msg)

        entry = json.loads(sessions_path.read_text().strip())
        assert entry["total_cost_usd"] == 0.0
        assert entry["num_turns"] == 0

    def test_log_computes_duration_seconds(self, tmp_path):
        mock_settings = _make_mock_settings(tmp_path)
        sessions_path = tmp_path / "logs" / "sessions.jsonl"
        with patch("hooks.session_logger.settings", mock_settings):
            with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
                from hooks.session_logger import log_session_result

                log_session_result(_make_result_message(duration_ms=3500))

        entry = json.loads(sessions_path.read_text().strip())
        assert entry["duration_s"] == 3.5


# ---------------------------------------------------------------------------
# load_session_history
# ---------------------------------------------------------------------------


class TestLoadSessionHistory:
    """Testes para load_session_history()."""

    def test_returns_empty_when_no_file(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import load_session_history

            assert load_session_history() == []

    def test_returns_parsed_entries(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        sessions_path.write_text(
            json.dumps({"total_cost_usd": 1.0, "num_turns": 3})
            + "\n"
            + json.dumps({"total_cost_usd": 2.0, "num_turns": 5})
            + "\n"
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import load_session_history

            result = load_session_history()
        assert len(result) == 2
        assert result[0]["total_cost_usd"] == 1.0
        assert result[1]["num_turns"] == 5

    def test_skips_malformed_lines(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        sessions_path.write_text(
            json.dumps({"total_cost_usd": 1.0})
            + "\n"
            + "esta linha é inválida\n"
            + json.dumps({"total_cost_usd": 2.0})
            + "\n"
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import load_session_history

            result = load_session_history()
        assert len(result) == 2

    def test_skips_blank_lines(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        sessions_path.write_text(json.dumps({"total_cost_usd": 1.0}) + "\n\n\n")
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import load_session_history

            result = load_session_history()
        assert len(result) == 1

    def test_returns_empty_on_oserror(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        sessions_path.write_text("{}\n")
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            with patch("builtins.open", side_effect=OSError("permission denied")):
                from hooks.session_logger import load_session_history

                result = load_session_history()
        assert result == []


# ---------------------------------------------------------------------------
# get_session_summary
# ---------------------------------------------------------------------------


class TestGetSessionSummary:
    """Testes para get_session_summary()."""

    def _write_sessions(self, path: Path, entries: list[dict]):
        lines = [json.dumps(e) for e in entries]
        path.write_text("\n".join(lines) + "\n")

    def test_empty_summary_when_no_sessions(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import get_session_summary

            result = get_session_summary()
        assert result["total_sessions"] == 0
        assert result["total_cost_usd"] == 0.0
        assert result["avg_cost_per_session"] == 0.0

    def test_aggregates_cost_and_turns(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        self._write_sessions(
            sessions_path,
            [
                {
                    "total_cost_usd": 1.0,
                    "num_turns": 3,
                    "duration_ms": 1000,
                    "timestamp": "2026-04-09T10:00:00Z",
                },
                {
                    "total_cost_usd": 2.0,
                    "num_turns": 7,
                    "duration_ms": 2000,
                    "timestamp": "2026-04-09T11:00:00Z",
                },
            ],
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import get_session_summary

            result = get_session_summary()
        assert result["total_sessions"] == 2
        assert result["total_cost_usd"] == 3.0
        assert result["total_turns"] == 10

    def test_avg_cost_per_session(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        self._write_sessions(
            sessions_path,
            [
                {
                    "total_cost_usd": 2.0,
                    "num_turns": 2,
                    "duration_ms": 0,
                    "timestamp": "2026-04-09T10:00:00Z",
                },
                {
                    "total_cost_usd": 4.0,
                    "num_turns": 4,
                    "duration_ms": 0,
                    "timestamp": "2026-04-09T11:00:00Z",
                },
            ],
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import get_session_summary

            result = get_session_summary()
        assert result["avg_cost_per_session"] == 3.0

    def test_sessions_grouped_by_date(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        self._write_sessions(
            sessions_path,
            [
                {
                    "total_cost_usd": 1.0,
                    "num_turns": 1,
                    "duration_ms": 0,
                    "timestamp": "2026-04-09T10:00:00Z",
                },
                {
                    "total_cost_usd": 1.0,
                    "num_turns": 1,
                    "duration_ms": 0,
                    "timestamp": "2026-04-09T12:00:00Z",
                },
                {
                    "total_cost_usd": 1.0,
                    "num_turns": 1,
                    "duration_ms": 0,
                    "timestamp": "2026-04-10T09:00:00Z",
                },
            ],
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import get_session_summary

            result = get_session_summary()
        assert result["sessions_by_date"]["2026-04-09"] == 2
        assert result["sessions_by_date"]["2026-04-10"] == 1

    def test_cost_grouped_by_date(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        self._write_sessions(
            sessions_path,
            [
                {
                    "total_cost_usd": 1.5,
                    "num_turns": 1,
                    "duration_ms": 0,
                    "timestamp": "2026-04-09T10:00:00Z",
                },
                {
                    "total_cost_usd": 0.5,
                    "num_turns": 1,
                    "duration_ms": 0,
                    "timestamp": "2026-04-09T12:00:00Z",
                },
            ],
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import get_session_summary

            result = get_session_summary()
        assert result["cost_by_date"]["2026-04-09"] == 2.0

    def test_handles_missing_timestamp_gracefully(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        self._write_sessions(
            sessions_path,
            [
                {"total_cost_usd": 1.0, "num_turns": 1, "duration_ms": 0},
            ],
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import get_session_summary

            result = get_session_summary()
        assert "unknown" in result["sessions_by_date"]

    def test_total_duration_ms(self, tmp_path):
        sessions_path = tmp_path / "sessions.jsonl"
        self._write_sessions(
            sessions_path,
            [
                {
                    "total_cost_usd": 1.0,
                    "num_turns": 1,
                    "duration_ms": 1000,
                    "timestamp": "2026-04-09T10:00:00Z",
                },
                {
                    "total_cost_usd": 1.0,
                    "num_turns": 1,
                    "duration_ms": 2000,
                    "timestamp": "2026-04-09T11:00:00Z",
                },
            ],
        )
        with patch("hooks.session_logger.SESSIONS_LOG_PATH", sessions_path):
            from hooks.session_logger import get_session_summary

            result = get_session_summary()
        assert result["total_duration_ms"] == 3000
