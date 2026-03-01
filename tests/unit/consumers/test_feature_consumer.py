"""Tests for DWHFeaturesService CDC parsing and data fetch."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from entrypoints.feature_consumer import DWHFeaturesService


@pytest.fixture
def service():
    with patch("entrypoints.feature_consumer.Consumer"), \
         patch("entrypoints.feature_consumer.Producer"), \
         patch("entrypoints.feature_consumer.setup_tracing", return_value=MagicMock()):
        svc = DWHFeaturesService()
        yield svc


class TestExtractSkIdCurrFromCdc:
    def test_plain_message(self, service):
        assert service._extract_sk_id_curr_from_cdc({"sk_id_curr": "100001"}) == "100001"

    def test_debezium_after(self, service):
        msg = {"payload": {"after": {"sk_id_curr": "200002"}}}
        assert service._extract_sk_id_curr_from_cdc(msg) == "200002"

    def test_empty_returns_none(self, service):
        assert service._extract_sk_id_curr_from_cdc({}) is None


class TestProcessLoanApplication:
    @patch("entrypoints.feature_consumer.get_table_columns")
    @patch("entrypoints.feature_consumer.fetch_all_by_sk_id_curr", new_callable=AsyncMock)
    async def test_happy_path(self, mock_fetch, mock_cols, service):
        mock_fetch.return_value = {
            "mart_previous_application": [{"col_a": 1.0, "sk_id_curr": 100}],
            "mart_pos_cash_balance": [],
            "mart_credit_card_balance": [],
        }
        mock_cols.return_value = ["sk_id_curr", "col_a"]

        # Patch MART_TABLES to match mock
        with patch("entrypoints.feature_consumer.MART_TABLES", ["mart_previous_application"]):
            result = await service.process_loan_application("100")

        assert result is not None
        assert result["sk_id_curr"] == "100"
        assert "ts" in result

    @patch("entrypoints.feature_consumer.get_table_columns")
    @patch("entrypoints.feature_consumer.fetch_all_by_sk_id_curr", new_callable=AsyncMock)
    async def test_missing_data_emits_none(self, mock_fetch, mock_cols, service):
        mock_fetch.return_value = {"mart_tbl": []}
        mock_cols.return_value = ["sk_id_curr", "feature_x"]

        with patch("entrypoints.feature_consumer.MART_TABLES", ["mart_tbl"]):
            result = await service.process_loan_application("100")

        assert result["feature_x"] is None

    @patch("entrypoints.feature_consumer.get_table_columns")
    @patch("entrypoints.feature_consumer.fetch_all_by_sk_id_curr", new_callable=AsyncMock)
    async def test_non_numeric_sk_id_returns_none(self, mock_fetch, mock_cols, service):
        result = await service.process_loan_application("abc_not_a_number")
        assert result is None

    @patch("entrypoints.feature_consumer.get_table_columns")
    @patch("entrypoints.feature_consumer.fetch_all_by_sk_id_curr", new_callable=AsyncMock)
    async def test_schema_driven_column_emission(self, mock_fetch, mock_cols, service):
        """Columns are driven by get_table_columns(), not by data keys."""
        mock_fetch.return_value = {"mart_tbl": [{"col_a": 1, "col_b": 2, "extra": 99}]}
        mock_cols.return_value = ["sk_id_curr", "col_a", "col_b"]

        with patch("entrypoints.feature_consumer.MART_TABLES", ["mart_tbl"]):
            result = await service.process_loan_application("100")

        assert result["col_a"] == 1
        assert result["col_b"] == 2
        assert "extra" not in result  # not in schema

    @patch("entrypoints.feature_consumer.get_table_columns")
    @patch("entrypoints.feature_consumer.fetch_all_by_sk_id_curr", new_callable=AsyncMock)
    async def test_fetch_error_returns_none(self, mock_fetch, mock_cols, service):
        mock_fetch.side_effect = Exception("DWH down")
        result = await service.process_loan_application("100")
        assert result is None
