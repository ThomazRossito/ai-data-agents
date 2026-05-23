"""
JSONL Tailer — observa arquivos JSONL e emite cada nova linha como dict.

Comportamento:
  - Começa do final do arquivo (não relê histórico — só eventos novos)
  - Tolera truncate/rotação: se file size < last_offset, reseta para 0
  - Tolera linhas JSON parciais (escreve incremental do produtor):
    guarda o resíduo no buffer e completa na próxima leitura
  - Pesquisa via watchdog (filesystem events) — sem polling caro
  - Thread-safe: callbacks são disparados via asyncio.run_coroutine_threadsafe
    no event loop fornecido na construção

Uso típico:
    async def on_event(raw: dict, source: str) -> None:
        ...

    tailer = JsonlTailer({
        "audit": Path("logs/audit.jsonl"),
        "workflow": Path("logs/workflows.jsonl"),
    }, on_event, loop=asyncio.get_event_loop())
    tailer.start()
    ...
    tailer.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger("data_agents.visualization.watcher")

EventCallback = Callable[[dict[str, Any], str], Awaitable[None]]


class _JsonlFileState:
    """Estado de um arquivo sendo observado (offset, buffer parcial)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = path.stat().st_size if path.exists() else 0
        self.partial = ""  # linha JSON parcial entre leituras

    def read_new_lines(self) -> list[str]:
        """
        Lê o que tiver de novo no arquivo a partir de `offset`. Lida com:
          - arquivo truncado (offset > tamanho atual → reseta)
          - última linha incompleta (sem \\n no fim → guarda no `partial`)
        Retorna lista de linhas completas (sem \\n).
        """
        try:
            current_size = self.path.stat().st_size
        except FileNotFoundError:
            self.offset = 0
            self.partial = ""
            return []

        if current_size < self.offset:
            # Truncate ou rotação — reseta tudo
            logger.info(
                f"{self.path.name}: detectado truncate ({current_size} < {self.offset}), resetando"
            )
            self.offset = 0
            self.partial = ""

        if current_size == self.offset:
            return []

        try:
            with self.path.open("r", encoding="utf-8") as f:
                f.seek(self.offset)
                chunk = f.read()
                self.offset = f.tell()
        except (FileNotFoundError, PermissionError) as e:
            logger.warning(f"{self.path.name}: erro lendo arquivo ({e})")
            return []

        data = self.partial + chunk
        lines = data.split("\n")
        # Última linha pode estar incompleta — guarda
        self.partial = lines[-1]
        return [line for line in lines[:-1] if line.strip()]


class _Handler(FileSystemEventHandler):
    """watchdog handler que dispara o tailer quando um dos arquivos é modificado."""

    def __init__(self, tailer: JsonlTailer) -> None:
        self._tailer = tailer
        self._watched_paths = {str(p.resolve()): name for name, p in tailer.sources.items()}

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        name = self._watched_paths.get(str(Path(event.src_path).resolve()))
        if name:
            self._tailer._drain_one(name)

    # Truncate em alguns sistemas vem como created + modified (especialmente macOS FSEvents)
    on_created = on_modified


class JsonlTailer:
    """
    Tail multi-arquivo. Cria UM observer cobrindo todos os diretórios dos
    arquivos de interesse e despacha as modificações pro estado certo.

    O callback (`on_event`) recebe (raw_dict, source_name). É invocado no
    event loop fornecido em `loop`, mesmo que a chamada original venha do
    thread do watchdog.
    """

    def __init__(
        self,
        sources: dict[str, Path],
        on_event: EventCallback,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.sources = {name: Path(p) for name, p in sources.items()}
        self._on_event = on_event
        self._loop = loop
        self._states: dict[str, _JsonlFileState] = {
            name: _JsonlFileState(p) for name, p in self.sources.items()
        }
        self._observer: Observer | None = None
        self._lock = threading.Lock()  # protege _states durante leitura

    def start(self) -> None:
        if self._observer is not None:
            return
        self._observer = Observer()
        handler = _Handler(self)
        # Observa o diretório de cada arquivo (sem duplicar diretórios)
        watched_dirs: set[Path] = set()
        for path in self.sources.values():
            d = path.parent
            if d not in watched_dirs:
                watched_dirs.add(d)
                d.mkdir(parents=True, exist_ok=True)
                self._observer.schedule(handler, str(d), recursive=False)
        self._observer.start()
        logger.info(f"JsonlTailer iniciado. Fontes: {[str(p) for p in self.sources.values()]}")

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=5.0)
        self._observer = None
        logger.info("JsonlTailer parado")

    def _drain_one(self, name: str) -> None:
        """Lê todas as linhas novas de um arquivo e despacha cada uma."""
        with self._lock:
            state = self._states[name]
            try:
                lines = state.read_new_lines()
            except Exception as e:  # noqa: BLE001
                logger.error(f"erro lendo {name}: {e}", exc_info=True)
                return

        for line in lines:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"linha JSON inválida em {name}: {line[:100]}")
                continue
            self._dispatch(raw, name)

    def _dispatch(self, raw: dict[str, Any], source: str) -> None:
        """Chama o callback no event loop alvo (thread-safe)."""
        try:
            asyncio.run_coroutine_threadsafe(self._on_event(raw, source), self._loop)
        except RuntimeError:
            # Loop pode estar fechando — silencia
            pass

    def force_drain_all(self) -> None:
        """Força leitura de todos os arquivos. Útil em testes/smoke."""
        for name in self.sources:
            self._drain_one(name)
