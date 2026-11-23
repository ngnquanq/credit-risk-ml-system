"""Loan API routes for four-eyes changes to decision thresholds."""

from datetime import datetime

from audit.writer import AuditWriter
from authz import Action, Principal, Resource
from core import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from infrastructure.persistence.models.sqlalchemy_models import PolicyChange as DbPolicyChange
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .access import require_action
from .dependencies import get_audit_writer
from .security import get_principal

router = APIRouter()

# Decision policy changes (E11): proposed by one risk manager, approved by another.
# The scoring service picks up the active bands at its next rollout (SCORING_APPROVE_BELOW,
# SCORING_REJECT_ABOVE); pushing them automatically is a follow-up.
class PolicyChangeRequest(BaseModel):
    approve_below: float = Field(..., gt=0, lt=1)
    reject_above: float = Field(..., gt=0, lt=1)
    rationale: str = Field(..., min_length=10, max_length=1000)


class PolicyDecisionRequest(BaseModel):
    approve: bool
    comment: str = Field("", max_length=1000)


def _policy_out(row: DbPolicyChange) -> dict:
    return {"id": row.id, "state": row.state, "payload": row.payload, "proposed_by": row.proposed_by,
            "approved_by": row.approved_by, "created_at": row.created_at, "decided_at": row.decided_at}


@router.get("/api/v1/policy-changes", tags=["Policy"])
async def list_policy_changes(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    await require_action(principal, Action.PROPOSE_POLICY_CHANGE, Resource(type="policy", id="-"), audit)
    rows = (await db.execute(select(DbPolicyChange).order_by(DbPolicyChange.id.desc()).limit(50))).scalars().all()
    return [_policy_out(r) for r in rows]


@router.post("/api/v1/policy-changes", status_code=status.HTTP_201_CREATED, tags=["Policy"])
async def propose_policy_change(
    body: PolicyChangeRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    if not body.approve_below <= body.reject_above:
        raise HTTPException(status_code=422, detail="approve_below must not exceed reject_above")
    payload = {"approve_below": body.approve_below, "reject_above": body.reject_above, "rationale": body.rationale}
    await require_action(principal, Action.PROPOSE_POLICY_CHANGE, Resource(type="policy", id="new"), audit,
                   {"payload": payload})
    row = DbPolicyChange(proposed_by=principal.sub, payload=payload, state="proposed")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _policy_out(row)


@router.post("/api/v1/policy-changes/{change_id}/decision", tags=["Policy"])
async def decide_policy_change(
    change_id: int,
    body: PolicyDecisionRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    row = (await db.execute(select(DbPolicyChange).where(DbPolicyChange.id == change_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy change not found")
    if row.state != "proposed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Policy change is {row.state}")
    await require_action(principal, Action.APPROVE_POLICY_CHANGE,
                   Resource(type="policy", id=str(change_id), proposed_by=row.proposed_by), audit,
                   {"payload": row.payload, "proposed_by": row.proposed_by})
    now = datetime.utcnow()
    if body.approve:
        for active in (await db.execute(select(DbPolicyChange).where(DbPolicyChange.state == "active"))).scalars():
            active.state = "superseded"
        row.state, row.approved_by = "active", principal.sub
    else:
        row.state = "rejected"
    row.decided_at = now
    await db.commit()
    return _policy_out(row)
