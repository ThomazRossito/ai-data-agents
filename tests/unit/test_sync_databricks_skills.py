"""
Testes offline de scripts/sync_databricks_skills.py (item 1.5 da Onda 1).

Tudo em diretórios temporários — o script nunca toca skills/databricks/ aqui.
A última classe olha o repositório REAL: o que está em skills/databricks/ tem
que bater com o UPSTREAM.json, e as custom têm que existir.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "sync_databricks_skills.py"


def _load():
    spec = importlib.util.spec_from_file_location("sync_databricks_skills", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_databricks_skills"] = mod
    spec.loader.exec_module(mod)
    return mod


sds = _load()

_REAL = _REPO / "skills" / "databricks"


def _snapshot_real() -> dict[str, int]:
    return {str(p.relative_to(_REAL)): p.stat().st_size for p in _REAL.rglob("*") if p.is_file()}


@pytest.fixture(autouse=True, scope="module")
def _o_diretorio_real_nao_pode_mudar():
    """Rede de segurança: se qualquer teste deste módulo tocar skills/databricks/
    REAL, o módulo inteiro falha aqui — antes de o estrago virar commit."""
    antes = _snapshot_real()
    yield
    assert _snapshot_real() == antes, "um teste escreveu em skills/databricks/ REAL"


def _skill(root: Path, nome: str, corpo: str = "# skill\n", extra: dict | None = None) -> Path:
    d = root / nome
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {nome}\n---\n{corpo}", encoding="utf-8")
    for rel, txt in (extra or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    return d


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """skills/databricks/ de brinquedo: 2 upstream antigas, 1 custom, TEMPLATE."""
    sk = tmp_path / "skills" / "databricks"
    _skill(sk, "databricks-bundles", "antigo")
    _skill(sk, "databricks-jobs", "v1")
    _skill(sk, "databricks-pricing", "custom!")  # está em CUSTOM
    (sk / "TEMPLATE").mkdir()
    (sk / "TEMPLATE" / "SKILL.md").write_text("template", encoding="utf-8")
    return sk


@pytest.fixture
def fonte(tmp_path: Path) -> Path:
    """Saída de `aitools install --path`: renome bundles→dabs, jobs mudou, nova skill."""
    f = tmp_path / "aitools"
    _skill(f, "databricks-dabs", "novo nome")
    _skill(f, "databricks-jobs", "v2", {"refs/x.md": "detalhe"})
    _skill(f, "databricks-core", "nova")
    (f / "databricks-jobs" / "__pycache__").mkdir()
    (f / "databricks-jobs" / "__pycache__" / "a.pyc").write_bytes(b"x")
    return f


class TestClassificar:
    def test_separa_as_tres_classes(self, repo: Path) -> None:
        c = sds.classificar(repo)
        assert c["upstream"] == ["databricks-bundles", "databricks-jobs"]
        assert c["custom"] == ["databricks-pricing"]
        assert c["scaffold"] == ["TEMPLATE"]

    def test_custom_bate_com_provenance(self) -> None:
        """A lista CUSTOM do script e a seção 2 do PROVENANCE.md são a mesma verdade."""
        prov = (_REPO / "skills/databricks/PROVENANCE.md").read_text(encoding="utf-8")
        for nome in sds.CUSTOM:
            assert f"`{nome}/`" in prov, f"{nome} está em CUSTOM mas não no PROVENANCE.md"


class TestDiff:
    def test_adicionar_remover_atualizar(self, repo: Path, fonte: Path) -> None:
        d = sds.diff(fonte, repo)
        assert d["adicionar"] == ["databricks-core", "databricks-dabs"]
        assert d["remover"] == ["databricks-bundles"]
        assert d["atualizar"] == ["databricks-jobs"]

    def test_custom_nunca_aparece_no_diff(self, repo: Path, fonte: Path) -> None:
        d = sds.diff(fonte, repo)
        assert "databricks-pricing" not in d["remover"], (
            "custom não está na fonte e MESMO ASSIM não pode ser removida"
        )

    def test_fonte_vazia_e_erro_claro(self, repo: Path, tmp_path: Path) -> None:
        with pytest.raises(sds.SyncError, match="aitools install"):
            sds.diff(tmp_path / "vazio", repo)

    def test_colisao_com_custom_bloqueia(self, repo: Path, tmp_path: Path) -> None:
        """Se a Databricks publicar uma skill chamada `pricing`, o sync PARA."""
        f = tmp_path / "f"
        _skill(f, "databricks-pricing", "homônima upstream")
        with pytest.raises(sds.SyncError, match="MESMO nome das custom"):
            sds.diff(f, repo)

    def test_pycache_nao_conta_como_mudanca(self, repo: Path, tmp_path: Path) -> None:
        f = tmp_path / "f"
        _skill(f, "databricks-jobs", "v1")
        (f / "databricks-jobs" / "__pycache__").mkdir()
        (f / "databricks-jobs" / "__pycache__" / "z.pyc").write_bytes(b"lixo")
        _skill(f, "databricks-bundles", "antigo")
        assert sds.diff(f, repo)["atualizar"] == []


class TestSync:
    def test_aplica_e_preserva_custom_e_template(self, repo: Path, fonte: Path) -> None:
        sds.sync(fonte, repo, versao="0.2.10")
        nomes = sorted(p.name for p in repo.iterdir())
        assert nomes == [
            "TEMPLATE",
            "UPSTREAM.json",
            "databricks-core",
            "databricks-dabs",
            "databricks-jobs",
            "databricks-pricing",
        ]
        assert (
            (repo / "databricks-pricing" / "SKILL.md")
            .read_text(encoding="utf-8")
            .endswith("custom!")
        )
        assert (repo / "databricks-jobs" / "refs" / "x.md").exists()
        assert not (repo / "databricks-jobs" / "__pycache__").exists(), "lixo não viaja"

    def test_manifest_e_a_fonte_de_verdade(self, repo: Path, fonte: Path) -> None:
        sds.sync(fonte, repo, versao="0.2.10")
        m = sds.ler_manifest(repo)
        assert m["versao_aitools"] == "0.2.10"
        assert m["upstream"] == ["databricks-core", "databricks-dabs", "databricks-jobs"]
        assert m["custom"] == sorted(sds.CUSTOM)
        assert m["sincronizado_em"].startswith("20")

    def test_idempotente(self, repo: Path, fonte: Path) -> None:
        sds.sync(fonte, repo, versao="0.2.10")
        d = sds.diff(fonte, repo)
        assert d == {"adicionar": [], "remover": [], "atualizar": []}

    def test_cli_check_exit_1_quando_diverge_e_0_quando_igual(
        self, repo: Path, fonte: Path, capsys
    ) -> None:
        """Via --skills-dir, NUNCA via monkeypatch do módulo: o default de parâmetro
        `skills_dir=SKILLS_DIR` é avaliado na definição da função e ignora o patch.
        Foi assim que, em 2026-09-22, este teste sobrescreveu skills/databricks/ real."""
        sd = ["--skills-dir", str(repo)]
        assert sds.main([str(fonte), "--check", *sd]) == 1
        assert sds.main([str(fonte), "--versao", "0.2.10", *sd]) == 0
        assert sds.main([str(fonte), "--check", *sd]) == 0
        out = capsys.readouterr().out
        assert "databricks-bundles" in out and "databricks-dabs" in out


class TestRepositorioReal:
    """O que está commitado em skills/databricks/ tem que ser coerente consigo mesmo."""

    SK = _REPO / "skills" / "databricks"

    def test_manifest_existe_e_lista_o_que_esta_no_disco(self) -> None:
        m = sds.ler_manifest(self.SK)
        assert m is not None, "UPSTREAM.json ausente — rode make refresh-databricks-skills"
        no_disco = set(sds.classificar(self.SK)["upstream"])
        assert no_disco == set(m["upstream"]), (
            f"disco ≠ manifest. só no disco: {sorted(no_disco - set(m['upstream']))}; "
            f"só no manifest: {sorted(set(m['upstream']) - no_disco)}"
        )

    def test_custom_existem(self) -> None:
        for nome in sds.CUSTOM:
            assert (self.SK / nome / "SKILL.md").is_file(), f"custom {nome} sumiu"

    def test_nomes_antigos_nao_existem_mais(self) -> None:
        for antigo in sds.RENOMES_CONHECIDOS:
            assert not (self.SK / antigo).exists(), f"{antigo} deveria ter sido renomeado"
        assert not (self.SK / "install_skills.sh").exists(), "instalador morto (404) foi removido"

    def test_versao_registrada(self) -> None:
        m = sds.ler_manifest(self.SK)
        assert m["versao_aitools"] not in ("", "desconhecida"), "passe --versao no sync"
