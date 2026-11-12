"""The video library, read side: which channels and videos there are, for the screens. They are added and kept up to date from YouTube by
catalogue.py (Admin's Library page, `tubes add`, `tubes sync`); until 2026-11 another service managed them and this module copied them
from it.

Lists are newest first and paged by a cursor after the last item (`<published>|<id>`), never an offset, so a page does not shift when a sync
adds videos.

A video YouTube no longer has (`gone`, see catalogue.recheck) is left out of every list and count, but `video(id)` still finds it, so a link
to it (or its cached copy) still opens. So is a stream that is live now or scheduled (`live`, see catalogue.py's notes); a past one is
shown, and rechecked daily in case its recording goes. An
iPlayer episode is left out the same way once it is gone from the programme's list or its `expires` has passed, except while its copy is
ready in the cache: one already fetched stays watchable until the cache evicts it.

On top of that, Admin's Settings page chooses which of the rest the watching side shows (`filters`, kept in `meta` under 'shown', so in the
database for every server that reads it): a shortest and a longest length (a video whose length is not known is kept), whether past
streams and premieres are shown too, the country the server watches from (a video YouTube says does not play there is left out), which
spoken languages are shown (a video's own, else its channel's; one neither says is kept unless Admin hides those too), and whether only
videos with captions are shown.

A video whose fetch YouTube refused as not available in this country (`blocked`, catalogue.mark_blocked) is left out like a gone one,
whatever the filters say: it cannot be played here. They only narrow the lists; nothing is changed or deleted, so changing them back brings the videos back.

`now` (an ISO string, default the present) is what `expires` is compared with."""
import datetime, json

from tubes import db, youtube

VIDEO_COLUMNS = """v.id, v.platform, v.channel_id, c.title AS channel, v.title, v.published, v.duration, v.thumbnail, v.views,
                   k.state AS cache_state, k.bytes AS cache_bytes, v.gone, v.live, v.expires, v.series, v.episode"""
AVAILABLE = "((v.gone IS NULL AND v.blocked IS NULL AND (v.expires IS NULL OR v.expires > ?)) OR (v.platform = 'iplayer' AND COALESCE(k.state, '') = 'ready'))"
# still offered (one `now` argument; needs the copies joined as k): not gone, not refused as blocked in this country, not expired from iPlayer unless cached
STREAMING = "(v.gone IS NULL AND v.blocked IS NULL AND v.live IN ('live', 'upcoming'))"        # a stream live now or scheduled: cannot be played, so never shown
NOT_STREAMING = "COALESCE(v.live, '') NOT IN ('live', 'upcoming')"

FILTERS = dict(min_seconds=None, max_seconds=None, streams='current', region=None, languages=[], unknown_language='show', captions='any')
# streams: 'current' hides those live now or scheduled (they cannot be played); 'all' hides past streams and premieres too
# region: the country the server watches from (`GB`); a video YouTube says does not play there is left out. None: not checked
# languages: base language codes (`en`) a video's spoken language must be one of (`en-GB` counts as `en`); empty: every language
# unknown_language: 'show' or 'hide' a video whose language neither it nor its channel says (only with `languages` chosen)
# captions: 'any', or 'only' those with captions the uploader added (a video it is not known for, such as an iPlayer episode, is kept)
STREAMS = ('current', 'all')
CHOICES = dict(streams=STREAMS, unknown_language=('show', 'hide'), captions=('any', 'only'))
LANGUAGE = "LOWER(COALESCE(v.language, c.language))"            # a video's spoken language, else its channel's (needs the channels joined as c)


def filters():
    """Which videos the watching side shows, as Admin set them (FILTERS, None: no limit)."""
    with db.connect() as con: row = con.execute("SELECT value FROM meta WHERE key = 'shown'").fetchone()
    try: saved = json.loads(row[0]) if row and row[0] else {}
    except ValueError: saved = {}
    return {k: saved.get(k, v) for k, v in FILTERS.items()} if isinstance(saved, dict) else dict(FILTERS)


def _chosen(f):
    """The SQL (and its arguments) for what `f` leaves in, never NULL so NOT works. Needs the channels joined as c."""
    parts, args = [], []
    if f['streams'] == 'all': parts.append('v.live IS NULL')
    if f['min_seconds'] is not None: parts.append('(v.duration IS NULL OR v.duration >= ?)'); args.append(f['min_seconds'])
    if f['max_seconds'] is not None: parts.append('(v.duration IS NULL OR v.duration <= ?)'); args.append(f['max_seconds'])
    if f.get('region'):           # the lists are comma-separated codes: wrapped in commas, `,GB,` is found only as a whole code
        parts.append("(v.regions_allowed IS NULL OR (',' || v.regions_allowed || ',') LIKE ?)"); args.append(f"%,{f['region']},%")
        parts.append("(v.regions_blocked IS NULL OR (',' || v.regions_blocked || ',') NOT LIKE ?)"); args.append(f"%,{f['region']},%")
    if f.get('languages'):
        each = []
        for code in f['languages']: each.append(f'{LANGUAGE} = ? OR {LANGUAGE} LIKE ?'); args += [code, code + '-%']
        if f.get('unknown_language', 'show') == 'show': each.append(f'{LANGUAGE} IS NULL')
        parts.append('(' + ' OR '.join(each) + ')')
    if f.get('captions') == 'only': parts.append('(v.captions IS NULL OR v.captions = ?)'); args.append(True)
    return ('(' + ' AND '.join(parts) + ')' if parts else '(1 = 1)'), args


