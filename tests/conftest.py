"""Shared pytest configuration. strata-python's pytest plugin makes every test hermetic (its own home and data folder, no network, the
variables in `strata_tuning_vars` removed and `strata_env` set: `[tool.pytest.ini_options]` in pyproject.toml), marks the tests under
tests/integration `integration`, and gives the `fake_urlopen`, `fake_popen`, `fake_run` and `db_*` fixtures. What is Tubes' own is here."""

import os
import sys

import pytest

FAKE_YTDLP = os.path.join(os.path.dirname(__file__), "utils", "fake_ytdlp.py")


@pytest.fixture(autouse=True)
def database(db_env):
    """Every test gets its own migrated database (strata_python.db's `db_env`: a SQLite copy of a template migrated once, or a throwaway
    Postgres database with `pytest --pg`), through the same TUBES_DATABASE_URL a deployment would set, so subprocesses (the integration
    suite) use it too. Tubes keeps an engine per URL (db.py), so it forgets them around each test."""
    from tubes import db

    db.reset()
    yield db_env
    db.reset()


@pytest.fixture(autouse=True)
def checked_answers(monkeypatch):
    """Every 200 answer of a route that declares its model (server/answers.py) is validated against it, so the schema the web app's types
    come from cannot drift from what the server sends."""
    from tubes.server import answers

    monkeypatch.setattr(answers, "CHECK", True)


@pytest.fixture(autouse=True)
def http_without_waits(monkeypatch):
    """Tubes' web clients (strata-python's Http, one per service) keep their rules (retries, which statuses are errors) but wait for nothing
    between attempts or requests, and forget what an earlier test taught them (a host cooling down after a 429)."""
    from tubes import iplayer, plex, related, segments, youtube

    for module in (iplayer, plex, related, segments, youtube):
        monkeypatch.setattr(module.HTTP, "_sleep", lambda seconds: None)
        monkeypatch.setattr(module.HTTP, "min_interval", 0)
        module.HTTP._next.clear()
        module.HTTP._cool_until.clear()


@pytest.fixture
def fake_ytdlp(monkeypatch, tmp_path):
    """Point `ytdlp` at tests/utils/fake_ytdlp.py (a real process that answers like yt-dlp, without the network, making media with ffmpeg) and
    return a helper: `fake_ytdlp.seconds(n)` sets a video's length, `fake_ytdlp.fail('substring')` fails a matching call."""

    class Fake:
        def seconds(self, n):
            monkeypatch.setenv("FAKE_YTDLP_SECONDS", str(n))
            return self

        def fail(self, part):
            monkeypatch.setenv("FAKE_YTDLP_FAIL", part)
            return self

    script = tmp_path / ("yt-dlp.cmd" if os.name == "nt" else "yt-dlp")
    script.write_text(
        f'@"{sys.executable}" "{FAKE_YTDLP}" %*\n'
        if os.name == "nt"
        else f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_YTDLP}" "$@"\n',
        encoding="utf8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("TUBES_YTDLP", str(script))
    return Fake()


@pytest.fixture
def fake_youtube(monkeypatch):
    """A stand-in YouTube Data API on localhost (tests/utils/fake_youtube.py), with the key set in the environment as a deployment would; fill
    it with `fake_youtube.channel(id, title, handle=..., videos=n)` and `.uploads(id, n)`, then check `.calls`."""
    from fake_youtube import KEY, FakeYoutube

    y = FakeYoutube()
    monkeypatch.setenv("TUBES_YOUTUBE_API", y.api)
    monkeypatch.setenv("TUBES_YOUTUBE_WEB", y.web)
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    yield y
    y.close()


@pytest.fixture
def fake_iplayer(monkeypatch):
    """A stand-in for BBC iPlayer's catalogue and mediaselector on localhost (tests/utils/fake_iplayer.py); fill it with
    `fake_iplayer.programme(pid, title, episodes=n)`, then check `.calls`."""
    from fake_iplayer import FakeIplayer

    f = FakeIplayer()
    monkeypatch.setenv("TUBES_IPLAYER_API", f.ibl)
    monkeypatch.setenv("TUBES_MEDIASELECTOR", f.ms)
    yield f
    f.close()


@pytest.fixture
def fake_plex(monkeypatch):
    """A stand-in Plex Media Server on localhost (tests/utils/fake_plex.py), with PLEX_URL and PLEX_TOKEN pointing at it; fill it with
    `fake_plex.film(key, title)` or `fake_plex.show(key, title, episodes=n)`, then check `.calls`."""
    from fake_plex import TOKEN, FakePlex

    f = FakePlex()
    monkeypatch.setenv("PLEX_URL", f.url)
    monkeypatch.setenv("PLEX_TOKEN", TOKEN)
    yield f
    f.close()
