from alembic import context

from atlasops.db import engine
from atlasops.models import Base


def run():
    if context.is_offline_mode():
        from atlasops.config import settings

        context.configure(url=settings().database_url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        with engine().connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()


run()
