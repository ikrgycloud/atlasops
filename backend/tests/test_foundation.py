from sqlalchemy import select

from atlasops.db import transaction
from atlasops.models import Membership


def test_authenticated_tenant_isolation(client, identities):
    a, b = identities["a"], identities["b"]
    assert client.get("/api/v1/environments").status_code == 401
    response = client.get("/api/v1/environments", headers=a["viewer"])
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == a["environment"]
    assert (
        client.get(f"/api/v1/environments/{b['environment']}", headers=a["administrator"]).status_code == 404
    )
    assert client.get("/api/v1/me", headers=a["viewer"]).json()["role"] == "viewer"


def test_permissions_and_current_membership(client, identities):
    headers = identities["a"]["viewer"]
    body = {"name": "new", "provider": "aws"}
    assert client.post("/api/v1/environments", headers=headers, json=body).status_code == 403
    with transaction() as session:
        membership = session.scalar(
            select(Membership).where(Membership.user_id == identities["a"]["viewer_id"])
        )
        session.delete(membership)
    assert client.get("/api/v1/me", headers=headers).status_code == 403


def test_environment_scoping(client, identities):
    a = identities["a"]
    with transaction() as session:
        m = session.scalar(select(Membership).where(Membership.user_id == a["viewer_id"]))
        m.environment_ids = []
    assert client.get("/api/v1/environments", headers=a["viewer"]).json()["total"] == 0
    assert client.get(f"/api/v1/environments/{a['environment']}", headers=a["viewer"]).status_code == 404


def test_validation_redacts_input(client):
    secret = "sensitive-do-not-echo"
    result = client.post(
        "/api/v1/auth/dev-token", json={"email": "x", "secret": secret, "unexpected": secret}
    )
    assert result.status_code == 422
    assert secret not in result.text


def test_readiness_and_invalid_credentials(client):
    assert client.get("/health/live").json()["status"] == "live"
    assert client.get("/health/ready").status_code == 200
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer forged"}).status_code == 401


def test_oidc_signature_issuer_audience_and_expiry(client, identities, monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from atlasops.config import settings
    from atlasops.models import now

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings(), "dev_auth_enabled", False)
    monkeypatch.setattr(settings(), "oidc_issuer", "https://issuer.example")
    monkeypatch.setattr(settings(), "oidc_audience", "atlasops")
    monkeypatch.setattr(
        "atlasops.auth.jwks_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())),
    )
    claims = {
        "sub": "test:a:viewer",
        "tid": identities["a"]["tenant"],
        "iss": "https://issuer.example",
        "aud": "atlasops",
        "iat": now(),
        "exp": now() + timedelta(minutes=5),
    }

    def call(value, signing_key=key):
        token = jwt.encode(value, signing_key, algorithm="RS256")
        return client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert call(claims).status_code == 200
    assert call({**claims, "iss": "https://attacker.example"}).status_code == 401
    assert call({**claims, "aud": "other"}).status_code == 401
    assert call({**claims, "exp": now() - timedelta(minutes=1)}).status_code == 401
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert call(claims, other).status_code == 401


def test_cross_tenant_service_reference_and_diagnostic_scope(client, identities):
    a, b = identities["a"], identities["b"]
    response = client.post(
        "/api/v1/services",
        headers=a["administrator"],
        json={"name": "bad-reference", "environment_id": b["environment"]},
    )
    assert response.status_code == 404
    response = client.get(f"/api/v1/environments/{b['environment']}/resources", headers=a["administrator"])
    assert response.status_code == 404
    response = client.post(
        "/api/v1/diagnostics/query",
        headers=a["operator"],
        json={
            "tool": "shell.execute",
            "incident_id": a["environment"],
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
            "command": "id",
        },
    )
    assert response.status_code == 422


def test_initial_migration_upgrade_downgrade_roundtrip():
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from atlasops.db import engine

    assert engine().url.database == "atlasops_test"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(config, "base")
    assert "tenants" not in inspect(engine()).get_table_names()
    command.upgrade(config, "head")
    assert "action_proposals" in inspect(engine()).get_table_names()
    command.check(config)
