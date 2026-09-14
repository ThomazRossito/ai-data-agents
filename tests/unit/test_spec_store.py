"""
Testes de `data_agents/spec/store.py`.

O teste que define o módulo é `TestSobreviveAoRename` — ele reproduz o caso
real do `logs/audit.jsonl` (`spec_ssas_comercial_brf.md` renomeado para
`spec_ssas_brf_comercial.md`) e exige que a busca continue achando. Se ele
falhar, o `/resume` volta a perder trabalho aprovado.

Tudo roda em `tmp_path`: nenhum teste toca `output/specs/` do repositório.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_agents.spec.state import SpecStatus, TransicaoInvalida, Trilha
from data_agents.spec.store import (
    IntencaoCongeladaViolada,
    Spec,
    SpecError,
    SpecIdDuplicado,
    caminho_canonico,
    criar,
    find_by_id,
    iter_specs,
    load,
    save,
    slugify,
    specs_abertos,
    transicionar,
)


@pytest.fixture
def specs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "specs"
    d.mkdir()
    return d


def _escrever(specs_dir: Path, nome: str, frontmatter: str, corpo: str = "Conteúdo.") -> Path:
    caminho = specs_dir / nome
    caminho.write_text(f"---\n{frontmatter.strip()}\n---\n\n{corpo}\n", encoding="utf-8")
    return caminho


# ─── slugify / caminho canônico ──────────────────────────────────────────────


class TestSlugify:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("Migração SSAS Comercial BRF", "migracao-ssas-comercial-brf"),
            ("  Pipeline   Bronze→Silver  ", "pipeline-bronze-silver"),
            ("Teradata → Databricks (fase 1)", "teradata-databricks-fase-1"),
            ("ONTOLOGIA_OWL", "ontologia-owl"),
        ],
    )
    def test_normaliza(self, entrada: str, esperado: str) -> None:
        assert slugify(entrada) == esperado

    def test_titulo_sem_alfanumerico_levanta(self) -> None:
        with pytest.raises(SpecError, match="spec_id"):
            slugify("—— ///")

    def test_caminho_canonico(self, specs_dir: Path) -> None:
        assert caminho_canonico("abc-def", specs_dir).name == "spec_abc-def.md"


# ─── Leitura ─────────────────────────────────────────────────────────────────


class TestLoad:
    def test_le_campos_e_corpo(self, specs_dir: Path) -> None:
        p = _escrever(
            specs_dir,
            "qualquer-nome.md",
            """
