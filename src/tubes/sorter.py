"""Working out how much of a thing each new video is (extents.py): whether it is whole (an episode, several joined, something complete) or part
of something (a clip, a promo). `tubes sort` does it after a sync, for the videos the watching side would show and nothing is known of.

Three things answer, in this order:

  a rule    a title that says it is a full episode, no longer than RULE_FULL; anything over RULE_LONG, or a past stream over RULE_STREAM, is
            several episodes joined. (A wrong one costs a clip that shows.)
  a model   a small logistic regression here (no library, no GPU), learned each time from every answer a language model or a person gave. It
            answers alone only for a channel it has shown it can be trusted with, and only when it is sure.
  an LLM    a language model asked through strata-models (strata_python.clients.models; settings `sort_model`, empty to ask none, and
            `sort_usd`, the most it may cost a month): every video of a channel not trusted yet, the ones the model is not sure of, and one in
            AUDIT of the rest, so a channel that changes is noticed.

The handover: before the LLM is asked, the model's guess is written down with the question, and kept with the answer (`guess`). A channel is
trusted once its last WINDOW guessed answers hold MIN_SURE the model was sure of, AGREE of them right, and it has MIN_TAGGED in all. The window
moves with the audit's answers, so trust is lost the same way it was won. A channel with fewer videos than that is answered by the LLM alone.

What the LLM is asked for first (the programme, how long its episodes run, why) is not kept: asked for the extent alone it was wrong more often."""

import math
import random
import re
import zlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from strata_python.clients import models as service

from tubes import cache, db, extents, library, settings
from tubes.db import Row
from tubes.shape import arr, obj

RULE_FULL = 1800  # seconds: a longer one that says "full episode" is not one
RULE_LONG = 3600
RULE_STREAM = 1200
FULL = re.compile(r"\bfull episode\b", re.IGNORECASE)  # not "full episodes"

SURE = 0.9  # how likely either way the model must think it
WINDOW = 75
MIN_TAGGED = 75
MIN_SURE = 50
AGREE = 0.95
AUDIT = 20  # one in this many of a trusted channel's videos is asked about all the same
ALONE = 100  # how many of a trusted channel's the model answers before the audit's answers are in
ROUND = 30  # how many of an untrusted channel's videos are asked about before it is looked at again
BATCH = 10  # videos in one question
LEARN_MIN = 200  # answers of a language model or a person before the model guesses at all
PARTS = ("clip", "promo")
SPENT = "sort_spent"  # the key in `meta`: {"month": "2026-11", "usd": 1.2}

