"""The application server: `./tubes serve` starts the FastAPI backend and serves the built React app.

    ./tubes serve [--host 127.0.0.1] [--port 8367]

The library (channels and videos) is managed here, from YouTube and BBC iPlayer (catalogue.py writes it, library.py reads it).

API (JSON):
  GET  /api/health                         {ok, version}
  GET  /api/system                         versions (app, Python, yt-dlp, ffmpeg), folders, disk, cache use, the library copy's state, prefetching (prefetch.py)
  GET  /api/skipping                      [{id, label, detail, mode}]: every kind of segment, with what the player does in it (settings skip_<id>)
  GET  /api/videos/{id}/segments          {segments: [{category, start, end, action}], categories: [{id, label, detail, mode}], error}: what can be skipped
  GET  /api/settings, PUT /api/settings    every setting (settings.py); PUT takes any subset, a null resets one
  GET  /api/library                       {synced, channels, videos, hidden, live, filtered, configured}: when every followed channel was last synced, and whether the YouTube key is set
  POST /api/library {input}                add a channel (followed; its sync starts at once, or after the running sync's channels) or one video from a link, id or @handle; an iPlayer programme or episode link works the same way: {kind, channel|video, sync}
  GET  /api/library/shown, PUT            which videos the watching side shows (library.filters): {min_seconds, max_seconds, streams, region, languages, unknown_language, captions, filtered, language_counts}; PUT takes any subset of the filters, null for no limit; filtered is how many they leave out, language_counts the languages there are to choose from (library.languages)
  GET  /api/library/sync                   the background sync: {running, total, done, current, added, errors, started, finished}
  POST /api/library/sync {channels}        start one for these channel ids (default: every followed channel); 409 while one runs
  GET  /api/quota                         the YouTube Data API quota: today's units used of the limit, what remains, when it resets, today by
                                           purpose, endpoint and hour, and the last 30 days (quota.py; Google has no call that says this)
  GET  /api/channels, GET /api/channels/{id}   channels with their video counts and sync state
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
Every other path serves the web app (`src/tubes/server/static/index.html` when built with `cd web && npm run build`, else the plain stand-in
`landing.html`), so a reload or a shared link opens that screen: the app routes in the browser (React Router)."""
import os, platform, shutil

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tubes import __version__, cache, catalogue, fetcher, history, iplayer, library, oslib, paste, prefetch, quota, segments, settings, viewing, youtube, ytdlp

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
LANDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'landing.html')
DEFAULT_PORT = 8367
MEDIA_TYPES = {'.m3u8': 'application/vnd.apple.mpegurl', '.mp4': 'video/mp4', '.m4s': 'video/iso.segment'}


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
    source: str | None = Field(None, max_length=32)
    detail: str | None = Field(None, max_length=500)
    rank: int | None = Field(None, ge=0)


class ProgressIn(BaseModel):
    position: float | None = Field(None, ge=0)
    watched: float | None = Field(None, ge=0)
    length: float | None = Field(None, ge=0)


def system_status():
    """A snapshot for the System page. Sizes are bytes; the web app formats them."""
    du = shutil.disk_usage(settings.cache_dir())
    return dict(version=__version__, python=platform.python_version(), platform=f'{platform.system()} {platform.release()}'.strip(),
                ytdlp=ytdlp.version(), ffmpeg=fetcher.ffmpeg_version(), can_fetch=oslib.CAN_PASS_FDS,
                data_dir=settings.data_dir(), cache_dir=settings.cache_dir(), cache=cache.usage(cache.utcnow()), fetching=fetcher.running(),
                disk=dict(total=du.total, used=du.used, free=du.free), library=library.status())