spec_id: migracao-brf
titulo: Migração BRF
status: em-execucao
trilha: plataforma
iteracao_revisao: 2
baseline_commit: abc1234
""",
            corpo="## Escopo\nTexto.",
        )
        spec = load(p)
        assert spec.spec_id == "migracao-brf"
        assert spec.status is SpecStatus.EM_EXECUCAO
        assert spec.trilha is Trilha.PLATAFORMA
        assert spec.iteracao_revisao == 2
        assert spec.baseline_commit == "abc1234"
        assert "## Escopo" in spec.corpo

    def test_sem_spec_id_levanta_com_o_porque(self, specs_dir: Path) -> None:
        p = _escrever(specs_dir, "x.md", "titulo: Sem id")
        with pytest.raises(SpecError, match="rename"):
            load(p)

    def test_sem_titulo_levanta(self, specs_dir: Path) -> None:
        p = _escrever(specs_dir, "x.md", "spec_id: abc")
        with pytest.raises(SpecError, match="titulo"):
            load(p)

    def test_status_desconhecido_levanta(self, specs_dir: Path) -> None:
        p = _escrever(specs_dir, "x.md", "spec_id: a\ntitulo: T\nstatus: quase-pronto")
        with pytest.raises(SpecError, match="quase-pronto"):
            load(p)

    @pytest.mark.parametrize("valor", ["-1", "'dois'", "true"])
    def test_iteracao_invalida_levanta(self, specs_dir: Path, valor: str) -> None:
        p = _escrever(specs_dir, "x.md", f"spec_id: a\ntitulo: T\niteracao_revisao: {valor}")
        with pytest.raises(SpecError, match="iteracao_revisao"):
            load(p)

    def test_defaults_quando_omitido(self, specs_dir: Path) -> None:
        p = _escrever(specs_dir, "x.md", "spec_id: a\ntitulo: T")
        spec = load(p)
        assert spec.status is SpecStatus.RASCUNHO
        assert spec.trilha is Trilha.TAREFA
        assert spec.iteracao_revisao == 0

    def test_sem_frontmatter_levanta(self, specs_dir: Path) -> None:
        p = specs_dir / "solto.md"
        p.write_text("# Só markdown\n", encoding="utf-8")
        with pytest.raises(SpecError):
            load(p)


# ─── Identidade resistente a rename ──────────────────────────────────────────


class TestSobreviveAoRename:
    """Reproduz o caso real de 26/jul/2026 registrado no audit log."""

    def test_acha_apos_rename(self, specs_dir: Path) -> None:
        _escrever(
            specs_dir,
            "spec_ssas_brf_comercial.md",  # nome NOVO, pós-rename
            "spec_id: ssas-comercial-brf\ntitulo: SSAS Comercial BRF\nstatus: pronto",
        )
        achado = find_by_id("ssas-comercial-brf", specs_dir)
        assert achado is not None, (
            "a busca falhou depois de um rename — é exatamente a regressão que "
            "fez o Supervisor regenerar o spec do zero em 26/jul"
        )
        assert achado.status is SpecStatus.PRONTO

    def test_acha_com_outra_convencao_de_nome(self, specs_dir: Path) -> None:
        """10/ago: spec_foundry_task_analyzer.md → foundry-ado-task-analyzer-spec.md"""
        _escrever(
            specs_dir,
            "foundry-ado-task-analyzer-spec.md",
            "spec_id: foundry-task-analyzer\ntitulo: Foundry Task Analyzer",
        )
        assert find_by_id("foundry-task-analyzer", specs_dir) is not None

    def test_acha_em_subdiretorio(self, specs_dir: Path) -> None:
        sub = specs_dir / "arquivados"
        sub.mkdir()
        _escrever(sub, "zzz.md", "spec_id: antigo\ntitulo: Antigo")
        assert find_by_id("antigo", specs_dir) is not None

    def test_busca_e_case_insensitive(self, specs_dir: Path) -> None:
        _escrever(specs_dir, "a.md", "spec_id: meu-spec\ntitulo: T")
        assert find_by_id("MEU-SPEC", specs_dir) is not None

    def test_inexistente_retorna_none(self, specs_dir: Path) -> None:
        assert find_by_id("nao-existe", specs_dir) is None

    def test_id_duplicado_levanta_em_vez_de_escolher(self, specs_dir: Path) -> None:
        """Escolher um dos dois em silêncio seria pior que falhar."""
        _escrever(specs_dir, "a.md", "spec_id: dup\ntitulo: A")
        _escrever(specs_dir, "b.md", "spec_id: dup\ntitulo: B")
        with pytest.raises(SpecIdDuplicado, match="mais de um arquivo"):
            find_by_id("dup", specs_dir)

    def test_arquivo_quebrado_nao_impede_achar_os_outros(self, specs_dir: Path) -> None:
        (specs_dir / "quebrado.md").write_text("sem frontmatter", encoding="utf-8")
        _escrever(specs_dir, "bom.md", "spec_id: bom\ntitulo: Bom")
        assert find_by_id("bom", specs_dir) is not None
        assert len(iter_specs(specs_dir)) == 1

    def test_diretorio_inexistente_devolve_vazio(self, tmp_path: Path) -> None:
        assert iter_specs(tmp_path / "nao-existe") == []


# ─── Escrita e round-trip ────────────────────────────────────────────────────


class TestSave:
    def test_round_trip_preserva_tudo(self, specs_dir: Path) -> None:
        spec = criar("Pipeline Vendas", trilha=Trilha.PIPELINE, specs_dir=specs_dir)
        spec.corpo = "## Escopo\nBronze → Silver → Gold."
        save(spec, por_humano=True, specs_dir=specs_dir)

        relido = load(spec.caminho)
        assert relido.spec_id == spec.spec_id
        assert relido.trilha is Trilha.PIPELINE
        assert "Bronze → Silver → Gold." in relido.corpo

    def test_campos_desconhecidos_sobrevivem(self, specs_dir: Path) -> None:
        """Um save não pode apagar campo que os templates venham a adicionar."""
        p = _escrever(
            specs_dir,
            "x.md",
            "spec_id: a\ntitulo: T\ncampo_futuro: valor\nlista_futura: [1, 2]",
        )
        spec = load(p)
        save(spec, por_humano=True, specs_dir=specs_dir)
        relido = load(p)
        assert relido.extras["campo_futuro"] == "valor"
        assert relido.extras["lista_futura"] == [1, 2]

    def test_atualiza_timestamp(self, specs_dir: Path) -> None:
        spec = criar("Teste", specs_dir=specs_dir)
        assert spec.atualizado_em
        assert spec.criado_em == spec.atualizado_em

    def test_criar_recusa_id_ja_existente(self, specs_dir: Path) -> None:
        criar("Mesma Coisa", specs_dir=specs_dir)
        with pytest.raises(SpecIdDuplicado, match="continue o trabalho"):
            criar("Mesma Coisa", specs_dir=specs_dir)

    def test_escrita_e_atomica_sem_deixar_tmp(self, specs_dir: Path) -> None:
        spec = criar("Atômico", specs_dir=specs_dir)
        save(spec, por_humano=True, specs_dir=specs_dir)
        sobras = list(specs_dir.glob("*.tmp"))
        assert not sobras, f"arquivos temporários vazados: {sobras}"


class TestIntencaoCongelada:
    _CORPO = "<intencao-congelada>\nMigrar sem perder linhagem.\n</intencao-congelada>\n\nResto."

    def test_extrai_o_bloco(self, specs_dir: Path) -> None:
        spec = criar("Com Intenção", corpo=self._CORPO, specs_dir=specs_dir)
        assert spec.intencao_congelada == "Migrar sem perder linhagem."

    def test_agente_nao_altera_o_bloco(self, specs_dir: Path) -> None:
        spec = criar("Com Intenção", corpo=self._CORPO, specs_dir=specs_dir)
        spec.corpo = spec.corpo.replace("sem perder linhagem", "do jeito que der")
        with pytest.raises(IntencaoCongeladaViolada, match="pertence ao humano"):
            save(spec, specs_dir=specs_dir)

    def test_humano_altera_o_bloco(self, specs_dir: Path) -> None:
        spec = criar("Com Intenção", corpo=self._CORPO, specs_dir=specs_dir)
        spec.corpo = spec.corpo.replace("sem perder linhagem", "com nova prioridade")
        save(spec, por_humano=True, specs_dir=specs_dir)
        assert load(spec.caminho).intencao_congelada == "Migrar com nova prioridade."

    def test_agente_pode_editar_o_resto_do_corpo(self, specs_dir: Path) -> None:
        """O guardrail protege a intenção, não congela o documento inteiro."""
        spec = criar("Com Intenção", corpo=self._CORPO, specs_dir=specs_dir)
        spec.corpo = spec.corpo.replace("Resto.", "Resto, agora com a análise preenchida.")
        save(spec, specs_dir=specs_dir)  # não deve levantar
        assert "análise preenchida" in load(spec.caminho).corpo

    def test_sem_bloco_nao_atrapalha(self, specs_dir: Path) -> None:
        spec = criar("Sem Intenção", corpo="Só texto.", specs_dir=specs_dir)
        spec.corpo = "Texto editado."
        save(spec, specs_dir=specs_dir)
        assert spec.intencao_congelada == ""


# ─── Transições sobre o disco ────────────────────────────────────────────────


class TestTransicionar:
    def test_percurso_completo_persiste(self, specs_dir: Path) -> None:
        spec = criar("Pipeline X", trilha=Trilha.PIPELINE, specs_dir=specs_dir)
        for destino in (
            SpecStatus.INVESTIGADO,
            SpecStatus.PRONTO,
            SpecStatus.EM_EXECUCAO,
            SpecStatus.EM_REVISAO,
            SpecStatus.CONCLUIDO,
        ):
            transicionar(spec, destino, specs_dir=specs_dir)
        assert load(spec.caminho).status is SpecStatus.CONCLUIDO

    def test_transicao_ilegal_nao_toca_o_disco(self, specs_dir: Path) -> None:
        spec = criar("Teste", specs_dir=specs_dir)
        antes = spec.caminho.read_text(encoding="utf-8")
        with pytest.raises(TransicaoInvalida):
            transicionar(spec, SpecStatus.CONCLUIDO, specs_dir=specs_dir)
        assert spec.caminho.read_text(encoding="utf-8") == antes, (
            "a validação tem que acontecer ANTES da escrita"
        )

    def test_volta_da_revisao_incrementa_e_persiste(self, specs_dir: Path) -> None:
        spec = criar("Pipeline Y", trilha=Trilha.PIPELINE, specs_dir=specs_dir)
        for destino in (SpecStatus.INVESTIGADO, SpecStatus.PRONTO, SpecStatus.EM_EXECUCAO):
            transicionar(spec, destino, specs_dir=specs_dir)
        transicionar(spec, SpecStatus.EM_REVISAO, specs_dir=specs_dir)
        transicionar(spec, SpecStatus.EM_EXECUCAO, specs_dir=specs_dir)
        assert load(spec.caminho).iteracao_revisao == 1

    def test_cancelar_exige_humano(self, specs_dir: Path) -> None:
        spec = criar("Abandonado", specs_dir=specs_dir)
        with pytest.raises(TransicaoInvalida, match="ação humana"):
            transicionar(spec, SpecStatus.CANCELADO, specs_dir=specs_dir)
        transicionar(spec, SpecStatus.CANCELADO, por_humano=True, specs_dir=specs_dir)
        assert load(spec.caminho).status is SpecStatus.CANCELADO


class TestSpecsAbertos:
    def test_exclui_finais(self, specs_dir: Path) -> None:
        _escrever(specs_dir, "a.md", "spec_id: vivo\ntitulo: A\nstatus: em-execucao")
        _escrever(specs_dir, "b.md", "spec_id: pronto\ntitulo: B\nstatus: concluido")
        _escrever(specs_dir, "c.md", "spec_id: morto\ntitulo: C\nstatus: cancelado")

        abertos = {s.spec_id for s in specs_abertos(specs_dir)}
        assert abertos == {"vivo"}, (
            "cancelado tem que sumir daqui — era o motivo de acrescentar o estado: "
            "sem ele, spec abandonado ficaria preso em em-execucao e o /resume "
            "ofereceria retomar trabalho morto"
        )

    def test_spec_novo_conta_como_aberto(self, specs_dir: Path) -> None:
        criar("Novinho", specs_dir=specs_dir)
        assert len(specs_abertos(specs_dir)) == 1


def test_dataclass_aceita_construcao_direta() -> None:
    """Spec é usável sem disco — importa para os testes do Supervisor."""
    s = Spec(spec_id="x", titulo="X")
    assert s.status is SpecStatus.RASCUNHO
    assert not s.e_final
