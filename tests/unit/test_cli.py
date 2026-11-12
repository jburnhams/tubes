import importlib, json
import pytest
from tubes import cache, catalogue, cli, fetcher, oslib, quota, settings, youtube, ytdlp
from library import seed
from test_cache import write_playlist


@pytest.fixture(autouse=True)
def tools(monkeypatch):
    monkeypatch.setattr(ytdlp, 'version', lambda: '2026.10.26'); monkeypatch.setattr(fetcher, 'ffmpeg_version', lambda: 'ffmpeg version 7.1')
    monkeypatch.setattr(oslib, 'CAN_PASS_FDS', True)


def test_doctor(capsys, monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'k'); monkeypatch.setenv('YOUTUBE_API_REFERER', 'https://site.test/')
    assert cli.main(['doctor']) == 0
    out = capsys.readouterr().out
    assert 'ok       yt-dlp 2026.10.26' in out and 'ok       ffmpeg ffmpeg version 7.1' in out and 'limit 1000 GB' in out and 'ok       library: YOUTUBE_API_KEY set (sent with a Referer)' in out
    assert 'library    0 channel(s), 0 video(s), synced never' in out

    real_import = importlib.import_module
    monkeypatch.setattr(importlib, 'import_module', lambda name: (_ for _ in ()).throw(ImportError(name)) if name == 'uvicorn' else real_import(name))
    monkeypatch.setattr(ytdlp, 'version', lambda: None); monkeypatch.setattr(fetcher, 'ffmpeg_version', lambda: None); monkeypatch.setattr(oslib, 'CAN_PASS_FDS', False)
    monkeypatch.delenv('YOUTUBE_API_KEY')
    assert cli.main(['doctor']) == 1
    out = capsys.readouterr().out
    assert 'MISSING  uvicorn' in out and 'MISSING  yt-dlp' in out and 'MISSING  ffmpeg' in out and 'MISSING  fetching needs Linux or macOS' in out and 'MISSING  library: YOUTUBE_API_KEY is not in the environment' in out


def test_add_sync_channels_and_remove(capsys, fake_youtube, monkeypatch):
    A = 'UCaaaaaaaaaaaaaaaaaaaaaa'
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=60).channel('UCbbbbbbbbbbbbbbbbbbbbbb', 'Night sky', videos=1)
    assert cli.main(['channels']) == 0 and 'no channels yet' in capsys.readouterr().out
    assert cli.main(['add', '@workshop']) == 0
    out = capsys.readouterr().out
    assert f'following {A}: Workshop' in out and '60 new  complete' in out and '1 channel(s) synced, 60 new video(s)' in out
    assert cli.main(['add', 'UCbbbbbbbbbbbbbbbbbbbbbb', '--no-sync']) == 0 and 'following' in capsys.readouterr().out
    assert cli.main(['add', 'UCbbbbbbbbbbbbbbbbbbbbbb', '--no-sync', '--json']) == 0 and json.loads(capsys.readouterr().out)['kind'] == 'channel'
    assert cli.main(['channels']) == 0
    out = capsys.readouterr().out
    assert 'UCbbbbbbbbbbbbbbbbbbbbbb        0 videos  backfilling  Night sky' in out and f'{A}       60 videos  complete     Workshop' in out
    assert cli.main(['sync', '--json']) == 0 and json.loads(capsys.readouterr().out)['added'] == 1
    fake_youtube.uploads(A, 1, start=100)
    assert cli.main(['add', 'aaaa0000100']) == 0 and 'added video aaaa0000100: Upload 100 of Workshop' in capsys.readouterr().out
    with pytest.raises(SystemExit, match='YouTube has no channel @nobody'): cli.main(['add', '@nobody'])
    assert cli.main(['channels', '--json']) == 0 and len(json.loads(capsys.readouterr().out)) == 2

    del fake_youtube.channels['UCbbbbbbbbbbbbbbbbbbbbbb']
    assert cli.main(['sync']) == 1 and 'FAILED  YouTube has no channel' in capsys.readouterr().out
    def down(now=None): raise youtube.YoutubeError('YouTube could not be reached: down')
    monkeypatch.setattr(catalogue, 'recheck', down)
    assert cli.main(['sync', A]) == 0 and cli.main(['sync']) == 1 and 'library                    FAILED  The recheck for videos gone from YouTube: YouTube could not be reached: down' in capsys.readouterr().out
    assert cli.main(['remove', 'UCbbbbbbbbbbbbbbbbbbbbbb']) == 0 and 'removed UCbbbbbbbbbbbbbbbbbbbbbb and 1 video(s)' in capsys.readouterr().out
    with pytest.raises(SystemExit, match='no channel UCbbbbbbbbbbbbbbbbbbbbbb'): cli.main(['remove', 'UCbbbbbbbbbbbbbbbbbbbbbb'])
    monkeypatch.delenv('YOUTUBE_API_KEY')
    with pytest.raises(SystemExit, match='YOUTUBE_API_KEY is not in the environment'): cli.main(['sync'])


