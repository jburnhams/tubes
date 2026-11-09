"""Everything that talks to yt-dlp: probing one video and choosing the streams to fetch.

yt-dlp runs as a command, not as a library: it is upgraded daily outside this app (YouTube breakage is fixed upstream within days), and a
command keeps a crash or a hang in its own process, with a timeout. Measured on the home server (docs/progress.md, 2026-11-09):

- `player_client=visionos` starts a download in about 2 s, against 7.8 s for the default clients, which YouTube makes wait 4 s first.
  But YouTube refuses it for many videos, and yt-dlp's fallback (`web_embedded`) waits 4-10 s for an ad before downloading.
- Signed in (`cookies_from_browser`) to a Premium account there is no ad wait for any client: the first segment came 5-7 s after Play on
  every test video, against 8-13 s signed out where the ad wait applied. `visionos` takes no cookies (yt-dlp skips it), so signed in it is
  dropped and `tv_downgraded` is the fastest client that still offers 1080p (`web_safari` and `tv` gave 360p only). Where `visionos` does play,
  signed out is 1-3 s sooner, so with a browser set both are probed at once (fetcher.choose_both).
- A probe says whether a download must wait: each format's `available_at` against the probe's `epoch` (`ad_wait`). A signed-in probe whose
  session cannot be read (no such profile, keyring unreachable) exits with an error rather than carrying on signed out.
- YouTube offers 1080p as separate video and audio streams. AV1, VP9 and H.264 were all offered; the latest Chrome (the only target) plays
  all three through MSE, so the order is AV1, VP9, H.264: AV1 is about half the size of H.264 at the same height.
- A height-only cap picked 1440p for a widescreen film (2560x1072), so the cap checks width as well (16:9 of the height).
- Some videos carry several auto-dubbed audio tracks; the original is the one yt-dlp ranks highest (`language_preference`) or notes as original."""
import json, re, subprocess

from tubes import settings

CODEC_RANK = (('av01', 0), ('vp09', 1), ('vp9', 1), ('avc1', 2))       # lower is better; anything else is not fetched
PROBE_TIMEOUT = 120
SIGNED_IN_CLIENT = 'tv_downgraded'
VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')


class YtdlpError(RuntimeError):
    """yt-dlp failed, timed out, could not be started, or found nothing usable; the message says which, in a sentence."""


def signed_in_available():
    """Whether a signed-in browser is set (`cookies_from_browser`)."""
    return bool(settings.get('cookies_from_browser'))


def base_command(signed_in=False):
    """yt-dlp and the options every call shares; signed in, it reads the browser's YouTube session (and a probe and its downloads must agree)."""
    cmd = [settings.get('ytdlp'), '--no-warnings', '--no-progress', '--ignore-config']
    client = settings.get('player_client')
    if signed_in:
        cmd += ['--cookies-from-browser', settings.get('cookies_from_browser')]
        if client == 'visionos': client = SIGNED_IN_CLIENT          # visionos takes no cookies; asking for it alone would leave no client
    if client: cmd += ['--extractor-args', f'youtube:player_client={client}']
    return cmd


def watch_url(video_id):
    """The watch link yt-dlp is given for a library video id, or YtdlpError when it is not one (the id goes on a command line and into a URL)."""
    if not VIDEO_ID.match(video_id or ''): raise YtdlpError(f'{video_id!r} is not a YouTube video id.')
    return f'https://www.youtube.com/watch?v={video_id}'


def run_json(args, timeout, signed_in=False):
    """Run yt-dlp with `args` and parse its JSON output."""
    cmd = base_command(signed_in) + list(args)
    try: p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError: raise YtdlpError(f'yt-dlp is not installed (looked for {cmd[0]!r}); set the ytdlp setting to its path.') from None
    except subprocess.TimeoutExpired: raise YtdlpError(f'yt-dlp took longer than {timeout} s and was stopped.') from None
    if p.returncode != 0: raise YtdlpError(last_error(p.stderr) or f'yt-dlp exited with code {p.returncode}.')
    try: return json.loads(p.stdout)
    except ValueError: raise YtdlpError('yt-dlp did not return JSON.') from None