SYSTEM = """You sort videos in a home video library from their metadata and what you know of these programmes. Ignore channel boilerplate in descriptions (lists of other videos or seasons).
extent, exactly one:
full_episode: one whole episode or film of a programme, even if short (many cartoons run 3-11 minutes).
several_episodes: two or more whole episodes or long stretches of a programme joined (compilation, marathon, looped stream, "best of").
clip: part of something longer: one scene, a moment, a vertical #shorts cut, a song cut from an episode.
promo: trailer, teaser, advert, announcement, product or toy advert, behind the scenes promotion.
standalone: complete in itself and not part of a programme made of episodes: a lesson, how-to, craft, original song, talk, toy-play video by a creator.
unclear: the metadata does not say.
Judge by the title first, then the length against the programme's normal episode length (from your own knowledge, or the channel's typical length), then the description. A cartoon far longer than its episode length is several_episodes even if the title names one story; near one episode length (or one of the two stories in a half-hour) is full_episode; much shorter is a clip unless the programme's episodes are that short. "Best bits/moments", themes, "N minutes/hours" and "+ more" mean joined stretches. A title that says it is one full episode is full_episode. A creator's or teacher's own video is standalone.
For each video give i (its number), show (the programme or film series it is from, "" if none), episode_minutes (how long one of that programme's episodes runs as published online, from your own knowledge; 0 if none or not known), why (at most 8 words), then extent."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["videos"],
    "properties": {
        "videos": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["i", "show", "episode_minutes", "why", "extent"],
                "properties": {
                    "i": {"type": "integer"},
                    "show": {"type": "string"},
                    "episode_minutes": {"type": "number"},
                    "why": {"type": "string"},
                    "extent": {
                        "type": "string",
                        "enum": ["full_episode", "several_episodes", "clip", "promo", "standalone", "unclear"],
                    },
                },
            },
        }
    },
}


# --- the model ---------------------------------------------------------------------------------------------------------------------

BITS = 20
WORD = re.compile(r"[^\W_]+|#\w+|\d+\+?")
STEPS = (3, 4, 5, 6, 7, 8, 10, 11, 12, 14, 16, 20, 22, 24, 26, 30, 40, 60)  # minutes
LENGTH_WORDS = frozenset(
    [
        "compilation",
        "episode",
        "episodes",
        "full",
        "minutes",
        "mins",
        "hour",
        "hours",
        "best",
        "clip",
        "scene",
        "moments",
        "season",
    ]
)


def features(v: Row, typical: float) -> list[int]:
    """The video as places in the model's table: its channel, its length (and against the channel's typical one), the title's words, pairs and
    threes, and the description's first words, each hashed. `v` needs channel_id, title, duration and description."""
    minutes = max(v["duration"] or 1, 1) / 60
    size = int(math.log2(minutes) * 2)
    found = [
        "bias",
        f"b{size}",
        f"ch={v['channel_id']}",
        f"ch={v['channel_id']}|b{size}",
        f"m{min(10, int(minutes * 60 / max(typical, 60) * 3))}",
        f"pipes{min(6, v['title'].count('|'))}",
    ]
    found += [f"d>{n}" for n in STEPS if minutes > n]
    words = WORD.findall(v["title"].lower())
    for n in (1, 2, 3):
        found += ["t:" + " ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
    found += [f"w{size}:{w}" for w in words if w in LENGTH_WORDS]
    said = WORD.findall((v["description"] or "")[:300].lower())[:45]
    found += ["d:" + w for w in said] + ["d:" + " ".join(said[i : i + 2]) for i in range(len(said) - 1)]
    return sorted({zlib.crc32(f.encode()) & ((1 << BITS) - 1) for f in found})


class Model:
    """Logistic regression over hashed features, learned a video at a time (AdaGrad): `guess` is how likely the video is part of something."""

    RATE, DECAY = 0.15, 1e-6

    def __init__(self) -> None:
        self.weights = [0.0] * (1 << BITS)
        self.seen = [1e-8] * (1 << BITS)

    def guess(self, at: Sequence[int]) -> float:
        z = sum(self.weights[i] for i in at) * 3 / math.sqrt(len(at))
        return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))

    def learn(self, at: Sequence[int], part: bool) -> None:
        push = (self.guess(at) - part) * 3 / math.sqrt(len(at))
        for i in at:
            g = push + self.DECAY * self.weights[i]
            self.seen[i] += g * g
            self.weights[i] -= self.RATE * g / math.sqrt(self.seen[i])


def train(known: Sequence[Row], typical: Mapping[str, float], rounds: int = 3) -> Model | None:
    """A model of these answers (rows with `extent`), or None when there are too few, or only one kind, to learn from."""
    parts = sum(1 for v in known if v["extent"] in PARTS)
    if len(known) < LEARN_MIN or not parts or parts == len(known):
        return None
    m = Model()
    rows = [(features(v, typical.get(v["channel_id"], 600)), v["extent"] in PARTS) for v in known]
    order = random.Random(1)  # noqa: S311 (the same order every time, not a secret)
    for _ in range(rounds):
        order.shuffle(rows)
        for at, part in rows:
            m.learn(at, part)
    return m


def sure(guess: float | None) -> bool:
    return guess is not None and (guess >= SURE or guess <= 1 - SURE)


def trusted(answers: Sequence[tuple[float | None, str]]) -> bool:
    """Whether a channel is the model's to answer, from its LLM answers, latest first: `(the guess before it, the answer)` (the module's notes)."""
    guessed = [(g, extent) for g, extent in answers if g is not None]
    held = [(g >= 0.5) == (extent in PARTS) for g, extent in guessed[:WINDOW] if sure(g)]
    return len(guessed) >= MIN_TAGGED and len(held) >= MIN_SURE and sum(held) / len(held) >= AGREE


