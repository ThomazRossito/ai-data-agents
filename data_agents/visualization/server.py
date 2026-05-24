"""
Visualization Server — FastAPI + WebSocket + Three.js cenário.

Endpoints:
  GET  /              → serve a cena 3D (static/index.html)
  GET  /health        → status do servidor + broker stats
  GET  /agents        → registry dos 14 agentes (frontend bootstrap)
  WS   /events        → stream de eventos em tempo real

Lifespan:
  - on_startup:  cria broker + tailer dos JSONLs, registra callback
  - on_shutdown: para tailer com graceful join

Rodar standalone:
    python -m data_agents.visualization.server

Ou via uvicorn:
    uvicorn data_agents.visualization.server:app --port 8512 --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Phase 8: fastapi + watchdog são deps opcionais do extra [viz].
# Nota: chainlit (extra [ui], 2.x+) puxa fastapi como transitiva, então testar
# fastapi sozinho não detecta a ausência do [viz]. watchdog é exclusivo do [viz]
# e é o guard correto para garantir que o módulo só rode com o extra completo.
try:
    import watchdog  # noqa: F401 — apenas para validar presença do extra [viz]
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as _exc:
    raise ImportError(
        "dependências do viz não instaladas (watchdog/fastapi). "
        "Para habilitar o servidor de visualização 3D:\n"
        '  pip install -e ".[viz]"\n'
        "  ou: pip install 'fastapi>=0.110' 'uvicorn[standard]>=0.27' 'watchdog>=4.0'"
    ) from _exc

from data_agents.visualization.event_translator import KNOWN_AGENTS, translate
from data_agents.visualization.watcher import JsonlTailer
from data_agents.visualization.ws_broker import WSBroker

logger = logging.getLogger("data_agents.visualization.server")

# Phase 7: arquivo em data_agents/visualization/server.py — raiz é 3 níveis acima.
ROOT = Path(__file__).parent.parent.parent
STATIC_DIR = Path(__file__).parent / "static"
# Tema alternativo V2 — Warcraft Guild Hall (paralelo ao Minecraft)
WARCRAFT_DIR = Path(__file__).parent / "themes" / "warcraft"
# Tema alternativo V3 — Datacenter Cyberpunk (paralelo)
DATACENTER_DIR = Path(__file__).parent / "themes" / "datacenter"

# Logs que o servidor faz tail
AUDIT_LOG = ROOT / "logs" / "audit.jsonl"
WORKFLOWS_LOG = ROOT / "logs" / "workflows.jsonl"
SESSIONS_LOG = ROOT / "logs" / "sessions.jsonl"


# ─── Lifespan ────────────────────────────────────────────────────────────────


async def _poll_backup(tailer: JsonlTailer, interval_s: float = 2.0) -> None:
    """
    Polling de fallback — força drain dos JSONLs periodicamente.

    Razão: watchdog/FSEvents no macOS perde notificações de modificação
    quando o producer (python main.py) escreve com buffered writes. Sem
    esse backup, o frontend pára de receber eventos depois das primeiras
    leituras. Polling de 2s garante zero perda.
    """
    try:
        while True:
            await asyncio.sleep(interval_s)
            try:
                tailer.force_drain_all()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"poll drain falhou: {e}")
    except asyncio.CancelledError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: cria broker + tailer + polling backup. Shutdown: para tudo."""
    broker = WSBroker(backlog_size=200)
    loop = asyncio.get_event_loop()

    async def on_jsonl_event(raw: dict[str, Any], source: str) -> None:
        visual_event = translate(raw, source)
        if visual_event is not None:
            logger.info(
                f"📨 [{source}] {visual_event['type']} "
                f"agent={visual_event.get('agent') or '-'} "
                f"tool={(visual_event.get('tool') or '-')[:50]}"
            )
            await broker.broadcast(visual_event)
        else:
            logger.debug(f"[filtered] source={source} event={raw.get('event', '?')}")

    tailer = JsonlTailer(
        sources={
            "audit": AUDIT_LOG,
            "workflow": WORKFLOWS_LOG,
            "session": SESSIONS_LOG,
        },
        on_event=on_jsonl_event,
        loop=loop,
    )
    tailer.start()
    # Polling fallback de 2s (watchdog do macOS pode perder eventos)
    poll_task = asyncio.create_task(_poll_backup(tailer, interval_s=2.0))

    app.state.broker = broker
    app.state.tailer = tailer
    app.state.poll_task = poll_task

    logger.info(f"servidor pronto na porta {_port()}")
    logger.info(f"  audit:    {AUDIT_LOG}")
    logger.info(f"  workflows: {WORKFLOWS_LOG}")
    logger.info(f"  sessions: {SESSIONS_LOG}")
    logger.info(f"  static:   {STATIC_DIR}")
    logger.info("  polling backup: 2s (fallback do watchdog FSEvents)")

    try:
        yield
    finally:
        poll_task.cancel()
        try:
            await poll_task
        except (asyncio.CancelledError, Exception):
            pass
        tailer.stop()
        logger.info("servidor desligado")


