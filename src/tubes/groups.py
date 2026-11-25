"""Groups of videos that belong together (a programme across its channels, a topic, an occasion), which the watching side lists on its
Groups page. A group is a name and its videos, each with a `score`: how well the video represents the group, compared only within it.
A video can be in several groups, or in none.

Groups are made outside (clustering the library) and loaded whole from a file (`load`, `tubes groups load`): `{"groups": [{"name", "kind",
"videos": [[video id, score], ...]}, ...]}`. A load replaces them all, and each new group takes over the id of the old one it shares most
videos with (at least MATCH of the two together), so a link to it still opens it; the name someone gave that group (`named`) stays too.

What is shown follows library.shown(), as every list does: a group counts, and is pictured by, only videos the watching side shows, and a
group with none is not listed. Its picture is one of the videos that represent it best, the top THUMB_SHARE of them (at least THUMB_MIN),
picked anew on every read, so the page looks different each time it is opened.

Between loads, `place` (`tubes sort`, after a sync) puts videos added since into the groups they belong to: those whose words are like the
group's own (its centre: the words its videos share, weighed by how rare they are across all groups), and those whose title says the group's
name, when that is how its videos are titled. It makes no group and takes nothing out; a thing that is new waits for the next load."""

import json
import math
import random
import re
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from typing import Any

from tubes import cache, db, library
from tubes.db import Row
from tubes.shape import arr, obj

THUMB_SHARE = 20  # one video in this many (5%) may picture its group...
THUMB_MIN = 10  # ...or this many, whichever is more
LAST_ID = "video_group_last_id"  # the key in `meta` of the highest id a group ever had
PLACED = "video_groups_placed"  # the key in `meta` of when videos were last placed: those added since are still to be
WORD = re.compile(r"[^\W_]+")
PLAIN = frozenset(
    [
        "the",
        "and",
        "of",
        "to",
        "in",
        "a",
        "for",
        "with",
        "on",
        "is",
        "from",
        "by",
        "at",
        "it",
        "its",
        "you",
        "your",
        "this",
        "that",
        "are",
        "how",
        "s",
        "full",
        "episode",
        "episodes",
        "kids",
        "cartoon",
        "cartoons",
        "children",
        "official",
        "video",
        "videos",
        "compilation",
        "season",
        "new",
        "best",
        "learn",
        "learning",
        "fun",
        "play",
        "watch",
        "more",
        "youtube",
        "subscribe",
        "live",
        "part",
        "minutes",
        "hour",
        "hours",
        "clip",
        "clips",
        "short",
        "shorts",
        "show",
    ]
)  # words that say nothing of what a video is about
CENTRE = 300  # words kept of a group's centre
LEAST = 0.12  # how alike a video and a centre must be at least (cosine)
LIKE_OWN = 0.2  # ...and at least as alike as this part of the group's own least alike videos
NEAR_BEST = 0.75  # ...and not much less alike than the group it is most like
SAMPLE = 200  # videos of a group that say how alike its own are
MATCH = 0.3  # of the videos two groups hold between them, how many they must share to be the same group


class BadFile(Exception):
    """The file to load is not one, said so a person can fix it."""


def read(text: str) -> list[Row]:
    """The groups of a file's text: `[{name, kind, videos: {id: score}}]`. Raises BadFile naming what is wrong. A group's name is trimmed, its
    best score kept for a video listed twice, and a group with no videos left out."""
    try:
        data = obj(json.loads(text))
    except ValueError as e:
        raise BadFile(f"The file is not JSON ({e}).") from None
    if not isinstance(data.get("groups"), list):
        raise BadFile("The file has no list of groups (`groups`).")
    out: list[Row] = []
    for n, item in enumerate(arr(data["groups"]), 1):
        g = obj(item)
        name = str(g.get("name") or "").strip()
        if not name:
            raise BadFile(f"Group {n} has no name.")
        if not isinstance(g.get("videos"), list):
            raise BadFile(f"Group {n} ({name}) has no list of videos.")
        videos: dict[str, float] = {}
        for pair in arr(g["videos"]):
            try:
                vid, score = arr(pair)
                value = float(score)
            except (TypeError, ValueError):
                raise BadFile(f"Group {n} ({name}) has a video that is not [id, score].") from None
            videos[str(vid)] = max(value, videos.get(str(vid), value))
        if videos:
            kind = g.get("kind")
            out.append(dict(name=name, kind=str(kind)[:32] if kind else None, videos=videos))
    return out


