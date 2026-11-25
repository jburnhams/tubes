#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2", "scipy>=1.14", "scikit-learn>=1.5", "igraph>=0.11", "leidenalg>=0.10", "strata-python[db]>=0.2.19,<0.3"]
# ///
"""Make the groups of videos again (src/tubes/groups.py), from what the videos say: `scripts/regroup.py OUT.json`, then `tubes groups renew
OUT.json`. Run now and then (weekly on the server), so a programme or a topic that is new gets a group; `tubes sort` places new videos in the
groups there are in between. It reads Tubes' database and writes only the file. Its libraries are its own (`uv run` fetches them), so the app
does not carry them.

No list of programmes goes in. Each video is the words of its title, tags and the start of its description, weighed by how rare they are; each is
joined to those most like it, and groups are where the joins are thick (Leiden). Those cut finer than a person would are joined again when the
same few words mark them; one held together by a style (a network, one channel) is cut again on its own, where what all of it says counts for
nothing. A group's name in words is the phrase its titles share; every title that says the phrase joins it, so groups overlap. A language model
(setting `sort_model`, through strata-models, counted against `sort_usd`) names those that are new, and says when a "group" is only a channel or a
mixture, which is left out, as is one it cannot make sense of; a group that was there keeps its name and kind, and is not asked about.

It is repeatable: the same library gives the same groups. Memory is about 4 GB for 90,000 videos, and a few minutes."""

import collections
import json
import os
import re
import sys
from collections.abc import Iterable, Sequence
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import igraph
import leidenalg
import numpy as np
import scipy.sparse as sp
from sklearn.cluster import AgglomerativeClustering
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from strata_python.clients import models as service

from tubes import db, groups, library, settings, sorter

PLAIN = frozenset(
    [
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
        "shows",
        "games",
        "game",
        "series",
        "english",
        "free",
        "song",
        "songs",
        "tv",
        "channel",
        "make",
        "made",
    ]
)  # says nothing of what a video is about
EDGE = frozenset(
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
        "w",
        "x",
        "ft",
        "vs",
        "or",
        "my",
        "me",
        "we",
        "our",
        "all",
    ]
)  # a phrase neither starts nor ends with one
STOP = sorted(PLAIN | EDGE)
NEIGHBOURS = 16
USEFUL = ("show or franchise", "topic", "occasion", "activity or format")
LEAST = 15  # videos in a group
FEWEST = 300  # videos in the library
SAID = re.compile(r"[a-z0-9][a-z0-9']+")


def words(text: str) -> list[str]:
    return SAID.findall(text.lower().replace("’", "'"))


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower().replace("&", "and").replace("’", ""))).strip()


def phrases(title: str) -> set[str]:
    w = title.split()
    return {" ".join(w[i : i + n]) for n in (1, 2, 3) for i in range(len(w) - n + 1)}


# --- the videos --------------------------------------------------------------------------------------------------------------------


def read() -> list[dict[str, Any]]:
    """The videos that may be in a group: shown, not known to be a clip or a promo, one of each exact repeat. With `said` (the words they are
    compared by) and `plain` (their title's)."""
    ok, args = library.shown()
    with db.connect() as con:
        found = db.rows(
            con.execute(
                f"""SELECT v.id, v.channel_id, c.title AS channel, v.title, v.duration, v.views, v.series, v.description FROM videos v
                    LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id
                    WHERE {ok} AND v.id NOT IN (SELECT e.video_id FROM video_extents e WHERE e.extent IN ('clip', 'promo'))
                    ORDER BY v.id""",  # noqa: S608 (library's own SQL; every value is bound)
                args,
            )
        )
        tags: dict[str, list[str]] = {}
        for vid, value in con.execute(
            "SELECT owner_id, value FROM tags WHERE owner = 'video' AND kind IN ('keyword', 'genre') ORDER BY owner_id, rank, value"
        ):
            tags.setdefault(vid, []).append(value)
    extra = repeats(found)
    videos = [v for v in found if v["id"] not in extra]
    size = collections.Counter(v["channel_id"] for v in videos)
    used = collections.Counter((v["channel_id"], t) for v in videos for t in {t.lower() for t in tags.get(v["id"], ())})
    for v in videos:
        cid = v["channel_id"]
        own = [t for t in tags.get(v["id"], ()) if size[cid] < 30 or used[cid, t.lower()] < 0.6 * size[cid]][:15]
        opening = words(" ".join(re.sub(r"https?://\S+", "", v["description"] or "").split())[:600])[:25]
        v["said"] = " ".join([v["title"]] * 3 + own + [v["series"] or ""] + opening)
        v["plain"] = plain(v["title"])
        v["phrases"] = phrases(v["plain"])
    return videos


