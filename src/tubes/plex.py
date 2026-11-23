"""A Plex Media Server as a source: its libraries' films and shows, kept as videos and channels with `platform` 'plex', and their files
fetched by ffmpeg straight from Plex (fetcher.py). Plex is the catalogue (its matching, titles, artwork, ratings, cast) and serves the
original files; it never transcodes (its server may be a small machine): what has to be converted is converted here.

The server and its token come from the environment only: `PLEX_URL` (`http://server.lan:32400`) and `PLEX_TOKEN` (an X-Plex-Token, from
Plex Web: an item's Get Info, View XML, the `X-Plex-Token` in its address). Every call sends the token as a header and asks for JSON. The
token must never reach a browser, so Plex's pictures are served through Tubes (`image_path` names them, the server's /api/plex/image
fetches them once, scales them with ffmpeg and keeps them), and its files are read only by ffmpeg here.

What Tubes keeps (ids `plex-<ratingKey>`, ratingKeys being Plex's own numbers):
  a show      a channel (kind `show`), its episodes videos (kind `episode`, `series` the season's title, `season` and `episode` numbers);
  a film      a video (kind `film`) under the channel `plex-films` (kind `category`), like iPlayer's Films;
  a filter    a channel of its own (kind `filter`, id `plex-filter-<n>`), holding every film or episode a library listing with these filters
              gives (`source` keeps {section, params}, the same filters Plex's own browser offers: genre, year, contentRating, unwatched...);
              a sync runs it again, so new matches arrive and ones that no longer match go.
Each video's `source` is its file's part key (`/library/parts/<id>/<ts>/file.mkv`), what ffmpeg reads. An item Plex marks deleted (its
file is gone; `deletedAt`) is kept `gone`, like a YouTube video that went, until Plex finds the file again.

Metadata (metadata.py's shape, which is Plex's): poster, backdrop, logo, square art and the episode's own frame as images, genres and
countries as tags, cast and crew with their photos, IMDb / Rotten Tomatoes / TMDB ratings, the title's IMDb, TMDB and TVDB ids, chapters
(with their pictures), and the file's audio and subtitle tracks. The details (credits, tracks, chapters) need one call per item; a sync
asks again only when Plex's `updatedAt` for it has changed (kept as the video's `checked`).

Measured 2026-11-14 against a real server on the LAN: a picture in 10-70 ms, a 1080p film's file at 117 MB/s, the first 4 s segment
0.24 s (copied) to 0.65 s (an XviD file converted) after ffmpeg starts."""

import json
import os
import re
import urllib.parse

from strata_python.http import Http

from tubes import USER_AGENT

TIMEOUT = 30
# A server on the home network: no gap between requests, and no retries (a Plex that is down or refuses says so at once).
HTTP = Http(USER_AGENT, min_interval=0, attempts=1, cool_down=0, timeout=TIMEOUT)
PREFIX = "plex-"
FILMS = "plex-films"  # the channel films followed one by one are kept under
FILTER = "plex-filter-"
VIDEO_ID = re.compile(r"^plex-(\d{1,12})$")
PART = re.compile(r"^/library/parts/\d+/\d+/file\.[A-Za-z0-9]{1,8}$")
IMAGE = re.compile(r"^/library/(metadata|media)/\d+/[A-Za-z]+(/\d+){1,2}$")
FILTER_KEYS = (
    "genre",
    "year",
    "decade",
    "contentRating",
    "collection",
    "director",
    "actor",
    "writer",
    "producer",
    "country",
    "studio",
    "resolution",
    "hdr",
    "unwatched",
    "inProgress",
    "videoCodec",
    "audioCodec",
    "audioLanguage",
    "subtitleLanguage",
    "label",
    "title",
    "sort",
)
PAGE = 500
KIDS_AGE = 7  # a rating for this age or younger counts as made for children
IMAGE_KINDS = dict(
    coverPoster="poster", background="backdrop", clearLogo="logo", backgroundSquare="square", snapshot="thumb"
)
CREDIT_ROLES = (("Role", "actor"), ("Director", "director"), ("Writer", "writer"), ("Producer", "producer"))
RATING_SOURCES = {"imdb": "imdb", "rottentomatoes": "rottentomatoes", "themoviedb": "tmdb"}


