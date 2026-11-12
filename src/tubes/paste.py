"""A list someone pastes into the Suggestions page (links, @handles, ids or plain names, one a line), turned into suggestions to follow.

Each line is read as the library's Add reads it (youtube.parse, iplayer.parse): a YouTube channel or video link, an id or an @handle names
its channel (a video, its channel); an iPlayer programme link names the programme, an episode link the programme it belongs to, and a category
link (or a film's link: a one-off kept under Films, iplayer.FILED_UNDER) the category, followed as a channel of its one-offs; another
one-off has nothing to follow, so it is a problem, not a suggestion. A YouTube playlist link (or a watch link played from one) names the
channels of its videos, at most PLAYLIST_VIDEOS of them, those with the most videos in it first. Anything else is a name, looked up on both: iPlayer's search (programmes whose title is
the name, ignoring case and punctuation; its search is fuzzy, so its first result is not trusted) and YouTube (the name as an @handle first,
one quota unit; a search only when that misses, 100 units, so at most NAME_SEARCHES names a paste are searched). A name both have is
suggested from both, and the one not wanted is dismissed.

What is found goes into `suggestions` (platform, title, picture, `pasted` now), so the page lists it with the rest, and a channel pasted
again that had been dismissed comes back. One already followed is said, not suggested. Nothing is followed here: that is the page's Follow."""
import datetime, re

from tubes import cache, db, iplayer, quota, youtube

MAX_LINES = 100
NAME_SEARCHES = 20
PLAYLIST_VIDEOS = 200                                                        # 4 pages of the playlist and 4 calls for its videos: about a dozen quota units with the channels
BULLET = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s+')


def lines(text):
    """The entries in what was pasted: one a line (bullets and numbering taken off; several links on one line are several entries), blanks
    and repeats left out, at most MAX_LINES."""
    out = []
    for raw in (text or '').splitlines():
        line = BULLET.sub('', raw).strip().strip(',;')
        if not line: continue
        words = line.split()
        parts = words if len(words) > 1 and all('://' in w or w.startswith(('www.', '@')) for w in words) else [line]
        for p in parts:
            if p not in out: out.append(p)
    return out[:MAX_LINES]


def _same(a, b):
    squash = lambda t: re.sub(r'[^0-9a-z]+', '', (t or '').lower())
    return squash(a) == squash(b) and squash(a) != ''


def _youtube(item):
    row = youtube.lookup_row(item)
    return dict(platform='youtube', channel_id=row['channel_id'], title=row['title'], handle=row['handle'], thumbnail=row['thumbnail'], subscribers=row['subscribers'],
                total_videos=row['total_videos'], topics=row['topics'], made_for_kids=row['made_for_kids'])


def _iplayer(prog):
    row = iplayer.channel_row(prog, None)
    return dict(platform='iplayer', channel_id=row['id'], title=row['title'], handle=None, thumbnail=row['thumbnail'], total_videos=row['total_videos'])


def _category(cat):
    row = iplayer.category_row(cat, None)
    return dict(platform='iplayer', channel_id=row['id'], title=row['title'], handle=None, thumbnail=None, total_videos=None)


def _youtube_channel(kind, value):
    """A Data API channel resource (with the parts suggestions keep) for an id, a handle or a video's id; None when YouTube has none."""
    if kind == 'video':
        items = youtube.videos([value])
        if not items: return None
        kind, value = 'channel', (items[0].get('snippet') or {}).get('channelId')
    items = youtube.call('channels', part=youtube.LOOKUP_PARTS, **({'id': value} if kind == 'channel' else {'forHandle': value})).get('items') or []
    return items[0] if items else None


def _playlist(pid):
    """The channels of a playlist's videos (the first PLAYLIST_VIDEOS), most videos first, then by where each first comes in it."""
    ids, token = [], None
    try:
        while len(ids) < PLAYLIST_VIDEOS:
            page, token = youtube.uploads_page(pid, token)
            ids += page
            if not token: break
    except youtube.YoutubeError as e:
        if e.status == 404: return [], 'YouTube has no such playlist, or it is private.'
        raise
    owners = [(v.get('snippet') or {}).get('channelId') for v in youtube.videos(ids[:PLAYLIST_VIDEOS])]   # private and removed videos are left out
    counts = {}
    for c in owners:
        if c: counts[c] = counts.get(c, 0) + 1
    if not counts: return [], 'That playlist has no videos YouTube still offers.'
    order = sorted(counts, key=lambda c: -counts[c])                           # stable: ties keep the playlist's order
    held = {i['id']: i for i in youtube.channels(order)}
    return [_youtube(held[c]) for c in order if c in held], None


