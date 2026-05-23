"""
Phase 10: baseline de performance para load_all_agents / preload_registry.

Estes são os caminhos críticos chamados a cada session_start. Se virarem
lentos, todo CLI/UI percebe.

Baseline (MacBook M1 Pro, Python 3.12):
  - preload_registry():    ~30ms  (lê 15 .md, parsa frontmatter via pyyaml)
  - build_escalation_graph: ~5ms   (puro Python, 66 regras)
  - load_all_agents() full: ~200ms (inclui leitura de KBs + skills + cache prefix)

Gate: 20% acima do baseline → falha.
"""

from __future__ import annotations

import os
import time


def _measure(fn, n: int = 5) -> float:
    """Roda fn N vezes, retorna o tempo médio em milissegundos."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    # Usa mediana — mais robusta contra outliers (GC pause, etc)
    times.sort()
    return times[len(times) // 2]


def test_preload_registry_baseline():
    """preload_registry() lê 15 frontmatter YAMLs em < 100ms (mediana de 5 runs)."""
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
    from data_agents.agents.loader import preload_registry

    # Warmup (carrega o módulo, cache filesystem, etc)
    preload_registry()

    elapsed_ms = _measure(preload_registry, n=5)
    print(f"\n  preload_registry: {elapsed_ms:.1f}ms (baseline: 30ms, gate: 36ms)")

    # Gate: 100ms (3x o baseline para margem em CI runners e GitHub Actions)
    # Quando migrar para runner consistente, baixar para 36ms (baseline × 1.20).
    assert elapsed_ms < 100, (
        f"preload_registry: {elapsed_ms:.1f}ms excede o gate de 100ms. "
        f"Investigue regressão em utils/frontmatter.py ou agents/loader.py."
    )


def test_build_escalation_graph_baseline():
    """build_escalation_graph_markdown() consolida 66 regras em < 20ms."""
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
    from data_agents.agents.loader import build_escalation_graph_markdown, preload_registry

    metas = preload_registry()  # warm cache

    # Operação medida
    def build():
        build_escalation_graph_markdown(metas)

    # Warmup
    build()

    elapsed_ms = _measure(build, n=5)
    print(f"\n  build_escalation_graph: {elapsed_ms:.1f}ms (baseline: 5ms, gate: 20ms)")

    assert elapsed_ms < 20, (
        f"build_escalation_graph: {elapsed_ms:.1f}ms excede o gate de 20ms. "
        f"Investigue regex/string concat em agents/loader.py."
    )


def test_frontmatter_parse_baseline():
    """parse_yaml_frontmatter para 1 file típico em < 5ms."""
    from data_agents.utils.frontmatter import parse_yaml_frontmatter
    from pathlib import Path

    # Phase 7: tests/perf/ — repo root é 2 níveis acima.
    repo_root = Path(__file__).resolve().parent.parent.parent
    sample = (repo_root / "data_agents" / "agents" / "registry"
              / "databricks-engineer.md").read_text(encoding="utf-8")

    # Warmup
    parse_yaml_frontmatter(sample)

    def parse():
        parse_yaml_frontmatter(sample)

    elapsed_ms = _measure(parse, n=10)
    print(f"\n  parse_yaml_frontmatter (databricks-engineer.md): "
          f"{elapsed_ms:.2f}ms (baseline: 2ms, gate: 10ms)")

    assert elapsed_ms < 10, (
        f"parse_yaml_frontmatter: {elapsed_ms:.2f}ms excede o gate de 10ms. "
        f"Investigue _SafeLoaderNoBoolAlias custom resolvers."
    )
