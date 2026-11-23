"""The database: Tubes' schema (`tubes`) in the shared PostgreSQL server, through strata_python.db (SQLAlchemy models in models.py, Alembic
migrations in migrations/, applied on first use). Which database: `STRATA_DB_URL`, else `TUBES_DATABASE_URL`, else the shared server named by
`STRATA_DB_DATABASE` over its Unix socket; a plain path means SQLite, which the tests use and which suits a quick local run (`data/tubes.db`).
A real Postgres database is refused unless the process has `STRATA_DB_LIVE=1` (the service units set it) and always under pytest.
There is deliberately no SQLite fallback when nothing is set: a service that lost its environment should fail to start, not serve an empty library.

Queries are plain SQL that runs on both engines (no Postgres-only features). `connect()` gives one transaction, committed when the block
ends and rolled back on an error; its `execute` takes `?` placeholders with a tuple, or `:name` with a dict, so call sites stay short."""

import contextlib
import threading
from collections.abc import Generator, Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import Connection as SaConnection
from sqlalchemy import CursorResult, Engine, Result, text
from strata_python.db import Project, url_for
from strata_python.db import connect as connect_engine

APP = "tubes"
_engines: dict[str, Engine] = {}  # url -> migrated engine
# Alembic keeps the running migration in module globals, so two threads migrating at once (a request and a background prefetch on a
# fresh database, or a test's leftover thread) break each other (KeyError: 'script'): one migration at a time, and once per URL.
_migrating = threading.Lock()


def url() -> str:
    return url_for(APP)


def engine() -> Engine:
    """The engine for the current URL, migrated to head the first time it is asked for in this process."""
    u = url()
    if u not in _engines:
        with _migrating:
            if u not in _engines:
                e = connect_engine(u)
                Project.load(__file__).upgrade(e)
                _engines[u] = e
    return _engines[u]


def reset() -> None:
    """Forget every engine (tests point the URL somewhere new for each test)."""
    for e in _engines.values():
        e.dispose()
    _engines.clear()


Params = Mapping[str, Any] | Sequence[Any] | None
Row = dict[str, Any]  # a row as the API sends it: column name -> value


def _named(sql: str, params: Params) -> tuple[str, Mapping[str, Any]]:
    """`?` placeholders and a tuple, as named ones and a dict (SQLAlchemy's text() takes named only)."""
    if params is None:
        return sql, {}
    if isinstance(params, Mapping):
        return sql, params
    parts = sql.split("?")
    if len(parts) - 1 != len(params):
        raise ValueError(f"{len(parts) - 1} placeholders but {len(params)} values")
    return "".join(p + (f":p{i}" if i < len(params) else "") for i, p in enumerate(parts)), {
        f"p{i}": v for i, v in enumerate(params)
    }


class Connection:
    def __init__(self, con: SaConnection) -> None:
        self.con = con

    def execute(self, sql: str, params: Params = None) -> CursorResult[*tuple[Any, ...]]:
        sql, named = _named(sql, params)
        return self.con.execute(text(sql), named)

    def executemany(self, sql: str, rows: Iterable[Mapping[str, Any]]) -> CursorResult[*tuple[Any, ...]] | None:
        many = list(rows)
        return self.con.execute(text(sql), many) if many else None


@contextlib.contextmanager
def connect() -> Generator[Connection]:
    with engine().begin() as con:
        yield Connection(con)


def rows(result: Result[*tuple[Any, ...]]) -> list[Row]:
    return [dict(m) for m in result.mappings()]


def row(result: Result[*tuple[Any, ...]]) -> Row | None:
    m = result.mappings().first()
    return dict(m) if m is not None else None


def one(result: Result[*tuple[Any, ...]]) -> Row:
    """The one row a query always has (an aggregate's); raises if it has none or several."""
    return dict(result.mappings().one())
