"""The application server: `./tubes serve` starts the FastAPI backend and serves the built React app.

    ./tubes serve [--host 127.0.0.1] [--port 8367]

The library (channels and videos) is managed here, from YouTube and BBC iPlayer (catalogue.py writes it, library.py reads it).

API (JSON):
  GET  /api/health                         {ok, version, commit} (strata-python's web.base_app)
  GET  /api/system                         versions (app, Python, yt-dlp, ffmpeg), folders, disk, cache use, the library copy's state, prefetching (prefetch.py)
  GET  /api/skipping                      [{id, label, detail, mode}]: every kind of segment, with what the player does in it (settings skip_<id>)
  GET  /api/break                         {url, minutes, limit_minutes}: the break the watching side takes from playing (settings break_*); url null when off
  GET  /api/videos/{id}/segments          {segments: [{category, start, end, action}], categories: [{id, label, detail, mode}], error}: what can be skipped
  GET  /api/settings, PUT /api/settings    every setting (settings.py, through web.base_app); PUT takes any subset, a null resets one
  GET  /api/library                       {synced, channels, videos, hidden, live, filtered, configured}: when every followed channel was last synced, and whether the YouTube key is set
  POST /api/library {input}                add a channel (followed; its sync starts at once, or after the running sync's channels) or one video from a link, id or @handle; an iPlayer programme or episode link works the same way: {kind, channel|video, sync}
  GET  /api/library/shown, PUT            which videos the watching side shows (library.filters): {min_seconds, max_seconds, streams, region, languages, unknown_language, captions, filtered, language_counts}; PUT takes any subset of the filters, null for no limit; filtered is how many they leave out, language_counts the languages there are to choose from (library.languages)
  GET  /api/library/sync                   the background sync: {running, total, done, current, added, errors, started, finished}
  POST /api/library/sync {channels}        start one for these channel ids (default: every followed channel); 409 while one runs
  GET  /api/quota                         the YouTube Data API quota: today's units used of the limit, what remains, when it resets, today by
                                           purpose, endpoint and hour, and the last 30 days (quota.py; Google has no call that says this)
  GET  /api/channels, GET /api/channels/{id}   channels with their video counts and sync state
  GET  /api/groups, GET /api/groups/{id}   groups of videos with their counts and a picture picked anew each time (groups.py)
  GET  /api/channels/{id}/overview         a channel's library state, watch history (per month, per account, videos watched most) and suggestion
  DELETE /api/channels/{id}                remove a channel and its videos
  POST /api/channels/{id}/restart          forget a channel's videos and sync state, then sync it again from the start
  GET  /api/videos?channel=&q=&after=&limit=   a page of videos, newest first: {videos, has_more}; `after` is the last one's cursor (`published|id`)
  GET  /api/videos/shuffle?count=&channel=     videos picked at random
  GET  /api/videos/{id}                    one video, with its copy's state, plays and last play
  GET  /api/videos/continue?limit=         Continue watching: videos part watched in the last 30 days, latest first, with `resume` and `progress`
  POST /api/videos/{id}/play {source, detail, rank}   record a play of a library video (and where it was started from, all optional) and
                                           start fetching unless it is cached; returns the stream status with `play_id` and `resume` (where it picks up)
  POST /api/plays/{id} {position, watched, length}   how the play is going (viewing.py): returns its `outcome` (none, short, partial, full)
  GET  /api/plays?limit=&after=&outcome=&source=   a page of plays, newest first, each with where it came from and how it went: {items, has_more}
  GET  /api/plays/summary?days=           the last `days` of viewing in numbers: plays by outcome and by source, seconds seen, channel visits by source
  GET  /api/channel-views?limit=&after=   a page of visits to channel pages, newest first, with where each came from: {items, has_more}
  POST /api/channels/{id}/views {source, detail}   someone opened the channel's page, and from where
  GET  /api/videos/{id}/stream             the stream status: {state, segments, seconds, complete, playable, error, formats, plays, last_played}
  GET  /api/media/{id}/{file}              the HLS playlist, init segment and segments (only those names; the playlist is never cached while it grows)
  GET  /api/cache                          use, limit and every cached video with its score
  PUT  /api/cache/{id} {pinned}            pin or unpin a copy
  DELETE /api/cache/{id}                   delete a copy now
  POST /api/cache/evict {dry_run}          run eviction
  GET  /api/suggestions?group=&topic=&kids=&q=&dismissed=&order=&pasted=&limit=   channels from the watch history, those related channels point at
                                           and those pasted in (order=watched, best score first, or suggested, most pointed at first; pasted=true
                                           only the pasted ones, latest first): {items, total}; each item's `link` is what Follow adds
  GET  /api/suggestions/summary            the histories, groups, topics and counts around that list (`database`: a history database is set)
  POST /api/suggestions/refresh            read the history database again if one is set, remake the suggestions, ask YouTube about new channels
  GET  /api/history?start=&end=&source=    what was watched then: counts, watches per day or month, top channels and videos (`configured`: channels can be followed)
  POST /api/suggestions/paste {text}       links, @handles or names (YouTube or iPlayer), one a line, into the suggestions: {found, already, problems}
  POST /api/suggestions/import {source, text}   import a Takeout watch history (its file's text) under a name, then refresh
  DELETE /api/suggestions/sources/{source}  forget an imported history
  PUT  /api/suggestions/groups/{id} {name}  name a group (empty: back to the made-up name)
  PUT  /api/suggestions/{channel} {dismissed}   dismiss a suggestion or bring it back
  POST /api/suggestions/{channel}/videos   add the channel's watched videos to the library without following it: {added, already, missing}
  (following a suggestion is POST /api/library with its `link`)
  GET  /api/plex                           whether Plex is set up and answers, and its film and TV libraries (plex.py)
  GET  /api/plex/sections/{key}/filters    the filters a library offers; /filters/{name} the values one takes (genre: Action, Animation...)
  GET  /api/plex/browse?section=&start=&size=&<filter>=...   a page of a library with Plex's own filters: {items, total}, each item `followed`
  GET  /api/plex/search?q=                 films and shows whose title matches
  POST /api/plex/follow {key} | {section, params, title}   follow a show or a film, or a filtered listing as a channel of its own (then synced)
  GET  /api/plex/image?path=&w=            one of Plex's pictures, scaled and kept here (the token never reaches the browser)
  A play's body may say what the browser decodes (`decodes`: h264, hevc, av1, vp9, hdr): a Plex film or episode is then fetched as its
  file has it when the browser plays that, else converted to H.264 (fetcher.plex_copy); the answer's `copy` is the id its files are under.
Every other path serves the web app (`src/tubes/server/static/index.html` when built with `cd web && npm run build`, else the plain stand-in
`landing.html`), so a reload or a shared link opens that screen: the app routes in the browser (React Router; strata-python's web.add_web).
Errors are raised, not caught in routes: web.add_error_handlers answers them as {detail, payload} with the status in ERRORS."""

