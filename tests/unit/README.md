# Unit tests

Shared commands, layout, hermetic setup and file-ownership rules are in [`tests/README.md`](../README.md); read that first. This file is owned by unit-test work.

Fast and isolated: synthetic data and fakes; no external services, no network. Each test gets a fresh database (omarchy_db's `db_url` fixture: SQLite, or Postgres with `--pg`). `pytest tests/unit --cov` is what CI gates on (`fail_under` in `pyproject.toml`).

## Where things are tested

| Module | Tests | Coverage | Status | Notes |
| --- | --- | --- | --- | --- |
| `settings.py` | `test_settings.py` | 100% | done | defaults, environment overrides, validation, save/load, corrupt JSON |
| `db.py` | `test_db.py` | 100% | done | `?` placeholders to named, migrations on first use, one engine per URL |
| `library.py` | `test_library.py` | 100% | done | D1 queries and every failure's message, paging by id, sync replacing the copy, search words (escaped LIKE), cursor paging, shuffle |
| `cache.py` | `test_cache.py` | ~100% | done | copy states, plays, score and eviction order, protections, pin, drop |
| `fetcher.py` | `test_fetcher.py` | ~100% | done | the yt-dlp to ffmpeg pipeline with a stand-in yt-dlp, playable after three segments, failures, the fetch limit |
| `ytdlp.py` | `test_ytdlp.py` | 100% | done | format choice (codec order, width as well as height, original audio), video ids |
| `oslib.py` | `test_oslib.py` | 100% | done | file locks, process liveness, process tree termination, priority, venv/cli helpers |
| `cli.py` | `test_cli.py` | 100% | done | doctor, sync, channels, fetch, cache, evict, set, serve delegation |
| `server/app.py` | `test_server.py` | 100% | done | landing/static index, every page path with its relative `<base>`, health, system, settings, library and sync, channels, videos (paged, search, shuffle), play and stream, media, cache (pin, drop, evict) |
