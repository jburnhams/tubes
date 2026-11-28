"""How loud each copy is, and the gain that brings it to the same loudness as the others without clipping.

The player plays every video at `gain` times its own level (strata-react's MediaPlayer `gain`, through Web Audio with a limiter), so 100%
on its volume is the same loudness whatever the video: a quiet one is raised, a loud one brought down. The gain comes from two figures
ffmpeg's `ebur128` filter measures from the copy's own segments: the integrated loudness (EBU R 128, in LUFS: the average a listener
hears, with silence gated out) and the sample peak (dBFS). Brought down, a video is simply brought to the target (`loudness_target`,
default -16 LUFS, the level most streaming services and podcasts aim for); raised, it stops where its loudest peak would reach
`CEILING_DB`, so normalising never clips. Measured (2026-11-28, a cloud machine, one thread): ten minutes of Opus in a 1080p copy took
about 4.5 s, nearly all of it decoding, so a whole hour is under half a minute; with true peak instead of sample peak it took half as
long again, for a difference the ceiling's 1 dB covers.

A copy still being fetched is measured as it grows: first once `MIN_SECONDS` are on disk (a whole copy shorter than that is measured whole) (before that the gain is 1, the video as it
is), then each time what is on disk has doubled, and once more when it is whole, so the measuring costs at most about twice one pass
over the whole copy. What has not arrived yet may be louder, so until the copy is whole a raise is held back twice: a cap that starts at
`FIRST_CAP_DB` and grows with each doubling of what was measured (to `MAX_RAISE_DB`), and room left under the ceiling for peaks not seen
yet, `UNSEEN_MARGIN_DB` times the share of the video still to come. Bringing a video down needs no such care. Each new measurement
changes the gain the player is given with the stream's status (it polls that each second while the copy arrives, and until the
measurement is final), and the player glides to it. The limiter in the player catches what a measurement could not foresee.

The figures are kept in the database by copy (the `loudness` table), not in the copy's folder, so they outlive eviction: a copy fetched
again plays at its final level from its first second, and is not measured again. A prefetched start (prefetch.py) is measured as soon as
it is kept, so a play of it starts at its first, careful gain. A copy fetched before this existed is measured the first time its stream
status is read (a play), or by `tubes loudness` for the whole cache. ffmpeg reads the init segment and the listed segments through a pipe (one process, no command
line as long as the copy), with one thread, so it never competes with a fetch for more than one core."""

import contextlib
import math
import re
import subprocess
import threading
from collections.abc import Callable
from typing import IO, cast

from tubes import cache, db, settings
from tubes.db import Row

MIN_SECONDS = 10.0  # less than this says too little about a video's level: it plays as it is
CEILING_DB = -1.0  # a raise stops where the loudest peak would reach this (dBFS)
MAX_RAISE_DB = 12.0  # never more than four times as loud
FIRST_CAP_DB = 3.0  # the most a copy measured from its first MIN_SECONDS is raised, growing by RAISE_PER_DOUBLING for each doubling
RAISE_PER_DOUBLING = 3.0
UNSEEN_MARGIN_DB = 3.0  # room kept for peaks not heard yet, times the share of the video still to come
SILENT_LUFS = -70.0  # ebur128's floor: no sound worth measuring
MAX_MEASURING = 2
TIMEOUT = 600

_lock = threading.Lock()
_measuring: set[str] = set()


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="loudness", daemon=True).start()


START: Callable[[Callable[[], None]], None] = (
    _thread  # how `ensure` runs a measurement (the tests' conftest runs none unless asked)
)


def read(video_id: str) -> Row | None:
    """The last measurement of a copy: `{seconds, segments, complete, integrated, peak, error, measured}` (integrated in LUFS, peak in dBFS,
    either None for a copy with no sound; `error` when ffmpeg could not measure it); None when it was never measured."""
    with db.connect() as con:
        r = db.row(con.execute("SELECT * FROM loudness WHERE video_id = ?", (video_id,)))
    if r is None:
        return None
    r["complete"] = bool(r["complete"])
    return r


