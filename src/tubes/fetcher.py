"""Fetching a video into the cache while it plays.

YouTube serves 1080p as separate video and audio streams, which yt-dlp normally downloads whole and merges at the end, so nothing can play until
it finishes. Here two yt-dlp processes write the two streams to stdout (`-o -`), each into a pipe that ffmpeg reads as `pipe:<fd>`, and ffmpeg
copies them, without re-encoding, into HLS: an init segment and 4-second fMP4 segments under a playlist that grows (`event`). The player starts
as soon as the first segment is listed and follows the playlist as it grows. Measured on the home server (2026-11-09): the first segment exists
about 2 s after the start, and downloads run at 100-250 Mbit/s, 20-50 times what 1080p playback needs. ffmpeg cannot fetch YouTube's stream URLs
itself (403), which is why yt-dlp does the downloading.

Fetches run in background threads of the server process, one per video, at most `MAX_RUNNING` at a time; a play of a video already being fetched
joins it. The pipes need file descriptors passed by number, which Windows lacks, so fetching runs on Linux and macOS only (oslib.CAN_PASS_FDS)."""
import os, subprocess, threading, time

from tubes import cache, oslib, settings, ytdlp

MAX_RUNNING = 3
STALL_SECONDS = 120          # a fetch whose playlist has not grown for this long is stopped
POLL_SECONDS = 1.0
LOG = 'fetch.log'

_lock = threading.Lock()
_running = {}                # video_id -> Job


class FetchError(RuntimeError):
    """A fetch cannot start; the message says why, in a sentence."""


class Job:
    def __init__(self, video_id):
        self.video_id, self.procs, self.cancelled, self.thread = video_id, [], False, None

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


def stream_command(fmt_id, url):
    return ytdlp.base_command() + ['--no-part', '-f', str(fmt_id), '-o', '-', url]


def running():
    with _lock: return sorted(_running)


def start(video_id, title=None, channel=None, background=True):
    """Make sure the video is fetched or being fetched; returns its cache status. Raises FetchError when it cannot start. `title` and `channel`
    are what the library calls it, kept with the copy for the Cache screen."""
    try: url = ytdlp.watch_url(video_id)
    except ytdlp.YtdlpError as e: raise FetchError(str(e)) from None
    with _lock:
        if video_id in _running: return cache.status(video_id)
        st = cache.status(video_id)
        if st['state'] == 'ready' and st['complete']: return st      # a ready row whose files are gone (the cache folder moved, or was cleared by hand) is fetched again
        if not oslib.CAN_PASS_FDS: raise FetchError('Fetching needs Linux or macOS.')
        if len(_running) >= MAX_RUNNING: raise FetchError(f'{MAX_RUNNING} videos are already being fetched; try again when one finishes.')
        job = _running[video_id] = Job(video_id)
        cache.begin(video_id, cache.stamp(), title, channel)
    if not background: _run(job, url); return cache.status(video_id)
    job.thread = threading.Thread(target=_run, args=(job, url), name=f'fetch-{video_id}', daemon=True); job.thread.start()
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
        info = ytdlp.probe(url)
        video, audio = ytdlp.choose_formats(info.get('formats') or [], settings.get('max_height'))
        cache.set_formats(job.video_id, ytdlp.describe(video, audio))
        if job.cancelled: return                     # deleted while probing: start nothing (finally records it as stopped)
        error = pipeline(job, url, video['format_id'], audio['format_id'], info.get('duration'))
    except ytdlp.YtdlpError as e: error = str(e)
    except OSError as e: error = f'Could not start the fetch: {e}'
    finally:
        if job.cancelled and not error: error = 'The fetch was stopped.'
        cache.finish(job.video_id, cache.stamp(), error)
        with _lock: _running.pop(job.video_id, None)
    if not error: cache.evict(cache.utcnow())


def pipeline(job, url, video_fmt, audio_fmt, duration=None):
    """Run yt-dlp x2 into ffmpeg until all three end; returns None when the playlist is complete, else the reason it is not."""
    out = cache.folder(job.video_id)
    rv, wv = os.pipe(); ra, wa = os.pipe()
    with open(os.path.join(out, LOG), 'ab') as log:
        try:
            ff = subprocess.Popen(hls_command(video_fd=rv, audio_fd=ra), cwd=out, pass_fds=(rv, ra), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
            job.procs.append(ff)
            job.procs.append(subprocess.Popen(stream_command(video_fmt, url), stdin=subprocess.DEVNULL, stdout=wv, stderr=log))
            job.procs.append(subprocess.Popen(stream_command(audio_fmt, url), stdin=subprocess.DEVNULL, stdout=wa, stderr=log))
        except OSError:
            job.stop(); raise
        finally:
            for fd in (rv, wv, ra, wa): os.close(fd)        # the children hold their own copies; ours would keep the pipes open and ffmpeg would never see the end
        if job.cancelled: job.stop()                  # a stop that came while they were starting saw only some of them
        stalled = not job.cancelled and watch(job)
    codes = [p.wait() for p in job.procs]
    if stalled: return f'Nothing arrived for {STALL_SECONDS} s, so the fetch was stopped.'
    if job.cancelled: return 'The fetch was stopped.'
    if any(codes):
        with open(os.path.join(out, LOG), encoding='utf8', errors='replace') as f: why = ytdlp.last_error(f.read())
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
