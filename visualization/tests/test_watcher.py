"""
Testes do JsonlTailer.

Foco no `_JsonlFileState` (lógica pura, sem watchdog), pra evitar
dependência de filesystem events nos testes — esses são lentos e flaky.
A integração com watchdog é coberta pelo smoke E2E.
"""

from __future__ import annotations

import json
from pathlib import Path

from visualization.watcher import _JsonlFileState


def _write_lines(path: Path, lines: list[dict]) -> None:
    """Append lines de JSON ao arquivo (sem newline final)."""
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def test_starts_at_end_of_existing_file(tmp_path):
    """Tailer nunca relê histórico — começa do tamanho atual."""
    p = tmp_path / "audit.jsonl"
    _write_lines(p, [{"event": "old1"}, {"event": "old2"}])
    state = _JsonlFileState(p)
    # Não deve ter lido nada — o conteúdo existente é histórico
    assert state.read_new_lines() == []
    # Próxima escrita é capturada
    _write_lines(p, [{"event": "new1"}])
    lines = state.read_new_lines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "new1"


def test_handles_truncate(tmp_path):
    """Se arquivo encolher, reseta offset."""
    p = tmp_path / "audit.jsonl"
    _write_lines(p, [{"event": "a"}, {"event": "b"}, {"event": "c"}])
    state = _JsonlFileState(p)
    # Trunca
    p.write_text("")
    # Escreve algo novo
    _write_lines(p, [{"event": "after_truncate"}])
    lines = state.read_new_lines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "after_truncate"


def test_handles_partial_lines(tmp_path):
    """Linha sem \\n no fim fica no buffer até a próxima leitura completar."""
    p = tmp_path / "audit.jsonl"
    p.touch()
    state = _JsonlFileState(p)
    # Escreve linha parcial (sem newline)
    with p.open("a", encoding="utf-8") as f:
        f.write('{"event":"par')
    lines = state.read_new_lines()
    assert lines == []  # nada completo ainda
    # Completa a linha
    with p.open("a", encoding="utf-8") as f:
        f.write('tial"}\n')
    lines = state.read_new_lines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "partial"


def test_skips_blank_lines(tmp_path):
    p = tmp_path / "audit.jsonl"
    p.touch()
    state = _JsonlFileState(p)
    with p.open("a", encoding="utf-8") as f:
        f.write('{"event":"a"}\n\n\n{"event":"b"}\n')
    lines = state.read_new_lines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "a"
    assert json.loads(lines[1])["event"] == "b"


def test_handles_nonexistent_file_gracefully(tmp_path):
    p = tmp_path / "missing.jsonl"
    state = _JsonlFileState(p)
    assert state.read_new_lines() == []


def test_offset_advances_correctly(tmp_path):
    p = tmp_path / "audit.jsonl"
    p.touch()
    state = _JsonlFileState(p)
    _write_lines(p, [{"event": "1"}])
    state.read_new_lines()
    initial_offset = state.offset
    _write_lines(p, [{"event": "2"}])
    state.read_new_lines()
    assert state.offset > initial_offset


def test_multiple_lines_in_one_chunk(tmp_path):
    """Várias linhas escritas no mesmo flush — todas retornadas."""
    p = tmp_path / "audit.jsonl"
    p.touch()
    state = _JsonlFileState(p)
    _write_lines(p, [{"event": "1"}, {"event": "2"}, {"event": "3"}])
    lines = state.read_new_lines()
    assert len(lines) == 3
