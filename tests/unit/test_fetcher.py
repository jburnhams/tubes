import json, os, subprocess, threading
import pytest
from tubes import cache, fetcher, oslib, settings, ytdlp
from library import seed
from test_cache import write_playlist

INFO = dict(duration=8, formats=[dict(format_id='399', vcodec='av01.0.08M.08', acodec='none', height=1080, width=1920, protocol='https'),
                                 dict(format_id='140', vcodec='none', acodec='mp4a.40.2', abr=129, protocol='https')])


@pytest.fixture(autouse=True)
def clean_jobs(monkeypatch):
    monkeypatch.setattr(fetcher, '_running', {}); monkeypatch.setattr(oslib, 'CAN_PASS_FDS', True)


def test_commands():
    assert fetcher.hls_command(video_fd=7, audio_fd=9)[:13] == ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', 'pipe:7', '-i', 'pipe:9', '-map', '0:v:0', '-map']
    assert fetcher.hls_command()[-1] == 'index.m3u8' and 'event' in fetcher.hls_command()
    assert fetcher.stream_command('399', '/c/probe.json')[-7:] == ['--no-part', '-f', '399', '--load-info-json', '/c/probe.json', '-o', '-']


def test_start_refusals(monkeypatch):
    seed()
    with pytest.raises(fetcher.FetchError, match="'zzz' is not a YouTube video id"): fetcher.start('zzz')
    monkeypatch.setattr(oslib, 'CAN_PASS_FDS', False)
    with pytest.raises(fetcher.FetchError, match='Linux or macOS'): fetcher.start('aaaaaaaaaaa')
    monkeypatch.setattr(oslib, 'CAN_PASS_FDS', True)
    monkeypatch.setattr(fetcher, '_running', {f'v{i}': None for i in range(fetcher.MAX_RUNNING)})
    with pytest.raises(fetcher.FetchError, match='already being fetched'): fetcher.start('aaaaaaaaaaa')


def test_start_joins_a_running_fetch_and_returns_a_ready_copy(monkeypatch):
    seed()
    monkeypatch.setattr(fetcher, '_running', {'aaaaaaaaaaa': fetcher.Job('aaaaaaaaaaa')})
    assert fetcher.start('aaaaaaaaaaa')['state'] == 'none' and fetcher.running() == ['aaaaaaaaaaa']
    cache.begin('bbbbbbbbbbb', cache.stamp()); write_playlist('bbbbbbbbbbb', 1, True); cache.finish('bbbbbbbbbbb', cache.stamp())
    monkeypatch.setattr(fetcher, '_run', lambda *a: pytest.fail('a ready copy is not fetched again'))
    assert fetcher.start('bbbbbbbbbbb')['state'] == 'ready'


def test_a_fetch_in_the_background_succeeds_and_trims_the_cache(monkeypatch):
    seed()
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    seen = []; gate = threading.Event()   # holds the fetch until the first answer is checked, which would otherwise race it
    def fake_pipeline(job, info_path, v, a, duration, signed_in):
        gate.wait(10)
        with open(info_path, encoding='utf8') as f: seen.append((json.load(f), v, a, duration))
        write_playlist(job.video_id, 2, True); return None
    monkeypatch.setattr(fetcher, 'pipeline', fake_pipeline)
    evicted = []; monkeypatch.setattr(cache, 'evict', lambda now: evicted.append(now))
    st = fetcher.start('aaaaaaaaaaa', 'Building a shelf', 'Workshop')
    assert st['state'] == 'fetching' and cache.entry('aaaaaaaaaaa')['title'] == 'Building a shelf'
    gate.set()
    fetcher._running.get('aaaaaaaaaaa') and fetcher._running['aaaaaaaaaaa'].thread.join(10)
    assert seen == [(INFO, '399', '140', 8)] and len(evicted) == 1
    assert not os.path.exists(os.path.join(cache.folder('aaaaaaaaaaa'), fetcher.INFO))       # the saved probe goes when the fetch ends
    assert cache.status('aaaaaaaaaaa') | dict() == dict(state='ready', segments=2, seconds=8.0, complete=True, playable=True, error=None, formats='1080p AV1 + AAC')
    assert fetcher.running() == []