def repeats(videos: Sequence[dict[str, Any]]) -> set[str]:
    """The ids of exact repeats: the same title and length (within 3 s or 2%), all but the most viewed of each."""
    by: dict[str, list[dict[str, Any]]] = {}
    for v in videos:
        key = plain(re.sub(r"[#@]\w+", "", v["title"]))
        if len(key) > 5 and v["duration"]:
            by.setdefault(key, []).append(v)
    out: set[str] = set()
    for same in by.values():
        same.sort(key=lambda v: (v["duration"], v["id"]))
        run = [same[0]]
        for v in [*same[1:], None]:
            if v and v["duration"] - run[-1]["duration"] <= max(3, 0.02 * v["duration"]):
                run.append(v)
                continue
            best = max(run, key=lambda x: (x["views"] or 0, x["id"]))
            out |= {x["id"] for x in run if x is not best}
            run = [v] if v else []
    return out


# --- finding groups ------------------------------------------------------------------------------------------------------------------


def nearest(z: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Each row's `k` most alike rows (itself left out) and how alike: exact, a block at a time."""
    at, how = np.empty((len(z), k), np.int64), np.empty((len(z), k), np.float32)
    for start in range(0, len(z), 2000):
        alike = z[start : start + 2000] @ z.T
        rows = np.arange(len(alike))
        alike[rows, start + rows] = -1
        top = np.argpartition(-alike, k - 1, axis=1)[:, :k]
        at[start : start + len(alike)], how[start : start + len(alike)] = top, np.take_along_axis(alike, top, 1)
    return at, how


def thick(z: np.ndarray, k: int, least: float, resolution: float) -> list[list[int]]:
    """Where the joins between alike rows are thick: lists of rows."""
    at, how = nearest(z, min(k, len(z) - 1))
    src = np.repeat(np.arange(len(z)), at.shape[1])
    keep = how.ravel() > least
    g = igraph.Graph(n=len(z), edges=np.c_[src[keep], at.ravel()[keep]].tolist())
    g.es["weight"] = how.ravel()[keep].tolist()
    g.simplify(combine_edges="max")
    found = leidenalg.find_partition(
        g,
        leidenalg.RBConfigurationVertexPartition,
        weights="weight",
        resolution_parameter=resolution,
        seed=1,
        n_iterations=2,
    )
    return [list(c) for c in found]


def vectors(matrix: Any, size: int) -> np.ndarray:
    return normalize(TruncatedSVD(size, random_state=0).fit_transform(matrix) + 1e-9).astype("float32")


class Finder:
    def __init__(self, videos: list[dict[str, Any]]) -> None:
        self.videos = videos
        tf = TfidfVectorizer(
            tokenizer=words,
            token_pattern=None,
            ngram_range=(1, 2),
            min_df=6,
            max_df=0.15,
            sublinear_tf=True,
            stop_words=STOP,
        )
        self.matrix = tf.fit_transform([v["said"] for v in videos])
        self.z = vectors(self.matrix, min(200, self.matrix.shape[1] - 1, len(videos) - 1))
        self.uses = collections.Counter(p for v in videos for p in v["phrases"])
        self.found: list[dict[str, Any]] = []
        self.build(self.joined(thick(self.z, NEIGHBOURS, 0.35, 10)))
        self.rejoin()

    def joined(self, fine: list[list[int]]) -> list[list[int]]:
        """Fine groups marked by the same few words, as one."""
        fine = [c for c in fine if len(c) >= 12]
        mean = sp.vstack([sp.csr_matrix(self.matrix[c].mean(0)) for c in fine]).tocsr()
        rare = np.log(1 / (np.asarray((mean > 0.02).mean(0)).ravel() + 1e-3))
        marked = mean.multiply(rare).tocsr()
        top = sp.lil_matrix(marked.shape)
        for r in range(marked.shape[0]):
            row = marked[r]
            for o in np.argsort(-row.data, kind="stable")[:8]:
                top[r, row.indices[o]] = row.data[o]
        unit = normalize(top.tocsr())
        alike = (unit @ unit.T).toarray()
        np.fill_diagonal(alike, 1)
        which = (
            AgglomerativeClustering(n_clusters=None, distance_threshold=0.6, metric="precomputed", linkage="average")
            .fit(np.clip(1 - alike, 0, 1))
            .labels_
        )
        out: dict[int, list[int]] = {}
        for c, label in zip(fine, which, strict=True):
            out.setdefault(int(label), []).extend(c)
        return [sorted(x) for x in out.values() if len(x) >= LEAST]

    def phrase(self, rows: Sequence[int], ban: frozenset[str] = frozenset()) -> list[tuple[float, str, float, float]]:
        """The phrases that mark these videos, best first: (how well, phrase, share of their titles that say it, share of its uses that are here)."""
        said = collections.Counter(p for i in rows for p in self.videos[i]["phrases"])
        out: list[tuple[float, str, float, float]] = []
        for p, n in said.items():
            w = p.split()
            if n < 0.2 * len(rows) or len(p) < 3 or p.isdigit() or ban & set(w) or not usable(w):
                continue
            share, here = n / len(rows), n / self.uses[p]
            if here >= 0.1:
                out.append((2 * share * here / (share + here) * (1 + 0.08 * (len(w) - 1)), p, share, here))
        return sorted(out, reverse=True)[:5]

    def cut(self, rows: list[int]) -> list[list[int]]:
        tf = TfidfVectorizer(
            tokenizer=words,
            token_pattern=None,
            ngram_range=(1, 2),
            min_df=max(4, len(rows) // 300),
            max_df=0.35,
            sublinear_tf=True,
            stop_words=STOP,
        )
        m = tf.fit_transform([self.videos[i]["said"] for i in rows])
        z = vectors(m, min(60, m.shape[1] - 1, len(rows) - 1))
        return [[rows[i] for i in c] for c in thick(z, 11, 0.3, 1.2)]

    def build(self, starts: list[list[int]]) -> None:
        """The groups, each mixed one cut again (twice at most) with its pieces beside it."""
        todo: list[tuple[list[int], int, frozenset[str]]] = [(x, 0, frozenset()) for x in starts]
        seen: dict[str, dict[str, Any]] = {}
        made: list[dict[str, Any]] = []
        while todo:
            rows, depth, ban = todo.pop()
            marks = self.phrase(rows, ban)
            made.append(dict(rows=rows, marks=marks))
            common = collections.Counter(w for i in rows for w in set(self.videos[i]["plain"].split()))
            ban = ban | {w for w, n in common.items() if n >= 0.5 * len(rows)}
            channel = collections.Counter(self.videos[i]["channel_id"] for i in rows).most_common(1)[0][1]
            style = bool(marks) and channel > 0.75 * len(rows) and marks[0][3] >= 0.9
            if depth < 2 and len(rows) >= 100:
                mixed = not marks or marks[0][2] < 0.6 or marks[0][0] < 0.55 or (style and len(rows) >= 250)
                if mixed:
                    pieces = [p for p in self.cut(rows) if len(p) >= 20]
                    good = [p for p in pieces if (m := self.phrase(p, ban)) and m[0][0] > 0.4 and m[0][2] > 0.45]
                    if len(good) >= 2:
                        todo += [(p, depth + 1, ban) for p in good]
        for g in sorted(made, key=lambda g: (-len(g["rows"]), g["rows"][0])):
            m = g["marks"]
            g["phrase"] = m[0][1] if m and m[0][0] > 0.35 and m[0][2] > 0.4 else None
            g["all"] = set(g["rows"]) | (self.saying(g["phrase"]) if g["phrase"] else set())
            if g["phrase"] in seen and g["phrase"]:
                seen[g["phrase"]]["all"] |= g["all"]
                continue
            if g["phrase"]:
                seen[g["phrase"]] = g
            self.found.append(g)

    def saying(self, phrase: str) -> set[int]:
        return {i for i, v in enumerate(self.videos) if phrase in v["phrases"]}

    def rejoin(self) -> None:
        """Something cut into pieces (its toys, its compilations, one channel's style): a phrase most titles of two groups or more say, and mostly
        said in them, makes a group of every title that says it, beside the pieces."""
        have = {g["phrase"] for g in self.found}
        by: dict[str, list[int]] = {}
        for j, g in enumerate(self.found):
            said = collections.Counter(p for i in g["rows"] for p in self.videos[i]["phrases"])
            for p, n in said.items():
                if n >= 0.5 * len(g["rows"]) and len(p) > 3 and not p.isdigit() and usable(p.split()):
                    by.setdefault(p, []).append(j)
        made: list[dict[str, Any]] = []
        for p, where in sorted(by.items(), key=lambda x: (-len(x[0].split()), x[0])):
            if len(where) < 2 or p in have or self.uses[p] < 80:
                continue
            core = {i for j in where for i in self.found[j]["rows"] if p in self.videos[i]["phrases"]}
            share = len(core) / self.uses[p]
            if share < (0.5 if " " in p else 0.65) or len(core) < 60:
                continue
            every = self.saying(p)
            if any(len(every & g["all"]) > 0.8 * len(every | g["all"]) for g in [*self.found, *made]):
                continue
            made.append(dict(rows=sorted(core), marks=[(share, p, 1.0, share)], phrase=p, all=every, again=True))
        made.sort(key=lambda g: (-len(g["all"]), g["phrase"]))
        for g in made:
            if not any(x.get("again") and len(g["all"] & x["all"]) >= 0.7 * len(g["all"]) for x in self.found):
                self.found.append(g)

    def scores(self, g: dict[str, Any]) -> list[tuple[str, float]]:
        """Its videos, those that represent it best first: how near each is to its centre, more for a title that says its phrase."""
        rows = sorted(g["all"])
        centre = self.z[rows].mean(0)
        near = self.z[rows] @ (centre / np.linalg.norm(centre))
        says = np.array([0.25 if g["phrase"] and g["phrase"] in self.videos[i]["phrases"] else 0.0 for i in rows])
        scored = [(self.videos[i]["id"], round(float(x), 4)) for i, x in zip(rows, near + says, strict=True)]
        return sorted(scored, key=lambda x: (-x[1], x[0]))


def usable(w: Sequence[str]) -> bool:
    """Whether words make a phrase that says something: not all plain, and not starting or ending on a small word."""
    return bool(set(w) - PLAIN - EDGE) and w[0] not in EDGE and w[-1] not in EDGE


# --- names ---------------------------------------------------------------------------------------------------------------------------

SYSTEM = """Groups of videos came out of automatic clustering of a home video library. For each group you get its distinctive phrases, sample titles and channels. Give: name, the short plain name a person would use for what these videos share (a show's proper name, a topic, an occasion), 1 to 4 words; type; coherent: true if at least 80% of the sample titles clearly fit the name. If the videos only share a channel, network or style, type is "channel or network"; if nothing, "mixed". Use only what the samples show."""
TYPES = [*USEFUL, "channel or network", "mixed"]
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["groups"],
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["i", "name", "type", "coherent"],
                "properties": {
                    "i": {"type": "integer"},
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": TYPES},
                    "coherent": {"type": "boolean"},
                },
            },
        }
    },
}


