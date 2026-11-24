"""Channels related to the ones the library follows and the history watches, counted up into suggestions (history.py's list).

The YouTube Data API no longer says which channels are like a channel: `search?relatedToVideoId=` was removed in 2023 and
`brandingSettings.channel.featuredChannelsUrls` is gone, and a channel page has no Channels tab any more. Two sources are left (measured on
the home server, docs/progress.md, 2026-11-12):

- What a watch page lists next to a video (YouTube's own "related" column: the web client's `next` call, signed out). About 20 videos a
  page, from 10-14 channels; across a handful of channels in one niche the same channels come up again and again, so counting them clusters.
  It needs no key and costs no quota, but it is not an official API: if YouTube changes the page, `watch_next` finds nothing and says so.
- What a channel features itself (`channelSections`, sections of type multipleChannels): one quota unit a channel. Mostly the brand's own
  other channels (other languages, sister shows), so it rarely overlaps between channels, but it is the creator's own word.

Sources: every followed channel, and the history's channels watched at least HISTORY_MIN times (best score first, at most HISTORY_SOURCES).
For each, the watch pages of VIDEOS_PER_SOURCE videos are read (a followed channel's newest uploads in the library, a history channel's
most recently watched videos) and its featured channels asked for. What it pointed at is kept per source (`related_links`) and asked again
after FRESH_DAYS, or RETRY_DAYS after a failure. A run asks about at most `limit` sources, oldest first, so the four-hourly sync spreads a
week's asking over many runs.

`aggregate` (no network) counts them up: a channel's `suggested_by` is how many sources point at it, and `related_score` adds, per source,
the share of its watch pages that listed the channel (plus FEATURED for a featured one), so a channel every source's pages list ranks first.
Channels the history has no watches for are added to `suggestions` with none, and take the group most of their sources are in."""

import collections
import datetime
import os
import re
import time
from collections.abc import Callable, Collection, Iterator, Sequence
from typing import Any, cast

from strata_python.http import Http

from tubes import USER_AGENT, cache, db, quota, youtube
from tubes.db import Row
from tubes.shape import arr, obj, objs

WEB = "https://www.youtube.com"
CLIENT = {"clientName": "WEB", "clientVersion": "2.20251101.00.00", "hl": "en", "gl": "GB"}
TIMEOUT = 30
# A POST that only reads (idempotent, so a 5xx is tried again); PAUSE between sources sets the pace, the gap is a floor under it.
HTTP = Http(USER_AGENT, min_interval=0.5, attempts=2, max_wait=30, timeout=TIMEOUT)
PAUSE = 1.0  # seconds between watch pages: a person's pace, not a crawler's
FRESH_DAYS = 7
RETRY_DAYS = 1
VIDEOS_PER_SOURCE = 3
HISTORY_MIN = 5
HISTORY_SOURCES = 100
RUN_LIMIT = 40  # sources a sync asks about (about 2 minutes)
FEATURED = 0.5
CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


class RelatedError(RuntimeError):
    """A watch page could not be read; the message says why, in a sentence."""


def _web() -> str:
    return os.environ.get("TUBES_YOUTUBE_WEB", WEB).rstrip("/")


def next_page(video_id: str) -> Any:
    """The web client's answer for a watch page (what it lists next), as JSON."""
    reply = HTTP.post(
        f"{_web()}/youtubei/v1/next?prettyPrint=false",
        json_body=dict(context=dict(client=CLIENT), videoId=video_id),
        headers={"Accept": "application/json"},
        idempotent=True,
    )
    if reply.status == 0:
        raise RelatedError(f"YouTube could not be reached: {reply.error}.")
    if not reply.ok:
        raise RelatedError(f"YouTube refused the watch page of {video_id} ({reply.status}).")
    try:
        return reply.json()
    except ValueError:
        raise RelatedError(f"YouTube did not answer with JSON for the watch page of {video_id}.") from None


def _find(node: object, key: str) -> Iterator[Any]:
    """Every value under `key` anywhere in a JSON tree, depth first."""
    if isinstance(node, dict):
        for k, v in cast(dict[str, Any], node).items():
            if k == key:
                yield v
            yield from _find(v, key)
    elif isinstance(node, list):
        for v in cast(list[Any], node):
            yield from _find(v, key)


def _channel_of(item: object) -> tuple[str | None, str | None]:
    """(channel id, its handle) from the first browse link to a channel inside one listed video, or (None, None)."""
    for b in map(obj, _find(item, "browseEndpoint")):
        cid = str(b.get("browseId") or "")
        if CHANNEL_ID.match(cid):
            h = str(b.get("canonicalBaseUrl") or "").lstrip("/")
            return cid, h if h.startswith("@") else None
    return None, None


