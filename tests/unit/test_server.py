import os, threading
import pytest
import uvicorn
from fastapi.testclient import TestClient
from tubes import cache, fetcher, library, oslib, ytdlp
from tubes.server import app as server_app
from tubes.server.app import create_app
from library import CHANNELS, VIDEOS, seed
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
    assert s['disk']['total'] > 0 and s['cache']['limit'] == 10**12 and s['cache_dir'].endswith('cache') and s['library'] == dict(synced=None, channels=0, videos=0, hidden=0, live=0, filtered=0, configured=False)
    assert client.put('/api/settings', json=dict(max_height=720, player_client='')).json()['max_height'] == 720
    assert client.get('/api/settings').json()['player_client'] == ''
    assert client.put('/api/settings', json=dict(max_height=None)).json()['max_height'] == 1080
    assert client.put('/api/settings', json=dict(cache_dir='relative')).json() == dict(detail='cache_dir must be an absolute path')
    assert client.put('/api/settings', json=dict(colour='red')).json() == dict(detail="unknown setting 'colour'")
    assert client.get('/api/library/shown').json() == dict(min_seconds=None, max_seconds=None, streams='current', region=None, languages=[], unknown_language='show', captions='any', filtered=0, language_counts=[])
    assert client.put('/api/library/shown', json=dict(min_seconds=120, streams='all')).json() == dict(min_seconds=120, max_seconds=None, streams='all', region=None, languages=[], unknown_language='show', captions='any', filtered=0, language_counts=[])
    r = client.put('/api/library/shown', json=dict(max_seconds=60)); assert r.status_code == 400 and r.json() == dict(detail='The shortest length must not be longer than the longest.')
    assert client.get('/api/library/shown').json()['max_seconds'] is None and client.get('/api/library').json()['filtered'] == 0


def test_shown_filters_narrow_the_watching_side(client):
    seed()
    r = client.put('/api/library/shown', json=dict(max_seconds=300)).json()                                 # every seeded video is 10 minutes
    assert r == dict(min_seconds=None, max_seconds=300, streams='current', region=None, languages=[], unknown_language='show', captions='any', filtered=4, language_counts=[dict(code=None, videos=4)]) and client.get('/api/videos').json()['videos'] == []
    assert client.get('/api/videos/shuffle').json() == [] and client.get('/api/library').json()['filtered'] == 4
    assert client.get(f"/api/videos/{VIDEOS[0]['id']}").status_code == 200                                     # a link still opens
    assert len(client.put('/api/library/shown', json=dict(max_seconds=None)).json() and client.get('/api/videos').json()['videos']) == 4


def test_quota_counts_what_the_server_asked_youtube(client, fake_youtube):
    q = client.get('/api/quota').json()
    assert (q['used'], q['limit'], q['remaining'], q['refused'], q['configured'], len(q['days'])) == (0, 10_000, 10_000, None, True, 30)
    fake_youtube.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop', handle='@workshop')
    client.post('/api/library', json=dict(input='@workshop')); client.app.state.sync.wait(10)
    q = client.get('/api/quota').json()
    assert q['used'] == len(fake_youtube.calls) > 1
    assert {p['purpose'] for p in q['today']['purposes']} == {'add', 'sync'} and q['remaining'] == 10_000 - q['used']


