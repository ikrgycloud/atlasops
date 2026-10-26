from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from atlasops.schemas import Finding


class AdapterError(Exception):
    """A stable, non-secret error code safe for API responses."""

    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class Capabilities:
    operations: frozenset[str]
    read_only: bool = True

    def require(self, operation: str):
        if operation not in self.operations:
            raise AdapterError("unsupported_operation")


class InfrastructureAdapter(Protocol):
    capabilities: Capabilities

    def inventory(self, resource_scope: list[str]) -> list[dict]: ...


class ObservabilityAdapter(Protocol):
    capabilities: Capabilities

    def query(self, expression: str, at: datetime) -> dict: ...


class CICDAdapter(Protocol):
    capabilities: Capabilities

    def runs(self) -> list[dict]: ...


class NotificationAdapter(Protocol):
    capabilities: Capabilities

    def send(self, recipient: str, subject: str, body: str, message_id: str) -> None: ...


class SecretProvider(Protocol):
    def get(self, reference: str) -> str: ...


class AIProvider(Protocol):
    capabilities: Capabilities

    def investigate(self, evidence: list[dict]) -> Finding: ...


class ExecutionAdapter(Protocol):
    capabilities: Capabilities

    def execute(self, resource, expected_revision: int) -> dict: ...
    def verify(self, resource, result: dict) -> bool: ...