# ─── App ─────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="ai-data-agents · visualization",
    description="Visualização 3D do escritório dos agentes em tempo real",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Status do servidor e do broker."""
    broker: WSBroker = app.state.broker
    tailer: JsonlTailer = app.state.tailer
    sources_info = {}
    for name, state in tailer._states.items():
        sources_info[name] = {
            "path": str(state.path),
            "exists": state.path.exists(),
            "current_size": state.path.stat().st_size if state.path.exists() else 0,
            "tailer_offset": state.offset,
            "partial_bytes": len(state.partial),
        }
    return {
        "status": "ok",
        "audit_log": str(AUDIT_LOG),
        "workflows_log": str(WORKFLOWS_LOG),
        "sessions_log": str(SESSIONS_LOG),
        "connections": broker.connection_count,
        "backlog_size": broker.backlog_size,
        "sources": sources_info,
    }


@app.get("/debug/recent")
async def debug_recent(n: int = 20) -> dict[str, Any]:
    """Retorna os últimos N eventos do backlog do broker, pra debug."""
    broker: WSBroker = app.state.broker
    events = list(broker._backlog)[-n:]
    return {
        "count": len(events),
        "events": events,
    }


@app.post("/debug/force-drain")
async def debug_force_drain() -> dict[str, Any]:
    """Força o tailer a ler todos os arquivos AGORA (útil quando watchdog perde eventos)."""
    tailer: JsonlTailer = app.state.tailer
    tailer.force_drain_all()
    return {"status": "drained", "sources": list(tailer.sources.keys())}


@app.get("/agents")
async def list_agents() -> dict[str, Any]:
    """
    Lista dos 14 agentes pro frontend popular a cena no bootstrap.
    Tenta carregar do registry; se falhar (claude_agent_sdk ausente),
    cai num roster estático embutido.
    """
    try:
        from data_agents.agents.loader import preload_registry

        registry = preload_registry()
        agents = [
            {
                "name": name,
                "tier": meta.tier,
                "description": meta.description[:120],
            }
            for name, meta in registry.items()
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"falha ao carregar registry ({e}); usando roster estático")
        agents = [
            {"name": n, "tier": _static_tier(n), "description": ""} for n in sorted(KNOWN_AGENTS)
        ]

    return {"agents": agents, "count": len(agents)}


_STATIC_TIERS = {
    "geral": "T0",
    "databricks-engineer": "T1",
    "databricks-ai": "T1",
    "fabric-engineer": "T1",
    "migration-expert": "T1",
    "python-expert": "T1",
    "business-analyst": "T3",
}


def _static_tier(name: str) -> str:
    return _STATIC_TIERS.get(name, "T2")


@app.websocket("/events")
async def events_ws(ws: WebSocket) -> None:
    """Conecta cliente ao broker. Recebe backlog imediato + stream contínuo."""
    broker: WSBroker = app.state.broker
    await broker.connect(ws)
    try:
        while True:
            # Mantemos a conexão viva — clientes podem mandar pings ou ignorar
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.debug(f"ws fechada com erro ({e})")
    finally:
        await broker.disconnect(ws)


# ─── Static files ────────────────────────────────────────────────────────────
# Mount precisa vir DEPOIS dos endpoints específicos pra não capturar /health etc.

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─── Tema alternativo: Warcraft Guild Hall (V2 paralelo) ─────────────────────
# Mount estático e endpoint dedicado. Reutiliza o mesmo WebSocket /events,
# mesmo /agents, mesmo /health. Frontend totalmente independente do Minecraft.
if WARCRAFT_DIR.exists():
    app.mount("/warcraft/static", StaticFiles(directory=str(WARCRAFT_DIR)), name="warcraft_static")

if DATACENTER_DIR.exists():
    app.mount(
        "/datacenter/static", StaticFiles(directory=str(DATACENTER_DIR)), name="datacenter_static"
    )


@app.middleware("http")
async def no_cache_on_static(request, call_next):
    """Desabilita cache em /static, /warcraft e / pra evitar JS/HTML obsoletos durante dev."""
    response = await call_next(request)
    path = request.url.path
    if (
        path == "/"
        or path.startswith("/static")
        or path.startswith("/warcraft")
        or path.startswith("/datacenter")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/")
async def index() -> Any:
    """Serve index.html da cena 3D (ou placeholder se ainda não existe)."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(
        {
            "message": "frontend não compilado ainda. Sprint 2 servirá a cena 3D aqui.",
            "endpoints": ["/health", "/agents", "/events (WebSocket)"],
        }
    )


@app.get("/warcraft")
async def warcraft_index() -> Any:
    """Serve o tema Warcraft (V2 em desenvolvimento paralelo)."""
    index_path = WARCRAFT_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(
        {"message": "Tema Warcraft ainda não inicializado. Veja visualization/themes/warcraft/"},
        status_code=404,
    )


@app.get("/warcraft/app.js")
async def warcraft_app_js() -> Any:
    """Atalho pra app.js do tema Warcraft (evita ter que escrever /warcraft/static/app.js no HTML)."""
    js_path = WARCRAFT_DIR / "app.js"
    if js_path.exists():
        return FileResponse(str(js_path), media_type="application/javascript")
    return JSONResponse({"error": "app.js not found"}, status_code=404)


@app.get("/datacenter")
async def datacenter_index() -> Any:
    """Tema V3: Datacenter cyberpunk — agentes como servidores rackeados."""
    index_path = DATACENTER_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(
        {"message": "Tema Datacenter ainda não inicializado."},
        status_code=404,
    )


@app.get("/datacenter/app.js")
async def datacenter_app_js() -> Any:
    """Atalho pra app.js do tema Datacenter."""
    js_path = DATACENTER_DIR / "app.js"
    if js_path.exists():
        return FileResponse(str(js_path), media_type="application/javascript")
    return JSONResponse({"error": "app.js not found"}, status_code=404)


# ─── Entry point ─────────────────────────────────────────────────────────────


def _port() -> int:
    """Lê porta do settings com fallback pro default 8512."""
    try:
        from data_agents.config.settings import settings

        return settings.visualization_port
    except Exception:
        return 8512


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    uvicorn.run(
        "data_agents.visualization.server:app",
        host="127.0.0.1",
        port=_port(),
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