def keep(video_id: str, m: Row) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM loudness WHERE video_id = ?", (video_id,))
        con.execute(
            "INSERT INTO loudness (video_id, seconds, segments, complete, measured, integrated, peak, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                video_id,
                m["seconds"],
                m["segments"],
                m["complete"],
                cache.stamp(),
                m.get("integrated"),
                m.get("peak"),
                m.get("error"),
            ),
        )


def gain_db(m: Row | None, duration: float | None, target: float) -> float | None:
    """The gain in dB for a measurement, or None to play the copy as it is (not measured, or not enough of it yet). `duration` is the
    video's whole length when known (the share still to come leaves room for its peaks)."""
    if m is None or m.get("error") or (float(m["seconds"]) < MIN_SECONDS and not m["complete"]):
        return None
    integrated, peak = m.get("integrated"), m.get("peak")
    if integrated is None or float(integrated) <= SILENT_LUFS:
        return 0.0
    want = target - float(integrated)
    if want <= 0:
        return round(want, 2)  # brought down: never clips, needs no care
    headroom = CEILING_DB - (float(peak) if peak is not None else CEILING_DB)
    cap = MAX_RAISE_DB
    if not m["complete"]:
        seconds = float(m["seconds"])
        unseen = 1.0 if not duration else min(max(1 - seconds / duration, 0.0), 1.0)
        headroom -= UNSEEN_MARGIN_DB * unseen
        cap = min(MAX_RAISE_DB, FIRST_CAP_DB + RAISE_PER_DOUBLING * math.log2(seconds / MIN_SECONDS))
    return round(min(want, max(headroom, 0.0), cap), 2)


def factor(db: float | None) -> float | None:
    return None if db is None else round(10 ** (db / 20), 3)


def status(video_id: str, duration: float | None) -> Row:
    """What the player is given: `{gain, measured, integrated, peak, final}`. `gain` is a factor (None: as it is); `final` once a whole
    copy has been measured (or could not be), so the player can stop asking."""
    m = read(video_id)
    on = settings.get("loudness_on") == "true"
    db = gain_db(m, duration, settings.get_float("loudness_target")) if on else None
    return dict(
        gain=factor(db),
        measured=float(m["seconds"]) if m else 0.0,
        integrated=m.get("integrated") if m else None,
        peak=m.get("peak") if m else None,
        final=not on or bool(m and m["complete"]),
    )


def wanted(video_id: str, m: Row | None = None) -> bool:
    """Whether the copy should be measured (again) now: enough of it is there and it has doubled, or become whole, since the last time."""
    st = cache.status(video_id)
    whole = st["state"] == "ready" and bool(st["complete"])
    if not st["playable"] or (float(st["seconds"]) < MIN_SECONDS and not whole):
        return False
    m = m if m is not None else read(video_id)
    if m is None:
        return True
    if m["complete"]:
        return False
    return whole or float(st["seconds"]) >= 2 * float(m["seconds"])


def ensure(video_id: str) -> bool:
    """Starts measuring the copy in the background when it is `wanted`, unless it is being measured or MAX_MEASURING are running (the next
    status read asks again). Returns whether it started."""
    if settings.get("loudness_on") != "true" or not wanted(video_id):
        return False
    with _lock:
        if video_id in _measuring or len(_measuring) >= MAX_MEASURING:
            return False
        _measuring.add(video_id)

    def work() -> None:
        try:
            measure(video_id)
        finally:
            with _lock:
                _measuring.discard(video_id)

    START(work)
    return True


