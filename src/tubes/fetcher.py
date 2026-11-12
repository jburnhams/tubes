"""Fetching a video into the cache while it plays.

YouTube serves 1080p as separate video and audio streams, which yt-dlp normally downloads whole and merges at the end, so nothing can play until
it finishes. Here two yt-dlp processes write the two streams to stdout (`-o -`), each into a pipe that ffmpeg reads as `pipe:<fd>`, and ffmpeg
copies them, without re-encoding, into HLS: an init segment and 4-second fMP4 segments under a playlist that grows (`event`). The player starts
as soon as the first segment is listed and follows the playlist as it grows. Measured on the home server (2026-11-09): the first segment exists
about 2 s after the start, and downloads run at 100-250 Mbit/s, 20-50 times what 1080p playback needs. ffmpeg cannot fetch YouTube's stream URLs
itself (403), which is why yt-dlp does the downloading.

yt-dlp works out a video's stream URLs once (the probe, about 3.5 s) and the two downloads reuse them (`--load-info-json`) instead of each
working them out again: that saves 2-4 s before the first segment, and the chosen formats cannot vanish between two extractions. Measured on
the home server on eight library videos (2026-11-09, docs/progress.md): YouTube refuses the fast `visionos` client for most of them, yt-dlp
falls back to `web_embedded`, and that client makes the download wait 4-10 s "as required by the site" (an ad); skipping the wait gets a 403.
So the first segment arrives about 3-4.5 s after Play without that wait and 8-13 s with it. About one probe in eight comes back without
usable streams (YouTube's SABR-only answer), so a probe whose streams cannot be chosen is tried once more. A download that fails (ffmpeg or a yt-dlp
stops early: seen once as yt-dlp's "Broken pipe" after ffmpeg had quit, 2026-11-12, when playing again worked) is run once more with
the same probe and streams before the copy is marked failed (`attempts`); a stall (two minutes with nothing) and YouTube saying the
video is gone or blocked are not run again. A failed fetch's log is kept as `failed-fetches/<id>.log` under the data folder (the copy's
folder, and the log in it, are deleted), and the reason goes to the server's log, so the next such failure can be explained.

iPlayer episodes (iplayer.py) need no yt-dlp: their HLS playlists carry tokened segment addresses that ffmpeg reads itself, muxed H.264 +
AAC in MPEG-TS, copied into the same fMP4 HLS (`direct_command`; the AAC needs `aac_adtstoasc` to leave TS). iplayer.stream picks 1080p50
when the episode has it, else 720p50. Should the BBC's services stop answering as iplayer.py expects, yt-dlp's own iPlayer support is
asked for its best muxed HLS stream instead (720p at most, as of 2026-11), so a change there costs quality rather than playback.

Fetches run in background threads of the server process, one per video, at most `MAX_RUNNING` at a time; a play of a video already being fetched
joins it. The pipes need file descriptors passed by number, which Windows lacks, so fetching from YouTube runs on Linux and macOS only (oslib.CAN_PASS_FDS); an iPlayer fetch has no pipes and runs anywhere."""
import json, os, shutil, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

from tubes import cache, catalogue, db, iplayer, oslib, settings, ytdlp

MAX_RUNNING = 3
ATTEMPTS = 2                 # a download that fails is run once more before the copy is marked failed (most failures are passing: a retry by hand worked)
STALL_SECONDS = 120          # a fetch whose playlist has not grown for this long is stopped
POLL_SECONDS = 1.0
LOG = 'fetch.log'
FAILED_LOGS = 'failed-fetches'   # under the data folder: the last failed fetch's log per video, for finding out why
INFO = 'probe.json'           # the probe yt-dlp's downloads reuse; never served (cache.FILE_NAME), deleted when the fetch ends

_lock = threading.Lock()
_running = {}                # video_id -> Job


class FetchError(RuntimeError):
    """A fetch cannot start; the message says why, in a sentence."""


class Job:
    def __init__(self, video_id):
        self.video_id, self.procs, self.cancelled, self.thread = video_id, [], False, None
        self.log_from = 0          # where this attempt's lines start in fetch.log (attempts); its reason is read from there only

    def stop(self, cancel=True):
        self.cancelled = self.cancelled or cancel
        for p in self.procs:
            if p.poll() is None: oslib.kill_tree(p.pid)


