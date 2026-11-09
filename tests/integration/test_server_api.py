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
    assert client.get('/api/library').json() == dict(synced=None, channels=0, videos=0, hidden=0, configured=True)
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