def resolve(text, searches):
    """What one entry names: `([found], problem or None)`. `searches` is a one-item list counting the YouTube searches left (shared over a paste)."""
    try: bbc = iplayer.parse(text)
    except ValueError as e: return [], str(e)
    if bbc:
        kind, pid = bbc
        if kind == 'category':
            cat = iplayer.category(pid)
            return ([_category(cat)], None) if cat else ([], 'iPlayer has no such category.')
        prog = iplayer.programme(pid) if kind in ('programme', 'pid') else None
        if prog: return [_iplayer(prog)], None
        if kind == 'programme': return [], 'iPlayer has no such programme.'
        ep = iplayer.episode(pid)
        if ep is None: return [], 'iPlayer does not offer that episode (it may have expired).'
        tleo = ep.get('tleo_id')
        prog = iplayer.programme(tleo) if tleo and tleo != pid else None
        if prog is None:
            cat = iplayer.category_id(iplayer.channel_of(ep))
            found = iplayer.category(cat) if cat else None
            if found: return [_category(found)], None                         # a film: following Films brings it, and every other film
            return [], 'That is a one-off with no programme or category to follow; add it in Library instead.'
        return [_iplayer(prog)], None
    playlist = youtube.playlist_id(text)
    if playlist:
        if not youtube.configured(): return [], 'YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.'
        return _playlist(playlist)
    link = '://' in text or text.startswith(('www.', 'youtube.com', 'youtu.be', 'm.youtube.com', '@')) or youtube.CHANNEL_ID.match(text)
    if link:
        try: kind, value = youtube.parse(text)
        except ValueError as e: return [], str(e)
        if not youtube.configured(): return [], 'YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.'
        item = _youtube_channel(kind, value)
        return ([_youtube(item)], None) if item else ([], 'YouTube has no such channel or video.')
    found, problems = [], []
    try: found += [_iplayer(p) for p in (iplayer.programme(x['id']) for x in iplayer.search(text) if x['kind'] == 'programme' and _same(x['title'], text)) if p]
    except iplayer.IplayerError as e: problems.append(str(e))
    if youtube.configured():
        try:
            item = _youtube_channel('handle', '@' + re.sub(r'[^0-9A-Za-z_.-]+', '', text))
            if not (item and _same((item.get('snippet') or {}).get('title'), text)):
                item = None
                if searches[0] > 0:
                    searches[0] -= 1
                    ids = youtube.search_channels(text)
                    item = _youtube_channel('channel', ids[0]) if ids else None
            if item: found.append(_youtube(item))
        except (youtube.YoutubeError, ValueError) as e: problems.append(str(e))
    if found: return found, None
    return [], problems[0] if problems else 'Neither YouTube nor iPlayer has a channel or programme by that name.'


FIELDS = ('platform', 'title', 'handle', 'thumbnail', 'subscribers', 'total_videos', 'topics', 'made_for_kids')


@quota.purpose('paste')
def paste(text, now=None):
    """Read a pasted list (see the module's notes) into the suggestions. Returns `{found: [{input, platform, channel_id, title}], already:
    [{input, title}], problems: [{input, error}]}`: `found` are now suggested (pasted now, and no longer dismissed), `already` are followed."""
    now = now or cache.stamp()
    entries = lines(text)
    if not entries: raise ValueError('Paste at least one link, @handle or name, one a line.')
    searches, out = [NAME_SEARCHES], dict(found=[], already=[], problems=[])
    with db.connect() as con: followed = {r[0]: r[1] for r in con.execute('SELECT id, title FROM channels WHERE follow = ?', (True,))}
    rows = {}
    for entry in entries:
        try: found, problem = resolve(entry, searches)
        except (youtube.YoutubeError, iplayer.IplayerError) as e: found, problem = [], str(e)
        if problem: out['problems'].append(dict(input=entry, error=problem))
        for f in found:
            if f['channel_id'] in followed: out['already'].append(dict(input=entry, title=followed[f['channel_id']])); continue
            if f['channel_id'] not in rows: out['found'].append(dict(input=entry, platform=f['platform'], channel_id=f['channel_id'], title=f['title']))
            rows[f['channel_id']] = f
    with db.connect() as con:
        held = {r[0] for r in con.execute('SELECT channel_id FROM suggestions')}
        start = datetime.datetime.fromisoformat(now)
        for i, (cid, f) in enumerate(rows.items()):                             # a second apart, so latest-first keeps the paste's order on any engine
            vals = {k: f.get(k) for k in FIELDS} | dict(c=cid, now=(start - datetime.timedelta(seconds=i)).isoformat(timespec='seconds'))
            if cid in held:
                con.execute(f"UPDATE suggestions SET {', '.join(f'{k} = COALESCE(:{k}, {k})' for k in FIELDS)}, pasted = :now, dismissed = NULL, missing = :no WHERE channel_id = :c", vals | dict(no=False))
            else:
                con.execute(f"INSERT INTO suggestions (channel_id, {', '.join(FIELDS)}, pasted, looked_up) VALUES (:c, {', '.join(':' + k for k in FIELDS)}, :now, :looked)",
                            vals | dict(looked=vals['now'] if f['platform'] == 'youtube' else None))
    return out
