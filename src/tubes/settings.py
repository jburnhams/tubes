"""User settings: one JSON file, `~/.tubes/settings.json` (the folder can be moved with the TUBES_HOME environment variable).

  data_dir         where the cache database (copies and plays) lives. Default: `data/` in this repository (gitignored) until configured.
  cache_dir        where fetched videos are kept, one folder per video. Default: `<data_dir>/cache`.
  cache_limit_gb   how much the cache may hold; eviction starts at 95% of it and stops at 90% (default 1000).
  max_height       the tallest picture to fetch, in pixels (default 1080; wider-than-16:9 pictures are capped by width too).
  player_client    the YouTube client yt-dlp asks as (default `visionos`, which starts downloads without the 4 s wait the default clients get; empty = yt-dlp's own choice).
  half_life_days   how fast a play's weight fades in the eviction score (default 30: a play counts half as much 30 days later).
  protect_days     how long a fetched video that nobody has played yet is kept from eviction (default 7).
  d1_database      the id of the Cloudflare D1 database that holds the library (`youtube_channels`, `youtube_videos`; library.py). The
                   credentials are the environment's CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID, never this file.
  ytdlp, ffmpeg    the commands to run (default `yt-dlp` and `ffmpeg` from PATH).

The environment variables TUBES_DATA, TUBES_CACHE, TUBES_YTDLP, TUBES_FFMPEG and TUBES_D1_DATABASE override the file (handy for tests and one-off runs)."""
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
    'half_life_days': (30.0, float, None),
    'protect_days': (7.0, float, None),
    'd1_database': ('', str, 'TUBES_D1_DATABASE'),
    'ytdlp': ('yt-dlp', str, 'TUBES_YTDLP'),
    'ffmpeg': ('ffmpeg', str, 'TUBES_FFMPEG'),
}
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