def test_library_channels_and_videos(client, monkeypatch):
    seed()
    assert client.get('/api/library').json() == dict(synced='2026-11-09T12:00:00+00:00', channels=2, videos=4, hidden=0, live=0, filtered=0, configured=False)
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
    r = client.post('/api/library', json=dict(input='UCbbbbbbbbbbbbbbbbbbbbbb')).json()     # added while the first runs: the running sync takes it next
    assert r['sync']['running'] is True and r['sync']['total'] == 2
    assert client.post('/api/library', json=dict(input='UCbbbbbbbbbbbbbbbbbbbbbb')).json()['sync']['total'] == 2   # queued once
    fake_youtube.hold.set(); job.wait(30)
    s = client.get('/api/library/sync').json()
    assert (s['running'], s['done'], s['added'], s['errors']) == (False, 2, 57, [])
    assert client.post('/api/library/sync').json()['total'] == 2; job.wait(30)
    assert client.get('/api/library/sync').json()['added'] == 0 and client.get('/api/library').json()['synced'] is not None
    c = client.get(f'/api/channels/{A}').json()
    assert (c['videos'], c['complete'], c['follow'], c['total_videos']) == (55, True, True, 55)
    v = client.post('/api/library', json=dict(input='https://youtu.be/aaaa0000003')).json()
    assert v['kind'] == 'video' and v['video']['channel'] == 'Workshop' and 'sync' not in v
    assert client.post('/api/library', json=dict(input='two words')).status_code == 400
    assert client.post('/api/library', json=dict(input='@nobody')).status_code == 404

    fake_youtube.hold.clear()
    r = client.post(f'/api/channels/{A}/restart').json()
    assert r['videos'] == 55 and r['sync']['running'] is True
    assert client.post(f'/api/channels/{A}/restart').json()['sync']['total'] == 2            # one is running: the restart follows it
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
    assert seg.headers['content-type'] == 'video/iso.segment' and seg.headers['cache-control'] == 'no-store' and len(seg.content) == 1000   # a retry may rewrite it
    write_playlist('aaaaaaaaaaa', 2, True)          # an attempt that ended (short or not) while the copy is still fetching: a retry may follow
    r = client.get('/api/media/aaaaaaaaaaa/index.m3u8')
    assert r.headers['cache-control'] == 'no-store' and 'seg_00000.m4s' in r.text and 'seg_00001.m4s' not in r.text and '#EXT-X-ENDLIST' not in r.text
    assert client.get('/api/videos/aaaaaaaaaaa/stream').json()['complete'] is False
    cache.finish('aaaaaaaaaaa', cache.stamp())
    r = client.get('/api/media/aaaaaaaaaaa/index.m3u8')
    assert r.headers['cache-control'] == 'private, max-age=86400' and '#EXT-X-ENDLIST' in r.text
    assert client.get('/api/media/aaaaaaaaaaa/seg_00000.m4s').headers['cache-control'] == 'private, max-age=86400'
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


def test_the_watching_side_reports_missing_videos(client, fake_youtube, monkeypatch):
    from fake_youtube import vid
    from tubes import catalogue
    A = 'UCaaaaaaaaaaaaaaaaaaaaaa'
    fake_youtube.channel(A, 'Workshop', videos=2); catalogue.add(A); catalogue.sync_channel(A)
    del fake_youtube.videos[vid(A, 0)]
    r = client.post('/api/videos/check', json=dict(ids=[vid(A, 0), vid(A, 1)]))
    assert r.status_code == 200 and r.json() == dict(checked=2, gone=1, back=0, hidden=[vid(A, 0)])
    assert [v['id'] for v in client.get('/api/videos').json()['videos']] == [vid(A, 1)] and client.get(f'/api/videos/{vid(A, 0)}').json()['gone']
    assert client.post('/api/videos/check', json=dict(ids=[])).status_code == 422 and client.post('/api/videos/check', json=dict(ids=['x'] * 51)).status_code == 422
    fake_youtube.quota_left = 0; catalogue.mark_gone(vid(A, 1))
    with catalogue.db.connect() as con: con.execute('UPDATE videos SET checked = NULL')
    assert client.post('/api/videos/check', json=dict(ids=[vid(A, 1)])).status_code == 502
    monkeypatch.delenv('YOUTUBE_API_KEY')
    r = client.post('/api/videos/check', json=dict(ids=[vid(A, 1)]))
    assert r.status_code == 503 and 'YOUTUBE_API_KEY' in r.json()['detail']


def test_a_past_stream_whose_recording_went_is_dropped_as_it_is_read(client, fake_youtube):
    from fake_youtube import vid
    from tubes import catalogue, db
    A = 'UCaaaaaaaaaaaaaaaaaaaaaa'
    fake_youtube.channel(A, 'Workshop', videos=3)
    for n in (0, 1, 2): fake_youtube.videos[vid(A, n)]['liveStreamingDetails'] = dict(actualEndTime='t')
    catalogue.add(A); catalogue.sync_channel(A)
    assert len(client.get('/api/videos').json()['videos']) == 3                                    # past streams are shown (asked about once, never checked)
    for n in (0, 1, 2): del fake_youtube.videos[vid(A, n)]
    assert len(client.get('/api/videos').json()['videos']) == 3                                    # asked about within the day: not again
    with db.connect() as con: con.execute("UPDATE videos SET checked = '2026-01-01T00:00:00'")
    assert [v['id'] for v in client.get('/api/videos/shuffle?count=1').json()] == []                      # the one picked had gone
    assert client.get('/api/videos').json()['videos'] == [] and client.get(f'/api/videos/{vid(A, 0)}').json()['gone']
    with db.connect() as con: con.execute("UPDATE videos SET checked = '2026-01-01T00:00:00', gone = NULL WHERE id = ?", (vid(A, 1),))
    assert client.get(f'/api/videos/{vid(A, 1)}').json()['gone']                                     # the Watch page's read finds it gone too


