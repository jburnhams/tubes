"""The command line end to end: `sync` against a stand-in D1 (tests/utils/fake_d1.py, a real HTTP server on localhost), and `fetch` with
tests/utils/fake_ytdlp.py standing in for yt-dlp (a real process, no network)."""
import json, shutil
import pytest
from tubes import oslib, settings

needs_ffmpeg = pytest.mark.skipif(not shutil.which('ffmpeg') or not oslib.CAN_PASS_FDS, reason='fetching needs ffmpeg on PATH and Linux or macOS')


def library(fake_d1):
    return (fake_d1.channel('UCaaaaaaaaaaaaaaaaaaaaaa', 'Workshop', custom_url='@workshop', best_thumbnail_url='https://img.test/w.jpg')
            .video('aaaaaaaaaaa', 'UCaaaaaaaaaaaaaaaaaaaaaa', 'Building a shelf', '2026-01-03T00:00:00Z', 9, thumbnail_url='https://img.test/a.jpg')
            .video('bbbbbbbbbbb', 'UCaaaaaaaaaaaaaaaaaaaaaa', 'Sanding', '2026-01-02T00:00:00Z'))


def test_doctor_reports_the_environment(cli, fake_ytdlp):
    r = cli('doctor', check=False)
    assert 'tubes 0.1.0' in r.stdout and 'ok       yt-dlp 2026.10.26' in r.stdout and 'MISSING  library' in r.stdout and 'synced never' in r.stdout


def test_sync_copies_the_library_from_d1_and_follows_removals(cli, fake_d1):
    library(fake_d1)
    assert '1 channel(s), 2 video(s), synced' in cli('sync').stdout
    assert json.loads(cli('channels', '--json').stdout)[0] | dict(synced=None) == dict(id='UCaaaaaaaaaaaaaaaaaaaaaa', title='Workshop', handle='@workshop', thumbnail='https://img.test/w.jpg', synced=None, videos=2, latest='2026-01-03T00:00:00Z')
    fake_d1.remove_video('bbbbbbbbbbb')
    assert '1 video(s)' in cli('sync').stdout
    fake_d1.token = 'rotated'
    r = cli('sync', check=False)
    assert r.code != 0 and 'D1 refused the query (403: Authentication error)' in r.out
    assert '1 videos' in cli('channels').stdout                                            # a failed sync keeps the copy


@needs_ffmpeg
def test_fetch_makes_a_complete_hls_copy_and_evict_trims_it(cli, fake_ytdlp, fake_d1):
    library(fake_d1); cli('sync'); fake_ytdlp.seconds(9)
    assert cli('fetch', 'aaaaaaaaaaa').stdout.strip() == 'aaaaaaaaaaa: ready, 3 segments, 9 s, 180p H.264 + AAC'
    c = json.loads(cli('cache', '--json').stdout)
    assert c['count'] == 1 and c['items'][0]['bytes'] > 10_000 and c['items'][0]['title'] == 'Building a shelf'
    settings.save(dict(cache_limit_gb=1e-9, protect_days=0))
    assert json.loads(cli('evict', '--json').stdout)['evicted'][0]['video_id'] == 'aaaaaaaaaaa'
    assert json.loads(cli('cache', '--json').stdout)['count'] == 0


@needs_ffmpeg
def test_a_failed_download_is_reported(cli, fake_ytdlp, fake_d1):
    library(fake_d1); cli('sync'); fake_ytdlp.fail('-f v264')
    r = cli('fetch', 'aaaaaaaaaaa', check=False)
    assert r.code != 0 and 'aaaaaaaaaaa: [youtube] fake: Video unavailable' in r.out
    assert 'is not in the library' in cli('fetch', 'zzzzzzzzzzz', check=False).out


def test_settings_are_viewed_and_updated_from_the_command_line(cli, tmp_path, monkeypatch):
    monkeypatch.delenv('TUBES_DATA', raising=False)
    elsewhere = tmp_path / 'elsewhere'
    assert str(elsewhere) in cli('set', 'data_dir', elsewhere).stdout and settings.data_dir() == str(elsewhere.resolve())
    assert 'data_dir' in cli('set', 'data_dir', 'default').stdout
    assert cli('set', 'nope', 'x', check=False).code != 0


def test_the_command_line_runs_as_a_real_process(cli_subprocess, fake_ytdlp, fake_d1):
    library(fake_d1)
    assert 'tubes 0.1.0' in cli_subprocess('doctor', check=False).stdout
    assert '2 video(s)' in cli_subprocess('sync').stdout                                     # the subprocess finds the stand-in D1 and the test's database by environment
    assert 'Workshop' in cli_subprocess('channels').stdout
