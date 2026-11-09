import os, threading
import pytest
import uvicorn
from fastapi.testclient import TestClient
from tubes import cache, fetcher, library, oslib, ytdlp
from tubes.server import app as server_app
from tubes.server.app import create_app
from library import CHANNELS, seed
from test_cache import write_playlist


@pytest.fixture
def client():
    return TestClient(create_app())


def test_landing_page_and_built_static_index(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, 'STATIC', str(tmp_path / 'no_static'))
    c = TestClient(create_app())
    assert '<h1>Tubes</h1>' in c.get('/').text and 'npm run build' in c.get('/').text
    assert c.get('/api/health').json() == dict(ok=True, version='0.1.0')

    static = tmp_path / 'static'; (static / 'assets').mkdir(parents=True)
    (static / 'index.html').write_text('<h1>built react app</h1>', encoding='utf8')
    (static / 'assets' / 'main.js').write_text('console.log(1)', encoding='utf8')
    monkeypatch.setattr(server_app, 'STATIC', str(static))
    c2 = TestClient(create_app())
    assert c2.get('/').text == '<base href="./"><h1>built react app</h1>'
    assert 'console.log(1)' in c2.get('/assets/main.js').text


def test_every_page_path_serves_the_app_with_a_base_back_to_its_root(tmp_path, monkeypatch):
    static = tmp_path / 'static'; static.mkdir()
    (static / 'index.html').write_text('<html><head><title>t</title></head></html>', encoding='utf8')
    (static / 'favicon.svg').write_text('<svg/>', encoding='utf8')
    monkeypatch.setattr(server_app, 'STATIC', str(static))
    c = TestClient(create_app())
    assert c.get('/settings').text == '<html><head><base href="./"><title>t</title></head></html>'
    assert '<base href="../">' in c.get('/watch/abc').text
    assert c.get('/favicon.svg').text == '<svg/>'
    for escape in ('..%5Capp.py', '..%2Fapp.py', 'C:%5Cwindows%5Cwin.ini', '..'):
        assert c.get('/' + escape).text.startswith('<html><head><base')
    assert server_app.static_file('..\\app.py') is None and server_app.static_file('C:\\x') is None and server_app.static_file('') is None and server_app.static_file('missing.txt') is None
    assert c.get('/api/nope').status_code == 404 and c.get('/api/nope').json() == dict(detail='no such endpoint')


def test_system_and_settings(client, monkeypatch):
    monkeypatch.setattr(ytdlp, 'version', lambda: '2026.10.26'); monkeypatch.setattr(fetcher, 'ffmpeg_version', lambda: 'ffmpeg version 7.1')
    s = client.get('/api/system').json()
    assert (s['ytdlp'], s['ffmpeg'], s['can_fetch'], s['fetching']) == ('2026.10.26', 'ffmpeg version 7.1', oslib.CAN_PASS_FDS, [])
    assert s['disk']['total'] > 0 and s['cache']['limit'] == 10**12 and s['cache_dir'].endswith('cache') and s['library'] == dict(synced=None, channels=0, videos=0, configured=False)
    assert client.put('/api/settings', json=dict(max_height=720, player_client='')).json()['max_height'] == 720
    assert client.get('/api/settings').json()['player_client'] == ''
    assert client.put('/api/settings', json=dict(max_height=None)).json()['max_height'] == 1080
    assert client.put('/api/settings', json=dict(cache_dir='relative')).json() == dict(detail='cache_dir must be an absolute path')
    assert client.put('/api/settings', json=dict(colour='red')).json() == dict(detail="unknown setting 'colour'")


