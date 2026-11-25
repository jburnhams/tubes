"""How much of a thing a video is: one full episode (or film), several episodes joined, a clip (part of something longer: a scene, a moment,
a short cut from an episode), a promo (a trailer, an advert, an announcement), or complete on its own (a lesson, a how-to, a song). Admin >
Settings > Shown videos can leave clips and promos out of every list; a video nothing is known of is always shown.

What said so is kept too (`by`, BY, weakest first): a local model, a language model, a rule (a title that says it is a full episode), or a
person. A later answer replaces an earlier one unless the earlier one was the stronger kind, so a person's answer stays."""

import json
from collections.abc import Iterable

from tubes import cache, db
from tubes.db import Row
from tubes.shape import arr, obj

EXTENTS = ("full_episode", "several_episodes", "clip", "promo", "standalone")
BY = ("model", "llm", "rule", "person")  # weakest first


class BadFile(Exception):
    """The file to load is not one, said so a person can fix it."""


def read(text: str) -> list[tuple[str, str, str]]:
    """The answers of a file's text, `{"videos": [[video id, extent, by], ...]}`. Raises BadFile naming what is wrong."""
    try:
        data = obj(json.loads(text))
    except ValueError as e:
        raise BadFile(f"The file is not JSON ({e}).") from None
    if not isinstance(data.get("videos"), list):
        raise BadFile("The file has no list of videos (`videos`).")
    out: list[tuple[str, str, str]] = []
    for n, item in enumerate(arr(data["videos"]), 1):
        row = arr(item)
        if len(row) != 3 or row[1] not in EXTENTS or row[2] not in BY:
            raise BadFile(
                f"Video {n} is not [id, extent, by]: the extent is one of {', '.join(EXTENTS)}, by one of {', '.join(BY)}."
            )
        out.append((str(row[0]), str(row[1]), str(row[2])))
    return out


def save(answers: Iterable[tuple[str, str, str]], now: str | None = None) -> int:
    """Keep these answers (`(video id, extent, by)`), each unless a stronger one is kept already; returns how many were. The last one wins when a
    video comes twice."""
    new = {vid: (extent, by) for vid, extent, by in answers}
    if not new:
        return 0
    at = now or cache.stamp()
    with db.connect() as con:
        held = {r[0]: r[1] for r in con.execute("SELECT video_id, said_by FROM video_extents")}
        keep = {vid: x for vid, x in new.items() if vid not in held or BY.index(x[1]) >= BY.index(held[vid])}
        con.executemany(
            "INSERT INTO video_extents (video_id, extent, said_by, at) VALUES (:v, :e, :b, :at) "
            "ON CONFLICT (video_id) DO UPDATE SET extent = excluded.extent, said_by = excluded.said_by, at = excluded.at",
            [dict(v=vid, e=extent, b=by, at=at) for vid, (extent, by) in keep.items()],
        )
    return len(keep)


def load(text: str, now: str | None = None) -> Row:
    """Keep a file's answers (see `save`): `{videos, kept}`."""
    answers = read(text)
    return dict(videos=len(answers), kept=save(answers, now))


def counts() -> dict[str, int]:
    """How many of the library's videos are known to be each extent (those still there, shown or not)."""
    with db.connect() as con:
        rows = con.execute(
            "SELECT e.extent, COUNT(*) FROM video_extents e JOIN videos v ON v.id = e.video_id WHERE v.gone IS NULL GROUP BY e.extent"
        ).fetchall()
    found = {r[0]: r[1] for r in rows}
    return {e: found.get(e, 0) for e in EXTENTS}