def test_recheck(capsys, fake_youtube, monkeypatch):
    A = 'UCaaaaaaaaaaaaaaaaaaaaaa'
    fake_youtube.channel(A, 'Workshop', videos=5); catalogue.add(A); catalogue.sync_channel(A)
    del fake_youtube.videos[next(iter(fake_youtube.videos))]
    assert cli.main(['recheck', '--limit', '2']) == 0 and '2 video(s) rechecked' in capsys.readouterr().out
    assert cli.main(['recheck', '--all', '--json']) == 0 and json.loads(capsys.readouterr().out)['checked'] == 5
    assert cli.main(['recheck']) == 0 and '5 video(s) rechecked: 0 gone from YouTube and hidden, 0 back' in capsys.readouterr().out
    monkeypatch.delenv('YOUTUBE_API_KEY')
    with pytest.raises(SystemExit, match='cannot be rechecked'): cli.main(['recheck'])


def test_fetch_cache_and_evict(capsys, monkeypatch):
    seed()
    def fake_start(vid, title, channel, background=True):
        if vid == 'bbbbbbbbbbb':
            cache.begin(vid, cache.stamp()); cache.finish(vid, cache.stamp(), error='Video unavailable'); return cache.status(vid)
        if vid == 'ccccccccccc': raise fetcher.FetchError('Fetching needs Linux or macOS.')
        cache.begin(vid, cache.stamp(), title); write_playlist(vid, 2, True); cache.finish(vid, cache.stamp()); cache.set_formats(vid, '1080p AV1 + AAC'); return cache.status(vid)
    monkeypatch.setattr(fetcher, 'start', fake_start)
    assert cli.main(['fetch', 'aaaaaaaaaaa']) == 0 and capsys.readouterr().out.strip() == 'aaaaaaaaaaa: ready, 2 segments, 8 s, 1080p AV1 + AAC'
    with pytest.raises(SystemExit, match='bbbbbbbbbbb: Video unavailable'): cli.main(['fetch', 'bbbbbbbbbbb'])
    with pytest.raises(SystemExit, match='Linux or macOS'): cli.main(['fetch', 'ccccccccccc'])
    with pytest.raises(SystemExit, match='zzz is not in the library'): cli.main(['fetch', 'zzz'])

    assert cli.main(['cache']) == 0
    out = capsys.readouterr().out
    assert 'in 2 video(s); eviction runs above 950.00 GB, down to 900.00 GB' in out and 'aaaaaaaaaaa    ready' in out and 'bbbbbbbbbbb    failed' in out
    assert cli.main(['cache', '--json']) == 0 and json.loads(capsys.readouterr().out)['count'] == 2

    settings.save(dict(cache_limit_gb=1e-9))
    assert cli.main(['evict', '--dry-run']) == 0 and 'would free' in capsys.readouterr().out
    assert cli.main(['evict', '--json']) == 0 and [e['video_id'] for e in json.loads(capsys.readouterr().out)['evicted']] == ['bbbbbbbbbbb']   # the fresh, unplayed copy is kept


def test_set_and_serve(capsys, monkeypatch):
    assert cli.main(['set', 'max_height']) == 0 and capsys.readouterr().out.strip() == 'max_height = 1080'
    assert cli.main(['set', 'max_height', '720']) == 0 and capsys.readouterr().out.strip() == 'max_height = 720'
    assert cli.main(['set', 'max_height', 'default']) == 0 and capsys.readouterr().out.strip() == 'max_height = 1080'
    with pytest.raises(SystemExit, match='must be a number'): cli.main(['set', 'max_height', 'tall'])
    with pytest.raises(SystemExit, match='unknown setting'): cli.main(['set', 'colour', 'red'])

    from tubes.server import app as server_app
    called = []
    monkeypatch.setattr(server_app, 'main', lambda argv: called.append(argv))
    assert cli.main(['serve', '--host', '0.0.0.0', '--port', '9000']) == 0
    assert called == [['--host', '0.0.0.0', '--port', '9000']]


