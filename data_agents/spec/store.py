"""
Persistência dos DOMA Specs — leitura, escrita e busca por identidade.

A DECISÃO CENTRAL: BUSCA POR CONTEÚDO, NÃO POR NOME
---------------------------------------------------
`find_by_id()` varre o corpo dos arquivos procurando `spec_id` no frontmatter.
Nunca deduz nada do nome do arquivo.

Isso parece rebuscado até olhar o que o `logs/audit.jsonl` deste projeto
registrou de verdade:

    26/jul 18:20   spec_ssas_comercial_brf.md
    26/jul 20:01   spec_ssas_brf_comercial.md     ← mesmo trabalho, palavras trocadas

    10/ago 01:41   spec_foundry_task_analyzer.md
    10/ago 15:34   foundry-ado-task-analyzer-spec.md   ← outra convenção inteira

Um índice por nome de arquivo perderia os dois casos. Um índice por `spec_id`
acha os dois, porque o id viaja dentro do documento. O nome do arquivo passa a
ser cosmético — existe `caminho_canonico()` para sugerir um bom nome, e o lint
avisa quando diverge, mas nada quebra se divergir.

A INTENÇÃO CONGELADA É UM GUARDRAIL, NÃO UM COMENTÁRIO
------------------------------------------------------
O bloco `<intencao-congelada>` pertence ao humano. `save()` compara o bloco
contra o que está em disco e **levanta** se um agente tentou alterá-lo sem
`por_humano=True`. Um bloco que diz "só o humano edita" e não é verificado é
exatamente o tipo de "texto mole" que o `migration_gate_hook` já documenta ter
visto o modelo atravessar.

ROUND-TRIP PRESERVA O DESCONHECIDO
-----------------------------------
Campos de frontmatter que este módulo não conhece são guardados em `extras` e
regravados. Sem isso, um `save()` apagaria silenciosamente qualquer campo que
os templates venham a adicionar.
"""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from data_agents.spec.state import (
    SpecStatus,
    TransicaoInvalida,
    Trilha,
    parse_status,
    parse_trilha,
    proxima_iteracao_revisao,
    validar_transicao,
)
from data_agents.utils.frontmatter import parse_yaml_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Onde o Supervisor grava specs (Step 0.9 do prompt).
SPECS_DIR = REPO_ROOT / "output" / "specs"

#: Campos que este módulo gerencia. O resto vai para `extras` e volta intacto.
_CAMPOS_CONHECIDOS = frozenset(
    {
        "spec_id",
        "titulo",
        "status",
        "trilha",
        "iteracao_revisao",
        "baseline_commit",
        "criado_em",
        "atualizado_em",
    }
)

_INTENCAO_RE = re.compile(
    r"<intencao-congelada>(.*?)</intencao-congelada>", re.DOTALL | re.IGNORECASE
)

_SLUG_INVALIDO_RE = re.compile(r"[^a-z0-9]+")


class SpecError(RuntimeError):
    """Falha de leitura, escrita ou identidade de spec."""


class SpecIdDuplicado(SpecError):
    """Dois arquivos declaram o mesmo `spec_id` — a identidade deixou de ser única."""


class IntencaoCongeladaViolada(SpecError):
    """Um agente tentou alterar o bloco que pertence ao humano."""


# ─── Modelo ──────────────────────────────────────────────────────────────────


