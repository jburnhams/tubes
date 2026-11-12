"""What is watched here: each play, where it was started from and how much of it was seen, and each visit to a channel's page. It is what
Continue watching is made from, and kept so that later work can learn what is worth suggesting (a click that ends after a few seconds says
something different from one watched to the end).

A play starts when the watch page opens (`start`, from POST /api/videos/{id}/play): the row says where the click came from (`source`, one of
SOURCES: the home grid, Continue watching, a channel's page, a search, Up next, or `link` for an address typed, reloaded or shared), which
one (`detail`: the channel's id, the search words, the video Up next was beside) and the video's place in that list (`rank`, from 0). While
it plays the page reports how it is going (`report`, from POST /api/plays/{id}): the running time, where the player is, and how many
seconds have been seen, each second counted once (going back over a part does not add to it; a part skipped as a sponsor read or an intro
counts as seen, so a video whose skipped parts make up a tenth of it can still be watched in full). From those, `outcome`:

  none     nothing seen yet (the fetch failed, or the page was left before the picture started)
  short    under PARTIAL of it (a tenth) seen, or under SHORT_SECONDS when the running time is not known: a look, then away
  partial  more than that, but under FULL
  full     FULL (90%) and more of it seen

The page reports every few seconds while it plays, when it pauses or ends, and as it is left, so a closed tab loses a few seconds at most.
A report only moves `watched` up: a late report from a page that knew less cannot undo a fuller one.

Continue watching (`unfinished`) is the videos with a partial play in the last CONTINUE_DAYS and no full play since (nor one that stopped
in the last tenth: a video watched in two halves is two partial plays, and finished), most recently played
first, each with where it stopped; a new play of one picks up there (`start` returns `resume`). Shorter plays after the partial one do not
take it off the list, and their position is where it picks up. Only videos the watching side shows (library.shown) are offered.

Channel views (`channel_view`) are one row per visit to a channel's page with where the visit came from (the rail, the Channels page, the
chips on Home, a video's card on one of the lists above, the watch page).

The imported histories (history.py) are kept apart: they say what was watched on YouTube, never how much, and they feed the channel
suggestions, which list only channels the library does not follow yet."""
import datetime

from tubes import db, library

FULL = 0.9
PARTIAL = 0.1
SHORT_SECONDS = 60
CONTINUE_DAYS = 30
CONTINUE_LIMIT = 12
SOURCES = ('home', 'continue', 'channel', 'search', 'up_next', 'watch', 'rail', 'chips', 'channels', 'link')
OUTCOMES = ('none', 'short', 'partial', 'full')
DETAIL_MAX = 200
RESUME_MIN = 10                                                                # seconds: a play stopped before this starts again from the beginning


class NotFound(Exception):
    pass


def _now(now=None): return now or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def _source(source):
    """A known source name, `link` when none was given, `other` for a name this server does not know (a newer page, say)."""
    if not source: return 'link'
    return source if source in SOURCES else 'other'


def _detail(detail):
    return str(detail)[:DETAIL_MAX] if detail not in (None, '') else None


def outcome(watched, length):
    """none, short, partial or full: how much of a video `watched` seconds of it is (see the module's notes)."""
    if not watched or watched <= 0: return 'none'
    if not length or length <= 0: return 'short' if watched < SHORT_SECONDS else 'partial'
    share = watched / length
    return 'full' if share >= FULL else 'partial' if share >= PARTIAL else 'short'


def resume(video_id, now=None):
    """Where a new play of this video picks up: the last position of its latest play since a partial one in the last CONTINUE_DAYS, if no
    full play came after; None when it starts from the beginning (as it does when that position is under RESUME_MIN or in the last tenth)."""
    found = _unfinished(now, video_id=video_id)
    if not found or found[0]['position'] is None: return None
    position, length = found[0]['position'], found[0]['length']
    if position < RESUME_MIN or (length and position >= length * FULL): return None     # hardly started, or as good as over: from the start
    return position


def start(video_id, now=None, source=None, detail=None, rank=None):
    """Record a play: `{play_id, resume}`, `resume` being where it picks up (None: from the start)."""
    now = _now(now)
    picks_up = resume(video_id, now)
    rank = rank if isinstance(rank, int) and rank >= 0 else None
    with db.connect() as con:
        play_id = con.execute('INSERT INTO plays (video_id, at, source, detail, rank, outcome) VALUES (?, ?, ?, ?, ?, ?) RETURNING id',
                              (video_id, now, _source(source), _detail(detail), rank, 'none')).scalar_one()
    return dict(play_id=play_id, resume=picks_up)


def report(play_id, position=None, watched=None, length=None, now=None):
    """How a play is going, as its page sees it: `{play_id, video_id, watched, position, length, outcome}`. NotFound for no such play."""
    now = _now(now)
    with db.connect() as con:
        r = db.row(con.execute('SELECT p.video_id, p.watched, p.length, p.position, v.duration FROM plays p LEFT JOIN videos v ON v.id = p.video_id WHERE p.id = ?', (play_id,)))
        if r is None: raise NotFound(f'There is no play {play_id}.')
        length = length if length and length > 0 else r['length'] or r['duration'] or None       # the player's own figure, else the library's
        seen = max(r['watched'] or 0.0, watched or 0.0)
        if length: seen = min(seen, length)
        position = position if position is not None and position >= 0 else r['position']
        result = outcome(seen, length)
        con.execute('UPDATE plays SET watched = ?, position = ?, length = ?, outcome = ?, updated = ? WHERE id = ?', (seen, position, length, result, now, play_id))
    return dict(play_id=play_id, video_id=r['video_id'], watched=seen, position=position, length=length, outcome=result)


