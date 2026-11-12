"""A stand-in for the YouTube Data API v3 (the three calls catalogue.py makes: channels, playlistItems, videos): a real HTTP server on
localhost, answering from what a test puts in it. Use through the `fake_youtube` fixture (tests/conftest.py), which points
TUBES_YOUTUBE_API at it and sets a key:

    fake_youtube.channel('UC...', 'Workshop', handle='@workshop').uploads('UC...', 120)    # 120 videos, newest first

Uploads are paged 50 at a time with opaque page tokens, as YouTube does. `calls` lists each request as (endpoint, params); `quota_left`
counts down one per call and answers 403 quotaExceeded at 0; `referer` makes every call without that Referer header fail as a
referrer-restricted key does; `hold` (a threading.Event) keeps every playlistItems call waiting until it is set, so a test can act while a
sync is part way.

It also stands in for what related.py reads: `featuring(cid, [ids], title=)` gives a channel a multipleChannels section (channelSections,
one quota unit), and `watch_next(video, [(channel id, name, handle), ...])` sets what a video's watch page lists next (the web client's
POST /youtubei/v1/next, in the lockupViewModel shape YouTube sends in 2026; TUBES_YOUTUBE_WEB points at `web`). A video with no list set
answers with an empty column; `web_down` answers every watch page 503."""
import json, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = 'test-key'


def vid(channel_id, n):
    """A stable 11-character video id for a channel's n-th upload (0 is the oldest)."""
    return (channel_id[2:6] + f'{n:07d}')[:11]


