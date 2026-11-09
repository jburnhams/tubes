# Tubes

A home video server: it keeps a copy of a video library (channels and videos, managed elsewhere), fetches a video with [yt-dlp](https://github.com/yt-dlp/yt-dlp) the first time someone plays it, and streams it while it downloads. Copies stay in a size-capped cache and the least wanted go first when it fills.

- **Library**: read-only. `tubes sync` copies the channels and videos from a Cloudflare D1 database (the one the library manager writes) into Tubes' own database; the app browses and searches that copy.
- **Fetch on play**: yt-dlp downloads the best format up to the chosen height (AV1, then VP9, then H.264, original audio) and ffmpeg writes it as an HLS playlist as it arrives, so playback starts after the first few seconds are on disk (about 2 s on a home connection).
- **Cache**: one folder with a size limit (default 1 TB). Above 95% of it, copies go lowest score first until it is under 90%; the score is every play, each worth half as much per half-life (default 30 days). Pinned copies, copies being fetched and recent unplayed fetches are kept.
- **Web app**: Browse, Search, Channels, Watch, Cache, System and Settings, built on [strata-react](https://github.com/jburnhams/strata-react). Latest Chrome is the target.

## Quick start

```bash
./scripts/setup_env.sh              # .venv, Python and web dependencies, web build (Windows: scripts\setup_env.ps1)
export CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=...   # read access to the library's D1 database
./tubes set d1_database <id>        # the library's D1 database id
./tubes doctor                      # yt-dlp, ffmpeg, the database, the library credentials
./tubes sync                        # copy the library
./tubes serve                       # http://127.0.0.1:8367
```

Tubes keeps its own tables (the library copy, cache copies, plays) in a database through [omarchy_db](https://github.com/jburnhams/database): its own `tubes` schema in the machine's shared Postgres by default (`TUBES_DATABASE_URL` or `OMARCHY_DB_URL` to change it; any SQLAlchemy URL, SQLite included). Migrations run on start. Running it on a server, with the timer and the reverse proxy, is in [`docs/deploy.md`](docs/deploy.md).

## Commands

| Command | What it does |
| --- | --- |
| `tubes doctor` | checks yt-dlp, ffmpeg, the database, the library's credentials and the copy's age |
| `tubes sync` | copies the library from D1 (the whole copy is replaced in one transaction) |
| `tubes channels` | lists the channels in the copy |
| `tubes fetch <id>` | fetches one video into the cache now |
| `tubes cache` / `tubes evict [--dry-run]` | shows the cache with each copy's score / trims it |
| `tubes set [key [value]]` | shows or changes a setting (`default` resets one) |
| `tubes serve` | the web app and the API (`/api/docs`) |

## Development

See [`AGENTS.md`](AGENTS.md) for the layout, the test suites and every command, and [`docs/`](docs/) for the design brief, plan and progress log.