def test_a_probe_without_usable_streams_is_tried_once_more(monkeypatch):
    answers = [dict(formats=[dict(format_id='96', vcodec='avc1', acodec='mp4a', height=1080, protocol='m3u8_native')]), INFO]   # SABR-only, then a normal answer
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: answers.pop(0))
    info, video, audio, signed_in = fetcher.choose('https://u')
    assert not signed_in and info is INFO and (video['format_id'], audio['format_id']) == ('399', '140') and answers == []


@pytest.mark.parametrize('probe, pipeline_result, error', [
    (ytdlp.YtdlpError('Sign in to confirm you are not a bot'), None, 'Sign in to confirm you are not a bot'),
    (dict(formats=[]), None, 'No video stream at or under 1080p in a codec Chrome plays (AV1, VP9 or H.264).'),
    (INFO, 'Only 4 s of 8 s arrived.', 'Only 4 s of 8 s arrived.'),
    (INFO, OSError('No such file: ffmpeg'), 'Could not start the fetch: No such file: ffmpeg'),
])
def test_failures_are_recorded_on_the_copy(monkeypatch, probe, pipeline_result, error):
    seed()
    def fake_probe(url, signed_in=False):
        if isinstance(probe, Exception): raise probe
        return probe
    def fake_pipeline(*a):
        if isinstance(pipeline_result, Exception): raise pipeline_result
        return pipeline_result
    monkeypatch.setattr(ytdlp, 'probe', fake_probe); monkeypatch.setattr(fetcher, 'pipeline', fake_pipeline)
    monkeypatch.setattr(cache, 'evict', lambda now: pytest.fail('nothing to trim after a failure'))
    st = fetcher.start('aaaaaaaaaaa', background=False)
    assert (st['state'], st['error']) == ('failed', error)


def test_a_cancelled_fetch_is_recorded_as_stopped(monkeypatch):
    seed()
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    def fake_pipeline(job, *a):
        job.cancelled = True; return None
    monkeypatch.setattr(fetcher, 'pipeline', fake_pipeline)
    assert fetcher.start('aaaaaaaaaaa', background=False)['error'] == 'The fetch was stopped.'


def test_cancel_stops_running_processes(monkeypatch, fake_popen):
    job = fetcher.Job('aaaaaaaaaaa'); p = fake_popen(['x']); done = fake_popen(['y']); done.returncode = 0
    job.procs = [p, done]; job.thread = threading.Thread(target=lambda: None); job.thread.start()
    killed = []; monkeypatch.setattr(oslib, 'kill_tree', lambda pid: killed.append(pid))
    fetcher._running['aaaaaaaaaaa'] = job
    fetcher.cancel(['aaaaaaaaaaa', 'not-running'])
    assert job.cancelled is True and killed == [p.pid]


class Proc:
    """A finished process with an exit code (pipeline waits for it)."""
    def __init__(self, cmd, code=0, **kw): self.cmd, self.kw, self.returncode, self.pid = cmd, kw, code, 1
    def poll(self): return self.returncode
    def wait(self): return self.returncode


def run_pipeline(monkeypatch, codes=(0, 0, 0), log=b'', stalled=False, cancelled=False, segments=2, complete=True, duration=8):
    seed(); cache.begin('aaaaaaaaaaa', cache.stamp())
    made = []
    def popen(cmd, **kw):
        made.append(Proc(cmd, codes[len(made)], **kw))
        if len(made) == 3:
            write_playlist('aaaaaaaaaaa', segments, complete)
            with open(os.path.join(cache.folder('aaaaaaaaaaa'), fetcher.LOG), 'ab') as f: f.write(log)
        return made[-1]
    monkeypatch.setattr(subprocess, 'Popen', popen)
    job = fetcher.Job('aaaaaaaaaaa')
    def fake_watch(j):
        j.cancelled = cancelled; return stalled
    monkeypatch.setattr(fetcher, 'watch', fake_watch)
    return fetcher.pipeline(job, '/c/probe.json', '399', '140', duration), made


