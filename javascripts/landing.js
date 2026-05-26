/* docs/site/javascripts/landing.js — interatividade da landing executiva.
 *
 * Responsabilidades:
 *   1. Trocar conteúdo das 3 tabs de persona (Stakeholder / Cliente / Dev)
 *   2. Abrir modal de detalhes quando o usuário clica num agente do org chart
 *
 * Os dados dos agentes são embedded estaticamente neste arquivo a partir
 * do frontmatter dos *.md em data_agents/agents/registry/. Para atualizar,
 * editar manualmente o objeto AGENT_DATA abaixo OU regenerar via script
 * (futuro: scripts/gen_landing_data.py).
 */

(function () {
  "use strict";

  // ── Dados dos agentes (snapshot do registry em v3.0.1) ────────────────
  const AGENT_DATA = {
    supervisor: {
      label: "Supervisor",
      tier: "Central",
      model: "kimi-k2.6",
      description:
        "Orquestrador central. Recebe a pergunta do usuário, consulta a Constituição (regras S1–S7), faz Clarity Checkpoint, planeja e delega ao agente especialista correto. Nunca executa SQL/PySpark nem acessa MCP diretamente.",
      mcps: [],
      kbs: ["constitution", "shared", "checklists"],
    },
    "databricks-engineer": {
      label: "databricks-engineer",
      tier: "T1",
      model: "kimi-k2.6",
      description:
        "Especialista completo em Databricks: SQL, PySpark, Delta Lake, LakeFlow/DLT, Jobs, CDC, diagnóstico Spark (OOM/skew/shuffle), Genie Spaces, AI/BI Dashboards.",
      mcps: ["databricks", "databricks_genie", "context7", "migration_source", "postgres", "memory_mcp", "github", "tavily"],
      kbs: ["databricks", "spark-patterns", "sql-patterns", "pipeline-design", "migration"],
    },
    "databricks-ai": {
      label: "databricks-ai",
      tier: "T1",
      model: "kimi-k2.6",
      description:
        "RAG, Vector Search, LLMOps, AI Functions, streaming com Kafka/Flink/Spark Structured Streaming no Databricks.",
      mcps: ["databricks", "context7", "tavily"],
      kbs: ["databricks", "spark-patterns", "pipeline-design"],
    },
    "fabric-engineer": {
      label: "fabric-engineer",
      tier: "T1",
      model: "kimi-k2.6",
      description:
        "Microsoft Fabric end-to-end: Medallion, Star Schema, Semantic Model, DAX, Direct Lake, governança, FinOps Capacity Units.",
      mcps: ["fabric", "fabric_community", "fabric_official", "fabric_sql", "fabric_semantic"],
      kbs: ["fabric", "pipeline-design", "semantic-modeling", "data-quality", "governance"],
    },
    "migration-expert": {
      label: "migration-expert",
      tier: "T1",
      model: "kimi-k2.6",
      description:
        "Assessment e migração de bancos relacionais (SQL Server, PostgreSQL) para Databricks ou Fabric. 7 fases automatizadas via /workflow WF-05.",
      mcps: ["migration_source", "databricks", "fabric", "fabric_sql", "context7"],
      kbs: ["migration", "pipeline-design", "databricks", "fabric", "sql-patterns"],
    },
    "python-expert": {
      label: "python-expert",
      tier: "T1",
      model: "kimi-k2.6",
      description:
        "Python puro: empacotamento, APIs (FastAPI), CLIs, testes (pytest), automação. Sem foco em plataformas de dados.",
      mcps: ["context7"],
      kbs: ["python-patterns"],
    },
    "dbt-expert": {
      label: "dbt-expert",
      tier: "T2",
      model: "kimi-k2.6",
      description:
        "dbt Core: models, testes, snapshots, docs, macros. Suporte a vários warehouses (Databricks, Postgres, BigQuery).",
      mcps: ["context7", "postgres"],
      kbs: ["sql-patterns"],
    },
    "data-quality-steward": {
      label: "data-quality-steward",
      tier: "T2",
      model: "kimi-k2.6",
      description:
        "Qualidade de dados cross-platform: expectations, profiling, drift detection, SLA. Lê de Databricks, Fabric e Postgres.",
      mcps: ["databricks", "fabric", "fabric_community", "fabric_rti", "postgres"],
      kbs: ["data-quality", "databricks", "fabric", "industry"],
    },
    "governance-auditor": {
      label: "governance-auditor",
      tier: "T2",
      model: "kimi-k2.6",
      description:
        "Governança cross-platform: LGPD/PII, linhagem, RLS/OLS, auditoria de permissões. NUNCA delegado para engenheiros (S6).",
      mcps: ["databricks", "fabric", "fabric_community", "tavily", "postgres", "memory_mcp"],
      kbs: ["governance", "databricks", "fabric", "industry"],
    },
    "data-contracts-engineer": {
      label: "data-contracts-engineer",
      tier: "T2",
      model: "kimi-k2.6",
      description:
        "Data Contracts (ODCS), SLA contratual, schema evolution, detecção de breaking changes. Comando /contract.",
      mcps: ["context7", "databricks", "fabric_sql", "postgres", "memory_mcp"],
      kbs: ["data-contracts", "data-quality", "governance"],
    },
    "data-mesh-architect": {
      label: "data-mesh-architect",
      tier: "T2",
      model: "kimi-k2.6",
      description:
        "Data Mesh: domínios, Data Products, governança federada, plataforma self-service. Comando /mesh.",
      mcps: ["context7", "tavily", "databricks", "memory_mcp"],
      kbs: ["data-mesh", "governance", "pipeline-design", "databricks", "fabric"],
    },
    "fabric-rti": {
      label: "fabric-rti",
      tier: "T2",
      model: "kimi-k2.6",
      description:
        "Microsoft Fabric Real-Time Intelligence: Eventhouse, KQL/Kusto, Eventstream, Data Activator.",
      mcps: ["fabric_rti"],
      kbs: ["fabric", "pipeline-design", "spark-patterns"],
    },
    "fabric-ontology": {
      label: "fabric-ontology",
      tier: "T2",
      model: "kimi-k2.6",
      description:
        "Web semântica + Fabric IQ Ontology: OWL 2, RDF, SPARQL, materialização para Delta. Comando /ontology.",
      mcps: ["context7", "tavily", "firecrawl", "fabric", "fabric_community", "fabric_official", "fabric_sql", "fabric_ontology"],
      kbs: ["semantic-web", "fabric", "governance"],
    },
    "azure-cost-calculator": {
      label: "azure-cost-calculator",
      tier: "T2",
      model: "kimi-k2.6",
      isNew: true,
      description:
        "FinOps Azure: cálculo de preços via Azure Retail Prices API, rightsizing, estimativas de custo de SKUs (compute, storage, Databricks DBUs, Fabric CUs).",
      mcps: ["azure_pricing"],
      kbs: ["azure-pricing"],
    },
    "business-analyst": {
      label: "business-analyst",
      tier: "T3",
      model: "kimi-k2.6",
      description:
        "Intake de requisitos: converte transcripts e briefings de negócio em backlog estruturado (épicos, histórias, critérios de aceite). Comando /brief.",
      mcps: ["tavily", "firecrawl"],
      kbs: ["business-analysis"],
    },
    geral: {
      label: "geral",
      tier: "T0",
      model: "kimi-k2.6",
      description:
        "Respostas conceituais rápidas, sem usar MCP. Para perguntas tipo 'o que é Delta Lake?' que não precisam tocar nenhuma plataforma. Comando /geral, ~95% mais barato.",
      mcps: [],
      kbs: [],
    },
  };

  // ── Conteúdo das tabs de persona ──────────────────────────────────────
  const PERSONA_CONTENT = {
    exec: `
      <p style="margin: 0 0 0.75rem; color: var(--md-default-fg-color--light); font-size: 0.9rem;">Em 3 frases para quem decide:</p>
      <ul>
        <li>Reduz o tempo de migração de DW on-premise para Databricks ou Fabric de meses para semanas — o workflow <code>WF-05</code> automatiza as 7 fases (briefing → assessment → execução → validação).</li>
        <li>Auditoria 100% rastreável — toda chamada de ferramenta é registrada em log estruturado e assinada com <code>HMAC-SHA256</code>, à prova de adulteração.</li>
        <li>Custo médio de <code>$0.07/sessão</code> usando Moonshot Kimi K2.6 — cerca de 5× mais barato que Claude Sonnet equivalente.</li>
      </ul>`,
    client: `
      <p style="margin: 0 0 0.75rem; color: var(--md-default-fg-color--light); font-size: 0.9rem;">O que você consegue fazer no dia 1:</p>
      <ul>
        <li><code>/migrate</code> — SQL Server / PostgreSQL → Databricks ou Fabric, 7 fases automatizadas</li>
        <li><code>/quality</code> — expectations e profiling cross-platform (Databricks + Fabric + Postgres)</li>
        <li><code>/governance</code> — auditoria de LGPD/PII, linhagem, RLS/OLS</li>
        <li><code>/sql</code>, <code>/spark</code>, <code>/pipeline</code> — SQL/Spark/pipelines direto pelo terminal ou chat</li>
        <li>Plugin Claude Code instalável em 1 comando — agentes e skills nativos no seu IDE</li>
      </ul>`,
    dev: `
      <p style="margin: 0 0 0.75rem; color: var(--md-default-fg-color--light); font-size: 0.9rem;">Stack e por onde começar:</p>
      <ul>
        <li>Python 3.11+ com Claude Agent SDK + Moonshot Kimi K2.6 via endpoint compat. Anthropic</li>
        <li>15 agentes declarativos em <code>data_agents/agents/registry/*.md</code> (frontmatter YAML)</li>
        <li>11 hooks de governança em <code>data_agents/hooks/</code> — Pre/PostToolUse interceptam tudo</li>
        <li>1.343 unit tests + 150 integration, cobertura 80%, CI verde</li>
        <li>Comece pela <a href="getting-started/">documentação Getting Started</a> ou pelo <a href="https://github.com/ThomazRossito/ai-data-agents/blob/main/CONTRIBUTING.md">CONTRIBUTING.md</a></li>
      </ul>`,
  };

  // ── Setup tabs ────────────────────────────────────────────────────────
  function setupPersonaTabs() {
    const tabs = document.querySelectorAll(".ada-persona-tab");
    const content = document.querySelector(".ada-persona-content");
    if (!tabs.length || !content) return;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => t.classList.remove("is-active"));
        tab.classList.add("is-active");
        const key = tab.dataset.persona;
        content.innerHTML = PERSONA_CONTENT[key] || "";
      });
    });
  }

  // ── Setup modal ───────────────────────────────────────────────────────
  function setupAgentModal() {
    const backdrop = document.getElementById("ada-modal");
    if (!backdrop) return;
    const titleEl = backdrop.querySelector(".ada-modal__title");
    const metaEl = backdrop.querySelector(".ada-modal__meta");
    const descEl = backdrop.querySelector(".ada-modal__desc");
    const mcpListEl = backdrop.querySelector('[data-list="mcps"]');
    const kbListEl = backdrop.querySelector('[data-list="kbs"]');
    const mcpSection = backdrop.querySelector('[data-section="mcps"]');
    const kbSection = backdrop.querySelector('[data-section="kbs"]');
    const closeEl = backdrop.querySelector(".ada-modal__close");

    function open(agentKey) {
      const data = AGENT_DATA[agentKey];
      if (!data) return;
      titleEl.textContent = data.label;
      metaEl.innerHTML = `
        <span class="ada-modal__chip">${data.tier}</span>
        <span class="ada-modal__chip">${data.model}</span>
        ${data.isNew ? '<span class="ada-modal__chip" style="background:#FAC775;color:#633806">Novo em v3.0.1</span>' : ""}
      `;
      descEl.textContent = data.description;

      if (data.mcps && data.mcps.length) {
        mcpSection.style.display = "";
        mcpListEl.innerHTML = data.mcps.map((m) => `<li>${m}</li>`).join("");
      } else {
        mcpSection.style.display = "none";
      }

      if (data.kbs && data.kbs.length) {
        kbSection.style.display = "";
        kbListEl.innerHTML = data.kbs.map((k) => `<li>${k}</li>`).join("");
      } else {
        kbSection.style.display = "none";
      }

      backdrop.classList.add("is-open");
    }

    function close() {
      backdrop.classList.remove("is-open");
    }

    document.querySelectorAll("[data-agent]").forEach((card) => {
      card.addEventListener("click", () => open(card.dataset.agent));
    });

    closeEl.addEventListener("click", close);
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
  }

  // ── Inicialização ─────────────────────────────────────────────────────
  function init() {
    setupPersonaTabs();
    setupAgentModal();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