class PlexError(RuntimeError):
    """A call to Plex failed; the message says why, in a sentence."""


def configured():
    return bool(os.environ.get("PLEX_URL") and os.environ.get("PLEX_TOKEN"))


def base():
    if not configured():
        raise PlexError("Plex is not set up: the server needs PLEX_URL and PLEX_TOKEN in its environment.")
    return os.environ["PLEX_URL"].rstrip("/")


def _get(path, params=None, accept="application/json"):
    """The body of a GET on the server, or PlexError saying why there is none."""
    url = base() + path + (("&" if "?" in path else "?") + urllib.parse.urlencode(params, doseq=True) if params else "")
    reply = HTTP.get(
        url,
        headers={
            "Accept": accept,
            "X-Plex-Token": os.environ["PLEX_TOKEN"],
            "X-Plex-Client-Identifier": "tubes",
            "X-Plex-Product": "Tubes",
        },
    )
    if reply.status == 0:
        raise PlexError(f"Plex could not be reached: {reply.error}.")
    if reply.status == 401:
        raise PlexError("Plex refused the token (401): PLEX_TOKEN is wrong or was revoked.")
    if reply.status == 404:
        raise PlexError("Plex has no such item (404).")
    if not reply.ok:
        raise PlexError(f"Plex refused the request ({reply.status}).")
    return reply.body


def call(path, **params):
    """One GET on the server; returns its MediaContainer."""
    body = _get(path, params)
    try:
        return json.loads(body).get("MediaContainer") or {}
    except ValueError:
        raise PlexError("Plex did not answer with JSON.") from None


def image_bytes(path):
    """A picture's bytes from Plex (`path` as image_path gives it)."""
    if not IMAGE.match(path or ""):
        raise PlexError("That is not a Plex picture.")
    return _get(path, accept="image/*")


def file_url(part_key):
    """The address ffmpeg reads a file from: its part key on the server, without the token, which ffmpeg sends as a header (`headers`), so
    no error message or log that names the address carries it."""
    if not PART.match(part_key or ""):
        raise PlexError(f"{part_key!r} is not a Plex file.")
    return f"{base()}{part_key}"


def headers():
    """The HTTP headers ffmpeg sends with a Plex file request (its -headers option)."""
    return f"X-Plex-Token: {os.environ.get('PLEX_TOKEN', '')}\r\n"


def redact(text):
    """Text with the token taken out, should anything have put it there (an error kept on a copy is shown to browsers)."""
    token = os.environ.get("PLEX_TOKEN")
    return text.replace(token, "***") if text and token else text


def reachable():
    """(ok, version or why not), for the System screen."""
    try:
        return True, call("/identity").get("version")
    except PlexError as e:
        return False, str(e)


# What Plex holds.


def sections():
    """The server's film and TV libraries: [{key, title, type (movie or show), locations}]."""
    return [
        dict(
            key=str(d["key"]),
            title=d.get("title"),
            type=d.get("type"),
            locations=[l.get("path") for l in d.get("Location") or []],
        )
        for d in call("/library/sections").get("Directory") or []
        if d.get("type") in ("movie", "show")
    ]


def filters(section):
    """The filters a library offers, as Plex's browser does: [{filter, title, type}] (a `tag` filter takes one of `choices(section, filter)`)."""
    return [
        dict(filter=d.get("filter"), title=d.get("title"), type=d.get("filterType"))
        for d in call(f"/library/sections/{int(section)}/filters").get("Directory") or []
    ]


