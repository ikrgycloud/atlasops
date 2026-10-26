"""Composition root: application services request interfaces from these replaceable factories."""

from atlasops.adapters.ai import CompatibleAI
from atlasops.adapters.aws import AWS
from atlasops.adapters.cicd import GitHubActions, Jenkins
from atlasops.adapters.contracts import AIProvider, CICDAdapter, InfrastructureAdapter, ObservabilityAdapter
from atlasops.adapters.observability import Grafana, Prometheus


def infrastructure(config: dict) -> InfrastructureAdapter:
    return AWS(config)


def observability(config: dict, secret_ref=None) -> ObservabilityAdapter:
    return Prometheus(config, secret_ref)


def cicd(provider: str, config: dict, secret_ref=None) -> CICDAdapter:
    return GitHubActions(config, secret_ref) if provider == "github" else Jenkins(config, secret_ref)


def dashboards(config: dict, secret_ref=None) -> Grafana:
    return Grafana(config, secret_ref)


def ai_provider() -> AIProvider:
    return CompatibleAI()