def test_pipeline_wires_two_downloads_into_ffmpeg(monkeypatch):
    result, made = run_pipeline(monkeypatch)
    assert result is None
    ff, v, a = made
    fds = ff.kw['pass_fds']
    assert ff.cmd[7] == f'pipe:{fds[0]}' and ff.cmd[9] == f'pipe:{fds[1]}' and ff.kw['cwd'] == cache.folder('aaaaaaaaaaa')
    assert v.cmd[-6:] == ['-f', '399', '--load-info-json', '/c/probe.json', '-o', '-'] and a.cmd[-6:] == ['-f', '140', '--load-info-json', '/c/probe.json', '-o', '-']
    assert isinstance(v.kw['stdout'], int) and isinstance(a.kw['stdout'], int)
    for fd in (*fds, v.kw['stdout'], a.kw['stdout']):
        with pytest.raises(OSError): os.fstat(fd)                                          # every pipe end is closed in this process


@pytest.mark.parametrize('kw, reason', [
    (dict(codes=(0, 1, 0), log=b'ERROR: [youtube] x: HTTP Error 403: Forbidden\n'), '[youtube] x: HTTP Error 403: Forbidden'),
    (dict(codes=(1, 0, 0)), 'The fetch failed (exit codes [1, 0, 0]).'),
    (dict(stalled=True), 'Nothing arrived for 120 s, so the fetch was stopped.'),
    (dict(cancelled=True), 'The fetch was stopped.'),
    (dict(complete=False), 'The fetch ended before the video was complete.'),
    (dict(segments=0), 'The fetch ended before the video was complete.'),
    (dict(segments=1, duration=60), 'Only 4 s of 60 s arrived.'),
])
def test_pipeline_says_why_a_copy_is_incomplete(monkeypatch, kw, reason):
    assert run_pipeline(monkeypatch, **kw)[0] == reason


def test_pipeline_stops_what_started_when_a_process_cannot_start(monkeypatch):
    seed(); cache.begin('aaaaaaaaaaa', cache.stamp())
    made = []
    def popen(cmd, **kw):
        if made: raise OSError('no yt-dlp')
        made.append(Proc(cmd, None)); return made[-1]
    monkeypatch.setattr(subprocess, 'Popen', popen)
    killed = []; monkeypatch.setattr(oslib, 'kill_tree', lambda pid: killed.append(pid))
    job = fetcher.Job('aaaaaaaaaaa')
    with pytest.raises(OSError, match='no yt-dlp'): fetcher.pipeline(job, 'u', 'v', 'a')
    assert killed == [1] and job.cancelled is True


def test_watch_stops_a_stalled_fetch(monkeypatch):
    seed(); cache.begin('aaaaaaaaaaa', cache.stamp())
    job = fetcher.Job('aaaaaaaaaaa'); p = Proc(['x'], None); job.procs = [p]
    killed = []; monkeypatch.setattr(oslib, 'kill_tree', lambda pid: killed.append(pid))
    t = [0.0]
    def sleep(s):
        t[0] += 50
        if t[0] == 50: write_playlist('aaaaaaaaaaa', 1, False)                              # it grows once, then nothing
    assert fetcher.watch(job, clock=lambda: t[0], sleep=sleep) is True
    assert killed == [1] and job.cancelled is False
    p.returncode = 0
    assert fetcher.watch(job, clock=lambda: 0, sleep=sleep) is False


def test_ffmpeg_version(fake_run, monkeypatch):
    fake_run.returns['-version'] = 'ffmpeg version 7.1 Copyright\nbuilt with gcc\n'
    assert fetcher.ffmpeg_version() == 'ffmpeg version 7.1 Copyright'
    fake_run.code = 1
    assert fetcher.ffmpeg_version() is None
    def missing(*a, **k): raise FileNotFoundError('ffmpeg')
    monkeypatch.setattr(subprocess, 'run', missing)
    assert fetcher.ffmpeg_version() is None


def test_a_copy_deleted_while_probing_starts_no_download(monkeypatch):
    seed()
    def probe(url, signed_in=False):
        fetcher._running['aaaaaaaaaaa'].stop(); return INFO                                 # the delete arrives while yt-dlp is still probing
    monkeypatch.setattr(ytdlp, 'probe', probe)
    monkeypatch.setattr(fetcher, 'pipeline', lambda *a: pytest.fail('no download starts after a stop'))
    assert fetcher.start('aaaaaaaaaaa', background=False)['error'] == 'The fetch was stopped.'


