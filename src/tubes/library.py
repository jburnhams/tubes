"""The video library: which channels and videos there are. They are not managed here. They live in a Cloudflare D1 database (`d1_database`)
that another service fills, in two tables: `youtube_channels` and `youtube_videos` (the schema of the storage service, whose screens add
channels and sync their videos). Tubes only reads it.

Reading D1 from the server costs 0.4-0.5 s a query (measured from the home server, 2026-11-09), too slow for every page, so `sync` copies the
columns the screens need into Tubes' own database (`channels`, `videos`; descriptions and raw JSON stay behind) and the screens read that copy.
A sync replaces the copy in one transaction, so a channel or video removed upstream goes here too. 40,000 videos take about ten queries of
5,000 rows each. The credentials are Cloudflare's own environment variables, `CLOUDFLARE_API_TOKEN` (with D1 read) and
`CLOUDFLARE_ACCOUNT_ID`, as wrangler reads them; they are never stored in the settings file. `TUBES_D1_API` points the queries at another
address (the tests' stand-in D1).

Lists are newest first and paged by a cursor after the last item (`<published>|<id>`), never an offset, so a page does not shift when a sync
adds videos."""
import json, os, urllib.error, urllib.request

from tubes import cache, db, settings

API = 'https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query'
TIMEOUT = 60
PAGE = 5000
CHANNEL_SQL = """SELECT youtube_id AS id, title, custom_url AS handle, COALESCE(best_thumbnail_url, thumbnail_url) AS thumbnail, last_sync_at AS synced
                 FROM youtube_channels ORDER BY youtube_id"""
VIDEO_SQL = """SELECT youtube_id AS id, channel_id, title, published_at AS published, duration_seconds AS duration,
                      COALESCE(best_thumbnail_url, thumbnail_url) AS thumbnail, view_count AS views
               FROM youtube_videos WHERE youtube_id > ? ORDER BY youtube_id LIMIT ?"""
VIDEO_COLUMNS = """v.id, v.channel_id, c.title AS channel, v.title, v.published, v.duration, v.thumbnail, v.views,
                   k.state AS cache_state, k.bytes AS cache_bytes"""


class LibraryError(RuntimeError):
    """The library could not be read; the message says why, in a sentence."""


def credentials():
    """(account, token, database), or LibraryError naming what is missing."""
    account, token, database = os.environ.get('CLOUDFLARE_ACCOUNT_ID', ''), os.environ.get('CLOUDFLARE_API_TOKEN', ''), settings.get('d1_database')
    missing = [name for name, v in (('the d1_database setting', database), ('CLOUDFLARE_ACCOUNT_ID', account), ('CLOUDFLARE_API_TOKEN', token)) if not v]
    if missing: raise LibraryError(f'The library cannot be read without {" and ".join(missing)}.')
    return account, token, database


def query(sql, params=()):
    """Run one read on the library's D1 database; returns its rows as dicts."""
    account, token, database = credentials()
    req = urllib.request.Request(os.environ.get('TUBES_D1_API', API).format(account=account, database=database), data=json.dumps(dict(sql=sql, params=list(params))).encode(), method='POST',
                                 headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r: body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: why = '; '.join(err.get('message', '') for err in json.loads(e.read()).get('errors', [])) or None
        except ValueError: why = None
        raise LibraryError(f'D1 refused the query ({e.code}{": " + why if why else ""}).') from None
    except (urllib.error.URLError, OSError) as e: raise LibraryError(f'D1 could not be reached: {getattr(e, "reason", e)}.') from None
    except ValueError: raise LibraryError('D1 did not answer with JSON.') from None
    if not body.get('success') or not body.get('result'): raise LibraryError('D1 said the query failed: ' + ('; '.join(e.get('message', '') for e in body.get('errors') or []) or 'no reason given') + '.')
    return body['result'][0].get('results') or []


def fetch_all():
    """Every channel, and every video in pages of PAGE, from D1."""
    channels = query(CHANNEL_SQL); videos, after = [], ''
    while True:
        page = query(VIDEO_SQL, (after, PAGE)); videos += page
        if len(page) < PAGE: return channels, videos
        after = page[-1]['id']


def sync(now=None):
    """Replace the local copy with what D1 holds now; returns `{channels, videos, synced}`. Nothing changes if reading D1 fails part way."""
    channels, videos = fetch_all(); now = now or cache.stamp()
    with db.connect() as con:
        con.execute('DELETE FROM videos'); con.execute('DELETE FROM channels')
        con.executemany('INSERT INTO channels (id, title, handle, thumbnail, synced) VALUES (:id, :title, :handle, :thumbnail, :synced)', channels)
        con.executemany('INSERT INTO videos (id, channel_id, title, published, duration, thumbnail, views) VALUES (:id, :channel_id, :title, :published, :duration, :thumbnail, :views)', videos)
        con.execute("INSERT INTO meta (key, value) VALUES ('library_synced', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (now,))
    return dict(channels=len(channels), videos=len(videos), synced=now)


def status():
    """`{synced, channels, videos, configured}`: when the copy was last refreshed (None: never) and what it holds."""
    with db.connect() as con:
        synced = con.execute("SELECT value FROM meta WHERE key = 'library_synced'").fetchone()
        counts = con.execute('SELECT (SELECT COUNT(*) FROM channels), (SELECT COUNT(*) FROM videos)').fetchone()
    try: credentials(); configured = True
    except LibraryError: configured = False
    return dict(synced=synced[0] if synced else None, channels=counts[0], videos=counts[1], configured=configured)


def channels():
    """Every channel with how many videos it has here, by title."""
    with db.connect() as con:
        return db.rows(con.execute("""SELECT c.*, COUNT(v.id) AS videos, MAX(v.published) AS latest FROM channels c LEFT JOIN videos v ON v.channel_id = c.id
                                      GROUP BY c.id ORDER BY LOWER(c.title), c.id"""))


def channel(channel_id):
    return next((c for c in channels() if c['id'] == channel_id), None)


def cursor(v):
    """The cursor that asks for the videos after this one."""
    return f"{v['published']}|{v['id']}"


def videos(channel_id=None, search=None, after=None, limit=24):
    """One page of videos, newest first: `{videos, has_more}`. `search` matches words in the title, in any order; `after` is a cursor."""
    where, args = [], []
    if channel_id: where.append('v.channel_id = ?'); args.append(channel_id)
    for word in (search or '').split():
        where.append("LOWER(v.title) LIKE LOWER(?) ESCAPE '\\'"); args.append('%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    if after:
        published, _, vid = after.rpartition('|')
        where.append('(v.published < ? OR (v.published = ? AND v.id < ?))'); args += [published, published, vid]
    sql = f"""SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id
              {'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY v.published DESC, v.id DESC LIMIT ?"""
    with db.connect() as con: rows = db.rows(con.execute(sql, args + [limit + 1]))
    return dict(videos=rows[:limit], has_more=len(rows) > limit)


def shuffle(count=24, channel_id=None):
    """`count` videos picked at random (from one channel, if given), for a page that offers something different on every visit."""
    where, args = ('WHERE v.channel_id = ?', [channel_id]) if channel_id else ('', [])
    with db.connect() as con:
        return db.rows(con.execute(f'SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id {where} ORDER BY RANDOM() LIMIT ?', args + [count]))


def video(video_id):
    """One video with its channel's title and its copy's state, or None when the library has no such video."""
    with db.connect() as con:
        return db.row(con.execute(f'SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id WHERE v.id = ?', (video_id,)))
