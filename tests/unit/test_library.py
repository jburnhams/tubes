import urllib.error
import pytest
from fakes import http_error
from library import CHANNELS, VIDEOS, d1, seed, video
from tubes import cache, library, settings


@pytest.fixture
def d1_env(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'acct'); monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'secret-token'); settings.save(dict(d1_database='db-id'))


def test_credentials_say_what_is_missing(monkeypatch):
    with pytest.raises(library.LibraryError, match='without the d1_database setting and CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN'): library.credentials()
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a'); monkeypatch.setenv('TUBES_D1_DATABASE', 'd')
    with pytest.raises(library.LibraryError, match='without CLOUDFLARE_API_TOKEN.$'): library.credentials()
    assert library.status()['configured'] is False


def test_query_posts_sql_and_reads_rows(d1_env, fake_urlopen):
    fake_urlopen.reply(d1([dict(id='x')]))
    assert library.query('SELECT ? AS id', ('x',)) == [dict(id='x')]
    call = fake_urlopen.calls[0]
    assert call['url'] == 'https://api.cloudflare.com/client/v4/accounts/acct/d1/database/db-id/query' and call['method'] == 'POST'
    assert call['headers']['authorization'] == 'Bearer secret-token' and call['body'] == dict(sql='SELECT ? AS id', params=['x'])
    fake_urlopen.reply(dict(success=True, result=[dict(success=True)]))
    assert library.query('SELECT 1') == []


@pytest.mark.parametrize('reply, message', [
    (http_error(403, dict(errors=[dict(message='Authentication error')])), r'D1 refused the query \(403: Authentication error\)'),
    (http_error(500, b'not json'), r'D1 refused the query \(500\)'),
    (urllib.error.URLError('no route'), 'D1 could not be reached: no route'),
    (b'<html>', 'D1 did not answer with JSON'),
    (d1([], success=False, errors=['no such table: youtube_videos']), 'D1 said the query failed: no such table: youtube_videos'),
    (dict(success=False), 'D1 said the query failed: no reason given'),
])
def test_query_failures(d1_env, fake_urlopen, reply, message):
    fake_urlopen.reply(reply)
    with pytest.raises(library.LibraryError, match=message): library.query('SELECT 1')


def test_sync_pages_through_d1_and_replaces_the_copy(d1_env, fake_urlopen, monkeypatch):
    monkeypatch.setattr(library, 'PAGE', 2)
    seed(videos=[video('zzzzzzzzzzz')])                                                      # gone upstream: a sync removes it
    fake_urlopen.reply(d1(CHANNELS), d1(VIDEOS[:2]), d1(VIDEOS[2:]), d1([]))
    assert library.sync('2026-11-09T13:00:00+00:00') == dict(channels=2, videos=4, synced='2026-11-09T13:00:00+00:00')
    assert [c['body']['params'] for c in fake_urlopen.calls[1:]] == [['', 2], ['bbbbbbbbbbb', 2], ['ddddddddddd', 2]]
    assert library.status() == dict(synced='2026-11-09T13:00:00+00:00', channels=2, videos=4, configured=True)
    assert library.video('zzzzzzzzzzz') is None

    fake_urlopen.reply(d1(CHANNELS[:1]), urllib.error.URLError('down'))                     # a failure part way changes nothing
    with pytest.raises(library.LibraryError): library.sync()
    assert library.status()['videos'] == 4
    fake_urlopen.reply(d1(CHANNELS[:1]), d1(VIDEOS[:1]))
    assert library.sync()['videos'] == 1 and library.status()['synced'] != '2026-11-09T13:00:00+00:00'


def test_status_before_any_sync():
    assert library.status() == dict(synced=None, channels=0, videos=0, configured=False)


def test_channels_by_title_with_counts():
    seed(); seed(channels=[dict(CHANNELS[0], id='UCempty', title='Alpha')], videos=[], synced=None)
    got = library.channels()
    assert [(c['title'], c['videos'], c['latest']) for c in got] == [('Alpha', 0, None), ('night sky', 2, '2026-01-02T00:00:00Z'), ('Workshop', 2, '2026-01-03T00:00:00Z')]
    assert library.channel('UCbbbbbbbbbbbbbbbbbbbbbb')['handle'] is None and library.channel('nope') is None


def test_videos_newest_first_in_pages_by_cursor():
    seed()
    first = library.videos(limit=2)
    assert [v['id'] for v in first['videos']] == ['aaaaaaaaaaa', 'ccccccccccc'] and first['has_more'] is True    # same day: the higher id first
    assert first['videos'][0]['channel'] == 'Workshop' and first['videos'][0]['cache_state'] is None
    rest = library.videos(after=library.cursor(first['videos'][-1]), limit=2)
    assert [v['id'] for v in rest['videos']] == ['bbbbbbbbbbb', 'ddddddddddd'] and rest['has_more'] is False
    assert [v['id'] for v in library.videos(channel_id='UCbbbbbbbbbbbbbbbbbbbbbb')['videos']] == ['ccccccccccc', 'ddddddddddd']


def test_search_matches_words_in_any_order_and_case():
    seed()
    assert [v['id'] for v in library.videos(search='SHELF')['videos']] == ['aaaaaaaaaaa', 'bbbbbbbbbbb']
    assert [v['id'] for v in library.videos(search='up moon')['videos']] == ['ddddddddddd']
    assert library.videos(search='50%')['videos'][0]['id'] == 'aaaaaaaaaaa'
    assert library.videos(search='5_%')['videos'] == []                                       # wildcards are literal
    assert library.videos(search='  ')['has_more'] is False and len(library.videos(search='  ')['videos']) == 4


def test_shuffle_and_one_video_with_its_copy():
    seed()
    assert sorted(v['id'] for v in library.shuffle()) == sorted(v['id'] for v in VIDEOS)
    assert len(library.shuffle(count=1)) == 1
    assert {v['channel_id'] for v in library.shuffle(channel_id=CHANNELS[1]['id'])} == {CHANNELS[1]['id']}
    cache.begin('ccccccccccc', cache.stamp())
    v = library.video('ccccccccccc')
    assert (v['title'], v['channel'], v['cache_state'], v['cache_bytes']) == ('Stars in winter', 'night sky', 'fetching', 0)