def test_a_stop_while_the_processes_start_reaches_all_of_them(monkeypatch):
    seed(); cache.begin('aaaaaaaaaaa', cache.stamp())
    job = fetcher.Job('aaaaaaaaaaa')
    def popen(cmd, **kw):
        if not job.procs: job.stop()                                                          # the stop lands after ffmpeg started, before the downloads
        return Proc(cmd, None, **kw)
    monkeypatch.setattr(subprocess, 'Popen', popen)
    killed = []; monkeypatch.setattr(oslib, 'kill_tree', lambda pid: killed.append(pid))
    assert fetcher.pipeline(job, 'u', 'v', 'a') == 'The fetch was stopped.'
    assert len(killed) == 3


def test_watch_ends_when_the_fetch_is_cancelled(monkeypatch):
    job = fetcher.Job('aaaaaaaaaaa'); job.procs = [Proc(['x'], None)]; job.cancelled = True
    killed = []; monkeypatch.setattr(oslib, 'kill_tree', lambda pid: killed.append(pid))
    assert fetcher.watch(job, sleep=lambda s: pytest.fail('no wait after a stop')) is False and killed == [1]


def test_a_ready_copy_whose_files_are_gone_is_fetched_again(monkeypatch, tmp_path):
    seed()
    cache.begin('aaaaaaaaaaa', cache.stamp()); write_playlist('aaaaaaaaaaa', 2, True); cache.finish('aaaaaaaaaaa', cache.stamp())
    monkeypatch.setenv('TUBES_CACHE', str(tmp_path / 'moved'))                                # the cache folder changed in Settings
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    ran = []; monkeypatch.setattr(fetcher, 'pipeline', lambda job, *a: ran.append(job.video_id) or write_playlist(job.video_id, 2, True))
    monkeypatch.setattr(cache, 'evict', lambda now: None)
    assert fetcher.start('aaaaaaaaaaa', background=False)['complete'] is True and ran == ['aaaaaaaaaaa']


def chosen_ids(result): return (result[1]['format_id'], result[2]['format_id'], result[3])


def test_signed_out_wins_when_its_streams_have_no_ad_wait(monkeypatch):
    settings.save(dict(cookies_from_browser='chrome'))
    calls = []
    def probe(url, signed_in=False):
        calls.append(signed_in); return dict(INFO, epoch=100, formats=[dict(f, available_at=100) for f in INFO['formats']])
    monkeypatch.setattr(ytdlp, 'probe', probe)
    assert chosen_ids(fetcher.choose('https://u')) == ('399', '140', False) and sorted(calls) == [False, True]


def test_signed_in_wins_over_an_ad_wait_and_signed_out_is_the_fallback(monkeypatch):
    settings.save(dict(cookies_from_browser='chrome'))
    waiting = dict(INFO, epoch=100, formats=[dict(f, available_at=109) for f in INFO['formats']])
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO if signed_in else waiting)
    assert chosen_ids(fetcher.choose('https://u')) == ('399', '140', True)
    def locked(url, signed_in=False):
        if signed_in: raise ytdlp.YtdlpError('Environment variable DBUS_SESSION_BUS_ADDRESS is unset')
        return waiting
    monkeypatch.setattr(ytdlp, 'probe', locked)
    result = fetcher.choose('https://u')
    assert chosen_ids(result) == ('399', '140', False) and ytdlp.ad_wait(result[0], result[1], result[2]) == 9


def test_signed_in_alone_when_signed_out_fails_and_both_failing_is_an_error(monkeypatch):
    settings.save(dict(cookies_from_browser='chrome'))
    def only_in(url, signed_in=False):
        if not signed_in: raise ytdlp.YtdlpError('UNPLAYABLE')
        return INFO
    monkeypatch.setattr(ytdlp, 'probe', only_in)
    assert chosen_ids(fetcher.choose('https://u')) == ('399', '140', True)
    def neither(url, signed_in=False): raise ytdlp.YtdlpError('cookies' if signed_in else 'UNPLAYABLE')
    monkeypatch.setattr(ytdlp, 'probe', neither)
    with pytest.raises(ytdlp.YtdlpError, match='cookies'): fetcher.choose('https://u')


def test_signed_in_downloads_read_the_browser_too():
    settings.save(dict(cookies_from_browser='chrome'))
    assert '--cookies-from-browser' in fetcher.stream_command('399', '/p.json', True) and '--cookies-from-browser' not in fetcher.stream_command('399', '/p.json')
