"""The library, write side: adding channels and videos from YouTube, syncing channels' uploads, removing and restarting them. Ported from the
storage service (src/services/youtube.ts and its routes), which managed the library before Tubes did; library.py reads what this writes.

A channel added here is followed: a sync reads its uploads playlist (youtube.uploads_page) a page of 50 at a time and asks for the details
of the videos not already held, 50 per call. The first sync of a channel walks every page back to its first upload; the page token is saved
after each page, so a sync that stops part way (an error, a restart, the quota) resumes from there next time. Once every page has been read
(`complete`), a sync reads only the newest pages until one brings nothing new, so keeping 20 channels current costs a few calls each. This
differs from storage, which re-read the whole playlist on every sync; the result is the same, at a fraction of the quota.

A video added on its own whose channel is not in the library brings its channel in unfollowed (`follow` false): the channel is named on the
watching side, but a sync leaves it alone. Adding the channel itself follows it.

Videos YouTube no longer has (deleted, made private, their account closed) are hidden, never deleted: `recheck` asks YouTube about a rolling
slice of the library after each sync of every followed channel (RECHECK videos, one unit per 50, oldest checked first, so the whole library
comes round every few days) and marks the missing ones `gone`; playing one whose fetch yt-dlp says is unavailable marks it at once
(`mark_gone`, from fetcher.py). A later recheck that finds it again, or a fetch that succeeds, clears the mark, so a video that was private
for a while comes back, and a wrong guess from yt-dlp's wording costs no more than a few days hidden. The watching side reports videos it
finds missing (a thumbnail that fails or is YouTube's placeholder, a fetch that fails) through POST /api/videos/check: `report` rechecks
those at once, so a report is never taken on trust, and skips any asked about in the last REPORT_GAP.

A stream that is live now or scheduled (`live`, see youtube.live) is hidden until it ends: a running one cannot be fetched whole and a
scheduled one cannot be played at all, so every recheck after a sync asks about each of them (they are few) before its rolling slice. A
past stream or premiere (`was`) is shown, but a past stream's recording is often cut or taken down soon after, so a past one a page is about
to show is asked about again if it was not in the last LIVE_GAP (`recheck_past`, from the server's video reads), and at once if its
thumbnail fails (`report`); one YouTube no longer has is hidden as `gone` like any other. The mark comes with the video's details, so the
sync sets it as a video is added and the recheck on videos added before it existed (`tubes recheck --all` does the whole library at once,
a unit per 50 videos).

iPlayer programmes and episodes (iplayer.py) are kept the same way, as channels and videos with `platform` 'iplayer'. iPlayer has no quota,
so a sync of a programme reads every page of its episodes (200 a page) and refreshes them all, catching new ones, changed titles and new
expiry dates in one pass; an episode no longer listed is marked `gone`. One whose `expires` has passed is hidden by library.py on its own,
without a sync, unless it is cached: a copy already fetched stays watchable until the cache evicts it. The YouTube recheck and the watching
side's reports leave iPlayer episodes alone.

`Job` runs a sync of several channels in a background thread for the web server, one at a time, and reports how far it has got; the timer
runs `tubes sync` (cli.py), which calls `sync` directly."""
import datetime, json, math, threading

from tubes import cache, db, iplayer, library, youtube

RECHECK = 2500                                                                   # videos per recheck: 50 quota units of the 10,000 a day
LIVE_GAP = datetime.timedelta(days=1)                                          # a past stream is asked about again after this (see the notes)
REPORT_GAP = datetime.timedelta(minutes=10)                                      # a reported video asked about this recently is not asked again (a page of broken thumbnails, reloaded)
CHANNEL_FIELDS = ('platform', 'title', 'handle', 'thumbnail', 'description', 'published', 'country', 'subscribers', 'total_videos', 'views', 'uploads')
VIDEO_FIELDS = ('platform', 'channel_id', 'title', 'published', 'duration', 'thumbnail', 'views', 'description', 'likes', 'comments', 'definition', 'live', 'expires', 'series', 'episode')
ERRORS = (youtube.YoutubeError, iplayer.IplayerError)                          # what a sync notes against a channel and goes on from


