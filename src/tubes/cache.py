"""The cache of fetched videos: one folder per video under `cache_dir`, holding an HLS playlist (`index.m3u8`), its init segment and 4-second
fMP4 segments, plus a row in the `copies` table. And eviction: when the cache passes 95% of its limit, the lowest-scoring videos go until it is
under 90%.

The score mixes popularity and recency: every play counts, and a play counts half as much for every `half_life_days` since it happened, so a
video played 10 times two months ago (about 2.5) and one played 3 times this week (about 2.8) both stay ahead of one played once a month ago
(0.5). Never evicted: a video being fetched, one pinned, one played in the last day. Kept for `protect_days` after it was fetched: a
video nobody has played yet (it was just asked for, or prefetched). Failed fetches go first. An evicted video stays in the library and is
fetched again the next time it is played. Plays are recorded here too (`record_play`), whether or not the copy is still kept.

A copy can also be `partial`: only its first seconds, fetched ahead of a play (prefetch.py), so the player starts at once. Its playlist is
kept twice, as `index.m3u8` and `prefix.m3u8`, with its init segment as `prefix-init.mp4` and the formats it was cut from in `prefix.json`.
When it is played, the whole video is fetched into the same folder (`resume`) from the same formats, and ffmpeg cuts the same segments
under the same names, byte for byte (measured on the home server, 2026-11-13: three videos, each probed afresh): it rewrites them in place
(each segment is written to a temporary name and renamed, so a reader never sees half of one) and starts `index.m3u8` again from nothing.
Until that playlist is longer than the prefix's, the player is given the prefix's (`served_playlist`) and its init segment (`served_file`),
so what it already plays never shrinks or changes."""
import hashlib, json, os, re, shutil
from datetime import datetime, timedelta, timezone

from tubes import db, settings

PLAYLIST = 'index.m3u8'
PREFIX, PREFIX_INIT, PREFIX_INFO = 'prefix.m3u8', 'prefix-init.mp4', 'prefix.json'     # a partial copy's playlist, init segment and formats; never served by name
FILE_NAME = re.compile(r'^(index\.m3u8|init\.mp4|seg_\d{5}\.m4s)$')
SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
HIGH, LOW = 0.95, 0.90
RECENT_PLAY = timedelta(days=1)


def folder_name(video_id):
    """The video's folder name: its id when that is a plain file name, else a hash of it (ids from some sites carry `/` or `:`)."""
    return video_id if SAFE_ID.match(video_id) else 'h' + hashlib.sha1(video_id.encode()).hexdigest()[:16]


def folder(video_id):
    return os.path.join(settings.cache_dir(), folder_name(video_id))


def file_path(video_id, name):
    """The path of one served file of a video, or None when the name is not one the cache writes (nothing else is ever served)."""
    if not FILE_NAME.match(name or ''): return None
    p = os.path.join(folder(video_id), name)
    return p if os.path.isfile(p) else None


def served_file(video_id, name):
    """The path to serve for one of a video's files, or None: as file_path, except that while a copy is fetched again from its prefix, its
    init segment is the prefix's (ffmpeg writes `init.mp4` again, identical, but not through a temporary name)."""
    p = file_path(video_id, name)
    if p and name == 'init.mp4':
        keep = os.path.join(folder(video_id), PREFIX_INIT)
        if os.path.isfile(keep): return keep
    return p