def create_app():
    app = FastAPI(title='tubes', docs_url='/api/docs', openapi_url='/api/openapi.json')
    cache.recover(cache.stamp())
    job = app.state.sync = catalogue.Job()
    ahead = app.state.prefetch = prefetch.Prefetcher()             # its thread is started by main(), so tests and other hosts of the app start none

    def guard(fn, *a, **kw):
        try: return fn(*a, **kw)
        except history.ImportProblem as e: raise HTTPException(502 if 'could not be read' in str(e) else 400, str(e))
        except (settings.SettingError, fetcher.FetchError, ValueError) as e: raise HTTPException(400, str(e))
        except (catalogue.NotFound, history.NotFound, viewing.NotFound) as e: raise HTTPException(404, str(e))
        except catalogue.Job.Busy as e: raise HTTPException(409, str(e))
        except youtube.YoutubeError as e: raise HTTPException(503 if not youtube.configured() else 502, str(e))
        except iplayer.IplayerError as e: raise HTTPException(502, str(e))
        except KeyError as e: raise HTTPException(400, str(e.args[0]))

    def stream(video_id): return dict(cache.status(video_id), **cache.plays(video_id))

    @app.get('/api/health')
    def get_health(): return dict(ok=True, version=__version__)

    @app.get('/api/system')
    def get_system(): return dict(system_status(), prefetch=ahead.state())

    @app.get('/api/settings')
    def get_settings(): return settings.all_settings()

    @app.put('/api/settings')
    def put_settings(changes: dict):
        guard(settings.save, changes); return settings.all_settings()

    def video_or_404(video_id):
        v = library.video(video_id)
        if v is None: raise HTTPException(404, f'There is no video {video_id} in the library.')
        return v

    @app.get('/api/library')
    def get_library(): return library.status()

    @app.post('/api/library')
    def post_library(b: AddIn):
        r = guard(catalogue.add, b.input)
        if r['kind'] == 'channel':                                   # a new channel's videos arrive at once, as when storage's Sync was pressed after adding it
            r['sync'] = job.follow_up([r['channel']['id']])          # after the running sync's own channels, if one runs
        return r

    @app.get('/api/library/shown')
    def get_shown(): return dict(library.filters(), filtered=library.status()['filtered'], language_counts=library.languages())

    @app.put('/api/library/shown')
    def put_shown(changes: dict): guard(catalogue.save_filters, changes); return get_shown()

    @app.get('/api/library/sync')
    def get_sync(): return job.state()

    @app.post('/api/library/sync')
    def post_sync(b: SyncIn | None = None):
        if not youtube.configured() and catalogue.needs_youtube(b.channels if b else None): raise HTTPException(503, 'YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.')
        return guard(job.start, b.channels if b else None)

    @app.get('/api/quota')
    def get_quota(): return quota.usage()

    @app.delete('/api/channels/{channel_id}')
    def delete_channel(channel_id: str): return guard(catalogue.remove, channel_id)

    @app.post('/api/channels/{channel_id}/restart')
    def post_restart(channel_id: str):
        r = guard(catalogue.restart, channel_id)
        if not youtube.configured() and catalogue.needs_youtube([channel_id]): return dict(r, sync=job.state())
        r['sync'] = job.follow_up([channel_id]); return r

    @app.get('/api/channels')
    def get_channels(): return library.channels()

    @app.get('/api/channels/{channel_id}/overview')
    def get_channel_overview(channel_id: str):
        """Everything known of a channel (library, watch history, suggestion), whether or not the library has it."""
        return guard(history.overview, channel_id)

    @app.post('/api/channels/{channel_id}/views')
    def post_channel_view(channel_id: str, b: FromIn | None = None):
        """Someone opened the channel's page: kept with where from, for what to suggest later (viewing.py)."""
        if library.channel(channel_id) is None: raise HTTPException(404, f'There is no channel {channel_id} in the library.')
        b = b or FromIn(); return viewing.channel_view(channel_id, source=b.source, detail=b.detail)

    @app.get('/api/channels/{channel_id}')
    def get_channel(channel_id: str):
        c = library.channel(channel_id)
        if c is None: raise HTTPException(404, f'There is no channel {channel_id} in the library.')
        return c

    @app.get('/api/videos')
    def get_videos(channel: str | None = None, q: str | None = None, after: str | None = None, limit: int = Query(24, ge=1, le=200)):
        while True:                                                               # a past stream whose recording went is left out at once
            r = library.videos(channel, q, after, limit); gone = catalogue.recheck_past(r['videos'])
            if channel and not q and not after: ahead.want([v['id'] for v in r['videos'] if v['id'] not in gone][:12])   # a channel's newest: prefetch their starts (Home's are anyway)
            if not gone: return r
            shown = [v for v in r['videos'] if v['id'] not in gone]
            if shown or not r['has_more']: return dict(r, videos=shown)
            after = library.cursor(r['videos'][-1])                               # every one went: the page reads on from the cursor, so read the next

    @app.get('/api/videos/shuffle')
    def get_shuffle(count: int = Query(24, ge=1, le=200), channel: str | None = None):
        rows = library.shuffle(count, channel); gone = catalogue.recheck_past(rows)
        shown = [v for v in rows if v['id'] not in gone]; ahead.want([v['id'] for v in shown[:12]]); return shown     # Up next: prefetch their starts

    @app.get('/api/videos/continue')
    def get_continue(limit: int = Query(viewing.CONTINUE_LIMIT, ge=1, le=100)):
        """Continue watching: videos part watched lately, most recent first, each with `resume` and `progress` (viewing.unfinished)."""
        return viewing.unfinished(limit)

    @app.post('/api/videos/check')
    def post_check(b: CheckIn):
        """The watching side found these videos missing (a thumbnail or a fetch failed): ask YouTube, and hide the ones it no longer has."""
        if not youtube.configured(): raise HTTPException(503, 'YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.')
        return guard(catalogue.report, b.ids)

    @app.get('/api/videos/{video_id}')
    def get_video(video_id: str):
        v = video_or_404(video_id)
        if catalogue.recheck_past([v]): v = video_or_404(video_id)                     # it went: the page says so
        return dict(v, **cache.plays(video_id))

    @app.post('/api/videos/{video_id}/play')
    def post_play(video_id: str, b: FromIn | None = None):
        v = video_or_404(video_id)
        guard(fetcher.start, video_id, v['title'], v['channel'])
        b = b or FromIn()
        started = viewing.start(video_id, cache.stamp(), source=b.source, detail=b.detail, rank=b.rank)    # before the status, so its count has this play
        return dict(stream(video_id), **started)

    @app.post('/api/plays/{play_id}')
    def post_progress(play_id: int, b: ProgressIn):
        """How a play is going: the page reports it while it plays, on pause and end, and as it is left (POST, so a closing page can send it)."""
        return guard(viewing.report, play_id, b.position, b.watched, b.length)

    @app.get('/api/plays')
    def get_plays(limit: int = Query(viewing.PAGE, ge=1, le=500), after: str | None = None, outcome: str | None = None, source: str | None = None):
        """A page of plays, newest first, with every detail kept of each (viewing.recent); `after` is the last one's cursor (`at|id`)."""
        return viewing.recent(limit, after, outcome, source)

    @app.get('/api/plays/summary')
    def get_plays_summary(days: int = Query(30, ge=1, le=3650)): return viewing.summary(days)

    @app.get('/api/channel-views')
    def get_channel_views(limit: int = Query(viewing.PAGE, ge=1, le=500), after: str | None = None):
        """A page of visits to channel pages, newest first, with where each came from."""
        return viewing.channel_visits(limit, after)

    @app.get('/api/skipping')
    def get_skipping():
        """Every kind of segment the player can skip, with its setting (`skip_<id>`, saved through PUT /api/settings)."""
        return segments.categories()

    @app.get('/api/videos/{video_id}/segments')
    def get_segments(video_id: str):
        """The parts of the video the player can skip, and what it does in each kind (segments.py)."""
        video_or_404(video_id); return segments.for_video(video_id)

    @app.get('/api/videos/{video_id}/stream')
    def get_stream(video_id: str): return stream(video_id)

    @app.get('/api/media/{video_id}/{name}')
    def get_media(video_id: str, name: str):
        p = cache.served_file(video_id, name)
        if p is None: raise HTTPException(404, 'no such file')
        e = cache.entry(video_id)
        if e and e['state'] == 'fetching':        # still changing: a retried download (fetcher.attempts) rewrites the playlist and its segments under the same names
            headers = {'Cache-Control': 'no-store'}
            if name == cache.PLAYLIST: return Response(cache.served_playlist(video_id) or '', media_type=MEDIA_TYPES['.m3u8'], headers=headers)
            return FileResponse(p, media_type=MEDIA_TYPES[os.path.splitext(name)[1]], headers=headers)
        growing = name == cache.PLAYLIST and not cache.read_playlist(video_id)['complete']
        headers = {'Cache-Control': 'no-store' if growing else 'private, max-age=86400'}
        return FileResponse(p, media_type=MEDIA_TYPES[os.path.splitext(name)[1]], headers=headers)

    @app.get('/api/cache')
    def get_cache():
        now = cache.utcnow()
        return dict(**cache.usage(now), items=[dict(e, protected=cache.protected(e, now, settings.get('protect_days'))) for e in cache.entries(now)])

    @app.put('/api/cache/{video_id}')
    def put_cache(video_id: str, b: PinIn):
        if not cache.pin(video_id, b.pinned): raise HTTPException(404, f'{video_id} is not in the cache')
        return cache.entry(video_id)

    @app.delete('/api/cache/{video_id}')
    def delete_cache(video_id: str):
        e = cache.entry(video_id)
        if e is None: raise HTTPException(404, f'{video_id} is not in the cache')
        fetcher.cancel([video_id]); return dict(video_id=video_id, freed=cache.forget([video_id]))

    @app.post('/api/cache/evict')
    def post_evict(b: EvictIn): return cache.evict(cache.utcnow(), dry_run=b.dry_run)

    @app.get('/api/suggestions')
    def get_suggestions(group: str | None = None, topic: str | None = None, kids: bool | None = None, q: str | None = None, dismissed: bool = False, limit: int = Query(history.LIST_LIMIT, ge=1, le=1000), order: str = 'watched', pasted: bool = False):
        return guard(history.suggestions, group, topic, kids, q, dismissed, limit, order, pasted)

    @app.get('/api/suggestions/summary')
    def get_suggestions_summary(): return history.summary()

    @app.post('/api/suggestions/refresh')
    def post_suggestions_refresh():
        r = guard(history.sync_database)['refresh'] if history.database_configured() else history.refresh()
        return dict(r, summary=history.summary())

    @app.get('/api/history')
    def get_history(start: str | None = None, end: str | None = None, source: str | None = None, top: int = Query(history.TOP, ge=1, le=200)):
        return dict(history.stats(start, end, source, top), sources=history.sources(), configured=youtube.configured())

    @app.post('/api/suggestions/paste')
    def post_suggestions_paste(b: PasteIn): return guard(paste.paste, b.text)

    @app.post('/api/suggestions/import')
    def post_suggestions_import(b: ImportIn): return guard(history.import_text, b.text, b.source)

    @app.delete('/api/suggestions/sources/{source}')
    def delete_source(source: str): return guard(history.remove_source, source)

    @app.put('/api/suggestions/groups/{group_id}')
    def put_group(group_id: int, b: NameIn): return guard(history.rename_group, group_id, b.name)

    @app.put('/api/suggestions/{channel_id}')
    def put_suggestion(channel_id: str, b: DismissIn): return guard(history.dismiss, channel_id, b.dismissed)

    @app.post('/api/suggestions/{channel_id}/videos')
    def post_suggestion_videos(channel_id: str):
        if not youtube.configured(): raise HTTPException(503, 'YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.')
        guard(history.suggestion, channel_id)
        return guard(catalogue.add_videos, history.watched_videos(channel_id))

    if os.path.isdir(os.path.join(STATIC, 'assets')): app.mount('/assets', StaticFiles(directory=os.path.join(STATIC, 'assets')), name='assets')

    @app.get('/{path:path}', response_class=HTMLResponse, include_in_schema=False)
    def page(path: str):
        if path.startswith('api/'): raise HTTPException(404, 'no such endpoint')
        top = static_file(path)
        if top: return FileResponse(top)     # favicon.svg and the like, built from web/public
        built = os.path.join(STATIC, 'index.html')          # the React app when it has been built (cd web && npm run build), else the plain stand-in page
        with open(built if os.path.exists(built) else LANDING, encoding='utf8') as f: html = f.read()
        return with_base(html, path)

    return app


