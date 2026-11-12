"""segments.py: SponsorBlock for YouTube videos (a stand-in on localhost), iPlayer's own intro and credits points (tests/utils/fake_iplayer.py),
the cache of both, and the skip settings."""
import hashlib, json, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from library import seed
from tubes import catalogue, db, segments, settings

V = 'aaaaaaaaaaa'                      # a library video (tests/utils/library.py)
NOW = '2026-11-12T06:00:00+00:00'


@pytest.fixture
def sponsorblock(monkeypatch):
    """SponsorBlock's skipSegments-by-hash-prefix on localhost: `.videos[id] = [segment dicts]`, `.status` to fail, `.calls` the prefixes asked."""
    class Fake:
        videos, status, calls, body = {}, 200, [], None
    fake = Fake()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path); prefix = u.path.rsplit('/', 1)[-1]
            q = urllib.parse.parse_qs(u.query)
            fake.calls.append((prefix, q.get('categories', [''])[0]))
            actions = json.loads(q.get('actionTypes', ['["skip"]'])[0])                   # as SponsorBlock: skip only unless asked
            hits = [dict(videoID=v, hash=hashlib.sha256(v.encode()).hexdigest(), segments=[x for x in s if x['actionType'] in actions or x['actionType'] in ('poi', 'chapter')])
                    for v, s in fake.videos.items() if hashlib.sha256(v.encode()).hexdigest().startswith(prefix)]
            status = fake.status if fake.status != 200 else (200 if hits else 404)
            b = fake.body if fake.body is not None else (json.dumps(hits) if status == 200 else 'Not Found').encode()
            self.send_response(status); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv('TUBES_SPONSORBLOCK', f'http://127.0.0.1:{server.server_port}')
    yield fake
    server.shutdown(); server.server_close()


def seg(cat, start, end, action='skip', votes=3): return dict(category=cat, actionType=action, segment=[start, end], votes=votes, UUID='x')


def test_sponsorblock_is_asked_by_hash_prefix_and_keeps_skips_and_mutes(sponsorblock):
    sponsorblock.videos[V] = [seg('sponsor', 10, 40), seg('music_offtopic', 0, 5, 'mute'), seg('poi_highlight', 50, 50, 'poi'), seg('chapter', 0, 60, 'chapter'), seg('intro', 9, 3)]
    sponsorblock.videos['bbbbbbbbbbb'] = [seg('sponsor', 1, 2)]
    got = segments.sponsorblock(V)
    assert got == [dict(category='sponsor', start=10.0, end=40.0, action='skip', votes=3), dict(category='music_offtopic', start=0.0, end=5.0, action='mute', votes=3)]
    prefix, cats = sponsorblock.calls[0]
    assert prefix == hashlib.sha256(V.encode()).hexdigest()[:4] and json.loads(cats) == list(settings.SKIP_DEFAULTS)
    assert segments.sponsorblock('zzzzzzzzzzz') == []                                         # 404: none known
    sponsorblock.status = 500
    with pytest.raises(segments.SegmentError, match=r'refused the request \(500\)'): segments.sponsorblock(V)
    sponsorblock.status, sponsorblock.body = 200, b'<html>'
    sponsorblock.videos['zzzz'] = []
    with pytest.raises(segments.SegmentError, match='did not answer with JSON'): segments.sponsorblock(V)


def test_sponsorblock_unreachable(monkeypatch):
    monkeypatch.setenv('TUBES_SPONSORBLOCK', 'http://127.0.0.1:9')
    with pytest.raises(segments.SegmentError, match='could not be reached'): segments.sponsorblock(V)


def test_iplayer_intro_recap_and_credits(fake_iplayer):
    fake_iplayer.programme('b0000001', 'Harbour Lights')
    v = dict(id='v0000001', kind='original', hd=True, duration=dict(value='PT29M0S'), credits_start=1698, availability=dict(end='2099-01-01T00:00:00Z'),
             interactions=[dict(type='skip', subtype='intro', interaction_points=dict(show_from=1, skip_to=24)), dict(type='skip', subtype='recap', interaction_points=dict(show_from=30, skip_to=90)),
                           dict(type='skip', subtype='something-new', interaction_points=dict(show_from=1, skip_to=2)), dict(type='skip', subtype='intro', interaction_points=dict(show_from=5))])
    e = fake_iplayer.episode('b0000001', 1, versions=[v])
    assert segments.iplayer_points(e) == [dict(category='intro', start=1.0, end=24.0, action='skip', votes=None), dict(category='preview', start=30.0, end=90.0, action='skip', votes=None),
                                          dict(category='outro', start=1698.0, end=1740.0, action='skip', votes=None)]
    bare = fake_iplayer.episode('b0000001', 2, versions=[dict(v, id='v0000002', interactions=[], credits_start=None)])
    assert segments.iplayer_points(bare) == [] and segments.iplayer_points('m0000099') == []
    fake_iplayer.close()
    with pytest.raises(segments.SegmentError, match='could not be reached'): segments.iplayer_points(e)


def test_a_video_s_list_is_cached_and_asked_again_when_due(sponsorblock, fake_iplayer):
    seed(); sponsorblock.videos[V] = [seg('sponsor', 10, 40), seg('sponsor', 10, 40)]
    r = segments.for_video(V, NOW)
    assert r['segments'] == [dict(category='sponsor', start=10.0, end=40.0, action='skip')] and r['error'] is None
    assert [c['id'] for c in r['categories']] == list(settings.SKIP_DEFAULTS) and r['categories'][0] == dict(id='sponsor', label='Sponsor', detail='A paid promotion or sponsor read.', mode='auto')
    sponsorblock.videos[V] = [seg('intro', 0, 8)]
    assert segments.for_video(V, '2026-11-12T12:00:00+00:00')['segments'][0]['category'] == 'sponsor'      # cached for a day
    assert segments.for_video(V, '2026-11-13T07:00:00+00:00')['segments'][0]['category'] == 'intro'
    sponsorblock.status = 503
    r = segments.for_video(V, '2026-11-15T07:00:00+00:00')
    assert r['error'] == 'SponsorBlock refused the request (503).' and r['segments'][0]['category'] == 'intro'      # said, and the cached list still given
    sponsorblock.status = 200
    assert segments.for_video(V, '2026-11-15T07:30:00+00:00')['error'] == 'SponsorBlock refused the request (503).'   # asked again after an hour, not sooner
    assert segments.for_video(V, '2026-11-15T08:30:00+00:00')['error'] is None
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=1); catalogue.add('https://www.bbc.co.uk/iplayer/episode/m0000001')
    with db.connect() as con: assert con.execute("SELECT platform FROM videos WHERE id = 'm0000001'").fetchone()[0] == 'iplayer'
    assert segments.for_video('m0000001', NOW)['segments'] == []                               # asked iPlayer, not SponsorBlock
    assert all(p != hashlib.sha256(b'm0000001').hexdigest()[:4] for p, _ in sponsorblock.calls)


def test_skip_settings():
    assert settings.get('skip_sponsor') == 'auto' and settings.get('skip_filler') == 'off'
    assert settings.save(dict(skip_intro='AUTO'))['skip_intro'] == 'auto'
    with pytest.raises(settings.SettingError, match='skip_intro must be off, ask or auto'): settings.save(dict(skip_intro='sometimes'))