import os
import platform
import shutil
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from strata_python import web

from tubes import (
    __version__,
    cache,
    catalogue,
    db,
    fetcher,
    groups,
    history,
    iplayer,
    library,
    paste,
    plex,
    prefetch,
    quota,
    segments,
    settings,
    viewing,
    youtube,
    ytdlp,
)
from tubes.db import Row

from . import answers as A
from .answers import answer

# The app's own exceptions as HTTP statuses, on top of strata-python's (ValueError 400, KeyError 404, ...). A KeyError here is a request
# naming a filter or setting there is none of, so 400 as before. YouTube, Plex and a history import choose by what went wrong: a service
# not set up here (503) is not one that failed (502), and a history file that is not a history (400) is not a page that could not be read (502).
ERRORS: web.ErrorMap = {
    fetcher.FetchError: 400,
    KeyError: 400,
    catalogue.NotFound: 404,
    history.NotFound: 404,
    viewing.NotFound: 404,
    catalogue.Job.Busy: 409,
    iplayer.IplayerError: 502,
    history.ImportProblem: lambda e: 502 if "could not be read" in str(e) else 400,
    youtube.YoutubeError: lambda e: 502 if youtube.configured() else 503,
    plex.PlexError: lambda e: 502 if plex.configured() else 503,
}

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
LANDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing.html")
DEFAULT_PORT = 8367
MEDIA_TYPES = {".m3u8": "application/vnd.apple.mpegurl", ".mp4": "video/mp4", ".m4s": "video/iso.segment"}


