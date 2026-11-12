"""The video library, read side: which channels and videos there are, for the screens. They are added and kept up to date from YouTube by
catalogue.py (Admin's Library page, `tubes add`, `tubes sync`); until 2026-11 another service managed them and this module copied them
from it.

Lists are newest first and paged by a cursor after the last item (`<published>|<id>`), never an offset, so a page does not shift when a sync
adds videos.

A video YouTube no longer has (`gone`, see catalogue.recheck) is left out of every list and count, but `video(id)` still finds it, so a link
to it (or its cached copy) still opens. So is a stream that is live now or scheduled (`live`, see catalogue.py's notes); a past one is
shown, and rechecked daily in case its recording goes."""
from tubes import db, youtube

VIDEO_COLUMNS = """v.id, v.channel_id, c.title AS channel, v.title, v.published, v.duration, v.thumbnail, v.views,
                   k.state AS cache_state, k.bytes AS cache_bytes, v.gone, v.live"""
HIDDEN = "(v.gone IS NOT NULL OR COALESCE(v.live, '') IN ('live', 'upcoming'))"            # gone from YouTube, or a stream not over yet
SHOWN = f'NOT {HIDDEN}'                                                          # what the lists show
CHANNEL_COLUMNS = """c.id, c.title, c.handle, c.thumbnail, c.synced, c.published, c.country, c.subscribers, c.total_videos, c.views, c.complete, c.follow,
                     c.added, c.sync_token IS NOT NULL AS resumable"""


def status():
    """`{synced, channels, videos, hidden, live, configured}`: when every followed channel was last synced (None: never), what the library
    holds (videos that can be watched, those hidden because YouTube no longer has them, and streams live now or scheduled, hidden until they end), and whether the YouTube key is in the environment
    (without it nothing can be added or synced)."""
    with db.connect() as con:
        synced = con.execute("SELECT value FROM meta WHERE key = 'library_synced'").fetchone()
        counts = con.execute(f'SELECT (SELECT COUNT(*) FROM channels), (SELECT COUNT(*) FROM videos v WHERE {SHOWN}), (SELECT COUNT(*) FROM videos WHERE gone IS NOT NULL), '
                             "(SELECT COUNT(*) FROM videos WHERE gone IS NULL AND live IN ('live', 'upcoming'))").fetchone()
    return dict(synced=synced[0] if synced else None, channels=counts[0], videos=counts[1], hidden=counts[2], live=counts[3], configured=youtube.configured())


def channels():
    """Every channel with how many videos it has here to watch, how many are hidden (gone from YouTube, or streams not over yet) and its newest one's date, by title."""
    with db.connect() as con:
        rows = db.rows(con.execute(f"""SELECT {CHANNEL_COLUMNS}, COUNT(v.id) - COUNT(CASE WHEN {HIDDEN} THEN 1 END) AS videos,
                                       COUNT(CASE WHEN {HIDDEN} THEN 1 END) AS hidden, MAX(CASE WHEN {SHOWN} THEN v.published END) AS latest FROM channels c LEFT JOIN videos v ON v.channel_id = c.id
                                       GROUP BY c.id ORDER BY LOWER(c.title), c.id"""))
    for r in rows: r.update(complete=bool(r['complete']), follow=bool(r['follow']), resumable=bool(r['resumable']))   # SQLite answers 0 and 1
    return rows


def channel(channel_id):
    return next((c for c in channels() if c['id'] == channel_id), None)


def cursor(v):
    """The cursor that asks for the videos after this one."""
    return f"{v['published']}|{v['id']}"


def videos(channel_id=None, search=None, after=None, limit=24):
    """One page of videos, newest first: `{videos, has_more}`. `search` matches words in the title, in any order; `after` is a cursor."""
    where, args = [SHOWN], []
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


def shuffle(count=24, channel_id=None):
    """`count` videos picked at random (from one channel, if given), for a page that offers something different on every visit."""
    where, args = (f'WHERE {SHOWN} AND v.channel_id = ?', [channel_id]) if channel_id else (f'WHERE {SHOWN}', [])
    with db.connect() as con:
        return db.rows(con.execute(f'SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id {where} ORDER BY RANDOM() LIMIT ?', args + [count]))


def video(video_id):
    """One video with its channel's title and its copy's state, or None when the library has no such video."""
    with db.connect() as con:
        return db.row(con.execute(f'SELECT {VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id WHERE v.id = ?', (video_id,)))
