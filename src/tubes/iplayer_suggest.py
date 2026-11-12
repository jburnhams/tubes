"""iPlayer programmes to suggest, found by what they are like: the iPlayer counterpart of related.py, which YouTube's watch pages feed.

iPlayer says nothing about which programmes are alike (ibl has no recommendations; an episode page's "related" block lists only the same
programme's episodes; measured 2026-11-12), but its catalogue describes every programme well: fine categories (`documentaries-history`,
`drama-crime`), a genre label (`Nature`), the network and three synopses. So programmes are compared by those:

- The catalogue: `refresh_catalogue` reads iPlayer's A to Z (27 letters, 200 programmes a page: about 3,800 programmes in some 30 calls and
  20 s) into `bbc_programmes`, at most once every CATALOGUE_HOURS, and drops what it no longer lists (only after reading every page).
- Each programme becomes a weighted bag of features: its categories (a fine one counts more than its top-level one), its label, its network
  (a little) and the words of its title and synopsis, each feature weighted by how rare it is across the catalogue (TF-IDF), so a shared
  `drama-crime` says more than a shared `drama-and-soaps`. Two programmes are as alike as their bags are (cosine, 0-1).
- What you like: every followed programme (weight 1) and every programme an episode of which was played here (more for more plays), the
  sources. And, so that suggestions come before much is followed here, the YouTube watch history's topics (History, Food, Music ...), mapped
  onto iPlayer's categories (TOPIC_CATEGORIES) and weighted by how much each was watched: one more source, `youtube`.
- A programme not followed scores by the source it is most like, plus a little for each other close one; LIMIT of those above MIN_SCORE go
  into `suggestions`, taken in turn from each source's best (`spread`), so every followed programme gets its share (platform 'iplayer', `related_score` the score, `suggested_by` how many sources it is close to), with the sources it is
  most like in `bbc_similar`, which the page shows as "Like A and B". Children's programmes are marked made for kids, so the page's filter
  applies. A suggestion no longer found is removed unless it was pasted, dismissed or watched. Category channels (`iplayer-films`) are
  followed for their one-offs, so they are not sources, and one-offs are not suggested here (Films covers them)."""
import collections, datetime, math, re

from tubes import cache, db, iplayer

LETTERS = [*'abcdefghijklmnopqrstuvwxyz', '0-9']
CATALOGUE_HOURS = 20
LIMIT = 60
MIN_SCORE = 0.12
CLOSE = 0.2                     # a source this alike counts towards `suggested_by`
TOP_SOURCES = 3
OTHERS = 0.25                   # what each further close source adds, times its likeness
BRIDGE = 0.6                    # the YouTube history's weight, against a followed programme's 1
WEIGHTS = dict(category=1.0, fine=2.0, label=1.5, network=0.5, word=1.0)
KIDS = ('cbeebies', 'cbbc', 'childrens')
STOP = set('the and for with from that this they their them into about after over who what when where which while will your you are was were has have had not but '
           'his her its our out all new one two three more most series episode episodes programme show shows how why can its it\'s also than then there these those '
           'take takes look looks find finds first last part year years time way back own being been just some each other'.split())
TOPIC_CATEGORIES = {      # YouTube's topic names (Wikipedia articles) to iPlayer's categories; its catch-alls (Hobby, Television program) say too little to map
    'History': ('history', 'documentaries-history'), 'Knowledge': ('documentaries',), 'Society': ('documentaries',), 'Food': ('food',),
    'Music': ('music',), 'Sport': ('sport',), 'Humour': ('comedy',), 'Lifestyle': ('lifestyle',), 'Politics': ('news', 'politics'),
    'Film': ('films',), 'Entertainment': ('entertainment',), 'Technology': ('science-and-nature',),
    'Health': ('lifestyle',), 'Tourism': ('lifestyle',), 'Physical fitness': ('sport',), 'Military': ('history', 'documentaries-history'), 'Religion': ('documentaries',),
    'Performing arts': ('arts',), 'Visual arts': ('arts',), 'Fashion': ('lifestyle',), 'Nature': ('science-and-nature',), 'Science': ('science-and-nature',),
    'Biology': ('science-and-nature',), 'Animals': ('science-and-nature',), 'Pet': ('science-and-nature',), 'Business': ('documentaries',),
}