def folder_bytes(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try: total += os.path.getsize(os.path.join(root, name))
            except OSError: pass
    return total


def read_playlist(video_id):
    """What the playlist says so far: `{segments, seconds, complete}` (zeros when there is none yet)."""
    try:
        with open(os.path.join(folder(video_id), PLAYLIST), encoding='utf8') as f: text = f.read()
    except OSError: return dict(segments=0, seconds=0.0, complete=False)
    return summary(text)


def summary(text):
    """`{segments, seconds, complete}` of a playlist's text."""
    lengths = [float(m) for m in re.findall(r'^#EXTINF:([\d.]+)', text or '', re.M)]
    return dict(segments=len(lengths), seconds=round(sum(lengths), 3), complete='#EXT-X-ENDLIST' in (text or ''))


def served_playlist(video_id, e=None):
    """The playlist as the player is given it, or None when there is none: while the copy is fetching, without `#EXT-X-ENDLIST` (nor the segment before it). A download
    that ends short also ends its playlist, and the fetcher then runs it again (fetcher.attempts) into the same names; a player that read the
    end would stop following and never see the rest."""
    try:
        with open(os.path.join(folder(video_id), PLAYLIST), encoding='utf8') as f: text = f.read()
    except OSError: return None
    e = e or entry(video_id)
    if not (e and e['state'] == 'fetching'): return text
    text = _held_back(text)
    try:
        with open(os.path.join(folder(video_id), PREFIX), encoding='utf8') as f: prefix = f.read()
    except OSError: return text
    return prefix if summary(prefix)['segments'] > summary(text)['segments'] else text     # a fetch from a prefix: never less than the player was given


def _held_back(text):
    """A fetching copy's playlist without an ended attempt's end and last segment (see served_playlist)."""
    if '#EXT-X-ENDLIST' not in text: return text
    # An attempt that ended: its last segment may be cut short (the stream stopped mid-segment), and a retry rewrites it whole under the same
    # name, so a player given the short one would keep it and jump a gap. Until the copy is ready, that segment is held back as well.
    lines = [ln for ln in text.splitlines(keepends=True) if ln.strip() != '#EXT-X-ENDLIST']
    uris = [i for i, ln in enumerate(lines) if ln.strip() and not ln.startswith('#')]
    if uris:
        last = uris[-1]; tag = max((i for i in range(last) if lines[i].startswith('#EXTINF')), default=last)
        del lines[tag:last + 1]
    return ''.join(lines)


def entry(video_id):
    with db.connect() as con: return db.row(con.execute('SELECT * FROM copies WHERE video_id = ?', (video_id,)))


def status(video_id):
    """The state of a video's copy for the player: `{state, segments, seconds, complete, playable, error, formats}`. `state` is none, fetching, partial (the first seconds only), ready or failed."""
    e = entry(video_id)
    if e is None: return dict(state='none', segments=0, seconds=0.0, complete=False, playable=False, error=None, formats=None)
    if e['state'] == 'failed': p = dict(segments=0, seconds=0.0, complete=False)
    elif e['state'] == 'fetching': p = summary(served_playlist(video_id, e))     # what the player is given: an ended attempt's end and last segment held back (a retry may follow)
    else: p = read_playlist(video_id)
    return dict(state=e['state'], **p, playable=p['segments'] > 0, error=e['error'], formats=e['formats'])


def begin(video_id, now, title=None, channel=None):
    """Mark a fetch as started, with an empty folder (a failed copy's files are cleared first). A title or channel already known is kept when none is given."""
    shutil.rmtree(folder(video_id), ignore_errors=True); os.makedirs(folder(video_id), exist_ok=True)
    with db.connect() as con:
        con.execute("""INSERT INTO copies (video_id, title, channel, state, bytes, started) VALUES (?, ?, ?, 'fetching', 0, ?)
                       ON CONFLICT(video_id) DO UPDATE SET title = COALESCE(excluded.title, copies.title), channel = COALESCE(excluded.channel, copies.channel),
                       state = 'fetching', bytes = 0, started = excluded.started, finished = NULL, error = NULL, formats = NULL""", (video_id, title, channel, now))


def set_formats(video_id, formats):
    with db.connect() as con: con.execute('UPDATE copies SET formats = ? WHERE video_id = ?', (formats, video_id))


def lengths(text):
    """(seconds, segment name) of each segment a playlist's text lists, in order."""
    out, length = [], None
    for ln in (text or '').splitlines():
        ln = ln.strip()
        if ln.startswith('#EXTINF:'): length = float(ln[8:].split(',')[0])
        elif ln and not ln.startswith('#') and length is not None: out.append((length, ln)); length = None
    return out


def covered(video_id):
    """Seconds the playlist lists so far, not counting its last segment (cut short when the fetch is stopped there)."""
    try:
        with open(os.path.join(folder(video_id), PLAYLIST), encoding='utf8') as f: segs = lengths(f.read())
    except OSError: return 0.0
    return sum(n for n, _ in segs[:-1])


def keep_prefix(video_id, until, now, formats):
    """After a fetch stopped on purpose once `until` seconds were listed: keep the segments that reach it, never the last listed one (a
    stop can cut it short, and a later fetch cuts it whole, so they would differ), drop the rest, and mark the copy partial. `formats` is
    {video, audio}: the format ids it was cut from, which the whole fetch must use too. Returns the seconds kept (0: nothing worth keeping,
    and the copy is forgotten)."""
    d = folder(video_id)
    try:
        with open(os.path.join(d, PLAYLIST), encoding='utf8') as f: text = f.read()
    except OSError: text = ''
    segs, kept = lengths(text)[:-1], []
    for length, name in segs:
        if sum(n for n, _ in kept) >= until: break
        kept.append((length, name))
    if not kept or not os.path.isfile(os.path.join(d, 'init.mp4')): forget([video_id]); return 0.0
    head = [ln for ln in text.splitlines() if ln.startswith('#') and not ln.startswith(('#EXTINF', '#EXT-X-ENDLIST'))]
    playlist = '\n'.join(head + [f'#EXTINF:{n:.6f},\n{name}' for n, name in kept]) + '\n'
    names = {name for _, name in kept} | {'init.mp4'}
    for f in os.listdir(d):
        if f not in names: os.remove(os.path.join(d, f))           # later segments, a half-written one, the fetch's log and probe
    for name in (PLAYLIST, PREFIX):
        with open(os.path.join(d, name), 'w', encoding='utf8') as f: f.write(playlist)
    shutil.copyfile(os.path.join(d, 'init.mp4'), os.path.join(d, PREFIX_INIT))
    with open(os.path.join(d, PREFIX_INFO), 'w', encoding='utf8') as f: json.dump(dict(formats, seconds=round(sum(n for n, _ in kept), 3)), f)
    with db.connect() as con:
        con.execute("UPDATE copies SET state = 'partial', bytes = ?, finished = ?, error = NULL WHERE video_id = ?", (folder_bytes(d), now, video_id))
    return round(sum(n for n, _ in kept), 3)


def prefix(video_id):
    """A partial copy's `{video, audio, seconds}` (the format ids it was cut from), or None when the copy has no prefix."""
    try:
        with open(os.path.join(folder(video_id), PREFIX_INFO), encoding='utf8') as f: d = json.load(f)
    except (OSError, ValueError): return None
    return d if isinstance(d, dict) and d.get('video') and d.get('audio') else None


def resume(video_id, now):
    """Mark a partial copy as fetching again, keeping its files: the whole video is fetched into the same folder (see the module's notes)."""
    with db.connect() as con:
        con.execute("UPDATE copies SET state = 'fetching', started = ?, finished = NULL, error = NULL WHERE video_id = ?", (now, video_id))


def drop_prefix(video_id):
    """Forget a copy's prefix files (the whole fetch could not use its formats, or no longer needs them)."""
    for name in (PREFIX, PREFIX_INIT, PREFIX_INFO):
        try: os.remove(os.path.join(folder(video_id), name))
        except OSError: pass


def finish(video_id, now, error=None):
    """Record how a fetch ended. A failed fetch keeps its row (so the player can say why) but not its files."""
    if error: shutil.rmtree(folder(video_id), ignore_errors=True)
    else: drop_prefix(video_id)
    size = 0 if error else folder_bytes(folder(video_id))
    with db.connect() as con:
        con.execute('UPDATE copies SET state = ?, bytes = ?, finished = ?, error = ? WHERE video_id = ?', ('failed' if error else 'ready', size, now, error, video_id))


def pin(video_id, pinned):
    with db.connect() as con: return con.execute('UPDATE copies SET pinned = ? WHERE video_id = ?', (bool(pinned), video_id)).rowcount > 0


def forget(video_ids):
    """Delete the copies (files and rows) of these videos; returns how many bytes that freed."""
    freed = 0
    for vid in video_ids:
        p = folder(vid); freed += folder_bytes(p); shutil.rmtree(p, ignore_errors=True)
        with db.connect() as con: con.execute('DELETE FROM copies WHERE video_id = ?', (vid,))
    return freed


def recover(now):
    """After a restart: a fetch that was running when the server stopped cannot be resumed, so it is marked failed and its files removed."""
    with db.connect() as con: stale = [r[0] for r in con.execute("SELECT video_id FROM copies WHERE state = 'fetching'")]
    for vid in stale:
        if prefix(vid) and back_to_prefix(vid, now): continue          # a whole fetch from a prefix: the prefix is still good
        finish(vid, now, error='The server stopped while this was being fetched; play it again to fetch it again.')
    return stale


def back_to_prefix(video_id, now):
    """Make a copy partial again from its kept prefix (the whole fetch from it stopped): its playlist, and only the files that lists."""
    d = folder(video_id)
    try:
        with open(os.path.join(d, PREFIX), encoding='utf8') as f: text = f.read()
    except OSError: return False
    keep = {name for _, name in lengths(text)} | {'init.mp4', PREFIX, PREFIX_INIT, PREFIX_INFO}
    for f in os.listdir(d):
        if f not in keep: os.remove(os.path.join(d, f))
    shutil.copyfile(os.path.join(d, PREFIX_INIT), os.path.join(d, 'init.mp4'))
    with open(os.path.join(d, PLAYLIST), 'w', encoding='utf8') as f: f.write(text)
    with db.connect() as con:
        con.execute("UPDATE copies SET state = 'partial', bytes = ?, finished = ?, error = NULL WHERE video_id = ?", (folder_bytes(d), now, video_id))
    return True


def record_play(video_id, now):
    with db.connect() as con: con.execute('INSERT INTO plays (video_id, at) VALUES (?, ?)', (video_id, now))


def plays(video_id):
    """How often a video has been played and when last: `{plays, last_played}`."""
    with db.connect() as con: n, last = con.execute('SELECT COUNT(*), MAX(at) FROM plays WHERE video_id = ?', (video_id,)).fetchone()
    return dict(plays=n, last_played=last)


def parse_time(s):
    return datetime.fromisoformat(s) if s else None


def score(play_times, now, half_life_days):
    """Every play counts, and counts half as much for every `half_life_days` since it happened."""
    return sum(0.5 ** (max((now - t).total_seconds(), 0) / 86400 / half_life_days) for t in play_times)


def entries(now):
    """Every cached video with its size (a running fetch's folder is measured), plays, last play, title and score, highest score first."""
    hl = settings.get('half_life_days')
    with db.connect() as con:
        rows = db.rows(con.execute('SELECT * FROM copies'))
        plays = {}
        for vid, at in con.execute('SELECT video_id, at FROM plays'): plays.setdefault(vid, []).append(parse_time(at))
    for r in rows:
        if r['state'] == 'fetching': r['bytes'] = folder_bytes(folder(r['video_id']))
        times = plays.get(r['video_id'], [])
        r.update(title=r['title'] or r['video_id'], plays=len(times), last_played=max(times).isoformat(timespec='seconds') if times else None, score=round(score(times, now, hl), 4), pinned=bool(r['pinned']))
    return sorted(rows, key=lambda r: (-r['score'], r['video_id']))


def protected(e, now, protect_days):
    """Why an entry may not be evicted now, or None."""
    if e['state'] == 'fetching': return 'fetching'
    if e['pinned']: return 'pinned'
    last = parse_time(e['last_played'])
    if last and now - last < RECENT_PLAY: return 'played in the last day'
    fetched = parse_time(e['finished'] or e['started'])
    if e['plays'] == 0 and e['state'] in ('ready', 'partial') and fetched and now - fetched < timedelta(days=protect_days): return 'not played yet'
    return None


def plan(items, limit_bytes, now, protect_days):
    """Which entries to evict: none while the total is at or under 95% of the limit; else failed copies first, then the lowest scores (the
    least recently played first among equals), until the total is under 90%. Protected entries are skipped even if the target is then missed."""
    total = sum(e['bytes'] for e in items)
    if total <= HIGH * limit_bytes: return []
    candidates = [e for e in items if protected(e, now, protect_days) is None]
    candidates.sort(key=lambda e: (e['state'] != 'failed', e['score'], e['last_played'] or '', e['finished'] or e['started'] or ''))
    out = []
    for e in candidates:
        if total < LOW * limit_bytes: break
        out.append(e); total -= e['bytes']
    return out


def usage(now):
    """`{used, limit, high, low, count, by_state, bytes_by_state}` for the Cache screen: how many copies, and how many bytes, are whole (ready), only a start (partial), fetching or failed. Sizes are bytes."""
    items = entries(now); limit = settings.cache_limit_bytes()
    states = ('fetching', 'partial', 'ready', 'failed')
    by_state = {s: sum(1 for e in items if e['state'] == s) for s in states}
    bytes_by_state = {s: sum(e['bytes'] for e in items if e['state'] == s) for s in states}
    return dict(used=sum(e['bytes'] for e in items), limit=limit, high=int(HIGH * limit), low=int(LOW * limit), count=len(items), by_state=by_state, bytes_by_state=bytes_by_state)


def evict(now, dry_run=False):
    """Run eviction; returns `{evicted: [{video_id, title, bytes, score}], freed}`."""
    items = entries(now)
    victims = plan(items, settings.cache_limit_bytes(), now, settings.get('protect_days'))
    gone = [dict(video_id=e['video_id'], title=e['title'], bytes=e['bytes'], score=e['score']) for e in victims]
    freed = sum(e['bytes'] for e in victims) if dry_run else forget([e['video_id'] for e in victims])
    return dict(evicted=gone, freed=freed, dry_run=dry_run)


def utcnow(): return datetime.now(timezone.utc)


def stamp():
    """Now, as the ISO string the database keeps."""
    return utcnow().isoformat(timespec='seconds')
