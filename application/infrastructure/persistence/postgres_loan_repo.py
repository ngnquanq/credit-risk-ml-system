from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from domain.entities.loan_application import LoanApplication, ApplicationStatus
from domain.interfaces.loan_repository import LoanRepository
from infrastructure.persistence.models.sqlalchemy_models import LoanApplication as DbLoanApplication

class PostgresLoanRepository(LoanRepository):
    """
    Infrastructure implementation of the Domain Repository.
    Bridges the gap between pure Domain Entities and SQLAlchemy Models.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, application: LoanApplication) -> None:
        """
        Converts Domain Entity -> DB Model and saves it.
        """
        # Check if exists to decide update vs insert (simplified)
        existing_stmt = select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == application.sk_id_curr)
        result = await self.session.execute(existing_stmt)
        db_model = result.scalar_one_or_none()
        
        # Flatten details: promote nested document_ids dict to top-level keys
        # e.g. {"document_ids": {"document_id_2": "doc_abc"}} 
        #   -> {"document_id_2": "doc_abc", ...}
        flat_details = dict(application.details or {})
        doc_ids = flat_details.pop('document_ids', None)
        if isinstance(doc_ids, dict):
            flat_details.update(doc_ids)
        
        # Get valid DB column names for filtering
        valid_columns = {c.key for c in DbLoanApplication.__table__.columns}
        
        if db_model:
            # Update existing — update fields from details
            for key, value in flat_details.items():
                if key in valid_columns and key != 'sk_id_curr' and value is not None:
                    setattr(db_model, key, value)
        else:
            # Create new from entity
            db_kwargs = {
                'sk_id_curr': application.sk_id_curr,
                'amt_credit': application.amt_credit,
                'amt_income_total': application.amt_income_total,
            }
            # Add any additional details that match valid DB columns
            for key, value in flat_details.items():
                if key in valid_columns and key not in db_kwargs and value is not None:
                    db_kwargs[key] = value
            
            db_model = DbLoanApplication(**db_kwargs)
            self.session.add(db_model)
            
        await self.session.commit()

    async def get_by_id(self, application_id: str) -> Optional[LoanApplication]:
        """
        Fetches DB Model and converts to Domain Entity.
        """
        stmt = select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == application_id)
        result = await self.session.execute(stmt)
        db_model = result.scalar_one_or_none()
        
        if not db_model:
            return None
            
        # Convert DB Model -> Domain Entity
        return LoanApplication(
            sk_id_curr=db_model.sk_id_curr,
            amt_credit=db_model.amt_credit,
            amt_income_total=db_model.amt_income_total,
            amt_goods_price=db_model.amt_goods_price,
            status=ApplicationStatus(db_model.status),
            request_date=db_model.created_at,
            details={} # Populate if needed
        )
