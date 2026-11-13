# Implementation plan

- [x] **Spike** (2026-11-09, on the home server): yt-dlp streaming 1080p while it downloads starts playback in about 2 s; see `progress.md`.
- [x] **M1 fetch, cache and library copy**: the library copied from D1 into Tubes' own database (omarchy_db), fetch on play as HLS while downloading, the size-capped cache with eviction by score, the CLI (`doctor`, `sync`, `channels`, `fetch`, `cache`, `evict`, `set`, `serve`), the API, and the web app (Home, Search, Channels, Watch in the old Tubes look; Cache, System, Settings under /admin in Strata's) with tests, Storybook and screenshot baselines.
- [ ] **M2 deploy**: the service, timer and reverse proxy on the home server (`deploy.md`); `dbtool new-app tubes` there; a first full sync.
- [x] **Library managed here** (2026-11-09): storage's YouTube catalogue ported into Tubes (add a channel or video, sync with a resumable backfill, bulk sync, start again, remove; Admin > Library and `tubes add/sync/remove`), with `tubes import-d1` to carry the existing library over once.
- [x] **Cut over on the server** (2026-11-09): deployed and restarted (the services read `YOUTUBE_API_KEY` and `YOUTUBE_API_REFERER` from the env file); no import from D1 was needed, since the tables already held the copied library, and the first `tubes sync` read each channel back in full. `d1import.py`, the `fake_d1` stand-in and every Cloudflare credential are gone. Storage's YouTube tables can go when nothing else reads them.
- [ ] **Library, next**: refresh counts (views) of held videos now and then (storage never did); edit or hide single videos; a quota meter.
- [ ] **M3 resume and history**: remember where each video was stopped; a "carry on" row on Home.
- [ ] **M4 predict and pre-fetch**: score unplayed videos from what is played (channel, recency, similar titles; pgvector embeddings are an option on Postgres), fetch the top few ahead overnight, and recommend them on Home.
  - [x] Instant starts (2026-11-13): the first 20 s of the videos Home, Up next and a channel's page offer are prefetched as partial copies (`prefetch.py`), and a play starts from them while the rest is fetched.