def choices(section, name):
    """The values one filter can take in a library (`genre`: Action, Animation...): [{key, title}]."""
    if name not in FILTER_KEYS:
        raise PlexError(f"{name} is not a filter Tubes knows.")
    return [
        dict(key=str(d.get("key")), title=d.get("title"))
        for d in call(f"/library/sections/{int(section)}/{name}").get("Directory") or []
    ]


def clean(params):
    """Only the filters Tubes passes on (FILTER_KEYS, plus Plex's `>>=` and `<<=` forms of them), as strings."""
    out = {}
    for k, v in (params or {}).items():
        name = re.sub(r"(>>|<<)?=?$", "", str(k)).rstrip("!")
        if name in FILTER_KEYS and v is not None and str(v).strip() != "":
            out[str(k)] = str(v)
    return out


def browse(section, params=None, start=0, size=50):
    """One page of a library with filters: ({items, total}) where each item is `summary`'s."""
    c = call(
        f"/library/sections/{int(section)}/all",
        **clean(params),
        **{"X-Plex-Container-Start": int(start), "X-Plex-Container-Size": int(size)},
    )
    return dict(items=[summary(m) for m in c.get("Metadata") or []], total=c.get("totalSize", c.get("size", 0)))


def everything(section, params=None):
    """Every item a library listing with these filters gives, page after page (a filter's whole list, for its sync)."""
    out, start = [], 0
    while True:
        c = call(
            f"/library/sections/{int(section)}/all",
            **clean(params),
            **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": PAGE},
        )
        items = c.get("Metadata") or []
        out += items
        start += len(items)
        if not items or start >= c.get("totalSize", start):
            return out


def search(text, limit=20):
    """Films and shows whose title matches, across the libraries: [summary]."""
    hubs = call("/hubs/search", query=text, limit=limit).get("Hub") or []
    return [summary(m) for h in hubs if h.get("type") in ("movie", "show") for m in h.get("Metadata") or []]


def item(rating_key, details=True):
    """One film, show or episode with everything Plex has on it (markers and chapters too), or None when Plex has no such item."""
    try:
        items = (
            call(
                f"/library/metadata/{int(rating_key)}", **(dict(includeChapters=1, includeMarkers=1) if details else {})
            ).get("Metadata")
            or []
        )
    except PlexError as e:
        if "404" in str(e):
            return None
        raise
    return items[0] if items else None


def episodes(show_key):
    """Every episode of a show, in order."""
    return call(f"/library/metadata/{int(show_key)}/allLeaves").get("Metadata") or []


def summary(m):
    """What a browser shows of an item: {key, type, title, year, thumb (a Tubes image address), summary, rating, episodes}."""
    return dict(
        key=str(m.get("ratingKey")),
        type=m.get("type"),
        title=m.get("title"),
        year=m.get("year"),
        thumb=image_path(m.get("thumb"), 300),
        summary=m.get("summary") or None,
        content_rating=m.get("contentRating"),
        episodes=m.get("leafCount"),
        section=str(m.get("librarySectionID") or "") or None,
    )


# As Tubes' rows.


def image_path(path, width=640):
    """A Plex picture as the address Tubes serves it at (relative, so it works behind the reverse proxy), or None."""
    if not path or not IMAGE.match(path):
        return None
    return "api/plex/image?" + urllib.parse.urlencode(dict(path=path, w=int(width)))


def video_id(rating_key):
    return f"{PREFIX}{int(rating_key)}"


def rating_key(vid):
    m = VIDEO_ID.match(vid or "")
    return m[1] if m else None