def _unfinished(now=None, video_id=None):
    """`[{video_id, position, length, at}]`: what Continue watching offers (see the module's notes), most recently played first."""
    now = _now(now)
    since = (datetime.datetime.fromisoformat(now) - datetime.timedelta(days=CONTINUE_DAYS)).isoformat(timespec='seconds')
    sql = 'SELECT video_id, at, outcome, position, length FROM plays WHERE at >= ? AND outcome IS NOT NULL'
    args = [since]
    if video_id: sql += ' AND video_id = ?'; args.append(video_id)
    with db.connect() as con: plays = con.execute(sql + ' ORDER BY at, id', args).fetchall()
    per = {}
    for vid, at, out, position, length in plays:                              # oldest first, so the last word on each video wins
        if out == 'full' or (position is not None and length and position >= length * FULL): per.pop(vid, None)   # finished, here or over several plays
        elif out == 'partial': per[vid] = dict(video_id=vid, position=position, length=length, at=at)
        elif vid in per:                                                      # a short look after it: still unfinished, and picks up where that left it
            if position is not None: per[vid].update(position=position)
            per[vid]['at'] = at
    return sorted(per.values(), key=lambda p: p['at'], reverse=True)


def unfinished(limit=CONTINUE_LIMIT, now=None):
    """Continue watching: the library's videos (as library.videos gives them) the watching side shows, each with `resume` (seconds) and
    `progress` (0-1, how far through it that is), most recently played first."""
    found = _unfinished(now)
    if not found: return []
    ok, args = library.shown(now)
    ids = [p['video_id'] for p in found]
    with db.connect() as con:
        rows = {r['id']: r for r in db.rows(con.execute(f'''SELECT {library.VIDEO_COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id
                                                             WHERE {ok} AND v.id IN ({', '.join('?' * len(ids))})''', args + ids))}
    out = []
    for p in found:
        v = rows.get(p['video_id'])
        if v is None: continue
        length = p['length'] or v['duration']
        progress = min(1.0, max(0.0, (p['position'] or 0) / length)) if length else None
        out.append(dict(v, resume=p['position'], progress=round(progress, 4) if progress is not None else None))
        if len(out) >= limit: break
    return out


def channel_view(channel_id, now=None, source=None, detail=None):
    """Record a visit to a channel's page: `{id}`."""
    with db.connect() as con:
        view_id = con.execute('INSERT INTO channel_views (channel_id, at, source, detail) VALUES (?, ?, ?, ?) RETURNING id',
                              (channel_id, _now(now), _source(source), _detail(detail))).scalar_one()
    return dict(id=view_id)


def recent(limit=50):
    """The latest plays, newest first, with their video's title and channel: `[{id, video_id, title, channel, at, source, detail, rank,
    length, watched, position, outcome}]`."""
    with db.connect() as con:
        return db.rows(con.execute('''SELECT p.id, p.video_id, COALESCE(v.title, k.title) AS title, COALESCE(c.title, k.channel) AS channel, p.at, p.source, p.detail, p.rank,
                                             p.length, p.watched, p.position, p.outcome
                                      FROM plays p LEFT JOIN videos v ON v.id = p.video_id LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = p.video_id
                                      ORDER BY p.at DESC, p.id DESC LIMIT ?''', (limit,)))


def summary(days=30, now=None):
    """The last `days` of viewing in numbers: `{since, plays, outcomes: {none, short, partial, full}, sources: {source: {plays, full}},
    channel_views: {source: views}}`; plays from before outcomes were kept count under none."""
    since = (datetime.datetime.fromisoformat(_now(now)) - datetime.timedelta(days=days)).isoformat(timespec='seconds')
    with db.connect() as con:
        plays = con.execute('SELECT source, outcome, COUNT(*) FROM plays WHERE at >= ? GROUP BY source, outcome', (since,)).fetchall()      # NULLs folded in below (a bound
        views = con.execute('SELECT source, COUNT(*) FROM channel_views WHERE at >= ? GROUP BY source', (since,)).fetchall()                # default in GROUP BY fails on Postgres)
    outcomes, sources, viewed = dict.fromkeys(OUTCOMES, 0), {}, {}
    for source, out, n in plays:
        source, out = source or 'link', out or 'none'
        outcomes[out] = outcomes.get(out, 0) + n
        s = sources.setdefault(source, dict(plays=0, full=0)); s['plays'] += n
        if out == 'full': s['full'] += n
    for source, n in views: viewed[source or 'link'] = viewed.get(source or 'link', 0) + n
    return dict(since=since, plays=sum(outcomes.values()), outcomes=outcomes, sources=dict(sorted(sources.items())), channel_views=dict(sorted(viewed.items())))