def hls_command(out_name=cache.PLAYLIST, video_fd=3, audio_fd=4):
    """ffmpeg reading video from fd `video_fd` and audio from fd `audio_fd`, copying both into growing fMP4 HLS in the working folder."""
    return [settings.get('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-i', f'pipe:{video_fd}', '-i', f'pipe:{audio_fd}', '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy',
            '-f', 'hls', '-hls_time', '4', '-hls_segment_type', 'fmp4', '-hls_playlist_type', 'event',
            '-hls_flags', 'independent_segments+temp_file', '-hls_fmp4_init_filename', 'init.mp4', '-hls_segment_filename', 'seg_%05d.m4s', out_name]


def direct_command(url, out_name=cache.PLAYLIST):
    """ffmpeg reading one muxed HLS stream itself (an iPlayer episode), copying it into growing fMP4 HLS in the working folder."""
    return [settings.get('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', url, '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
            '-f', 'hls', '-hls_time', '4', '-hls_segment_type', 'fmp4', '-hls_playlist_type', 'event',
            '-hls_flags', 'independent_segments+temp_file', '-hls_fmp4_init_filename', 'init.mp4', '-hls_segment_filename', 'seg_%05d.m4s', out_name]


def stream_command(fmt_id, info_path, signed_in=False):
    return ytdlp.base_command(signed_in) + ['--no-part', '-f', str(fmt_id), '--load-info-json', info_path, '-o', '-']


def choose_once(url, signed_in=False):
    """One probe and its streams: (info, video format, audio format, signed_in)."""
    info = ytdlp.probe(url, signed_in)
    return (info, *ytdlp.choose_formats(info.get('formats') or [], settings.get('max_height')), signed_in)


def choose_both(url):
    """With a signed-in browser set: probe signed out (the fast `visionos` client) and signed in at once. The signed-out answer wins when its
    streams have no ad wait (visionos played; about 1.3 s sooner); else the signed-in one; else, when the session cannot be read (browser
    signed out, keyring locked), the signed-out one with its wait. Running both costs neither any time (measured)."""
    pool = ThreadPoolExecutor(2)
    try:
        out, inn = pool.submit(choose_once, url, False), pool.submit(choose_once, url, True)
        try:
            fast = out.result()
            if ytdlp.ad_wait(fast[0], fast[1], fast[2]) == 0: return fast
        except ytdlp.YtdlpError: fast = None
        try: return inn.result()
        except ytdlp.YtdlpError:
            if fast: return fast
            raise
    finally: pool.shutdown(wait=False)        # a probe that lost is left to finish on its own


def choose(url):
    """Probe the video and choose its streams: (info, video format, audio format, signed_in). A probe without usable streams is tried once more."""
    for attempt in (1, 2):
        try: return choose_both(url) if ytdlp.signed_in_available() else choose_once(url)
        except ytdlp.YtdlpError:
            if attempt == 2: raise


def platform(video_id):
    """Where a library video comes from (`youtube` when the library does not have it, as before there was a choice)."""
    with db.connect() as con: r = con.execute('SELECT platform, duration FROM videos WHERE id = ?', (video_id,)).fetchone()
    return (r[0] if r else None) or 'youtube'


def source_url(video_id):
    """(platform, the link to fetch from) for a library video, or FetchError when its id cannot be one (it goes on a command line)."""
    where = platform(video_id)
    if where == 'iplayer':
        if not iplayer.PID.match(video_id or ''): raise FetchError(f'{video_id!r} is not an iPlayer episode id.')
        return where, iplayer.episode_url(video_id)
    try: return where, ytdlp.watch_url(video_id)
    except ytdlp.YtdlpError as e: raise FetchError(str(e)) from None


def iplayer_stream(video_id, url, max_height):
    """(stream URL, label) for an iPlayer episode: iplayer.stream, else yt-dlp's best muxed HLS stream (see the module's notes); raises
    IplayerError with iPlayer's reason when neither has one."""
    try: s = iplayer.stream(video_id, max_height); return s['url'], s['label']
    except iplayer.IplayerError as e:
        if 'only plays in the UK' in str(e) or 'no longer offers' in str(e): raise
        first = e
    try: info = ytdlp.probe(url)
    except ytdlp.YtdlpError: raise first from None
    muxed = [f for f in info.get('formats') or [] if f.get('vcodec') not in (None, 'none') and f.get('acodec') not in (None, 'none')
             and (f.get('protocol') or '').startswith('m3u8') and (f.get('height') or 0) <= max_height and f.get('url')]
    if not muxed: raise first
    best = max(muxed, key=lambda f: (f.get('height') or 0, f.get('tbr') or 0))
    return best['url'], f"{best.get('height')}p H.264 + AAC (yt-dlp)"


def running():
    with _lock: return sorted(_running)


def start(video_id, title=None, channel=None, background=True):
    """Make sure the video is fetched or being fetched; returns its cache status. Raises FetchError when it cannot start. `title` and `channel`
    are what the library calls it, kept with the copy for the Cache screen."""
    where, url = source_url(video_id)
    with _lock:
        if video_id in _running: return cache.status(video_id)
        st = cache.status(video_id)
        if st['state'] == 'ready' and st['complete']: return st      # a ready row whose files are gone (the cache folder moved, or was cleared by hand) is fetched again
        if where == 'youtube' and not oslib.CAN_PASS_FDS: raise FetchError('Fetching needs Linux or macOS.')      # an iPlayer fetch passes no pipes
        if len(_running) >= MAX_RUNNING: raise FetchError(f'{MAX_RUNNING} videos are already being fetched; try again when one finishes.')
        job = _running[video_id] = Job(video_id)
        cache.begin(video_id, cache.stamp(), title, channel)
    run = _run_iplayer if where == 'iplayer' else _run
    if not background: run(job, url); return cache.status(video_id)
    job.thread = threading.Thread(target=run, args=(job, url), name=f'fetch-{video_id}', daemon=True); job.thread.start()
    return cache.status(video_id)


def cancel(video_ids):
    """Stop the fetches of these videos (used before their copies are deleted)."""
    with _lock: jobs = [_running[v] for v in video_ids if v in _running]
    for j in jobs: j.stop()
    for j in jobs:
        if j.thread is not None: j.thread.join(timeout=30)


def _run(job, url):
    """Probe, choose the streams, run the pipeline, record the result, then trim the cache. Never raises: a failure is recorded on the video's copy."""
    error = None
    try:
        info, video, audio, signed_in = choose(url)
        cache.set_formats(job.video_id, ytdlp.describe(video, audio))
        if job.cancelled: return                     # deleted while probing: start nothing (finally records it as stopped)
        info_path = os.path.join(cache.folder(job.video_id), INFO)
        with open(info_path, 'w', encoding='utf8') as f: json.dump(info, f)
        error = attempts(job, lambda: pipeline(job, info_path, video['format_id'], audio['format_id'], info.get('duration'), signed_in))
    except ytdlp.YtdlpError as e: error = str(e)
    except OSError as e: error = f'Could not start the fetch: {e}'
    finally:
        if job.cancelled and not error: error = 'The fetch was stopped.'
        try: os.remove(os.path.join(cache.folder(job.video_id), INFO))     # its stream URLs expire within hours anyway
        except OSError: pass
        if error: keep_log(job.video_id, error)
        cache.finish(job.video_id, cache.stamp(), error)
        with _lock: _running.pop(job.video_id, None)
    if ytdlp.says_blocked(error): catalogue.mark_blocked(job.video_id)   # not offered in this country: hidden until a fetch succeeds
    elif ytdlp.says_gone(error): catalogue.mark_gone(job.video_id)     # hidden from the lists until a recheck or a later fetch finds it
    if not error: catalogue.mark_found(job.video_id); cache.evict(cache.utcnow())


def _run_iplayer(job, url):
    """As `_run`, for an iPlayer episode: choose its stream, then ffmpeg alone (see the module's notes)."""
    error = None
    try:
        with db.connect() as con: r = con.execute('SELECT duration FROM videos WHERE id = ?', (job.video_id,)).fetchone()
        stream_url, label = iplayer_stream(job.video_id, url, settings.get('max_height'))
        cache.set_formats(job.video_id, label)
        if not job.cancelled: error = attempts(job, lambda: direct_pipeline(job, stream_url, r[0] if r else None))
    except iplayer.IplayerError as e: error = str(e)
    except OSError as e: error = f'Could not start the fetch: {e}'
    finally:
        if job.cancelled and not error: error = 'The fetch was stopped.'
        if error: keep_log(job.video_id, error)
        cache.finish(job.video_id, cache.stamp(), error)
        with _lock: _running.pop(job.video_id, None)
    if not error: catalogue.mark_found(job.video_id); cache.evict(cache.utcnow())


def attempts(job, run):
    """Run one download (`pipeline` or `direct_pipeline`) up to ATTEMPTS times, until it completes or is stopped; returns the last one's reason.
    A retry reuses the probe and the same streams, so ffmpeg cuts the same segments under the same names: it rewrites the playlist and
    overwrites the files in place while the player keeps playing what had arrived. Both runs write to the one fetch.log, the failure noted."""
    attempt = 1
    while True:
        try: job.log_from = os.path.getsize(os.path.join(cache.folder(job.video_id), LOG))
        except OSError: job.log_from = 0
        error = run()
        if not retryable(job, error) or attempt >= ATTEMPTS: return error
        note(job.video_id, f'[tubes] attempt {attempt} failed: {error}; trying again')
        job.procs = []           # the finished processes; a stop now reaches only the new ones
        attempt += 1


def retryable(job, error):
    """Whether a failed download is worth one more run: not stopped, not stalled (that already waited two minutes), not YouTube saying no."""
    return bool(error) and not job.cancelled and not error.startswith('Nothing arrived') and not ytdlp.says_gone(error) and not ytdlp.says_blocked(error)


def note(video_id, line):
    """Add a line of our own to the fetch's log, between one run's output and the next."""
    try:
        with open(os.path.join(cache.folder(video_id), LOG), 'a', encoding='utf8') as f: f.write(line + '\n')
    except OSError: pass


def keep_log(video_id, error):
    """Before a failed copy's folder is deleted (cache.finish), keep its log as `failed-fetches/<id>.log` and say why in the server's log."""
    print(f'tubes: fetching {video_id} failed: {error}', file=sys.stderr, flush=True)
    path = os.path.join(cache.folder(video_id), LOG)
    if not os.path.exists(path): return          # it failed before a download ran: the reason is on the copy and in the server's log
    note(video_id, f'[tubes] failed: {error}')
    try:
        keep = os.path.join(settings.data_dir(), FAILED_LOGS); os.makedirs(keep, exist_ok=True)
        shutil.copyfile(path, os.path.join(keep, cache.folder_name(video_id) + '.log'))
    except OSError: pass


def direct_pipeline(job, url, duration=None):
    """Run ffmpeg on one stream until it ends; returns None when the playlist is complete, else the reason it is not (as `pipeline`)."""
    out = cache.folder(job.video_id)
    with open(os.path.join(out, LOG), 'ab') as log:
        job.procs.append(subprocess.Popen(direct_command(url), cwd=out, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log))
        if job.cancelled: job.stop()
        stalled = not job.cancelled and watch(job)
    return outcome(job, [p.wait() for p in job.procs], stalled, duration)


def pipeline(job, info_path, video_fmt, audio_fmt, duration=None, signed_in=False):
    """Run yt-dlp x2 into ffmpeg until all three end; returns None when the playlist is complete, else the reason it is not."""
    out = cache.folder(job.video_id)
    rv, wv = os.pipe(); ra, wa = os.pipe()
    with open(os.path.join(out, LOG), 'ab') as log:
        try:
            ff = subprocess.Popen(hls_command(video_fd=rv, audio_fd=ra), cwd=out, pass_fds=(rv, ra), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
            job.procs.append(ff)
            job.procs.append(subprocess.Popen(stream_command(video_fmt, info_path, signed_in), stdin=subprocess.DEVNULL, stdout=wv, stderr=log))
            job.procs.append(subprocess.Popen(stream_command(audio_fmt, info_path, signed_in), stdin=subprocess.DEVNULL, stdout=wa, stderr=log))
        except OSError:
            job.stop(); raise
        finally:
            for fd in (rv, wv, ra, wa): os.close(fd)        # the children hold their own copies; ours would keep the pipes open and ffmpeg would never see the end
        if job.cancelled: job.stop()                  # a stop that came while they were starting saw only some of them
        stalled = not job.cancelled and watch(job)
    return outcome(job, [p.wait() for p in job.procs], stalled, duration)


def outcome(job, codes, stalled, duration):
    """Why the copy the processes made is not complete (None when it is), from their exit codes, the log and the playlist."""
    out = cache.folder(job.video_id)
    if stalled: return f'Nothing arrived for {STALL_SECONDS} s, so the fetch was stopped.'
    if job.cancelled: return 'The fetch was stopped.'
    if any(codes):
        with open(os.path.join(out, LOG), 'rb') as f: f.seek(job.log_from); why = ytdlp.last_error(f.read().decode('utf8', 'replace'))     # this attempt's lines: an earlier one's ERROR would win
        return why or f'The fetch failed (exit codes {codes}).'
    pl = cache.read_playlist(job.video_id)
    if not pl['complete'] or pl['segments'] == 0: return 'The fetch ended before the video was complete.'
    if duration and pl['seconds'] < duration - max(10, duration * 0.05): return f'Only {pl["seconds"]:.0f} s of {duration:.0f} s arrived.'
    return None


def watch(job, clock=time.monotonic, sleep=time.sleep):
    """Wait for the processes to end; stop them if the playlist stops growing for STALL_SECONDS. Returns True when it stalled."""
    last_size, last_change = -1, clock()
    while any(p.poll() is None for p in job.procs):
        if job.cancelled: job.stop(); return False
        size = cache.folder_bytes(cache.folder(job.video_id))
        if size != last_size: last_size, last_change = size, clock()
        elif clock() - last_change > STALL_SECONDS:
            job.stop(cancel=False); return True
        sleep(POLL_SECONDS)
    return False


def ffmpeg_version():
    """ffmpeg's version line, or None when it cannot be run."""
    try: p = subprocess.run([settings.get('ffmpeg'), '-version'], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired): return None
    return ((p.stdout.splitlines() or [''])[0].strip() or None) if p.returncode == 0 else None
