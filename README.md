# Tubes

A home video server: it keeps a video library (YouTube channels and videos, added in its admin area), fetches a video with [yt-dlp](https://github.com/yt-dlp/yt-dlp) the first time someone plays it, and streams it while it downloads. Copies stay in a size-capped cache and the least wanted go first when it fills.

- **Library**: channels and single videos are added in Admin > Library (or `tubes add`) by link, id or @handle, and their details come from the YouTube Data API. A followed channel's uploads are read back to its first video once, and each sync (every few hours, or Sync in Admin) picks up the new ones. The app browses and searches the library from Tubes' own database.
- **Fetch on play**: yt-dlp downloads the best format up to the chosen height (AV1, then VP9, then H.264, original audio) and ffmpeg writes it as an HLS playlist as it arrives, so playback starts after the first few seconds are on disk (about 2 s on a home connection).
- **Cache**: one folder with a size limit (default 1 TB). Above 95% of it, copies go lowest score first until it is under 90%; the score is every play, each worth half as much per half-life (default 30 days). Pinned copies, copies being fetched and recent unplayed fetches are kept.
- **Web app**: the watching side (Home, Search, Channels, Watch) in the old Tubes look, a video site's layout with Tubes' own mark; the admin area under `/admin` (Library, Cache, System, Settings) in [strata-react](https://github.com/jburnhams/strata-react)'s look. Latest Chrome is the target.

## Quick start

```bash
./scripts/setup_env.sh              # .venv, Python and web dependencies, web build (Windows: scripts\setup_env.ps1)
export YOUTUBE_API_KEY=...          # a YouTube Data API v3 key (YOUTUBE_API_REFERER too if the key is restricted to a site)
./tubes doctor                      # yt-dlp, ffmpeg, the database, the YouTube key
./tubes add https://www.youtube.com/@somechannel   # follow a channel and fetch its videos' details
./tubes serve                       # http://127.0.0.1:8367
```

Tubes keeps its own tables (the library, cache copies, plays) in a database through [omarchy_db](https://github.com/jburnhams/database): its own `tubes` schema in the machine's shared Postgres by default (`TUBES_DATABASE_URL` or `OMARCHY_DB_URL` to change it; any SQLAlchemy URL, SQLite included). Migrations run on start. Running it on a server, with the timer and the reverse proxy, is in [`docs/deploy.md`](docs/deploy.md).

## Commands

| Command | What it does |
| --- | --- |
| `tubes doctor` | checks yt-dlp, ffmpeg, the database, the YouTube key and when the library was last synced |
| `tubes add <link, id or @handle>` | follows a channel and syncs it (`--no-sync` to wait), or adds one video |
| `tubes sync [channel ...]` | fetches new videos for every followed channel (or the ones named); a first sync reads back to the channel's first upload |
| `tubes recheck [--limit N \| --all]` | asks YouTube about the videos checked longest ago, hiding those it no longer has and live streams (each sync does 2,500; `--all` costs a unit per 50 videos) |
| `tubes channels` / `tubes remove <channel>` | lists the channels with their state / removes one and its videos |
| `tubes fetch <id>` | fetches one video into the cache now |
| `tubes cache` / `tubes evict [--dry-run]` | shows the cache with each copy's score / trims it |
| `tubes set [key [value]]` | shows or changes a setting (`default` resets one) |
| `tubes serve` | the web app and the API (`/api/docs`) |

## Development

See [`AGENTS.md`](AGENTS.md) for the layout, the test suites and every command, and [`docs/`](docs/) for the design brief, plan and progress log.
