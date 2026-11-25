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
  break_on, break_url, break_minutes, break_limit_minutes   a break (GET /api/break, the Watch page's break.ts): with `break_on` true and a page at `break_url` (an
                   http(s) link, or a path on this server such as `/other-app/page`), the watching side pauses the video after every
                   `break_minutes` of playing (default 20, counted in each browser across videos) and shows the page over it, until the
                   page says it is done or `break_limit_minutes` pass (default 10). Off by default.

The file handling, the order (environment, then the file, then the default), validation and the API's shape come from strata-python's
`Settings`; this module only declares them. Every setting can be overridden by `TUBES_<KEY>` in the environment (handy for tests and one-off
runs), the folders and tools by their older names TUBES_DATA, TUBES_CACHE, TUBES_YTDLP, TUBES_FFMPEG, TUBES_HISTORY_URL and TUBES_HISTORY_TABLE.
Values are canonical strings (read them with `get_int`/`get_float`); GET /api/settings sends the numbers as JSON numbers (`numbers=True`),
and a settings file Tubes wrote before strata-python (numbers as JSON numbers) is read as it is.
The YouTube key (YOUTUBE_API_KEY) is only ever in the environment."""

import os
import re
from urllib.parse import urlsplit

from strata_python.settings import (
    Setting,
    Settings,
    absolute_path,
    boolean,
    non_empty,
    number_between,
    positive,
    whole_between,
)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(REPO, "data")
# The kinds of segment the player can skip, SponsorBlock's own categories (https://wiki.sponsor.ajay.app/w/Segment_Categories), with their default.
SKIP_DEFAULTS = dict(
    sponsor="auto",
    selfpromo="ask",
    interaction="ask",
    intro="ask",
    outro="ask",
    preview="ask",
    hook="off",
    filler="off",
    music_offtopic="off",
)
SKIP_MODES = ("off", "ask", "auto")


def trimmed(value: str) -> str:
    return value.strip()


def page_url(value: str) -> str:
    """Normaliser: empty, an http(s) link or a path on this server (`/app/page`): what a break shows in its frame. Anything else
    (`javascript:`, a bare word that would be read against the watch page's own path, `//host`, a link a browser cannot parse such as
    `https://[host`) is refused, so the Watch page never meets a link it cannot open."""
    v = value.strip()
    if not v:
        return v
    if re.match(r"^/(?!/)\S*$", v):
        return v
    try:
        parts = urlsplit(v)
        ok = parts.port is None or parts.port >= 0  # reading a port that is not a number raises
    except ValueError:
        parts, ok = None, False
    if (
        not ok
        or not parts
        or parts.scheme.lower() not in ("http", "https")
        or not parts.hostname
        or re.search(r"\s", v)
    ):
        raise ValueError("must be an http(s) link or a path starting with /")
    return v


SETTINGS = Settings(
    "tubes",
    [
        Setting("data_dir", default=lambda: DEFAULT_DATA_DIR, normalise=absolute_path, env="TUBES_DATA"),
        Setting(
            "cache_dir",
            default=lambda: os.path.join(SETTINGS.get("data_dir"), "cache"),
            normalise=absolute_path,
            env="TUBES_CACHE",
        ),
        Setting("cache_limit_gb", default="1000", normalise=positive()),
        Setting("max_height", default="1080", normalise=whole_between(1, 10000)),
        Setting("player_client", default="visionos", normalise=trimmed),
        Setting("cookies_from_browser", default="", normalise=trimmed),
        Setting("half_life_days", default="30", normalise=positive()),
        Setting("protect_days", default="7", normalise=number_between(0, 36500)),
        Setting("prefetch_seconds", default="20", normalise=number_between(0, 3600)),
        Setting("prefetch_per_day", default="150", normalise=whole_between(0, 100000)),
        Setting("ytdlp", default="yt-dlp", normalise=non_empty, env="TUBES_YTDLP"),
        Setting("ffmpeg", default="ffmpeg", normalise=non_empty, env="TUBES_FFMPEG"),
        Setting("history_url", default="", normalise=trimmed, env="TUBES_HISTORY_URL"),
        Setting("history_table", default="", normalise=trimmed, env="TUBES_HISTORY_TABLE"),
        Setting("sort_model", default="", normalise=trimmed),
        Setting("sort_usd", default="2", normalise=number_between(0, 1000)),
        Setting("break_on", default="false", normalise=boolean),
        Setting("break_url", default="", normalise=page_url),
        Setting("break_minutes", default="20", normalise=number_between(1, 1440)),
        Setting("break_limit_minutes", default="10", normalise=number_between(1, 240)),
        *(Setting(f"skip_{c}", default=mode, choices=SKIP_MODES) for c, mode in SKIP_DEFAULTS.items()),
    ],
    numbers=True,
)

KNOWN = SETTINGS.keys
get, get_int, get_float, save, load, home = (
    SETTINGS.get,
    SETTINGS.get_int,
    SETTINGS.get_float,
    SETTINGS.save,
    SETTINGS.load,
    SETTINGS.home,
)


def data_dir():
    """The folder that holds the data Tubes keeps beside its database (created when asked for)."""
    return SETTINGS.folder("data_dir")


def cache_dir():
    """The folder that holds fetched videos (created when asked for)."""
    return SETTINGS.folder("cache_dir")


def cache_limit_bytes():
    return int(get_float("cache_limit_gb") * 1e9)
