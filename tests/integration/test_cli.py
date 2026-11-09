"""The command line end to end: `add`, `sync` and `remove` against a stand-in YouTube Data API (tests/utils/fake_youtube.py), `import-d1`
against a stand-in D1 (tests/utils/fake_d1.py), both real HTTP servers on localhost, and `fetch` with tests/utils/fake_ytdlp.py standing in
for yt-dlp (a real process, no network)."""
import json, shutil
import pytest
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


def test_import_d1_carries_the_library_over_once(cli, fake_d1, fake_youtube):
    (fake_d1.channel(A, 'Workshop', custom_url='@workshop', upload_playlist_id='UU' + A[2:], last_sync_at='2026-01-20T10:00:00Z', video_count=3)
            .video('aaaa0000001', A, 'Upload 1 of Workshop', '2020-01-02T12:00:00Z', 9).video('aaaa0000000', A, 'Upload 0 of Workshop', '2020-01-01T12:00:00Z'))
    assert 'imported 1 channel(s) and 2 video(s)' in cli('import-d1').stdout
    assert '2 videos  complete' in cli('channels').stdout
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=3)                       # one more on YouTube since storage's last sync
    assert '1 new video(s)' in cli('sync').stdout and fake_youtube.count('videos') == 1
    fake_d1.token = 'rotated'
    r = cli('import-d1', check=False)
    assert r.code != 0 and 'D1 refused the query (403: Authentication error)' in r.out


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
