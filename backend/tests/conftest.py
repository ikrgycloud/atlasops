import os
from datetime import timedelta
from pathlib import Path

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from atlasops.config import settings
from atlasops.db import engine, transaction
from atlasops.models import Environment, Membership, Tenant, User, now

# A dedicated local test database; never truncate the application database.
original_url = make_url(settings().database_url)
test_url = original_url.set(database="atlasops_test")
with create_engine(original_url, isolation_level="AUTOCOMMIT").connect() as conn:
    if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname='atlasops_test'")):
        conn.execute(text("CREATE DATABASE atlasops_test"))
os.environ["ATLAS_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
# Test execution must never use a developer's actual AI credentials or make paid model calls.
os.environ["OPENAI_API_KEY"] = ""
os.environ["ATLAS_AI_URL"] = ""
os.environ["ATLAS_AI_MODEL"] = ""
os.environ["ATLAS_AI_PROVIDER"] = "compatible"
os.environ["ATLAS_AI_SECRET_REF"] = ""
settings.cache_clear()
engine.cache_clear()
command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")

from atlasops.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    from atlasops.models import Base

    with engine().begin() as conn:
        names = ", ".join(f'"{name}"' for name in Base.metadata.tables)
        conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def identities():
    result = {}
    with transaction() as session:
        for label in ("a", "b"):
            tenant = Tenant(name=label, demo=True)
            session.add(tenant)
            session.flush()
            env = Environment(tenant_id=tenant.id, name=f"{label}-sandbox", provider="sandbox", demo=True)
            session.add(env)
            session.flush()
            result[label] = {"tenant": tenant.id, "environment": env.id}
            for role in ("administrator", "operator", "approver", "viewer"):
                user = User(email=f"{label}-{role}@test.local", external_subject=f"test:{label}:{role}")
                session.add(user)
                session.flush()
                session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role))
                token = jwt.encode(
                    {
                        "sub": user.external_subject,
                        "tid": tenant.id,
                        "iss": "atlasops-development",
                        "aud": "atlasops",
                        "iat": now(),
                        "exp": now() + timedelta(minutes=30),
                    },
                    settings().dev_auth_secret,
                    algorithm="HS256",
                )
                result[label][role] = {"Authorization": f"Bearer {token}"}
                result[label][f"{role}_id"] = user.id
    return result


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def ai_config(monkeypatch):
    config = settings()
    for key, value in {
        "ai_provider": "openai",
        "ai_url": "https://api.openai.com/v1",
        "ai_model": "operator-selected-test-model",
        "openai_api_key": SecretStr("test-only-openai-credential"),
        "ai_secret_ref": "",
        "ai_allowed_hosts": "api.openai.com",
        "ai_response_format": "json_schema",
        "ai_token_parameter": "max_completion_tokens",
    }.items():
        monkeypatch.setattr(config, key, value)
    return config