class NotFound(LookupError):
    """YouTube or iPlayer, or the library, has no such channel or video; the message says which."""


def _upsert(con, table, fields, rows, keep=()):
    """Insert rows, or update every field of the ones already there; a `keep` field (such as when it was added) is only filled if empty."""
    cols = ('id', *fields, *keep)
    sets = [f'{f} = excluded.{f}' for f in fields] + [f'{k} = COALESCE({table}.{k}, excluded.{k})' for k in keep]
    con.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) ON CONFLICT (id) DO UPDATE SET {', '.join(sets)}", rows)


def save_channel(con, row, follow=None):
    _upsert(con, 'channels', CHANNEL_FIELDS, [row], keep=('added',))
    if follow is not None: con.execute('UPDATE channels SET follow = ? WHERE id = ?', (follow, row['id']))


def save_videos(con, rows):
    _upsert(con, 'videos', VIDEO_FIELDS, rows, keep=('added',))


def _channel(kind, value):
    item = youtube.channel(kind, value)
    if item is None: raise NotFound(f'YouTube has no channel {value}.')
    return item


def add(text, now=None):
    """Add what a person pasted: a channel (followed, and synced by the caller) or one video. Returns `{kind, channel}` or `{kind, video}`;
    adding something already there refreshes it (and follows a channel that was only there for one of its videos)."""
    now = now or cache.stamp()
    bbc = iplayer.parse(text)
    if bbc: return add_iplayer(*bbc, now=now)
    kind, value = youtube.parse(text)
    if kind == 'video':
        items = youtube.videos([value])
        if not items: raise NotFound(f'YouTube has no video {value} (or it is private).')
        row = youtube.video_row(items[0], now)
        with db.connect() as con:
            known = con.execute('SELECT 1 FROM channels WHERE id = ?', (row['channel_id'],)).fetchone()
        if not known:
            ch = youtube.channel('channel', row['channel_id'])
            if ch:
                with db.connect() as con: save_channel(con, youtube.channel_row(ch, now), follow=False)
        with db.connect() as con: save_videos(con, [row])
        return dict(kind='video', video=library.video(row['id']))
    row = youtube.channel_row(_channel(kind, value), now)
    with db.connect() as con: save_channel(con, row, follow=True)
    return dict(kind='channel', channel=library.channel(row['id']))


def add_iplayer(kind, pid, now=None):
    """Add an iPlayer programme or category (followed) or one episode (its programme comes in unfollowed, or for a one-off its category's
    channel or its network), as `add`."""
    now = now or cache.stamp()
    if kind == 'category':
        cat = iplayer.category(pid)
        if cat is None: raise NotFound(f'iPlayer has no category {pid}.')
        row = iplayer.category_row(cat, now)
        with db.connect() as con: save_channel(con, row, follow=True)
        return dict(kind='channel', channel=library.channel(row['id']))
    prog = iplayer.programme(pid) if kind in ('programme', 'pid') else None
    if prog is None and kind == 'programme': raise NotFound(f'iPlayer has no programme {pid}.')
    if prog is not None:
        row = iplayer.channel_row(prog, now)
        with db.connect() as con: save_channel(con, row, follow=True)
        return dict(kind='channel', channel=library.channel(row['id']))
    ep = iplayer.episode(pid)
    if ep is None: raise NotFound(f'iPlayer does not offer {pid} (it may have expired).')
    row = iplayer.video_row(ep, now)
    with db.connect() as con: known = con.execute('SELECT 1 FROM channels WHERE id = ?', (row['channel_id'],)).fetchone()
    if not known:
        tleo = iplayer.programme(row['channel_id']) if row['channel_id'] == ep.get('tleo_id') else None
        cat = iplayer.category(iplayer.category_id(row['channel_id'])) if iplayer.category_id(row['channel_id']) else None
        ch = iplayer.channel_row(tleo, now) if tleo else iplayer.category_row(cat, now) if cat else iplayer.network_row(ep, now)
        row['channel_id'] = ch['id']                                             # its programme is not offered: kept under its network, where it can be found
        with db.connect() as con: save_channel(con, ch, follow=False)
    with db.connect() as con: save_videos(con, [row])
    return dict(kind='video', video=library.video(row['id']))


