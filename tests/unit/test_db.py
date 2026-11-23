import pytest
from tubes import db

# strata_python.db's standard tests: the migrated test database matches the models, and every revision goes up, down and up again on a
# scratch database (what `strata-db check` does), on SQLite and with --pg on Postgres.
from strata_python.db.testing import test_migrations, test_schema_matches_models  # noqa: F401


def test_the_engine_tubes_opens_matches_the_models():
    from strata_python.db import drift
    from tubes.models import Base
    assert drift(db.engine(), Base.metadata) == []


def test_a_unit_of_work_commits_or_is_undone_whole():
    with db.connect() as con: con.execute("INSERT INTO meta (key, value) VALUES ('a', ?)", ('1',))
    with pytest.raises(Exception):
        with db.connect() as con:
            con.execute("INSERT INTO meta (key, value) VALUES (:k, :v)", dict(k='b', v='2'))
            con.execute("INSERT INTO meta (key, value) VALUES ('a', '3')")                     # duplicate key: the whole unit of work is undone
    with db.connect() as con:
        assert db.rows(con.execute('SELECT key, value FROM meta')) == [dict(key='a', value='1')]
        assert db.row(con.execute("SELECT key FROM meta WHERE key = 'b'")) is None
        assert con.executemany('INSERT INTO meta (key) VALUES (:key)', []) is None


def test_placeholders_must_match_the_values():
    with pytest.raises(ValueError, match='2 placeholders but 1 values'), db.connect() as con: con.execute('SELECT ?, ?', (1,))


def test_one_engine_per_url(monkeypatch, tmp_path):
    first = db.engine()
    assert db.engine() is first
    monkeypatch.delenv('STRATA_DB_URL'); monkeypatch.setenv('TUBES_DATABASE_URL', str(tmp_path / 'other.db'))      # the app's own variable (STRATA_DB_URL would win)
    assert db.engine() is not first and db.url().endswith('other.db')
    with db.connect() as con: assert con.execute('SELECT COUNT(*) FROM copies').scalar() == 0     # migrated on first use


def test_threads_asking_at_once_migrate_once_and_one_at_a_time(monkeypatch, tmp_path):
    import threading, time
    from strata_python.db import Project
    monkeypatch.delenv('STRATA_DB_URL'); monkeypatch.setenv('TUBES_DATABASE_URL', str(tmp_path / 'fresh.db'))         # not migrated yet in this process
    running, ran, overlapped = [], [], []
    def upgrade(self, engine):
        if running: overlapped.append(True)
        running.append(1); time.sleep(0.05); ran.append(1); running.pop()
    monkeypatch.setattr(Project, 'upgrade', upgrade)
    threads = [threading.Thread(target=db.engine) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert ran == [1] and overlapped == []
