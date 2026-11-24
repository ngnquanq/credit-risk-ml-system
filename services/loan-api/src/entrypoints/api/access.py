"""Authorization enforcement and audit for Loan API actions."""

from audit.writer import AuditEvent, AuditWriter
from authz import Action, Principal, Resource, authorize
from fastapi import HTTPException, status
from loguru import logger


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
    who = {"id": principal.sub, "type": principal.realm, "role": ",".join(sorted(principal.roles))}
    what = {"type": resource.type, "id": resource.id or "-"}
    if decision.allowed:
        logger.info("Access allowed", event="authz.access.allowed", actor=who, target=what,
                    action=action.value, status="SUCCESS", reason_code=decision.rule)
    else:
        logger.warning("Access denied", event="authz.access.denied", actor=who, target=what,
                       action=action.value, status="DENIED", reason_code=decision.rule)
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden", "rule": decision.rule})