def languages(now=None):
    """The spoken languages of the videos the library offers (before Admin's filters), as base codes with how many videos each: `[{code,
    videos}]`, most first, with `code` None for those whose language is not known. What Settings offers to choose from."""
    with db.connect() as con:
        rows = con.execute(f"""SELECT {LANGUAGE}, COUNT(*) FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id
                               WHERE {AVAILABLE} AND {NOT_STREAMING} GROUP BY {LANGUAGE}""", [_now(now)]).fetchall()
    counts = {}
    for code, n in rows:
        base = code.split('-')[0] if code else None
        counts[base] = counts.get(base, 0) + n
    return [dict(code=c, videos=n) for c, n in sorted(counts.items(), key=lambda x: (-x[1], x[0] or ''))]


def shown(now=None, f=None):
    """What the lists show, as SQL and its arguments (needs the copies joined as k and the channels as c): still offered, not a stream live now or scheduled, and
    let through by Admin's filters. Never NULL, so NOT works."""
    chosen, args = _chosen(f or filters())
    return f'({AVAILABLE} AND {NOT_STREAMING} AND {chosen})', [_now(now)] + args


CHANNEL_COLUMNS = """c.id, c.platform, c.title, c.handle, c.thumbnail, c.synced, c.published, c.country, c.subscribers, c.total_videos, c.views, c.complete, c.follow,
                     c.added, c.sync_token IS NOT NULL AS resumable"""


def _now(now=None): return now or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def status(now=None):
    """`{synced, channels, videos, hidden, live, filtered, configured}`: when every followed channel was last synced (None: never), what the
    library holds (videos that can be watched; those hidden because YouTube no longer has them or iPlayer no longer offers them; streams live
    now or scheduled, hidden until they end; and those Admin's filters leave out), and whether the YouTube key is in the environment
    (without it nothing can be added or synced from YouTube)."""
    sql, args = shown(now)
    chosen, chosen_args = _chosen(filters())
    with db.connect() as con:
        synced = con.execute("SELECT value FROM meta WHERE key = 'library_synced'").fetchone()
        counts = con.execute(f"""SELECT (SELECT COUNT(*) FROM channels), COUNT(v.id), COALESCE(SUM(CASE WHEN {sql} THEN 1 ELSE 0 END), 0),
                                        COALESCE(SUM(CASE WHEN {STREAMING} THEN 1 ELSE 0 END), 0),
                                        COALESCE(SUM(CASE WHEN {AVAILABLE} AND {NOT_STREAMING} AND NOT {chosen} THEN 1 ELSE 0 END), 0)
                                 FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id""", args + [_now(now)] + chosen_args).fetchone()
    channel_count, total, videos_, live, filtered = counts
    return dict(synced=synced[0] if synced else None, channels=channel_count, videos=videos_, hidden=total - videos_ - live - filtered, live=live, filtered=filtered,
                configured=youtube.configured())


def channels(now=None):
    """Every channel with how many videos it has here to watch, how many are hidden (gone, streams not over yet, expired from iPlayer, or
    left out by Admin's filters) and its newest one's date, by title."""
    ok, args = shown(now)
    with db.connect() as con:
        rows = db.rows(con.execute(f"""SELECT {CHANNEL_COLUMNS}, COALESCE(SUM(CASE WHEN v.id IS NOT NULL AND {ok} THEN 1 ELSE 0 END), 0) AS videos,
                                       COALESCE(SUM(CASE WHEN v.id IS NOT NULL AND NOT {ok} THEN 1 ELSE 0 END), 0) AS hidden,
                                       MAX(CASE WHEN v.id IS NOT NULL AND {ok} THEN v.published END) AS latest
                                       FROM channels c LEFT JOIN videos v ON v.channel_id = c.id LEFT JOIN copies k ON k.video_id = v.id
                                       GROUP BY c.id ORDER BY LOWER(c.title), c.id""", args * 3))
    for r in rows: r.update(complete=bool(r['complete']), follow=bool(r['follow']), resumable=bool(r['resumable']))   # SQLite answers 0 and 1
    return rows


def channel(channel_id):
    return next((c for c in channels() if c['id'] == channel_id), None)


def cursor(v):
    """The cursor that asks for the videos after this one."""
    return f"{v['published']}|{v['id']}"


def videos(channel_id=None, search=None, after=None, limit=24, now=None):
    """One page of videos, newest first: `{videos, has_more}`. `search` matches words in the title, in any order; `after` is a cursor."""
    ok, args = shown(now)
    where = [ok]
    if channel_id: where.append('v.channel_id = ?'); args.append(channel_id)
    for word in (search or '').split():
        where.append("LOWER(v.title) LIKE LOWER(?) ESCAPE '\\'"); args.append('%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    if after:
        published, _, vid = after.rpartition('|')
        where.append('(v.published < ? OR (v.published = ? AND v.id < ?))'); args += [published, published, vid]
    sql = f"""SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id
              WHERE {' AND '.join(where)} ORDER BY v.published DESC, v.id DESC LIMIT ?"""
    with db.connect() as con: rows = db.rows(con.execute(sql, args + [limit + 1]))
    return dict(videos=rows[:limit], has_more=len(rows) > limit)


def shuffle(count=24, channel_id=None, now=None):
    """`count` videos picked at random (from one channel, if given), for a page that offers something different on every visit."""
    ok, args = shown(now)
    where, args = (f'WHERE {ok} AND v.channel_id = ?', args + [channel_id]) if channel_id else (f'WHERE {ok}', args)
    with db.connect() as con:
        return db.rows(con.execute(f'SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id {where} ORDER BY RANDOM() LIMIT ?', args + [count]))


def video(video_id):
    """One video with its channel's title and its copy's state, or None when the library has no such video."""
    with db.connect() as con:
        return db.row(con.execute(f'SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id WHERE v.id = ?', (video_id,)))
