import json, os, subprocess, threading
import pytest
from tubes import cache, catalogue, fetcher, library, oslib, settings, ytdlp
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


def test_a_failed_download_is_run_once_more_with_the_same_streams(monkeypatch):
    seed()
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    runs = []
    def flaky(job, info_path, v, a, duration, signed_in):
        runs.append((v, a, os.path.exists(info_path)))
        if len(runs) == 1: write_playlist(job.video_id, 1, False); return 'unable to write data: [Errno 32] Broken pipe'
        write_playlist(job.video_id, 2, True); return None
    monkeypatch.setattr(fetcher, 'pipeline', flaky); monkeypatch.setattr(cache, 'evict', lambda now: None)
    st = fetcher.start('aaaaaaaaaaa', background=False)
    assert runs == [('399', '140', True)] * 2 and (st['state'], st['error'], st['segments']) == ('ready', None, 2)
    with open(os.path.join(cache.folder('aaaaaaaaaaa'), fetcher.LOG), encoding='utf8') as f: assert 'attempt 1 failed: unable to write data' in f.read()


def test_a_download_failing_every_attempt_records_the_last_reason(monkeypatch):
    seed()
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    reasons = ['Broken pipe', 'Only 4 s of 8 s arrived.']
    monkeypatch.setattr(fetcher, 'pipeline', lambda *a: reasons.pop(0))
    st = fetcher.start('aaaaaaaaaaa', background=False)
    assert (st['state'], st['error'], reasons) == ('failed', 'Only 4 s of 8 s arrived.', [])


def test_a_stopped_download_is_not_run_again(monkeypatch):
    seed()
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    runs = []
    def stopped(job, *a):
        runs.append(1); job.cancelled = True; return 'The fetch was stopped.'
    monkeypatch.setattr(fetcher, 'pipeline', stopped)
    assert fetcher.start('aaaaaaaaaaa', background=False)['error'] == 'The fetch was stopped.' and runs == [1]


def test_a_failed_iplayer_download_is_run_once_more(monkeypatch):
    seed_episode()
    monkeypatch.setattr(iplayer, 'stream', lambda pid, h: dict(url='u', label='720p50 H.264 + AAC'))
    runs = []
    def flaky(job, url, duration):
        runs.append(url)
        if len(runs) == 1: return 'Server returned 403 Forbidden'
        write_playlist(job.video_id, 2, True); return None
    monkeypatch.setattr(fetcher, 'direct_pipeline', flaky); monkeypatch.setattr(cache, 'evict', lambda now: None)
    assert fetcher.start(E, background=False)['state'] == 'ready' and runs == ['u', 'u']


def test_a_video_youtube_no_longer_has_is_hidden_until_a_fetch_finds_it(monkeypatch):
    seed()
    def gone(url, signed_in=False): raise ytdlp.YtdlpError('[youtube] aaaaaaaaaaa: Video unavailable. This video has been removed by the uploader')
    monkeypatch.setattr(ytdlp, 'probe', gone)
    assert fetcher.start('aaaaaaaaaaa', background=False)['state'] == 'failed'
    assert library.video('aaaaaaaaaaa')['gone'] and 'aaaaaaaaaaa' not in [v['id'] for v in library.videos()['videos']]
    catalogue.mark_gone('aaaaaaaaaaa', now='later'); assert library.video('aaaaaaaaaaa')['gone'] != 'later'     # keeps when it first went
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    monkeypatch.setattr(fetcher, 'pipeline', lambda job, *a: write_playlist(job.video_id, 2, True))
    monkeypatch.setattr(cache, 'evict', lambda now: None)
    assert fetcher.start('aaaaaaaaaaa', background=False)['state'] == 'ready' and library.video('aaaaaaaaaaa')['gone'] is None


def test_a_video_not_offered_in_this_country_is_hidden_as_blocked_not_gone(monkeypatch):
    seed()
    def blocked(url, signed_in=False): raise ytdlp.YtdlpError('[youtube] aaaaaaaaaaa: The uploader has not made this video available in your country')
    monkeypatch.setattr(ytdlp, 'probe', blocked)
    assert fetcher.start('aaaaaaaaaaa', background=False)['state'] == 'failed'
    v = library.video('aaaaaaaaaaa')
    assert v['gone'] is None and 'aaaaaaaaaaa' not in [x['id'] for x in library.videos()['videos']]
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO)
    monkeypatch.setattr(fetcher, 'pipeline', lambda job, *a: write_playlist(job.video_id, 2, True))
    monkeypatch.setattr(cache, 'evict', lambda now: None)
    assert fetcher.start('aaaaaaaaaaa', background=False)['state'] == 'ready' and 'aaaaaaaaaaa' in [x['id'] for x in library.videos()['videos']]


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