def _name_of(item: object) -> str | None:
    """The channel's name as the listing writes it: the first metadata line (lockupViewModel) or the byline (the older compactVideoRenderer)."""
    for rows in _find(item, "metadataRows"):
        for row in objs(rows):
            for part in objs(row.get("metadataParts")):
                t = str(obj(part.get("text")).get("content") or "").strip()
                if t:
                    return t
    for by in _find(item, "shortBylineText"):
        runs = objs(obj(by).get("runs"))
        if runs and runs[0].get("text"):
            return str(runs[0]["text"])
    return None


def parse_next(data: object) -> list[Row]:
    """The channels of the videos a watch page lists next: `[{channel_id, title, handle}]`, one per listed video (so a channel listed twice
    is here twice), in the page's order. Shorts shelves and playlists are left out (they name no channel); the video's own channel is kept,
    the caller drops it."""
    results = next(_find(data, "secondaryResults"), None)
    out: list[Row] = []
    for entry in objs(next(_find(results, "results"), None)):
        item = entry.get("lockupViewModel") or entry.get("compactVideoRenderer")
        if not item:
            continue
        if "lockupViewModel" in entry and obj(entry["lockupViewModel"]).get("contentType") not in (
            None,
            "LOCKUP_CONTENT_TYPE_VIDEO",
        ):
            continue
        cid, handle = _channel_of(item)
        if cid:
            out.append(dict(channel_id=cid, title=_name_of(item), handle=handle))
    return out


def watch_next(video_id: str) -> list[Row]:
    """See `parse_next`; RelatedError when the page cannot be read or lists nothing (YouTube changed it, or the video is gone)."""
    found = parse_next(next_page(video_id))
    if not found:
        raise RelatedError(f"The watch page of {video_id} listed no videos.")
    return found


def featured(channel_id: str) -> list[str]:
    """The channel ids a channel features itself (channelSections of type multipleChannels; the type comes back in either case)."""
    items = arr(youtube.call("channelSections", part="snippet,contentDetails", channelId=channel_id).get("items"))
    ids: list[str] = []
    for s in objs(items):
        if str(obj(s.get("snippet")).get("type") or "").lower() != "multiplechannels":
            continue
        for c in arr(obj(s.get("contentDetails")).get("channels")):
            if c not in ids and c != channel_id:
                ids.append(c)
    return ids


def _followed_and_watched(con: db.Connection) -> tuple[list[str], list[str]]:
    follows = [
        r[0]
        for r in con.execute("SELECT id FROM channels WHERE follow = ? AND platform = ? ORDER BY id", (True, "youtube"))
    ]  # watch pages are YouTube's
    watched = [
        r[0]
        for r in con.execute(
            "SELECT channel_id FROM suggestions WHERE watches >= ? AND missing = ? ORDER BY score DESC, channel_id LIMIT ?",
            (HISTORY_MIN, False, HISTORY_SOURCES),
        )
    ]
    return follows, [c for c in watched if c not in set(follows)]


def source_ids() -> set[str]:
    """The channels asked about (see `sources`), without their videos."""
    with db.connect() as con:
        follows, watched = _followed_and_watched(con)
    return set(follows) | set(watched)


def sources() -> dict[str, list[str]]:
    """The channels to ask about, `{channel_id: [video ids]}`: followed ones (their newest uploads), then the history's most watched (the
    videos of it watched last)."""
    with db.connect() as con:
        follows, watched = _followed_and_watched(con)
        out = {
            c: [
                r[0]
                for r in con.execute(
                    "SELECT id FROM videos WHERE channel_id = ? AND gone IS NULL ORDER BY published DESC, id LIMIT ?",
                    (c, VIDEOS_PER_SOURCE),
                )
            ]
            for c in follows
        }
        for c in watched:
            out[c] = [
                r[0]
                for r in con.execute(
                    "SELECT video_id FROM watches WHERE channel_id = ? GROUP BY video_id ORDER BY MAX(at) DESC, video_id LIMIT ?",
                    (c, VIDEOS_PER_SOURCE),
                )
            ]
    return out


def _ago(now: str, days: float) -> str:
    return (datetime.datetime.fromisoformat(now) - datetime.timedelta(days=days)).isoformat(timespec="seconds")


def due(now: str | None = None) -> dict[str, list[str]]:
    """The sources not asked about for FRESH_DAYS (RETRY_DAYS after a failure), never asked first, then oldest first: `{channel_id: [video ids]}`."""
    now = now or cache.stamp()
    every = sources()
    with db.connect() as con:
        asked = {r[0]: (r[1], r[2]) for r in con.execute("SELECT channel_id, fetched, error FROM related_sources")}
    fresh, retry = _ago(now, FRESH_DAYS), _ago(now, RETRY_DAYS)
    wanted = [c for c in every if c not in asked or asked[c][0] < (retry if asked[c][1] else fresh)]
    wanted.sort(key=lambda c: (c in asked, asked.get(c, ("",))[0], c))
    return {c: every[c] for c in wanted}