def audited(video_id: str) -> bool:
    return zlib.crc32(video_id.encode()) % AUDIT == 0


# --- what to work out --------------------------------------------------------------------------------------------------------------

COLUMNS = "v.id, v.channel_id, c.title AS channel, v.title, v.duration, v.live, v.description"


def unknown() -> list[Row]:
    """The YouTube videos the watching side would show, clips or not, that nothing is known of, newest first."""
    ok, args = library.shown(f=dict(library.filters(), clips="show", promos="show"))
    with db.connect() as con:
        return db.rows(
            con.execute(
                f"""SELECT {COLUMNS} FROM videos v LEFT JOIN channels c ON c.id = v.channel_id LEFT JOIN copies k ON k.video_id = v.id
                    WHERE {ok} AND v.platform = 'youtube' AND v.id NOT IN (SELECT e.video_id FROM video_extents e)
                    ORDER BY v.published DESC, v.id DESC""",
                args,
            )
        )


def rule(v: Row) -> str | None:
    """What a rule says the video is, or None."""
    length = v["duration"] or 0
    if length > RULE_LONG or (v["live"] == "was" and length >= RULE_STREAM):
        return "several_episodes"
    return "full_episode" if FULL.search(v["title"]) and 0 < length <= RULE_FULL else None


def learned() -> tuple[list[Row], dict[str, float], dict[str, list[tuple[float | None, str]]]]:
    """What there is to learn from: every answer of a language model or a person (with its video), each channel's typical length (its
    middle one), and each channel's LLM answers, latest first."""
    with db.connect() as con:
        known = db.rows(
            con.execute(
                f"""SELECT {COLUMNS}, e.extent, e.said_by, e.guess FROM video_extents e JOIN videos v ON v.id = e.video_id
                    LEFT JOIN channels c ON c.id = v.channel_id
                    WHERE e.said_by IN ('llm', 'person') AND e.extent NOT IN ('whole', 'unclear') AND v.platform = 'youtube' ORDER BY e.at DESC, e.video_id"""
            )
        )
        lengths: dict[str, list[float]] = {}
        for cid, length in con.execute(
            "SELECT channel_id, duration FROM videos WHERE platform = 'youtube' AND duration IS NOT NULL"
        ):
            lengths.setdefault(cid, []).append(length)
    typical = {cid: sorted(x)[len(x) // 2] for cid, x in lengths.items()}
    answers: dict[str, list[tuple[float | None, str]]] = {}
    for v in known:
        if v["said_by"] == "llm":
            answers.setdefault(v["channel_id"], []).append((v["guess"], v["extent"]))
    return known, typical, answers


# --- the language model ------------------------------------------------------------------------------------------------------------


def spent(now: str | None = None) -> float:
    """What the LLM has cost this month, in dollars."""
    with db.connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (SPENT,)).fetchone()
    month, _, usd = (row[0] if row else "").partition(" ")
    return float(usd) if month == (now or cache.stamp())[:7] and usd else 0.0


def _spend(usd: float, now: str | None = None) -> None:
    total = spent(now) + usd
    with db.connect() as con:
        con.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (SPENT, f"{(now or cache.stamp())[:7]} {total:.6f}"),
        )


def question(videos: Iterable[Row], typical: Mapping[str, float]) -> str:
    lines: list[str] = []
    for n, v in enumerate(videos):
        said = " ".join(re.sub(r"https?://\S+", "", v["description"] or "").split())[:300]
        length = int(v["duration"] or 0)
        lines.append(
            f"[{n}] channel: {v['channel'] or v['channel_id']} (typical length {int(typical.get(v['channel_id'], 600)) // 60}m) | title: {v['title']} | "
            f"{length // 60}m{length % 60:02d}s{' | past live stream' if v['live'] else ''} | desc: {said}"
        )
    return "\n".join(lines)


