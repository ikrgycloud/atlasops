from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlasops.auth import Principal
from atlasops.models import AuditEvent, Environment


def scoped_query(model, principal: Principal):
    query = select(model).where(model.tenant_id == principal.tenant_id)
    if model is Environment and "*" not in principal.environment_ids:
        query = query.where(model.id.in_(principal.environment_ids))
    if hasattr(model, "environment_id") and "*" not in principal.environment_ids:
        query = query.where(model.environment_id.in_(principal.environment_ids))
    return query


def scoped_get(session: Session, model, object_id: str, principal: Principal, *, for_update=False):
    query = scoped_query(model, principal).where(model.id == object_id)
    if for_update:
        query = query.with_for_update()
    record = session.scalar(query)
    if not record:
        raise HTTPException(404, "Not found")
    return record


def audit(session: Session, principal: Principal, kind: str, record, data=None):
    session.add(
        AuditEvent(
            tenant_id=principal.tenant_id,
            environment_id=getattr(record, "environment_id", None),
            actor_id=principal.user_id,
            kind=kind,
            object_id=record.id,
            data=data or {},
        )
    )