class PinIn(BaseModel):
    pinned: bool


class EvictIn(BaseModel):
    dry_run: bool = False


class AddIn(BaseModel):
    input: str


class SyncIn(BaseModel):
    channels: list[str] | None = None


class DismissIn(BaseModel):
    dismissed: bool


class NameIn(BaseModel):
    name: str


class PasteIn(BaseModel):
    text: str


class ImportIn(BaseModel):
    source: str
    text: str


class CheckIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=50)


class FromIn(BaseModel):
    """Where a play or a channel visit was started from (viewing.py): all optional, so an old page or a typed address still works."""

    source: str | None = Field(default=None, max_length=32)
    detail: str | None = Field(default=None, max_length=500)
    rank: int | None = Field(default=None, ge=0)
    decodes: list[str] | None = Field(
        default=None, max_length=20
    )  # what the browser plays as it is (h264, hevc, av1, vp9, hdr): which copy of a Plex video to fetch


class FollowIn(BaseModel):
    """A Plex show or film by its ratingKey, or a library listing with filters to follow as a channel."""

    key: str | None = Field(default=None, max_length=12)
    section: str | None = Field(default=None, max_length=12)
    params: dict[str, str] | None = None
    title: str | None = Field(default=None, max_length=200)


class ProgressIn(BaseModel):
    position: float | None = Field(default=None, ge=0)
    watched: float | None = Field(default=None, ge=0)
    length: float | None = Field(default=None, ge=0)


def system_status():
    """A snapshot for the System page. Sizes are bytes; the web app formats them."""
    du = shutil.disk_usage(settings.cache_dir())
    return dict(
        version=__version__,
        python=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}".strip(),
        ytdlp=ytdlp.version(),
        ffmpeg=fetcher.ffmpeg_version(),
        can_fetch=fetcher.CAN_PASS_FDS,
        data_dir=settings.data_dir(),
        cache_dir=settings.cache_dir(),
        cache=cache.usage(cache.utcnow()),
        fetching=fetcher.running(),
        disk=dict(total=du.total, used=du.used, free=du.free),
        library=library.status(),
    )