def same(new: Sequence[Mapping[str, float]], old: Mapping[int, set[str]]) -> list[int | None]:
    """For each new group (its videos), the id of the old one it is, or None. The pairs that share most go first; an id is given once."""
    holds: dict[str, list[int]] = {}
    for gid, videos in old.items():
        for v in videos:
            holds.setdefault(v, []).append(gid)
    pairs: list[tuple[float, int, int]] = []
    for i, videos in enumerate(new):
        shared: dict[int, int] = {}
        for v in videos:
            for gid in holds.get(v, ()):
                shared[gid] = shared.get(gid, 0) + 1
        for gid, n in shared.items():
            share = n / (len(videos) + len(old[gid]) - n)
            if share >= MATCH:
                pairs.append((share, i, gid))
    taken: list[int | None] = [None] * len(new)
    used: set[int] = set()
    for _, i, gid in sorted(pairs, key=lambda p: (-p[0], p[1], p[2])):
        if taken[i] is None and gid not in used:
            taken[i] = gid
            used.add(gid)
    return taken


def load(text: str) -> Row:
    """Replace every group with the file's: `{groups, videos, kept}` (groups loaded, the videos in them counted once, groups that kept an id)."""
    new = read(text)
    with db.connect() as con:
        rows = con.execute("SELECT id, name, named FROM video_groups").fetchall()
        was = {r[0]: (r[1], bool(r[2])) for r in rows}
        old: dict[int, set[str]] = {gid: set() for gid in was}
        for gid, vid in con.execute("SELECT group_id, video_id FROM video_group_members"):
            old.setdefault(gid, set()).add(vid)
        ids = same([g["videos"] for g in new], {gid: old[gid] for gid in was})
        last = con.execute("SELECT value FROM meta WHERE key = ?", (LAST_ID,)).fetchone()
        free = max([*was, int(last[0]) if last else 0])
        con.execute("DELETE FROM video_group_members")
        con.execute("DELETE FROM video_groups")
        for g, found in zip(new, ids, strict=True):
            if found is None:
                free += 1  # never an id any group had: a link to a group that went must not open another
            gid = free if found is None else found
            name, named = was[gid] if found is not None and was[gid][1] else (g["name"], False)
            con.execute(
                "INSERT INTO video_groups (id, name, kind, named) VALUES (?, ?, ?, ?)", (gid, name, g["kind"], named)
            )
            con.executemany(
                "INSERT INTO video_group_members (group_id, video_id, score) VALUES (:g, :v, :s)",
                [dict(g=gid, v=vid, s=score) for vid, score in g["videos"].items()],
            )
        con.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (LAST_ID, str(free)),
        )
        _placed(con, cache.stamp())  # the file has every video its maker knew of
    return dict(
        groups=len(new),
        videos=len({vid for g in new for vid in g["videos"]}),
        kept=sum(1 for i in ids if i is not None),
    )


def _rows(now: str | None, group_id: int | None = None) -> list[Row]:
    """The videos that may picture each group (or one), best first, with the group and how many of its videos are shown."""
    ok, args = library.shown(now)
    where, only = ("AND g.id = ?", [group_id]) if group_id is not None else ("", [])
    with db.connect() as con:
        return db.rows(
            con.execute(
                f"""SELECT * FROM (
                      SELECT g.id, g.name, g.kind, v.id AS video_id, v.thumbnail,
                             ROW_NUMBER() OVER (PARTITION BY g.id ORDER BY m.score DESC, v.id) AS place,
                             COUNT(*) OVER (PARTITION BY g.id) AS videos
                      FROM video_groups g JOIN video_group_members m ON m.group_id = g.id JOIN videos v ON v.id = m.video_id
                      LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id
                      WHERE {ok} {where}) ranked
                    WHERE place <= ? OR place <= (videos + ?) / ?
                    ORDER BY videos DESC, LOWER(name), id, place""",
                [*args, *only, THUMB_MIN, THUMB_SHARE - 1, THUMB_SHARE],
            )
        )


