import asyncio
from datetime import date
from workflows.submit_loan import SubmitLoanWorkflow, SubmitLoanInput
from infrastructure.persistence.postgres_loan_repo import PostgresLoanRepository
from infrastructure.external.kafka_scoring import KafkaScoringGateway
from infrastructure.external.bureau_adapter import BureauAdapter
from db_models.schemas import LoanApplicationCreate

# Mock dependencies to test wiring
class MockRepo:
    async def save(self, app):
        print(f"[MockRepo] Saving application {app.sk_id_curr}, status={app.status}")

class MockScoring:
    async def publish_for_scoring(self, app_id):
        print(f"[MockScoring] Publishing {app_id}")

class MockBureau:
    async def get_bureau_data(self, app_id):
        return {}

async def test_workflow_wiring():
    # 1. Setup Dependencies
    repo = MockRepo()
    scoring = MockScoring()
    bureau = MockBureau()
    
    workflow = SubmitLoanWorkflow(repo, bureau, scoring)
    
    # 2. Create Input DTO (Reusing your Pydantic Schema)
    input_data = LoanApplicationCreate(
        sk_id_curr="100001",
        code_gender="M",
        birth_date=date(1985, 1, 1),
        amt_credit=200000.0,
        amt_income_total=50000.0,
        name_contract_type="Cash loans",
        name_income_type="Working",
        name_education_type="Higher education",
        name_family_status="Married",
        name_housing_type="House / apartment"
    )
    
    # 3. Execute Workflow (Structural Test)
    print("--- Starting Workflow Execution ---")
    result = await workflow.execute(input_data)
    print("--- Workflow Finished ---")
    
    # 4. Verify Output
    print(f"Result Status: {result.status}")
    assert result.application_id == "100001"
    print("✅ Verification Successful: Workflow instantiated and executed correctly.")

if __name__ == "__main__":
    asyncio.run(test_workflow_wiring())
