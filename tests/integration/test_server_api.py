"""The HTTP API end to end over real files, with a stand-in D1 (tests/utils/fake_d1.py) and tests/utils/fake_ytdlp.py standing in for yt-dlp:
sync the library, browse it, play while it fetches, read the playlist and segments as a player would, and see it in the cache."""
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


def library(client, fake_d1):
    fake_d1.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop').video('aaaaaaaaaaa', 'UCaaaaaaaaaaaaaaaaaaaaaa', 'Building a shelf', '2026-01-03T00:00:00Z')
    assert client.post('/api/library/sync').json()['videos'] == 1


def test_sync_browse_and_settings(client, fake_ytdlp, fake_d1):
    assert client.get('/api/library').json() == dict(synced=None, channels=0, videos=0, configured=True)
    library(client, fake_d1)
    assert [c['title'] for c in client.get('/api/channels').json()] == ['Workshop']
    assert client.get('/api/videos', params=dict(q='shelf')).json()['videos'][0]['channel'] == 'Workshop'
    assert client.post('/api/videos/bbbbbbbbbbb/play').status_code == 404
    assert client.put('/api/settings', json=dict(max_height=720)).json()['max_height'] == 720
    assert client.put('/api/settings', json=dict(data_dir='relative')).status_code == 400
    s = client.get('/api/system').json()
    assert s['ytdlp'] == '2026.10.26' and s['library']['videos'] == 1
    fake_d1.close()
    assert 'D1 could not be reached' in client.post('/api/library/sync').json()['detail']


@needs_ffmpeg
def test_play_streams_while_it_fetches_then_plays_from_the_cache(client, fake_ytdlp, fake_d1):
    library(client, fake_d1); fake_ytdlp.seconds(20)
    first = client.post('/api/videos/aaaaaaaaaaa/play').json()
    assert first['state'] == 'fetching'
    playable = wait_for(lambda: (s := client.get('/api/videos/aaaaaaaaaaa/stream').json())['playable'] and s)
    assert playable['segments'] >= 1

    done = wait_for(lambda: (s := client.get('/api/videos/aaaaaaaaaaa/stream').json())['state'] == 'ready' and s)
    assert done == dict(state='ready', segments=5, seconds=20.0, complete=True, playable=True, error=None, formats='180p H.264 + AAC', plays=1, last_played=done['last_played'])
    playlist = client.get('/api/media/aaaaaaaaaaa/index.m3u8').text
    assert '#EXT-X-MAP:URI="init.mp4"' in playlist and '#EXT-X-ENDLIST' in playlist
    for name in ['init.mp4'] + re.findall(r'^seg_\d{5}\.m4s$', playlist, re.M):
        r = client.get(f'/api/media/aaaaaaaaaaa/{name}')
        assert r.status_code == 200 and len(r.content) > 100
    assert client.post('/api/videos/aaaaaaaaaaa/play').json()['state'] == 'ready'          # the second play is from the cache
    c = client.get('/api/cache').json()
    assert c['items'][0]['plays'] == 2 and c['items'][0]['protected'] == 'played in the last day' and c['items'][0]['title'] == 'Building a shelf'
    assert client.get('/api/videos/aaaaaaaaaaa').json()['cache_state'] == 'ready'


@needs_ffmpeg
def test_a_failed_fetch_says_why(client, fake_ytdlp, fake_d1):
    library(client, fake_d1); fake_ytdlp.fail('--no-playlist')
    client.post('/api/videos/aaaaaaaaaaa/play')
    failed = wait_for(lambda: (s := client.get('/api/videos/aaaaaaaaaaa/stream').json())['state'] == 'failed' and s)
    assert failed['error'] == '[youtube] fake: Video unavailable'