def test_library_channels_and_videos(client, monkeypatch):
    seed()
    assert client.get('/api/library').json() == dict(synced='2026-11-09T12:00:00+00:00', channels=2, videos=4, configured=False)
    assert [c['title'] for c in client.get('/api/channels').json()] == ['night sky', 'Workshop']
    assert client.get(f"/api/channels/{CHANNELS[0]['id']}").json()['videos'] == 2 and client.get('/api/channels/nope').status_code == 404
    page = client.get('/api/videos', params=dict(limit=3)).json()
    assert [v['id'] for v in page['videos']] == ['aaaaaaaaaaa', 'ccccccccccc', 'bbbbbbbbbbb'] and page['has_more'] is True
    assert client.get('/api/videos', params=dict(after=library.cursor(page['videos'][-1]))).json()['videos'][0]['id'] == 'ddddddddddd'
    assert [v['id'] for v in client.get('/api/videos', params=dict(q='shelf', channel=CHANNELS[0]['id'])).json()['videos']] == ['aaaaaaaaaaa', 'bbbbbbbbbbb']
    assert client.get('/api/videos', params=dict(limit=0)).status_code == 422
    assert len(client.get('/api/videos/shuffle', params=dict(count=2)).json()) == 2
    v = client.get('/api/videos/ccccccccccc').json()
    assert (v['title'], v['channel'], v['plays'], v['last_played']) == ('Stars in winter', 'night sky', 0, None)
    assert client.get('/api/videos/zzz').status_code == 404

    r = client.post('/api/library/sync')
    assert r.status_code == 503 and 'without YOUTUBE_API_KEY' in r.json()['detail']
    r = client.post('/api/library', json=dict(input='@workshop'))
    assert r.status_code == 503 and 'without YOUTUBE_API_KEY' in r.json()['detail']


def test_manage_the_library(client, fake_youtube):
    A = 'UCaaaaaaaaaaaaaaaaaaaaaa'
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=55).channel('UCbbbbbbbbbbbbbbbbbbbbbb', 'Night sky', videos=2)
    job = client.app.state.sync; fake_youtube.hold = threading.Event()
    assert client.get('/api/library/sync').json()['running'] is False
    r = client.post('/api/library', json=dict(input='https://www.youtube.com/@workshop')).json()
    assert r['kind'] == 'channel' and r['channel']['title'] == 'Workshop' and r['sync']['running'] is True and r['sync']['total'] == 1
    assert client.post('/api/library/sync', json=dict(channels=[A])).status_code == 409      # one at a time
    r = client.post('/api/library', json=dict(input='UCbbbbbbbbbbbbbbbbbbbbbb')).json()     # added while the first runs: synced by the next one
    assert r['sync']['running'] is True and r['sync']['total'] == 1
    fake_youtube.hold.set(); job.wait(30)
    s = client.get('/api/library/sync').json()
    assert (s['running'], s['done'], s['added'], s['errors']) == (False, 1, 55, [])
    assert client.post('/api/library/sync').json()['total'] == 2; job.wait(30)
    assert client.get('/api/library/sync').json()['added'] == 2 and client.get('/api/library').json()['synced'] is not None
    c = client.get(f'/api/channels/{A}').json()
    assert (c['videos'], c['complete'], c['follow'], c['total_videos']) == (55, True, True, 55)
    v = client.post('/api/library', json=dict(input='https://youtu.be/aaaa0000003')).json()
    assert v['kind'] == 'video' and v['video']['channel'] == 'Workshop' and 'sync' not in v
    assert client.post('/api/library', json=dict(input='two words')).status_code == 400
    assert client.post('/api/library', json=dict(input='@nobody')).status_code == 404

    fake_youtube.hold.clear()
    r = client.post(f'/api/channels/{A}/restart').json()
    assert r['videos'] == 55 and r['sync']['running'] is True
    assert client.post(f'/api/channels/{A}/restart').json()['sync']['running'] is True       # one is running: the restart waits for the next
    fake_youtube.hold.set(); job.wait(30)
    assert client.get(f'/api/channels/{A}').json()['videos'] == 55
    assert client.delete(f'/api/channels/{A}').json() == dict(channel=A, videos=55)
    assert client.delete(f'/api/channels/{A}').status_code == 404 and client.post(f'/api/channels/{A}/restart').status_code == 404
    fake_youtube.quota_left = 0
    assert client.post('/api/library', json=dict(input='@workshop')).status_code == 502