def add_videos(ids, now=None):
    """Add these videos (say, the ones of a channel watched before, from history.py) without following anything: each one's channel comes in
    unfollowed if the library does not have it. Returns `{added, already, missing}`: new to the library, held already (refreshed), and those
    YouTube no longer has (private or removed)."""
    ids = list(dict.fromkeys(ids)); now = now or cache.stamp()
    if not ids: return dict(added=0, already=0, missing=0)
    rows = [youtube.video_row(item, now) for item in youtube.videos(ids)]
    with db.connect() as con:
        have = {r[0] for r in con.execute(f"SELECT id FROM videos WHERE id IN ({', '.join('?' * len(ids))})", tuple(ids))}
        known = {r[0] for r in con.execute('SELECT id FROM channels')}
    new_channels = sorted({r['channel_id'] for r in rows} - known - {''})
    channels = [youtube.channel_row(item, now) for item in youtube.channels(new_channels, youtube.CHANNEL_PARTS)] if new_channels else []
    with db.connect() as con:
        for c in channels: save_channel(con, c, follow=False)
        save_videos(con, rows)
    return dict(added=sum(1 for r in rows if r['id'] not in have), already=sum(1 for r in rows if r['id'] in have), missing=len(ids) - len(rows))


def remove(channel_id):
    """Remove a channel and its videos (their cached copies stay until evicted); returns how many videos went."""
    with db.connect() as con:
        if not con.execute('SELECT 1 FROM channels WHERE id = ?', (channel_id,)).fetchone(): raise NotFound(f'There is no channel {channel_id} in the library.')
        con.execute('DELETE FROM channels WHERE id = ?', (channel_id,))                 # the channel first: a sync saving videos holds its row (see _store)
        gone = con.execute('DELETE FROM videos WHERE channel_id = ?', (channel_id,)).rowcount
    return dict(channel=channel_id, videos=gone)


def restart(channel_id):
    """Forget a channel's videos and how far its sync got, so the next sync reads it again from the newest upload back (storage's Resync)."""
    with db.connect() as con:
        if not con.execute('SELECT 1 FROM channels WHERE id = ?', (channel_id,)).fetchone(): raise NotFound(f'There is no channel {channel_id} in the library.')
        con.execute('UPDATE channels SET sync_token = NULL, complete = ?, synced = NULL WHERE id = ?', (False, channel_id))
        gone = con.execute('DELETE FROM videos WHERE channel_id = ?', (channel_id,)).rowcount
    return dict(channel=channel_id, videos=gone)


def _gone(channel_id): return NotFound(f'The channel {channel_id} was removed while it synced.')


def _store(channel_id, ids, now):
    """Save the videos among `ids` that the library does not have yet; returns how many were new. The channel's row is touched in the same
    transaction first: on Postgres that holds it, so a removal (which deletes the channel before its videos) either waits for these videos and
    then deletes them, or has already gone and they are not saved. Either way no video outlives its channel."""
    if not ids: return 0
    with db.connect() as con:
        have = {r[0] for r in con.execute(f"SELECT id FROM videos WHERE id IN ({', '.join('?' * len(ids))})", tuple(ids))}
    new = [i for i in ids if i not in have]
    rows = [youtube.video_row(item, now) for item in youtube.videos(new)] if new else []
    if rows:
        with db.connect() as con:
            held = con.execute('UPDATE channels SET id = id WHERE id = ?', (channel_id,)).rowcount
            if held: save_videos(con, rows)
        if not held: raise _gone(channel_id)
    return len(rows)