def test_a_retry_is_judged_by_its_own_log_lines(monkeypatch):
    seed(); cache.begin('aaaaaaaaaaa', cache.stamp())
    logs = [b'ERROR: unable to write data: [Errno 32] Broken pipe\n', b'[https @ 0x1] HTTP error 403 Forbidden\n']
    made = []
    def popen(cmd, **kw):
        made.append(Proc(cmd, 1 if len(made) % 3 == 0 else 0, **kw))
        if len(made) % 3 == 0:
            with open(os.path.join(cache.folder('aaaaaaaaaaa'), fetcher.LOG), 'ab') as f: f.write(logs.pop(0))
        return made[-1]
    monkeypatch.setattr(subprocess, 'Popen', popen); monkeypatch.setattr(fetcher, 'watch', lambda j: False)
    job = fetcher.Job('aaaaaaaaaaa')
    assert fetcher.attempts(job, lambda: fetcher.pipeline(job, '/c/probe.json', '399', '140', 8)) == '[https @ 0x1] HTTP error 403 Forbidden'
    with open(os.path.join(cache.folder('aaaaaaaaaaa'), fetcher.LOG), encoding='utf8') as f: assert 'Broken pipe' in f.read()     # both runs stay in the log
    assert len(made) == 6 and logs == []


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
    asked_signed_in = threading.Event()        # the losing probe runs on its own thread and may start after the winner returns
    def probe(url, signed_in=False):
        if signed_in: asked_signed_in.set()
        return dict(INFO, epoch=100, formats=[dict(f, available_at=100) for f in INFO['formats']])
    monkeypatch.setattr(ytdlp, 'probe', probe)
    assert chosen_ids(fetcher.choose('https://u')) == ('399', '140', False) and asked_signed_in.wait(5)


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


# iPlayer episodes: ffmpeg alone, from iplayer.stream (or yt-dlp's muxed HLS when that fails).

from tubes import iplayer  # noqa: E402

E = 'm0000001'


def seed_episode(e=E, duration=6.0, fresh=True):
    if fresh: seed()
    from tubes import db
    with db.connect() as con:
        con.execute("INSERT INTO videos (id, platform, channel_id, title, published, duration) VALUES (?, 'iplayer', 'b0000001', 'Chapter 1', '2026-01-01T00:00:00+00:00', ?)", (e, duration))


def test_direct_command():
    cmd = fetcher.direct_command('https://cdn.test/x.m3u8')
    assert cmd[6:16] == ['-i', 'https://cdn.test/x.m3u8', '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', '-bsf:a', 'aac_adtstoasc'] and cmd[-1] == 'index.m3u8'


def test_source_url_by_platform():
    seed_episode(); seed_episode('bad id!', fresh=False)
    assert fetcher.source_url(E) == ('iplayer', 'https://www.bbc.co.uk/iplayer/episode/m0000001')
    assert fetcher.source_url('aaaaaaaaaaa') == ('youtube', 'https://www.youtube.com/watch?v=aaaaaaaaaaa')
    assert fetcher.platform('zzzzzzzzzzz') == 'youtube'
    with pytest.raises(fetcher.FetchError, match="'bad id!' is not an iPlayer episode id"): fetcher.start('bad id!')


def test_an_iplayer_fetch_runs_ffmpeg_on_the_chosen_stream(monkeypatch):
    seed_episode()
    monkeypatch.setattr(iplayer, 'stream', lambda pid, h: dict(url='https://cdn.test/fhd.m3u8', height=1080, fps=50, label='1080p50 H.264 + AAC'))
    seen = []
    def fake_direct(job, url, duration):
        seen.append((url, duration)); write_playlist(job.video_id, 2, True); return None
    monkeypatch.setattr(fetcher, 'direct_pipeline', fake_direct)
    monkeypatch.setattr(ytdlp, 'probe', lambda *a, **kw: pytest.fail('yt-dlp is not asked when iPlayer answers'))
    evicted = []; monkeypatch.setattr(cache, 'evict', lambda now: evicted.append(now))
    fetcher.start(E, 'Chapter 1', 'Harbour Lights', background=False)
    assert cache.entry(E)['title'] == 'Chapter 1' and seen == [('https://cdn.test/fhd.m3u8', 6.0)] and len(evicted) == 1
    assert cache.status(E)['formats'] == '1080p50 H.264 + AAC' and cache.status(E)['state'] == 'ready'


