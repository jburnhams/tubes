"""BBC iPlayer, as the catalogue (catalogue.py) and the fetcher (fetcher.py) use it: a programme is kept as a channel and its episodes as
videos (`platform` 'iplayer'), so every screen shows them as it shows YouTube's.

Two public BBC services, neither needing a key, both answering only from the UK:
  ibl            the catalogue iPlayer's own apps read (`/ibl/v1`): a programme (title, synopsis, images, categories, network), its episodes a
                 page of up to 200 at a time (titles like `Series 1: 2. Name`, synopses, images, and per version its duration, first
                 broadcast, whether it is HD and when it stops being offered), one episode by id, and search.
  mediaselector  which streams an episode's version (its `vpid`) has: for the `iptv-all` set, an HLS master playlist whose best variant is
                 720p at 50 frames a second, muxed H.264 + AAC in MPEG-TS.
HD episodes also exist at 1080p50: the 720p50 variant's address with its video bitrate swapped for `video=12000000` (the way get_iplayer
reaches them; mediaselector does not list it, and not every HD episode has one, so it is asked for and kept only when it answers). ffmpeg
reads either playlist itself: unlike YouTube's, the segment addresses carry their own token, so no yt-dlp is needed between them (see
fetcher.py). Measured on the home server (2026-11-12): the first segment in 0.4 s, a 29-minute episode (1.9 GB at 1080p50) in under a minute.

Episode images are templates (`.../{recipe}/<id>.jpg`) filled in with a size; 16:9 like YouTube's thumbnails. A one-off (a film: its own
top-level programme) has no programme to follow. A category (iPlayer's `films`, `documentaries` ...) can be followed instead, as a channel
with the id `iplayer-<category>`: its sync takes the category's one-offs (ibl lists a category's programmes 200 a page, a one-off's
`initial_children` being the whole episode, so a sync of every film is two calls) and leaves its series to be followed as programmes. A
one-off added on its own is kept under the category channel when it is a film (FILED_UNDER), else under its network (`bbc_one`), unfollowed.

`TUBES_IPLAYER_API` and `TUBES_MEDIASELECTOR` point the calls elsewhere (the tests' stand-in)."""
import datetime, json, os, re, urllib.error, urllib.parse, urllib.request

IBL = 'https://ibl.api.bbc.co.uk/ibl/v1'
MEDIASELECTOR = 'https://open.live.bbc.co.uk/mediaselector/6/select/version/2.0'
MEDIASET = 'iptv-all'
TIMEOUT = 30
PAGE = 200
FHD_BITRATE = 12000000
THUMB = '1280x720'                    # an episode's or programme's wide image, as big as YouTube's best thumbnails that the cards scale down
AVATAR = '480x480'                    # a programme's square image, for the round channel avatar
PID = re.compile(r'^[b-df-hj-np-tv-z0-9]{8,15}$')     # BBC programme ids: lower-case consonants and digits
SUBTITLE = re.compile(r'^(?P<series>[^:]+):\s*(?:(?P<n>\d+)\.\s*)?(?P<rest>.*)$')
SKIP_KINDS = ('audio-described', 'signed')                   # versions for those who need them, never the default one
KIND_ORDER = ('original', 'editorial', 'shortened')
HOSTS = ('bbc.co.uk', 'www.bbc.co.uk', 'bbc.com', 'www.bbc.com')
CATEGORY = re.compile(r'^[a-z][a-z-]{1,40}$')
PREFIX = 'iplayer-'                                          # a category channel's id: `iplayer-films`
FILED_UNDER = ('films',)                                     # a one-off in one of these categories is kept under its category's channel


class IplayerError(RuntimeError):
    """A call to iPlayer failed, or it cannot play this; the message says why, in a sentence."""


