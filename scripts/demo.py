"""
Demo canônico do Data Agents.

Executa uma query que requer apenas `ANTHROPIC_API_KEY` — roteia para o
agente `geral` (Haiku 4.5, zero MCP, zero Supervisor). Serve de smoke
test end-to-end para novos usuários que ainda não configuraram
Databricks nem Fabric.

Uso:
    python scripts/demo.py
    make demo

Custo aproximado: ~$0.005 por execução (Haiku 4.5, prompt curto).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

DEMO_QUERY = (
    "Explique a arquitetura Medallion em um data lakehouse "
    "(Bronze → Silver → Gold) em 3 parágrafos curtos, um para cada camada. "
    "Seja objetivo: 2-3 frases por camada."
)


def _load_env() -> None:
    """Carrega .env manualmente (sem dep de python-dotenv)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        # Não sobrescreve se já está no ambiente
        if key and value and key not in os.environ:
            os.environ[key] = value


def _check_api_key() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or key.startswith("sk-ant-...") or "XXX" in key:
        print("\n❌ ANTHROPIC_API_KEY não configurada ou placeholder.")
        print("   Rode `make bootstrap` primeiro ou edite .env manualmente.\n")
        return False
    return True


async def _run_demo() -> int:
    from commands.geral import run_geral_query

    print("━" * 60)
    print(" Data Agents — Demo (Haiku 4.5, zero MCP)")
    print("━" * 60)
    print(f"\nQuery: {DEMO_QUERY}\n")
    print("Executando… (costuma levar 3-8s)\n")
    print("━" * 60)

    history: list[dict] = [{"role": "user", "content": DEMO_QUERY}]
    try:
        response, metrics = await run_geral_query(DEMO_QUERY, history, session_type="demo")
    except Exception as e:
        print(f"\n❌ Demo falhou: {e}")
        print("   Verifique se ANTHROPIC_API_KEY é válida e tem créditos.\n")
        return 1

    print()
    print(response.strip())
    print()
    print("━" * 60)
    print(f"💰 Custo: ${metrics.get('cost', 0):.5f} | ⏱ {metrics.get('duration', 0):.1f}s")
    print("━" * 60)
    print("\n✅ Demo OK. Próximo passo: `make run` para modo interativo.\n")
    return 0


def main() -> int:
    _load_env()
    if not _check_api_key():
        return 1

    # Garante que o REPO_ROOT está no sys.path antes de importar commands.geral
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        return asyncio.run(_run_demo())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrompido pelo usuário.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
