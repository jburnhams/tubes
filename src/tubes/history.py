"""A viewing history brought in from elsewhere, and the channel suggestions made from it.

Import: a Google Takeout watch history (`YouTube and YouTube Music/history/watch-history.json` or `.html`; Takeout writes one or the other)
is read into `watches` under a `source` name (say, one per account), replacing whatever that source held before, so importing a newer export
again is safe. Only watches are kept: ads ("From Google Ads"), searches, surveys and the like are left out. Takeout writes the HTML in the
account's language; the English wording ("Watched", UK and US dates) is what is read, and a JSON export reads the same in any case.

Or a history is read from another database that keeps one (settings `history_url` and `history_table`): `sync_database` copies a table
or view with the columns account, at (a timestamp, or an ISO string), video_id, title, channel_id and channel_name, one source per account
(replacing it, as an import does), then refreshes. Sources that are not in that table (Takeout imports) are left alone.

Suggestions: `refresh` turns the history into one row per channel (`suggestions`): how many times and how lately it was watched, and a
score that adds up its watches with each one counting half as much every HALF_LIFE_DAYS, so a channel watched a lot years ago and one
watched a lot this month both rank. Then it groups channels by the sittings they were watched in: watches less than SITTING_GAP apart are one
sitting; two channels are linked by how many sittings they share (normalised by how much each was watched, so a channel watched in every
sitting does not pull everything into its group), and Louvain community detection (networkx) finds the groups. Only channels watched at least
GROUP_MIN times are grouped; fewer watches say too little. A group's name is made from its top channels until someone names it; a regrouping
gives each new group the id and name of the old group it shares most channels with, so names survive a new import.

Then YouTube is asked about the channels watched at least LOOKUP_MIN times that it has not been asked about for LOOKUP_DAYS (one unit per 50):
their picture, counts, topics (YouTube's own broad categories, such as Music or Hobby) and whether the channel says it is made for kids. A
channel YouTube no longer has is marked `missing` and left out of the list.

Related channels (related.py) add to this: what the library's followed channels and the history's most watched ones point at, counted up
into `suggested_by`, so a channel never watched can be suggested too (it has no watches, and borrows the group most of its pointers are in).

The list leaves out channels the library follows (following one is accepting it) and those dismissed, unless asked for those. Dismissing is
kept when the history is imported again."""
import collections, datetime, html, itertools, json, math, re

from tubes import cache, db, iplayer, iplayer_suggest, quota, related, settings, youtube

HALF_LIFE_DAYS = 365.0
SITTING_GAP = datetime.timedelta(minutes=30)
GROUP_MIN = 5
LOOKUP_MIN = 2
LOOKUP_DAYS = 30
NAME_FROM = 3                                                                  # channels named in a group's made-up name
LIST_LIMIT = 200
ZONES = {'UTC': 0, 'GMT': 0, 'BST': 1, 'IST': 1, 'WET': 0, 'WEST': 1, 'CET': 1, 'CEST': 2, 'EET': 2, 'EEST': 3, 'EST': -5, 'EDT': -4, 'CST': -6, 'CDT': -5,
         'MST': -7, 'MDT': -6, 'PST': -8, 'PDT': -7, 'AKST': -9, 'AKDT': -8, 'HST': -10, 'AEST': 10, 'AEDT': 11, 'ACST': 9.5, 'ACDT': 10.5, 'AWST': 8, 'NZST': 12, 'NZDT': 13, 'JST': 9}
WHEN_FORMATS = ('%d %b %Y, %H:%M:%S', '%b %d, %Y, %I:%M:%S %p')
VIDEO = re.compile(r'[?&]v=([A-Za-z0-9_-]{11})')
CHANNEL = re.compile(r'/channel/(UC[A-Za-z0-9_-]{22})')
LINK = re.compile(r'<a href="([^"]+)">(.*?)</a>', re.S)


class NotFound(LookupError):
    """No such suggestion, group or source; the message says which."""


class ImportProblem(ValueError):
    """The file is not a watch history that can be read; the message says why."""