def create_app(recover: bool = True) -> FastAPI:
    """The app. `recover=False` builds it without touching the database or the cache (what `tubes openapi` needs to write the schema).
    strata-python's base_app gives /api/health (with the commit the server runs), /api/settings (typed from settings.SETTINGS) and the docs."""
    app = web.base_app("tubes", __version__, settings.SETTINGS, commit=web.source_commit(__file__))
    web.add_error_handlers(app, ERRORS)
    app.router.route_class = (
        A.CheckedRoute
    )  # every answer checked against its declared model while the tests run (answers.py)
    if recover:
        cache.recover(cache.stamp())
    job = app.state.sync = catalogue.Job()
    ahead = app.state.prefetch = (
        prefetch.Prefetcher()
    )  # its thread is started by main(), so tests and other hosts of the app start none

    def stream(video_id: str) -> Row:
        return dict(cache.status(video_id), **cache.plays(video_id))

    @app.get("/api/system", responses=answer(A.SystemStatus))
    def get_system():
        return dict(system_status(), prefetch=ahead.state())

    def video_or_404(video_id: str, meta: bool = False) -> Row:
        v = library.video(video_id, meta=meta)
        if v is None:
            raise HTTPException(404, f"There is no video {video_id} in the library.")
        return v

    @app.get("/api/library", responses=answer(A.LibraryStatus))
    def get_library():
        return library.status()

    @app.post("/api/library", responses=answer(A.Added))
    def post_library(b: AddIn):
        r = catalogue.add(b.input)
        if (
            r["kind"] == "channel"
        ):  # a new channel's videos arrive at once, as when storage's Sync was pressed after adding it
            r["sync"] = job.follow_up([r["channel"]["id"]])  # after the running sync's own channels, if one runs
        return r

    @app.get("/api/library/shown", responses=answer(A.ShownFilters))
    def get_shown():
        return dict(library.filters(), filtered=library.status()["filtered"], language_counts=library.languages())

    @app.put("/api/library/shown", responses=answer(A.ShownFilters))
    def put_shown(changes: dict[str, Any]):
        catalogue.save_filters(changes)
        return get_shown()

    @app.get("/api/library/sync", responses=answer(A.SyncJob))
    def get_sync():
        return job.state()

    @app.post("/api/library/sync", responses=answer(A.SyncJob))
    def post_sync(b: SyncIn | None = None):
        if not youtube.configured() and catalogue.needs_youtube(b.channels if b else None):
            raise HTTPException(503, "YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.")
        return job.start(b.channels if b else None)

    @app.get("/api/quota", responses=answer(A.QuotaUsage))
    def get_quota():
        return quota.usage()

    @app.delete("/api/channels/{channel_id}", responses=answer(A.Removed))
    def delete_channel(channel_id: str):
        return catalogue.remove(channel_id)

    @app.post("/api/channels/{channel_id}/restart", responses=answer(A.Restarted))
    def post_restart(channel_id: str):
        r = catalogue.restart(channel_id)
        if not youtube.configured() and catalogue.needs_youtube([channel_id]):
            return dict(r, sync=job.state())
        r["sync"] = job.follow_up([channel_id])
        return r

    @app.get("/api/channels", responses=answer(list[A.Channel]))
    def get_channels():
        return library.channels()

    @app.get("/api/channels/{channel_id}/overview", responses=answer(A.ChannelOverview))
    def get_channel_overview(channel_id: str):
        """Everything known of a channel (library, watch history, suggestion), whether or not the library has it."""
        return history.overview(channel_id)

    @app.post("/api/channels/{channel_id}/views", responses=answer(A.Visited))
    def post_channel_view(channel_id: str, b: FromIn | None = None):
        """Someone opened the channel's page: kept with where from, for what to suggest later (viewing.py)."""
        if library.channel(channel_id) is None:
            raise HTTPException(404, f"There is no channel {channel_id} in the library.")
        b = b or FromIn()
        return viewing.channel_view(channel_id, source=b.source, detail=b.detail)

    @app.get("/api/channels/{channel_id}", responses=answer(A.Channel))
    def get_channel(channel_id: str):
        c = library.channel(channel_id)
        if c is None:
            raise HTTPException(404, f"There is no channel {channel_id} in the library.")
        return c

    @app.get("/api/groups", responses=answer(list[A.VideoGroup]))
    def get_groups():
        return groups.listing()

    @app.get("/api/groups/{group_id}", responses=answer(A.VideoGroup))
    def get_group(group_id: int):
        g = groups.group(group_id)
        if g is None:
            raise HTTPException(404, f"There is no group {group_id}.")
        return g

    @app.get("/api/videos", responses=answer(A.VideoPage))
    def get_videos(
        channel: str | None = None,
        q: str | None = None,
        after: str | None = None,
        limit: int = Query(24, ge=1, le=200),
        group: int | None = None,
    ):
        while True:  # a past stream whose recording went is left out at once
            r = library.videos(channel, q, after, limit, group_id=group)
            gone = catalogue.recheck_past(r["videos"])
            if (channel or group is not None) and not q and not after:
                ahead.want(
                    [v["id"] for v in r["videos"] if v["id"] not in gone][:12]
                )  # a channel's or group's newest: prefetch their starts (Home's are anyway)
            if not gone:
                return r
            shown = [v for v in r["videos"] if v["id"] not in gone]
            if shown or not r["has_more"]:
                return dict(r, videos=shown)
            after = library.cursor(
                r["videos"][-1]
            )  # every one went: the page reads on from the cursor, so read the next

    @app.get("/api/videos/shuffle", responses=answer(list[A.Video]))
    def get_shuffle(count: int = Query(24, ge=1, le=200), channel: str | None = None):
        rows = library.shuffle(count, channel)
        gone = catalogue.recheck_past(rows)
        shown = [v for v in rows if v["id"] not in gone]
        ahead.want([v["id"] for v in shown[:12]])
        return shown  # Up next: prefetch their starts

    @app.get("/api/videos/continue", responses=answer(list[A.ContinueVideo]))
    def get_continue(limit: int = Query(viewing.CONTINUE_LIMIT, ge=1, le=100)):
        """Continue watching: videos part watched lately, most recent first, each with `resume` and `progress` (viewing.unfinished)."""
        return viewing.unfinished(limit)

    @app.post("/api/videos/check", responses=answer(A.Checked))
    def post_check(b: CheckIn):
        """The watching side found these videos missing (a thumbnail or a fetch failed): ask YouTube, and hide the ones it no longer has."""
        if not youtube.configured():
            raise HTTPException(503, "YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.")
        return catalogue.report(b.ids)

    @app.get("/api/videos/{video_id}", responses=answer(A.VideoDetail))
    def get_video(video_id: str):
        v = video_or_404(video_id, meta=True)  # the Watch page: its description and every metadata table too
        if catalogue.recheck_past([v]):
            v = video_or_404(video_id, meta=True)  # it went: the page says so
        return dict(v, **cache.plays(video_id))

    @app.post("/api/videos/{video_id}/play", responses=answer(A.Started))
    def post_play(video_id: str, b: FromIn | None = None):
        v = video_or_404(video_id)
        b = b or FromIn()
        copy = fetcher.plex_copy(video_id, b.decodes)  # the video itself, but for a Plex file a browser plays as it is
        fetcher.start(copy, v["title"], v["channel"])
        started = viewing.start(
            video_id, cache.stamp(), source=b.source, detail=b.detail, rank=b.rank
        )  # before the status, so its count has this play
        return dict(stream(copy), copy=copy, **started)

    @app.get("/api/plex", responses=answer(A.PlexStatus))
    def get_plex():
        if not plex.configured():
            return dict(configured=False, reachable=False, version=None, sections=[])
        ok, said = plex.reachable()
        return dict(
            configured=True,
            reachable=ok,
            version=said if ok else None,
            error=None if ok else said,
            sections=plex.sections() if ok else [],
        )

    @app.get("/api/plex/sections/{section}/filters", responses=answer(list[A.PlexFilterKind]))
    def get_plex_filters(section: str):
        return plex.filters(section)

    @app.get("/api/plex/sections/{section}/filters/{name}", responses=answer(list[A.PlexChoice]))
    def get_plex_choices(section: str, name: str):
        return plex.choices(section, name)

    def followed(items: list[Row]) -> list[Row]:
        ids = [plex.video_id(i["key"]) for i in items if i.get("key", "").isdigit()]
        if not ids:
            return items
        with db.connect() as con:
            have = {
                r[0]
                for r in con.execute(
                    f"SELECT id FROM channels WHERE follow = ? AND id IN ({', '.join('?' * len(ids))})", (True, *ids)
                )
            }
            have |= {
                r[0]
                for r in con.execute(f"SELECT id FROM videos WHERE id IN ({', '.join('?' * len(ids))})", tuple(ids))
            }
        return [dict(i, followed=plex.video_id(i["key"]) in have) for i in items]

    @app.get("/api/plex/browse", responses=answer(A.PlexPage))
    def get_plex_browse(
        request: Request, section: str, start: int = Query(0, ge=0), size: int = Query(50, ge=1, le=200)
    ):
        params = {k: v for k, v in request.query_params.items() if k not in ("section", "start", "size")}
        r = plex.browse(section, params, start, size)
        return dict(r, items=followed(r["items"]), params=plex.clean(params))

    @app.get("/api/plex/search", responses=answer(list[A.PlexItem]))
    def get_plex_search(q: str = Query(..., min_length=1, max_length=200)):
        return followed(plex.search(q))

    @app.post("/api/plex/follow", responses=answer(A.Added))
    def post_plex_follow(b: FollowIn):
        if b.key:
            r = catalogue.add_plex(b.key)
        elif b.section:
            r = catalogue.add_plex_filter(b.section, b.params or {}, b.title)
        else:
            raise HTTPException(400, "Say which show or film (key), or which library and filters (section, params).")
        cid = r["channel"]["id"] if r["kind"] == "channel" else plex.FILMS
        if r["kind"] == "channel":
            r["sync"] = job.follow_up([cid])
        return r

    @app.get("/api/plex/image")
    def get_plex_image(path: str = Query(..., max_length=300), w: int = Query(640, ge=16, le=4000)):
        f = plex.cached_image(path, w)
        return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})

    @app.post("/api/plays/{play_id}", responses=answer(A.Reported))
    def post_progress(play_id: int, b: ProgressIn):
        """How a play is going: the page reports it while it plays, on pause and end, and as it is left (POST, so a closing page can send it)."""
        return viewing.report(play_id, b.position, b.watched, b.length)

    @app.get("/api/plays", responses=answer(A.PlayPage))
    def get_plays(
        limit: int = Query(viewing.PAGE, ge=1, le=500),
        after: str | None = None,
        outcome: str | None = None,
        source: str | None = None,
    ):
        """A page of plays, newest first, with every detail kept of each (viewing.recent); `after` is the last one's cursor (`at|id`)."""
        return viewing.recent(limit, after, outcome, source)

    @app.get("/api/plays/summary", responses=answer(A.PlaySummary))
    def get_plays_summary(days: int = Query(30, ge=1, le=3650)):
        return viewing.summary(days)

    @app.get("/api/channel-views", responses=answer(A.ChannelVisitPage))
    def get_channel_views(limit: int = Query(viewing.PAGE, ge=1, le=500), after: str | None = None):
        """A page of visits to channel pages, newest first, with where each came from."""
        return viewing.channel_visits(limit, after)

    @app.get("/api/skipping", responses=answer(list[A.SegmentKind]))
    def get_skipping():
        """Every kind of segment the player can skip, with its setting (`skip_<id>`, saved through PUT /api/settings)."""
        return segments.categories()

    @app.get("/api/break", responses=answer(A.Break))
    def get_break():
        """The break the Watch page takes (settings break_*), with no url while it is off or has no page."""
        on = settings.get("break_on") == "true" and settings.get("break_url")
        return dict(
            url=settings.get("break_url") if on else None,
            minutes=settings.get_float("break_minutes"),
            limit_minutes=settings.get_float("break_limit_minutes"),
        )

    @app.get("/api/videos/{video_id}/segments", responses=answer(A.Segments))
    def get_segments(video_id: str):
        """The parts of the video the player can skip, and what it does in each kind (segments.py)."""
        video_or_404(video_id)
        return segments.for_video(video_id)

    @app.get("/api/videos/{video_id}/stream", responses=answer(A.Stream))
    def get_stream(video_id: str):
        return stream(video_id)

    @app.get("/api/media/{video_id}/{name}")
    def get_media(video_id: str, name: str):
        p = cache.served_file(video_id, name)
        if p is None:
            raise HTTPException(404, "no such file")
        e = cache.entry(video_id)
        if (
            e and e["state"] == "fetching"
        ):  # still changing: a retried download (fetcher.attempts) rewrites the playlist and its segments under the same names
            headers = {"Cache-Control": "no-store"}
            if name == cache.PLAYLIST:
                return Response(cache.served_playlist(video_id) or "", media_type=MEDIA_TYPES[".m3u8"], headers=headers)
            return FileResponse(p, media_type=MEDIA_TYPES[os.path.splitext(name)[1]], headers=headers)
        growing = name == cache.PLAYLIST and not cache.read_playlist(video_id)["complete"]
        headers = {"Cache-Control": "no-store" if growing else "private, max-age=86400"}
        return FileResponse(p, media_type=MEDIA_TYPES[os.path.splitext(name)[1]], headers=headers)

    @app.get("/api/cache", responses=answer(A.CacheReport))
    def get_cache():
        now = cache.utcnow()
        return dict(
            **cache.usage(now),
            items=[
                dict(e, protected=cache.protected(e, now, settings.get_float("protect_days")))
                for e in cache.entries(now)
            ],
        )

    @app.put("/api/cache/{video_id}")
    def put_cache(video_id: str, b: PinIn):
        if not cache.pin(video_id, b.pinned):
            raise HTTPException(404, f"{video_id} is not in the cache")
        return cache.entry(video_id)

    @app.delete("/api/cache/{video_id}", responses=answer(A.Dropped))
    def delete_cache(video_id: str):
        e = cache.entry(video_id)
        if e is None:
            raise HTTPException(404, f"{video_id} is not in the cache")
        fetcher.cancel([video_id])
        return dict(video_id=video_id, freed=cache.forget([video_id]))

    @app.post("/api/cache/evict", responses=answer(A.Evicted))
    def post_evict(b: EvictIn):
        return cache.evict(cache.utcnow(), dry_run=b.dry_run)

    @app.get("/api/suggestions", responses=answer(A.SuggestionPage))
    def get_suggestions(
        group: str | None = None,
        topic: str | None = None,
        kids: bool | None = None,
        q: str | None = None,
        dismissed: bool = False,
        limit: int = Query(history.LIST_LIMIT, ge=1, le=1000),
        order: str = "watched",
        pasted: bool = False,
    ):
        return history.suggestions(group, topic, kids, q, dismissed, limit, order, pasted)

    @app.get("/api/suggestions/summary", responses=answer(A.SuggestionSummary))
    def get_suggestions_summary():
        return history.summary()

    @app.post("/api/suggestions/refresh", responses=answer(A.RefreshedWithSummary))
    def post_suggestions_refresh():
        r = history.sync_database()["refresh"] if history.database_configured() else history.refresh()
        return dict(r, summary=history.summary())

    @app.get("/api/history", responses=answer(A.HistoryStats))
    def get_history(
        start: str | None = None,
        end: str | None = None,
        source: str | None = None,
        top: int = Query(history.TOP, ge=1, le=200),
    ):
        return dict(history.stats(start, end, source, top), sources=history.sources(), configured=youtube.configured())

    @app.post("/api/suggestions/paste", responses=answer(A.Pasted))
    def post_suggestions_paste(b: PasteIn):
        return paste.paste(b.text)

    @app.post("/api/suggestions/import", responses=answer(A.Imported))
    def post_suggestions_import(b: ImportIn):
        return history.import_text(b.text, b.source)

    @app.delete("/api/suggestions/sources/{source}", responses=answer(A.SourceRemoved))
    def delete_source(source: str):
        return history.remove_source(source)

    @app.put("/api/suggestions/groups/{group_id}", responses=answer(A.OverviewGroup))
    def put_group(group_id: int, b: NameIn):
        return history.rename_group(group_id, b.name)

    @app.put("/api/suggestions/{channel_id}", responses=answer(A.Suggestion))
    def put_suggestion(channel_id: str, b: DismissIn):
        return history.dismiss(channel_id, b.dismissed)

    @app.post("/api/suggestions/{channel_id}/videos", responses=answer(A.AddedWatched))
    def post_suggestion_videos(channel_id: str):
        if not youtube.configured():
            raise HTTPException(503, "YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.")
        history.suggestion(channel_id)
        return catalogue.add_videos(history.watched_videos(channel_id))

    web.add_web(app, STATIC, LANDING)  # last: the catch-all page
    return app


def main(argv: Sequence[str] | None = None) -> None:
    app = create_app()
    app.state.prefetch.start()
    web.serve(
        app,
        argv,
        default_port=DEFAULT_PORT,
        banner=f"data folder: {settings.data_dir()}\ncache folder: {settings.cache_dir()}",
    )