def sync_channel(channel_id, now=None, progress=None):
    """Bring one channel up to date (see the module's notes); returns `{channel, title, added, pages, complete}`. `progress(added)` is
    called after each page."""
    now = now or cache.stamp()
    with db.connect() as con: c = db.row(con.execute('SELECT id, platform, sync_token, complete FROM channels WHERE id = ?', (channel_id,)))
    if c is None: raise NotFound(f'There is no channel {channel_id} in the library.')
    if c['platform'] == 'iplayer': return sync_programme(channel_id, now, progress)
    row = youtube.channel_row(_channel('channel', channel_id), now)              # fresh counts and the uploads playlist, one unit
    with db.connect() as con:                                                    # an update, never an insert: a channel removed meanwhile stays removed
        held = con.execute(f"UPDATE channels SET {', '.join(f'{f} = :{f}' for f in CHANNEL_FIELDS)} WHERE id = :id", {k: row[k] for k in ('id', *CHANNEL_FIELDS)}).rowcount
    if not held: raise _gone(channel_id)
    if not row['uploads']: raise NotFound(f'YouTube gives no uploads for channel {channel_id}.')
    token, complete, added, pages = c['sync_token'], bool(c['complete']), 0, 0

    def mark(**kw):
        with db.connect() as con: con.execute(f"UPDATE channels SET {', '.join(f'{k} = :{k}' for k in kw)} WHERE id = :id", dict(kw, id=channel_id))

    page, first = None, not complete and token is None                           # the newest pages, until one brings nothing new
    while True:
        ids, after = youtube.uploads_page(row['uploads'], page); pages += 1
        new = _store(channel_id, ids, now); added += new
        if progress: progress(added)
        if after is None: token, complete = None, True; break                   # read to the first upload: nothing left to backfill
        if first: token = after; mark(sync_token=token)                         # a first sync: this walk is the backfill, saved as it goes
        elif not new: break                                                      # caught up; a backfill (if any) resumes from its token
        page = after
    while not complete and token:                                                # the rest of an unfinished backfill
        ids, token = youtube.uploads_page(row['uploads'], token); pages += 1
        added += _store(channel_id, ids, now); complete = token is None
        mark(sync_token=token)
        if progress: progress(added)
    mark(sync_token=token, complete=complete, synced=now)
    return dict(channel=channel_id, title=row['title'], added=added, pages=pages, complete=complete)


def sync_programme(channel_id, now=None, progress=None):
    """Bring one iPlayer programme, or category (its one-offs), up to date (see the module's notes); returns what `sync_channel` does."""
    now = now or cache.stamp()
    cat = iplayer.category_id(channel_id)
    if cat:
        found = iplayer.category(cat)
        if found is None: raise NotFound(f'iPlayer has no category {cat} any more.')
        row, pages = iplayer.category_row(found, now), lambda page: iplayer.category_page(cat, page)          # (one-offs, more, programmes listed)
    else:
        prog = iplayer.programme(channel_id)
        if prog is None: raise NotFound(f'iPlayer has no programme {channel_id} any more.')
        row, pages = iplayer.channel_row(prog, now), lambda page: (*(r := iplayer.episodes_page(channel_id, page)), len(r[0]))
    with db.connect() as con:
        held = con.execute(f"UPDATE channels SET {', '.join(f'{f} = :{f}' for f in CHANNEL_FIELDS)} WHERE id = :id", {k: row[k] for k in ('id', *CHANNEL_FIELDS)}).rowcount
    if not held: raise _gone(channel_id)
    seen, added, page, more, whole = [], 0, 0, True, False
    while more:
        page += 1
        eps, more, listed = pages(page)
        rows = [r for r in (iplayer.video_row(e, now) for e in eps) if cat or r['channel_id'] == channel_id]     # a programme's list holds only its own; never move one elsewhere
        for r in rows: r['channel_id'] = channel_id                             # a category keeps every one-off it lists (a one-off documentary's network would be its own)
        if not listed: break                                                     # an empty page: the list may be cut short, so nothing is marked gone
        whole = not more
        if not rows: continue                                                    # a page of a category's series only: nothing to keep, but the list goes on
        ids = [r['id'] for r in rows]; seen += ids
        with db.connect() as con:
            have = {r[0] for r in con.execute(f"SELECT id FROM videos WHERE id IN ({', '.join('?' * len(ids))})", tuple(ids))}
            held = con.execute('UPDATE channels SET id = id WHERE id = ?', (channel_id,)).rowcount      # holds the channel, as _store does
            if held:
                save_videos(con, rows)
                con.executemany('UPDATE videos SET gone = NULL, checked = :now WHERE id = :id', [dict(now=now, id=i) for i in ids])
        if not held: raise _gone(channel_id)
        added += sum(1 for i in ids if i not in have)
        if progress: progress(added)
    with db.connect() as con:
        old = [r[0] for r in con.execute('SELECT id FROM videos WHERE channel_id = ? AND gone IS NULL', (channel_id,))]
        missing = sorted(set(old) - set(seen)) if whole else []
        if missing: con.executemany('UPDATE videos SET gone = :now, checked = :now WHERE id = :id', [dict(id=i, now=now) for i in missing])
        con.execute('UPDATE channels SET sync_token = NULL, complete = ?, synced = ? WHERE id = ?', (True, now, channel_id))
    return dict(channel=channel_id, title=row['title'], added=added, pages=page, complete=True)


