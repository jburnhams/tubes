"""The HTTP API end to end over real files, with a stand-in YouTube Data API (tests/utils/fake_youtube.py) and tests/utils/fake_ytdlp.py
standing in for yt-dlp: add a channel and let its sync run, browse it, play while it fetches, read the playlist and segments as a player
would, and see it in the cache."""
import re, shutil, time
import pytest
from tubes import oslib

needs_ffmpeg = pytest.mark.skipif(not shutil.which('ffmpeg') or not oslib.CAN_PASS_FDS, reason='fetching needs ffmpeg on PATH and Linux or macOS')


def wait_for(fn, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        v = fn()
        if v: return v
        time.sleep(0.1)
    raise AssertionError('timed out')


V = 'aaaa0000000'


def library(client, fake_youtube):
    fake_youtube.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop', handle='@workshop', videos=1)
    assert client.post('/api/library', json=dict(input='@workshop')).json()['sync']['running'] is True
    assert wait_for(lambda: not (s := client.get('/api/library/sync').json())['running'] and s)['added'] == 1


def test_add_sync_browse_and_settings(client, fake_ytdlp, fake_youtube):
    assert client.get('/api/library').json() == dict(synced=None, channels=0, videos=0, hidden=0, live=0, configured=True)
    library(client, fake_youtube)
    assert [c['title'] for c in client.get('/api/channels').json()] == ['Workshop']
    assert client.get('/api/videos', params=dict(q='upload workshop')).json()['videos'][0]['channel'] == 'Workshop'
    assert client.post('/api/videos/bbbbbbbbbbb/play').status_code == 404
    assert client.put('/api/settings', json=dict(max_height=720)).json()['max_height'] == 720
    assert client.put('/api/settings', json=dict(data_dir='relative')).status_code == 400
    s = client.get('/api/system').json()
    assert s['ytdlp'] == '2026.10.26' and s['library']['videos'] == 1
    fake_youtube.close()
    client.post('/api/library/sync')
    assert 'YouTube could not be reached' in wait_for(lambda: not (j := client.get('/api/library/sync').json())['running'] and j)['errors'][0]['error']


@needs_ffmpeg
def test_play_streams_while_it_fetches_then_plays_from_the_cache(client, fake_ytdlp, fake_youtube):
    library(client, fake_youtube); fake_ytdlp.seconds(20)
    first = client.post(f'/api/videos/{V}/play').json()
    assert first['state'] == 'fetching'
    playable = wait_for(lambda: (s := client.get(f'/api/videos/{V}/stream').json())['playable'] and s)
    assert playable['segments'] >= 1

    done = wait_for(lambda: (s := client.get(f'/api/videos/{V}/stream').json())['state'] == 'ready' and s)
    assert done == dict(state='ready', segments=5, seconds=20.0, complete=True, playable=True, error=None, formats='180p H.264 + AAC', plays=1, last_played=done['last_played'])
    playlist = client.get(f'/api/media/{V}/index.m3u8').text
    assert '#EXT-X-MAP:URI="init.mp4"' in playlist and '#EXT-X-ENDLIST' in playlist
    for name in ['init.mp4'] + re.findall(r'^seg_\d{5}\.m4s$', playlist, re.M):
        r = client.get(f'/api/media/{V}/{name}')
        assert r.status_code == 200 and len(r.content) > 100
    assert client.post(f'/api/videos/{V}/play').json()['state'] == 'ready'          # the second play is from the cache
    c = client.get('/api/cache').json()
    assert c['items'][0]['plays'] == 2 and c['items'][0]['protected'] == 'played in the last day' and c['items'][0]['title'] == 'Upload 0 of Workshop'
    assert client.get(f'/api/videos/{V}').json()['cache_state'] == 'ready'


@needs_ffmpeg
def test_a_failed_fetch_says_why(client, fake_ytdlp, fake_youtube):
    library(client, fake_youtube); fake_ytdlp.fail('--no-playlist')
    client.post(f'/api/videos/{V}/play')
    failed = wait_for(lambda: (s := client.get(f'/api/videos/{V}/stream').json())['state'] == 'failed' and s)
    assert failed['error'] == '[youtube] fake: Video unavailable'


@pytest.fixture
def episode_media(tmp_path):
    """A 6-second muxed H.264 + AAC MPEG-TS HLS stream, as iPlayer serves: `index.m3u8` and its `.ts` segments."""
    import subprocess
    out = tmp_path / 'bbc'; out.mkdir()
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=25:duration=6', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-g', '25', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-f', 'hls', '-hls_time', '2', '-hls_list_size', '0',
                    '-hls_segment_type', 'mpegts', '-hls_segment_filename', str(out / 'seg%d.ts'), str(out / 'index.m3u8')], check=True)
    return str(out)


