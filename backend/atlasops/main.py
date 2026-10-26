import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from atlasops.access import audit, scoped_get, scoped_query
from atlasops.auth import DevLogin, Principal, current_user, dev_token
from atlasops.config import settings
from atlasops.db import engine, get_session
from atlasops.logging import configure_logging
from atlasops.models import (
    ActionExecution,
    BackgroundJob,
    Environment,
    Integration,
    NotificationDelivery,
    Service,
    Tenant,
    User,
    public_record,
)
from atlasops.schemas import EnvironmentInput, ServiceInput

REQUESTS = Counter("atlasops_http_requests_total", "Requests", ["method", "route", "status"])
JOBS = Gauge("atlasops_durable_jobs", "Persisted jobs by state", ["status"])
INTEGRATIONS = Gauge("atlasops_integrations", "Integration state", ["status"])
DELIVERIES = Gauge("atlasops_email_deliveries", "Persisted email deliveries", ["status"])
EXECUTIONS = Gauge("atlasops_executions", "Persisted execution outcomes", ["status"])
LATENCY = Histogram("atlasops_http_request_seconds", "Request latency", ["route"])


@asynccontextmanager
async def lifespan(app):
    settings()
    configure_logging()
    yield


app = FastAPI(title="AtlasOps AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings().allowed_hosts.split(","))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"error": {"code": "invalid_length", "message": "Invalid content length"}}, 400)
    if content_length > 1024 * 1024:
        return JSONResponse({"error": {"code": "body_too_large", "message": "Request exceeds 1 MiB"}}, 413)
    start = time.monotonic()
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    REQUESTS.labels(request.method, route, response.status_code).inc()
    LATENCY.labels(route).observe(time.monotonic() - start)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(request, error):
    return JSONResponse(
        {"error": {"code": str(error.status_code), "message": error.detail}},
        error.status_code,
        headers=error.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    # Pydantic's default response echoes inputs, which may contain credentials.
    return JSONResponse(
        {
            "error": {
                "code": "validation_error",
                "message": "Invalid request",
                "fields": [".".join(map(str, e["loc"])) for e in error.errors()],
            }
        },
        422,
    )


@app.exception_handler(IntegrityError)
async def conflict(request, error):
    return JSONResponse(
        {"error": {"code": "conflict", "message": "Record conflicts with existing state"}}, 409
    )


@app.exception_handler(Exception)
async def internal_error(request, error):
    logging.getLogger("atlasops").error("unhandled_error")
    return JSONResponse({"error": {"code": "internal_error", "message": "Internal operation failed"}}, 500)


@app.get("/health/live")
def live():
    return {"status": "live"}


@app.get("/health/ready")
def ready():
    try:
        with engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT version_num FROM alembic_version"))
        Redis.from_url(settings().redis_url, socket_timeout=2).ping()
    except Exception:
        raise HTTPException(503, "Database, migrations, or broker unavailable")
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    from atlasops.db import session_factory

    with session_factory()() as session:
        for gauge, model in [
            (JOBS, BackgroundJob),
            (INTEGRATIONS, Integration),
            (DELIVERIES, NotificationDelivery),
            (EXECUTIONS, ActionExecution),
        ]:
            gauge.clear()
            for status, count in session.execute(select(model.status, func.count()).group_by(model.status)):
                gauge.labels(status=status).set(count)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/auth/dev-token")
def login(body: DevLogin, request: Request, session: Session = Depends(get_session)):
    return dev_token(body, request, session)


@app.get("/api/v1/me")
def me(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    user = session.get(User, p.user_id)
    tenant = session.get(Tenant, p.tenant_id)
    return {
        "user_id": user.id,
        "email": user.email,
        "tenant_id": p.tenant_id,
        "role": p.role,
        "environment_ids": p.environment_ids,
        "demo": tenant.demo,
        "tenant_name": tenant.name,
        "ai_available": bool(settings().ai_url),
    }


def page(session: Session, model, principal: Principal, limit=25, offset=0, query=None):
    query = query if query is not None else scoped_query(model, principal)
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = session.scalars(query.order_by(model.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [public_record(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@app.get("/api/v1/environments")
def environments(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    query = scoped_query(Environment, p)
    if "*" not in p.environment_ids:
        query = query.where(Environment.id.in_(p.environment_ids))
    return page(session, Environment, p, query=query)


@app.post("/api/v1/environments", status_code=201)
def create_environment(
    body: EnvironmentInput, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("configure")
    if "*" not in p.environment_ids:
        raise HTTPException(403, "Tenant-wide configuration permission required")
    row = Environment(tenant_id=p.tenant_id, **body.model_dump())
    session.add(row)
    session.flush()
    audit(session, p, "environment.registered", row)
    session.commit()
    return public_record(row)


@app.get("/api/v1/environments/{object_id}")
def environment_detail(
    object_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    row = scoped_get(session, Environment, str(object_id), p)
    if not p.permits_environment(row.id):
        raise HTTPException(404, "Not found")
    return public_record(row)


@app.get("/api/v1/services")
def services(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    return page(session, Service, p)


@app.post("/api/v1/services", status_code=201)
def create_service(
    body: ServiceInput, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("configure")
    env = scoped_get(session, Environment, str(body.environment_id), p)
    if not p.permits_environment(env.id):
        raise HTTPException(404, "Not found")
    row = Service(tenant_id=p.tenant_id, **body.model_dump(mode="json"))
    session.add(row)
    session.flush()
    audit(session, p, "service.registered", row)
    session.commit()
    return public_record(row)


@app.get("/api/v1/services/{object_id}")
def service_detail(
    object_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    return public_record(scoped_get(session, Service, str(object_id), p))


# Keep the application services independent of the HTTP layer.
from atlasops.api import router  # noqa: E402

app.include_router(router)

from opentelemetry import trace  # noqa: E402
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402

trace.set_tracer_provider(TracerProvider())
FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,metrics")
