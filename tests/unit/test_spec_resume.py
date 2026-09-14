"""
Testes da integração spec ↔ /resume (Onda 2.1).

Duas garantias, e a segunda é a que me preocupa mais:

  1. Havendo spec aberto, o `/resume` entrega o estado autoritativo e encolhe o
     orçamento de transcript.

  2. **Nada disso pode quebrar o `/resume`.** Um spec malformado, um módulo que
     não importa, um diretório sem permissão — qualquer um desses tem que
     degradar para o comportamento antigo, não estourar. Retomada é justamente
     o momento em que o usuário está tentando recuperar trabalho; falhar ali é
     falhar duas vezes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from data_agents.commands.sessions import (
    _RESUME_MAX_TURNS,
    _RESUME_MAX_TURNS_COM_SPEC,
    build_resume_prompt_for_session,
    build_spec_context,
)
from data_agents.spec.state import SpecStatus, Trilha
from data_agents.spec.store import criar, transicionar


@pytest.fixture
def specs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "specs"
    d.mkdir()
    return d


class TestBlocoDeSpec:
    def test_vazio_sem_specs(self, specs_dir: Path) -> None:
        assert build_spec_context(specs_dir) == ""

    def test_vazio_quando_diretorio_nem_existe(self, tmp_path: Path) -> None:
        assert build_spec_context(tmp_path / "nao-existe") == ""

    def test_lista_spec_aberto_com_status(self, specs_dir: Path) -> None:
        spec = criar("Migração BRF", trilha=Trilha.PLATAFORMA, specs_dir=specs_dir)
        transicionar(spec, SpecStatus.INVESTIGADO, specs_dir=specs_dir)

        bloco = build_spec_context(specs_dir)
        assert "migracao-brf" in bloco
        assert "investigado" in bloco
        assert "plataforma" in bloco

    def test_omite_concluido_e_cancelado(self, specs_dir: Path) -> None:
        vivo = criar("Ainda Vivo", specs_dir=specs_dir)
        transicionar(vivo, SpecStatus.INVESTIGADO, specs_dir=specs_dir)

        morto = criar("Abandonado", specs_dir=specs_dir)
        transicionar(morto, SpecStatus.CANCELADO, por_humano=True, specs_dir=specs_dir)

        pronto = criar("Entregue", trilha=Trilha.DIRETA, specs_dir=specs_dir)
        for destino in (SpecStatus.INVESTIGADO, SpecStatus.PRONTO, SpecStatus.EM_EXECUCAO):
            transicionar(pronto, destino, specs_dir=specs_dir)
        transicionar(pronto, SpecStatus.CONCLUIDO, specs_dir=specs_dir)

        bloco = build_spec_context(specs_dir)
        assert "ainda-vivo" in bloco
        assert "abandonado" not in bloco, (
            "spec cancelado apareceu na retomada — era exatamente o motivo de "
            "acrescentar o estado `cancelado` ao enum"
        )
        assert "entregue" not in bloco

    def test_instrui_a_continuar_e_nao_recomecar(self, specs_dir: Path) -> None:
        criar("Qualquer", specs_dir=specs_dir)
        bloco = build_spec_context(specs_dir)
        assert "não recomece" in bloco.lower()
        assert "spec_id" in bloco
        assert "intencao-congelada" in bloco

    def test_mais_recente_primeiro(self, specs_dir: Path) -> None:
        """Ordem por `atualizado_em`, o único critério útil numa retomada.

        A primeira versão deste teste falhou e o erro era do código, não do
        teste: `atualizado_em` guardava só AAAA-MM-DD, então dois specs tocados
        no mesmo dia empatavam e a listagem caía em ordem alfabética de arquivo.
        "Mesmo dia" é o caso comum. `store._agora()` passou a gravar timestamp
        ISO com segundos por causa disto.
        """
        import time

        criar("Antigo", specs_dir=specs_dir)
        time.sleep(1.05)  # o timestamp tem resolução de segundos
        criar("Novo", specs_dir=specs_dir)

        bloco = build_spec_context(specs_dir)
        assert bloco.index("`novo`") < bloco.index("`antigo`"), (
            "specs criados no mesmo dia não ordenaram por horário — "
            "`atualizado_em` voltou a ter granularidade de dia?"
        )

    def test_atualizado_em_tem_resolucao_de_segundos(self, specs_dir: Path) -> None:
        """Guarda direta contra a regressão: data pura não basta."""
        spec = criar("Com Timestamp", specs_dir=specs_dir)
        assert "T" in spec.atualizado_em and ":" in spec.atualizado_em, (
            f"atualizado_em={spec.atualizado_em!r} parece só uma data — "
            "dois specs do mesmo dia voltariam a empatar na ordenação"
        )


class TestNuncaQuebraOResume:
    """O /resume tem que sobreviver a qualquer problema no módulo de spec."""

    def test_spec_malformado_nao_estoura(self, specs_dir: Path) -> None:
        (specs_dir / "lixo.md").write_text("isto não é frontmatter", encoding="utf-8")
        (specs_dir / "meio-quebrado.md").write_text(
            "---\nspec_id: [isto, e, uma, lista]\n---\ncorpo\n", encoding="utf-8"
        )
        assert build_spec_context(specs_dir) == ""  # não levanta

    def test_spec_bom_sobrevive_ao_lado_de_spec_quebrado(self, specs_dir: Path) -> None:
        (specs_dir / "lixo.md").write_text("sem frontmatter", encoding="utf-8")
        criar("Bom Spec", specs_dir=specs_dir)
        bloco = build_spec_context(specs_dir)
        assert "bom-spec" in bloco

    def test_erro_inesperado_degrada_para_vazio(self, specs_dir: Path) -> None:
        with patch(
            "data_agents.spec.store.specs_abertos", side_effect=RuntimeError("disco pegou fogo")
        ):
            assert build_spec_context(specs_dir) == ""


class TestOrcamentoDeTranscript:
    def _patch_transcript(self, retorno: str):
        return patch(
            "data_agents.commands.sessions.build_resume_prompt_from_transcript",
            return_value=retorno,
        )

    def test_sem_spec_mantem_orcamento_cheio(self, specs_dir: Path) -> None:
        with patch("data_agents.commands.sessions.build_spec_context", return_value=""):
            with self._patch_transcript("TRANSCRIPT") as mock:
                build_resume_prompt_for_session("s1")
                assert mock.call_args.kwargs["max_turns"] == _RESUME_MAX_TURNS

    def test_com_spec_encolhe_o_orcamento(self) -> None:
        with patch("data_agents.commands.sessions.build_spec_context", return_value="SPEC\n"):
            with self._patch_transcript("TRANSCRIPT") as mock:
                build_resume_prompt_for_session("s1")
                assert mock.call_args.kwargs["max_turns"] == _RESUME_MAX_TURNS_COM_SPEC, (
                    "com o estado vindo do frontmatter, reler 30 turns é gastar "
                    "~15k tokens para deduzir o que o spec já afirma"
                )

    def test_chamador_com_orcamento_menor_e_respeitado(self) -> None:
        """Encolher é teto, não imposição — quem pediu 3 turns recebe 3."""
        with patch("data_agents.commands.sessions.build_spec_context", return_value="SPEC\n"):
            with self._patch_transcript("TRANSCRIPT") as mock:
                build_resume_prompt_for_session("s1", max_turns=3)
                assert mock.call_args.kwargs["max_turns"] == 3

    def test_spec_vem_antes_do_transcript(self) -> None:
        with patch("data_agents.commands.sessions.build_spec_context", return_value="SPEC\n"):
            with self._patch_transcript("TRANSCRIPT"):
                prompt = build_resume_prompt_for_session("s1")
        assert prompt.startswith("SPEC\n"), "o estado tem que chegar antes do contexto"
        assert "TRANSCRIPT" in prompt


class TestPrecedencia:
    def test_sem_transcript_usa_checkpoint_com_o_spec_junto(self) -> None:
        with patch("data_agents.commands.sessions.build_spec_context", return_value="SPEC\n"):
            with patch(
                "data_agents.commands.sessions.build_resume_prompt_from_transcript",
                return_value="",
            ):
                with patch(
                    "data_agents.commands.sessions.load_session_by_id", return_value={"x": 1}
                ):
                    with patch(
                        "data_agents.commands.sessions.build_resume_prompt",
                        return_value="CHECKPOINT",
                    ):
                        prompt = build_resume_prompt_for_session("s1")
        assert prompt == "SPEC\nCHECKPOINT"

    def test_so_spec_ainda_permite_retomar(self) -> None:
        """Sessão sem rastro, mas com spec aberto: o spec sozinho basta."""
        with patch("data_agents.commands.sessions.build_spec_context", return_value="SPEC\n"):
            with patch(
                "data_agents.commands.sessions.build_resume_prompt_from_transcript",
                return_value="",
            ):
                with patch("data_agents.commands.sessions.load_session_by_id", return_value=None):
                    assert build_resume_prompt_for_session("s1") == "SPEC\n"

    def test_sem_nada_devolve_none(self) -> None:
        """Comportamento antigo preservado quando não há spec nenhum."""
        with patch("data_agents.commands.sessions.build_spec_context", return_value=""):
            with patch(
                "data_agents.commands.sessions.build_resume_prompt_from_transcript",
                return_value="",
            ):
                with patch("data_agents.commands.sessions.load_session_by_id", return_value=None):
                    assert build_resume_prompt_for_session("s1") is None
