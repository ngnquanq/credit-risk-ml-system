"""Authorization enforcement and audit for Loan API actions."""

from audit.writer import AuditEvent, AuditWriter
from authz import Action, Principal, Resource, authorize
from fastapi import HTTPException, status


async def require_action(
    principal: Principal,
    action: Action,
    resource: Resource,
    audit: AuditWriter,
    details: dict | None = None,
) -> None:
    """Record the authorization decision and reject denied API actions."""
    decision = authorize(principal, action, resource)
    await audit.record(AuditEvent(
        actor_sub=principal.sub,
        actor_realm=principal.realm,
        actor_roles=tuple(principal.roles),
        action=action.value,
        resource_type=resource.type,
        resource_id=resource.id or "-",
        outcome="allowed" if decision.allowed else "denied",
        details={"rule": decision.rule, **(details or {})},
    ))
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden", "rule": decision.rule})