def test_restart_without_a_key_only_forgets(client):
    seed()
    r = client.post(f"/api/channels/{CHANNELS[0]['id']}/restart").json()
    assert r['videos'] == 2 and r['sync']['running'] is False


def test_play_stream_and_media(client, monkeypatch):
    seed()
    started = []
    def fake_start(vid, title, channel):
        started.append((vid, title, channel)); cache.begin(vid, cache.stamp(), title, channel); write_playlist(vid, 1, False); return cache.status(vid)
    monkeypatch.setattr(fetcher, 'start', fake_start)
    st = client.post('/api/videos/aaaaaaaaaaa/play').json()
    assert (st['state'], st['segments'], st['playable'], st['plays']) == ('fetching', 1, True, 1) and started == [('aaaaaaaaaaa', 'Building a 50% shelf', 'Workshop')]
    assert client.get('/api/videos/aaaaaaaaaaa').json()['plays'] == 1
    assert client.post('/api/videos/zzzzzzzzzzz/play').json() == dict(detail='There is no video zzzzzzzzzzz in the library.')
    assert client.get('/api/videos/zzzzzzzzzzz/stream').json()['state'] == 'none' 

    r = client.get('/api/media/aaaaaaaaaaa/index.m3u8')
    assert r.status_code == 200 and r.headers['content-type'] == 'application/vnd.apple.mpegurl' and r.headers['cache-control'] == 'no-store'
    seg = client.get('/api/media/aaaaaaaaaaa/seg_00000.m4s')
    assert seg.headers['content-type'] == 'video/iso.segment' and seg.headers['cache-control'] == 'private, max-age=86400' and len(seg.content) == 1000
    write_playlist('aaaaaaaaaaa', 2, True)
    assert client.get('/api/media/aaaaaaaaaaa/index.m3u8').headers['cache-control'] == 'private, max-age=86400'
    assert client.get('/api/videos/aaaaaaaaaaa/stream').json()['complete'] is True
    for bad in ('fetch.log', 'init.mp4', '..%2Fx'):
        assert client.get(f'/api/media/aaaaaaaaaaa/{bad}').status_code == 404

    def refuse(*a): raise fetcher.FetchError('Fetching needs Linux or macOS.')
    monkeypatch.setattr(fetcher, 'start', refuse)
    assert client.post('/api/videos/bbbbbbbbbbb/play').json() == dict(detail='Fetching needs Linux or macOS.')


def test_cache_endpoints(client, monkeypatch):
    cache.begin('aaaaaaaaaaa', cache.stamp(), 'A title'); write_playlist('aaaaaaaaaaa', 2, True); cache.finish('aaaaaaaaaaa', cache.stamp())
    c = client.get('/api/cache').json()
    assert c['count'] == 1 and c['items'][0]['video_id'] == 'aaaaaaaaaaa' and c['items'][0]['protected'] == 'not played yet' and c['items'][0]['title'] == 'A title'
    assert client.put('/api/cache/aaaaaaaaaaa', json=dict(pinned=True)).json()['pinned'] in (1, True)
    assert client.put('/api/cache/zzz', json=dict(pinned=True)).status_code == 404
    assert client.post('/api/cache/evict', json=dict(dry_run=True)).json() == dict(evicted=[], freed=0, dry_run=True)
    cancelled = []; monkeypatch.setattr(fetcher, 'cancel', lambda ids: cancelled.extend(ids))
    freed = client.delete('/api/cache/aaaaaaaaaaa').json()
    assert freed['video_id'] == 'aaaaaaaaaaa' and freed['freed'] > 2000 and cancelled == ['aaaaaaaaaaa']
    assert client.delete('/api/cache/aaaaaaaaaaa').status_code == 404


def test_server_main(monkeypatch, capsys):
    runs = []
    monkeypatch.setattr(uvicorn, 'run', lambda app, host, port, log_level: runs.append((host, port, log_level)))
    server_app.main([])
    assert runs == [('127.0.0.1', 8367, 'warning')] and 'cache folder' in capsys.readouterr().out
