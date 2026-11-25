"""Groups of videos that belong together (a programme across its channels, a topic, an occasion), which the watching side lists on its
Groups page. A group is a name and its videos, each with a `score`: how well the video represents the group, compared only within it.
A video can be in several groups, or in none.

Groups are made outside (clustering the library) and loaded whole from a file (`load`, `tubes groups load`): `{"groups": [{"name", "kind",
"videos": [[video id, score], ...]}, ...]}`. A load replaces them all, and each new group takes over the id of the old one it shares most
videos with (at least MATCH of the two together), so a link to it still opens it; the name someone gave that group (`named`) stays too.

What is shown follows library.shown(), as every list does: a group counts, and is pictured by, only videos the watching side shows, and a
group with none is not listed. Its picture is one of the videos that represent it best, the top THUMB_SHARE of them (at least THUMB_MIN),
picked anew on every read, so the page looks different each time it is opened."""

import json
import random
from collections.abc import Mapping, Sequence
from typing import Any

from tubes import db, library
from tubes.db import Row
from tubes.shape import arr, obj

THUMB_SHARE = 20  # one video in this many (5%) may picture its group...
THUMB_MIN = 10  # ...or this many, whichever is more
LAST_ID = "video_group_last_id"  # the key in `meta` of the highest id a group ever had
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