def ask(videos: Sequence[Row], typical: Mapping[str, float]) -> dict[str, str]:
    """What the LLM says these videos are, by id; one it leaves out is not in it. Its cost is counted. Raises
    service.Unavailable, service.JobFailed or TimeoutError when there is no answer."""
    r = service.run(
        "text",
        dict(prompt=question(videos, typical), system=SYSTEM, schema=SCHEMA, max_tokens=6000, effort="medium"),
        app="tubes",
        priority="low",
        model=settings.get("sort_model"),
        timeout=1800,
    )
    _spend(float(r.get("cost_usd") or 0))
    out: dict[str, str] = {}
    for item in arr(obj(r.get("json")).get("videos")):
        x = obj(item)
        n = x.get("i")
        if isinstance(n, int) and 0 <= n < len(videos) and x.get("extent") in extents.EXTENTS:
            out[videos[n]["id"]] = str(x["extent"])
    return out


# --- a run -------------------------------------------------------------------------------------------------------------------------


def work_out() -> Row:
    """Answer what can be answered now: `{rules, model, llm, left, trusted, channels, spent, problem}` (how many videos each answered, how many
    are left for another run, how many of the channels with videos to answer are the model's, this month's cost, and what went wrong)."""
    done = dict(rules=0, model=0, llm=0)
    problem: str | None = None
    todo: dict[str, list[Row]] = {}
    ruled: list[tuple[str, str, str]] = []
    for v in unknown():
        said = rule(v)
        if said:
            ruled.append((v["id"], said, "rule"))
        else:
            todo.setdefault(v["channel_id"], []).append(v)
    done["rules"] = extents.save(ruled)
    channels = len(todo)
    if not todo:
        return dict(done, left=0, trusted=0, channels=0, spent=round(spent(), 4), problem=None)
    known, typical, answers = learned()
    model = train(known, typical)
    at = {v["id"]: features(v, typical.get(v["channel_id"], 600)) for vs in todo.values() for v in vs}
    asked: set[str] = set()  # asked about in this run, answered or not: one left out is not asked again at once
    budget, with_llm = settings.get_float("sort_usd"), bool(settings.get("sort_model"))
    while True:
        wanted: list[Row] = []
        more = False  # the model has videos it had no turn for
        for cid, vs in todo.items():
            own = trusted(answers.get(cid, []))
            alone: list[tuple[str, str, str]] = []
            waiting: list[Row] = []
            for v in vs:
                g = model.guess(at[v["id"]]) if model else None
                check = with_llm and audited(v["id"]) and v["id"] not in asked
                if own and sure(g) and not check and len(alone) < ALONE:
                    alone.append((v["id"], "clip" if g is not None and g >= 0.5 else "whole", "model"))
                else:
                    waiting.append(v)
            done["model"] += extents.save(alone)
            todo[cid] = waiting
            fresh = [v for v in waiting if v["id"] not in asked]
            # a trusted channel's: the ones it is not sure of and the audit's, not those it had no turn for yet
            due = [
                v for v in fresh if not own or not sure(model.guess(at[v["id"]]) if model else None) or audited(v["id"])
            ]
            wanted += due[:ROUND]
            more = more or len(alone) == ALONE
        if problem or not (more or (with_llm and wanted)):
            break
        for i in range(0, len(wanted) if with_llm else 0, BATCH):
            if spent() >= budget:
                problem = f"The month's {budget:g} dollars for the language model are spent (sort_usd)."
                break
            some = wanted[i : i + BATCH]
            guesses = {v["id"]: model.guess(at[v["id"]]) if model else None for v in some}
            try:
                said_now = ask(some, typical)
            except (service.Unavailable, service.JobFailed, TimeoutError) as e:
                problem = f"The language model did not answer: {e}"
                break
            asked |= {v["id"] for v in some}
            done["llm"] += extents.save([(vid, e, "llm") for vid, e in said_now.items()], guesses=guesses)
            for v in some:
                said = said_now.get(v["id"])
                if said is None or said == "unclear":  # left out, or it cannot say: nothing to learn
                    continue
                answers.setdefault(v["channel_id"], []).insert(0, (guesses[v["id"]], said))
                if model:
                    model.learn(at[v["id"]], said in PARTS)
            for v in some:
                todo[v["channel_id"]] = [x for x in todo[v["channel_id"]] if x["id"] not in said_now]
        if problem:
            break
    return dict(
        done,
        left=sum(len(vs) for vs in todo.values()),
        trusted=sum(1 for cid in todo if trusted(answers.get(cid, []))),
        channels=channels,
        spent=round(spent(), 4),
        problem=problem,
    )
