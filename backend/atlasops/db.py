from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from atlasops.config import settings


@lru_cache
def engine():
    return create_engine(settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)


def session_factory():
    return sessionmaker(engine(), expire_on_commit=False)


@contextmanager
def transaction():
    with session_factory()() as session, session.begin():
        yield session


def get_session():
    with session_factory()() as session:
        yield session


def lock(session: Session, model, object_id: str):
    from sqlalchemy import select

    return session.scalar(select(model).where(model.id == object_id).with_for_update())