def when(text):
    """A Takeout HTML time (`9 Oct 2026, 21:57:37 BST`, `Oct 9, 2026, 9:57:37 PM EDT`) as an ISO time in UTC, or None. A zone it does not know counts as UTC."""
    t = html.unescape(text or '').replace(' ', ' ').replace('\xa0', ' ').replace('Sept ', 'Sep ').strip()
    m = re.match(r'^(.*\S)\s+([A-Z]{2,5}|UTC[+-]\d+(?::\d\d)?|GMT[+-]\d+(?::\d\d)?)$', t)
    stamp, zone = (m.group(1), m.group(2)) if m and m.group(2) not in ('AM', 'PM') else (t, 'UTC')
    for f in WHEN_FORMATS:
        try: local = datetime.datetime.strptime(stamp, f); break
        except ValueError: continue
    else: return None
    off = re.match(r'^(?:UTC|GMT)([+-])(\d+)(?::(\d\d))?$', zone)
    hours = (1 if off.group(1) == '+' else -1) * (int(off.group(2)) + int(off.group(3) or 0) / 60) if off else ZONES.get(zone, 0)
    return (local - datetime.timedelta(hours=hours)).replace(tzinfo=datetime.timezone.utc).isoformat(timespec='seconds')


def _row(at, url, title, channel_url, channel_title):
    v = VIDEO.search(url or '')
    if not v or not at: return None
    c = CHANNEL.search(channel_url or '')
    title = (title or '').strip()
    return dict(at=at, video_id=v.group(1), title=None if not title or title == url else title, channel_id=c.group(1) if c else None, channel_title=(channel_title or '').strip() or None if c else None)


def parse_json(data):
    """Watches from a Takeout `watch-history.json` (a list of activity records)."""
    if not isinstance(data, list): raise ImportProblem('That JSON is not a watch history: Takeout writes a list of watches.')
    out = []
    for e in data:
        if not isinstance(e, dict) or not str(e.get('title', '')).startswith('Watched '): continue
        if any((d or {}).get('name') == 'From Google Ads' for d in e.get('details') or []): continue
        try: at = datetime.datetime.fromisoformat(str(e.get('time')).replace('Z', '+00:00')).astimezone(datetime.timezone.utc).isoformat(timespec='seconds')
        except ValueError: continue
        sub = (e.get('subtitles') or [{}])[0] or {}
        r = _row(at, e.get('titleUrl'), e['title'][len('Watched '):], sub.get('url'), sub.get('name'))
        if r: out.append(r)
    return out


def parse_html(text):
    """Watches from a Takeout `watch-history.html` (one card per activity)."""
    out = []
    for cell in text.split('<div class="outer-cell')[1:]:
        if 'From Google Ads' in cell: continue
        m = re.search(r'mdl-typography--body-1">(.*?)</div>', cell, re.S)
        if not m or not m.group(1).startswith('Watched'): continue
        body = m.group(1); links = LINK.findall(body)
        if not links: continue
        url, title = html.unescape(links[0][0]), html.unescape(links[0][1])
        channel = next(((html.unescape(u), html.unescape(t)) for u, t in links[1:] if '/channel/' in u), (None, None))
        r = _row(when(body.rstrip().removesuffix('<br>').rsplit('<br>', 1)[-1]), url, title, *channel)
        if r: out.append(r)
    return out


def parse(text):
    """Watches from the text of a Takeout watch history, JSON or HTML (told apart by the first character)."""
    t = text.lstrip('﻿ \t\r\n')
    if t.startswith('['):
        try: data = json.loads(t)
        except ValueError as e: raise ImportProblem(f'That file looks like JSON but cannot be read: {e}.') from None
        return parse_json(data)
    if '<div class="outer-cell' not in t: raise ImportProblem('That is not a Google Takeout watch history (watch-history.json or watch-history.html).')
    return parse_html(t)


def import_text(text, source, now=None, lookup=True):
    """Replace what `source` held with the watches in this Takeout file's text, then `refresh`. Returns `{source, watches, first, last, refresh}`."""
    source = (source or '').strip()
    if not source or len(source) > 64: raise ImportProblem('Name the history (up to 64 characters), say after the account it came from.')
    rows = parse(text)
    if not rows: raise ImportProblem('That watch history has no watches in it.')
    _replace(source, rows)
    ats = sorted(r['at'] for r in rows)
    return dict(source=source, watches=len(rows), first=ats[0], last=ats[-1], refresh=refresh(now, lookup=lookup))