def test_an_iplayer_fetch_falls_back_to_yt_dlp(monkeypatch):
    seed_episode()
    def broken(pid, h): raise iplayer.IplayerError('iPlayer did not answer with JSON.')
    monkeypatch.setattr(iplayer, 'stream', broken)
    info = dict(formats=[dict(format_id='hls-1', vcodec='avc1.64001F', acodec='mp4a.40.2', protocol='m3u8_native', height=720, tbr=5000, url='https://cdn.test/720.m3u8'),
                         dict(format_id='hls-0', vcodec='avc1.4D401F', acodec='mp4a.40.2', protocol='m3u8_native', height=540, tbr=2800, url='https://cdn.test/540.m3u8'),
                         dict(format_id='dash-v', vcodec='avc3.640020', acodec='none', protocol='http_dash_segments', height=720, url='https://cdn.test/x.mpd')])
    asked = []; monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: asked.append(url) or info)
    assert fetcher.iplayer_stream(E, 'https://www.bbc.co.uk/iplayer/episode/m0000001', 1080) == ('https://cdn.test/720.m3u8', '720p H.264 + AAC (yt-dlp)')
    assert fetcher.iplayer_stream(E, 'u', 600) == ('https://cdn.test/540.m3u8', '540p H.264 + AAC (yt-dlp)')
    assert asked[0] == 'https://www.bbc.co.uk/iplayer/episode/m0000001'
    with pytest.raises(iplayer.IplayerError, match='did not answer with JSON'): fetcher.iplayer_stream(E, 'u', 200)       # nothing fits: iPlayer's own reason
    def no_ytdlp(url, signed_in=False): raise ytdlp.YtdlpError('yt-dlp is not installed')
    monkeypatch.setattr(ytdlp, 'probe', no_ytdlp)
    with pytest.raises(iplayer.IplayerError, match='did not answer with JSON'): fetcher.iplayer_stream(E, 'u', 1080)


@pytest.mark.parametrize('why', ['iPlayer only plays in the UK, and this server is not seen as in the UK.', 'iPlayer no longer offers this episode.'])
def test_an_iplayer_refusal_that_yt_dlp_cannot_help_is_recorded(monkeypatch, why):
    seed_episode()
    def refuse(pid, h): raise iplayer.IplayerError(why)
    monkeypatch.setattr(iplayer, 'stream', refuse)
    monkeypatch.setattr(ytdlp, 'probe', lambda *a, **kw: pytest.fail('yt-dlp cannot help here'))
    st = fetcher.start(E, background=False)
    assert (st['state'], st['error']) == ('failed', why)


def test_an_iplayer_fetch_records_why_it_failed_or_stopped(monkeypatch):
    seed_episode()
    monkeypatch.setattr(iplayer, 'stream', lambda pid, h: dict(url='u', label='720p50 H.264 + AAC'))
    def cannot(job, url, duration): raise OSError('no ffmpeg')
    monkeypatch.setattr(fetcher, 'direct_pipeline', cannot)
    assert fetcher.start(E, background=False)['error'] == 'Could not start the fetch: no ffmpeg'
    def stopped(job, url, duration):
        job.cancelled = True; return None
    monkeypatch.setattr(fetcher, 'direct_pipeline', stopped)
    assert fetcher.start(E, background=False)['error'] == 'The fetch was stopped.'


def test_direct_pipeline_runs_ffmpeg_and_reads_the_result(monkeypatch):
    seed_episode(); cache.begin(E, cache.stamp())
    made = []
    def popen(cmd, **kw):
        made.append(Proc(cmd, 0, **kw)); write_playlist(E, 2, True); return made[-1]
    monkeypatch.setattr(subprocess, 'Popen', popen)
    monkeypatch.setattr(fetcher, 'watch', lambda j: False)
    job = fetcher.Job(E)
    assert fetcher.direct_pipeline(job, 'https://cdn.test/x.m3u8', 8) is None
    assert made[0].cmd[7] == 'https://cdn.test/x.m3u8' and made[0].kw['cwd'] == cache.folder(E)
    job2 = fetcher.Job(E); job2.cancelled = True
    killed = []; monkeypatch.setattr(oslib, 'kill_tree', lambda pid: killed.append(pid))
    assert fetcher.direct_pipeline(job2, 'u', 8) == 'The fetch was stopped.'