def recheck(limit=None, now=None, ids=None, since=None):
    """Ask YouTube about the `limit` (default RECHECK; 0 for every one) videos checked longest ago, after every stream not over, or about these `ids` (those the library holds, and not checked since `since`): refresh the ones it has (clearing `gone`), mark the rest `gone`. Returns `{checked, gone, back}`:
    how many were asked about, newly hidden, and found again."""
    now = now or cache.stamp(); limit = RECHECK if limit is None else limit
    with db.connect() as con:
        if ids is not None:
            ids = list(dict.fromkeys(ids))
            rows = con.execute(f"SELECT id, gone, checked FROM videos WHERE platform = 'youtube' AND id IN ({', '.join('?' * len(ids))})", tuple(ids)) if ids else []
            was = {r[0]: r[1] for r in rows if not (since and r[2] and r[2] >= since)}
        else:
            was = dict(tuple(r) for r in con.execute("SELECT id, gone FROM videos WHERE platform = 'youtube' AND live IN ('live', 'upcoming')"))   # to find the ones that have ended
            sql = "SELECT id, gone FROM videos WHERE platform = 'youtube' ORDER BY COALESCE(checked, ''), id" + (' LIMIT ?' if limit else '')
            was.update((r[0], r[1]) for r in con.execute(sql, (limit,) if limit else ()))
    if not was: return dict(checked=0, gone=0, back=0)
    found = {r['id']: r for r in (youtube.video_row(item, now) for item in youtube.videos(list(was)))}
    fields = [f for f in VIDEO_FIELDS if f != 'channel_id']                     # a video stays with the channel it was added under
    with db.connect() as con:                                                    # updates only: a video removed meanwhile stays removed
        if found: con.executemany(f"UPDATE videos SET {', '.join(f'{f} = :{f}' for f in fields)}, gone = NULL, checked = :checked WHERE id = :id", [dict({f: r[f] for f in fields}, id=i, checked=now) for i, r in found.items()])
        missing = [i for i in was if i not in found]
        if missing: con.executemany('UPDATE videos SET gone = COALESCE(gone, :now), checked = :now WHERE id = :id', [dict(id=i, now=now) for i in missing])
    return dict(checked=len(was), gone=sum(1 for i in missing if not was[i]), back=sum(1 for i in found if was[i]))


