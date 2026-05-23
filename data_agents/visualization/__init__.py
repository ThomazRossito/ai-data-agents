"""
Visualization — Escritório dos agentes em tempo real.

Servidor FastAPI + WebSocket que faz tail dos logs JSONL (audit + workflows)
e empurra eventos pra uma cena Three.js no browser. Mostra:

  - 14 agentes voxel sentados em mesas num escritório isométrico
  - Supervisor coordenando no centro
  - Dispatcher selecionando subset (agentes adormecem visualmente)
  - Beams animados Supervisor → agente em cada delegação
  - Pulsos no monitor durante tool calls
  - HUD com custo acumulado e badges por agente

Rodar:
    pip install -e ".[viz]"
    python -m data_agents.visualization.server

Componentes:
    watcher.py            — tail dos JSONLs (audit.jsonl + workflows.jsonl)
    event_translator.py   — raw events → schema visual
    ws_broker.py          — gerenciamento de WebSocket connections
    server.py             — FastAPI app
    static/               — frontend Three.js
"""
