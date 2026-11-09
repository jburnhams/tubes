import pytest
from tubes import db
from tubes.models import Base
from omarchy_db import drift


def test_schema_matches_models():
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
    monkeypatch.setenv('TUBES_DATABASE_URL', str(tmp_path / 'other.db'))
    assert db.engine() is not first and db.url().endswith('other.db')
    with db.connect() as con: assert con.execute('SELECT COUNT(*) FROM copies').scalar() == 0     # migrated on first use