def report(ids, now=None, gap=REPORT_GAP):
    """The watching side found these videos missing: recheck those not asked about in `gap` (see the module's notes). Returns the
    recheck's counts and `hidden`, the ids among them that are hidden now, so the page can drop them at once."""
    now = now or cache.stamp(); ids = list(dict.fromkeys(ids))
    since = (datetime.datetime.fromisoformat(now) - gap).isoformat(timespec='seconds')
    r = recheck(now=now, ids=ids, since=since)
    with db.connect() as con:
        gone = {row[0] for row in con.execute(f"SELECT id FROM videos WHERE gone IS NOT NULL AND id IN ({', '.join('?' * len(ids))})", tuple(ids))} if ids else set()
    return dict(r, hidden=[i for i in ids if i in gone])


def recheck_past(videos, now=None):
    """Of these video rows a page is about to show, ask YouTube again about the past streams not asked about in LIVE_GAP, and return the ids
    it no longer has (now hidden), for the caller to leave out. Without a key, or when YouTube refuses, nothing is asked and the page shows
    them as they are: the next read tries again, and a fetch that fails still hides one."""
    ids = [v['id'] for v in videos if v.get('live') == 'was' and not v.get('gone')]
    if not ids or not youtube.configured(): return set()
    try: return set(report(ids, now, LIVE_GAP)['hidden'])
    except youtube.YoutubeError: return set()


def mark_gone(video_id, now=None):
    """Hide a video that playing found unavailable, until a recheck or a fetch finds it again."""
    with db.connect() as con: con.execute('UPDATE videos SET gone = COALESCE(gone, ?) WHERE id = ?', (now or cache.stamp(), video_id))


def mark_found(video_id):
    with db.connect() as con: con.execute('UPDATE videos SET gone = NULL WHERE id = ? AND gone IS NOT NULL', (video_id,))


class FilterError(ValueError):
    """Raised when a filter for what the watching side shows cannot be used; the message says why, for the person who set it."""


