import json, pathlib, urllib.error
import pytest
from fakes import http_error
from library import d1, seed, video
from tubes import d1import, library, settings


@pytest.fixture
def d1_env(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'acct'); monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'secret-token'); monkeypatch.setenv('TUBES_D1_DATABASE', 'db-id')


def test_credentials_say_what_is_missing(monkeypatch):
    with pytest.raises(d1import.D1Error, match=r'without the D1 database id \(--database\) and CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN'): d1import.credentials()
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a')
    settings.save({}); (pathlib.Path(settings.home()) / 'settings.json').write_text(json.dumps(dict(d1_database='old')))     # an older settings file names it
    with pytest.raises(d1import.D1Error, match='without CLOUDFLARE_API_TOKEN.$'): d1import.credentials()
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 't')
    assert d1import.credentials() == ('a', 't', 'old') and d1import.credentials('given') == ('a', 't', 'given')


def test_query_posts_sql_and_reads_rows(d1_env, fake_urlopen):
    creds = d1import.credentials()
    fake_urlopen.reply(d1([dict(id='x')]))
    assert d1import.query(creds, 'SELECT ? AS id', ('x',)) == [dict(id='x')]
    call = fake_urlopen.calls[0]
    assert call['url'] == 'https://api.cloudflare.com/client/v4/accounts/acct/d1/database/db-id/query' and call['method'] == 'POST'
    assert call['headers']['authorization'] == 'Bearer secret-token' and call['body'] == dict(sql='SELECT ? AS id', params=['x'])
    fake_urlopen.reply(dict(success=True, result=[dict(success=True)]))
    assert d1import.query(creds, 'SELECT 1') == []


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
    with pytest.raises(d1import.D1Error, match=message): d1import.query(d1import.credentials(), 'SELECT 1')


def test_run_merges_d1_into_the_library(fake_d1, monkeypatch):
    monkeypatch.setattr(d1import, 'PAGE', 2)
    seed(videos=[video('zzzzzzzzzzz')])                                             # already here and not in D1: kept
    (fake_d1.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop', custom_url='@workshop', best_thumbnail_url='https://img.test/w.jpg', upload_playlist_id='UUaaaaaaaaaaaaaaaaaaaaaa',
                     last_sync_at='2026-01-20T10:00:00Z', video_count=3, created_at='2025-12-01T00:00:00Z')
            .channel('UCcccccccccccccccccccccc', 'Half done', upload_playlist_id='UUcccccccccccccccccccccc', last_sync_at='2026-01-20T10:00:00Z', last_sync_token='CDIQAA')
            .video('aaaaaaaaaaa', 'UCaaaaaaaaaaaaaaaaaaaaaa', 'Building a shelf', '2026-01-03T00:00:00Z', 9, description='How', like_count=4, definition='hd')
            .video('bbbbbbbbbbb', 'UCaaaaaaaaaaaaaaaaaaaaaa', 'Sanding', '2026-01-02T00:00:00Z')
            .video('eeeeeeeeeee', 'UCcccccccccccccccccccccc', 'Part one', '2026-01-01T00:00:00Z'))
    assert d1import.run(now='2026-11-09T12:00:00+00:00') == dict(channels=2, videos=3)
    w, h = library.channel('UCaaaaaaaaaaaaaaaaaaaaaa'), library.channel('UCcccccccccccccccccccccc')
    assert (w['title'], w['handle'], w['thumbnail'], w['complete'], w['follow'], w['total_videos'], w['added'], w['videos']) == ('Workshop', '@workshop', 'https://img.test/w.jpg', True, True, 3, '2025-12-01T00:00:00Z', 3)
    assert (h['complete'], h['resumable'], h['added']) == (False, True, '2026-11-09T12:00:00+00:00')
    assert library.channel('UCbbbbbbbbbbbbbbbbbbbbbb')['follow'] is True and library.video('zzzzzzzzzzz') is not None
    assert library.video('aaaaaaaaaaa')['duration'] == 9 and library.status()['videos'] == 4
    assert d1import.run()['videos'] == 3 and library.status()['videos'] == 4                      # again: the same, merged