def test_history_import_list_refresh_and_remove(capsys, tmp_path, fake_youtube):
    from takeout import as_html, as_json, chan, watch
    ws = [watch(f'2026-0{1 + n % 3}-0{1 + n}T10:00:00Z', f'v{n:010d}', f'Video {n}', chan('a'), 'Channel a') for n in range(6)]
    (tmp_path / 'a.json').write_text(as_json(ws), encoding='utf8'); (tmp_path / 'b.html').write_text(as_html(ws[:2]), encoding='utf8')
    assert cli.main(['history']) == 0 and 'no history yet' in capsys.readouterr().out
    fake_youtube.channel(chan('a'), 'Channel a')
    assert cli.main(['history', 'import', str(tmp_path / 'a.json'), '--source', 'one']) == 0
    out = capsys.readouterr().out
    assert 'one: 6 watch(es) from 2026-01-01 to 2026-03-06' in out and '1 channel(s) in the history, 0 in 0 group(s); YouTube asked about 1 (0 no longer there)' in out
    assert cli.main(['history', 'import', str(tmp_path / 'b.html'), '--source', 'two', '--no-lookup', '--json']) == 0 and json.loads(capsys.readouterr().out)['watches'] == 2
    assert cli.main(['history']) == 0 and '  one                        6 watches       1 channels  2026-01-01 to 2026-03-06' in capsys.readouterr().out
    assert cli.main(['history', '--json']) == 0 and [s['source'] for s in json.loads(capsys.readouterr().out)] == ['one', 'two']
    fake_youtube.quota_left = 0
    assert cli.main(['history', 'refresh']) == 0 and '1 channel(s) in the history' in capsys.readouterr().out
    from tubes import history
    err = history.refresh(now='2027-06-01T00:00:00+00:00')['error']
    assert 'quota' in err and 'YouTube could not be asked' in cli.describe_refresh(dict(channels=1, groups=0, grouped=0, looked_up=0, missing=0, error=err))
    assert cli.main(['history', 'remove', '--source', 'two']) == 0 and 'forgot two' in capsys.readouterr().out
    with pytest.raises(SystemExit, match='no history called two'): cli.main(['history', 'remove', '--source', 'two'])
    with pytest.raises(SystemExit, match='usage: tubes history remove'): cli.main(['history', 'remove'])
    with pytest.raises(SystemExit, match='usage: tubes history import'): cli.main(['history', 'import', str(tmp_path / 'a.json')])
    with pytest.raises(SystemExit, match='No such file'): cli.main(['history', 'import', str(tmp_path / 'none.json'), '--source', 'x'])
    (tmp_path / 'c.txt').write_text('hello', encoding='utf8')
    with pytest.raises(SystemExit, match='not a Google Takeout watch history'): cli.main(['history', 'import', str(tmp_path / 'c.txt'), '--source', 'x'])


def test_history_sync_from_a_history_database(capsys, tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / 'kept.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE kept (account TEXT, at TEXT, video_id TEXT, title TEXT, channel_id TEXT, channel_name TEXT)')
        con.execute("INSERT INTO kept VALUES ('main', '2026-01-01T10:00:00Z', 'v0000000001', 'One', 'UCaaaaaaaaaaaaaaaaaaaaaa', 'Channel a')")
    with pytest.raises(SystemExit, match='No history database is set'): cli.main(['history', 'sync'])
    assert cli.main(['set', 'history_url', f'sqlite:///{path}']) == 0 and cli.main(['set', 'history_table', 'kept']) == 0
    capsys.readouterr()
    assert cli.main(['history', 'sync', '--no-lookup']) == 0
    assert capsys.readouterr().out == '  main: 1 watch(es)\n  1 channel(s) in the history, 0 in 0 group(s)\n'


