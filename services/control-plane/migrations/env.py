from aiflux.config import get_settings
from aiflux.db import engine_for
from aiflux.models import Base
from alembic import context
from sqlalchemy import Connection

supplied_connection = context.config.attributes.get("connection")
settings = get_settings() if supplied_connection is None else None
url = context.config.get_main_option("sqlalchemy.url") or (settings.database_url if settings else None)
if supplied_connection is None and not url:
    raise RuntimeError("AIFLUX_DATABASE_URL is required for migrations")

if context.is_offline_mode():
    context.configure(
        url=url, target_metadata=Base.metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    def migrate(connection: Connection) -> None:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()

    if supplied_connection is not None:
        migrate(supplied_connection)
    else:
        with engine_for(url).connect() as connection:
            migrate(connection)
