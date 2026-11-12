"""A stand-in for BBC iPlayer's two services (iplayer.py): ibl (programmes, their episodes paged, one episode) and the mediaselector, plus
the HLS playlists it points at, and ibl's `new-search` (fuzzy: any word of the query in a programme's or episode's title). A real HTTP server on localhost, answering from what a test puts in it. Use through the `fake_iplayer`
fixture (tests/conftest.py), which points TUBES_IPLAYER_API and TUBES_MEDIASELECTOR at it:

    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=3)       # three episodes, newest first, Series 1: 1-3

Each episode has one version (`v` + its id's last 7 characters) whose master playlist lists 396p25, 540p50 and 720p50 variants; `fhd`
(default True) says whether the 1080p50 variant answers too. `region` set to 'geolocation' makes the mediaselector refuse as outside the UK.
`media_dir` (a folder holding `index.m3u8` and its `.ts` segments) is served as every variant's content, so a fetch can run for real;
without it a variant answers a playlist of one segment that does not exist. `calls` lists each path asked for."""
import json, os, re, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VARIANTS = ((704, 396, 25, 1570000), (960, 540, 50, 2812000), (1280, 720, 50, 5070000))


def ep_id(pid, n):
    """A stable episode id for a programme's n-th episode: `m`, three of the programme's characters, the number (iPlayer ids have no vowels)."""
    return 'm' + pid[1:4] + f'{n:04d}'