def fetch_source(channel_id: str, video_ids: Sequence[str], use_api: bool = True, pause: float | None = None) -> Row:
    """Ask YouTube what one channel points at: `{links: {channel_id: {title, handle, hits, featured}}, videos, error}`. Watch pages that
    fail are skipped; `error` says why when none answered (then what it pointed at before is kept: the page may have changed under us)."""
    pause = PAUSE if pause is None else pause
    links: dict[str, Row] = {}
    problems: list[str] = []
    read = 0
    for i, v in enumerate(video_ids):
        if i and pause:
            time.sleep(pause)
        try:
            found = watch_next(v)
        except RelatedError as e:
            problems.append(str(e))
            continue
        read += 1
        for c in {f["channel_id"] for f in found} - {channel_id}:
            f = next(x for x in found if x["channel_id"] == c)
            link = links.setdefault(c, dict(title=f["title"], handle=f["handle"], hits=0, featured=False))
            link["hits"] += 1
    asked_api = False
    if use_api and youtube.configured():
        try:
            for c in featured(channel_id):
                links.setdefault(c, dict(title=None, handle=None, hits=0, featured=False))["featured"] = True
            asked_api = True
        except youtube.YoutubeError as e:
            problems.append(str(e))
    if read or (asked_api and not video_ids):
        error = None  # with no videos to read, what it features is all there is
    else:
        error = problems[0] if problems else "It has no videos to read the watch pages of."
    return dict(links=links, videos=read, error=error)


def save_source(channel_id: str, got: Row, now: str) -> None:
    """Keep what one source pointed at (replacing what it pointed at before, unless this ask failed outright)."""
    with db.connect() as con:  # a failure keeps the links, so the page count they were made from too
        if not got["error"]:
            con.execute("DELETE FROM related_links WHERE source_id = ?", (channel_id,))
            con.executemany(
                "INSERT INTO related_links (source_id, channel_id, title, handle, hits, featured) VALUES (:s, :c, :title, :handle, :hits, :featured)",
                [dict(link, s=channel_id, c=c) for c, link in got["links"].items()],
            )
        con.execute(
            """INSERT INTO related_sources (channel_id, fetched, videos, error) VALUES (?, ?, ?, ?)
                       ON CONFLICT (channel_id) DO UPDATE SET fetched = excluded.fetched, error = excluded.error,
                       videos = CASE WHEN excluded.error IS NULL THEN excluded.videos ELSE related_sources.videos END""",
            (channel_id, now, got["videos"], got["error"]),
        )


@quota.purpose("related")
def refresh(
    now: str | None = None,
    limit: int | None = RUN_LIMIT,
    force: bool = False,
    pause: float | None = None,
    progress: Callable[[int, int, str, Row], None] | None = None,
) -> Row:
    """Ask about the sources that are due (every source with `force`), at most `limit` of them, then count everything up (`aggregate`).
    Returns `{asked, failed, due, links, errors: [{channel, error}], ...aggregate}`; `due` counts what is still waiting for a later run."""
    now, pause = now or cache.stamp(), PAUSE if pause is None else pause
    todo = sources() if force else due(now)
    batch = list(todo.items())[:limit] if limit else list(todo.items())
    errors: list[Row] = []
    links = 0
    for n, (cid, vids) in enumerate(batch):
        if n and pause:
            time.sleep(pause)
        got = fetch_source(cid, vids, pause=pause)
        save_source(cid, got, now)
        links += len(got["links"])
        if got["error"]:
            errors.append(dict(channel=cid, error=got["error"]))
        if progress:
            progress(n + 1, len(batch), cid, got)
    return dict(
        asked=len(batch), failed=len(errors), due=len(todo) - len(batch), links=links, errors=errors, **aggregate()
    )