def _stamp(seconds):
    import datetime

    try:
        return datetime.datetime.fromtimestamp(int(seconds), datetime.UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _date(text):
    return f"{text}T00:00:00+00:00" if re.match(r"^\d{4}-\d{2}-\d{2}$", text or "") else None


def picture(media):
    """(width, height, hdr) of an item's first file."""
    md = (media or [{}])[0]
    streams = [s for p in md.get("Part") or [] for s in p.get("Stream") or [] if s.get("streamType") == 1]
    v = streams[0] if streams else {}
    hdr = None
    if v:
        hdr = v.get("colorTrc") in ("smpte2084", "arib-std-b67") or bool(v.get("DOVIPresent"))
    elif md.get("videoDynamicRange"):
        hdr = md["videoDynamicRange"] != "SDR"
    return md.get("width"), md.get("height"), hdr


def part(media):
    """The first file's part: {key, size, container, duration}."""
    p = ((media or [{}])[0].get("Part") or [{}])[0]
    return p if p.get("key") else None


def codecs(media):
    """{video, audio, container, profile, bit_depth} of an item's first file, as Plex read them (what the fetch decides by)."""
    md = (media or [{}])[0]
    streams = [s for p in md.get("Part") or [] for s in p.get("Stream") or []]
    v = next((s for s in streams if s.get("streamType") == 1), {})
    return dict(
        video=md.get("videoCodec"),
        audio=md.get("audioCodec"),
        container=md.get("container"),
        profile=v.get("profile") or md.get("videoProfile"),
        bit_depth=v.get("bitDepth"),
    )


def images(m, thumb_from="art"):
    """An item's pictures as `images` rows: Plex's Image list (poster, backdrop, logo, square, an episode's frame) as Tubes addresses, and
    the 16:9 one to show on a card as `thumb` (an episode's own frame, else the backdrop)."""
    out, seen = [], set()
    for im in m.get("Image") or []:
        kind = IMAGE_KINDS.get(im.get("type"))
        url = image_path(im.get("url"), 1280 if kind in ("backdrop", "thumb") else 640)
        if kind and url and kind not in seen:
            seen.add(kind)
            out.append(dict(kind=kind, url=url))
    if "poster" not in seen and m.get("type") in ("movie", "show") and image_path(m.get("thumb")):
        out.append(dict(kind="poster", url=image_path(m["thumb"])))
    if "backdrop" not in seen and image_path(m.get("art"), 1280):
        out.append(dict(kind="backdrop", url=image_path(m["art"], 1280)))
    if "thumb" not in {i["kind"] for i in out}:
        src = m.get("thumb") if m.get("type") == "episode" else m.get(thumb_from)
        if image_path(src, 1280):
            out.insert(0, dict(kind="thumb", url=image_path(src, 1280)))
    return out


def credits(m):
    out = []
    for key, role in CREDIT_ROLES:
        for i, c in enumerate(m.get(key) or []):
            if c.get("tag"):
                out.append(
                    dict(
                        role=role,
                        rank=i,
                        name=c["tag"],
                        character=c.get("role") if role == "actor" else None,
                        photo=c.get("thumb") if str(c.get("thumb") or "").startswith("https://") else None,
                    )
                )
    return out


def ratings(m):
    """IMDb, Rotten Tomatoes (critics and audience) and TMDB scores out of 10, from Plex's Rating list."""
    out = {}
    for r in m.get("Rating") or []:
        src = RATING_SOURCES.get(str(r.get("image") or "").split("://")[0])
        if not src or not isinstance(r.get("value"), (int, float)):
            continue
        if src == "rottentomatoes":
            src += "_critic" if r.get("type") == "critic" else "_audience"
        out.setdefault(src, float(r["value"]))
    return [dict(source=k, value=v) for k, v in out.items()]


def external_ids(m):
    out = [
        dict(source=g["id"].split("://")[0], value=g["id"].split("://", 1)[1])
        for g in m.get("Guid") or []
        if "://" in str(g.get("id"))
    ]
    if str(m.get("guid") or "").startswith("plex://"):
        out.append(dict(source="plex", value=m["guid"][len("plex://") :]))
    return out


def chapters(m):
    out = []
    for c in m.get("Chapter") or []:
        if not isinstance(c.get("startTimeOffset"), int):
            continue
        out.append(
            dict(
                start=c["startTimeOffset"] / 1000,
                end=c["endTimeOffset"] / 1000 if isinstance(c.get("endTimeOffset"), int) else None,
                title=c.get("tag") or None,
                image=image_path(c.get("thumb"), 320),
            )
        )
    return out


def tracks(m):
    """The first file's audio and subtitle streams as `tracks` rows (`ref` the stream's index in the file, for ffmpeg's -map)."""
    out, rank = [], {"audio": 0, "subtitle": 0}
    for s in [s for p in ((m.get("Media") or [{}])[0].get("Part") or [])[:1] for s in p.get("Stream") or []]:
        kind = {2: "audio", 3: "subtitle"}.get(s.get("streamType"))
        if not kind:
            continue
        out.append(
            dict(
                kind=kind,
                rank=rank[kind],
                language=s.get("languageTag") or s.get("languageCode"),
                label=s.get("displayTitle") or s.get("title"),
                codec=s.get("codec"),
                ref=str(s["index"]) if isinstance(s.get("index"), int) else None,
                is_default=bool(s.get("default") or s.get("selected")),
                forced=bool(s.get("forced")),
            )
        )
        rank[kind] += 1
    return out


def tags(m):
    return [dict(kind="genre", value=g["tag"]) for g in m.get("Genre") or [] if g.get("tag")] + [
        dict(kind="country", value=c["tag"]) for c in m.get("Country") or [] if c.get("tag")
    ]


def meta(m, details=True):
    """An item's `meta` (metadata.py). Without `details` (a list's thin answer), only what that carries: pictures, genres, countries."""
    out = dict(images=images(m), tags=tags(m))
    if details:
        out.update(credits=credits(m), ratings=ratings(m), external_ids=external_ids(m))
    return out


def _rated(m):
    age = m.get("contentRatingAge")
    return dict(
        content_rating=m.get("contentRating") or None,
        min_age=age if isinstance(age, int) else None,
        kids=age <= KIDS_AGE if isinstance(age, int) else None,
    )


def channel_row(m, now):
    """A show as a `channels` row."""
    from tubes import metadata

    square = next((i["url"] for i in images(m) if i["kind"] == "square"), None)
    return dict(
        id=video_id(m["ratingKey"]),
        platform="plex",
        title=m.get("title") or str(m["ratingKey"]),
        handle=None,
        thumbnail=square or image_path(m.get("thumb"), 480),
        description=m.get("summary") or None,
        published=_date(m.get("originallyAvailableAt")),
        country=None,
        language=None,
        subscribers=None,
        total_videos=m.get("leafCount"),
        views=None,
        uploads=None,
        added=now,
        kind="show",
        tagline=m.get("tagline") or None,
        network=m.get("studio") or None,
        colours=metadata.colours(m.get("UltraBlurColors")),
        **_rated(m),
        meta=meta(m, details="Role" in m or "Guid" in m),
    )


def films_row(now):
    return dict(
        id=FILMS,
        platform="plex",
        title="Films",
        handle=None,
        thumbnail=None,
        description="Films from Plex, followed one by one.",
        published=None,
        country=None,
        language=None,
        subscribers=None,
        total_videos=None,
        views=None,
        uploads=None,
        added=now,
        kind="category",
    )


def filter_row(cid, title, section, params, now):
    """A followed filter as a `channels` row; its filters are kept in `source`."""
    return dict(
        id=cid,
        platform="plex",
        title=title,
        handle=None,
        thumbnail=None,
        description=None,
        published=None,
        country=None,
        language=None,
        subscribers=None,
        total_videos=None,
        views=None,
        uploads=None,
        added=now,
        kind="filter",
        source=json.dumps(dict(section=str(int(section)), params=clean(params)), sort_keys=True),
    )


def version(m):
    """What says an item changed: Plex's updatedAt (an episode often has none, then when it was added)."""
    return str(m.get("updatedAt") or m.get("addedAt") or "") or None


def video_row(m, channel_id, now, details=True):
    """A film or an episode as a `videos` row (`details`: `m` came from `item`, with its credits, chapters and tracks)."""
    from tubes import metadata

    p = part(m.get("Media"))
    w, h, hdr = picture(m.get("Media"))
    episode = m.get("type") == "episode"
    published = _date(m.get("originallyAvailableAt")) or _stamp(m.get("addedAt")) or now
    lang = next((t["language"] for t in tracks(m) if t["kind"] == "audio" and t["language"]), None)
    row = dict(
        id=video_id(m["ratingKey"]),
        platform="plex",
        channel_id=channel_id,
        title=m.get("title") or str(m["ratingKey"]),
        published=published,
        duration=round(m["duration"] / 1000, 3) if isinstance(m.get("duration"), int) else None,
        thumbnail=(images(m) or [{}])[0].get("url"),
        views=None,
        description=m.get("summary") or None,
        likes=None,
        comments=None,
        definition=("hd" if (h or 0) >= 720 else "sd") if h else None,
        live=None,
        expires=None,
        series=m.get("parentTitle") if episode else None,
        episode=m.get("index") if episode else None,
        season=m.get("parentIndex") if episode else None,
        language=lang,
        captions=any(t["kind"] == "subtitle" for t in tracks(m)) if details else None,
        regions_allowed=None,
        regions_blocked=None,
        added=now,
        kind="episode" if episode else "film",
        tagline=m.get("tagline") or None,
        year=m.get("year") if isinstance(m.get("year"), int) else None,
        network=m.get("studio") or None,
        width=w,
        height=h,
        hdr=hdr,
        colours=metadata.colours(m.get("UltraBlurColors")),
        source=p["key"] if p else None,
        gone=_stamp(m.get("deletedAt")) if m.get("deletedAt") else None,
        checked=version(m),
        **_rated(m),
    )
    row["meta"] = dict(meta(m, details), **(dict(chapters=chapters(m), tracks=tracks(m)) if details else {}))
    return row


def parse(text):
    """A Plex item's ratingKey from what a person pastes: `plex:21394`, or a Plex Web address (`.../details?key=%2Flibrary%2Fmetadata%2F21394`); else None."""
    t = (text or "").strip()
    m = re.match(r"^plex:(\d{1,12})$", t, re.I)
    if m:
        return m[1]
    if "plex" in t.lower() or ":32400" in t:
        m = re.search(r"(?:key=|/)(?:%2F|/)library(?:%2F|/)metadata(?:%2F|/)(\d{1,12})", t, re.I)
        if m:
            return m[1]
    return None


WIDTHS = (160, 320, 480, 640, 960, 1280, 1920)
IMAGES = "plex-images"  # under the data folder: Plex's pictures as served, one file per picture and width


def cached_image(path, width=640):
    """The file of a Plex picture scaled to (the nearest of WIDTHS at or above) `width`, fetched from Plex and scaled by ffmpeg the first time:
    Plex's own resizing takes about 0.4 s a picture on a small server, and its originals are up to 4K. A picture Plex later changes gets a
    new path (its address ends in when it changed), so a kept one is never stale."""
    import hashlib
    import subprocess

    from tubes import settings

    w = next((x for x in WIDTHS if x >= int(width or 0)), WIDTHS[-1])
    folder = os.path.join(settings.data_dir(), IMAGES)
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, f"{hashlib.sha1(path.encode()).hexdigest()[:20]}-{w}.jpg")
    if os.path.exists(out):
        return out
    data = image_bytes(path)
    from strata_python.files import atomic_path

    try:
        with atomic_path(out) as tmp:  # its own temp name: two requests for one picture at once never share a file
            p = subprocess.run(
                [
                    settings.get("ffmpeg"),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-i",
                    "pipe:0",
                    "-vf",
                    f"scale='min({w},iw)':-2",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    "-f",
                    "mjpeg",
                    tmp,
                ],
                input=data,
                capture_output=True,
                timeout=60,
            )
            if p.returncode != 0 or not os.path.exists(tmp):
                raise PlexError("The picture could not be scaled.")
    except (OSError, subprocess.TimeoutExpired):
        raise PlexError("The picture could not be scaled.") from None
    return out
