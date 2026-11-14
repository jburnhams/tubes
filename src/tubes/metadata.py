"""A channel's or video's metadata beyond the few fields every list shows: one shape for every source, modelled on Plex's (the richest), that
YouTube and iPlayer fill as far as they can.

On the rows themselves (models.py): `kind` (video, episode or film; a channel is a channel, programme, network, category, show or filter),
`tagline`, `year`, `network`, `season` (with `series`, the series' title, and `episode`), `content_rating` and `min_age`, `kids`, the
picture's `width`, `height` and `hdr`, and `colours` for a backdrop. In tables of their own, keyed by `owner` ('channel' or 'video') and its
id: `images` (every picture by kind, rank 0 the one to show), `tags` (genres, categories, topics, keywords, labels, countries), `credits` (cast
and crew in billing order), `ratings` (out of 10, by source), `external_ids` (the same title's ids elsewhere, so two sources can be matched),
and for videos `chapters` and `tracks` (audio and subtitle tracks, and other versions such as audio-described or signed).

What each source gives (2026-11-14):
  YouTube   video: thumbnails in every size, tags, category, topics, madeForKids, an age restriction (`18`), chapters from the description's
            timestamps (YouTube's own rule: the first at 0:00, at least three, each at least 10 s); channel: avatar in every size, banner,
            keywords, topics, madeForKids. No credits, ratings or tracks (captions stay the row's `captions`).
  iPlayer   episode: 16:9, portrait and promotional images, short synopsis as tagline, categories and label, network, series number, the
            children's flag, HD/UHD/HDR, the audio-described and signed versions; programme: its images, short synopsis, categories, label,
            network. ibl has no credits (its credits endpoints answer 404).
  Plex      everything above, plus credits, ratings, external ids, chapters with images, audio and subtitle tracks (plex.py, to come).

A source row (youtube.video_row, iplayer.channel_row...) carries these lists under `meta` ({table: [rows]}); `save` replaces, for each table a
row names, whatever the owner had there before, and leaves the tables it does not name alone, so a source that never gives credits never
clears another's. `get` reads them back for one owner, as lists."""
import json

from tubes import db

IMAGE_KINDS = ('thumb', 'poster', 'backdrop', 'logo', 'square', 'banner', 'avatar', 'portrait')
TAG_KINDS = ('genre', 'category', 'topic', 'keyword', 'label', 'country')
TABLES = {    # table: (its columns past the owner's, in order; whether it is keyed by video_id alone)
    'images': (('kind', 'rank', 'url', 'width', 'height'), False),
    'tags': (('kind', 'value', 'rank'), False),
    'credits': (('role', 'rank', 'name', 'character', 'photo'), False),
    'ratings': (('source', 'value'), False),
    'external_ids': (('source', 'value'), False),
    'chapters': (('start', 'end', 'title', 'image'), True),
    'tracks': (('kind', 'rank', 'language', 'label', 'codec', 'ref', 'is_default', 'forced'), True),
}
PRIMARY = dict(images=('kind', 'rank'), tags=('kind', 'value'), credits=('role', 'rank'), ratings=('source',), external_ids=('source',), chapters=('start',), tracks=('kind', 'rank'))
ORDER = dict(images='kind, rank', tags='kind, rank, value', credits='role, rank', ratings='source', external_ids='source', chapters='start', tracks='kind, rank')
DEFAULTS = dict(width=None, height=None, rank=0, character=None, photo=None, end=None, title=None, image=None, language=None, label=None, codec=None, ref=None, is_default=False, forced=False)


def _col(c): return f'"{c}"' if c == 'end' else c       # `end` is a keyword in SQL (segments quotes it too)


def colours(blur):
    """Plex's UltraBlurColors (or any such dict of four hex colours) as the JSON kept in `colours`, or None."""
    keys = ('topLeft', 'topRight', 'bottomRight', 'bottomLeft')
    if not isinstance(blur, dict) or not all(isinstance(blur.get(k), str) for k in keys): return None
    return json.dumps({k: '#' + blur[k].lstrip('#')[:6] for k in keys})


def strip(row):
    """A source row without its `meta`, for the row's own table."""
    return {k: v for k, v in row.items() if k != 'meta'}


def save(con, owner, rows):
    """Write the `meta` of these source rows (each with `id`) for this owner ('channel' or 'video'): each table a row names is replaced for it."""
    for row in rows:
        meta = row.get('meta') or {}
        for table, items in meta.items():
            if table not in TABLES: raise ValueError(f'{table} is not a metadata table')
            cols, by_video = TABLES[table]
            key = ('video_id',) if by_video else ('owner', 'owner_id')
            if by_video and owner != 'video': raise ValueError(f'only a video has {table}')
            where = ' AND '.join(f'{k} = :{k}' for k in key)
            ids = dict(video_id=row['id']) if by_video else dict(owner=owner, owner_id=row['id'])
            con.execute(f'DELETE FROM {table} WHERE {where}', ids)
            seen, out = set(), []
            for i, item in enumerate(items or []):
                r = dict(DEFAULTS, **({'rank': i} if 'rank' in cols and 'rank' not in item else {}), **item, **ids)
                pk = tuple(r.get(c) for c in PRIMARY[table])
                if pk in seen: continue                                   # a source that repeats itself (the same tag twice) keeps the first
                seen.add(pk); out.append({c: r.get(c) for c in (*key, *cols)})
            if out: con.executemany(f"INSERT INTO {table} ({', '.join(_col(c) for c in (*key, *cols))}) VALUES ({', '.join(':' + c for c in (*key, *cols))})", out)


def get(owner, owner_id):
    """Every metadata table's rows for one channel or video, as {table: [rows]} (a video's chapters and tracks too); empty lists where none."""
    out = {}
    with db.connect() as con:
        for table, (cols, by_video) in TABLES.items():
            if by_video and owner != 'video': continue
            where, args = ('video_id = ?', (owner_id,)) if by_video else ('owner = ? AND owner_id = ?', (owner, owner_id))
            rows = db.rows(con.execute(f"SELECT {', '.join(_col(c) for c in cols)} FROM {table} WHERE {where} ORDER BY {ORDER[table]}", args))
            for r in rows:
                for b in ('is_default', 'forced'):
                    if b in r: r[b] = bool(r[b])                          # SQLite answers 0 and 1
            out[table] = rows
    return out


def delete(con, owner, ids):
    """Forget the metadata of these channels or videos (they left the library)."""
    ids = list(ids)
    if not ids: return
    marks = ', '.join('?' * len(ids))
    for table, (_cols, by_video) in TABLES.items():
        if by_video and owner != 'video': continue
        if by_video: con.execute(f'DELETE FROM {table} WHERE video_id IN ({marks})', tuple(ids))
        else: con.execute(f'DELETE FROM {table} WHERE owner = ? AND owner_id IN ({marks})', (owner, *ids))
