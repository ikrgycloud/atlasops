import argparse

from sqlalchemy import select

from atlasops.config import settings
from atlasops.db import transaction
from atlasops.models import Environment, Membership, SandboxResource, Service, Tenant, User


def seed():
    if settings().mode != "development":
        raise SystemExit("Demo seed is restricted to development")
    with transaction() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.name == "AtlasOps Demo"))
        if tenant:
            print("Demo data already exists; left unchanged")
            return
        tenant = Tenant(name="AtlasOps Demo", demo=True)
        session.add(tenant)
        session.flush()
        for role in ("administrator", "operator", "approver", "viewer"):
            user = User(email=f"{role}@atlasops.local", external_subject=f"development:{role}")
            session.add(user)
            session.flush()
            session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role))
        env = Environment(
            tenant_id=tenant.id,
            name="Recovery sandbox",
            provider="sandbox",
            demo=True,
            description="Synthetic database sandbox; no infrastructure is changed",
        )
        session.add(env)
        session.flush()
        session.add(Service(tenant_id=tenant.id, environment_id=env.id, name="sample-api", owner="Platform"))
        session.add(SandboxResource(tenant_id=tenant.id, environment_id=env.id, name="sample-api"))
    print("Created explicitly labeled demo tenant and four development identities")


def seed_scenario():
    """Create an isolated, explicitly synthetic pilot tenant for each browser test run."""
    if settings().mode != "development":
        raise SystemExit("Synthetic scenarios are development-only")
    import json

    from atlasops.models import new_id

    suffix = new_id()[:8]
    with transaction() as session:
        tenant = Tenant(name="AtlasOps E2E " + suffix, demo=True)
        session.add(tenant)
        session.flush()
        email = f"e2e-{suffix}@atlasops.local"
        user = User(email=email, external_subject="development:e2e:" + suffix)
        session.add(user)
        session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="administrator"))
        env = Environment(tenant_id=tenant.id, name="E2E recovery sandbox", provider="sandbox", demo=True)
        session.add(env)
        session.flush()
        session.add(SandboxResource(tenant_id=tenant.id, environment_id=env.id, name="synthetic-api"))
        session.add(
            Service(tenant_id=tenant.id, environment_id=env.id, name="synthetic-api", owner="Test runner")
        )
    print(json.dumps({"email": email, "tenant_id": tenant.id}))


def provision(email: str, subject: str, tenant_name: str, role: str):
    with transaction() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.name == tenant_name))
        if not tenant:
            tenant = Tenant(name=tenant_name)
            session.add(tenant)
            session.flush()
        user = session.scalar(select(User).where(User.external_subject == subject))
        if not user:
            user = User(email=email, external_subject=subject)
            session.add(user)
            session.flush()
        if session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant.id)
        ):
            raise SystemExit("Membership already exists; change it using an audited administrator procedure")
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role))
    print("Provisioned identity and tenant membership")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    sub.add_parser("seed-scenario")
    p = sub.add_parser("provision-user")
    for field in ("email", "subject", "tenant"):
        p.add_argument(f"--{field}", required=True)
    p.add_argument("--role", choices=["viewer", "operator", "approver", "administrator"], required=True)
    args = parser.parse_args()
    if args.command == "seed":
        seed()
    elif args.command == "seed-scenario":
        seed_scenario()
    else:
        provision(args.email, args.subject, args.tenant, args.role)
