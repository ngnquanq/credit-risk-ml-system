"""Tests for bureau_client.py ClickHouse query helpers."""

import queue
from unittest.mock import MagicMock, patch

from infrastructure.external import bureau_client as mod
from infrastructure.external.bureau_client import (
    _query_dicts,
    close_bureau_client,
    fetch_bureau_by_loan_id,
    fetch_external_scores,
)


def _pool_with(*clients):
    pool = queue.Queue(maxsize=max(len(clients), 1))
    for client in clients:
        pool.put(client)
    return pool


class TestQueryDicts:
    def setup_method(self):
        mod._pool = None

    def test_returns_list_of_dicts(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ["SK_ID_CURR", "AMOUNT"]
        mock_result.result_rows = [(100, 5000.0), (101, 6000.0)]
        mock_client.query.return_value = mock_result
        mod._pool = _pool_with(mock_client)

        result = _query_dicts("SELECT * FROM bureau")

        assert len(result) == 2
        assert result[0] == {"sk_id_curr": 100, "amount": 5000.0}
        mock_client.query.assert_called_once_with("SELECT * FROM bureau")

    def test_lowercases_column_names(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ["SK_ID_CURR", "CREDIT_ACTIVE"]
        mock_result.result_rows = [(1, "Active")]
        mock_client.query.return_value = mock_result
        mod._pool = _pool_with(mock_client)

        result = _query_dicts("SELECT *")
        assert "sk_id_curr" in result[0]
        assert "credit_active" in result[0]

    def test_empty_result(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.column_names = ["A"]
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result
        mod._pool = _pool_with(mock_client)

        assert _query_dicts("SELECT *") == []


class TestFetchBureauByLoanId:
    @patch("infrastructure.external.bureau_client._query_dicts")
    async def test_returns_bureau_and_balance(self, mock_query):
        mock_query.side_effect = [
            [{"sk_id_curr": 100, "sk_id_bureau": 1}],
            [{"sk_id_bureau": 1, "months_balance": -1}],
        ]
        result = await fetch_bureau_by_loan_id(100)

        assert result["sk_id_curr"] == 100
        assert len(result["bureau"]) == 1
        assert len(result["bureau_balance"]) == 1

    @patch("infrastructure.external.bureau_client._query_dicts")
    async def test_no_bureau_ids_skips_balance(self, mock_query):
        mock_query.return_value = []
        result = await fetch_bureau_by_loan_id(999)

        assert result["bureau"] == []
        assert result["bureau_balance"] == []
        mock_query.assert_called_once()

    @patch("infrastructure.external.bureau_client._query_dicts")
    async def test_multiple_bureau_ids(self, mock_query):
        mock_query.side_effect = [
            [
                {"sk_id_curr": 100, "sk_id_bureau": 1},
                {"sk_id_curr": 100, "sk_id_bureau": 2},
            ],
            [{"sk_id_bureau": 1, "months_balance": 0}],
        ]
        result = await fetch_bureau_by_loan_id(100)
        assert len(result["bureau"]) == 2


class TestFetchExternalScores:
    @patch("infrastructure.external.bureau_client._query_dicts")
    async def test_returns_first_row(self, mock_query):
        mock_query.return_value = [{"ext_source_1": 0.5, "ext_source_2": 0.6}]
        result = await fetch_external_scores(100)
        assert result["ext_source_1"] == 0.5

    @patch("infrastructure.external.bureau_client._query_dicts")
    async def test_empty_returns_empty_dict(self, mock_query):
        mock_query.return_value = []
        result = await fetch_external_scores(100)
        assert result == {}


class TestCloseBureauClient:
    async def test_close_calls_client_close(self):
        mock_client = MagicMock()
        mod._pool = _pool_with(mock_client)

        await close_bureau_client()

        mock_client.close.assert_called_once()
        assert mod._pool is None

    async def test_close_swallows_error(self):
        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("already closed")
        mod._pool = _pool_with(mock_client)

        await close_bureau_client()