def listing(now: str | None = None, group_id: int | None = None) -> list[Row]:
    """Every group (or the one) that has a video to show, largest first: `[{id, name, kind, videos, thumbnail, thumbnail_video}]`. The picture
    is picked afresh each time (the module's notes); None when no video that could picture it has one."""
    picks: dict[int, list[Row]] = {}
    for r in _rows(now, group_id):
        picks.setdefault(r["id"], []).append(r)
    out: list[Row] = []
    for gid, rows in picks.items():
        pictured: list[Row] = [r for r in rows if r["thumbnail"]]
        pick: dict[str, Any] = random.choice(pictured) if pictured else {}  # noqa: S311 (which picture to show, not a secret)
        out.append(
            dict(
                id=gid,
                name=rows[0]["name"],
                kind=rows[0]["kind"],
                videos=rows[0]["videos"],
                thumbnail=pick.get("thumbnail"),
                thumbnail_video=pick.get("video_id"),
            )
        )
    return out


def group(group_id: int, now: str | None = None) -> Row | None:
    """One group as `listing` gives it, or None. A group whose videos are all hidden just now is still found, with none and no picture."""
    found = listing(now, group_id)
    if found:
        return found[0]
    with db.connect() as con:
        r = db.row(con.execute("SELECT id, name, kind FROM video_groups WHERE id = ?", (group_id,)))
    return dict(r, videos=0, thumbnail=None, thumbnail_video=None) if r else None


# --- placing new videos --------------------------------------------------------------------------------------------------------------


def _placed(con: db.Connection, at: str) -> None:
    con.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (PLACED, at),
    )


def terms(title: str, description: str | None) -> dict[str, float]:
    """The words that say what a video is about: its title's, and the title's pairs, at three times its description's first ones."""
    words = [w for w in WORD.findall(title.lower()) if w not in PLAIN and not w.isdigit()]
    said = [w for w in WORD.findall((description or "")[:160].lower()) if w not in PLAIN and not w.isdigit()][:15]
    heavy = words + [" ".join(words[i : i + 2]) for i in range(len(words) - 1)]
    return {**dict.fromkeys(said, 1.0), **dict.fromkeys(heavy, 1 + math.log(3))}


def spoken(text: str) -> str:
    """Text as its words, for finding a name in a title."""
    return f" {' '.join(WORD.findall(text.lower().replace('’', '').replace(chr(39), '')))} "


