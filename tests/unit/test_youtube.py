import urllib.error
import pytest
from fakes import http_error
from tubes import youtube


@pytest.mark.parametrize('text, want', [
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10', ('video', 'dQw4w9WgXcQ')),
    ('youtu.be/dQw4w9WgXcQ', ('video', 'dQw4w9WgXcQ')),
    ('https://m.youtube.com/shorts/dQw4w9WgXcQ', ('video', 'dQw4w9WgXcQ')),
    ('https://www.youtube.com/live/dQw4w9WgXcQ?si=x', ('video', 'dQw4w9WgXcQ')),
    ('https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa/videos', ('channel', 'UCaaaaaaaaaaaaaaaaaaaaaa')),
    ('https://www.youtube.com/@Some.Maker/featured', ('handle', '@Some.Maker')),
    ('www.youtube.com/c/oldname', ('handle', '@oldname')),
    ('https://youtube.com/user/oldername', ('handle', '@oldername')),
    ('UCaaaaaaaaaaaaaaaaaaaaaa', ('channel', 'UCaaaaaaaaaaaaaaaaaaaaaa')),
    (' @workshop ', ('handle', '@workshop')),
    ('dQw4w9WgXcQ', ('video', 'dQw4w9WgXcQ')),
    ('workshop', ('handle', '@workshop')),
])
def test_parse_reads_links_ids_and_handles(text, want):
    assert youtube.parse(text) == want


@pytest.mark.parametrize('text, message', [('', 'Enter a channel or video'), ('https://example.com/watch', 'not to a YouTube channel or video'), ('two words', 'paste its link')])
def test_parse_says_what_it_wanted(text, message):
    with pytest.raises(ValueError, match=message): youtube.parse(text)


def test_seconds_and_best_thumbnail():
    assert [youtube.seconds(d) for d in ('PT4M5S', 'PT1H', 'P1DT2S', 'P0D', 'PT', 'bad', None)] == [245, 3600, 86402, 0, 0, None, None]
    sized = dict(default=dict(url='s', width=120, height=90), high=dict(url='h', width=480, height=360), medium=dict(url='m', width=320, height=180))
    assert youtube.best_thumbnail(sized) == 'h'
    assert youtube.best_thumbnail(dict(default=dict(url='d'), high=dict(url='h'))) == 'h'                   # no sizes: by name
    assert youtube.best_thumbnail(dict(odd=dict(url='o'))) == 'o' and youtube.best_thumbnail(None) is None and youtube.best_thumbnail(dict(x=dict())) is None


def test_rows_from_resources():
    ch = dict(id='UCx', snippet=dict(title='T', customUrl='@t', publishedAt='2015', thumbnails={}), statistics=dict(hiddenSubscriberCount=True, subscriberCount='9', videoCount='3', viewCount='x'), contentDetails={})
    row = youtube.channel_row(ch, 'now')
    assert (row['subscribers'], row['total_videos'], row['views'], row['uploads'], row['description'], row['added']) == (None, 3, None, None, None, 'now')
    v = youtube.video_row(dict(id='abcdefghijk', snippet={}, contentDetails={}, statistics={}), 'now')
    assert (v['title'], v['published'], v['duration'], v['channel_id']) == ('abcdefghijk', 'now', None, '')


def test_call_sends_the_key_and_referer(monkeypatch, fake_urlopen):
    with pytest.raises(youtube.YoutubeError, match='without YOUTUBE_API_KEY'): youtube.call('channels', id='x')
    assert youtube.configured() is False
    monkeypatch.setenv('YOUTUBE_API_KEY', 'k&y'); monkeypatch.setenv('YOUTUBE_API_REFERER', 'https://site.test/')
    fake_urlopen.reply(dict(items=[]))
    assert youtube.call('channels', id='UCx', part='id') == dict(items=[])
    call = fake_urlopen.calls[0]
    assert call['url'] == 'https://www.googleapis.com/youtube/v3/channels?id=UCx&part=id&key=k%26y' and call['headers']['referer'] == 'https://site.test/'


@pytest.mark.parametrize('reply, message', [
    (http_error(403, dict(error=dict(message='Requests from referer <empty> are blocked.', errors=[dict(reason='forbidden')]))), r'YouTube refused the request \(403: Requests from referer'),
    (http_error(403, dict(error=dict(message='quota', errors=[dict(reason='quotaExceeded')]))), r'\(403: the key has used its quota for today'),
    (http_error(500, b'<html>'), r'YouTube refused the request \(500\)\.'),
    (urllib.error.URLError('no route'), 'YouTube could not be reached: no route'),
    (b'not json', 'YouTube did not answer with JSON'),
])
def test_call_failures(monkeypatch, fake_urlopen, reply, message):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'k'); fake_urlopen.reply(reply)
    with pytest.raises(youtube.YoutubeError, match=message): youtube.call('videos', id='x')


def test_the_three_calls_against_the_stand_in(fake_youtube):
    fake_youtube.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop', handle='@workshop', videos=120)
    assert youtube.channel('handle', '@Workshop')['id'] == 'UCaaaaaaaaaaaaaaaaaaaaaa' and youtube.channel('channel', 'UCzzzzzzzzzzzzzzzzzzzzzz') is None
    ids, token = youtube.uploads_page('UUaaaaaaaaaaaaaaaaaaaaaa')
    assert len(ids) == 50 and token == 'P50' and ids[0] == 'aaaa0000119'
    assert youtube.uploads_page('UUaaaaaaaaaaaaaaaaaaaaaa', 'P100') == (['aaaa%07d' % n for n in range(19, -1, -1)], None)
    got = youtube.videos(ids + ids[:10] + ['missingxxxx'])                       # 61 ids: two calls; YouTube leaves out what it lacks
    assert len(got) == 60 and fake_youtube.count('videos') == 2
    fake_youtube.referer = 'https://site.test/'
    with pytest.raises(youtube.YoutubeError, match='403'): youtube.channel('channel', 'UCaaaaaaaaaaaaaaaaaaaaaa')