def test_an_iplayer_fetch_needs_no_pipes(monkeypatch):
    seed_episode(); monkeypatch.setattr(oslib, 'CAN_PASS_FDS', False)
    monkeypatch.setattr(iplayer, 'stream', lambda pid, h: dict(url='u', label='720p50 H.264 + AAC'))
    monkeypatch.setattr(fetcher, 'direct_pipeline', lambda job, url, d: write_playlist(job.video_id, 1, True))
    assert fetcher.start(E, background=False)['state'] == 'ready'


def failing(monkeypatch, results):
    """A fetch whose download runs give `results` in turn, each writing a line to the log; returns the runs."""
    seed()
    monkeypatch.setattr(ytdlp, 'probe', lambda url, signed_in=False: INFO); monkeypatch.setattr(cache, 'evict', lambda now: None)
    runs = []
    def fake_pipeline(job, *a):
        runs.append(1)
        with open(os.path.join(cache.folder(job.video_id), fetcher.LOG), 'a') as f: f.write(f'run {len(runs)}\n')
        r = results[len(runs) - 1]
        if r is None: write_playlist(job.video_id, 2, True)
        return r
    monkeypatch.setattr(fetcher, 'pipeline', fake_pipeline)
    return runs


def test_a_fetch_that_fails_twice_keeps_its_log_and_says_why_in_the_server_log(monkeypatch, capsys):
    runs = failing(monkeypatch, ['Broken pipe', 'The fetch ended before the video was complete.'])
    st = fetcher.start('aaaaaaaaaaa', background=False)
    assert (st['state'], st['error'], len(runs)) == ('failed', 'The fetch ended before the video was complete.', 2)
    with open(os.path.join(settings.data_dir(), fetcher.FAILED_LOGS, 'aaaaaaaaaaa.log')) as f: kept = f.read()
    assert kept == 'run 1\n[tubes] attempt 1 failed: Broken pipe; trying again\nrun 2\n[tubes] failed: The fetch ended before the video was complete.\n'
    assert not os.path.exists(cache.folder('aaaaaaaaaaa'))                           # the copy's own files still go
    assert 'tubes: fetching aaaaaaaaaaa failed: The fetch ended before the video was complete.' in capsys.readouterr().err


def test_a_probe_failure_has_no_log_to_keep(monkeypatch, capsys):
    seed()
    def refuse(url, signed_in=False): raise ytdlp.YtdlpError('Sign in to confirm you are not a bot')
    monkeypatch.setattr(ytdlp, 'probe', refuse)
    assert fetcher.start('aaaaaaaaaaa', background=False)['state'] == 'failed'
    assert not os.path.exists(os.path.join(settings.data_dir(), fetcher.FAILED_LOGS, 'aaaaaaaaaaa.log')) and 'not a bot' in capsys.readouterr().err


@pytest.mark.parametrize('error', ['Nothing arrived for 120 s, so the fetch was stopped.', '[youtube] x: Video unavailable. This video has been removed by the uploader',
                                   '[youtube] x: The uploader has not made this video available in your country'])
def test_stalls_and_youtube_saying_no_are_not_run_again(monkeypatch, error):
    runs = failing(monkeypatch, [error, None])
    assert fetcher.start('aaaaaaaaaaa', background=False)['error'] == error and runs == [1]


def test_keeping_a_log_never_fails_the_fetch(monkeypatch, tmp_path):
    fetcher.note('zzzzzzzzzzz', 'no folder')                                          # nothing to write into: ignored
    cache.begin('aaaaaaaaaaa', cache.stamp()); fetcher.note('aaaaaaaaaaa', 'ran')
    with open(os.path.join(settings.data_dir(), fetcher.FAILED_LOGS), 'w') as f: f.write('a file where the folder goes')
    fetcher.keep_log('aaaaaaaaaaa', 'it broke')                                      # nowhere to keep it: the reason is still recorded
