"""Tests for dwh_client_ch.py ClickHouse DWH query helpers."""

import queue
from unittest.mock import MagicMock, patch

from infrastructure.external import dwh_client_ch as mod


def _pool_with(*clients):
    pool = queue.Queue(maxsize=max(len(clients), 1))
    for client in clients:
        pool.put(client)
    return pool


class TestDwhQueryDicts:
    def setup_method(self):
        mod._pool = None

    def test_returns_lowercased_dicts(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ["SK_ID_CURR", "AMT_CREDIT"]
        mock_result.result_rows = [(100, 50000.0)]
        mock_client.query.return_value = mock_result
        mod._pool = _pool_with(mock_client)

        result = mod._query_dicts("SELECT *")
        assert result == [{"sk_id_curr": 100, "amt_credit": 50000.0}]

    def test_empty_result(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ["A"]
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result
        mod._pool = _pool_with(mock_client)

        assert mod._query_dicts("SELECT *") == []


class TestGetTableColumns:
    @patch("infrastructure.external.dwh_client_ch._query")
    def test_returns_lowercased_names(self, mock_query):
        mock_result = MagicMock()
        mock_result.result_rows = [("SK_ID_CURR",), ("AMT_CREDIT",)]
        mock_query.return_value = mock_result

        mod._schema_cache = {}
        result = mod.get_table_columns("mart_test")
        assert result == ["sk_id_curr", "amt_credit"]

    @patch("infrastructure.external.dwh_client_ch._query")
    def test_caches_result(self, mock_query):
        mock_result = MagicMock()
        mock_result.result_rows = [("COL_A",)]
        mock_query.return_value = mock_result

        mod._schema_cache = {}

        mod.get_table_columns("mart_cached")
        mod.get_table_columns("mart_cached")

        mock_query.assert_called_once()


class TestFetchAllBySkIdCurr:
    @patch("infrastructure.external.dwh_client_ch._query_dicts")
    async def test_returns_dict_per_table(self, mock_query):
        mock_query.return_value = [{"sk_id_curr": 100, "col": 1}]

        result = await mod.fetch_all_by_sk_id_curr(100)

        for tbl in mod.MART_TABLES:
            assert tbl in result

    @patch("infrastructure.external.dwh_client_ch._query_dicts")
    async def test_empty_tables(self, mock_query):
        mock_query.return_value = []

        result = await mod.fetch_all_by_sk_id_curr(999)

        for tbl_rows in result.values():
            assert tbl_rows == []


class TestCloseDwhClient:
    async def test_close(self):
        mock_client = MagicMock()
        mod._pool = _pool_with(mock_client)

        await mod.close_dwh_client()

        mock_client.close.assert_called_once()
        assert mod._pool is None

    async def test_close_with_none_pool(self):
        mod._pool = None
        await mod.close_dwh_client()
