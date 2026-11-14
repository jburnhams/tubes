"""User settings: one JSON file, `~/.tubes/settings.json` (the folder can be moved with the TUBES_HOME environment variable).

  data_dir         where the cache database (copies and plays) lives. Default: `data/` in this repository (gitignored) until configured.
  cache_dir        where fetched videos are kept, one folder per video. Default: `<data_dir>/cache`.
  cache_limit_gb   how much the cache may hold; eviction starts at 95% of it and stops at 90% (default 1000).
  max_height       the tallest picture to fetch, in pixels (default 1080; wider-than-16:9 pictures are capped by width too).
  player_client    the YouTube client yt-dlp asks as (default `visionos`, which starts downloads without the 4 s wait the default clients get; empty = yt-dlp's own choice).
  cookies_from_browser  a signed-in browser yt-dlp reads the YouTube session from (`--cookies-from-browser`, e.g. `chrome+gnomekeyring`;
                   default empty: signed out). Signed in to a Premium account there are no ad waits before a download starts. Each fetch
                   probes signed out (visionos) and signed in at once, and goes signed out when that has no ad wait, signed in otherwise,
                   and signed out with the wait when the session cannot be read. The cookies stay in the browser, which keeps them fresh.
  half_life_days   how fast a play's weight fades in the eviction score (default 30: a play counts half as much 30 days later).
  protect_days     how long a fetched video that nobody has played yet is kept from eviction (default 7).
  prefetch_seconds  how much of a video's start to fetch ahead of a play, for the videos Home and Up next show (prefetch.py), so they start
                   at once (default 20; more when a part the player skips covers the start; 0 = no prefetching).
  prefetch_per_day  at most this many prefetches a day, to go easy on YouTube (default 150).
  ytdlp, ffmpeg    the commands to run (default `yt-dlp` and `ffmpeg` from PATH).
  history_url      a database that keeps a viewing history (an SQLAlchemy URL, such as `postgresql+psycopg:///mydb`; default empty: none).
  history_table    the table or view in it to read, optionally with its schema (`schema.table`), with the columns account, at, video_id,
                   title, channel_id and channel_name (history.py `sync_database`). `tubes history sync` copies it in, one source per account.
  skip_<category>  what the player does in each kind of segment (segments.py: SponsorBlock's categories, which iPlayer's intro and
                   credits are mapped onto): `off` (nothing, not even drawn), `ask` (a Skip button while it plays) or `auto` (skipped, with
                   Undo). Defaults: sponsor auto; self-promotion, subscribe reminders, intros, credits and previews ask; the rest off.

The environment variables TUBES_DATA, TUBES_CACHE, TUBES_YTDLP, TUBES_FFMPEG, TUBES_HISTORY_URL and TUBES_HISTORY_TABLE override the file (handy for tests and one-off runs). The YouTube key
(YOUTUBE_API_KEY) is only ever in the environment."""
import json, os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(REPO, 'data')

# name -> (default, type, environment override). Folders are handled by data_dir() and cache_dir() because their defaults depend on other settings.
SPEC = {
    'data_dir': (None, str, 'TUBES_DATA'),
    'cache_dir': (None, str, 'TUBES_CACHE'),
    'cache_limit_gb': (1000.0, float, None),
    'max_height': (1080, int, None),
    'player_client': ('visionos', str, None),
    'cookies_from_browser': ('', str, None),
    'half_life_days': (30.0, float, None),
    'protect_days': (7.0, float, None),
    'prefetch_seconds': (20.0, float, None),
    'prefetch_per_day': (150, int, None),
    'ytdlp': ('yt-dlp', str, 'TUBES_YTDLP'),
    'ffmpeg': ('ffmpeg', str, 'TUBES_FFMPEG'),
    'history_url': ('', str, 'TUBES_HISTORY_URL'),
    'history_table': ('', str, 'TUBES_HISTORY_TABLE'),
}
# The kinds of segment the player can skip, SponsorBlock's own categories (https://wiki.sponsor.ajay.app/w/Segment_Categories), with their default.
SKIP_DEFAULTS = dict(sponsor='auto', selfpromo='ask', interaction='ask', intro='ask', outro='ask', preview='ask', hook='off', filler='off', music_offtopic='off')
SKIP_MODES = ('off', 'ask', 'auto')
SPEC.update({f'skip_{c}': (mode, str, None) for c, mode in SKIP_DEFAULTS.items()})
KNOWN = tuple(SPEC)
POSITIVE = ('cache_limit_gb', 'max_height', 'half_life_days')


class SettingError(ValueError):
    """Raised when a setting's value cannot be used."""


def home():
    return os.environ.get('TUBES_HOME') or os.path.join(os.path.expanduser('~'), '.tubes')


def _path(): return os.path.join(home(), 'settings.json')


def load():
    try:
        with open(_path(), encoding='utf8') as f: d = json.load(f)
    except (OSError, ValueError): d = {}
    return d if isinstance(d, dict) else {}


def parse(key, value):
    """`value` as the setting's type (a string from the CLI or JSON from the API), or SettingError with the reason."""
    if key not in SPEC: raise KeyError(f'unknown setting {key!r}')
    kind = SPEC[key][1]
    if key in ('data_dir', 'cache_dir'):
        v = str(value).strip()
        if not os.path.isabs(os.path.expanduser(v)): raise SettingError(f'{key} must be an absolute path')
        return v
    if key.startswith('skip_'):
        v = str(value).strip().lower()
        if v not in SKIP_MODES: raise SettingError(f"{key} must be {', '.join(SKIP_MODES[:-1])} or {SKIP_MODES[-1]}")
        return v
    if kind is str: return str(value).strip()
    try: v = kind(value)
    except (TypeError, ValueError): raise SettingError(f'{key} must be a number') from None
    if key in POSITIVE and v <= 0: raise SettingError(f'{key} must be more than 0')
    if v < 0: raise SettingError(f'{key} must not be negative')
    return v


def save(changes):
    """Merge `changes` into the settings file after checking every value (nothing is saved if one is wrong); returns the saved settings. A None value removes the setting (back to its default)."""
    d = load()
    for k, v in changes.items():
        if v is None:
            if k not in SPEC: raise KeyError(f'unknown setting {k!r}')
            d.pop(k, None)
        else: d[k] = parse(k, v)
    os.makedirs(home(), exist_ok=True); tmp = _path() + '.tmp'
    with open(tmp, 'w', encoding='utf8') as f: json.dump(d, f, indent=1)
    os.replace(tmp, _path()); return d


def get(key):
    """One setting: the environment override, else the file, else the default (a bad value in the file falls back to the default)."""
    default, _kind, env = SPEC[key]
    raw = (os.environ.get(env) if env else None) or load().get(key)
    if raw is None: return default
    try: return parse(key, raw)
    except SettingError: return default


def _folder(p):
    p = os.path.abspath(os.path.expanduser(p)); os.makedirs(p, exist_ok=True); return p


def data_dir():
    """The folder that holds the database (created when asked for)."""
    return _folder(get('data_dir') or DEFAULT_DATA_DIR)


def cache_dir():
    """The folder that holds fetched videos (created when asked for)."""
    return _folder(get('cache_dir') or os.path.join(data_dir(), 'cache'))


def cache_limit_bytes():
    return int(get('cache_limit_gb') * 1e9)


def all_settings():
    d = {k: get(k) for k in KNOWN}
    d.update(data_dir=data_dir(), cache_dir=cache_dir()); return d