class Places:
    """The groups as places a video can go, made from their videos: `members` {group id: {video id: score}}, `videos` {id: (title, description)}."""

    def __init__(
        self,
        names: Mapping[int, str],
        members: Mapping[int, Mapping[str, float]],
        videos: Mapping[str, tuple[str, str | None]],
    ) -> None:
        found = {vid: terms(*videos[vid]) for vid in {v for m in members.values() for v in m} if vid in videos}
        seen: dict[str, int] = {}
        for t in found.values():
            for w in t:
                seen[w] = seen.get(w, 0) + 1
        self.rare = {w: math.log(1 + len(found) / n) for w, n in seen.items() if n >= 2}
        self.centres: dict[int, dict[str, float]] = {}
        self.where: dict[str, list[tuple[int, float]]] = {}
        self.least: dict[int, float] = {}
        self.own: dict[
            int, tuple[list[float], list[float]]
        ] = {}  # how alike its videos are, and their scores, both sorted
        self.named: dict[int, str] = {}
        for gid, m in members.items():
            here = [v for v in m if v in found]
            if not here:
                continue
            total: dict[str, float] = {}
            for vid in here:
                for w, x in self._vector(found[vid]).items():
                    total[w] = total.get(w, 0.0) + x
            self.centres[gid] = _unit(dict(sorted(total.items(), key=lambda p: (-p[1], p[0]))[:CENTRE]))
            for w, x in self.centres[gid].items():
                self.where.setdefault(w, []).append((gid, x))
            some = sorted(here)[:: max(1, len(here) // SAMPLE)]
            alike = sorted(_dot(self._vector(found[vid]), self.centres[gid]) for vid in some)
            self.least[gid] = max(LEAST, alike[int(len(alike) * LIKE_OWN)])
            self.own[gid] = (alike, sorted(m[vid] for vid in some))
            name = spoken(names[gid])
            if name.strip() and 2 * sum(name in spoken(videos[vid][0]) for vid in here) >= len(here):
                self.named[gid] = name

    def _vector(self, found: Mapping[str, float]) -> dict[str, float]:
        return _unit({w: x * self.rare[w] for w, x in found.items() if w in self.rare})

    def of(self, title: str, description: str | None) -> dict[int, float]:
        """The groups a video belongs in, each with its score there: the score the group's own video of that likeness has."""
        mine = self._vector(terms(title, description))
        alike: dict[int, float] = {}
        for w, x in mine.items():
            for gid, y in self.where.get(w, ()):
                alike[gid] = alike.get(gid, 0.0) + x * y
        best = max(alike.values(), default=0.0)
        said = spoken(title)
        into = {g for g, x in alike.items() if x >= self.least[g] and x >= NEAR_BEST * best}
        into |= {g for g, name in self.named.items() if name in said}
        return {g: self._score(g, alike.get(g, 0.0)) for g in sorted(into)}

    def _score(self, gid: int, alike: float) -> float:
        own, scores = self.own[gid]
        return scores[min(bisect_left(own, alike), len(scores) - 1)]


def _unit(x: Mapping[str, float]) -> dict[str, float]:
    size = math.sqrt(sum(v * v for v in x.values())) or 1.0
    return {w: v / size for w, v in x.items()}


def _dot(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    return sum(x * b[w] for w, x in a.items() if w in b)


def place(now: str | None = None) -> Row:
    """Put the videos added since the last time into the groups they belong in: `{new, placed, memberships}`. Only those the watching side
    shows, and none known to be a clip or a promo. The first time, with no time kept, only notes the time."""
    at = now or cache.stamp()
    ok, args = library.shown(now)
    with db.connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (PLACED,)).fetchone()
        new = (
            db.rows(
                con.execute(
                    f"""SELECT v.id, v.title, v.description FROM videos v LEFT JOIN channels c ON c.id = v.channel_id
                        LEFT JOIN copies k ON k.video_id = v.id
                        WHERE {ok} AND v.added >= ? AND v.id NOT IN (SELECT m.video_id FROM video_group_members m)
                        AND v.id NOT IN (SELECT e.video_id FROM video_extents e WHERE e.extent IN ('clip', 'promo')) ORDER BY v.id""",
                    [*args, row[0]],
                )
            )
            if row
            else []
        )
        members: dict[int, dict[str, float]] = {}
        names: dict[int, str] = {}
        videos: dict[str, tuple[str, str | None]] = {}
        if new:
            names = {r[0]: r[1] for r in con.execute("SELECT id, name FROM video_groups")}
            for gid, vid, score in con.execute("SELECT group_id, video_id, score FROM video_group_members"):
                members.setdefault(gid, {})[vid] = score
            for vid, title, description in con.execute(
                "SELECT v.id, v.title, v.description FROM videos v WHERE v.id IN (SELECT m.video_id FROM video_group_members m)"
            ):
                videos[vid] = (title, description)
    places = Places(names, members, videos)
    into = {v["id"]: places.of(v["title"], v["description"]) for v in new}
    rows = [dict(g=gid, v=vid, s=score) for vid, where in into.items() for gid, score in where.items()]
    with db.connect() as con:
        con.executemany(
            "INSERT INTO video_group_members (group_id, video_id, score) VALUES (:g, :v, :s) ON CONFLICT DO NOTHING",
            rows,
        )
        _placed(con, at)
    return dict(new=len(new), placed=sum(1 for w in into.values() if w), memberships=len(rows))
