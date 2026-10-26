import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import select

from atlasops.access import audit, scoped_get
from atlasops.adapters.contracts import Capabilities, ExecutionAdapter
from atlasops.auth import resolve_principal
from atlasops.db import transaction
from atlasops.incidents import event
from atlasops.models import (
    ActionExecution,
    ActionProposal,
    Approval,
    Environment,
    Incident,
    Observation,
    SandboxResource,
    now,
)
from atlasops.schemas import PlanParameters, StrictModel

TRANSITIONS = {
    "PROPOSED": {"POLICY_VALIDATED", "REJECTED"},
    "POLICY_VALIDATED": {"AWAITING_APPROVAL"},
    "AWAITING_APPROVAL": {"APPROVED", "REJECTED", "EXPIRED", "CANCELLED"},
    "APPROVED": {"EXECUTING", "EXPIRED", "CANCELLED"},
    "EXECUTING": {"VERIFYING", "FAILED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "VERIFYING": {"SUCCEEDED", "FAILED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "UNKNOWN": {"RECONCILIATION_REQUIRED"},
    "RECONCILIATION_REQUIRED": {"SUCCEEDED", "FAILED", "UNKNOWN"},
}


class ActionPlan(StrictModel):
    version: Literal[1] = 1
    tenant_id: UUID
    environment_id: UUID
    incident_id: UUID
    resource_id: UUID
    action_type: Literal["sandbox.recover"]
    parameters: PlanParameters
    reason: str = Field(min_length=10, max_length=2000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=20)
    expected_effect: str
    risk: Literal["low"]
    impact: str
    required_permissions: list[Literal["sandbox.execute"]]
    preconditions: list[str]
    timeout_seconds: Literal[15] = 15
    verification: Literal["Read sandbox resource and confirm healthy state and incremented revision"]
    rollback: str
    created_at: datetime
    expires_at: datetime


def plan_hash(plan: dict) -> str:
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def transition(proposal, target):
    if target not in TRANSITIONS.get(proposal.state, set()):
        raise HTTPException(409, "Invalid action state transition")
    proposal.state = target


def validate_policy(session, proposal, principal):
    try:
        plan = ActionPlan.model_validate(proposal.plan)
    except ValidationError:
        raise HTTPException(409, "Action plan schema invalid")
    if plan_hash(proposal.plan) != proposal.plan_hash:
        raise HTTPException(409, "Action plan changed")
    if str(plan.tenant_id) != principal.tenant_id or str(plan.environment_id) != proposal.environment_id:
        raise HTTPException(403, "Action scope invalid")
    if str(plan.incident_id) != proposal.incident_id or plan.expires_at != proposal.expires_at:
        raise HTTPException(409, "Action metadata changed")
    if not principal.permits_environment(proposal.environment_id):
        raise HTTPException(403, "Action environment denied")
    env = scoped_get(session, Environment, proposal.environment_id, principal)
    if env.provider != "sandbox" or not env.demo:
        raise HTTPException(403, "Only explicitly labeled demo sandbox execution is enabled")
    resource = scoped_get(session, SandboxResource, str(plan.resource_id), principal)
    if resource.environment_id != env.id:
        raise HTTPException(403, "Resource target outside approved environment")
    if env.resource_scope and resource.id not in env.resource_scope:
        raise HTTPException(403, "Resource no longer in scope")
    return plan


def propose(session, principal, incident, body):
    principal.require("operate")
    resource = scoped_get(session, SandboxResource, str(body.resource_id), principal)
    if resource.environment_id != incident.environment_id:
        raise HTTPException(422, "Resource belongs to another environment")
    evidence = session.scalars(
        select(Observation).where(
            Observation.id.in_([str(x) for x in body.evidence_ids]),
            Observation.tenant_id == principal.tenant_id,
            Observation.environment_id == incident.environment_id,
        )
    ).all()
    if len({row.id for row in evidence}) != len(set(body.evidence_ids)):
        raise HTTPException(422, "Evidence references outside authorized scope")
    if resource.revision != body.parameters.expected_revision or resource.healthy:
        raise HTTPException(409, "Sandbox preconditions do not hold")
    expires_at = now() + timedelta(minutes=body.expires_in_minutes)
    data = body.model_dump(mode="json", exclude={"expires_in_minutes"})
    plan = ActionPlan(
        **data,
        tenant_id=principal.tenant_id,
        environment_id=incident.environment_id,
        incident_id=incident.id,
        required_permissions=["sandbox.execute"],
        created_at=now(),
        expires_at=expires_at,
        preconditions=["Sandbox unhealthy", "Resource revision equals expected_revision"],
        verification="Read sandbox resource and confirm healthy state and incremented revision",
    ).model_dump(mode="json")
    proposal = ActionProposal(
        tenant_id=principal.tenant_id,
        environment_id=incident.environment_id,
        incident_id=incident.id,
        plan=plan,
        plan_hash=plan_hash(plan),
        expires_at=expires_at,
        state="PROPOSED",
    )
    session.add(proposal)
    session.flush()
    validate_policy(session, proposal, principal)
    transition(proposal, "POLICY_VALIDATED")
    transition(proposal, "AWAITING_APPROVAL")
    session.add(
        Approval(
            tenant_id=principal.tenant_id,
            environment_id=incident.environment_id,
            proposal_id=proposal.id,
            plan_hash=proposal.plan_hash,
            expires_at=expires_at,
        )
    )
    incident.status = "AWAITING_APPROVAL"
    event(
        session,
        incident,
        "proposal",
        "A sandbox action requires human approval",
        {"proposal_id": proposal.id},
    )
    audit(session, principal, "action.proposed", proposal, {"plan_hash": proposal.plan_hash})
    return proposal


def decide(session, principal, approval_id, body):
    principal.require("approve")
    # Lock order is always proposal → approval, including worker claims.
    lookup = scoped_get(session, Approval, approval_id, principal)
    proposal = scoped_get(session, ActionProposal, lookup.proposal_id, principal, for_update=True)
    approval = scoped_get(session, Approval, approval_id, principal, for_update=True)
    if proposal.state != "AWAITING_APPROVAL" or approval.decision:
        raise HTTPException(409, "Approval already decided or action no longer valid")
    validate_policy(session, proposal, principal)
    if approval.expires_at <= now() or proposal.expires_at <= now():
        raise HTTPException(409, "Approval expired")
    if body.plan_hash != proposal.plan_hash or approval.plan_hash != proposal.plan_hash:
        raise HTTPException(409, "Plan hash mismatch")
    if body.decision == "APPROVE":
        resource = scoped_get(
            session, SandboxResource, str(proposal.plan["resource_id"]), principal, for_update=True
        )
        if resource.healthy or resource.revision != proposal.plan["parameters"]["expected_revision"]:
            raise HTTPException(409, "Action preconditions changed before approval")
    approval.decision = body.decision
    approval.approver_id = principal.user_id
    approval.decided_at = now()
    approval.expires_at = min(proposal.expires_at, now() + timedelta(minutes=15))
    transition(proposal, "APPROVED" if body.decision == "APPROVE" else "REJECTED")
    audit(
        session,
        principal,
        "approval.decided",
        approval,
        {"decision": body.decision, "plan_hash": proposal.plan_hash},
    )
    return approval


class SandboxExecutor:
    capabilities = Capabilities(frozenset({"sandbox.recover"}), read_only=False)

    def execute(self, resource, expected_revision: int) -> dict:
        if resource.revision != expected_revision or resource.healthy:
            raise HTTPException(409, "Sandbox preconditions changed")
        resource.healthy = True
        resource.revision += 1
        return {"expected_revision": expected_revision + 1, "synthetic": True}

    def verify(self, resource, result: dict) -> bool:
        return resource.healthy and resource.revision == result["expected_revision"]


def execute(proposal_id: str, actor_id: str, tenant_id: str, adapter: ExecutionAdapter | None = None):
    adapter = adapter or SandboxExecutor()
    # Commit the single-use claim before calling any handler. A crash requires reconciliation, never redispatch.
    with transaction() as session:
        principal = resolve_principal(session, actor_id, tenant_id)
        principal.require("execute")
        proposal = scoped_get(session, ActionProposal, proposal_id, principal, for_update=True)
        approval = session.scalar(
            select(Approval).where(Approval.proposal_id == proposal.id).with_for_update()
        )
        if (
            proposal.state != "APPROVED"
            or not approval
            or approval.decision != "APPROVE"
            or approval.consumed_at
        ):
            raise HTTPException(409, "An unused explicit human approval is required")
        plan = validate_policy(session, proposal, principal)
        approver = resolve_principal(session, approval.approver_id, tenant_id)
        approver.require("approve")
        if not approver.permits_environment(proposal.environment_id):
            raise HTTPException(403, "Approver no longer has environment access")
        if approval.expires_at <= now() or proposal.expires_at <= now():
            transition(proposal, "EXPIRED")
            audit(session, principal, "action.expired", proposal)
            return {"status": "EXPIRED"}
        if approval.plan_hash != proposal.plan_hash:
            raise HTTPException(409, "Approved plan hash does not match")
        adapter.capabilities.require(plan.action_type)
        resource = scoped_get(session, SandboxResource, str(plan.resource_id), principal, for_update=True)
        if resource.revision != plan.parameters.expected_revision or resource.healthy:
            raise HTTPException(409, "Preconditions changed since approval")
        approval.consumed_at = now()
        transition(proposal, "EXECUTING")
        execution = ActionExecution(
            tenant_id=tenant_id,
            environment_id=proposal.environment_id,
            proposal_id=proposal.id,
            status="EXECUTING",
        )
        session.add(execution)
        audit(session, principal, "execution.claimed", proposal)
    try:
        with transaction() as session:
            principal = resolve_principal(session, actor_id, tenant_id)
            principal.require("execute")
            proposal = scoped_get(session, ActionProposal, proposal_id, principal, for_update=True)
            plan = validate_policy(session, proposal, principal)
            if proposal.state != "EXECUTING":
                raise HTTPException(409, "Execution claim is no longer active")
            resource = scoped_get(session, SandboxResource, str(plan.resource_id), principal, for_update=True)
            result = adapter.execute(resource, plan.parameters.expected_revision)
            session.flush()
            transition(proposal, "VERIFYING")
            # Query the persisted target independently of the handler's return value.
            session.refresh(resource)
            verified = adapter.verify(resource, result)
            transition(proposal, "SUCCEEDED" if verified else "FAILED")
            execution = session.scalar(
                select(ActionExecution).where(ActionExecution.proposal_id == proposal_id)
            )
            execution.status, execution.result, execution.completed_at = proposal.state, result, now()
            incident = session.get(Incident, proposal.incident_id)
            incident.status = "MONITORING_RECOVERY" if verified else "INVESTIGATING"
            event(
                session,
                incident,
                "execution",
                "Sandbox action verified" if verified else "Sandbox verification failed",
                {"proposal_id": proposal_id, "status": proposal.state},
            )
            audit(session, principal, "execution.completed", proposal, {"status": proposal.state})
            return {"status": proposal.state, "result": result}
    except Exception as error:
        uncertain = isinstance(error, (TimeoutError, ConnectionError))
        with transaction() as session:
            proposal = session.scalar(
                select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
            )
            if proposal.state in {"EXECUTING", "VERIFYING"}:
                transition(proposal, "RECONCILIATION_REQUIRED" if uncertain else "FAILED")
                execution = session.scalar(
                    select(ActionExecution).where(ActionExecution.proposal_id == proposal_id)
                )
                execution.status = proposal.state
                execution.result = {"error_code": "outcome_uncertain" if uncertain else "handler_failed"}
                execution.completed_at = now()
                audit(session, principal, "execution.failed", proposal, {"status": proposal.state})
            return {"status": proposal.state}


def reconcile(session, principal, proposal_id):
    """Read-only target inspection after uncertain execution; never replays the mutation."""
    principal.require("execute")
    proposal = scoped_get(session, ActionProposal, proposal_id, principal, for_update=True)
    if proposal.state not in {"RECONCILIATION_REQUIRED", "UNKNOWN"}:
        raise HTTPException(409, "This action does not require reconciliation")
    plan = validate_policy(session, proposal, principal)
    approval = session.scalar(select(Approval).where(Approval.proposal_id == proposal.id))
    if not approval or not approval.consumed_at or approval.plan_hash != proposal.plan_hash:
        raise HTTPException(409, "No valid consumed approval exists")
    resource = scoped_get(session, SandboxResource, str(plan.resource_id), principal)
    if proposal.state == "UNKNOWN":
        transition(proposal, "RECONCILIATION_REQUIRED")
    verified = SandboxExecutor().verify(
        resource, {"expected_revision": plan.parameters.expected_revision + 1}
    )
    outcome = (
        "SUCCEEDED"
        if verified
        else (
            "FAILED"
            if resource.revision == plan.parameters.expected_revision and not resource.healthy
            else "UNKNOWN"
        )
    )
    transition(proposal, outcome)
    execution = session.scalar(select(ActionExecution).where(ActionExecution.proposal_id == proposal.id))
    if execution:
        execution.status, execution.completed_at = outcome, now()
        execution.result = {"reconciled": True, "verified": verified, "synthetic": True}
    audit(session, principal, "execution.reconciled", proposal, {"status": outcome})
    return proposal