def save_filters(changes):
    """Merge `changes` into which videos the watching side shows (library.filters: `min_seconds`, `max_seconds`, None for no limit, and
    `streams`, 'current' or 'all'), after checking every value (nothing is saved if one is wrong); returns the filters now in force."""
    f = library.filters()
    for k, v in changes.items():
        if k not in library.FILTERS: raise FilterError(f'There is no filter called {k}.')
        if k == 'streams':
            if v not in library.STREAMS: raise FilterError(f'streams must be one of {", ".join(library.STREAMS)}.')
        elif v is not None:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0: raise FilterError('A length must be a number of seconds, 0 or more.')   # 1e309 parses as infinity, which JSON cannot carry back
            v = int(v) if float(v).is_integer() else float(v)
        f[k] = v
    if f['min_seconds'] is not None and f['max_seconds'] is not None and f['min_seconds'] > f['max_seconds']:
        raise FilterError('The shortest length must not be longer than the longest.')
    with db.connect() as con:
        con.execute("INSERT INTO meta (key, value) VALUES ('shown', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (json.dumps(f),))
    return f


def needs_youtube(channel_ids=None):
    """Whether a sync of these channels (default: every followed one) asks YouTube, so needs its key: iPlayer programmes sync without one."""
    with db.connect() as con:
        if channel_ids is None: rows = con.execute("SELECT 1 FROM channels WHERE follow = ? AND platform = 'youtube'", (True,)).fetchall()
        else:
            ids = list(channel_ids)
            if not ids: return False
            known = {r[0]: r[1] for r in con.execute(f"SELECT id, platform FROM channels WHERE id IN ({', '.join('?' * len(ids))})", tuple(ids))}
            return any(known.get(i, 'youtube') == 'youtube' for i in ids)          # one the library does not know fails as YouTube's would
    return bool(rows)


def followed():
    with db.connect() as con: return [tuple(r) for r in con.execute('SELECT id, title FROM channels WHERE follow = ? ORDER BY LOWER(title), id', (True,))]


def sync(channel_ids=None, now=None, on_channel=None, progress=None):
    """Sync these channels (default: every followed one) in turn; returns `{channels: [...], errors: [...], added, synced}`. A failure on one
    channel is noted (with the videos it had added before it failed, which are kept and counted) and the next goes on, except running out of
    quota, which stops the rest. `on_channel(id, title)` is called before each. A sync of every followed channel that did not run out of quota
    ends with a `recheck` (its result is `recheck`, or None).
    After a sync of every followed channel, the library's `synced` time moves on."""
    now = now or cache.stamp(); everything = channel_ids is None
    if everything: todo = followed()
    else:
        with db.connect() as con: titles = dict(tuple(r) for r in con.execute('SELECT id, title FROM channels'))
        todo = [(i, titles.get(i, i)) for i in channel_ids]
    done, errors = [], []
    for cid, title in todo:
        if on_channel: on_channel(cid, title)
        so_far = [0]

        def counted(added, so_far=so_far):
            so_far[0] = added
            if progress: progress(added)
        try: done.append(sync_channel(cid, now, counted))
        except (*ERRORS, NotFound) as e:
            errors.append(dict(channel=cid, title=title, error=str(e), added=so_far[0]))
            if 'quota' in str(e): break
    if everything and not errors:
        with db.connect() as con: con.execute("INSERT INTO meta (key, value) VALUES ('library_synced', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (now,))
    checked = None
    if everything and not any('quota' in e['error'] for e in errors):
        try: checked = recheck(now=now)
        except youtube.YoutubeError as e: errors.append(dict(channel=None, title='The recheck for videos gone from YouTube', error=str(e), added=0))   # named: not one that stopped the sync
    return dict(channels=done, errors=errors, added=sum(d['added'] for d in done + errors), synced=now, recheck=checked)


class Job:
    """One sync at a time in a background thread, for the web server: `start(ids)` (None: every followed channel), `state()` for the page
    that polls it. Starting while one runs is refused (`Busy`); `follow_up(ids)` instead adds channels to the running sync, which reads them
    after the ones it has (a channel added or started again while a sync runs, so following several in a row fetches each)."""

    class Busy(RuntimeError): pass

    def __init__(self):
        self.lock, self.thread, self.queued = threading.Lock(), None, []
        self.s = dict(running=False, total=0, done=0, current=None, added=0, gone=0, errors=[], started=None, finished=None)

    def state(self):
        with self.lock: return dict(self.s, errors=list(self.s['errors']))

    def start(self, channel_ids=None):
        with self.lock:
            if self.s['running']: raise Job.Busy('A sync is already running; it says how far it has got.')
            total = len(channel_ids) if channel_ids is not None else len(followed())
            self.s = dict(running=True, total=total, done=0, current=None, added=0, gone=0, errors=[], started=cache.stamp(), finished=None)
        self.thread = threading.Thread(target=self._run, args=(channel_ids,), daemon=True, name='tubes-sync'); self.thread.start()
        return self.state()

    def follow_up(self, channel_ids):
        """Sync these channels after the running sync's own, or start a sync of them if none runs."""
        with self.lock:
            if self.s['running']:
                new = [c for c in channel_ids if c not in self.queued]
                self.queued += new; self.s['total'] += len(new)
                return dict(self.s, errors=list(self.s['errors']))
        return self.start(list(channel_ids))

    def _run(self, channel_ids):
        base = [0]

        def on_channel(cid, title):
            with self.lock:
                if self.s['current']: self.s['done'] += 1
                self.s['current'] = title; base[0] = self.s['added']

        def progress(added):
            with self.lock: self.s['added'] = base[0] + added

        try:
            while True:
                with self.lock: before = self.s['added']
                r = sync(channel_ids, on_channel=on_channel, progress=progress)
                with self.lock:
                    self.s.update(errors=self.s['errors'] + r['errors'], added=before + r['added'], gone=self.s['gone'] + (r['recheck'] or {}).get('gone', 0))
                    channel_ids, self.queued = self.queued, []
                if not channel_ids: break
        except Exception as e:                                                   # the database went away, say: the page must still stop waiting
            with self.lock: self.s['errors'].append(dict(channel=None, title=None, error=f'The sync stopped: {e}'))
        finally:
            with self.lock: self.queued = []; self.s.update(running=False, current=None, done=self.s['total'], finished=cache.stamp())

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)