def static_file(path: str) -> str | None:
    """The built file at the top of the static folder that `path` names, or None. Only a plain file name is served: a path with either separator,
    a drive or `..` could reach outside the folder (on Windows `..\\app.py` has no `/`, and `os.path.join` drops STATIC for `C:\\...`), so the
    resolved file must also sit directly in STATIC."""
    if not path or '/' in path or '\\' in path or ':' in path or path in ('.', '..'): return None
    root = os.path.realpath(STATIC)
    full = os.path.realpath(os.path.join(root, path))
    return full if os.path.dirname(full) == root and os.path.isfile(full) else None


def with_base(html: str, path: str) -> str:
    """Give the page a relative <base> that points back at where the app is served, so one build works at the server's root and behind a reverse proxy at /<prefix>/.

    The server only sees the path under its own root (`settings`, `a/b`), never the proxy's prefix, but that is enough: the depth says how many `../` lead back up.
    The web app reads its base from `document.baseURI` (web/src/api.ts BASE), for its API calls and as React Router's basename, and its assets are relative (vite.config.ts base './')."""
    depth = path.count('/')
    tag = f'<base href="{"../" * depth or "./"}">'
    return html.replace('<head>', '<head>' + tag, 1) if '<head>' in html else tag + html


def main(argv=None):
    import argparse, uvicorn
    a = argparse.ArgumentParser(); a.add_argument('--host', default='127.0.0.1'); a.add_argument('--port', type=int, default=DEFAULT_PORT); a = a.parse_args(argv)
    print(f'data folder: {settings.data_dir()}\ncache folder: {settings.cache_dir()}\nhttp://{a.host}:{a.port}/'); app = create_app(); app.state.prefetch.start()
    uvicorn.run(app, host=a.host, port=a.port, log_level='warning')
