# Implementation plan

- [x] **Spike** (2026-11-09, on the home server): yt-dlp streaming 1080p while it downloads starts playback in about 2 s; see `progress.md`.
- [x] **M1 fetch, cache and library copy**: the library copied from D1 into Tubes' own database (omarchy_db), fetch on play as HLS while downloading, the size-capped cache with eviction by score, the CLI (`doctor`, `sync`, `channels`, `fetch`, `cache`, `evict`, `set`, `serve`), the API, and the web app (Home, Search, Channels, Watch in the old Tubes look; Cache, System, Settings under /admin in Strata's) with tests, Storybook and screenshot baselines.
- [ ] **M2 deploy**: the service, timer and reverse proxy on the home server (`deploy.md`); `dbtool new-app tubes` there; a first full sync.
- [ ] **M3 resume and history**: remember where each video was stopped; a "carry on" row on Home.
- [ ] **M4 predict and pre-fetch**: score unplayed videos from what is played (channel, recency, similar titles; pgvector embeddings are an option on Postgres), fetch the top few ahead overnight, and recommend them on Home.