@dataclass
class Spec:
    spec_id: str
    titulo: str
    status: SpecStatus = SpecStatus.RASCUNHO
    trilha: Trilha = Trilha.TAREFA
    iteracao_revisao: int = 0
    baseline_commit: str = ""
    criado_em: str = ""
    atualizado_em: str = ""
    corpo: str = ""
    caminho: Path | None = None
    #: Campos de frontmatter que este módulo não conhece — preservados no save.
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def intencao_congelada(self) -> str:
        """Conteúdo do bloco `<intencao-congelada>`, ou string vazia se não houver."""
        m = _INTENCAO_RE.search(self.corpo)
        return m.group(1).strip() if m else ""

    @property
    def e_final(self) -> bool:
        from data_agents.spec.state import ESTADOS_FINAIS

        return self.status in ESTADOS_FINAIS

    def to_frontmatter(self) -> dict[str, Any]:
        """Dicionário pronto para virar o bloco YAML. Extras primeiro-a-entrar, último-a-sair."""
        base: dict[str, Any] = {
            "spec_id": self.spec_id,
            "titulo": self.titulo,
            "status": self.status.value,
            "trilha": self.trilha.value,
            "iteracao_revisao": self.iteracao_revisao,
        }
        if self.baseline_commit:
            base["baseline_commit"] = self.baseline_commit
        base["criado_em"] = self.criado_em or _agora()
        base["atualizado_em"] = self.atualizado_em or _agora()
        base.update(self.extras)
        return base


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _agora() -> str:
    """Timestamp ISO-8601 UTC com segundos.

    Era `date.today().isoformat()` (só AAAA-MM-DD) até um teste de ordenação do
    `/resume` expor o furo: com granularidade de DIA, dois specs tocados na
    mesma data empatam — e "mesma data" é o caso comum, não a exceção. O
    `/resume` acabaria listando por ordem alfabética de arquivo em vez de por
    "o que mexi por último", que é a única ordem útil ali.

    Data pura continua sendo aceita na leitura (o campo é string livre e os
    templates trazem AAAA-MM-DD): "2026-09-14" ordena antes de qualquer
    timestamp do mesmo dia, que é o comportamento esperado para um valor
    preenchido à mão.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(texto: str) -> str:
    """Converte um título em `spec_id` kebab-case, sem acento.

    'Migração SSAS Comercial — BRF' → 'migracao-ssas-comercial-brf'
    """
    normalizado = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))
    slug = _SLUG_INVALIDO_RE.sub("-", sem_acento.lower()).strip("-")
    if not slug:
        raise SpecError(f"não foi possível derivar spec_id de {texto!r}")
    return slug


def caminho_canonico(spec_id: str, specs_dir: Path | None = None) -> Path:
    """Nome de arquivo sugerido: `spec_<spec_id>.md`.

    É sugestão, não lei — `find_by_id` acha o spec em qualquer nome. Existe
    para que arquivos novos nasçam consistentes, já que o histórico mostra o
    Supervisor alternando entre `spec_<nome>.md` e `<nome>-spec.md`.
    """
    return (specs_dir or SPECS_DIR) / f"spec_{spec_id}.md"


# ─── Leitura ─────────────────────────────────────────────────────────────────


def load(caminho: Path) -> Spec:
    """Lê um spec do disco. Levanta SpecError se o frontmatter for inválido."""
    try:
        conteudo = Path(caminho).read_text(encoding="utf-8")
    except OSError as e:
        raise SpecError(f"não foi possível ler {caminho}: {e}") from e

    try:
        meta, corpo = parse_yaml_frontmatter(conteudo)
    except ValueError as e:
        raise SpecError(f"{caminho}: {e}") from e

    spec_id = meta.get("spec_id")
    if not isinstance(spec_id, str) or not spec_id.strip():
        raise SpecError(
            f"{caminho}: frontmatter sem `spec_id` — sem identidade estável o spec "
            "não sobrevive a um rename, que é exatamente o que este módulo existe "
            "para evitar"
        )

    titulo = meta.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        raise SpecError(f"{caminho}: frontmatter sem `titulo`")

    try:
        status = parse_status(meta.get("status", SpecStatus.RASCUNHO.value))
        trilha = parse_trilha(meta.get("trilha", Trilha.TAREFA.value))
    except TransicaoInvalida as e:
        raise SpecError(f"{caminho}: {e}") from e

    iteracao = meta.get("iteracao_revisao", 0)
    if not isinstance(iteracao, int) or isinstance(iteracao, bool) or iteracao < 0:
        raise SpecError(f"{caminho}: `iteracao_revisao` deve ser inteiro >= 0, veio {iteracao!r}")

    return Spec(
        spec_id=spec_id.strip(),
        titulo=titulo.strip(),
        status=status,
        trilha=trilha,
        iteracao_revisao=iteracao,
        baseline_commit=str(meta.get("baseline_commit", "") or ""),
        criado_em=str(meta.get("criado_em", "") or ""),
        atualizado_em=str(meta.get("atualizado_em", "") or ""),
        corpo=corpo,
        caminho=Path(caminho),
        extras={k: v for k, v in meta.items() if k not in _CAMPOS_CONHECIDOS},
    )


def iter_specs(specs_dir: Path | None = None) -> list[Spec]:
    """Todos os specs legíveis sob `specs_dir`. Arquivos inválidos são pulados.

    Pular o inválido é deliberado: um spec quebrado não pode impedir o
    Supervisor de achar os outros 20. O `lint_specs()` é quem reporta.
    """
    raiz = specs_dir or SPECS_DIR
    if not raiz.is_dir():
        return []
    achados: list[Spec] = []
    for caminho in sorted(raiz.rglob("*.md")):
        try:
            achados.append(load(caminho))
        except SpecError:
            continue
    return achados


def find_by_id(spec_id: str, specs_dir: Path | None = None) -> Spec | None:
    """Acha um spec pelo `spec_id` do frontmatter, independente do nome do arquivo.

    Raises:
        SpecIdDuplicado: se dois arquivos declararem o mesmo id.
    """
    alvo = spec_id.strip().lower()
    achados = [s for s in iter_specs(specs_dir) if s.spec_id.lower() == alvo]
    if not achados:
        return None
    if len(achados) > 1:
        caminhos = ", ".join(str(s.caminho) for s in achados)
        raise SpecIdDuplicado(
            f"spec_id {spec_id!r} aparece em mais de um arquivo: {caminhos} — "
            "renomeie o id de um deles; identidade duplicada quebra o roteamento por status"
        )
    return achados[0]


def specs_abertos(specs_dir: Path | None = None) -> list[Spec]:
    """Specs que ainda pedem trabalho — o que o `/resume` deve oferecer.

    Exclui `concluido` e `cancelado`. Sem o estado `cancelado` no enum, um spec
    abandonado apareceria aqui para sempre.
    """
    return [s for s in iter_specs(specs_dir) if not s.e_final]


# ─── Escrita ─────────────────────────────────────────────────────────────────


def _render(spec: Spec) -> str:
    bloco = yaml.safe_dump(
        spec.to_frontmatter(), sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    corpo = spec.corpo.strip("\n")
    return f"---\n{bloco}\n---\n\n{corpo}\n"


def save(spec: Spec, *, por_humano: bool = False, specs_dir: Path | None = None) -> Path:
    """Grava o spec. Escrita atômica.

    Args:
        spec: o spec a gravar. Usa `spec.caminho`, ou o canônico se for None.
        por_humano: libera alteração do bloco `<intencao-congelada>`.
        specs_dir: raiz alternativa (testes).

    Raises:
        IntencaoCongeladaViolada: agente tentou mexer no bloco do humano.
    """
    destino = spec.caminho or caminho_canonico(spec.spec_id, specs_dir)
    destino = Path(destino)

    if destino.is_file() and not por_humano:
        try:
            anterior = load(destino)
        except SpecError:
            anterior = None
        if anterior is not None and anterior.intencao_congelada != spec.intencao_congelada:
            raise IntencaoCongeladaViolada(
                f"{destino.name}: o bloco <intencao-congelada> mudou, e ele pertence ao "
                "humano. Se a intenção realmente mudou, quem edita é a pessoa — o agente "
                "trabalha dentro da intenção, não a reescreve."
            )

    spec.atualizado_em = _agora()
    if not spec.criado_em:
        spec.criado_em = spec.atualizado_em

    destino.parent.mkdir(parents=True, exist_ok=True)
    conteudo = _render(spec)

    # Atômica: escreve ao lado e troca. Crash no meio não corrompe o spec
    # existente — que pode carregar horas de investigação.
    fd, tmp = tempfile.mkstemp(dir=str(destino.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(conteudo)
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    spec.caminho = destino
    return destino


def criar(
    titulo: str,
    *,
    trilha: Trilha = Trilha.TAREFA,
    corpo: str = "",
    baseline_commit: str = "",
    spec_id: str | None = None,
    specs_dir: Path | None = None,
) -> Spec:
    """Cria um spec novo em `rascunho` e grava. Levanta se o id já existir."""
    ident = (spec_id or slugify(titulo)).strip().lower()
    if find_by_id(ident, specs_dir) is not None:
        raise SpecIdDuplicado(
            f"já existe spec com id {ident!r} — use `find_by_id` e continue o trabalho "
            "em vez de criar outro (regenerar do zero é o desperdício que este módulo evita)"
        )
    spec = Spec(
        spec_id=ident,
        titulo=titulo.strip(),
        status=SpecStatus.RASCUNHO,
        trilha=trilha,
        baseline_commit=baseline_commit,
        corpo=corpo,
        caminho=caminho_canonico(ident, specs_dir),
    )
    save(spec, por_humano=True, specs_dir=specs_dir)
    return spec


def transicionar(
    spec: Spec,
    novo_status: SpecStatus,
    *,
    por_humano: bool = False,
    specs_dir: Path | None = None,
) -> Spec:
    """Valida a transição, atualiza status + contador de revisão, e grava.

    Toda mudança de status do sistema passa por aqui — é o único ponto em que
    `validar_transicao` é chamado antes de tocar o disco.
    """
    validar_transicao(
        spec.status,
        novo_status,
        trilha=spec.trilha,
        iteracao_revisao=spec.iteracao_revisao,
        por_humano=por_humano,
    )
    spec.iteracao_revisao = proxima_iteracao_revisao(
        spec.status, novo_status, spec.iteracao_revisao
    )
    spec.status = novo_status
    save(spec, por_humano=por_humano, specs_dir=specs_dir)
    return spec