def last_error(text):
    """The most telling line of yt-dlp's or ffmpeg's error output: the last `ERROR:` line, else the last line."""
    lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.startswith('ERROR:')]
    pick = (errors or lines or [''])[-1]
    return pick.removeprefix('ERROR:').strip()[:500]


GONE = re.compile(r'Video unavailable|This video is unavailable|Private video|has been removed|no longer available|account associated with this video has been terminated', re.I)
BUSY = re.compile(r'try again later|not a bot|confirm your age', re.I)


def says_gone(message):
    """Whether yt-dlp's error says YouTube no longer has the video (deleted, private, its account closed), rather than that it refused this
    request (rate limits, bot checks and age checks are worded "try again later", "not a bot" or "confirm your age", sometimes after "Video
    unavailable"). A wrong yes only hides the video until the next recheck finds it (catalogue.recheck)."""
    return bool(message and GONE.search(message) and not BUSY.search(message))


def probe(url, signed_in=False):
    """Full information about one video, with its formats. A signed-in probe whose browser session cannot be read fails (yt-dlp exits with an error in about 0.6 s)."""
    return run_json(['--dump-single-json', '--no-playlist', url], PROBE_TIMEOUT, signed_in)


def ad_wait(info, *chosen):
    """Seconds the download of the chosen formats must wait for an ad (`available_at` against the probe's `epoch`), 0 when none, None when the probe does not say."""
    times = [f.get('available_at') for f in chosen]
    if not chosen or any(t is None for t in times) or info.get('epoch') is None: return None
    return max(0, max(times) - info['epoch'])


def codec_rank(vcodec):
    v = (vcodec or '').lower()
    return next((rank for prefix, rank in CODEC_RANK if v.startswith(prefix)), None)


def choose_formats(formats, max_height):
    """The (video, audio) formats to fetch: the tallest video within `max_height` (and 16:9 of it in width), the better codec at that height,
    then the higher bitrate; and the original audio track at the highest bitrate, AAC before Opus. Raises YtdlpError when either is missing."""
    max_width = round(max_height * 16 / 9)
    videos = [f for f in formats if f.get('vcodec') not in (None, 'none') and f.get('acodec') in (None, 'none') and codec_rank(f.get('vcodec')) is not None
              and (f.get('protocol') or 'https').startswith('http') and not f.get('has_drm')
              and (f.get('height') or 0) <= max_height and (f.get('width') or 0) <= max_width and f.get('height')]
    audios = [f for f in formats if f.get('acodec') not in (None, 'none') and f.get('vcodec') in (None, 'none')
              and (f.get('protocol') or 'https').startswith('http') and not f.get('has_drm')]
    if not videos: raise YtdlpError(f'No video stream at or under {max_height}p in a codec Chrome plays (AV1, VP9 or H.264).')
    if not audios: raise YtdlpError('No separate audio stream was offered.')
    video = max(videos, key=lambda f: (f['height'], -codec_rank(f['vcodec']), f.get('tbr') or 0))
    audio = max(audios, key=lambda f: (f.get('language_preference') or 0, 'original' in (f.get('format_note') or '').lower(),
                                       (f.get('acodec') or '').startswith('mp4a'), f.get('abr') or f.get('tbr') or 0))
    return video, audio


def describe(video, audio):
    """A short label for what was fetched, such as `1080p AV1 + AAC`."""
    names = {'av01': 'AV1', 'vp09': 'VP9', 'vp9': 'VP9', 'avc1': 'H.264', 'mp4a': 'AAC', 'opus': 'Opus'}
    name = lambda c: next((n for p, n in names.items() if (c or '').lower().startswith(p)), (c or '?').split('.')[0])
    return f"{video.get('height')}p {name(video.get('vcodec'))} + {name(audio.get('acodec'))}"


def version():
    """yt-dlp's version, or None when it cannot be run."""
    try: p = subprocess.run([settings.get('ytdlp'), '--version'], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired): return None
    return (p.stdout.strip() or None) if p.returncode == 0 else None
