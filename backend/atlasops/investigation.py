"""Bounded read-only investigation orchestration. Deliberately has no execution/approval imports."""

import json
import time
from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from atlasops.access import audit, scoped_query
from atlasops.adapters import registry
from atlasops.adapters.ai import ai_configuration_status, validate_finding
from atlasops.adapters.contracts import AdapterError, AIProvider
from atlasops.ai_schemas import InvestigationStep
from atlasops.auth import resolve_principal
from atlasops.config import settings
from atlasops.diagnostics import EvidenceQuery, registered_tools, run_diagnostic
from atlasops.models import Environment, now
from atlasops.schemas import Finding


@dataclass
class Budget:
    deadline: float
    max_iterations: int
    max_tool_calls: int
    iterations: int = 0
    tool_calls: int = 0
    queries: set[str] = field(default_factory=set)

    def check_time(self, clock):
        if clock() >= self.deadline:
            raise AdapterError("investigation_deadline_exhausted")


@dataclass
class InvestigationResult:
    status: str
    finding: Finding
    evidence: list[dict]
    metadata: dict
    error_code: str | None = None

    def as_dict(self):
        return {
            **self.finding.model_dump(),
            "evidence": self.evidence,
            **self.metadata,
            "error_code": self.error_code,
        }


def _source_coverage(evidence):
    def matched(source):
        if source == "incidents":
            return [e for e in evidence if e["kind"] == "incident"]
        if source == "deployments":
            return [e for e in evidence if e["kind"] == "deployment"]
        if source == "observations":
            return [e for e in evidence if e["kind"] not in {"incident", "deployment"}]
        if source == "logs":
            return [
                e
                for e in evidence
                if e["kind"] == "log_reference"
                or (
                    e["kind"] not in {"incident", "deployment"}
                    and isinstance(references := e["data"].get("log_references"), list)
                    and references
                    and all(isinstance(reference, str) and reference.strip() for reference in references)
                )
            ]
        key = {"metrics": "metric", "traces": "trace_id"}[source]
        return [e for e in evidence if key in e["data"]]

    return {
        source: {
            "status": "available" if (rows := matched(source)) else "missing",
            "count": len(rows),
            "latest_observation": max((e["observed_at"] for e in rows), default=None),
            "capability": "stored references only" if source in {"logs", "traces"} else "stored records",
        }
        for source in ("incidents", "observations", "metrics", "deployments", "logs", "traces")
    }


def _missing(coverage, clipped):
    messages = [
        f"{source}: no authorized records in the investigation window"
        for source, value in coverage.items()
        if value["status"] == "missing"
    ]
    messages += [
        "Raw external log content was not retrieved",
        "External trace/span payloads were not retrieved",
    ]
    if clipped:
        messages.append(
            "Evidence is partial: field redaction/truncation, record, query-result or context-size limits applied"
        )
    return messages


def _correlations(evidence):
    """Links are shared identifiers or temporal candidates, never inferred proof of causation."""
    groups = {}
    for record in evidence:
        for key in ("resource", "route", "trace_id", "span_id", "deployment_revision"):
            value = record.get("resource") if key == "resource" else record["data"].get(key)
            if isinstance(value, str) and value:
                groups.setdefault((key, value), []).append(record["id"])
        if record["kind"] == "deployment" and record["data"].get("revision"):
            groups.setdefault(("deployment_revision", record["data"]["revision"]), []).append(record["id"])
    return [
        {
            "relation": "shared_identifier",
            "field": key,
            "value": value,
            "evidence_ids": list(dict.fromkeys(ids)),
        }
        for (key, value), ids in groups.items()
        if len(set(ids)) > 1
    ][:30]


