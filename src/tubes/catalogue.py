"""The library, write side: adding channels and videos from YouTube, syncing channels' uploads, removing and restarting them. Ported from the
storage service (src/services/youtube.ts and its routes), which managed the library before Tubes did; library.py reads what this writes.

A channel added here is followed: a sync reads its uploads playlist (youtube.uploads_page) a page of 50 at a time and asks for the details
of the videos not already held, 50 per call. The first sync of a channel walks every page back to its first upload; the page token is saved
after each page, so a sync that stops part way (an error, a restart, the quota) resumes from there next time. Once every page has been read
(`complete`), a sync reads only the newest pages until one brings nothing new, so keeping 20 channels current costs a few calls each. This
differs from storage, which re-read the whole playlist on every sync; the result is the same, at a fraction of the quota.

A video added on its own whose channel is not in the library brings its channel in unfollowed (`follow` false): the channel is named on the
watching side, but a sync leaves it alone. Adding the channel itself follows it.

`Job` runs a sync of several channels in a background thread for the web server, one at a time, and reports how far it has got; the timer
runs `tubes sync` (cli.py), which calls `sync` directly."""
import threading

from tubes import cache, db, library, youtube

CHANNEL_FIELDS = ('title', 'handle', 'thumbnail', 'description', 'published', 'country', 'subscribers', 'total_videos', 'views', 'uploads')
VIDEO_FIELDS = ('channel_id', 'title', 'published', 'duration', 'thumbnail', 'views', 'description', 'likes', 'comments', 'definition')


class NotFound(LookupError):
    """YouTube, or the library, has no such channel or video; the message says which."""


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
    kind, value = youtube.parse(text); now = now or cache.stamp()
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


def remove(channel_id):
    """Remove a channel and its videos (their cached copies stay until evicted); returns how many videos went."""
    with db.connect() as con:
        if not con.execute('SELECT 1 FROM channels WHERE id = ?', (channel_id,)).fetchone(): raise NotFound(f'There is no channel {channel_id} in the library.')
        gone = con.execute('DELETE FROM videos WHERE channel_id = ?', (channel_id,)).rowcount
        con.execute('DELETE FROM channels WHERE id = ?', (channel_id,))
    return dict(channel=channel_id, videos=gone)


def restart(channel_id):
    """Forget a channel's videos and how far its sync got, so the next sync reads it again from the newest upload back (storage's Resync)."""
    with db.connect() as con:
        if not con.execute('SELECT 1 FROM channels WHERE id = ?', (channel_id,)).fetchone(): raise NotFound(f'There is no channel {channel_id} in the library.')
        gone = con.execute('DELETE FROM videos WHERE channel_id = ?', (channel_id,)).rowcount
        con.execute('UPDATE channels SET sync_token = NULL, complete = ?, synced = NULL WHERE id = ?', (False, channel_id))
    return dict(channel=channel_id, videos=gone)


def _store(ids, now):
    """Save the videos among `ids` that the library does not have yet; returns how many were new."""
    if not ids: return 0
    with db.connect() as con:
        have = {r[0] for r in con.execute(f"SELECT id FROM videos WHERE id IN ({', '.join('?' * len(ids))})", tuple(ids))}
    new = [i for i in ids if i not in have]
    rows = [youtube.video_row(item, now) for item in youtube.videos(new)] if new else []
    if rows:
        with db.connect() as con: save_videos(con, rows)
    return len(rows)


