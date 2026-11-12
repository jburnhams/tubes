"""How much of the YouTube Data API's daily quota Tubes has used, and on what. Google offers no call that says how much of a key's quota is
left (its console shows it, an API does not), so every call youtube.py makes is counted here as it is made: by the Pacific day and hour it
fell in (the quota resets at midnight Pacific time), the endpoint, and the purpose it was made for (a sync, a recheck, adding a channel...).
The Admin > Quota page reads it back (`usage`).

A purpose is set around the work with `purpose('sync')`, as a `with` block or a decorator; the innermost one wins, so the recheck a sync
runs at its end counts as a recheck. The CLI sets the command's name around every command (cli.main), so a command whose functions name no
purpose of their own still counts under it; a call made with none set counts as `other`.

Units: every call Tubes makes (`channels`, `videos`, `playlistItems`, `channelSections`) costs 1, however many parts or ids it asks for;
`search` would cost 100 (COSTS). Google charges a request that it answers with an error too, so those count, and are also counted as
`failed`; one refused because the quota is spent is counted as `refused` as well, and the time of the last one is kept, so the page can say
the key is out until the reset even when other users of the same key spent it. A call that never reached Google (no network) costs nothing.

The limit is the key's daily quota: `YOUTUBE_API_QUOTA` in the environment (where the key itself is), else Google's default of 10,000.
Rows older than KEEP_DAYS are dropped as new days begin. Counting never stops a call: a database that cannot be written to is logged."""
import contextlib, contextvars, datetime, logging, os

from sqlalchemy.exc import IntegrityError

from tubes import db

DEFAULT_LIMIT = 10_000
COSTS = {'search': 100}                     # units per call by endpoint; any other list call is 1
KEEP_DAYS = 90
HISTORY_DAYS = 30                           # how many days `usage` gives by day
REFUSED_KEY = 'youtube_quota_refused'       # meta: when YouTube last answered quotaExceeded
log = logging.getLogger(__name__)
_purpose = contextvars.ContextVar('youtube_purpose', default='other')


def limit():
    """The key's daily quota in units: YOUTUBE_API_QUOTA, else Google's default."""
    try: n = int(os.environ.get('YOUTUBE_API_QUOTA') or DEFAULT_LIMIT)
    except ValueError: return DEFAULT_LIMIT
    return n if n > 0 else DEFAULT_LIMIT


@contextlib.contextmanager
def purpose(name):
    """Count the YouTube calls made inside this block (or decorated function) under `name`."""
    token = _purpose.set(name)
    try: yield
    finally: _purpose.reset(token)


def current(): return _purpose.get()


def _utc(now):
    if now is None: return datetime.datetime.now(datetime.timezone.utc)
    if isinstance(now, str): now = datetime.datetime.fromisoformat(now.replace('Z', '+00:00'))
    return now if now.tzinfo else now.replace(tzinfo=datetime.timezone.utc)


def _nth_sunday(year, month, n):
    first = datetime.date(year, month, 1)
    return first + datetime.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def pacific(now=None):
    """`now` as Pacific wall-clock time (naive), by the US rule: daylight time from 2 am on March's second Sunday to 2 am on November's
    first. Worked out here rather than with zoneinfo, which on Windows needs the tzdata package installed."""
    u = _utc(now).replace(tzinfo=None)
    start = datetime.datetime.combine(_nth_sunday(u.year, 3, 2), datetime.time(10))        # 2 am PST is 10:00 UTC
    end = datetime.datetime.combine(_nth_sunday(u.year, 11, 1), datetime.time(9))          # 2 am PDT is 09:00 UTC
    return u - datetime.timedelta(hours=7 if start <= u < end else 8)


def day(now=None):
    """The quota day `now` falls in, as YYYY-MM-DD (Pacific)."""
    return pacific(now).date().isoformat()


def resets(now=None):
    """When the quota next resets: the coming midnight Pacific, in UTC (ISO 8601)."""
    u, local = _utc(now), pacific(now)
    midnight = datetime.datetime.combine(local.date() + datetime.timedelta(days=1), datetime.time())
    at = u.replace(tzinfo=None) + (midnight - local)
    at += midnight - pacific(at)                 # a clock change before midnight moves it by the hour
    return at.replace(tzinfo=datetime.timezone.utc).isoformat(timespec='seconds')


