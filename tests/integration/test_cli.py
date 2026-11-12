"""The command line end to end: `add`, `sync` and `remove` against a stand-in YouTube Data API (tests/utils/fake_youtube.py), a real HTTP
server on localhost, and `fetch` with tests/utils/fake_ytdlp.py standing in for yt-dlp (a real process, no network)."""
import json, shutil
import pytest
from fake_youtube import vid
from library import seed
from tubes import oslib, settings

needs_ffmpeg = pytest.mark.skipif(not shutil.which('ffmpeg') or not oslib.CAN_PASS_FDS, reason='fetching needs ffmpeg on PATH and Linux or macOS')


A = 'UCaaaaaaaaaaaaaaaaaaaaaa'


def library(cli, fake_youtube, videos=2):
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=videos)
    cli('add', '@workshop')


def test_doctor_reports_the_environment(cli, fake_ytdlp):
    r = cli('doctor', check=False)
    assert 'tubes 0.1.0' in r.stdout and 'ok       yt-dlp 2026.10.26' in r.stdout and 'MISSING  library' in r.stdout and 'synced never' in r.stdout


def test_add_sync_and_remove_a_channel(cli, fake_youtube):
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=130)
    assert '130 new  complete' in cli('add', 'https://www.youtube.com/@workshop').stdout
    c = json.loads(cli('channels', '--json').stdout)[0]
    assert (c['id'], c['title'], c['handle'], c['videos'], c['total_videos'], c['complete'], c['follow']) == (A, 'Workshop', '@workshop', 130, 130, True, True)
    fake_youtube.uploads(A, 2); fake_youtube.calls.clear()
    assert '2 new video(s)' in cli('sync').stdout and fake_youtube.count('playlistItems') == 2      # caught up after two pages, not all three
    fake_youtube.quota_left = 0
    r = cli('sync', check=False)
    assert r.code == 1 and 'quota for today' in r.out
    assert '132 videos' in cli('channels').stdout                                          # a failed sync keeps what is there
    assert 'removed UCaaaaaaaaaaaaaaaaaaaaaa and 132 video(s)' in cli('remove', A).stdout


def test_the_first_sync_reads_back_a_library_copied_before_tubes_managed_it(cli, fake_youtube):
    # The tables as the old copy from the storage service left them: channels with no sync state (followed by the column's default) and
    # some of their videos. The first sync reads each channel back to its first upload and adds only what is missing.
    seed(channels=[dict(id=A, title='Workshop', handle=None, thumbnail=None, synced='2026-01-20T10:00:00Z')],
         videos=[dict(id=vid(A, n), channel_id=A, title=f'Upload {n} of Workshop', published=f'2020-01-0{n + 1}T12:00:00Z', duration=245, thumbnail=None, views=1) for n in (0, 1)])
    assert '2 videos  backfilling' in cli('channels').stdout
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=3)                       # one more on YouTube since the last copy
    out = cli('sync').stdout
    assert '1 new  complete' in out and '3 video(s) rechecked: 0 gone from YouTube and hidden, 0 back' in out and fake_youtube.count('videos') == 2     # the new one's details, then the recheck
    assert '3 videos  complete     Workshop' in cli('channels').stdout


@needs_ffmpeg
def test_fetch_makes_a_complete_hls_copy_and_evict_trims_it(cli, fake_ytdlp, fake_youtube):
    library(cli, fake_youtube); fake_ytdlp.seconds(9)
    assert cli('fetch', 'aaaa0000001').stdout.strip() == 'aaaa0000001: ready, 3 segments, 9 s, 180p H.264 + AAC'
    c = json.loads(cli('cache', '--json').stdout)
    assert c['count'] == 1 and c['items'][0]['bytes'] > 10_000 and c['items'][0]['title'] == 'Upload 1 of Workshop'
    settings.save(dict(cache_limit_gb=1e-9, protect_days=0))
    assert json.loads(cli('evict', '--json').stdout)['evicted'][0]['video_id'] == 'aaaa0000001'
    assert json.loads(cli('cache', '--json').stdout)['count'] == 0


@needs_ffmpeg
def test_a_failed_download_is_reported(cli, fake_ytdlp, fake_youtube):
    library(cli, fake_youtube); fake_ytdlp.fail('-f v264')
    r = cli('fetch', 'aaaa0000001', check=False)
    assert r.code != 0 and 'aaaa0000001: [youtube] fake: Video unavailable' in r.out
    assert 'is not in the library' in cli('fetch', 'zzzzzzzzzzz', check=False).out


def test_settings_are_viewed_and_updated_from_the_command_line(cli, tmp_path, monkeypatch):
    monkeypatch.delenv('TUBES_DATA', raising=False)
    elsewhere = tmp_path / 'elsewhere'
    assert str(elsewhere) in cli('set', 'data_dir', elsewhere).stdout and settings.data_dir() == str(elsewhere.resolve())
    assert 'data_dir' in cli('set', 'data_dir', 'default').stdout
    assert cli('set', 'nope', 'x', check=False).code != 0


def test_the_command_line_runs_as_a_real_process(cli_subprocess, fake_ytdlp, fake_youtube):
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=2)
    assert 'tubes 0.1.0' in cli_subprocess('doctor', check=False).stdout
    assert '2 new video(s)' in cli_subprocess('add', '@workshop').stdout                   # the subprocess finds the stand-in YouTube and the test's database by environment
    assert 'Workshop' in cli_subprocess('channels').stdout


def test_related_suggests_what_the_followed_channels_watch_pages_list(cli_subprocess, client, fake_youtube):
    # A real process, so the one-second pause between watch pages is real too: two channels with one video each keep it to about a second.
    b, p = 'UCbbbbbbbbbbbbbbbbbbbbbb', 'UCpppppppppppppppppppppp'
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=1).channel(b, 'Garden', videos=1).channel(p, 'Potter', handle='@potter', topics=['Hobby'])
    fake_youtube.watch_next(vid(A, 0), [(p, 'Potter', '@potter'), (b, 'Garden', None)]).watch_next(vid(b, 0), [(p, 'Potter', '@potter')]).featuring(b, [A])
    cli_subprocess('add', A); cli_subprocess('add', b)
    out = cli_subprocess('related').stdout
    assert 'asked about 2 channel(s) (0 failed), 0 still due; 1 channel(s) suggested by them, 1 new' in out and 'YouTube asked about 1 channel(s)' in out
    page = client.get('/api/suggestions', params=dict(order='suggested')).json()
    assert [(i['channel_id'], i['title'], i['suggested_by'], i['suggested_from'], i['topics'], i['watches']) for i in page['items']] == [(p, 'Potter', 2, ['Workshop', 'Garden'], ['Hobby'], 0)]
    s = client.get('/api/suggestions/summary').json()
    assert (s['suggested'], s['unwatched'], s['related']['sources'], s['related']['asked'], s['related']['due'], s['related']['failed']) == (1, 1, 2, 2, 0, 0)
    r = client.get('/api/suggestions', params=dict(order='newest'))
    assert r.status_code == 400 and r.json()['detail'] == 'Order by watched or suggested, not newest.'
