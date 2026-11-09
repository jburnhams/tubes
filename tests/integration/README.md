# Integration tests

Shared commands, layout, hermetic setup and file-ownership rules are in [`tests/README.md`](../README.md); read that first. This file is owned by integration-test work.

These run the program's boundaries end to end: the command line (in-process and as a subprocess) and the HTTP API over real on-disk files and a real database, with a stand-in yt-dlp (`fake_ytdlp`), a stand-in YouTube Data API (`fake_youtube`, `tests/utils/fake_youtube.py`) and a stand-in D1 HTTP server (`fake_d1`, `tests/utils/fake_d1.py`, for the one-time import) that runs storage's SQL on in-memory SQLite.

## Fixtures (`conftest.py`)

| Fixture | What it gives you |
| --- | --- |
| `cli` | `cli('cache', '--json')` -> `Result(stdout, stderr, code, out)`, **in process** (fast). Raises with the output on a non-zero exit unless `check=False`. |
| `cli_subprocess` | The same through a real `python -m tubes` process: entry-point smoke test, and anything that must not share this process's state. |
| `client` | A FastAPI `TestClient` over the real on-disk state. |
| `fake_youtube` | The stand-in YouTube Data API, with `TUBES_YOUTUBE_API` and a key set; `.channel(id, title, handle=, videos=n)`, `.uploads(id, n)`, `.calls`, `.quota_left`, `.referer`, `.hold`. |
| `fake_d1` | The stand-in D1 server, with the environment pointed at it (`TUBES_D1_API`, credentials); `.channel()`, `.video()`, `.remove_video()` change what it holds. |

## Coverage

Not gated. `pytest tests/integration -n auto --cov --cov-fail-under=0 --cov-report=term-missing`.

| Area | Tests |
| --- | --- |
| `cli.py` | `test_cli.py`: doctor, add and sync from YouTube (a later sync reads only the newest pages; out of quota), remove, import-d1, channels, fetch, cache, evict, settings, real subprocess |
| `server/app.py` | `test_server_api.py`: add a channel and its background sync, browse and search, play to a complete copy and its playlist, cache pin and evict, settings updates, validation errors |
