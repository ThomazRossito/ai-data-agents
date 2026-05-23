"""
WebSocket Broker — broadcast de eventos visuais para todos os clientes conectados.

Características:
  - Buffer circular dos últimos N eventos: cliente que conecta recebe
    o backlog imediatamente (catch-up state)
  - Broadcast assíncrono: erros em um cliente não bloqueiam os outros
  - Disconnect graceful: limpa conexões mortas automaticamente
  - Thread-safe (operações async-safe via lock)

Uso:
    broker = WSBroker()
    await broker.connect(websocket)         # também envia backlog
    await broker.broadcast({"type": "tool_call", ...})
    await broker.disconnect(websocket)
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

# Phase 8: fastapi é dep opcional do extra [viz].
try:
    from fastapi import WebSocket
except ImportError as _exc:
    raise ImportError(
        'fastapi não instalado. Para habilitar a visualização 3D:\n  pip install -e ".[viz]"'
    ) from _exc

logger = logging.getLogger("data_agents.visualization.ws_broker")


class WSBroker:
    """Broker que multiplexa eventos para múltiplos clientes WebSocket."""

    def __init__(self, backlog_size: int = 200) -> None:
        self._connections: set[WebSocket] = set()
        self._backlog: deque[dict[str, Any]] = deque(maxlen=backlog_size)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """
        Aceita a conexão, registra, e empurra o backlog imediatamente.
        Mantém ordem de eventos consistente entre clientes.
        """
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
            backlog = list(self._backlog)

        if backlog:
            # Envia backlog em batch único pra reduzir ruído na rede
            try:
                await ws.send_json({"type": "_backlog", "events": backlog})
            except Exception as e:  # noqa: BLE001
                logger.warning(f"erro enviando backlog: {e}")

        logger.info(f"cliente conectado. total: {len(self._connections)}")

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove conexão do set. Idempotente."""
        async with self._lock:
            self._connections.discard(ws)
        logger.info(f"cliente desconectado. total: {len(self._connections)}")

    async def broadcast(self, event: dict[str, Any]) -> None:
        """
        Envia evento pra todas conexões ativas. Falhas em clientes individuais
        não bloqueiam o broadcast — apenas removem o cliente faltoso.

        Também adiciona ao backlog (cliente que conecta depois pega).
        """
        async with self._lock:
            self._backlog.append(event)
            targets = list(self._connections)

        if not targets:
            return

        # Envia em paralelo — gather captura exceções por cliente
        results = await asyncio.gather(
            *[self._send_safe(ws, event) for ws in targets],
            return_exceptions=True,
        )

        # Remove conexões que falharam
        dead: list[WebSocket] = []
        for ws, result in zip(targets, results, strict=False):
            if isinstance(result, Exception):
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
            logger.info(f"limpou {len(dead)} conexões mortas")

    async def _send_safe(self, ws: WebSocket, event: dict[str, Any]) -> None:
        """Wrapper que envia evento e propaga exceção para o gather."""
        await ws.send_json(event)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def backlog_size(self) -> int:
        return len(self._backlog)
