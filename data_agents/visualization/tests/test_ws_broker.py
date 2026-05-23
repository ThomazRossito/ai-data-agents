"""Testes do WSBroker — broadcast multi-cliente com buffer."""

from __future__ import annotations

import pytest

from data_agents.visualization.ws_broker import WSBroker


class FakeWebSocket:
    """Mock minimalista de WebSocket pra testes."""

    def __init__(self, fail_on_send: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict] = []
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail_on_send:
            raise ConnectionError("simulated")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_connect_accepts_and_sends_empty_backlog():
    broker = WSBroker()
    ws = FakeWebSocket()
    await broker.connect(ws)
    assert ws.accepted is True
    # Sem eventos prévios, não envia backlog (lista vazia)
    assert ws.sent == []
    assert broker.connection_count == 1


@pytest.mark.asyncio
async def test_connect_replays_backlog():
    broker = WSBroker(backlog_size=10)
    # Eventos antes da conexão
    await broker.broadcast({"type": "tool_call", "agent": "a", "tool": "x"})
    await broker.broadcast({"type": "delegation", "agent": "b"})
    # Cliente conecta DEPOIS
    ws = FakeWebSocket()
    await broker.connect(ws)
    assert len(ws.sent) == 1
    msg = ws.sent[0]
    assert msg["type"] == "_backlog"
    assert len(msg["events"]) == 2
    assert msg["events"][0]["agent"] == "a"
    assert msg["events"][1]["agent"] == "b"


@pytest.mark.asyncio
async def test_broadcast_reaches_all_connections():
    broker = WSBroker()
    a, b, c = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
    await broker.connect(a)
    await broker.connect(b)
    await broker.connect(c)
    await broker.broadcast({"type": "tool_call", "tool": "Read"})
    assert a.sent[-1]["tool"] == "Read"
    assert b.sent[-1]["tool"] == "Read"
    assert c.sent[-1]["tool"] == "Read"


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections():
    broker = WSBroker()
    healthy = FakeWebSocket()
    broken = FakeWebSocket(fail_on_send=True)
    await broker.connect(healthy)
    await broker.connect(broken)
    assert broker.connection_count == 2
    await broker.broadcast({"type": "tool_call"})
    # Cliente saudável recebeu, broken foi removido
    assert len(healthy.sent) >= 1
    assert broker.connection_count == 1


@pytest.mark.asyncio
async def test_disconnect_removes_connection():
    broker = WSBroker()
    ws = FakeWebSocket()
    await broker.connect(ws)
    assert broker.connection_count == 1
    await broker.disconnect(ws)
    assert broker.connection_count == 0


@pytest.mark.asyncio
async def test_backlog_respects_max_size():
    broker = WSBroker(backlog_size=3)
    for i in range(10):
        await broker.broadcast({"type": "x", "n": i})
    assert broker.backlog_size == 3
    # Os últimos 3 são os preservados (7, 8, 9)
    ws = FakeWebSocket()
    await broker.connect(ws)
    backlog = ws.sent[0]["events"]
    assert [e["n"] for e in backlog] == [7, 8, 9]


@pytest.mark.asyncio
async def test_broadcast_with_no_connections_still_buffers():
    """Mesmo sem clientes, broadcast deve preencher o backlog."""
    broker = WSBroker()
    await broker.broadcast({"type": "x", "v": 1})
    assert broker.backlog_size == 1


@pytest.mark.asyncio
async def test_disconnect_is_idempotent():
    broker = WSBroker()
    ws = FakeWebSocket()
    await broker.connect(ws)
    await broker.disconnect(ws)
    await broker.disconnect(ws)  # não levanta
    assert broker.connection_count == 0