def _get(url, accept='application/json', error_body=False):
    """The body of a GET. `error_body`: an error status's body is returned too (the mediaselector says why it will not play in a JSON body with 403 or 404)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': 'tubes'}), timeout=TIMEOUT) as r: return r.read()
    except urllib.error.HTTPError as e:
        if error_body:
            try: return e.read()
            except OSError: pass
        raise IplayerError(f'iPlayer refused the request ({e.code}).') from None
    except (urllib.error.URLError, OSError) as e: raise IplayerError(f'iPlayer could not be reached: {getattr(e, "reason", e)}.') from None


def call(path, **params):
    """One GET on ibl; returns its JSON."""
    url = f"{os.environ.get('TUBES_IPLAYER_API', IBL)}/{path}" + (f'?{urllib.parse.urlencode(params)}' if params else '')
    try: return json.loads(_get(url))
    except ValueError: raise IplayerError('iPlayer did not answer with JSON.') from None


def parse(text):
    """('programme', pid), ('episode', pid), ('pid', pid) (a bbc.co.uk/programmes link, which may be either) or ('category', id) (an
    iPlayer category page: /iplayer/categories/films/..., /iplayer/browse/films) for an iPlayer or BBC programmes link; None when it is not one (so YouTube can read it); ValueError for a BBC link that names no programme."""
    t = (text or '').strip()
    if '://' not in t and not t.startswith(HOSTS): return None
    u = urllib.parse.urlparse(t if '://' in t else 'https://' + t)
    if u.netloc.lower() not in HOSTS: return None
    path = [p for p in u.path.split('/') if p]
    if len(path) >= 3 and path[0] == 'iplayer' and path[1] in ('episodes', 'episode') and PID.match(path[2]):
        return ('programme' if path[1] == 'episodes' else 'episode'), path[2]
    if len(path) >= 2 and path[0] == 'programmes' and PID.match(path[1]): return 'pid', path[1]
    if len(path) >= 3 and path[0] == 'iplayer' and path[1] in ('categories', 'browse') and CATEGORY.match(path[2]): return 'category', path[2]
    raise ValueError('That BBC link is not to an iPlayer programme, episode or category.')


def image(template, recipe=THUMB):
    return template.replace('{recipe}', recipe) if template else None


def stamp(value):
    """A BBC time (`2026-11-11T19:30:00.000Z`) as the ISO string the database keeps (`2026-11-11T19:30:00+00:00`); None when unreadable."""
    try: t = datetime.datetime.fromisoformat((value or '').replace('Z', '+00:00'))
    except ValueError: return None
    if t.tzinfo is None: t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()


DURATION = re.compile(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?$')


def seconds(duration):
    """`PT29M0.117333S` in seconds (29.0 min); None when it cannot be read."""
    m = DURATION.match(duration or '')
    if not m or not any(m.groups()): return None
    h, mi, s = m.groups()
    return round(int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0), 3)


def version(episode):
    """The version to show and play: the original (or the broadcast edit) rather than the audio-described or signed one; None when it has none."""
    vs = [v for v in episode.get('versions') or [] if v.get('id')]
    plain = [v for v in vs if v.get('kind') not in SKIP_KINDS] or vs
    if not plain: return None
    return min(plain, key=lambda v: KIND_ORDER.index(v['kind']) if v.get('kind') in KIND_ORDER else len(KIND_ORDER))


def names(episode):
    """(title, series, number) from an episode: `Series 1: 2. Name` is ('Name', 'Series 1', 2); a dated one (`11/11/2026`) keeps the date as its title."""
    sub, number = (episode.get('subtitle') or '').strip(), episode.get('parent_position')
    number = number if isinstance(number, int) else None
    m = SUBTITLE.match(sub)
    if m and m['rest'].strip():
        return m['rest'].strip(), m['series'].strip(), number if number is not None else (int(m['n']) if m['n'] else None)
    return sub or (episode.get('original_title') or '').strip() or episode.get('title') or episode['id'], None, number


def channel_row(programme, now):
    """An ibl programme as a `channels` row."""
    im, syn = programme.get('images') or {}, programme.get('synopses') or {}
    return dict(id=programme['id'], platform='iplayer', title=programme.get('title') or programme['id'], handle=None,
                thumbnail=image(im.get('standard') or im.get('promotional'), AVATAR), description=syn.get('large') or syn.get('medium') or syn.get('small'),
                published=None, country='GB', subscribers=None, total_videos=programme.get('count'), views=None, uploads=None, added=now)


def network_row(episode, now):
    """The channel a one-off is kept under: its network (`bbc_one`, BBC One)."""
    mb = episode.get('master_brand') or {}
    title = (mb.get('titles') or {}).get('large') or mb.get('id') or 'BBC'
    return dict(id=mb.get('id') or 'bbc', platform='iplayer', title=title, handle=None, thumbnail=None, description=None, published=None, country='GB',
                subscribers=None, total_videos=None, views=None, uploads=None, added=now)


def one_off(episode):
    return episode.get('tleo_type') == 'episode' or not episode.get('tleo_id') or episode.get('tleo_id') == episode['id']


def channel_of(episode):
    """The id of the channel an episode is kept under: its programme; for a one-off, its category's channel when it is a film, else its network."""
    if not one_off(episode): return episode['tleo_id']
    filed = next((c for c in FILED_UNDER if c in (episode.get('categories') or [])), None)
    return PREFIX + filed if filed else (episode.get('master_brand') or {}).get('id') or 'bbc'