def test_related_asks_counts_and_says_what_failed(capsys, fake_youtube, monkeypatch):
    from fake_youtube import vid
    from tubes import related
    monkeypatch.setattr(related, 'PAUSE', 0)
    x, y, p = 'UC' + 'x' * 22, 'UC' + 'y' * 22, 'UC' + 'p' * 22
    for c in (x, y): fake_youtube.channel(c, f'Channel {c[2]}', videos=2); catalogue.add(c)
    catalogue.sync()
    fake_youtube.watch_next(vid(x, 1), [(p, 'Channel p', '@p')]).watch_next(vid(x, 0), [(p, 'Channel p', '@p')])
    fake_youtube.channel(p, 'Channel p', handle='@p')
    assert cli.main(['related', '-v']) == 0
    out = capsys.readouterr().out
    assert f'     1/2 {x:26} 1 channel(s) from 2 page(s)' in out and f'     2/2 {y:26} The watch page of {vid(y, 1)} listed no videos.' in out
    assert f'  {y:26} FAILED  The watch page of {vid(y, 1)} listed no videos.' in out
    assert 'asked about 2 channel(s) (1 failed), 0 still due; 1 channel(s) suggested by them, 1 new' in out and 'YouTube asked about 1 channel(s)' in out
    assert cli.main(['related', '--json']) == 0 and json.loads(capsys.readouterr().out)['asked'] == 0      # asked lately: not again
    fake_youtube.web_down = True; fake_youtube.quota_left = 0
    assert cli.main(['related', '--all', '--limit', '0']) == 1                                            # every one failed
    assert 'asked about 2 channel(s) (2 failed)' in capsys.readouterr().out
    fake_youtube.quota_left = None
    monkeypatch.setattr(related, 'aggregate', lambda: dict(suggested=1, added=0))
    with __import__('tubes').db.connect() as con: con.execute("UPDATE suggestions SET looked_up = NULL")
    fake_youtube.quota_left = 0
    assert cli.main(['related', '--limit', '1']) == 0 and 'YouTube could not be asked about the channels' in capsys.readouterr().out


def test_an_iplayer_programme_is_added_and_synced_without_a_youtube_key(capsys, fake_iplayer):
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=2)
    assert cli.main(['add', 'https://www.bbc.co.uk/iplayer/episodes/b0000001']) == 0
    out = capsys.readouterr().out
    assert 'following b0000001: Harbour Lights' in out and '1 channel(s) synced, 2 new video(s)' in out
    assert cli.main(['sync']) == 0
    with pytest.raises(SystemExit, match='YOUTUBE_API_KEY is not in the environment'): cli.main(['sync', 'UCaaaaaaaaaaaaaaaaaaaaaa'])


def test_quota_counts_a_command_under_its_name(capsys, fake_youtube):
    fake_youtube.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop', handle='@workshop')
    assert cli.main(['recheck']) == 0 and cli.main(['add', '@workshop', '--no-sync']) == 0; capsys.readouterr()
    with quota.purpose('history'): youtube.channels(['UCaaaaaaaaaaaaaaaaaaaaaa'])
    fake_youtube.quota_left = 0
    with pytest.raises(youtube.YoutubeError): youtube.videos(['Ab1-Cd2_Ef3'])
    assert cli.main(['quota']) == 0
    out = capsys.readouterr().out
    assert 'units used on' in out and 'YouTube refused a call for want of quota' in out and 'add' in out and 'history' in out
    assert cli.main(['quota', '--json']) == 0 and json.loads(capsys.readouterr().out)['remaining'] == 0


def test_plays_lists_the_latest_and_sums_up_the_month(capsys):
    from tubes import viewing
    seed()
    now = cache.stamp()
    p = viewing.start('aaaaaaaaaaa', now, source='home', rank=0); viewing.report(p['play_id'], position=550, watched=550, length=600)
    viewing.start('bbbbbbbbbbb', now); viewing.channel_view('UCaaaaaaaaaaaaaaaaaaaaaa', now, source='rail')
    assert cli.main(['plays']) == 0
    lines = capsys.readouterr().out.splitlines()
    assert 'none' in lines[0] and 'link' in lines[0] and 'Sanding the shelf' in lines[0]
    assert 'full' in lines[1] and ' 92%' in lines[1] and 'home' in lines[1] and 'Building a 50% shelf' in lines[1]
    assert lines[2] == '  last 30 days: 2 play(s), 1 none, 0 short, 0 partial, 1 full'
    assert lines[3:] == ['    from home          1 play(s), 1 watched to the end', '    from link          1 play(s), 0 watched to the end', '  channel pages opened from rail 1']
    assert cli.main(['plays', '--json', '--limit', '1']) == 0
    assert len(json.loads(capsys.readouterr().out)['items']) == 1
