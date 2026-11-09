"""The YouTube Data API v3, as the catalogue (catalogue.py) uses it: channels by id or handle, a channel's uploads playlist a page at a
time, and videos' details in batches of 50. Ported from the storage service's Worker (src/services/youtube.ts), which managed the library
before Tubes did.

The key is the environment's `YOUTUBE_API_KEY`, never the settings file. A key can be restricted to HTTP referrers in Google's console;
`YOUTUBE_API_REFERER` is then sent as the Referer header (without it such a key gets 403). `TUBES_YOUTUBE_API` points the calls at another
address (the tests' stand-in). Each call costs one unit of the key's daily quota (10,000 by default): a page of 50 uploads is one, the
details of up to 50 videos are one more.

`parse` reads what a person pastes (a channel or video link, an id, a handle) so one field can add either."""
import json, os, re, urllib.error, urllib.parse, urllib.request

API = 'https://www.googleapis.com/youtube/v3'
TIMEOUT = 30
VIDEO_PARTS = 'snippet,contentDetails,statistics'
CHANNEL_PARTS = 'snippet,statistics,contentDetails'
VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
CHANNEL_ID = re.compile(r'^UC[A-Za-z0-9_-]{22}$')
DURATION = re.compile(r'^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$')
THUMBS = ('maxres', 'standard', 'high', 'medium', 'default')


class YoutubeError(RuntimeError):
    """A call to the Data API failed; the message says why, in a sentence. `status` is the HTTP status when there was one."""
    def __init__(self, message, status=None):
        super().__init__(message); self.status = status


def configured():
    return bool(os.environ.get('YOUTUBE_API_KEY'))


def call(endpoint, **params):
    """One GET on the Data API; returns its JSON."""
    key = os.environ.get('YOUTUBE_API_KEY', '')
    if not key: raise YoutubeError('YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.')
    url = f"{os.environ.get('TUBES_YOUTUBE_API', API)}/{endpoint}?{urllib.parse.urlencode(dict(params, key=key))}"
    headers = {'Accept': 'application/json'}
    if os.environ.get('YOUTUBE_API_REFERER'): headers['Referer'] = os.environ['YOUTUBE_API_REFERER']
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: err = json.loads(e.read()).get('error') or {}
        except ValueError: err = {}
        reason = next((x.get('reason') for x in err.get('errors') or [] if x.get('reason')), None)
        why = err.get('message') or reason
        if reason == 'quotaExceeded': why = 'the key has used its quota for today (it resets at midnight Pacific time)'
        raise YoutubeError(f'YouTube refused the request ({e.code}{": " + why if why else ""}).', e.code) from None
    except (urllib.error.URLError, OSError) as e: raise YoutubeError(f'YouTube could not be reached: {getattr(e, "reason", e)}.') from None
    except ValueError: raise YoutubeError('YouTube did not answer with JSON.') from None


def parse(text):
    """('video', id), ('channel', id) or ('handle', '@name') for what a person typed or pasted, or ValueError saying what was expected."""
    t = (text or '').strip()
    if not t: raise ValueError('Enter a channel or video: a link, an id or an @handle.')
    if '://' in t or t.startswith(('www.', 'youtube.com', 'youtu.be', 'm.youtube.com')):
        u = urllib.parse.urlparse(t if '://' in t else 'https://' + t); path = [p for p in u.path.split('/') if p]
        if u.netloc.endswith('youtu.be') and path: return 'video', path[0]
        v = urllib.parse.parse_qs(u.query).get('v')
        if v: return 'video', v[0]
        if len(path) >= 2 and path[0] in ('shorts', 'live', 'embed', 'v'): return 'video', path[1]
        if len(path) >= 2 and path[0] == 'channel': return 'channel', path[1]
        if path and path[0].startswith('@'): return 'handle', urllib.parse.unquote(path[0])
        if len(path) >= 2 and path[0] in ('c', 'user'): return 'handle', '@' + path[1]
        raise ValueError('That link is not to a YouTube channel or video.')
    if CHANNEL_ID.match(t): return 'channel', t
    if t.startswith('@'): return 'handle', t
    if VIDEO_ID.match(t): return 'video', t
    if re.match(r'^[\w.-]{3,30}$', t): return 'handle', '@' + t
    raise ValueError('That is not a channel or video: paste its link, or type its id or @handle.')


def seconds(duration):
    """An ISO 8601 duration (`PT1H2M3S`, `P1DT2S`) in seconds; None when it cannot be read (a live stream says `P0D`, which is 0)."""
    m = DURATION.match(duration or '')
    if not m: return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def best_thumbnail(thumbnails):
    """The largest thumbnail's URL, by pixels (names are not trusted to be in order), else the first by name."""
    ts = [t for t in (thumbnails or {}).values() if isinstance(t, dict) and t.get('url')]
    if not ts: return None
    sized = [t for t in ts if t.get('width') and t.get('height')]
    if sized: return max(sized, key=lambda t: t['width'] * t['height'])['url']
    return next((thumbnails[k]['url'] for k in THUMBS if (thumbnails.get(k) or {}).get('url')), ts[0]['url'])


def _int(v):
    try: return int(v)
    except (TypeError, ValueError): return None


def channel_row(item, now):
    """A Data API channel resource as a `channels` row."""
    sn, st = item.get('snippet') or {}, item.get('statistics') or {}
    return dict(id=item['id'], title=sn.get('title') or item['id'], handle=sn.get('customUrl') or None, thumbnail=best_thumbnail(sn.get('thumbnails')),
                description=sn.get('description') or None, published=sn.get('publishedAt'), country=sn.get('country'),
                subscribers=None if st.get('hiddenSubscriberCount') else _int(st.get('subscriberCount')), total_videos=_int(st.get('videoCount')), views=_int(st.get('viewCount')),
                uploads=((item.get('contentDetails') or {}).get('relatedPlaylists') or {}).get('uploads'), added=now)


def video_row(item, now):
    """A Data API video resource as a `videos` row."""
    sn, cd, st = item.get('snippet') or {}, item.get('contentDetails') or {}, item.get('statistics') or {}
    return dict(id=item['id'], channel_id=sn.get('channelId') or '', title=sn.get('title') or item['id'], published=sn.get('publishedAt') or now,
                duration=seconds(cd.get('duration')), thumbnail=best_thumbnail(sn.get('thumbnails')), views=_int(st.get('viewCount')),
                description=sn.get('description') or None, likes=_int(st.get('likeCount')), comments=_int(st.get('commentCount')), definition=cd.get('definition'), added=now)


def channel(kind, value):
    """The channel resource for an id or a handle, or None when YouTube has no such channel."""
    items = call('channels', part=CHANNEL_PARTS, **({'id': value} if kind == 'channel' else {'forHandle': value})).get('items') or []
    return items[0] if items else None


def videos(ids):
    """The video resources for these ids (YouTube leaves out any it does not have, such as private or removed ones), 50 per call."""
    ids, out = list(ids), []
    for i in range(0, len(ids), 50): out += call('videos', part=VIDEO_PARTS, id=','.join(ids[i:i + 50]), maxResults=50).get('items') or []
    return out


def uploads_page(playlist, token=None):
    """One page (up to 50) of a channel's uploads, newest first: (video ids, the next page's token or None at the end)."""
    r = call('playlistItems', part='contentDetails', playlistId=playlist, maxResults=50, **({'pageToken': token} if token else {}))
    return [i['contentDetails']['videoId'] for i in r.get('items') or [] if (i.get('contentDetails') or {}).get('videoId')], r.get('nextPageToken')