def test_a_page_emptied_by_the_recheck_reads_on(client, fake_youtube):
    from fake_youtube import vid
    from tubes import catalogue, db
    A = 'UCaaaaaaaaaaaaaaaaaaaaaa'
    fake_youtube.channel(A, 'Workshop', videos=4)
    for n in range(4): fake_youtube.videos[vid(A, n)]['liveStreamingDetails'] = dict(actualEndTime='t')
    catalogue.add(A); catalogue.sync_channel(A)
    order = [v['id'] for v in client.get('/api/videos').json()['videos']]
    for i in order[:2]: del fake_youtube.videos[i]                                                  # the two newest went
    with db.connect() as con: con.execute("UPDATE videos SET checked = '2026-01-01T00:00:00'")
    r = client.get('/api/videos', params=dict(limit=2)).json()
    assert [v['id'] for v in r['videos']] == order[2:] and r['has_more'] is False                 # not an empty page with more behind it
    for i in order[2:]: del fake_youtube.videos[i]
    with db.connect() as con: con.execute("UPDATE videos SET checked = '2026-01-01T00:00:00'")
    assert client.get('/api/videos', params=dict(limit=2)).json() == dict(videos=[], has_more=False)


def test_suggestions(client, fake_youtube, monkeypatch):
    from takeout import as_json, chan, watch
    from fake_youtube import vid
    a, b = chan('a'), chan('b')
    fake_youtube.channel(a, 'Channel a', topics=['Music'], videos=3).channel(b, 'Channel b')
    ws = [watch(f'2026-01-0{d}T10:0{m}:00Z', vid(c, d % 3), f'Video {d}', c, f'Channel {c[2]}') for d in range(1, 7) for m, c in enumerate((a, b))]
    assert client.get('/api/suggestions/summary').json()['open'] == 0
    assert client.post('/api/suggestions/import', json=dict(source='one', text='nope')).status_code == 400
    r = client.post('/api/suggestions/import', json=dict(source='one', text=as_json(ws))).json()
    assert (r['watches'], r['refresh']['groups'], r['refresh']['looked_up']) == (12, 1, 2)
    s = client.get('/api/suggestions/summary').json()
    assert (s['open'], s['topics'], [g['channels'] for g in s['groups']]) == (2, [dict(name='Music', channels=1)], [2])
    assert [i['channel_id'] for i in client.get('/api/suggestions', params=dict(topic='Music')).json()['items']] == [a]
    assert client.get('/api/suggestions', params=dict(group='x')).status_code == 404
    gid = s['groups'][0]['id']
    assert client.put(f'/api/suggestions/groups/{gid}', json=dict(name='Both')).json()['name'] == 'Both'
    assert client.put('/api/suggestions/groups/99', json=dict(name='x')).status_code == 404
    assert client.put(f'/api/suggestions/{b}', json=dict(dismissed=True)).json()['dismissed'] is not None
    assert client.get('/api/suggestions', params=dict(dismissed=True)).json()['total'] == 1
    assert client.put('/api/suggestions/UCnone', json=dict(dismissed=True)).status_code == 404
    assert client.post(f'/api/suggestions/{a}/videos').json() == dict(added=3, already=0, missing=0)
    assert client.get(f'/api/channels/{a}').json()['follow'] is False
    assert client.post('/api/suggestions/UCnone/videos').status_code == 404
    assert client.post('/api/suggestions/refresh').json()['summary']['open'] == 1
    assert client.delete('/api/suggestions/sources/one').json()['refresh']['channels'] == 0
    assert client.delete('/api/suggestions/sources/one').status_code == 404
    monkeypatch.delenv('YOUTUBE_API_KEY')
    assert client.post(f'/api/suggestions/{a}/videos').status_code == 503