def _replace(source, rows):
    with db.connect() as con:
        con.execute('DELETE FROM watches WHERE source = ?', (source,))
        con.executemany('INSERT INTO watches (source, at, video_id, title, channel_id, channel_title) VALUES (:source, :at, :video_id, :title, :channel_id, :channel_title)', [dict(r, source=source) for r in rows])


TABLE = re.compile(r'^[A-Za-z_]\w*(\.[A-Za-z_]\w*)?$')


def _utc(v):
    if isinstance(v, datetime.datetime): t = v if v.tzinfo else v.replace(tzinfo=datetime.timezone.utc)
    else:
        try: t = datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        except ValueError: return None
        t = t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(datetime.timezone.utc).isoformat(timespec='seconds')


def database_configured():
    return bool(settings.get('history_url') and settings.get('history_table'))


def sync_database(url=None, table=None, now=None, lookup=True):
    """Copy the history kept in another database in (see the module's notes). Returns `{sources: {account: watches}, refresh}`."""
    import sqlalchemy
    url, table = url or settings.get('history_url'), table or settings.get('history_table')
    if not url or not table: raise ImportProblem('No history database is set: set history_url and history_table (tubes set).')
    if not TABLE.match(table): raise ImportProblem(f'{table} is not a table name (name or schema.name).')
    engine = sqlalchemy.create_engine(url)
    try:
        with engine.connect() as con:
            got = con.execute(sqlalchemy.text(f'SELECT account, at, video_id, title, channel_id, channel_name FROM {table} WHERE video_id IS NOT NULL')).fetchall()
    except sqlalchemy.exc.SQLAlchemyError as e: raise ImportProblem(f'The history database could not be read: {str(e).splitlines()[0]}') from None
    finally: engine.dispose()
    per = collections.defaultdict(list)
    for account, at, vid, title, cid, cname in got:
        at = _utc(at)
        if at and account: per[str(account)[:64]].append(dict(at=at, video_id=str(vid)[:64], title=title, channel_id=cid or None, channel_title=cname if cid else None))
    for source, rows in per.items(): _replace(source, rows)
    return dict(sources={k: len(v) for k, v in sorted(per.items())}, refresh=refresh(now, lookup=lookup))


def import_file(path, source, now=None, lookup=True):
    with open(path, encoding='utf-8-sig', errors='replace') as f: return import_text(f.read(), source, now, lookup)


def sources():
    """Each imported history: `{source, watches, channels, first, last}`, by name."""
    with db.connect() as con:
        return db.rows(con.execute('SELECT source, COUNT(*) AS watches, COUNT(DISTINCT channel_id) AS channels, MIN(at) AS first, MAX(at) AS last FROM watches GROUP BY source ORDER BY source'))


def remove_source(source, now=None):
    """Forget an imported history and refresh the suggestions without it (YouTube is not asked again)."""
    with db.connect() as con:
        if not con.execute('DELETE FROM watches WHERE source = ?', (source,)).rowcount: raise NotFound(f'There is no history called {source}.')
    return dict(source=source, refresh=refresh(now, lookup=False))


def score(ats, now, half_life=HALF_LIFE_DAYS):
    """Each watch counts 1 when new and half as much every `half_life` days after."""
    t = datetime.datetime.fromisoformat(now)
    return sum(0.5 ** (max(0.0, (t - datetime.datetime.fromisoformat(a)).total_seconds()) / 86400 / half_life) for a in ats)


def sittings(rows):
    """The channels watched in each sitting: rows of (source, at, channel_id), in order, split where the source changes or watches are more than SITTING_GAP apart."""
    out, cur, prev = [], set(), None
    for source, at, cid in rows:
        t = datetime.datetime.fromisoformat(at)
        if prev and (source != prev[0] or t - prev[1] > SITTING_GAP): out.append(cur); cur = set()
        cur.add(cid); prev = (source, t)
    if cur: out.append(cur)
    return out