class FakeIplayer:
    def __init__(self):
        self.programmes, self.episodes, self.order, self.calls = {}, {}, {}, []
        self.region, self.fhd, self.media_dir, self.lock = None, True, None, threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path); q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                with fake.lock: fake.calls.append(u.path)
                status, ctype, body = fake.answer(u.path, q, f'http://127.0.0.1:{fake.server.server_port}')
                b = body if isinstance(body, bytes) else (json.dumps(body) if ctype == 'application/json' else body).encode()
                self.send_response(status); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{self.server.server_port}'
        self.ibl, self.ms = base + '/ibl/v1', base + '/ms'

    # What iPlayer holds.

    def programme(self, pid, title, episodes=0, network=('bbc_one', 'BBC One')):
        self.programmes[pid] = dict(id=pid, type='programme_large', title=title, synopses=dict(small=f'About {title}', medium=f'All about {title}'),
                                    images=dict(type='image', standard=f'https://img.test/ic/{{recipe}}/{pid}.jpg'), categories=['drama'], count=0,
                                    master_brand=dict(id=network[0], titles=dict(large=network[1])), tleo_type='brand')
        self.order.setdefault(pid, [])
        for n in range(1, episodes + 1): self.episode(pid, n)
        return self

    def episode(self, pid, n, subtitle=None, expires='2099-01-01T00:00:00Z', hd=True, versions=None, number=True):
        """Add episode n of a programme (n=1 the oldest; each is a day newer); it goes to the top of the programme's list."""
        eid = ep_id(pid, n); title = self.programmes[pid]['title'] if pid in self.programmes else 'One-off'
        version = dict(id='v' + eid[1:], kind='original', hd=hd, duration=dict(value='PT6.0S'), first_broadcast_date_time=f'2026-01-{n:02d}T19:30:00.000Z',
                       availability=dict(start=f'2026-01-{n:02d}T20:00:00Z', end=expires))
        self.episodes[eid] = dict(id=eid, type='episode', title=title, subtitle=subtitle or f'Series 1: {n}. Chapter {n}', original_title=f'Chapter {n}',
                                  parent_position=n if number else None, tleo_id=pid, tleo_type='brand' if pid in self.programmes else 'episode',
                                  master_brand=dict(id='bbc_one', titles=dict(large='BBC One')), synopses=dict(small=f'Chapter {n} in short', medium=f'Chapter {n}, told'),
                                  images=dict(type='image', standard=f'https://img.test/ic/{{recipe}}/{eid}.jpg'), versions=versions if versions is not None else [version])
        if pid in self.programmes:
            self.order[pid].insert(0, eid); self.programmes[pid]['count'] = len(self.order[pid])
        return eid

    def one_off(self, eid, title):
        """A film: its own top-level programme, so it has no programme to follow; kept under its network (BBC Two)."""
        self.episodes[eid] = dict(id=eid, type='episode', title=title, subtitle='', original_title=title, tleo_id=eid, tleo_type='episode',
                                  master_brand=dict(id='bbc_two', titles=dict(large='BBC Two')), synopses=dict(small=f'{title} in short'),
                                  images=dict(type='image', standard=f'https://img.test/ic/{{recipe}}/{eid}.jpg'),
                                  versions=[dict(id='v' + eid[1:], kind='original', hd=False, duration=dict(value='PT1H30M'), availability=dict(end='2099-01-01T00:00:00Z'))])
        return eid

    def drop(self, eid):
        """iPlayer stops listing (and offering) an episode."""
        self.episodes.pop(eid, None)
        for pl in self.order.values():
            if eid in pl: pl.remove(eid)

    # The answers.

    def answer(self, path, q, base):
        if path == '/ibl/v1/new-search':                                     # fuzzy, as iPlayer's is: any word of the query in a title
            words = [w for w in q.get('q', '').lower().split() if w]
            hit = lambda t: any(w in t.lower() for w in words)
            progs = [dict(p, type='programme') for p in self.programmes.values() if hit(p['title'])]
            eps = [e for e in self.episodes.values() if hit(e['title'])]
            return 200, 'application/json', dict(version='1.0', new_search=dict(query=q.get('q'), results=progs + eps))
        m = re.match(r'^/ibl/v1/programmes/([^/]+)/episodes$', path)
        if m:
            ids = self.order.get(m[1], []); size, page = int(q.get('per_page', 20)), int(q.get('page', 1))
            els = [self.episodes[i] for i in ids[(page - 1) * size:page * size]]
            return 200, 'application/json', dict(programme_episodes=dict(count=len(ids), page=page, per_page=size, elements=els))
        m = re.match(r'^/ibl/v1/programmes/([^/]+)$', path)
        if m: return 200, 'application/json', dict(programmes=[self.programmes[m[1]]] if m[1] in self.programmes else [])
        m = re.match(r'^/ibl/v1/episodes/([^/]+)$', path)
        if m: return 200, 'application/json', dict(episodes=[self.episodes[m[1]]] if m[1] in self.episodes else [])
        m = re.match(r'^/ms/mediaset/([^/]+)/vpid/([^/]+)/format/json$', path)
        if m:
            if self.region: return 403, 'application/json', dict(result=self.region)
            known = any(v['id'] == m[2] for e in self.episodes.values() for v in e.get('versions') or [])
            if not known: return 404, 'application/json', dict(result='selectionunavailable')
            href = f'{base}/hls/{m[2]}/master.m3u8?at=token'
            return 200, 'application/json', dict(media=[dict(kind='video', connection=[dict(transferFormat='dash', href=f'{base}/dash/{m[2]}.mpd'), dict(transferFormat='hls', href=href)]),
                                                        dict(kind='captions', connection=[dict(transferFormat='plain', href=f'{base}/cc/{m[2]}.xml')])])
        m = re.match(r'^/hls/([^/]+)/master\.m3u8$', path)
        if m:
            lines = ['#EXTM3U']
            for w, h, fps, bw in VARIANTS: lines += [f'#EXT-X-STREAM-INF:BANDWIDTH={bw + 128000},CODECS="mp4a.40.2,avc1.640020",RESOLUTION={w}x{h},FRAME-RATE={fps}', f'{m[1]}-audio=128000-video={bw}.m3u8']
            return 200, 'application/vnd.apple.mpegurl', '\n'.join(lines) + '\n'
        m = re.match(r'^/hls/([^/]+)/[^/]*-video=(\d+)\.m3u8$', path)
        if m:
            if int(m[2]) == 12000000 and not self.fhd: return 403, 'text/html', '<html>Forbidden</html>'
            if self.media_dir:
                with open(os.path.join(self.media_dir, 'index.m3u8'), encoding='utf8') as f: text = f.read()
                return 200, 'application/vnd.apple.mpegurl', text.replace('seg', f'{m[1]}-video={m[2]}-seg')
            return 200, 'application/vnd.apple.mpegurl', f'#EXTM3U\n#EXTINF:8,\n{m[1]}-video={m[2]}-1.ts\n#EXT-X-ENDLIST\n'
        m = re.match(r'^/hls/[^/]+/[^/]*-video=\d+-(seg\d+\.ts)$', path)
        if m and self.media_dir:
            with open(os.path.join(self.media_dir, m[1]), 'rb') as f: return 200, 'video/mp2t', f.read()
        return 404, 'text/html', '<html>Not found</html>'

    def close(self): self.server.shutdown(); self.server.server_close()
