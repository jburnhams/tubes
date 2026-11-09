"""The application server: `./tubes serve` starts the FastAPI backend and serves the built React app.

    ./tubes serve [--host 127.0.0.1] [--port 8367]

The library (channels and videos) is managed elsewhere and copied here by `tubes sync` (library.py); the screens read the copy.

API (JSON):
  GET  /api/health                         {ok, version}
  GET  /api/system                         versions (app, Python, yt-dlp, ffmpeg), folders, disk, cache use, the library copy's state
  GET  /api/settings, PUT /api/settings    every setting (settings.py); PUT takes any subset, a null resets one
  GET  /api/library, POST /api/library/sync   the library copy: {synced, channels, videos, configured}; sync refreshes it from D1
  GET  /api/channels, GET /api/channels/{id}   channels with their video counts
  GET  /api/videos?channel=&q=&after=&limit=   a page of videos, newest first: {videos, has_more}; `after` is the last one's cursor (`published|id`)
  GET  /api/videos/shuffle?count=&channel=     videos picked at random
  GET  /api/videos/{id}                    one video, with its copy's state, plays and last play
  POST /api/videos/{id}/play               record a play of a library video and start fetching unless it is cached; returns the stream status
  GET  /api/videos/{id}/stream             the stream status: {state, segments, seconds, complete, playable, error, formats, plays, last_played}
  GET  /api/media/{id}/{file}              the HLS playlist, init segment and segments (only those names; the playlist is never cached while it grows)
  GET  /api/cache                          use, limit and every cached video with its score
  PUT  /api/cache/{id} {pinned}            pin or unpin a copy
  DELETE /api/cache/{id}                   delete a copy now
  POST /api/cache/evict {dry_run}          run eviction
Every other path serves the web app (`src/tubes/server/static/index.html` when built with `cd web && npm run build`, else the plain stand-in
`landing.html`), so a reload or a shared link opens that screen: the app routes in the browser (React Router)."""
import os, platform, shutil

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tubes import __version__, cache, fetcher, library, oslib, settings, ytdlp

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
LANDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'landing.html')
DEFAULT_PORT = 8367
MEDIA_TYPES = {'.m3u8': 'application/vnd.apple.mpegurl', '.mp4': 'video/mp4', '.m4s': 'video/iso.segment'}


class PinIn(BaseModel):
    pinned: bool


class EvictIn(BaseModel):
    dry_run: bool = False


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

    def guard(fn, *a, **kw):
        try: return fn(*a, **kw)
        except (settings.SettingError, fetcher.FetchError) as e: raise HTTPException(400, str(e))
        except library.LibraryError as e: raise HTTPException(502, str(e))
        except KeyError as e: raise HTTPException(400, str(e.args[0]))

    def stream(video_id): return dict(cache.status(video_id), **cache.plays(video_id))

    @app.get('/api/health')
    def get_health(): return dict(ok=True, version=__version__)

    @app.get('/api/system')
    def get_system(): return system_status()

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

    @app.post('/api/library/sync')
    def post_sync(): return guard(library.sync)

    @app.get('/api/channels')
    def get_channels(): return library.channels()

    @app.get('/api/channels/{channel_id}')
    def get_channel(channel_id: str):
        c = library.channel(channel_id)
        if c is None: raise HTTPException(404, f'There is no channel {channel_id} in the library.')
        return c

    @app.get('/api/videos')
    def get_videos(channel: str | None = None, q: str | None = None, after: str | None = None, limit: int = Query(24, ge=1, le=200)):
        return library.videos(channel, q, after, limit)

    @app.get('/api/videos/shuffle')
    def get_shuffle(count: int = Query(24, ge=1, le=200), channel: str | None = None): return library.shuffle(count, channel)

    @app.get('/api/videos/{video_id}')
    def get_video(video_id: str): return dict(video_or_404(video_id), **cache.plays(video_id))

    @app.post('/api/videos/{video_id}/play')
    def post_play(video_id: str):
        v = video_or_404(video_id)
        guard(fetcher.start, video_id, v['title'], v['channel'])
        cache.record_play(video_id, cache.stamp()); return stream(video_id)

    @app.get('/api/videos/{video_id}/stream')
    def get_stream(video_id: str): return stream(video_id)

    @app.get('/api/media/{video_id}/{name}')
    def get_media(video_id: str, name: str):
        p = cache.file_path(video_id, name)
        if p is None: raise HTTPException(404, 'no such file')
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
    print(f'data folder: {settings.data_dir()}\ncache folder: {settings.cache_dir()}\nhttp://{a.host}:{a.port}/'); uvicorn.run(create_app(), host=a.host, port=a.port, log_level='warning')
