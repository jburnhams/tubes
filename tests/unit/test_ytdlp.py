import json, subprocess
import pytest
from tubes import settings, ytdlp


def test_watch_url_takes_youtube_ids_only():
    assert ytdlp.watch_url('abc123DEF-_') == 'https://www.youtube.com/watch?v=abc123DEF-_'
    for bad in ('', None, 'short', 'abc123DEF-_x', 'abc 23DEF-_', '--exec=rm'):
        with pytest.raises(ytdlp.YtdlpError, match='not a YouTube video id'): ytdlp.watch_url(bad)


def test_base_command_uses_the_player_client_setting():
    assert ytdlp.base_command() == ['yt-dlp', '--no-warnings', '--no-progress', '--ignore-config', '--extractor-args', 'youtube:player_client=visionos']
    settings.save(dict(player_client='', ytdlp='/opt/bin/yt-dlp'))
    assert ytdlp.base_command() == ['/opt/bin/yt-dlp', '--no-warnings', '--no-progress', '--ignore-config']


def test_signed_in_reads_the_browser_and_swaps_visionos_for_a_client_that_takes_cookies():
    settings.save(dict(cookies_from_browser='chrome+gnomekeyring'))
    assert ytdlp.base_command()[4:] == ['--cookies-from-browser', 'chrome+gnomekeyring', '--extractor-args', 'youtube:player_client=tv_downgraded']
    settings.save(dict(player_client='mweb'))
    assert ytdlp.base_command()[-1] == 'youtube:player_client=mweb'
    settings.save(dict(player_client=''))
    assert ytdlp.base_command()[4:] == ['--cookies-from-browser', 'chrome+gnomekeyring']


def test_run_json_failures(fake_run, monkeypatch):
    fake_run.returns['--dump-single-json'] = 'not json'
    with pytest.raises(ytdlp.YtdlpError, match='did not return JSON'): ytdlp.probe('https://x.test/v')

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a[0], 1, '', 'WARNING: slow\nERROR: [youtube] x: Sign in to confirm\nmore\n'))
    with pytest.raises(ytdlp.YtdlpError, match='^\\[youtube\\] x: Sign in to confirm$'): ytdlp.probe('https://x.test/v')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a[0], 2, '', ''))
    with pytest.raises(ytdlp.YtdlpError, match='exited with code 2'): ytdlp.probe('https://x.test/v')

    def missing(*a, **k): raise FileNotFoundError(a[0][0])
    monkeypatch.setattr(subprocess, 'run', missing)
    with pytest.raises(ytdlp.YtdlpError, match='not installed'): ytdlp.probe('https://x.test/v')
    assert ytdlp.version() is None

    def slow(*a, **k): raise subprocess.TimeoutExpired(a[0], k['timeout'])
    monkeypatch.setattr(subprocess, 'run', slow)
    with pytest.raises(ytdlp.YtdlpError, match='longer than 120 s'): ytdlp.probe('https://x.test/v')
    assert ytdlp.version() is None


def test_version(fake_run):
    fake_run.returns['--version'] = '2026.10.26\n'
    assert ytdlp.version() == '2026.10.26'
    fake_run.code = 1
    assert ytdlp.version() is None


def test_last_error():
    assert ytdlp.last_error('a\nb\n') == 'b'
    assert ytdlp.last_error('ERROR: one\nERROR: two\ntrailing') == 'two'
    assert ytdlp.last_error('') == '' and ytdlp.last_error(None) == ''


def fmt(fid, v=None, a=None, h=None, w=None, **kw):
    return dict(format_id=fid, vcodec=v or 'none', acodec=a or 'none', height=h, width=w, protocol='https') | kw


FORMATS = [
    fmt('sb0', v='none', a='none', protocol='mhtml'),
    fmt('137', v='avc1.640028', h=1080, w=1920, tbr=4500), fmt('248', v='vp9', h=1080, w=1920, tbr=2600), fmt('399', v='av01.0.08M.08', h=1080, w=1920, tbr=2200),
    fmt('400', v='av01.0.12M.08', h=1440, w=2560, tbr=5000), fmt('136', v='avc1.4d401f', h=720, w=1280, tbr=2000),
    fmt('96', v='avc1', a='mp4a', h=1080, w=1920) | dict(protocol='m3u8_native'), fmt('hev', v='hev1', h=1080, w=1920, tbr=9000),
    fmt('140-dub', a='mp4a.40.2', abr=129, language_preference=-1, format_note='Spanish'), fmt('140', a='mp4a.40.2', abr=129, language_preference=10, format_note='English original, medium'),
    fmt('251', a='opus', abr=130, language_preference=10, format_note='English original'), fmt('drm', a='mp4a', abr=320, has_drm=True, language_preference=10),
]


def test_choose_formats_prefers_height_then_codec_then_bitrate_and_the_original_audio():
    video, audio = ytdlp.choose_formats(FORMATS, 1080)
    assert (video['format_id'], audio['format_id']) == ('399', '140')
    assert ytdlp.describe(video, audio) == '1080p AV1 + AAC'
    assert ytdlp.choose_formats(FORMATS, 720)[0]['format_id'] == '136'
    assert ytdlp.choose_formats([f for f in FORMATS if f['format_id'] != '399'], 1080)[0]['format_id'] == '248'
    widescreen = [fmt('w', v='vp9', h=1072, w=2560, tbr=1), fmt('n', v='vp9', h=800, w=1920, tbr=1), fmt('a', a='opus', abr=1)]
    assert ytdlp.choose_formats(widescreen, 1080)[0]['format_id'] == 'n'          # 2560 wide is over 16:9 of 1080, whatever its height
    assert ytdlp.describe(dict(height=480, vcodec='vp09.00.40.08'), dict(acodec='opus')) == '480p VP9 + Opus'
    assert ytdlp.describe(dict(height=480, vcodec='weird.1'), dict(acodec=None)) == '480p weird + ?'


def test_choose_formats_says_what_is_missing():
    with pytest.raises(ytdlp.YtdlpError, match='No video stream at or under 1080p'): ytdlp.choose_formats([fmt('a', a='opus')], 1080)
    with pytest.raises(ytdlp.YtdlpError, match='No separate audio'): ytdlp.choose_formats([fmt('v', v='vp9', h=360, w=640)], 1080)
    with pytest.raises(ytdlp.YtdlpError, match='No video'): ytdlp.choose_formats([], 1080)
