# Design brief

## 1. Goal

Watch a library of online videos at home, at 1080p, without waiting and without depending on a third-party player. The library (which channels and videos exist) is managed in its own app; Tubes reads it, fetches a video the first time someone plays it, and keeps copies on a large local disk so the next play is instant.

Decisions (2026-11-09): run on the home server (a residential connection; datacenter IPs are blocked); fetch on demand and stream while downloading rather than pre-download everything; 1080p where offered (a 4K screen); a 1 TB cache on a 10 TB disk, trimmed by a mix of recency and popularity; latest Chrome as the only player (VP9 and AV1 are fine). Later: predict what will be wanted, fetch it ahead and recommend it.

## 2. Architecture

- **Library copy (`library.py`)**: reads the library's Cloudflare D1 database through its HTTP API (`POST .../d1/database/{id}/query`, SELECT only, 5,000 rows a page by id) and replaces the local copy (`channels`, `videos`) in one transaction. A copy, not a read-through: D1 answers in 0.4–0.5 s a query, too slow for a page of thumbnails, and the app keeps working when D1 or the network is down. `tubes sync` runs every few hours from a timer and on demand (System > Sync now).
- **Database (`db.py`, `models.py`, `migrations/`)**: Tubes' own tables through [omarchy_db](https://github.com/jburnhams/database): the library copy, `copies` (one row per cached video: state, size, formats, pinned) and `plays` (one row per play). Postgres in production (its own `tubes` schema in the shared database), SQLite in tests; SQL is kept portable.
- **Fetcher (`fetcher.py`, `ytdlp.py`)**: `POST /api/videos/{id}/play` records the play and, unless a copy exists, starts yt-dlp (format AV1 > VP9 > H.264 at `max_height`, width checked too, original audio) writing to stdout into ffmpeg, which writes an fMP4 HLS event playlist in the video's cache folder. The player starts once three segments exist. yt-dlp downloads itself (YouTube refuses ffmpeg's own requests) and asks as the `visionos` client, which skips a 4 s wait.
- **Cache (`cache.py`)**: score = Σ 0.5^(days since play / half-life). Eviction starts above 95% of the limit and stops under 90%, lowest score first; pinned copies, copies being fetched and unplayed copies younger than `protect_days` are kept; failed copies go first.
- **Server (`server/app.py`)**: FastAPI, JSON under `/api/*`, media under `/api/media/{id}/`, the built web app at every other path with a relative `<base>` (works behind a reverse proxy at a subpath).
- **Web app (`web/`)**: React 19 on strata-react, a palette generated from the subject (`web/src/styles/`), hls.js for playback (`web/src/player.ts`). Every read is `useLoad`/`useInfiniteLoad` with a skeleton and an empty state; long lists page by cursor (`published|id`), never by offset.

## 3. Principles

- **Generic**: nothing in the repo names real channels, videos or viewers. Curation is the library app's job.
- **Read-only on the library**; credentials only from the environment.
- **Hermetic tests**: a stand-in yt-dlp and a stand-in D1 (`tests/utils/`), no network; SQLite by default, `--pg` for Postgres.
- **Ratcheting coverage floors**: Python unit coverage (`fail_under` in `pyproject.toml`) and web combined coverage (`web/coverage-floor.json`) only go up.