def category_id(channel_id):
    """The category a channel follows (`films` for `iplayer-films`), or None for any other channel."""
    return channel_id[len(PREFIX):] if (channel_id or '').startswith(PREFIX) else None


def category(cat):
    """iPlayer's category with this id (`{id, title}`), or None when it has none."""
    return next((c for c in call('categories').get('categories') or [] if c.get('id') == cat), None)


def category_row(cat, now):
    """A category (`{id, title}`) as a `channels` row, id `iplayer-<id>`."""
    return dict(id=PREFIX + cat['id'], platform='iplayer', title=cat.get('title') or cat['id'], handle=None, thumbnail=None,
                description=f"Every one-off in iPlayer's {cat.get('title') or cat['id']}, as iPlayer offers them.", published=None, country='GB',
                subscribers=None, total_videos=None, views=None, uploads=None, added=now)


def category_page(cat, page=1):
    """One page (up to PAGE) of a category's programmes, as iPlayer orders them: (its one-offs, as whole episodes; whether there are more;
    how many programmes the page listed). Its series are left out (they are followed as programmes), so a page can list programmes and
    hold no one-offs; `count` is every programme in it."""
    r = call(f'categories/{cat}/programmes', per_page=PAGE, page=page).get('category_programmes') or {}
    items = r.get('elements') or []
    eps = [c for p in items if p.get('tleo_type') == 'episode' for c in (p.get('initial_children') or [])[:1] if c.get('id')]
    return eps, page * PAGE < (r.get('count') or 0) and bool(items), len(items)


def video_row(episode, now):
    """An ibl episode as a `videos` row."""
    v, im, syn = version(episode) or {}, episode.get('images') or {}, episode.get('synopses') or {}
    title, series, number = names(episode)
    avail = v.get('availability') or {}
    published = stamp(v.get('first_broadcast_date_time')) or stamp(episode.get('release_date_time')) or stamp(avail.get('start')) or now
    return dict(id=episode['id'], platform='iplayer', channel_id=channel_of(episode), title=title, published=published,
                duration=seconds((v.get('duration') or {}).get('value')), thumbnail=image(im.get('standard')), views=None,
                description=syn.get('large') or syn.get('medium') or syn.get('small') or syn.get('editorial'), likes=None, comments=None,
                definition=('hd' if v.get('hd') else 'sd') if v else None, live=None, expires=stamp(avail.get('end')), series=series, episode=number, added=now)


def programme(pid):
    """The ibl programme for this id, or None when iPlayer has no such programme (an episode's id answers None too)."""
    items = call(f'programmes/{pid}').get('programmes') or []
    return items[0] if items and items[0].get('id') == pid else None


def search(text):
    """What iPlayer finds for some words (`new-search`, the only search ibl answers; measured 2026-11-12): programmes and episodes, fuzzy and
    unpaged, so callers match titles themselves. Returns `[{id, title, kind, thumbnail}]` with `id` the followable programme: a programme's
    own id, an episode's `tleo_id` when it belongs to one (`tleo_type` brand or series); one-offs, which have no programme, are left out."""
    out, seen = [], set()
    for r in (call('new-search', q=text, rights='web').get('new_search') or {}).get('results') or []:
        if r.get('type') == 'programme': pid = r.get('id')
        elif r.get('type') == 'episode' and r.get('tleo_type') in ('brand', 'series') and r.get('tleo_id') != r.get('id'): pid = r.get('tleo_id')
        else: continue
        if not pid or pid in seen: continue
        seen.add(pid); im = r.get('images') or {}
        out.append(dict(id=pid, title=r.get('title') or pid, kind=r['type'], thumbnail=image(im.get('standard') or im.get('promotional'), AVATAR)))
    return out


def programme_url(pid):
    cat = category_id(pid)
    return f'https://www.bbc.co.uk/iplayer/categories/{cat}/featured' if cat else f'https://www.bbc.co.uk/iplayer/episodes/{pid}'


def episode(pid):
    """The ibl episode for this id, or None when iPlayer does not offer it."""
    items = call(f'episodes/{pid}').get('episodes') or []
    return items[0] if items and items[0].get('id') == pid else None


def episodes_page(pid, page=1):
    """One page (up to PAGE) of a programme's episodes, newest first: (episodes, whether there are more)."""
    r = call(f'programmes/{pid}/episodes', per_page=PAGE, page=page).get('programme_episodes') or {}
    items = [e for e in r.get('elements') or [] if e.get('type') == 'episode' and e.get('id')]
    return items, page * PAGE < (r.get('count') or 0) and bool(items)