def communities(sits, counts, minimum=GROUP_MIN):
    """Groups of channels watched in the same sittings (see the module's notes): a list of sets, largest first; channels watched fewer than
    `minimum` times, and those that share no two sittings with another, are in none."""
    import networkx as nx
    keep = {c for c, n in counts.items() if n >= minimum}
    shared = collections.Counter()
    for s in sits:
        for a, b in itertools.combinations(sorted(s & keep), 2): shared[a, b] += 1
    g = nx.Graph()
    g.add_weighted_edges_from((a, b, n / math.sqrt(counts[a] * counts[b])) for (a, b), n in shared.items() if n >= 2)
    if not g.number_of_edges(): return []
    found = nx.community.louvain_communities(g, weight='weight', seed=1)
    return sorted((set(c) for c in found if len(c) >= 2), key=lambda c: (-sum(counts[x] for x in c), min(c)))


def match_groups(found, old, taken_ids=()):
    """Give each new group (largest first) the id of the old group (`{channel: id}`) it shares most channels with, if not given already; a new
    id otherwise. Returns a list of ids in the order of `found`."""
    used, ids, nxt = set(), [], max([0, *old.values(), *taken_ids]) + 1
    for members in found:
        overlap = collections.Counter(old[c] for c in members if c in old)
        best = next((g for g, _ in sorted(overlap.items(), key=lambda x: (-x[1], x[0])) if g not in used), None)
        if best is None: best, nxt = nxt, nxt + 1
        used.add(best); ids.append(best)
    return ids


