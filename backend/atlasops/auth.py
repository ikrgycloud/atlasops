import hmac
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlasops.config import settings
from atlasops.db import get_session
from atlasops.models import Membership, User, now

PERMISSIONS = {
    "viewer": {"read"},
    "operator": {"read", "operate", "execute", "report"},
    "approver": {"read", "approve"},
    "administrator": {"read", "operate", "execute", "report", "approve", "configure", "audit"},
}


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str
    environment_ids: tuple[str, ...]

    def require(self, permission: str):
        if permission not in PERMISSIONS.get(self.role, set()):
            logging.getLogger("atlasops.security").warning("permission_denied", extra={"actor": self.user_id})
            raise HTTPException(403, "Permission denied")

    def permits_environment(self, environment_id: str) -> bool:
        return "*" in self.environment_ids or environment_id in self.environment_ids


@lru_cache
def jwks_client():
    return jwt.PyJWKClient(settings().oidc_jwks_url, cache_keys=True, timeout=5)


def resolve_principal(session: Session, user_id: str, tenant_id: str) -> Principal:
    user = session.scalar(select(User).where(User.id == user_id).execution_options(populate_existing=True))
    membership = session.scalar(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.tenant_id == tenant_id)
        .execution_options(populate_existing=True)
    )
    if not user or not user.active or not membership or membership.role not in PERMISSIONS:
        raise HTTPException(403, "No active tenant membership")
    return Principal(user_id, tenant_id, membership.role, tuple(membership.environment_ids))


def current_user(
    authorization: str = Header(default=""),
    x_tenant_id: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Principal:
    config = settings()
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("Invalid scheme")
        if config.dev_auth_enabled:
            claims = jwt.decode(
                token,
                config.dev_auth_secret,
                algorithms=["HS256"],
                audience="atlasops",
                issuer="atlasops-development",
                options={"require": ["exp", "iat", "sub", "tid"]},
            )
        else:
            key = jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=config.oidc_audience,
                issuer=config.oidc_issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        user = session.scalar(select(User).where(User.external_subject == claims["sub"]))
        tenant_id = str(UUID(x_tenant_id or claims.get("tid", "")))
        if not user:
            raise ValueError("Unknown user")
    except (ValueError, KeyError, jwt.PyJWTError):
        raise HTTPException(401, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"})
    return resolve_principal(session, user.id, tenant_id)


class DevLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=255)
    secret: str = Field(min_length=1, max_length=512)


_attempts: dict[str, deque] = defaultdict(deque)


def dev_token(body: DevLogin, request: Request, session: Session):
    config = settings()
    if not config.dev_auth_enabled:
        raise HTTPException(404, "Not found")
    address = request.client.host if request.client else "unknown"
    attempts = _attempts[address]
    cutoff = time.monotonic() - 60
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if len(attempts) >= 5:
        raise HTTPException(429, "Too many authentication attempts")
    attempts.append(time.monotonic())
    if not hmac.compare_digest(body.secret, config.dev_auth_secret):
        raise HTTPException(401, "Invalid credentials")
    user = session.scalar(select(User).where(User.email == body.email, User.active.is_(True)))
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id)) if user else None
    if not user or not membership:
        raise HTTPException(401, "Invalid credentials")
    token = jwt.encode(
        {
            "sub": user.external_subject,
            "tid": membership.tenant_id,
            "iss": "atlasops-development",
            "aud": "atlasops",
            "iat": now(),
            "exp": now() + timedelta(hours=1),
        },
        config.dev_auth_secret,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": 3600}
