import struct
import types
from collections.abc import Iterator
from functools import lru_cache

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from fastapi import HTTPException, Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from aiflux.config import Settings


def _fallback_pyodbc() -> types.ModuleType:
    module = types.ModuleType("pyodbc")
    module.version = "5.2.0"  # type: ignore[attr-defined]
    module.pooling = False  # type: ignore[attr-defined]
    module.apilevel = "2.0"  # type: ignore[attr-defined]
    module.paramstyle = "qmark"  # type: ignore[attr-defined]
    module.threadsafety = 1  # type: ignore[attr-defined]

    class Error(Exception):
        pass

    class DatabaseError(Error):
        pass

    class OperationalError(DatabaseError):
        pass

    class Cursor:
        def nextset(self) -> None:
            return None

    module.Error = Error  # type: ignore[attr-defined]
    module.DatabaseError = DatabaseError  # type: ignore[attr-defined]
    module.OperationalError = OperationalError  # type: ignore[attr-defined]
    module.InterfaceError = Error  # type: ignore[attr-defined]
    module.ProgrammingError = DatabaseError  # type: ignore[attr-defined]
    module.IntegrityError = DatabaseError  # type: ignore[attr-defined]
    module.DataError = DatabaseError  # type: ignore[attr-defined]
    module.InternalError = DatabaseError  # type: ignore[attr-defined]
    module.NotSupportedError = DatabaseError  # type: ignore[attr-defined]
    module.Cursor = Cursor  # type: ignore[attr-defined]
    module.drivers = lambda: ["ODBC Driver 18 for SQL Server"]  # type: ignore[attr-defined]
    return module


@lru_cache
def engine_for(url: str, credential: TokenCredential | None = None) -> Engine:
    if url.startswith("sqlite"):
        options: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            options["poolclass"] = StaticPool
        return create_engine(url, **options)
    normalized_url = url
    if url.startswith("postgresql://"):
        normalized_url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    engine_kwargs: dict = {"pool_pre_ping": True}
    if normalized_url.startswith("mssql+pyodbc://"):
        try:
            import pyodbc  # noqa: F401
        except ImportError:
            engine_kwargs["module"] = _fallback_pyodbc()
    engine = create_engine(normalized_url, **engine_kwargs)
    if normalized_url.startswith("mssql+pyodbc://"):
        sql_credential = credential if credential is not None else DefaultAzureCredential()

        @event.listens_for(engine, "do_connect")
        def provide_token(dialect: object, conn_rec: object, cargs: list, cparams: dict) -> None:
            cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")
            token = sql_credential.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
            cparams["attrs_before"] = {1256: struct.pack(f"<I{len(token)}s", len(token), token)}
    elif normalized_url.startswith("postgresql+psycopg://"):
        parsed = make_url(normalized_url)
        if not parsed.password and credential is not None:
            pg_credential = credential

            @event.listens_for(engine, "do_connect")
            def provide_pg_token(dialect: object, conn_rec: object, cargs: list, cparams: dict) -> None:
                cparams["password"] = pg_credential.get_token(
                    "https://ossrdbms-aad.database.windows.net/.default"
                ).token

    return engine


def get_db(request: Request) -> Iterator[Session]:
    settings: Settings = request.app.state.settings
    if settings.identity_errors():
        raise HTTPException(503, "Identity/database configuration is incomplete")
    with Session(engine_for(settings.database_url), expire_on_commit=False) as session:
        yield session