def cost(endpoint): return COSTS.get(endpoint, 1)


def record(endpoint, failed=False, refused=False, now=None):
    """Count one call that reached YouTube. Never raises: a call that worked is not turned into a failure by its bookkeeping."""
    try: _record(endpoint, failed, refused, now)
    except Exception as e: log.warning('could not count a YouTube call (%s): %s', endpoint, e)


def _record(endpoint, failed, refused, now):
    local = pacific(now); key = dict(day=local.date().isoformat(), hour=local.hour, purpose=current()[:32], endpoint=endpoint[:32])
    add = dict(key, units=cost(endpoint), failed=int(bool(failed)), refused=int(bool(refused)))
    bump = 'UPDATE api_usage SET calls = calls + 1, units = units + :units, failed = failed + :failed, refused = refused + :refused WHERE day = :day AND hour = :hour AND purpose = :purpose AND endpoint = :endpoint'
    for _ in range(2):          # update the hour's row, else insert it; another process may insert it first, then update again
        with db.connect() as con:
            if con.execute(bump, add).rowcount: break
        try:
            with db.connect() as con:
                con.execute('INSERT INTO api_usage (day, hour, purpose, endpoint, calls, units, failed, refused) VALUES (:day, :hour, :purpose, :endpoint, 1, :units, :failed, :refused)', add)
                cutoff = (local.date() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
                con.execute('DELETE FROM api_usage WHERE day < ?', (cutoff,))              # a new row is at most once an hour per purpose: cheap enough
            break
        except IntegrityError: continue
    if refused:
        with db.connect() as con:
            stamp = _utc(now).isoformat(timespec='seconds')
            if not con.execute('UPDATE meta SET value = ? WHERE key = ?', (stamp, REFUSED_KEY)).rowcount: con.execute('INSERT INTO meta (key, value) VALUES (?, ?)', (REFUSED_KEY, stamp))


def usage(now=None, days=HISTORY_DAYS):
    """Today's use against the limit, what it went on (by purpose, by endpoint, by hour), and the last `days` days, newest first."""
    today, lim = day(now), limit()
    first = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days - 1)).isoformat()
    with db.connect() as con:
        rows = db.rows(con.execute('SELECT day, hour, purpose, endpoint, calls, units, failed, refused FROM api_usage WHERE day >= ? ORDER BY day, hour', (first,)))
        refused_at = db.row(con.execute('SELECT value FROM meta WHERE key = ?', (REFUSED_KEY,)))
    refused_at = refused_at and refused_at['value']
    if refused_at and day(refused_at) != today: refused_at = None              # spent yesterday: the reset has given it back

    def total(rs): return dict(calls=sum(r['calls'] for r in rs), units=sum(r['units'] for r in rs), failed=sum(r['failed'] for r in rs), refused=sum(r['refused'] for r in rs))

    def by(rs, field): return sorted(({field: k, **total([r for r in rs if r[field] == k])} for k in {r[field] for r in rs}), key=lambda g: (-g['units'], g[field]))

    now_rows = [r for r in rows if r['day'] == today]; used = sum(r['units'] for r in now_rows)
    hours = {r['hour'] for r in now_rows}
    by_day = []
    for i in range(days):
        d = (datetime.date.fromisoformat(today) - datetime.timedelta(days=i)).isoformat(); rs = [r for r in rows if r['day'] == d]
        by_day.append(dict(day=d, **total(rs), purposes={g['purpose']: g['units'] for g in by(rs, 'purpose')}))
    return dict(configured=bool(os.environ.get('YOUTUBE_API_KEY')), limit=lim, day=today, used=used, remaining=0 if refused_at else max(lim - used, 0),
                resets=resets(now), refused=refused_at, today=dict(total(now_rows), purposes=by(now_rows, 'purpose'), endpoints=by(now_rows, 'endpoint'),
                hours=[dict(hour=h, **total([r for r in now_rows if r['hour'] == h])) for h in sorted(hours)]), days=by_day)