def sync_channel(channel_id, now=None, progress=None):
    """Bring one channel up to date (see the module's notes); returns `{channel, title, added, pages, complete}`. `progress(added)` is
    called after each page."""
    now = now or cache.stamp()
    with db.connect() as con: c = db.row(con.execute('SELECT id, sync_token, complete FROM channels WHERE id = ?', (channel_id,)))
    if c is None: raise NotFound(f'There is no channel {channel_id} in the library.')
    row = youtube.channel_row(_channel('channel', channel_id), now)              # fresh counts and the uploads playlist, one unit
    with db.connect() as con: save_channel(con, row)
    if not row['uploads']: raise NotFound(f'YouTube gives no uploads for channel {channel_id}.')
    token, complete, added, pages = c['sync_token'], bool(c['complete']), 0, 0

    def mark(**kw):
        with db.connect() as con: con.execute(f"UPDATE channels SET {', '.join(f'{k} = :{k}' for k in kw)} WHERE id = :id", dict(kw, id=channel_id))

    page, first = None, not complete and token is None                           # the newest pages, until one brings nothing new
    while True:
        ids, after = youtube.uploads_page(row['uploads'], page); pages += 1
        new = _store(ids, now); added += new
        if progress: progress(added)
        if after is None: token, complete = None, True; break                   # read to the first upload: nothing left to backfill
        if first: token = after; mark(sync_token=token)                         # a first sync: this walk is the backfill, saved as it goes
        elif not new: break                                                      # caught up; a backfill (if any) resumes from its token
        page = after
    while not complete and token:                                                # the rest of an unfinished backfill
        ids, token = youtube.uploads_page(row['uploads'], token); pages += 1
        added += _store(ids, now); complete = token is None
        mark(sync_token=token)
        if progress: progress(added)
    mark(sync_token=token, complete=complete, synced=now)
    return dict(channel=channel_id, title=row['title'], added=added, pages=pages, complete=complete)


def followed():
    with db.connect() as con: return [tuple(r) for r in con.execute('SELECT id, title FROM channels WHERE follow = ? ORDER BY LOWER(title), id', (True,))]


def sync(channel_ids=None, now=None, on_channel=None, progress=None):
    """Sync these channels (default: every followed one) in turn; returns `{channels: [...], errors: [...], added, synced}`. A failure on one
    channel is noted and the next goes on, except running out of quota, which stops the rest. `on_channel(id, title)` is called before each.
    After a sync of every followed channel, the library's `synced` time moves on."""
    now = now or cache.stamp(); everything = channel_ids is None
    if everything: todo = followed()
    else:
        with db.connect() as con: titles = dict(tuple(r) for r in con.execute('SELECT id, title FROM channels'))
        todo = [(i, titles.get(i, i)) for i in channel_ids]
    done, errors = [], []
    for cid, title in todo:
        if on_channel: on_channel(cid, title)
        try: done.append(sync_channel(cid, now, progress))
        except (youtube.YoutubeError, NotFound) as e:
            errors.append(dict(channel=cid, title=title, error=str(e)))
            if 'quota' in str(e): break
    if everything and not errors:
        with db.connect() as con: con.execute("INSERT INTO meta (key, value) VALUES ('library_synced', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (now,))
    return dict(channels=done, errors=errors, added=sum(d['added'] for d in done), synced=now)


class Job:
    """One sync at a time in a background thread, for the web server: `start(ids)` (None: every followed channel), `state()` for the page
    that polls it. Starting while one runs is refused (`Busy`)."""

    class Busy(RuntimeError): pass

    def __init__(self):
        self.lock, self.thread = threading.Lock(), None
        self.s = dict(running=False, total=0, done=0, current=None, added=0, errors=[], started=None, finished=None)

    def state(self):
        with self.lock: return dict(self.s, errors=list(self.s['errors']))

    def start(self, channel_ids=None):
        with self.lock:
            if self.s['running']: raise Job.Busy('A sync is already running; it says how far it has got.')
            total = len(channel_ids) if channel_ids is not None else len(followed())
            self.s = dict(running=True, total=total, done=0, current=None, added=0, errors=[], started=cache.stamp(), finished=None)
        self.thread = threading.Thread(target=self._run, args=(channel_ids,), daemon=True, name='tubes-sync'); self.thread.start()
        return self.state()

    def _run(self, channel_ids):
        base = [0]

        def on_channel(cid, title):
            with self.lock:
                if self.s['current']: self.s['done'] += 1
                self.s['current'] = title; base[0] = self.s['added']

        def progress(added):
            with self.lock: self.s['added'] = base[0] + added

        try:
            r = sync(channel_ids, on_channel=on_channel, progress=progress)
            with self.lock: self.s.update(errors=r['errors'], added=r['added'])
        except Exception as e:                                                   # the database went away, say: the page must still stop waiting
            with self.lock: self.s['errors'].append(dict(channel=None, title=None, error=f'The sync stopped: {e}'))
        finally:
            with self.lock: self.s.update(running=False, current=None, done=self.s['total'], finished=cache.stamp())

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)