def test_history_stats_and_refresh_from_a_history_database(client, tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / 'kept.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE kept (account TEXT, at TEXT, video_id TEXT, title TEXT, channel_id TEXT, channel_name TEXT)')
        con.executemany('INSERT INTO kept VALUES (?, ?, ?, ?, ?, ?)', [('main', f'2026-01-0{d}T10:00:00Z', f'v000000000{d}', f'V{d}', 'UC' + 'a' * 22, 'Channel a') for d in range(1, 6)])
    assert client.get('/api/suggestions/summary').json()['database'] is False
    monkeypatch.setenv('TUBES_HISTORY_URL', f'sqlite:///{path}'); monkeypatch.setenv('TUBES_HISTORY_TABLE', 'kept')
    r = client.post('/api/suggestions/refresh').json()
    assert (r['channels'], r['summary']['database'], [s['source'] for s in r['summary']['sources']]) == (1, True, ['main'])
    h = client.get('/api/history', params=dict(start='2026-01-02T00:00:00+00:00', end='2026-01-04T00:00:00+00:00', source='main')).json()
    assert (h['watches'], h['by'], [p['period'] for p in h['periods']], h['channels_top'][0]['watches'], h['sources'][0]['watches'], h['configured']) == (2, 'day', ['2026-01-02', '2026-01-03'], 2, 5, False)
    monkeypatch.setenv('TUBES_HISTORY_TABLE', 'nothere')
    assert client.post('/api/suggestions/refresh').status_code == 502
    monkeypatch.setenv('TUBES_HISTORY_TABLE', 'bad name')
    assert client.post('/api/suggestions/refresh').status_code == 400


def test_iplayer_programmes_sync_without_a_youtube_key(client, fake_iplayer):
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=2)
    r = client.post('/api/library', json=dict(input='https://www.bbc.co.uk/iplayer/episodes/b0000001')).json()
    assert r['kind'] == 'channel' and r['sync']['total'] == 1
    client.app.state.sync.wait(10)
    assert client.get('/api/library/sync').json()['added'] == 2
    assert client.post('/api/library/sync').status_code == 200
    client.app.state.sync.wait(10)
    assert client.post('/api/channels/b0000001/restart').json()['sync']['total'] == 1
    client.app.state.sync.wait(10)
    assert client.post('/api/library/sync', json=dict(channels=['UCaaaaaaaaaaaaaaaaaaaaaa'])).status_code == 503


def test_channel_overview(client):
    assert client.get('/api/channels/UCnone/overview').status_code == 404


def test_segments_endpoint(client, monkeypatch):
    from library import seed
    from tubes import segments
    seed()
    monkeypatch.setattr(segments, 'sponsorblock', lambda vid: [dict(category='sponsor', start=1.0, end=2.0, action='skip', votes=1)])
    r = client.get('/api/videos/aaaaaaaaaaa/segments').json()
    assert r['segments'] == [dict(category='sponsor', start=1.0, end=2.0, action='skip')] and len(r['categories']) == 9
    assert client.get('/api/videos/zzzzzzzzzzz/segments').status_code == 404
    client.put('/api/settings', json=dict(skip_intro='auto'))
    assert next(k for k in client.get('/api/skipping').json() if k['id'] == 'intro')['mode'] == 'auto'


def test_offered_videos_are_prefetched_and_system_says_how_it_goes(monkeypatch):
    seed(); app = create_app(); c = TestClient(app)
    shown = [v['id'] for v in c.get('/api/videos/shuffle', params=dict(count=2)).json()]
    assert list(reversed(app.state.prefetch.asked)) == list(reversed(shown))
    c.get('/api/videos', params=dict(channel=CHANNELS[1]['id']))
    assert list(app.state.prefetch.asked)[-2:] == ['ccccccccccc', 'ddddddddddd']
    before = list(app.state.prefetch.asked); c.get('/api/videos'); c.get('/api/videos', params=dict(q='shelf'))
    assert list(app.state.prefetch.asked) == before                                             # Home is prefetched anyway; a search is not
    assert app.state.prefetch.thread is None                                                     # only `tubes serve` starts it
    assert c.get('/api/system').json()['prefetch'] == dict(enabled=True, seconds=20.0, today=0, per_day=150, paused_until=None, last=None)


def test_a_fetch_from_a_prefix_serves_the_prefixes_init_segment(client):
    from test_cache import keep
    keep(); cache.resume('aaaaaaaaaaa', cache.stamp())
    d = cache.folder('aaaaaaaaaaa')
    with open(os.path.join(d, 'init.mp4'), 'wb') as f: f.write(b'')                              # ffmpeg writing it again
    assert client.get('/api/media/aaaaaaaaaaa/init.mp4').content == b'i'
    assert client.get('/api/media/aaaaaaaaaaa/prefix.json').status_code == 404
    assert client.get('/api/media/aaaaaaaaaaa/index.m3u8').text.count('seg_') == 3