def _parts(video_id: str) -> tuple[list[str], float, bool]:
    """The files that make up what the player is given (init segment first), their seconds, and whether that is the whole copy."""
    text = cache.served_playlist(video_id) or ""
    listed = cache.lengths(text)
    init = cache.served_file(video_id, "init.mp4")
    files = [p for _s, name in listed if (p := cache.file_path(video_id, name))]
    if not init or len(files) != len(listed):
        return [], 0.0, False
    e = cache.entry(video_id)
    return (
        [init, *files],
        round(sum(s for s, _n in listed), 3),
        bool(e and e["state"] == "ready") and "#EXT-X-ENDLIST" in text,
    )


SUMMARY = re.compile(r"Summary:(.*)", re.S)
INTEGRATED = re.compile(r"\bI:\s+(-?[\d.]+) LUFS")
PEAK = re.compile(r"\bPeak:\s+(-?[\d.]+|-inf) dBFS")


def parse(stderr: str) -> tuple[float | None, float | None] | None:
    """(integrated LUFS, sample peak dBFS) from ffmpeg's ebur128 summary, None for either when there is no sound; None when there is no
    summary (ffmpeg failed)."""
    m = SUMMARY.search(stderr)
    if not m:
        return None
    i, p = INTEGRATED.search(m.group(1)), PEAK.search(m.group(1))
    if not i:
        return None
    integrated = float(i.group(1))
    peak = None if not p or p.group(1) == "-inf" else float(p.group(1))
    return (None if integrated <= SILENT_LUFS else integrated), peak


def command() -> list[str]:
    return [
        settings.get("ffmpeg"),
        "-hide_banner",
        "-nostats",
        "-threads",
        "1",
        "-i",
        "pipe:0",
        "-map",
        "0:a:0",
        "-af",
        "ebur128=peak=sample:framelog=verbose",  # each frame's figures at verbose, so only the summary is printed
        "-f",
        "null",
        "-",
    ]


def measure(video_id: str) -> Row | None:
    """Measures what is on disk of a copy now and keeps the figures; returns them (None when there was nothing to measure)."""
    files, seconds, complete = _parts(video_id)
    if not files:
        return None
    proc = subprocess.Popen(  # noqa: S603 (the configured ffmpeg, reading a pipe)
        command(), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    stdin = cast(IO[bytes], proc.stdin)  # stdin=PIPE: always there

    def feed() -> None:
        with contextlib.suppress(OSError):  # ffmpeg stopped reading (no sound in the file): its error says why
            for p in files:
                with open(p, "rb") as f:
                    while chunk := f.read(1 << 20):
                        stdin.write(chunk)
        with contextlib.suppress(OSError):
            stdin.close()

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    # Not communicate(): it closes stdin at once, under the feeder. The timer stops an ffmpeg that hangs.
    timer = threading.Timer(TIMEOUT, proc.kill)
    timer.start()
    try:
        err = proc.stderr.read() if proc.stderr else b""
        proc.wait()
    finally:
        timer.cancel()
    feeder.join(timeout=5)
    text = err.decode("utf8", "replace")
    found = parse(text) if proc.returncode == 0 else None
    m: Row = dict(seconds=seconds, segments=len(files) - 1, complete=complete)
    if found is None:
        tail = [ln for ln in text.strip().splitlines() if ln.strip()][-1:] or ["ffmpeg stopped without saying why"]
        m["error"] = tail[0][:300]
    else:
        m["integrated"], m["peak"] = found
    keep(video_id, m)
    return m


def measure_all(say: Callable[[str], None] = print) -> int:
    """Measures every whole copy in the cache that has no final measurement (`tubes loudness`); returns how many were measured."""
    done = 0
    for video_id in cache.ready_ids():
        m = read(video_id)
        if m and m["complete"]:
            continue
        r = measure(video_id)
        if r is None:
            continue
        done += 1
        say(
            f"{video_id}: {r['error']}"
            if r.get("error")
            else f"{video_id}: {r['integrated'] if r['integrated'] is not None else 'silent'} LUFS, peak {r['peak']} dBFS"
        )
    return done