def investigate(
    session, principal, incident, *, provider: AIProvider | None = None, use_ai=True, clock=time.monotonic
) -> InvestigationResult:
    config = settings()
    budget = Budget(
        clock() + config.ai_max_elapsed_seconds, config.ai_max_iterations, config.ai_max_tool_calls
    )
    end = min(now(), incident.last_observed_at + timedelta(minutes=30))
    start = max(
        incident.first_observed_at - timedelta(minutes=30),
        end - timedelta(seconds=config.ai_max_query_window_seconds),
    )
    # If observations span many hours, this run examines the latest bounded window explicitly.
    known: dict[str, dict] = {}
    history = []
    clipped = False

    def revalidate():
        current = resolve_principal(session, principal.user_id, principal.tenant_id)
        current.require("operate")
        environment = session.scalar(
            scoped_query(Environment, current)
            .where(Environment.id == incident.environment_id)
            .execution_options(populate_existing=True)
        )
        if not environment:
            raise HTTPException(403, "Investigation environment access revoked")
        if environment.resource_scope and any(
            e["kind"] not in {"incident", "deployment"} and e["resource"] not in environment.resource_scope
            for e in known.values()
        ):
            raise HTTPException(403, "Investigation resource scope changed")

    def collect(query):
        nonlocal clipped
        budget.check_time(clock)
        if budget.tool_calls >= budget.max_tool_calls:
            raise AdapterError("investigation_tool_budget_exhausted")
        if query.start < start or query.end > end:
            raise AdapterError("diagnostic_window_denied")
        key = query.model_dump_json()
        if key in budget.queries:
            raise AdapterError("diagnostic_repeated_query")
        budget.tool_calls += 1
        budget.queries.add(key)
        records = run_diagnostic(session, principal, query)
        budget.check_time(clock)
        added = 0
        for record in records:
            if record.get("data_limited"):
                clipped = True
            if record["id"] in known:
                continue
            if len(known) >= config.ai_max_evidence:
                clipped = True
                break
            # The rest of the context/schema has reserved space in the per-request budget.
            candidate = [*known.values(), record]
            if len(json.dumps(candidate, ensure_ascii=False).encode()) > config.ai_max_context_bytes // 2:
                clipped = True
                continue
            known[record["id"]] = record
            added += 1
        if len(records) == query.limit:
            clipped = True
        history.append(
            {
                "tool": query.tool,
                "start": query.start.isoformat(),
                "end": query.end.isoformat(),
                "resource": query.resource,
                "limit": query.limit,
                "returned": len(records),
                "added": added,
            }
        )

    def result(status, finding=None, error_code=None):
        records = list(known.values())
        coverage = _source_coverage(records)
        missing = _missing(coverage, clipped)
        if finding is None:
            finding = Finding(
                classification="insufficient_evidence",
                confidence=0,
                summary=(
                    "AI investigation is unavailable. Authorized evidence has been collected for human review."
                    if status == "AI_UNAVAILABLE"
                    else "The investigation could not establish a reliable root cause within its verified evidence and limits."
                ),
                evidence_ids=[e["id"] for e in records][:50],
                missing_data=missing,
                next_queries=["Review source coverage and collect the missing authorized telemetry"],
            )
        else:
            finding = finding.model_copy(
                update={"missing_data": list(dict.fromkeys(finding.missing_data + missing))[:20]}
            )
            # Record/reference presence alone cannot prove a confirmed cause. Preserve useful hypotheses.
            if finding.classification in {"confirmed", "probable"}:
                support = [e for e in records if e["id"] in finding.evidence_ids and e["kind"] != "incident"]
                if len(support) < 2 or (
                    finding.classification == "confirmed"
                    and (len({e["source"] for e in support}) < 2 or clipped)
                ):
                    finding = finding.model_copy(
                        update={
                            "classification": "hypothesis",
                            "confidence": min(0.5, finding.confidence),
                            "missing_data": list(
                                dict.fromkeys(
                                    finding.missing_data
                                    + ["Independent corroboration of the proposed root cause is insufficient"]
                                )
                            )[:20],
                        }
                    )
        metadata = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "sources": coverage,
            "correlations": _correlations(records),
            "evidence_partial": clipped,
            "planner": {
                "iterations": budget.iterations,
                "tool_calls": budget.tool_calls,
                "max_iterations": budget.max_iterations,
                "max_tool_calls": budget.max_tool_calls,
                "termination_reason": error_code or status.lower(),
                "elapsed_seconds": round(
                    max(0, config.ai_max_elapsed_seconds - (budget.deadline - clock())), 3
                ),
            },
            "diagnostic_queries": history,
            "verification": "model-generated findings require human assessment",
        }
        audit(
            session,
            principal,
            "investigation.planner_finished",
            incident,
            {
                "status": status,
                "iterations": budget.iterations,
                "tool_calls": budget.tool_calls,
                "error_code": error_code,
            },
        )
        return InvestigationResult(status, finding, records, metadata, error_code)

    try:
        # Initial collection is included in the tool-call budget. These are the same registered handlers.
        for tool in ("incident.read", "evidence.read", "deployments.read"):
            collect(EvidenceQuery(tool=tool, incident_id=incident.id, start=start, end=end, limit=25))
        availability = ai_configuration_status()
        if not use_ai or (provider is None and not availability["available"]):
            return result(
                "AI_UNAVAILABLE",
                error_code="ai_disabled_for_request" if not use_ai else availability["reason"],
            )
        provider = provider or registry.ai_provider()
        provider.capabilities.require("investigation.plan")
        for _ in range(budget.max_iterations):
            budget.check_time(clock)
            revalidate()
            budget.iterations += 1
            context = {
                "incident_id": incident.id,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "evidence": list(known.values()),
                "sources": _source_coverage(list(known.values())),
                "correlations": _correlations(list(known.values())),
                "registered_tools": registered_tools(),
                "diagnostic_history": history,
                "remaining_iterations": budget.max_iterations - budget.iterations,
                "remaining_tool_calls": budget.max_tool_calls - budget.tool_calls,
                "missing_data": _missing(_source_coverage(list(known.values())), clipped),
            }
            if len(json.dumps(context, ensure_ascii=False).encode()) > config.ai_max_context_bytes:
                raise AdapterError("ai_context_budget_exhausted")
            step = provider.next_step(context, deadline=budget.deadline)
            budget.check_time(clock)
            # Validate even a custom provider's return value at the application boundary.
            step = InvestigationStep.model_validate(step.model_dump())
            if step.finding:
                revalidate()
                finding = validate_finding(step.finding.model_dump(), list(known.values()))
                return result("COMPLETED", finding=finding)
            if len(step.requests) > budget.max_tool_calls - budget.tool_calls:
                raise AdapterError("investigation_tool_budget_exhausted")
            if budget.iterations == budget.max_iterations:
                raise AdapterError("investigation_iteration_budget_exhausted")
            for request in step.requests:
                collect(EvidenceQuery(incident_id=incident.id, **request.model_dump()))
        raise AdapterError("investigation_iteration_budget_exhausted")
    except AdapterError as error:
        exhausted = error.code.endswith("exhausted")
        return result("BUDGET_EXHAUSTED" if exhausted else "FAILED", error_code=error.code)
    except ValidationError:
        return result("FAILED", error_code="invalid_diagnostic_request")
    except HTTPException:
        return result("FAILED", error_code="diagnostic_access_denied")
    # SQL timeouts invalidate the transaction: let the worker roll it back instead of claiming success.
    except SQLAlchemyError:
        raise AdapterError("diagnostic_database_unavailable")
