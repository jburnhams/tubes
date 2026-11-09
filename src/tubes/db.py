"""The database: Tubes' schema (`tubes`) in the shared PostgreSQL server, through omarchy_db (the `database` repo: SQLAlchemy models in
models.py, Alembic migrations in migrations/, applied on first use). Which database: `TUBES_DATABASE_URL` (or `OMARCHY_DB_URL`), else the
shared server over its Unix socket; a plain path means SQLite, which the tests use and which suits a quick local run (`data/tubes.db`).

Queries are plain SQL that runs on both engines (no Postgres-only features). `connect()` gives one transaction, committed when the block
ends and rolled back on an error; its `execute` takes `?` placeholders with a tuple, or `:name` with a dict, so call sites stay short."""
import contextlib

from sqlalchemy import text

from omarchy_db import Project, connect as connect_engine, url_for

APP = 'tubes'
_engines = {}                # url -> migrated engine


def url():
    return url_for(APP)


def engine():
    """The engine for the current URL, migrated to head the first time it is asked for in this process."""
    u = url()
    if u not in _engines:
        e = connect_engine(u); Project.load(__file__).upgrade(e); _engines[u] = e
    return _engines[u]


def reset():
    """Forget every engine (tests point the URL somewhere new for each test)."""
    for e in _engines.values(): e.dispose()
    _engines.clear()


def _named(sql, params):
    """`?` placeholders and a tuple, as named ones and a dict (SQLAlchemy's text() takes named only)."""
    if isinstance(params, dict) or params is None: return sql, params or {}
    parts = sql.split('?')
    if len(parts) - 1 != len(params): raise ValueError(f'{len(parts) - 1} placeholders but {len(params)} values')
    return ''.join(p + (f':p{i}' if i < len(params) else '') for i, p in enumerate(parts)), {f'p{i}': v for i, v in enumerate(params)}


class Connection:
    def __init__(self, con): self.con = con

    def execute(self, sql, params=None):
        sql, params = _named(sql, params)
        return self.con.execute(text(sql), params)

    def executemany(self, sql, rows):
        rows = list(rows)
        return self.con.execute(text(sql), rows) if rows else None


@contextlib.contextmanager
def connect():
    with engine().begin() as con: yield Connection(con)


def rows(result):
    return [dict(r._mapping) for r in result]


def row(result):
    r = result.first(); return dict(r._mapping) if r is not None else None


