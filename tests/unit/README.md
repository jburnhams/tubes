# Unit tests

Shared commands, layout, hermetic setup and file-ownership rules are in [`tests/README.md`](../README.md); read that first. This file is owned by unit-test work.

Fast and isolated: synthetic data and fakes; no external services, no network. Each test gets a fresh database (omarchy_db's `db_url` fixture: SQLite, or Postgres with `--pg`). `pytest tests/unit --cov` is what CI gates on (`fail_under` in `pyproject.toml`).

## Where things are tested

| Module | Tests | Coverage | Status | Notes |
| --- | --- | --- | --- | --- |
| `settings.py` | `test_settings.py` | 100% | done | defaults, environment overrides, validation, save/load, corrupt JSON |
| `db.py` | `test_db.py` | 100% | done | `?` placeholders to named, migrations on first use, one engine per URL |
| `library.py` | `test_library.py` | 100% | done | status, channels with counts and sync state (booleans on both engines), search words (escaped LIKE), cursor paging, shuffle |
| `youtube.py` | `test_youtube.py` | 100% | done | what a person pastes (links, ids, handles), durations, thumbnails, rows, the key and Referer, every failure's message (quota, referrer), the three calls against the stand-in |
| `catalogue.py` | `test_catalogue.py` | ~100% | done | add a channel or a video (its channel unfollowed), first sync to the end, later syncs stop at nothing new, a stopped backfill resumes, quota stops the rest, remove, start again, the background job |
| `history.py` | `test_history.py` | 100% | done | Takeout JSON and HTML (UK/US times, zones, ads, gone videos), import replaces a source, score, sittings, groups that keep ids and names, YouTube's topics and audience, quota, the list's filters, dismiss, rename |
| `related.py` | `test_related.py` | 100% | done | watch pages' next column (lockupViewModel and the older compactVideoRenderer, shelves left out), featured channels in either case, a week's expiry and a day's retry, failures keep the old links, the count and borrowed groups, history channels as sources, sources that stop counting |
| `paste.py` | `test_paste.py` | ~100% | done | splitting a paste (bullets, several links a line), YouTube links, ids, handles and videos, iPlayer programme and episode links (one-offs refused), names on both (handle first, a bounded search, exact titles on iPlayer), followed and dismissed ones, failures per line, kept through a regroup |
| `cache.py` | `test_cache.py` | ~100% | done | copy states, plays, score and eviction order, protections, pin, drop |
| `fetcher.py` | `test_fetcher.py` | ~100% | done | the yt-dlp to ffmpeg pipeline with a stand-in yt-dlp, playable after three segments, failures, the fetch limit; iPlayer episodes through ffmpeg alone, the yt-dlp fallback |
| `prefetch.py` | `test_prefetch.py` | 100% | done | how much of a start (skipped parts at the start added), offered videos before Home's, passed-over videos, waiting for a play's fetch, the day's limit, failures forgotten, slowing down |
| `iplayer.py` | `test_iplayer.py` | 100% | done | links, BBC times and durations, the version to play, titles from `Series 1: 2. Name`, rows, the catalogue and mediaselector calls and refusals against the stand-in (tests/utils/fake_iplayer.py), 1080p50 then the best listed variant |
| `ytdlp.py` | `test_ytdlp.py` | 100% | done | format choice (codec order, width as well as height, original audio), video ids |
| `oslib.py` | `test_oslib.py` | 100% | done | file locks, process liveness, process tree termination, priority, venv/cli helpers |
| `viewing.py` | `test_viewing.py` | ~100% | done | none/short/partial/full at the 10% and 90% lines (and with no length known), where a play came from, reports that only move up, the library's length when the player gave none, Continue watching (finished, too old, hidden, short looks after), where a play picks up, channel views, the summary, the latest plays |
| `quota.py` | `test_quota.py` | ~100% | done | Pacific day and reset across both clock changes, the limit from the environment, counting by purpose/endpoint/hour, refusals, old days dropped, a racing insert, counting never breaks a call, real calls through the stand-in YouTube under their purposes |
| `cli.py` | `test_cli.py` | 100% | done | doctor, add, sync, remove, channels, fetch, cache, evict, set, serve delegation |
| `server/app.py` | `test_server.py` | 100% | done | landing/static index, every page path with its relative `<base>`, health, system, settings, library: add, the background sync, remove, start again; channels, videos (paged, search, shuffle), play and stream, media, cache (pin, drop, evict) |