@needs_ffmpeg
def test_follow_an_iplayer_programme_and_play_an_episode(client, fake_iplayer, episode_media):
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=2); fake_iplayer.media_dir = episode_media
    r = client.post('/api/library', json=dict(input='https://www.bbc.co.uk/iplayer/episodes/b0000001/harbour-lights')).json()
    assert r['kind'] == 'channel' and r['channel']['platform'] == 'iplayer'
    assert wait_for(lambda: not (s := client.get('/api/library/sync').json())['running'] and s)['added'] == 2
    vs = client.get('/api/videos', params=dict(channel='b0000001')).json()['videos']
    assert [(v['title'], v['series'], v['episode'], v['channel']) for v in vs] == [('Chapter 2', 'Series 1', 2, 'Harbour Lights'), ('Chapter 1', 'Series 1', 1, 'Harbour Lights')]
    e = vs[0]['id']
    assert client.post(f'/api/videos/{e}/play').json()['state'] == 'fetching'
    done = wait_for(lambda: (s := client.get(f'/api/videos/{e}/stream').json())['state'] in ('ready', 'failed') and s)
    assert (done['state'], done['error'], done['formats'], done['complete']) == ('ready', None, '1080p50 H.264 + AAC', True) and done['seconds'] >= 5
    playlist = client.get(f'/api/media/{e}/index.m3u8').text
    assert '#EXT-X-MAP:URI="init.mp4"' in playlist and '#EXT-X-ENDLIST' in playlist
    assert any('-video=12000000-seg0.ts' in c for c in fake_iplayer.calls)                   # the 1080p50 variant was the one read


def test_an_iplayer_episode_outside_the_uk_fails_with_why(client, fake_iplayer, fake_ytdlp):
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=1)
    e = client.post('/api/library', json=dict(input='https://www.bbc.co.uk/iplayer/episode/m0000001')).json()['video']['id']
    fake_iplayer.region = 'geolocation'
    client.post(f'/api/videos/{e}/play')
    done = wait_for(lambda: (s := client.get(f'/api/videos/{e}/stream').json())['state'] == 'failed' and s)
    assert done['error'] == 'iPlayer only plays in the UK, and this server is not seen as in the UK.'
    fake_iplayer.close()
    assert client.post('/api/library', json=dict(input='https://www.bbc.co.uk/iplayer/episodes/b0000002')).status_code == 502


def test_a_pasted_list_becomes_suggestions_to_follow(client, fake_youtube, fake_iplayer):
    fake_youtube.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop', handle='@workshop', videos=1)
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=1)
    r = client.post('/api/suggestions/paste', json=dict(text='- https://www.youtube.com/@workshop\n- Harbour Lights\n- Nothing At All'))
    assert r.status_code == 200
    assert [(f['platform'], f['channel_id']) for f in r.json()['found']] == [('youtube', 'UCaaaaaaaaaaaaaaaaaaaaaa'), ('iplayer', 'b0000001')] and r.json()['problems'][0]['input'] == 'Nothing At All'
    items = client.get('/api/suggestions', params=dict(pasted='true')).json()['items']
    assert [(i['title'], i['link']) for i in items] == [('Workshop', 'https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa'), ('Harbour Lights', 'https://www.bbc.co.uk/iplayer/episodes/b0000001')]
    assert client.post('/api/library', json=dict(input=items[1]['link'])).json()['kind'] == 'channel'     # Follow adds its link
    assert [i['title'] for i in client.get('/api/suggestions', params=dict(pasted='true')).json()['items']] == ['Workshop']
    assert client.get('/api/suggestions/summary').json()['pasted'] == 1
    assert client.post('/api/suggestions/paste', json=dict(text='  ')).status_code == 400
