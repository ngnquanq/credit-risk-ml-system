"""Tests for ExternalBureauService CDC parsing and data fetch."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from entrypoints.bureau_consumer import ExternalBureauService


@pytest.fixture
def service():
    with patch("entrypoints.bureau_consumer.Consumer"), \
         patch("entrypoints.bureau_consumer.Producer"), \
         patch("entrypoints.bureau_consumer.setup_tracing", return_value=MagicMock()):
        svc = ExternalBureauService()
        yield svc


class TestExtractSkIdCurrFromCdc:
    def test_plain_message(self, service):
        msg = {"sk_id_curr": "100001"}
        assert service._extract_sk_id_curr_from_cdc(msg) == "100001"

    def test_debezium_after(self, service):
        msg = {"payload": {"after": {"sk_id_curr": "200002"}}}
        assert service._extract_sk_id_curr_from_cdc(msg) == "200002"

    def test_debezium_before_fallback(self, service):
        msg = {"payload": {"before": {"sk_id_curr": "300003"}, "after": None}}
        assert service._extract_sk_id_curr_from_cdc(msg) == "300003"

    def test_nested_value_field(self, service):
        msg = {"value": {"sk_id_curr": "400004"}}
        assert service._extract_sk_id_curr_from_cdc(msg) == "400004"

    def test_empty_message_returns_none(self, service):
        assert service._extract_sk_id_curr_from_cdc({}) is None

    def test_int_sk_id_curr_to_str(self, service):
        msg = {"sk_id_curr": 12345}
        assert service._extract_sk_id_curr_from_cdc(msg) == "12345"


class TestFetchAndPrepareRawData:
    @patch("entrypoints.bureau_consumer.fetch_external_scores", new_callable=AsyncMock)
    @patch("entrypoints.bureau_consumer.fetch_bureau_by_loan_id", new_callable=AsyncMock)
    async def test_happy_path(self, mock_bureau, mock_ext, service):
        mock_bureau.return_value = {
            "bureau": [{"id": 1}],
            "bureau_balance": [{"bal": 100}],
            "sk_id_curr": 100001,
        }
        mock_ext.return_value = {"ext_source_1": 0.5, "ext_source_2": 0.6, "ext_source_3": 0.7}

        result = await service.fetch_and_prepare_raw_data("100001")

        assert result is not None
        assert result["sk_id_curr"] == "100001"  # string override
        assert result["external_scores"]["ext_source_1"] == 0.5
        assert "ts" in result

    @patch("entrypoints.bureau_consumer.fetch_external_scores", new_callable=AsyncMock)
    @patch("entrypoints.bureau_consumer.fetch_bureau_by_loan_id", new_callable=AsyncMock)
    async def test_int_coercion(self, mock_bureau, mock_ext, service):
        """int() is called on sk_id_curr for ClickHouse queries."""
        mock_bureau.return_value = {"bureau": [], "bureau_balance": []}
        mock_ext.return_value = {}

        await service.fetch_and_prepare_raw_data("999")
        mock_bureau.assert_called_once_with(999)

    @patch("entrypoints.bureau_consumer.fetch_external_scores", new_callable=AsyncMock)
    @patch("entrypoints.bureau_consumer.fetch_bureau_by_loan_id", new_callable=AsyncMock)
    async def test_non_numeric_sk_id_returns_none(self, mock_bureau, mock_ext, service):
        result = await service.fetch_and_prepare_raw_data("abc")
        assert result is None

    @patch("entrypoints.bureau_consumer.fetch_external_scores", new_callable=AsyncMock)
    @patch("entrypoints.bureau_consumer.fetch_bureau_by_loan_id", new_callable=AsyncMock)
    async def test_clickhouse_error_returns_none(self, mock_bureau, mock_ext, service):
        mock_bureau.side_effect = Exception("ClickHouse timeout")

        result = await service.fetch_and_prepare_raw_data("100001")
        assert result is None