def _ago(now, hours): return (datetime.datetime.fromisoformat(now) - datetime.timedelta(hours=hours)).isoformat(timespec='seconds')


def _row(p, now):
    syn, im, mb = p.get('synopses') or {}, p.get('images') or {}, p.get('master_brand') or {}
    return dict(id=p['id'], title=p.get('title') or p['id'], synopsis=syn.get('medium') or syn.get('small') or syn.get('large'),
                categories='|'.join(p.get('categories') or []) or None, label=(p.get('labels') or {}).get('category'), network=mb.get('id'),
                kind=p.get('tleo_type'), episodes=p.get('count'), thumbnail=iplayer.image(im.get('standard') or im.get('promotional'), iplayer.AVATAR), now=now)


def refresh_catalogue(now=None, force=False):
    """Read iPlayer's A to Z into `bbc_programmes` unless it was read in the last CATALOGUE_HOURS (or `force`). Returns `{read, new, dropped}`,
    or `{skipped: when}`. An error part way keeps what was there."""
    now = now or cache.stamp()
    with db.connect() as con: last = con.execute("SELECT value FROM meta WHERE key = 'bbc_catalogue'").fetchone()
    if last and not force and last[0] >= _ago(now, CATALOGUE_HOURS): return dict(skipped=last[0])
    found = {}
    for letter in LETTERS:
        page, more = 0, True
        while more:
            page += 1
            items, more = iplayer.atoz_page(letter, page)
            for p in items: found.setdefault(p['id'], _row(p, now))
    with db.connect() as con:
        held = {r[0] for r in con.execute('SELECT id FROM bbc_programmes')}
        con.executemany('''INSERT INTO bbc_programmes (id, title, synopsis, categories, label, network, kind, episodes, thumbnail, seen, refreshed)
                           VALUES (:id, :title, :synopsis, :categories, :label, :network, :kind, :episodes, :thumbnail, :now, :now)
                           ON CONFLICT (id) DO UPDATE SET title = excluded.title, synopsis = excluded.synopsis, categories = excluded.categories, label = excluded.label,
                           network = excluded.network, kind = excluded.kind, episodes = excluded.episodes, thumbnail = excluded.thumbnail, refreshed = excluded.refreshed''', list(found.values()))
        gone = sorted(held - set(found))
        if gone: con.executemany('DELETE FROM bbc_programmes WHERE id = :id', [dict(id=i) for i in gone])
        con.execute("INSERT INTO meta (key, value) VALUES ('bbc_catalogue', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (now,))
    return dict(read=len(found), new=len(set(found) - held), dropped=len(gone))


def words(text):
    return [w for w in re.findall(r"[a-z][a-z']+", (text or '').lower()) if len(w) > 2 and w not in STOP]


def fine(cats):
    """The categories that narrow another one listed (`documentaries-history` under `documentaries`); the rest are top-level (even with a
    hyphen, as `science-and-nature` is)."""
    return {c for c in cats if any(c != o and c.startswith(o + '-') for o in cats)}


def features(p):
    """A programme's raw features, `{feature: weight}` (before rarity is weighed)."""
    out = collections.Counter()
    cats = [c for c in (p['categories'] or '').split('|') if c]
    narrow = fine(cats)
    for c in cats: out['c:' + c] += WEIGHTS['fine'] if c in narrow else WEIGHTS['category']
    if p['label']: out['l:' + p['label'].lower()] += WEIGHTS['label']
    if p['network']: out['n:' + p['network']] += WEIGHTS['network']
    ws = words(f"{p['title']} {p['synopsis'] or ''}")
    for w in ws: out['w:' + w] += WEIGHTS['word'] / math.sqrt(len(ws))
    return out


def vectors(programmes):
    """`{id: unit vector}` over the catalogue, every feature weighted by how rare it is (TF-IDF)."""
    raw = {p['id']: features(p) for p in programmes}
    df = collections.Counter(f for v in raw.values() for f in v)
    n = len(raw) or 1
    out = {}
    for pid, v in raw.items():
        w = {f: x * math.log(1 + n / df[f]) for f, x in v.items()}
        norm = math.sqrt(sum(x * x for x in w.values())) or 1.0
        out[pid] = {f: x / norm for f, x in w.items()}
    return out


def cosine(a, b):
    if len(a) > len(b): a, b = b, a
    return sum(x * b.get(f, 0.0) for f, x in a.items())


def sources():
    """What suggestions are made from: `{programme id: weight}` (followed programmes 1, played ones more for more plays), and the YouTube
    history's topics as `{iPlayer category: weight}`."""
    with db.connect() as con:
        followed = [r[0] for r in con.execute('SELECT id FROM channels WHERE platform = ? AND follow = ?', ('iplayer', True)) if not iplayer.category_id(r[0])]
        plays = con.execute('''SELECT v.channel_id, COUNT(*) FROM plays p JOIN videos v ON v.id = p.video_id WHERE v.platform = ? GROUP BY v.channel_id''', ('iplayer',)).fetchall()
        topics = con.execute("SELECT topics, score FROM suggestions WHERE platform = 'youtube' AND watches > ? AND topics IS NOT NULL", (0,)).fetchall()
    weight = collections.Counter({p: 1.0 for p in followed})
    for cid, n in plays:
        if not iplayer.category_id(cid): weight[cid] = min(2.0, weight[cid] + 0.5 + 0.25 * math.log2(n))
    bridge = collections.Counter()
    for raw, score in topics:
        for t in raw.split('|'):
            for c in TOPIC_CATEGORIES.get(t, ()): bridge[c] += score or 0.0
    return dict(weight), dict(bridge)


def kids(p): return any(c.startswith(KIDS) for c in (p['categories'] or '').split('|'))


def score(now=None):
    """Score the catalogue against the sources into suggestions (see the module's notes). No network. Returns `{sources, suggested, added}`."""
    now = now or cache.stamp()
    with db.connect() as con:
        programmes = db.rows(con.execute('SELECT id, title, synopsis, categories, label, network, kind, episodes, thumbnail FROM bbc_programmes'))
        followed = {r[0] for r in con.execute('SELECT id FROM channels WHERE follow = ?', (True,))}
    by_id = {p['id']: p for p in programmes}
    weight, bridge = sources()
    vec = vectors(programmes)
    srcs = {s: (w, vec[s]) for s, w in weight.items() if s in vec}
    if bridge:                                                                # the YouTube history as one more source: its topics as categories
        total = sum(bridge.values()) or 1.0
        b = {'c:' + c: x / total for c, x in bridge.items()}
        norm = math.sqrt(sum(x * x for x in b.values())) or 1.0
        srcs['youtube'] = (BRIDGE, {f: x / norm for f, x in b.items()})
    found = {}
    for p in programmes:
        if p['id'] in followed or p['id'] in weight or p['kind'] == 'episode' or not srcs: continue
        likes = sorted(((w * cosine(vec[p['id']], v), s) for s, (w, v) in srcs.items()), reverse=True)
        likes = [(x, s) for x, s in likes if x > 0]
        if not likes: continue
        total = likes[0][0] + OTHERS * sum(x for x, _ in likes[1:TOP_SOURCES])
        if total >= MIN_SCORE: found[p['id']] = (total, likes[:TOP_SOURCES], sum(1 for x, _ in likes if x >= CLOSE) or 1)
    best = dict(spread(found, LIMIT))
    with db.connect() as con:
        held = {r[0]: r[1] for r in con.execute("SELECT channel_id, watches FROM suggestions WHERE platform = 'iplayer'")}
        con.execute("UPDATE suggestions SET suggested_by = ?, related_score = ? WHERE platform = 'iplayer'", (0, 0.0))
        con.execute('DELETE FROM bbc_similar')
        for pid, (total, likes, close) in best.items():
            p = by_id[pid]; cats = [c for c in (p['categories'] or '').split('|') if c]; cats = [c for c in cats if c not in fine(cats)]
            vals = dict(c=pid, t=p['title'], th=p['thumbnail'], n=p['episodes'], tp='|'.join(dict.fromkeys(([p['label']] if p['label'] else []) + [c.replace('-', ' ').capitalize() for c in cats]))[:400] or None,
                        k=kids(p), by=close, s=round(total, 4))
            if pid in held:
                con.execute('UPDATE suggestions SET title = :t, thumbnail = COALESCE(:th, thumbnail), total_videos = :n, topics = :tp, made_for_kids = :k, suggested_by = :by, related_score = :s WHERE channel_id = :c', vals)
            else:
                con.execute("INSERT INTO suggestions (channel_id, platform, title, thumbnail, total_videos, topics, made_for_kids, suggested_by, related_score) VALUES (:c, 'iplayer', :t, :th, :n, :tp, :k, :by, :s)", vals)
            con.executemany('INSERT INTO bbc_similar (channel_id, source_id, score) VALUES (:c, :s, :x)', [dict(c=pid, s=s, x=round(x, 4)) for x, s in likes])
        con.execute("DELETE FROM suggestions WHERE platform = 'iplayer' AND suggested_by = ? AND watches = ? AND pasted IS NULL AND dismissed IS NULL", (0, 0))
        con.execute("INSERT INTO meta (key, value) VALUES ('bbc_suggested', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (now,))
    return dict(sources=len(srcs), suggested=len(best), added=sum(1 for pid in best if pid not in held))


def spread(found, limit):
    """The best `limit` of `found` ({id: (score, [(likeness, source)], close)}), taken in turn from each source's own best (by the source it
    is most like), so one dense corner of the catalogue (a dozen nature series like one followed) does not fill every place."""
    lanes = collections.defaultdict(list)
    for pid, v in sorted(found.items(), key=lambda kv: (-kv[1][0], kv[0])): lanes[v[1][0][1]].append((pid, v))
    order = sorted(lanes, key=lambda src: (-lanes[src][0][1][0], src))          # the lane with the best suggestion first
    out = []
    for i in range(max((len(x) for x in lanes.values()), default=0)):
        out += [lanes[src][i] for src in order if i < len(lanes[src])]
    return out[:limit]


def run(now=None, force=False):
    """Refresh the catalogue if it is due (or `force`), then score: what `tubes related` does for iPlayer after YouTube. Returns both results."""
    return dict(catalogue=refresh_catalogue(now, force), **score(now))


def pointers(channel_ids, top=TOP_SOURCES):
    """For each suggested programme, the titles of what it is most like, the closest first: `{channel_id: [title]}`."""
    if not channel_ids: return {}
    out, ids = collections.defaultdict(list), list(channel_ids)
    with db.connect() as con:
        rows = con.execute(f'''SELECT x.channel_id, x.source_id, COALESCE(c.title, b.title, x.source_id) FROM bbc_similar x LEFT JOIN channels c ON c.id = x.source_id
                               LEFT JOIN bbc_programmes b ON b.id = x.source_id WHERE x.channel_id IN ({', '.join('?' * len(ids))}) ORDER BY x.channel_id, x.score DESC, x.source_id''', tuple(ids))
        for cid, src, name in rows:
            if len(out[cid]) < top: out[cid].append('your YouTube history' if src == 'youtube' else name)
    return dict(out)
