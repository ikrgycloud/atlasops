"""Provider-neutral schemas. None of these objects can carry execution authority."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from atlasops.schemas import Finding, StrictModel

DiagnosticName = Literal[
    "incident.read",
    "evidence.read",
    "metrics.read",
    "deployments.read",
    "logs.references",
    "traces.references",
]


class DiagnosticRequest(StrictModel):
    tool: DiagnosticName
    start: datetime
    end: datetime
    resource: str | None = Field(default=None, min_length=1, max_length=255)
    limit: int = Field(default=25, ge=1, le=50)


class InvestigationStep(StrictModel):
    requests: list[DiagnosticRequest] = Field(default_factory=list, max_length=4)
    finding: Finding | None = None

    @model_validator(mode="after")
    def one_kind_of_step(self):
        if bool(self.requests) == bool(self.finding):
            raise ValueError("Return diagnostic requests OR one final finding")
        return self