def aggregate() -> Row:
    """Count what every source points at into `suggestions` (see the module's notes). No network. Returns `{suggested, added}`."""
    with db.connect() as con:
        links = db.rows(
            con.execute(
                "SELECT l.source_id, l.channel_id, l.title, l.handle, l.hits, l.featured, s.videos FROM related_links l JOIN related_sources s ON s.channel_id = l.source_id"
            )
        )
        live = source_ids()  # a source no longer followed or watched stops counting
        group_of = {
            r[0]: r[1]
            for r in con.execute(
                "SELECT channel_id, group_id FROM suggestions WHERE group_id IS NOT NULL AND watches > ?", (0,)
            )
        }
        held = {r[0]: r[1] for r in con.execute("SELECT channel_id, watches FROM suggestions")}
        followed = {
            r[0] for r in con.execute("SELECT id FROM channels WHERE follow = ?", (True,))
        }  # in already: not suggested
        by: collections.defaultdict[str, set[str]] = collections.defaultdict(set)
        score: collections.defaultdict[str, float] = collections.defaultdict(float)
        title: dict[str, str] = {}
        handle: dict[str, str] = {}
        votes: collections.defaultdict[str, collections.Counter[int]] = collections.defaultdict(collections.Counter)
        for link in links:
            c = link["channel_id"]
            if link["source_id"] not in live or c in followed:
                continue
            by[c].add(link["source_id"])
            score[c] += (link["hits"] / link["videos"] if link["videos"] else 0) + (FEATURED if link["featured"] else 0)
            if link["title"]:
                title.setdefault(c, link["title"])
            if link["handle"]:
                handle.setdefault(c, link["handle"])
            if link["source_id"] in group_of:
                votes[c][group_of[link["source_id"]]] += 1
        con.execute(
            "UPDATE suggestions SET suggested_by = ?, related_score = ? WHERE platform = 'youtube'", (0, 0.0)
        )  # iPlayer's are iplayer_suggest.py's
        new = [c for c in by if c not in held]
        con.executemany(
            "INSERT INTO suggestions (channel_id, title, handle) VALUES (:c, :t, :h)",
            [dict(c=c, t=title.get(c) or c, h=handle.get(c)) for c in new],
        )
        con.executemany(
            "UPDATE suggestions SET suggested_by = :n, related_score = :s WHERE channel_id = :c",
            [dict(c=c, n=len(s), s=round(score[c], 4)) for c, s in by.items()],
        )
        unwatched = [c for c in by if not held.get(c)]  # a channel with watches keeps the group its sittings gave it
        con.executemany(
            "UPDATE suggestions SET group_id = :g WHERE channel_id = :c",
            [
                dict(c=c, g=min(votes[c].items(), key=lambda x: (-x[1], x[0]))[0] if votes[c] else None)
                for c in unwatched
            ],
        )
        con.execute(
            "DELETE FROM suggestions WHERE platform = 'youtube' AND watches = ? AND suggested_by = ? AND pasted IS NULL AND dismissed IS NULL",
            (0, 0),
        )  # a dismissal is kept, should YouTube point at it again
        con.execute(
            "INSERT INTO meta (key, value) VALUES ('related_counted', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (cache.stamp(),),
        )
    return dict(suggested=len(by), added=len(new))


def status(now: str | None = None) -> Row:
    """What the Suggestions page says of this: `{sources, asked, due, failed, last}` (`last`: when a source was last asked)."""
    now = now or cache.stamp()
    every = source_ids()
    with db.connect() as con:
        asked = {r[0]: (r[1], r[2]) for r in con.execute("SELECT channel_id, fetched, error FROM related_sources")}
    fresh, retry = _ago(now, FRESH_DAYS), _ago(now, RETRY_DAYS)
    seen = [c for c in every if c in asked]
    waiting = [c for c in every if c not in asked or asked[c][0] < (retry if asked[c][1] else fresh)]
    return dict(
        sources=len(every),
        asked=len(seen),
        due=len(waiting),
        failed=sum(1 for c in seen if asked[c][1]),
        last=max((asked[c][0] for c in seen), default=None),
    )


def pointers(channel_ids: Collection[str], top: int = 3) -> dict[str, list[str]]:
    """For each channel, the titles of the sources that point at it, the strongest first (at most `top`): `{channel_id: [title]}`."""
    if not channel_ids:
        return {}
    live = source_ids()
    out: collections.defaultdict[str, list[str]] = collections.defaultdict(list)
    with db.connect() as con:
        ids = list(channel_ids)
        for i in range(0, len(ids), 500):
            part = ids[i : i + 500]
            rows = con.execute(
                f"""SELECT l.channel_id, l.source_id, COALESCE(c.title, s.title, l.source_id), l.hits, l.featured FROM related_links l
                                   LEFT JOIN channels c ON c.id = l.source_id LEFT JOIN suggestions s ON s.channel_id = l.source_id
                                   WHERE l.channel_id IN ({", ".join("?" * len(part))}) ORDER BY l.channel_id, l.hits DESC, l.source_id""",
                tuple(part),
            )
            for cid, src, name, _hits, _featured in rows:
                if src in live and len(out[cid]) < top:
                    out[cid].append(name)
    return dict(out)
