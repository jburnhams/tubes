"""Shared pytest configuration: every test is hermetic (its own home and data folder, no network, no stray override variables). Tests under tests/integration get the `integration` marker automatically."""
import os, socket, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
TUNING = ('TUBES_D1_API', 'TUBES_YOUTUBE_API', 'YOUTUBE_API_KEY', 'YOUTUBE_API_REFERER', 'TUBES_CACHE', 'TUBES_YTDLP', 'TUBES_FFMPEG', 'TUBES_D1_DATABASE', 'CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID', 'OMARCHY_DB_URL', 'FAKE_YTDLP_SECONDS', 'FAKE_YTDLP_FAIL')
FAKE_YTDLP = os.path.join(os.path.dirname(__file__), 'utils', 'fake_ytdlp.py')


def pytest_collection_modifyitems(items):
    for item in items:
        if os.sep + 'integration' + os.sep in str(item.fspath): item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path_factory, monkeypatch):
    """`~/.tubes` and the data folder point into a tmp dir (outside the test's own tmp_path), so nothing reads or writes the developer's real settings or data; override variables are removed."""
    base = tmp_path_factory.mktemp('env')
    monkeypatch.setenv('HOME', str(base / 'home')); monkeypatch.setenv('USERPROFILE', str(base / 'home'))
    monkeypatch.setenv('TUBES_HOME', str(base / 'app-home')); monkeypatch.setenv('TUBES_DATA', str(base / 'data'))
    for k in TUNING: monkeypatch.delenv(k, raising=False)
    return base


@pytest.fixture(autouse=True)
def database(db_url, monkeypatch):
    """Every test gets its own migrated database (omarchy_db's `db_url`: a SQLite copy of a template migrated once; `pytest --pg` uses a throwaway
    Postgres database instead), through the same TUBES_DATABASE_URL a deployment would set, so subprocesses (the integration suite) use it too."""
    from tubes import db
    monkeypatch.setenv('TUBES_DATABASE_URL', db_url); db.reset()
    yield db_url
    db.reset()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A test that opens an outbound connection fails at once (loopback and unix sockets are fine)."""
    real = socket.socket.connect

    def guarded(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else None
        if self.family in (socket.AF_INET, socket.AF_INET6) and host not in ('127.0.0.1', '::1', 'localhost'): raise AssertionError(f'tests must not use the network (tried {address!r})')
        return real(self, address, *a, **kw)
    monkeypatch.setattr(socket.socket, 'connect', guarded)


@pytest.fixture
def fake_urlopen(monkeypatch):
    """Script `urllib.request.urlopen`: `fake_urlopen.reply({...}, http_error(429))`, then assert on `fake_urlopen.calls` (url, method, headers, parsed JSON body). Unexpected calls fail."""
    import urllib.request
    from fakes import FakeUrlopen
    f = FakeUrlopen(); monkeypatch.setattr(urllib.request, 'urlopen', f); return f


@pytest.fixture
def fake_popen(monkeypatch):
    """Replace `subprocess.Popen` everywhere: nothing starts; `fake_popen.instances` lists the commands (`.cmd`) and kwargs (`.kw`) it was asked to run."""
    import subprocess
    from fakes import FakePopen
    FakePopen.instances = []; monkeypatch.setattr(subprocess, 'Popen', FakePopen); return FakePopen


@pytest.fixture
def fake_run(monkeypatch):
    """Replace `subprocess.run` / `check_output`: record the command lines in `.calls`; set `.returns['cmd'] = b'...'` (substring of the command line) for output, `.code = 1` to fail."""
    import subprocess
    from fakes import FakeRun
    f = FakeRun(); monkeypatch.setattr(subprocess, 'run', f); monkeypatch.setattr(subprocess, 'check_output', f.check_output); return f


@pytest.fixture
def fake_ytdlp(monkeypatch, tmp_path):
    """Point `ytdlp` at tests/utils/fake_ytdlp.py (a real process that answers like yt-dlp, without the network, making media with ffmpeg) and
    return a helper: `fake_ytdlp.seconds(n)` sets a video's length, `fake_ytdlp.fail('substring')` fails a matching call."""
    import sys

    class Fake:
        def seconds(self, n): monkeypatch.setenv('FAKE_YTDLP_SECONDS', str(n)); return self
        def fail(self, part): monkeypatch.setenv('FAKE_YTDLP_FAIL', part); return self

    script = tmp_path / ('yt-dlp.cmd' if os.name == 'nt' else 'yt-dlp')
    script.write_text(f'@"{sys.executable}" "{FAKE_YTDLP}" %*\n' if os.name == 'nt' else f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_YTDLP}" "$@"\n', encoding='utf8'); script.chmod(0o755)
    monkeypatch.setenv('TUBES_YTDLP', str(script))
    return Fake()


@pytest.fixture
def fake_youtube(monkeypatch):
    """A stand-in YouTube Data API on localhost (tests/utils/fake_youtube.py), with the key set in the environment as a deployment would; fill
    it with `fake_youtube.channel(id, title, handle=..., videos=n)` and `.uploads(id, n)`, then check `.calls`."""
    from fake_youtube import KEY, FakeYoutube
    y = FakeYoutube()
    monkeypatch.setenv('TUBES_YOUTUBE_API', y.api); monkeypatch.setenv('YOUTUBE_API_KEY', KEY)
    yield y
    y.close()


@pytest.fixture
def fake_d1(monkeypatch):
    """A stand-in D1 HTTP API on localhost (tests/utils/fake_d1.py) holding the storage service's library tables, with the credentials and
    database id set in the environment as a deployment would (for `tubes import-d1`); fill it with `fake_d1.channel(id, title)` and
    `fake_d1.video(id, channel_id, title, published)`."""
    from fake_d1 import FakeD1
    d = FakeD1()
    monkeypatch.setenv('TUBES_D1_API', d.api); monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', d.account); monkeypatch.setenv('CLOUDFLARE_API_TOKEN', d.token); monkeypatch.setenv('TUBES_D1_DATABASE', d.database)
    yield d
    d.close()
