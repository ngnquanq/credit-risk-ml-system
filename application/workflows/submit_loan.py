from domain.entities.loan_application import LoanApplication, ApplicationStatus
from domain.interfaces.loan_repository import LoanRepository
from domain.interfaces.bureau_gateway import BureauGateway
from domain.interfaces.scoring_gateway import ScoringGateway
from workflows.dtos import SubmitLoanInput, SubmitLoanOutput
import uuid
import logging

class SubmitLoanWorkflow:
    def __init__(
        self,
        loan_repo: LoanRepository,
        scoring_gateway: ScoringGateway,
    ):
        self.loan_repo = loan_repo
        self.scoring_gateway = scoring_gateway
        self.logger = logging.getLogger(__name__)

    async def execute(self, input_data: SubmitLoanInput) -> SubmitLoanOutput:
        # 1. Create Domain Entity
        application = LoanApplication(
            sk_id_curr=input_data.sk_id_curr,
            amt_credit=input_data.amt_credit,
            amt_income_total=input_data.amt_income_total,
            amt_goods_price=input_data.amt_goods_price,
            # Pass all fields for persistence
            details=input_data.model_dump()
        )
        
        self.logger.info(f"Received application for {application.sk_id_curr}")

        # 2. Persist Initial State
        application.status = ApplicationStatus.SUBMITTED
        await self.loan_repo.save(application)

        # 3. Publish to Scoring Queue (Async processing)
        # The Scoring Service will pick this up, fetch Bureau data, and score it.
        await self.scoring_gateway.publish_for_scoring(application.sk_id_curr)
        
        # 4. Return Pending Status
        return SubmitLoanOutput(
            application_id=application.sk_id_curr,
            status=application.status.value,
            is_approved=None, # Decision pending
            risk_score=None
        )
