import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


Json = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Scoped(Record):
    tenant_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("tenants.id"), index=True)


class Tenant(Record, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(160))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="tenant")


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True)
    external_subject: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(Scoped, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(24))
    environment_ids: Mapped[list] = mapped_column(Json, default=lambda: ["*"])
    tenant: Mapped[Tenant] = relationship(back_populates="memberships")


class Environment(Scoped, Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("tenant_id", "id"), UniqueConstraint("tenant_id", "name"))
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(Text, default="")
    resource_scope: Mapped[list] = mapped_column(Json, default=list)
    health: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class InEnvironment(Scoped):
    environment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)


def environment_fk():
    return ForeignKeyConstraint(
        ["tenant_id", "environment_id"], ["environments.tenant_id", "environments.id"]
    )


class Service(InEnvironment, Base):
    __tablename__ = "services"
    __table_args__ = (environment_fk(), UniqueConstraint("tenant_id", "id"))
    name: Mapped[str] = mapped_column(String(160))
    owner: Mapped[str] = mapped_column(String(160), default="unassigned")
    criticality: Mapped[str] = mapped_column(String(24), default="medium")
    health: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    environment: Mapped[Environment] = relationship()


class Integration(InEnvironment, Base):
    __tablename__ = "integrations"
    __table_args__ = (environment_fk(), UniqueConstraint("tenant_id", "id"))
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict] = mapped_column(Json, default=dict)
    secret_ref: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), default="UNTESTED")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))


class Deployment(InEnvironment, Base):
    __tablename__ = "deployments"
    __table_args__ = (environment_fk(), UniqueConstraint("tenant_id", "external_id"))
    external_id: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(32))
    repository: Mapped[str] = mapped_column(String(255), default="")
    revision: Mapped[str] = mapped_column(String(160), default="")
    branch: Mapped[str] = mapped_column(String(160), default="")
    workflow: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32))
    run_url: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Incident(InEnvironment, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        environment_fk(),
        UniqueConstraint("tenant_id", "fingerprint"),
        UniqueConstraint("tenant_id", "id"),
    )
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="NEW")
    fingerprint: Mapped[str] = mapped_column(String(128))
    service_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    source: Mapped[str] = mapped_column(String(64))
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    owner: Mapped[str] = mapped_column(String(160), default="unassigned")


class IncidentEvent(InEnvironment, Base):
    __tablename__ = "incident_events"
    __table_args__ = (
        environment_fk(),
        ForeignKeyConstraint(["tenant_id", "incident_id"], ["incidents.tenant_id", "incidents.id"]),
    )
    incident_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(Json, default=dict)


class Observation(InEnvironment, Base):
    __tablename__ = "observations"
    __table_args__ = (environment_fk(),)
    integration_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    source: Mapped[str] = mapped_column(String(64))
    resource: Mapped[str] = mapped_column(String(255))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    data: Mapped[dict] = mapped_column(Json)
    quality: Mapped[str] = mapped_column(String(24), default="partial")


class Investigation(InEnvironment, Base):
    __tablename__ = "investigations"
    __table_args__ = (
        environment_fk(),
        ForeignKeyConstraint(["tenant_id", "incident_id"], ["incidents.tenant_id", "incidents.id"]),
    )
    incident_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    findings: Mapped[dict] = mapped_column(Json, default=dict)


class ActionProposal(InEnvironment, Base):
    __tablename__ = "action_proposals"
    __table_args__ = (
        environment_fk(),
        ForeignKeyConstraint(["tenant_id", "incident_id"], ["incidents.tenant_id", "incidents.id"]),
        UniqueConstraint("tenant_id", "id"),
    )
    incident_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    state: Mapped[str] = mapped_column(String(32), default="PROPOSED", index=True)
    plan: Mapped[dict] = mapped_column(Json)
    plan_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Approval(InEnvironment, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        environment_fk(),
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"], ["action_proposals.tenant_id", "action_proposals.id"]
        ),
        UniqueConstraint("proposal_id"),
    )
    proposal_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    plan_hash: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str | None] = mapped_column(String(16))
    approver_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionExecution(InEnvironment, Base):
    __tablename__ = "action_executions"
    __table_args__ = (
        environment_fk(),
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"], ["action_proposals.tenant_id", "action_proposals.id"]
        ),
        UniqueConstraint("proposal_id"),
    )
    proposal_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    status: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict] = mapped_column(Json, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(InEnvironment, Base):
    __tablename__ = "audit_events"
    # Audit entries for tenant-level events have no environment.
    environment_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(80), index=True)
    object_id: Mapped[str] = mapped_column(String(160))
    data: Mapped[dict] = mapped_column(Json, default=dict)


class Report(Scoped, Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("tenant_id", "window_start", "window_end", "scope_key"),)
    scope_key: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(Json)


class NotificationDelivery(Scoped, Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("report_id", "recipient"),)
    report_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("reports.id"))
    recipient: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))


class BackgroundJob(Scoped, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        Index("ix_jobs_dispatch", "status", "available_at"),
    )
    kind: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class WebhookReceipt(Scoped, Base):
    __tablename__ = "webhook_receipts"
    __table_args__ = (UniqueConstraint("integration_id", "external_id"),)
    integration_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("integrations.id"))
    external_id: Mapped[str] = mapped_column(String(255))


class Connector(InEnvironment, Base):
    __tablename__ = "connectors"
    __table_args__ = (environment_fk(),)
    name: Mapped[str] = mapped_column(String(160))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    resource: Mapped[str] = mapped_column(String(255))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[str] = mapped_column(String(40), default="unknown")


class SandboxResource(InEnvironment, Base):
    __tablename__ = "sandbox_resources"
    __table_args__ = (environment_fk(), UniqueConstraint("tenant_id", "environment_id", "name"))
    name: Mapped[str] = mapped_column(String(160))
    healthy: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)


def public_record(record: Any) -> dict:
    return {c.key: getattr(record, c.key) for c in record.__table__.columns}