def episode_url(pid): return f'https://www.bbc.co.uk/iplayer/episode/{pid}'


# Streams.

def mediaselector(vpid):
    """The mediaselector's answer for a version: its HLS master playlists (one per CDN). Raises IplayerError saying why there are none."""
    url = f"{os.environ.get('TUBES_MEDIASELECTOR', MEDIASELECTOR)}/mediaset/{MEDIASET}/vpid/{vpid}/format/json"
    try: d = json.loads(_get(url, error_body=True))
    except ValueError: raise IplayerError('iPlayer did not answer with JSON.') from None
    if d.get('result'):
        why = {'geolocation': 'iPlayer only plays in the UK, and this server is not seen as in the UK.',
               'selectionunavailable': 'iPlayer has no stream of this episode (it may have just expired).'}.get(d['result'])
        raise IplayerError(why or f'iPlayer would not play this episode ({d["result"]}).')
    masters = [c['href'] for m in d.get('media') or [] if m.get('kind') == 'video' for c in m.get('connection') or []
               if c.get('transferFormat') == 'hls' and c.get('href')]
    if not masters: raise IplayerError('iPlayer offered no HLS stream of this episode.')
    return list(dict.fromkeys(masters))


ATTR = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def variants(master_url, text):
    """The variants of an HLS master playlist: [{url, height, fps, bandwidth, codecs}], addresses made absolute."""
    out, attrs = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#EXT-X-STREAM-INF:'): attrs = {k: v.strip('"') for k, v in ATTR.findall(line.split(':', 1)[1])}
        elif line and not line.startswith('#') and attrs is not None:
            res = attrs.get('RESOLUTION', '')
            out.append(dict(url=urllib.parse.urljoin(master_url, line), height=int(res.split('x')[1]) if 'x' in res else 0,
                            fps=float(attrs.get('FRAME-RATE') or 0), bandwidth=int(attrs.get('BANDWIDTH') or 0), codecs=attrs.get('CODECS', '')))
            attrs = None
    return out


def fhd_url(url):
    """The 1080p50 sibling of a 720p50 variant's address (see the module's notes), or None when the address names no video bitrate."""
    new = re.sub(r'video=\d+', f'video={FHD_BITRATE}', url)
    return new if new != url else None


def _answers(url):
    """True when a variant playlist answers with segments of its own bitrate (an asked-for 1080p variant that does not exist answers 403 or 404)."""
    try: text = _get(url, accept='*/*').decode('utf8', 'replace')
    except IplayerError: return False
    return '#EXTINF' in text and f'video={FHD_BITRATE}' in text


def stream(episode_pid, max_height=1080):
    """The stream to fetch for an episode: `{url, height, fps, label}`, the tallest within `max_height` (1080p50 when the episode is HD and
    has one, else the best listed variant). Raises IplayerError when iPlayer does not offer it or will not play it here."""
    ep = episode(episode_pid)
    if ep is None: raise IplayerError('iPlayer no longer offers this episode.')
    v = version(ep)
    if v is None: raise IplayerError('iPlayer lists no playable version of this episode.')
    error = None
    for master in mediaselector(v['id']):
        try: listed = variants(master, _get(master, accept='*/*').decode('utf8', 'replace'))
        except IplayerError as e: error = e; continue
        fit = [x for x in listed if x['height'] and x['height'] <= max_height]
        if not fit: continue
        best = max(fit, key=lambda x: (x['height'], x['fps'], x['bandwidth']))
        if max_height >= 1080 and v.get('hd') and best['height'] == 720 and best['fps'] >= 50:
            fhd = fhd_url(best['url'])
            if fhd and _answers(fhd): return dict(url=fhd, height=1080, fps=50, label='1080p50 H.264 + AAC')
        return dict(url=best['url'], height=best['height'], fps=best['fps'], label=f"{best['height']}p{best['fps']:g} H.264 + AAC")
    raise error or IplayerError(f'iPlayer offered no stream at or under {max_height}p.')


def reachable():
    """Whether the mediaselector answers here as it does in the UK: (True, None), or (False, why). Asks about a version that does not exist,
    which a UK address is told is unavailable and any other is told is out of region."""
    try: mediaselector('b0000000')
    except IplayerError as e:
        msg = str(e)
        if 'only plays in the UK' in msg or 'could not be reached' in msg or 'refused' in msg: return False, msg
        return True, None
    return True, None