class FakeYoutube:
    def __init__(self):
        self.channels, self.videos, self.playlists, self.calls = {}, {}, {}, []
        self.quota_left, self.referer, self.hold, self.lock = None, None, None, threading.Lock()
        self.sections, self.next, self.web_down, self.pages = {}, {}, False, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path); q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                endpoint = u.path.rsplit('/', 1)[-1]
                with fake.lock: fake.calls.append((endpoint, {k: v for k, v in q.items() if k != 'key'}))
                if q.get('key') != KEY: return self.error(400, 'API key not valid. Please pass a valid API key.', 'badRequest')
                if fake.referer and self.headers.get('Referer') != fake.referer: return self.error(403, 'Requests from referer <empty> are blocked.', 'forbidden')
                with fake.lock:
                    if fake.quota_left is not None:
                        if fake.quota_left <= 0: return self.error(403, 'The request cannot be completed because you have exceeded your quota.', 'quotaExceeded')
                        fake.quota_left -= 1
                if endpoint == 'playlistItems' and fake.hold: fake.hold.wait(30)
                handler = dict(channels=fake.answer_channels, playlistItems=fake.answer_playlist, videos=fake.answer_videos, channelSections=fake.answer_sections, search=fake.answer_search).get(endpoint)
                if not handler: return self.error(404, 'Not Found', 'notFound')
                status, body = handler(q)
                self.send_json(status, body)

            def do_POST(self):
                u = urllib.parse.urlparse(self.path)
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                with fake.lock: fake.pages.append(body.get('videoId'))
                if u.path != '/youtubei/v1/next': return self.send_json(404, {})
                if fake.web_down: return self.send_json(503, {})
                self.send_json(200, fake.answer_next(body.get('videoId')))

            def error(self, code, message, reason):
                self.send_json(code, dict(error=dict(code=code, message=message, errors=[dict(message=message, reason=reason)])))

            def send_json(self, code, data):
                b = json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.web = f'http://127.0.0.1:{self.server.server_port}'
        self.api = f'{self.web}/youtube/v3'

    # What YouTube holds.

    def channel(self, cid, title, handle=None, videos=0, topics=None, kids=None):
        self.channels[cid] = dict(kind='youtube#channel', id=cid, snippet=dict(title=title, description=f'About {title}', customUrl=handle, publishedAt='2015-01-01T00:00:00Z', country='GB',
                                                                               thumbnails=dict(default=dict(url=f'https://img.test/{cid}/s.jpg', width=88, height=88), high=dict(url=f'https://img.test/{cid}/l.jpg', width=800, height=800))),
                                  statistics=dict(viewCount='1000', subscriberCount='50', hiddenSubscriberCount=False, videoCount=str(videos)),
                                  contentDetails=dict(relatedPlaylists=dict(uploads='UU' + cid[2:])), status=dict(madeForKids=kids) if kids is not None else {},
                                  topicDetails=dict(topicCategories=[f'https://en.wikipedia.org/wiki/{t}' for t in topics]) if topics else {})
        self.playlists.setdefault('UU' + cid[2:], [])
        if videos: self.uploads(cid, videos)
        return self

    def uploads(self, cid, count, start=None):
        """Give the channel `count` more uploads, each newer than the last (one a day from 2020-01-01); they go to the top of its playlist."""
        pl = self.playlists['UU' + cid[2:]]; first = len(pl) if start is None else start
        for n in range(first, first + count):
            v = vid(cid, n); day = f'{2020 + n // 360}-{(n // 30) % 12 + 1:02d}-{n % 30 + 1:02d}T12:00:00Z'
            self.video(v, cid, f'Upload {n} of {self.channels[cid]["snippet"]["title"]}', day)
            pl.insert(0, v)
        self.channels[cid]['statistics']['videoCount'] = str(len(pl))
        return self

    def video(self, v, cid, title, published, duration='PT4M5S'):
        self.videos[v] = dict(kind='youtube#video', id=v, snippet=dict(title=title, description=f'{title}, described', channelId=cid, publishedAt=published,
                                                                       thumbnails=dict(medium=dict(url=f'https://img.test/{v}/m.jpg', width=320, height=180), maxres=dict(url=f'https://img.test/{v}/x.jpg', width=1280, height=720))),
                              contentDetails=dict(duration=duration, definition='hd'), statistics=dict(viewCount='12', likeCount='3', commentCount='1'))
        return self

    def featuring(self, cid, ids, title='Our friends'):
        self.sections.setdefault(cid, []).append(dict(kind='youtube#channelSection', id=f'{cid}.{len(self.sections.get(cid, []))}', snippet=dict(type='multiplechannels', title=title, channelId=cid), contentDetails=dict(channels=list(ids))))
        return self

    def watch_next(self, video, listed):
        """What `video`'s watch page lists next: (channel id, channel name, handle) per listed video, in order."""
        self.next[video] = list(listed); return self

    # The calls.

    def answer_search(self, q):
        """Channels whose title holds every word of the query, as YouTube's channel search (type=channel) answers; costs 100 units there, one here."""
        words = q.get('q', '').lower().split()
        found = [c for c in self.channels.values() if words and all(w in c['snippet']['title'].lower() for w in words)][:int(q.get('maxResults', 5))]
        return 200, dict(kind='youtube#searchListResponse', items=[dict(kind='youtube#searchResult', id=dict(kind='youtube#channel', channelId=c['id']), snippet=dict(channelId=c['id'], title=c['snippet']['title'], channelTitle=c['snippet']['title'])) for c in found])

    def answer_sections(self, q):
        return 200, dict(kind='youtube#channelSectionListResponse', items=[dict(kind='youtube#channelSection', id=f"{q.get('channelId')}.s", snippet=dict(type='singlePlaylist', title='Popular uploads'))] + self.sections.get(q.get('channelId'), []))

    def answer_next(self, video):
        def lockup(n, cid, name, handle):
            browse = dict(browseId=cid, canonicalBaseUrl=f'/{handle}' if handle else f'/channel/{cid}')
            return dict(lockupViewModel=dict(contentId=f'{video[:6]}{n:05d}', contentType='LOCKUP_CONTENT_TYPE_VIDEO', metadata=dict(lockupMetadataViewModel=dict(
                title=dict(content=f'Listed {n}'),
                image=dict(decoratedAvatarViewModel=dict(rendererContext=dict(commandContext=dict(onTap=dict(innertubeCommand=dict(browseEndpoint=browse))))))),
                metadata=dict(contentMetadataViewModel=dict(metadataRows=[dict(metadataParts=[dict(text=dict(content=name))]), dict(metadataParts=[dict(text=dict(content='1K views'))])])))))
        results = [dict(reelShelfRenderer=dict(title=dict(runs=[dict(text='Shorts')])))] + [lockup(n, *x) for n, x in enumerate(self.next.get(video, []))]
        return dict(contents=dict(twoColumnWatchNextResults=dict(results={}, secondaryResults=dict(secondaryResults=dict(results=results + [dict(continuationItemRenderer={})])))))

    def answer_channels(self, q):
        if 'forHandle' in q:
            h = q['forHandle'].lower(); h = h if h.startswith('@') else '@' + h
            items = [c for c in self.channels.values() if (c['snippet']['customUrl'] or '').lower() == h]
        else: items = [self.channels[i] for i in q.get('id', '').split(',') if i in self.channels]
        return 200, dict(kind='youtube#channelListResponse', items=items, pageInfo=dict(totalResults=len(items)))

    def answer_playlist(self, q):
        pl = self.playlists.get(q.get('playlistId'))
        if pl is None: return 404, dict(error=dict(code=404, message='The playlist identified with the request\'s playlistId parameter cannot be found.', errors=[dict(reason='playlistNotFound')]))
        start = int(q['pageToken'][1:]) if q.get('pageToken') else 0; size = int(q.get('maxResults', 5))
        page = pl[start:start + size]
        body = dict(items=[dict(kind='youtube#playlistItem', contentDetails=dict(videoId=v)) for v in page], pageInfo=dict(totalResults=len(pl)))
        if start + size < len(pl): body['nextPageToken'] = f'P{start + size}'
        return 200, body

    def answer_videos(self, q):
        ids = [i for i in q.get('id', '').split(',') if i]
        assert len(ids) <= 50, 'YouTube takes at most 50 ids a call'
        return 200, dict(items=[self.videos[i] for i in ids if i in self.videos])

    def count(self, endpoint): return sum(1 for e, _ in self.calls if e == endpoint)

    def close(self): self.server.shutdown(); self.server.server_close()
