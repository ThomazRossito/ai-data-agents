"""
Testes unitários para mcp_servers/fabric_semantic/server.py.

Cobre:
  - _build_measure_tmdl_block: sintaxe TMDL correta (inline, multi-linha, props, lineageTag)
  - _inject_measures_into_tmdl: insert de nova medida, update de existente, posição relativa à partition
  - _parse_tmdl_text_table: round-trip parse de TMDL de tabela com medidas e colunas
  - fabric_semantic_update_definition: fluxo completo com HTTP mockado, incluindo bloqueio
    por erro de sintaxe DAX na validação pré-publicação
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch


from mcp_servers.fabric_semantic.server import (
    _build_measure_tmdl_block,
    _inject_measures_into_tmdl,
    _parse_tmdl_text_table,
    fabric_semantic_update_definition,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

SAMPLE_TMDL_TABLE = """\
table vw_monitoramento_powerbi
\tlineageTag: aaaa-bbbb

\tcolumn workspace_id
\t\tdataType: string
\t\tlineageTag: cccc-dddd

\tmeasure 'Total Atualizações' = COUNTROWS(vw_monitoramento_powerbi)
\t\tformatString: "#,0"
\t\tlineageTag: eeee-ffff

\tpartition vw_monitoramento_powerbi-partition = entity
\t\tmode: directLake
\t\tentityName: 'vw_monitoramento_powerbi'
"""

FIXED_UUID = "00000000-0000-0000-0000-000000000001"


# ─── _build_measure_tmdl_block ───────────────────────────────────────────────


class TestBuildMeasureTmdlBlock:
    def test_inline_expression(self):
        block = _build_measure_tmdl_block(
            {"name": "Total Vendas", "expression": "SUM(fato[valor])"}
        )
        assert block.startswith("\tmeasure 'Total Vendas' = SUM(fato[valor])")

    def test_multiline_expression_uses_triple_tab(self):
        expr = "DIVIDE(\n    SUM(fato[valor]),\n    COUNT(fato[id])\n)"
        block = _build_measure_tmdl_block({"name": "Ticket Médio", "expression": expr})
        lines = block.splitlines()
        assert lines[0] == "\tmeasure 'Ticket Médio' ="
        # Corpo da expressão começa com 3 tabs
        assert all(line.startswith("\t\t\t") for line in [lines[1], lines[2], lines[3]])

    def test_long_inline_becomes_multiline(self):
        long_expr = "CALCULATE(SUM(fato[valor]), FILTER(dim_data, dim_data[ano] = YEAR(TODAY())), ALL(dim_cliente))"
        assert len(long_expr) > 80
        block = _build_measure_tmdl_block({"name": "Vendas Ano Atual", "expression": long_expr})
        assert "\tmeasure 'Vendas Ano Atual' =" in block

    def test_format_string_uses_double_quotes(self):
        block = _build_measure_tmdl_block(
            {"name": "Tx Sucesso", "expression": "0.5", "format_string": "0.00%"}
        )
        assert '\t\tformatString: "0.00%"' in block

    def test_description_included(self):
        block = _build_measure_tmdl_block(
            {"name": "M1", "expression": "1", "description": "Minha medida"}
        )
        assert '\t\tdescription: "Minha medida"' in block

    def test_display_folder_included(self):
        block = _build_measure_tmdl_block(
            {"name": "M1", "expression": "1", "display_folder": "KPIs"}
        )
        assert '\t\tdisplayFolder: "KPIs"' in block

    def test_lineage_tag_always_present(self):
        block = _build_measure_tmdl_block({"name": "M1", "expression": "1"})
        assert "\t\tlineageTag:" in block

    def test_lineage_tag_uses_provided_value(self):
        block = _build_measure_tmdl_block(
            {"name": "M1", "expression": "1", "lineage_tag": FIXED_UUID}
        )
        assert f"\t\tlineageTag: {FIXED_UUID}" in block

    def test_lineage_tag_auto_generated_is_valid_uuid(self):
        import re
        import uuid

        block = _build_measure_tmdl_block({"name": "M1", "expression": "1"})
        match = re.search(r"\t\tlineageTag: (.+)", block)
        assert match, "lineageTag não encontrado"
        uuid.UUID(match.group(1))  # lança ValueError se inválido

    def test_properties_order_format_before_lineage(self):
        block = _build_measure_tmdl_block({"name": "M1", "expression": "1", "format_string": "#,0"})
        fmt_pos = block.index("formatString")
        ltag_pos = block.index("lineageTag")
        assert fmt_pos < ltag_pos


# ─── _inject_measures_into_tmdl ──────────────────────────────────────────────


class TestInjectMeasuresIntoTmdl:
    def test_insert_new_measure_before_partition(self):
        # Retorno: (tmdl, updated_names, inserted_names)
        result, updated, inserted = _inject_measures_into_tmdl(
            SAMPLE_TMDL_TABLE,
            [{"name": "Total Falhas", "expression": 'COUNTROWS(FILTER(t, t[status]="Falha"))'}],
        )
        assert "Total Falhas" in inserted
        assert "Total Falhas" not in updated
        # Medida nova deve aparecer antes da partition
        assert result.index("Total Falhas") < result.index("\tpartition ")

    def test_update_existing_measure(self):
        result, updated, inserted = _inject_measures_into_tmdl(
            SAMPLE_TMDL_TABLE,
            [
                {
                    "name": "Total Atualizações",
                    "expression": "DISTINCTCOUNT(vw_monitoramento_powerbi[id])",
                }
            ],
        )
        assert "Total Atualizações" in updated
        assert "Total Atualizações" not in inserted
        # Nova expressão presente
        assert "DISTINCTCOUNT" in result
        # Expressão antiga removida
        assert "COUNTROWS(vw_monitoramento_powerbi)" not in result

    def test_update_does_not_eat_adjacent_measure(self):
        tmdl = (
            "table t\n"
            "\tmeasure 'A' = 1\n"
            "\t\tlineageTag: aaa\n"
            "\tmeasure 'B' = 2\n"
            "\t\tlineageTag: bbb\n"
            "\tpartition t-p = entity\n"
            "\t\tmode: directLake\n"
        )
        result, updated, _ = _inject_measures_into_tmdl(
            tmdl,
            [{"name": "A", "expression": "99", "lineage_tag": FIXED_UUID}],
        )
        assert "A" in updated
        # Medida B deve continuar intacta
        assert "\tmeasure 'B' = 2" in result

    def test_insert_without_partition_appends_to_end(self):
        tmdl_no_partition = "table t\n\tlineageTag: xxx\n"
        result, _, inserted = _inject_measures_into_tmdl(
            tmdl_no_partition,
            [{"name": "Nova", "expression": "1"}],
        )
        assert "Nova" in inserted
        assert "Nova" in result

    def test_multiple_measures_in_one_call(self):
        result, updated, inserted = _inject_measures_into_tmdl(
            SAMPLE_TMDL_TABLE,
            [
                {"name": "Nova A", "expression": "1"},
                {"name": "Nova B", "expression": "2"},
                {"name": "Total Atualizações", "expression": "999"},
            ],
        )
        assert set(inserted) == {"Nova A", "Nova B"}
        assert updated == ["Total Atualizações"]


# ─── _parse_tmdl_text_table ──────────────────────────────────────────────────


class TestParseTmdlTextTable:
    def test_table_name_parsed(self):
        result = _parse_tmdl_text_table(SAMPLE_TMDL_TABLE)
        assert result["name"] == "vw_monitoramento_powerbi"

    def test_column_parsed(self):
        result = _parse_tmdl_text_table(SAMPLE_TMDL_TABLE)
        col_names = [c["name"] for c in result["columns"]]
        assert "workspace_id" in col_names

    def test_measure_parsed(self):
        result = _parse_tmdl_text_table(SAMPLE_TMDL_TABLE)
        msr_names = [m["name"] for m in result["measures"]]
        assert "Total Atualizações" in msr_names

    def test_measure_expression_parsed(self):
        result = _parse_tmdl_text_table(SAMPLE_TMDL_TABLE)
        msr = next(m for m in result["measures"] if m["name"] == "Total Atualizações")
        assert "COUNTROWS" in msr["expression"]

    def test_measure_format_string_parsed(self):
        result = _parse_tmdl_text_table(SAMPLE_TMDL_TABLE)
        msr = next(m for m in result["measures"] if m["name"] == "Total Atualizações")
        assert msr["format_string"] == "#,0"

    def test_partition_parsed(self):
        result = _parse_tmdl_text_table(SAMPLE_TMDL_TABLE)
        assert len(result["partitions"]) == 1
        assert result["partitions"][0]["mode"] == "directLake"

    def test_round_trip_inject_then_parse(self):
        """Medida injetada via _inject_measures_into_tmdl deve ser parseável."""
        new_tmdl, _, _ = _inject_measures_into_tmdl(
            SAMPLE_TMDL_TABLE,
            [
                {
                    "name": "Taxa Sucesso",
                    "expression": "0.95",
                    "format_string": "0.00%",
                    "lineage_tag": FIXED_UUID,
                }
            ],
        )
        result = _parse_tmdl_text_table(new_tmdl)
        msr_names = [m["name"] for m in result["measures"]]
        assert "Taxa Sucesso" in msr_names


# ─── fabric_semantic_update_definition (integração com HTTP mockado) ─────────


def _make_parts(
    tmdl_content: str, path: str = "definition/tables/vw_monitoramento_powerbi.tmdl"
) -> list[dict]:
    """Gera lista de parts TMDL codificadas em base64 para uso nos mocks."""
    payload = base64.b64encode(tmdl_content.encode()).decode()
    return [{"path": path, "payload": payload, "payloadType": "InlineBase64"}]


class TestFabricSemanticUpdateDefinition:
    """Testa fabric_semantic_update_definition com requests.post/get mockados."""

    ENV = {
        "AZURE_TENANT_ID": "tenant",
        "AZURE_CLIENT_ID": "client",
        "AZURE_CLIENT_SECRET": "secret",
        "FABRIC_WORKSPACE_ID": "workspace-id",
    }

    def _mock_get_token(self, scope):  # pragma: no cover
        return "fake-token"

    def _get_definition_resp(self, parts: list[dict], status: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {"definition": {"parts": parts}}
        resp.headers = {}
        return resp

    def _execute_queries_ok_resp(self) -> MagicMock:
        """Simula executeQueries sem erro de sintaxe DAX."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"results": [{"tables": [{"rows": [{"[Value]": 1}]}]}]}
        return resp

    def _execute_queries_dax_error_resp(self, message: str) -> MagicMock:
        """Simula executeQueries com erro de sintaxe DAX (200 + error no body)."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "results": [{"error": {"code": "SyntaxError", "message": message}}]
        }
        return resp

    def _update_definition_ok_resp(self) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        return resp

    @patch.dict("os.environ", ENV)
    @patch("mcp_servers.fabric_semantic.server._get_token")
    @patch("mcp_servers.fabric_semantic.server.requests")
    def test_insert_new_measure_success(self, mock_requests, mock_token):
        mock_token.return_value = "fake-token"
        parts = _make_parts(SAMPLE_TMDL_TABLE)

        mock_requests.post.side_effect = [
            self._get_definition_resp(parts),  # getDefinition
            self._execute_queries_ok_resp(),  # validação DAX
            self._update_definition_ok_resp(),  # updateDefinition
        ]

        result = json.loads(
            fabric_semantic_update_definition(
                model_id="model-123",
                table_name="vw_monitoramento_powerbi",
                measures=[{"name": "Nova Medida", "expression": "1"}],
            )
        )

        assert result["status"] == "success"
        assert "Nova Medida" in result["measures_inserted"]
        assert result["measures_updated"] == []

    @patch.dict("os.environ", ENV)
    @patch("mcp_servers.fabric_semantic.server._get_token")
    @patch("mcp_servers.fabric_semantic.server.requests")
    def test_update_existing_measure_success(self, mock_requests, mock_token):
        mock_token.return_value = "fake-token"
        parts = _make_parts(SAMPLE_TMDL_TABLE)

        mock_requests.post.side_effect = [
            self._get_definition_resp(parts),
            self._execute_queries_ok_resp(),
            self._update_definition_ok_resp(),
        ]

        result = json.loads(
            fabric_semantic_update_definition(
                model_id="model-123",
                table_name="vw_monitoramento_powerbi",
                measures=[{"name": "Total Atualizações", "expression": "999"}],
            )
        )

        assert result["status"] == "success"
        assert "Total Atualizações" in result["measures_updated"]
        assert result["measures_inserted"] == []

    @patch.dict("os.environ", ENV)
    @patch("mcp_servers.fabric_semantic.server._get_token")
    @patch("mcp_servers.fabric_semantic.server.requests")
    def test_dax_syntax_error_blocks_publish(self, mock_requests, mock_token):
        """Validação DAX falha → updateDefinition NÃO deve ser chamado."""
        mock_token.return_value = "fake-token"
        parts = _make_parts(SAMPLE_TMDL_TABLE)

        mock_requests.post.side_effect = [
            self._get_definition_resp(parts),  # getDefinition
            self._execute_queries_dax_error_resp("Syntax error near '='"),  # validação DAX
        ]

        result = json.loads(
            fabric_semantic_update_definition(
                model_id="model-123",
                table_name="vw_monitoramento_powerbi",
                measures=[{"name": "Medida Ruim", "expression": "= = ERRO"}],
            )
        )

        assert result["status"] == "validation_error"
        assert len(result["syntax_errors"]) == 1
        assert result["syntax_errors"][0]["measure"] == "Medida Ruim"
        # updateDefinition não deve ter sido chamado (apenas 2 POST: getDefinition + executeQueries)
        assert mock_requests.post.call_count == 2

    @patch.dict("os.environ", ENV)
    @patch("mcp_servers.fabric_semantic.server._get_token")
    @patch("mcp_servers.fabric_semantic.server.requests")
    def test_table_not_found_returns_error(self, mock_requests, mock_token):
        mock_token.return_value = "fake-token"
        parts = _make_parts(SAMPLE_TMDL_TABLE)

        mock_requests.post.return_value = self._get_definition_resp(parts)

        result = json.loads(
            fabric_semantic_update_definition(
                model_id="model-123",
                table_name="tabela_inexistente",
                measures=[{"name": "M", "expression": "1"}],
            )
        )

        assert "error" in result
        assert "tabela_inexistente" in result["error"]

    @patch.dict("os.environ", ENV)
    @patch("mcp_servers.fabric_semantic.server._get_token")
    @patch("mcp_servers.fabric_semantic.server.requests")
    def test_get_definition_http_error_returns_error(self, mock_requests, mock_token):
        mock_token.return_value = "fake-token"
        err_resp = MagicMock()
        err_resp.status_code = 403
        err_resp.text = "Forbidden"
        err_resp.headers = {}
        mock_requests.post.return_value = err_resp

        result = json.loads(
            fabric_semantic_update_definition(
                model_id="model-123",
                table_name="vw_monitoramento_powerbi",
                measures=[{"name": "M", "expression": "1"}],
            )
        )

        assert "error" in result
