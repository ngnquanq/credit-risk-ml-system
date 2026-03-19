"""Tests for SubmitLoanWorkflow orchestration."""

import pytest
from unittest.mock import AsyncMock, call

from workflows.submit_loan import SubmitLoanWorkflow
from workflows.dtos import SubmitLoanInput, SubmitLoanOutput
from domain.entities.loan_application import ApplicationStatus


@pytest.fixture
def valid_input(valid_create_payload):
    return SubmitLoanInput(**valid_create_payload)


class TestSubmitLoanWorkflow:
    async def test_execute_saves_application(self, mock_loan_repo, mock_scoring_gateway, valid_input):
        wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
        await wf.execute(valid_input)

        mock_loan_repo.save.assert_called_once()
        saved_app = mock_loan_repo.save.call_args[0][0]
        assert saved_app.sk_id_curr == valid_input.sk_id_curr
        assert saved_app.amt_credit == valid_input.amt_credit

    async def test_execute_publishes_for_scoring(self, mock_loan_repo, mock_scoring_gateway, valid_input):
        wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
        await wf.execute(valid_input)

        mock_scoring_gateway.publish_for_scoring.assert_called_once_with(valid_input.sk_id_curr)

    async def test_execute_returns_submitted_status(self, mock_loan_repo, mock_scoring_gateway, valid_input):
        wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
        output = await wf.execute(valid_input)

        assert output.status == "submitted"
        assert output.application_id == valid_input.sk_id_curr

    async def test_execute_is_approved_is_none(self, mock_loan_repo, mock_scoring_gateway, valid_input):
        """BUG DOC: is_approved typed as bool but assigned None."""
        wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
        output = await wf.execute(valid_input)

        assert output.is_approved is None  # violates type annotation `bool`

    async def test_execution_order(self, mock_loan_repo, mock_scoring_gateway, valid_input):
        """Save must happen before publish."""
        call_order = []
        mock_loan_repo.save.side_effect = lambda _: call_order.append("save")
        mock_scoring_gateway.publish_for_scoring.side_effect = lambda _: call_order.append("publish")

        wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
        await wf.execute(valid_input)

        assert call_order == ["save", "publish"]

    async def test_repo_exception_propagates(self, mock_loan_repo, mock_scoring_gateway, valid_input):
        """No try/except in workflow — errors propagate to caller."""
        mock_loan_repo.save.side_effect = RuntimeError("DB down")

        wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
        with pytest.raises(RuntimeError, match="DB down"):
            await wf.execute(valid_input)

    async def test_details_contains_full_input(self, mock_loan_repo, mock_scoring_gateway, valid_input):
        wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
        await wf.execute(valid_input)

        saved_app = mock_loan_repo.save.call_args[0][0]
        assert saved_app.details == valid_input.model_dump()