def name(new: Sequence[dict[str, Any]], videos: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the language model calls each of these groups: `{name, type, coherent}`, `{}` for one it left out."""
    out: list[dict[str, Any]] = [{} for _ in new]
    for start in range(0, len(new), 8):
        lines: list[str] = []
        for n, g in enumerate(new[start : start + 8]):
            rows = sorted(g["all"])
            some = rows[:: max(1, len(rows) // 14)][:14]
            top = collections.Counter(videos[i]["channel"] or "" for i in rows).most_common(4)
            lines.append(
                f"[{n}] {len(rows)} videos; phrases: {', '.join(m[1] for m in g['marks'])}; channels: {', '.join(f'{c} ({k})' for c, k in top)}"
            )
            lines += [f"   - {videos[i]['title'][:95]}" for i in some]
        if sorter.spent() >= settings.get_float("sort_usd"):
            print(
                "  the month's dollars for the language model are spent (sort_usd): the rest of the new groups wait",
                file=sys.stderr,
            )
            break
        r = service.run(
            "text",
            dict(prompt="\n".join(lines), system=SYSTEM, schema=SCHEMA, max_tokens=4000, effort="low"),
            app="tubes",
            priority="low",
            model=settings.get("sort_model"),
            timeout=1800,
        )
        sorter.spend(float(r.get("cost_usd") or 0))
        for x in (r.get("json") or {}).get("groups", []):
            if isinstance(x.get("i"), int) and 0 <= x["i"] < min(8, len(new) - start):
                out[start + x["i"]] = x
    return out


def key(text: str) -> str:
    return plain(text).replace(" videos", "").replace("the ", "")


def settle(
    found: Sequence[dict[str, Any]], finder: Finder, kept: dict[int, tuple[str, str | None]]
) -> list[dict[str, Any]]:
    """The groups to keep, named: one that was there under its name and kind, a new one under the model's when it makes sense of it. Two of one
    name are one."""
    old = groups.members()
    ids = groups.same([dict.fromkeys((finder.videos[i]["id"] for i in g["all"]), 1.0) for g in found], old)
    new = [g for g, gid in zip(found, ids, strict=True) if gid is None]
    said = iter(name(new, finder.videos)) if settings.get("sort_model") else iter([{} for _ in new])
    out: dict[str, dict[str, Any]] = {}
    for g, gid in zip(found, ids, strict=True):
        if gid is not None:
            g["name"], g["kind"] = kept[gid]
        else:
            x = next(said)
            if not x or x["type"] not in USEFUL or not x["coherent"] or not str(x["name"]).strip():
                continue
            g["name"], g["kind"] = str(x["name"]).strip(), x["type"]
        g["new"] = gid is None
        k = key(g["name"])
        if k in out:
            if g.get("again") and plain(g["name"]) != g["phrase"]:
                continue  # a word like "friends" gathers too much under a show's name
            out[k]["all"] |= g["all"]
            out[k]["new"] = out[k]["new"] and g["new"]
        else:
            out[k] = g
    return [g for g in out.values() if len(g["all"]) >= LEAST]


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    if len(args) != 1:
        print("usage: regroup.py OUT.json", file=sys.stderr)
        return 2
    videos = read()
    print(f"  {len(videos)} videos", flush=True)
    if len(videos) < FEWEST:
        print(f"  Too few to make groups of (under {FEWEST}): nothing is written.", file=sys.stderr)
        return 1
    finder = Finder(videos)
    kept = {g["id"]: (g["name"], g["kind"]) for g in groups.every()}
    done = settle(finder.found, finder, kept)
    out = [dict(name=g["name"], kind=g["kind"], videos=finder.scores(g)) for g in done]
    with open(args[0], "w", encoding="utf8") as f:
        json.dump(dict(groups=out), f, ensure_ascii=False)
    fresh = sorted(g["name"] for g in done if g["new"])
    print(f"  {len(finder.found)} found, {len(done)} kept, {len(fresh)} new: {', '.join(fresh)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