def refresh(now=None, lookup=True):
    """Remake the suggestions from the history (see the module's notes), then ask YouTube about channels it has not been asked about lately
    (`lookup`; only with a key). Returns `{channels, groups, grouped, looked_up, missing, error}`."""
    now = now or cache.stamp()
    with db.connect() as con:
        rows = [tuple(r) for r in con.execute('SELECT source, at, channel_id, channel_title, video_id FROM watches WHERE channel_id IS NOT NULL ORDER BY source, at, id')]
        old = dict(tuple(r) for r in con.execute('SELECT channel_id, group_id FROM suggestions WHERE group_id IS NOT NULL AND watches > ?', (0,)))   # an unwatched one's group is borrowed (related.py)
        named = {r[0]: r[1] for r in con.execute('SELECT id, name FROM suggestion_groups WHERE named = ?', (True,))}
        all_ids = [r[0] for r in con.execute('SELECT id FROM suggestion_groups')]
    per = collections.defaultdict(list); title, videos = {}, collections.defaultdict(set)
    for _source, at, cid, ctitle, vid in rows:
        per[cid].append(at); videos[cid].add(vid)
        if ctitle: title[cid] = ctitle                                          # the newest name it went by
    counts = {c: len(a) for c, a in per.items()}
    scores = {c: score(a, now) for c, a in per.items()}
    found = communities(sittings((s, a, c) for s, a, c, _t, _v in rows), counts)
    ids = match_groups(found, old, all_ids)
    group_of = {c: gid for gid, members in zip(ids, found) for c in members}
    stats = [dict(channel_id=c, title=title.get(c) or c, watches=counts[c], videos=len(videos[c]), first=min(a), last=max(a), score=round(scores[c], 4), group_id=group_of.get(c)) for c, a in per.items()]
    groups = []
    for gid, members in zip(ids, found):
        top = sorted(members, key=lambda c: (-scores[c], c))[:NAME_FROM]
        groups.append(dict(id=gid, name=named.get(gid) or ', '.join(title.get(c) or c for c in top), named=gid in named))
    with db.connect() as con:
        con.execute('DELETE FROM suggestion_groups')
        con.executemany('INSERT INTO suggestion_groups (id, name, named) VALUES (:id, :name, :named)', groups)
        fields = ('title', 'watches', 'videos', 'first', 'last', 'score', 'group_id')
        con.executemany(f"INSERT INTO suggestions (channel_id, {', '.join(fields)}) VALUES (:channel_id, {', '.join(':' + f for f in fields)}) ON CONFLICT (channel_id) DO UPDATE SET {', '.join(f'{f} = excluded.{f}' for f in fields)}", stats)
        held = {r[0] for r in con.execute('SELECT channel_id FROM suggestions')}
        gone = sorted(held - set(per))
        for i in range(0, len(gone), 500):                                      # one the related channels still point at stays, with no watches
            part, marks = tuple(gone[i:i + 500]), ', '.join('?' * len(gone[i:i + 500]))
            con.execute(f'DELETE FROM suggestions WHERE suggested_by = ? AND pasted IS NULL AND channel_id IN ({marks})', (0,) + part)   # a pasted one stays too
            con.execute(f'UPDATE suggestions SET watches = ?, videos = ?, first = NULL, last = NULL, score = ?, group_id = NULL WHERE channel_id IN ({marks})', (0, 0, 0.0) + part)
        con.execute("INSERT INTO meta (key, value) VALUES ('suggestions_refreshed', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (now,))
    related.aggregate()                                                         # groups moved, so the related channels' borrowed ones do too
    out = dict(channels=len(stats), groups=len(groups), grouped=len(group_of), looked_up=0, missing=0, error=None)
    if lookup and youtube.configured():
        try: out.update(look_up(now))
        except youtube.YoutubeError as e: out['error'] = str(e)
    return out


@quota.purpose('suggestions')
def look_up(now=None, limit=None):
    """Ask YouTube about the channels watched at least LOOKUP_MIN times, or that a related channel points at, that it has not been asked about
    for LOOKUP_DAYS, most watched first (at most `limit`): see the module's notes. Returns `{looked_up, missing}`."""
    now = now or cache.stamp()
    since = (datetime.datetime.fromisoformat(now) - datetime.timedelta(days=LOOKUP_DAYS)).isoformat(timespec='seconds')
    with db.connect() as con:
        sql = 'SELECT channel_id FROM suggestions WHERE platform = ? AND (watches >= ? OR suggested_by > ?) AND (looked_up IS NULL OR looked_up < ?) ORDER BY score DESC, related_score DESC, channel_id' + (' LIMIT ?' if limit else '')
        ids = [r[0] for r in con.execute(sql, ('youtube', LOOKUP_MIN, 0, since, limit) if limit else ('youtube', LOOKUP_MIN, 0, since))]
    if not ids: return dict(looked_up=0, missing=0)
    found = {}
    for i in range(0, len(ids), 50):                                            # saved a call at a time, so running out of quota keeps what came
        part = ids[i:i + 50]
        rows = {r['channel_id']: r for r in (youtube.lookup_row(item) for item in youtube.channels(part))}
        found.update(rows)
        fields = ('title', 'handle', 'thumbnail', 'subscribers', 'total_videos', 'topics', 'made_for_kids')
        with db.connect() as con:
            if rows: con.executemany(f"UPDATE suggestions SET {', '.join(f'{f} = :{f}' for f in fields)}, looked_up = :now, missing = :no WHERE channel_id = :channel_id", [dict(r, now=now, no=False) for r in rows.values()])
            lost = [c for c in part if c not in rows]
            if lost: con.executemany('UPDATE suggestions SET looked_up = :now, missing = :yes WHERE channel_id = :c', [dict(c=c, now=now, yes=True) for c in lost])
    return dict(looked_up=len(ids), missing=len(ids) - len(found))


def _topics(raw): return [t for t in (raw or '').split('|') if t]


def _item(r, by=None):
    r = dict(r); r['topics'] = _topics(r['topics']); r['suggested_from'] = (by or {}).get(r['channel_id'], [])
    r['link'] = iplayer.programme_url(r['channel_id']) if r['platform'] == 'iplayer' else f"https://www.youtube.com/channel/{r['channel_id']}"   # what Follow adds, and where its title goes
    for k in ('missing', 'in_library'): r[k] = bool(r[k])
    r['made_for_kids'] = None if r['made_for_kids'] is None else bool(r['made_for_kids'])
    return r


COLUMNS = """s.channel_id, s.title, s.handle, s.thumbnail, s.watches, s.videos, s.first, s.last, s.score, s.group_id, s.subscribers, s.total_videos,
             s.topics, s.made_for_kids, s.missing, s.dismissed, s.suggested_by, s.related_score, s.platform, s.pasted, c.id IS NOT NULL AS in_library"""
ORDERS = {'watched': 's.score DESC, s.related_score DESC, s.channel_id', 'suggested': 's.suggested_by DESC, s.related_score DESC, s.score DESC, s.channel_id'}
PASTED_ORDER = 's.pasted DESC, s.score DESC, s.related_score DESC, s.channel_id'   # the latest paste first


def _where(group=None, topic=None, kids=None, q=None, dismissed=False, pasted=False):
    where, args = ['s.missing = ?', '(c.id IS NULL OR c.follow = ?)'], [False, False]   # following a channel is accepting it
    where.append('s.dismissed IS NOT NULL' if dismissed else 's.dismissed IS NULL')
    if pasted: where.append('s.pasted IS NOT NULL')
    if group == 'none': where.append('s.group_id IS NULL')
    elif group not in (None, ''):
        try: where.append('s.group_id = ?'); args.append(int(group))
        except ValueError: raise NotFound(f'There is no group {group}.') from None
    if topic: where.append("('|' || COALESCE(s.topics, '') || '|') LIKE ?"); args.append(f'%|{topic}|%')
    if kids is not None: where.append('s.made_for_kids = ?' if kids else '(s.made_for_kids = ? OR s.made_for_kids IS NULL)'); args.append(bool(kids))
    for word in (q or '').split():
        where.append("LOWER(s.title) LIKE LOWER(?) ESCAPE '\\'"); args.append('%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    return ' AND '.join(where), args


def suggestions(group=None, topic=None, kids=None, q=None, dismissed=False, limit=LIST_LIMIT, order='watched', pasted=False):
    """The channels to consider, best score first: `{items, total}` (`total` counts every match, `items` holds the first `limit`). `group` is a
    group's id or 'none' for the ungrouped; `topic` one of YouTube's topics; `kids` True or False for what the channel says of its audience
    (False includes channels that say nothing); `q` words in the title; `dismissed` lists the dismissed ones instead. `order` is 'watched'
    (best score first) or 'suggested' (pointed at by the most of the library's and the history's channels first, related.py); each item's
    `suggested_from` names up to three of those. `pasted` lists only what was pasted in (paste.py), the latest paste first."""
    if order not in ORDERS: raise ValueError(f"Order by {' or '.join(ORDERS)}, not {order}.")
    where, args = _where(group, topic, kids, q, dismissed, pasted)
    with db.connect() as con:
        total = con.execute(f'SELECT COUNT(*) FROM suggestions s LEFT JOIN channels c ON c.id = s.channel_id WHERE {where}', tuple(args)).fetchone()[0]
        rows = db.rows(con.execute(f'SELECT {COLUMNS} FROM suggestions s LEFT JOIN channels c ON c.id = s.channel_id WHERE {where} ORDER BY {PASTED_ORDER if pasted else ORDERS[order]} LIMIT ?', tuple(args) + (limit,)))
    by = related.pointers([r['channel_id'] for r in rows if r['suggested_by'] and r['platform'] == 'youtube'])
    by.update(iplayer_suggest.pointers([r['channel_id'] for r in rows if r['suggested_by'] and r['platform'] == 'iplayer']))
    return dict(items=[_item(r, by) for r in rows], total=total)


def summary():
    """What the Suggestions page shows around its list: the imported histories, the groups and topics among the channels still to consider
    (with how many each holds), how many are open, dismissed and followed, and when the suggestions were last made; `suggested` counts the
    open ones a related channel points at, `unwatched` those with no watches, and `related` says how far asking about them has got (related.status)."""
    with db.connect() as con:
        rows = db.rows(con.execute('''SELECT s.group_id, s.topics, s.made_for_kids, s.dismissed, s.watches, s.suggested_by, s.pasted, c.id IS NOT NULL AND c.follow = ? AS followed
                                      FROM suggestions s LEFT JOIN channels c ON c.id = s.channel_id WHERE s.missing = ?''', (True, False)))
        groups = db.rows(con.execute('SELECT id, name, named FROM suggestion_groups ORDER BY id'))
        refreshed = con.execute("SELECT value FROM meta WHERE key = 'suggestions_refreshed'").fetchone()
    open_ = [r for r in rows if not r['followed'] and not r['dismissed']]
    per_group = collections.Counter(r['group_id'] for r in open_); topics = collections.Counter(t for r in open_ for t in _topics(r['topics']))
    for g in groups: g.update(named=bool(g['named']), channels=per_group.get(g['id'], 0))
    return dict(sources=sources(), groups=sorted(groups, key=lambda g: (-g['channels'], g['id'])), ungrouped=per_group.get(None, 0),
                topics=[dict(name=t, channels=n) for t, n in sorted(topics.items(), key=lambda x: (-x[1], x[0]))],
                kids=sum(1 for r in open_ if r['made_for_kids']), open=len(open_), dismissed=sum(1 for r in rows if r['dismissed'] and not r['followed']),
                followed=sum(1 for r in rows if r['followed']), refreshed=refreshed[0] if refreshed else None, configured=youtube.configured(), database=database_configured(),
                suggested=sum(1 for r in open_ if r['suggested_by']), unwatched=sum(1 for r in open_ if not r['watches']), pasted=sum(1 for r in open_ if r['pasted']), related=related.status())


def suggestion(channel_id):
    with db.connect() as con:
        r = db.row(con.execute(f'SELECT {COLUMNS} FROM suggestions s LEFT JOIN channels c ON c.id = s.channel_id WHERE s.channel_id = ?', (channel_id,)))
    if r is None: raise NotFound(f'There is no suggestion {channel_id}.')
    return _item(r, ((iplayer_suggest if r['platform'] == 'iplayer' else related).pointers([channel_id])) if r['suggested_by'] else None)


def dismiss(channel_id, dismissed=True, now=None):
    """Dismiss a suggestion (it leaves the list, and stays dismissed when the history is imported again), or bring it back."""
    with db.connect() as con:
        if not con.execute('UPDATE suggestions SET dismissed = ? WHERE channel_id = ?', ((now or cache.stamp()) if dismissed else None, channel_id)).rowcount: raise NotFound(f'There is no suggestion {channel_id}.')
    return suggestion(channel_id)


def rename_group(group_id, name):
    """Name a group (an empty name goes back to the one made from its channels at the next refresh)."""
    name = (name or '').strip()
    if len(name) > 80: raise ValueError('A group name is at most 80 characters.')
    with db.connect() as con:
        if not con.execute('UPDATE suggestion_groups SET name = COALESCE(?, name), named = ? WHERE id = ?', (name or None, bool(name), group_id)).rowcount: raise NotFound(f'There is no group {group_id}.')
        return db.row(con.execute('SELECT id, name, named FROM suggestion_groups WHERE id = ?', (group_id,))) | dict(named=bool(name))


def watched_videos(channel_id):
    """The different videos of this channel in the history, most recently watched first."""
    with db.connect() as con:
        return [r[0] for r in con.execute('SELECT video_id FROM watches WHERE channel_id = ? GROUP BY video_id ORDER BY MAX(at) DESC, video_id', (channel_id,))]


TOP = 25


def stats(start=None, end=None, source=None, top=TOP):
    """What was watched between `start` and `end` (ISO times; either may be open), in one source or all: `{watches, videos, channels, first,
    last, by, periods, channels_top, videos_top}`. `periods` counts watches per month (`by` 'month'), or per day when the span is 92 days or
    less (`by` 'day'). Videos that have gone (no channel in the history) count as watches, but are left out of the top channels."""
    def where(t=''):
        parts, args = ['1 = 1'], []
        for sql, v in ((f'{t}at >= ?', start), (f'{t}at < ?', end), (f'{t}source = ?', source)):
            if v: parts.append(sql); args.append(v)
        return ' AND '.join(parts), tuple(args)
    w, args = where()
    with db.connect() as con:
        n = db.row(con.execute(f'SELECT COUNT(*) AS watches, COUNT(DISTINCT video_id) AS videos, COUNT(DISTINCT channel_id) AS channels, MIN(at) AS first, MAX(at) AS last FROM watches WHERE {w}', args))
        span = (datetime.datetime.fromisoformat(n['last']) - datetime.datetime.fromisoformat(n['first'])).days if n['first'] else 0
        by, size = ('day', 10) if span <= 92 else ('month', 7)
        periods = [dict(period=r[0], watches=r[1]) for r in con.execute(f'SELECT SUBSTR(at, 1, {size}) AS p, COUNT(*) FROM watches WHERE {w} GROUP BY SUBSTR(at, 1, {size}) ORDER BY p', args)]
        channels = db.rows(con.execute(f"""SELECT w.channel_id, MAX(w.channel_title) AS title, COUNT(*) AS watches, COUNT(DISTINCT w.video_id) AS videos, MAX(w.at) AS last,
                                           MAX(CASE WHEN c.follow = ? THEN 1 ELSE 0 END) AS followed FROM watches w LEFT JOIN channels c ON c.id = w.channel_id
                                           WHERE {where('w.')[0]} AND w.channel_id IS NOT NULL GROUP BY w.channel_id ORDER BY watches DESC, last DESC, w.channel_id LIMIT ?""", (True, *args, top)))
        videos = db.rows(con.execute(f"""SELECT video_id, MAX(title) AS title, MAX(channel_id) AS channel_id, MAX(channel_title) AS channel, COUNT(*) AS watches, MAX(at) AS last
                                         FROM watches WHERE {w} GROUP BY video_id ORDER BY watches DESC, last DESC, video_id LIMIT ?""", (*args, top)))
    for c in channels: c['followed'] = bool(c['followed'])
    return dict(n, by=by, periods=periods, channels_top=channels, videos_top=videos)


def overview(channel_id, top=10):
    """Everything known of one channel, for the detail panel every admin page opens: `{channel_id, title, thumbnail, handle, library,
    suggestion, group, history}`. `library` is the library's channel (None if not there), `suggestion` its suggestion (None if never in a
    history), `history` its watches: totals, per account, per month over all time, and the videos watched most. NotFound if nothing knows it."""
    from tubes import library
    lib = library.channel(channel_id)
    try: sug = suggestion(channel_id)
    except NotFound: sug = None
    with db.connect() as con:
        n = db.row(con.execute('SELECT COUNT(*) AS watches, COUNT(DISTINCT video_id) AS videos, MIN(at) AS first, MAX(at) AS last, MAX(channel_title) AS title FROM watches WHERE channel_id = ?', (channel_id,)))
        by_source = [dict(source=r[0], watches=r[1]) for r in con.execute('SELECT source, COUNT(*) FROM watches WHERE channel_id = ? GROUP BY source ORDER BY COUNT(*) DESC, source', (channel_id,))]
        periods = [dict(period=r[0], watches=r[1]) for r in con.execute('SELECT SUBSTR(at, 1, 7) AS p, COUNT(*) FROM watches WHERE channel_id = ? GROUP BY SUBSTR(at, 1, 7) ORDER BY p', (channel_id,))]
        videos = db.rows(con.execute('''SELECT w.video_id, MAX(w.title) AS title, COUNT(*) AS watches, MAX(w.at) AS last, MAX(CASE WHEN v.id IS NOT NULL AND v.gone IS NULL THEN 1 ELSE 0 END) AS in_library
                                        FROM watches w LEFT JOIN videos v ON v.id = w.video_id WHERE w.channel_id = ? GROUP BY w.video_id ORDER BY watches DESC, last DESC, w.video_id LIMIT ?''', (channel_id, top)))
        group = db.row(con.execute('SELECT id, name, named FROM suggestion_groups WHERE id = ?', (sug['group_id'],))) if sug and sug['group_id'] is not None else None
    if lib is None and sug is None and not n['watches']: raise NotFound(f'Nothing is known of channel {channel_id}.')
    for v in videos: v['in_library'] = bool(v['in_library'])
    if group: group['named'] = bool(group['named'])
    title = (lib or {}).get('title') or (sug or {}).get('title') or n['title'] or channel_id
    return dict(channel_id=channel_id, title=title, thumbnail=(lib or {}).get('thumbnail') or (sug or {}).get('thumbnail'), handle=(lib or {}).get('handle') or (sug or {}).get('handle'),
                library=lib, suggestion=sug, group=group, configured=youtube.configured(),
                history=dict(watches=n['watches'], videos=n['videos'], first=n['first'], last=n['last'], sources=by_source, periods=periods, videos_top=videos))
