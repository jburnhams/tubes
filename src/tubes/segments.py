"""Parts of a video the player can skip, one list for every platform under SponsorBlock's categories (settings.SKIP_DEFAULTS), and what the
player does in each kind (`skip_<category>` settings: off, ask or auto).

- YouTube: SponsorBlock (sponsor.ajay.app), the community's database of sponsor reads, intros, end cards and the like, asked without a key.
  It is asked by the first 4 hex digits of the video id's SHA-256, as its extension does, so the server never says which video is played; the
  answer covers every video with that prefix, and the one wanted is picked out. A 404 means none are known. Only `skip` and `mute` segments
  are kept (not chapters, highlights or whole-video labels).
- iPlayer: each episode's version says where its intro is (an `interactions` entry, type skip, subtype intro, from `show_from` to `skip_to`;
  a recap's subtype is mapped onto `preview`) and where its credits start (`credits_start`, to the end: `outro`). Both are iPlayer's own
  "Skip intro" and "Up next" points, so they are exact.

A video's list is kept in `segments` and asked again after FRESH_DAYS (people keep adding to SponsorBlock), or RETRY_HOURS after the
source failed; a failure is said, and the cached list (if any) is still given. `TUBES_SPONSORBLOCK` points the calls elsewhere (the tests'
stand-in)."""
import datetime, hashlib, json, os, urllib.error, urllib.parse, urllib.request

from tubes import cache, db, iplayer, settings

API = 'https://sponsor.ajay.app'
TIMEOUT = 15
FRESH_DAYS = 1
RETRY_HOURS = 1
ACTIONS = ('skip', 'mute')
LABELS = dict(sponsor='Sponsor', selfpromo='Self-promotion', interaction='Subscribe reminder', intro='Intro', outro='Credits and end cards',
              preview='Preview or recap', hook='Hook or greeting', filler='Filler or tangent', music_offtopic='Non-music section')
DETAILS = dict(sponsor='A paid promotion or sponsor read.', selfpromo="Unpaid promotion: the creator's own merchandise, Patreon or other channels.",
               interaction='A reminder to like, subscribe or follow.', intro='An intro or title sequence (iPlayer marks these on its programmes).',
               outro='Credits or end cards (iPlayer marks where its credits start).', preview='A preview of what is coming, or a recap of what came before.',
               hook='A teaser or greeting at the start, before the video gets going.', filler='A tangent or joke that is not needed to follow the video.',
               music_offtopic='The talking or other parts of a music video that are not the music.')


class SegmentError(RuntimeError):
    """The source of a video's segments could not be asked; the message says why, in a sentence."""


def categories():
    """Every category, in SponsorBlock's order, with its label, a sentence and the setting for it: `[{id, label, detail, mode}]`."""
    return [dict(id=c, label=LABELS[c], detail=DETAILS[c], mode=settings.get(f'skip_{c}')) for c in settings.SKIP_DEFAULTS]


def sponsorblock(video_id):
    """SponsorBlock's segments for a YouTube video: `[{category, start, end, action, votes}]` (see the module's notes)."""
    prefix = hashlib.sha256(video_id.encode()).hexdigest()[:4]
    cats = json.dumps(list(settings.SKIP_DEFAULTS), separators=(',', ':'))
    url = f"{os.environ.get('TUBES_SPONSORBLOCK', API).rstrip('/')}/api/skipSegments/{prefix}?{urllib.parse.urlencode(dict(categories=cats))}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'tubes'}), timeout=TIMEOUT) as r: data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404: return []
        raise SegmentError(f'SponsorBlock refused the request ({e.code}).') from None
    except (urllib.error.URLError, OSError) as e: raise SegmentError(f'SponsorBlock could not be reached: {getattr(e, "reason", e)}.') from None
    except ValueError: raise SegmentError('SponsorBlock did not answer with JSON.') from None
    mine = next((v for v in data if isinstance(v, dict) and v.get('videoID') == video_id), None) if isinstance(data, list) else None
    out = []
    for s in (mine or {}).get('segments') or []:
        seg, cat, act = s.get('segment') or [], s.get('category'), s.get('actionType') or 'skip'
        if cat in settings.SKIP_DEFAULTS and act in ACTIONS and len(seg) == 2 and seg[1] > seg[0]:
            out.append(dict(category=cat, start=round(float(seg[0]), 3), end=round(float(seg[1]), 3), action=act, votes=s.get('votes')))
    return out


SUBTYPES = dict(intro='intro', recap='preview', preview='preview')


def iplayer_points(episode_pid):
    """iPlayer's own skip points for an episode: `[{category, start, end, action, votes}]` (see the module's notes)."""
    try: ep = iplayer.episode(episode_pid)
    except iplayer.IplayerError as e: raise SegmentError(str(e)) from None
    v = iplayer.version(ep) if ep else None
    if not v: return []
    out = []
    for i in v.get('interactions') or []:
        cat, pts = SUBTYPES.get(i.get('subtype')), i.get('interaction_points') or {}
        start, end = pts.get('show_from'), pts.get('skip_to')
        if i.get('type') == 'skip' and cat and isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            out.append(dict(category=cat, start=float(start), end=float(end), action='skip', votes=None))
    length = iplayer.seconds((v.get('duration') or {}).get('value'))
    credits = v.get('credits_start')
    if isinstance(credits, (int, float)) and length and length > credits:
        out.append(dict(category='outro', start=float(credits), end=float(length), action='skip', votes=None))
    return out


def _ago(now, **kw): return (datetime.datetime.fromisoformat(now) - datetime.timedelta(**kw)).isoformat(timespec='seconds')


def for_video(video_id, now=None):
    """A video's segments and what the player does in each: `{segments: [{category, start, end, action}], categories: [...], error}` (`error`
    when the source could not be asked just now). Asks the source when its list is due (see the module's notes)."""
    now = now or cache.stamp()
    with db.connect() as con:
        v = con.execute('SELECT platform FROM videos WHERE id = ?', (video_id,)).fetchone()
        check = con.execute('SELECT checked, error FROM segment_checks WHERE video_id = ?', (video_id,)).fetchone()
    platform = (v[0] if v else None) or 'youtube'
    due = check is None or check[0] < (_ago(now, hours=RETRY_HOURS) if check[1] else _ago(now, days=FRESH_DAYS))
    error = check[1] if check else None
    if due:
        try:
            got, error = (iplayer_points(video_id) if platform == 'iplayer' else sponsorblock(video_id)), None
            with db.connect() as con:
                con.execute('DELETE FROM segments WHERE video_id = ?', (video_id,))
                rows = {(s['start'], s['category']): s for s in got}                       # SponsorBlock can list two of a kind at one start
                con.executemany('INSERT INTO segments (video_id, start, category, "end", source, action, votes) VALUES (:v, :start, :category, :end, :src, :action, :votes)',
                                [dict(s, v=video_id, src='iplayer' if platform == 'iplayer' else 'sponsorblock') for s in rows.values()])
        except SegmentError as e: error = str(e)
        with db.connect() as con:
            con.execute('INSERT INTO segment_checks (video_id, checked, error) VALUES (?, ?, ?) ON CONFLICT (video_id) DO UPDATE SET checked = excluded.checked, error = excluded.error',
                        (video_id, now, error))
    with db.connect() as con:
        segs = db.rows(con.execute('SELECT category, start, "end", action FROM segments WHERE video_id = ? ORDER BY start, category', (video_id,)))
    return dict(segments=segs, categories=categories(), error=error)
