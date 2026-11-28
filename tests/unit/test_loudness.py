import os
import re
import subprocess
import threading
from typing import ClassVar

import pytest

from tubes import cache, db, loudness, settings

VID = "aaaaaaaaaaa"
TARGET = -16.0


def m(seconds=60.0, integrated=-26.0, peak=-12.0, complete=True, **kw):
    return dict(seconds=seconds, segments=int(seconds // 4), complete=complete, integrated=integrated, peak=peak, **kw)


# --- the gain -------------------------------------------------------------------------------------------------------------------


def test_nothing_measured_or_too_little_plays_as_it_is():
    assert loudness.gain_db(None, 600, TARGET) is None
    assert loudness.gain_db(m(seconds=8, complete=False), 600, TARGET) is None
    assert loudness.gain_db(m(error="no sound"), 600, TARGET) is None
    assert loudness.factor(None) is None


def test_a_whole_copy_is_raised_to_the_target_while_its_peaks_allow():
    assert (
        loudness.gain_db(m(integrated=-26, peak=-12), 60, TARGET) == 10.0
    )  # 10 dB short, 11 dB of room under the ceiling
    assert loudness.gain_db(m(integrated=-26, peak=-5), 60, TARGET) == 4.0  # peaks reach -1 dBFS first
    assert loudness.gain_db(m(integrated=-40, peak=-30), 60, TARGET) == loudness.MAX_RAISE_DB  # never more than 12 dB
    assert (
        loudness.gain_db(m(integrated=-20, peak=0.0), 60, TARGET) == 0.0
    )  # peaks already at full scale: left as it is
    assert loudness.factor(10.0) == pytest.approx(3.162, abs=0.001)


def test_a_loud_copy_is_brought_down_whatever_its_peaks():
    assert loudness.gain_db(m(integrated=-9, peak=0.5), 60, TARGET) == -7.0
    assert loudness.gain_db(m(integrated=-9, peak=0.5, seconds=10, complete=False), 3600, TARGET) == -7.0
    assert loudness.factor(-6.0) == pytest.approx(0.501, abs=0.001)


def test_silence_is_left_alone():
    assert loudness.gain_db(m(integrated=None, peak=None), 60, TARGET) == 0.0


def test_a_partial_copy_is_raised_carefully_and_less_so_as_more_arrives():
    """A quiet hour-long video (-30 LUFS, quiet peaks) as it downloads: 3 dB at 10 s, more at each doubling, the whole 12 dB once it is whole."""
    seen = [
        loudness.gain_db(m(integrated=-30, peak=-25, seconds=s, complete=False), 3600, TARGET)
        for s in (10, 20, 40, 80, 3000)
    ]
    assert seen == [3.0, 6.0, 9.0, 12.0, 12.0]
    assert loudness.gain_db(m(integrated=-30, peak=-25, seconds=3600), 3600, TARGET) == 12.0
    assert seen == sorted(seen)


def test_a_partial_copy_keeps_room_for_peaks_still_to_come():
    # 6 dB under the ceiling so far; with nine tenths of the video to come, 2.7 dB of that is kept back.
    assert loudness.gain_db(m(integrated=-30, peak=-7, seconds=360, complete=False), 3600, TARGET) == 3.3
    # The length not known: all of it counts as still to come.
    assert loudness.gain_db(m(integrated=-30, peak=-7, seconds=360, complete=False), None, TARGET) == 3.0
    assert loudness.gain_db(m(integrated=-30, peak=-7, seconds=3600), 3600, TARGET) == 6.0


def test_a_whole_copy_shorter_than_the_minimum_is_still_normalised():
    assert loudness.gain_db(m(seconds=6, integrated=-20, peak=-10), 6, TARGET) == 4.0


# --- ffmpeg's summary -----------------------------------------------------------------------------------------------------------

SUMMARY = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -23.4 LUFS
    Threshold: -33.4 LUFS

  Loudness range:
    LRA:         5.1 LU

  Sample peak:
    Peak:       -3.2 dBFS
"""


def test_parse():
    assert loudness.parse("noise\n" + SUMMARY) == (-23.4, -3.2)
    assert loudness.parse(SUMMARY.replace("-23.4", "-70.0").replace("-3.2", "-inf")) == (None, None)
    assert loudness.parse("Stream map '0:a:0' matches no streams.") is None
    assert loudness.parse("Summary:\n nothing") is None


# --- measuring a copy -----------------------------------------------------------------------------------------------------------


# --- measuring a copy, against a stand-in ffmpeg (tests/integration/test_loudness.py runs the real one) -------------------------


class FakeFfmpeg:
    """Stands in for ffmpeg's ebur128 pass: reads what it is fed on stdin and prints the summary for the figures the copy's segments
    carry (`I=<lufs> P=<dbfs>`, as `make_copy` writes them), or ffmpeg's error for a copy with no sound. Notes every run in `runs`."""

    runs: ClassVar[list["FakeFfmpeg"]] = []

    def __init__(self, cmd, stdin, stdout, stderr):
        self.cmd = cmd
        self.fed = bytearray()
        self.closed = threading.Event()
        self.returncode: int | None = None
        self.stdin = self
        self.stderr = self
        FakeFfmpeg.runs.append(self)

    def write(self, chunk):
        self.fed += chunk

    def close(self):
        self.closed.set()

    def read(self):  # stderr: what ffmpeg says once its input has ended
        assert self.closed.wait(5)
        found = re.search(rb"I=(\S+) P=(\S+)", bytes(self.fed))
        if not found:
            self.returncode = 1
            return b"Stream map '0:a:0' matches no streams.\n"
        self.returncode = 0
        i, p = found.group(1).decode(), found.group(2).decode()
        return SUMMARY.replace("-23.4", i).replace("-3.2", p).encode()

    def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


@pytest.fixture(autouse=True)
def ffmpeg(monkeypatch):
    FakeFfmpeg.runs = []
    monkeypatch.setattr(subprocess, "Popen", FakeFfmpeg)
    return FakeFfmpeg


def make_copy(vid, seconds, integrated=-30.0, peak=-25.0, state="ready", segments=None):
    """A copy as a fetch leaves it, in 2 s segments: an init segment, a playlist, and segments that tell FakeFfmpeg the figures
    (`integrated` None: no sound). `segments` keeps only that many listed, without the end, as while it is fetched."""
    d = cache.folder(vid)
    os.makedirs(d, exist_ok=True)
    count = int(seconds // 2)
    body = b"silent" if integrated is None else f"I={integrated} P={peak}\n".encode()
    with open(os.path.join(d, "init.mp4"), "wb") as f:
        f.write(b"init")
    for i in range(count):
        with open(os.path.join(d, f"seg_{i:05d}.m4s"), "wb") as f:
            f.write(body)
    listed = count if segments is None else segments
    with open(os.path.join(d, cache.PLAYLIST), "w", encoding="utf8") as f:
        f.write(
            '#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:2\n#EXT-X-PLAYLIST-TYPE:EVENT\n#EXT-X-MAP:URI="init.mp4"\n'
        )
        f.write("".join(f"#EXTINF:2.000000,\nseg_{i:05d}.m4s\n" for i in range(listed)))
        if segments is None:
            f.write("#EXT-X-ENDLIST\n")
    with db.connect() as con:
        con.execute(
            "INSERT INTO copies (video_id, title, channel, state, bytes, started) VALUES (?, 't', 'c', ?, 0, '2026-11-28T00:00:00+00:00')",
            (vid, state),
        )


def run_now(monkeypatch):
    monkeypatch.setattr(loudness, "START", lambda work: work())


def test_a_whole_copy_is_measured_and_its_gain_given(monkeypatch, ffmpeg):
    make_copy(VID, 12, integrated=-26.0, peak=-12.0)
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    run = ffmpeg.runs[0]
    assert run.cmd[run.cmd.index("-i") + 1] == "pipe:0" and "-threads" in run.cmd
    assert bytes(run.fed) == b"init" + b"I=-26.0 P=-12.0\n" * 6  # the init segment first, then every listed segment
    r = loudness.read(VID)
    assert r is not None and (r["complete"], r["segments"], r["seconds"], r["integrated"], r["peak"]) == (
        True,
        6,
        12,
        -26,
        -12,
    )
    assert loudness.status(VID, 12) == dict(
        gain=loudness.factor(10.0), measured=12, integrated=-26, peak=-12, final=True
    )
    assert loudness.ensure(VID) is False and len(ffmpeg.runs) == 1  # final: never measured again


def test_a_copy_being_fetched_is_measured_again_as_it_doubles(monkeypatch, ffmpeg):
    make_copy(VID, 40, state="fetching", segments=7)  # 14 s listed
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    first = loudness.read(VID)
    assert first is not None and first["complete"] is False and first["seconds"] == cache.status(VID)["seconds"] == 14
    # 14 dB short of the target, but this early a raise is capped: 3 dB at 10 s, 4.46 at 14 s.
    assert loudness.status(VID, 40)["gain"] == loudness.factor(4.46) and loudness.status(VID, 40)["final"] is False
    assert loudness.wanted(VID) is False and loudness.ensure(VID) is False  # not doubled yet
    with db.connect() as con:
        con.execute("UPDATE copies SET state = 'ready' WHERE video_id = ?", (VID,))
    with open(os.path.join(cache.folder(VID), cache.PLAYLIST), "a", encoding="utf8") as f:
        f.write("".join(f"#EXTINF:2.000000,\nseg_{i:05d}.m4s\n" for i in range(7, 20)) + "#EXT-X-ENDLIST\n")
    assert loudness.wanted(VID) is True and loudness.ensure(VID) is True
    whole = loudness.status(VID, 40)
    assert (whole["measured"], whole["final"], whole["gain"]) == (40, True, loudness.factor(loudness.MAX_RAISE_DB))
    assert len(ffmpeg.runs) == 2


def test_a_copy_without_sound_is_final_with_no_gain(ffmpeg):
    make_copy(VID, 12, integrated=None)
    r = loudness.measure(VID)
    assert r is not None and r["complete"] is True and r["error"] == "Stream map '0:a:0' matches no streams."
    assert loudness.status(VID, 12) == dict(gain=None, measured=12, integrated=None, peak=None, final=True)


def test_ffmpeg_that_says_nothing_is_kept_as_an_error(monkeypatch, ffmpeg):
    make_copy(VID, 12, integrated=None)
    monkeypatch.setattr(FakeFfmpeg, "read", lambda self: (self.closed.wait(5), setattr(self, "returncode", 1), b"")[2])
    assert loudness.measure(VID)["error"] == "ffmpeg stopped without saying why"  # type: ignore[index]


def test_a_feed_ffmpeg_stops_reading_ends_quietly(monkeypatch, ffmpeg):
    make_copy(VID, 12, integrated=None)

    def refuse(self, chunk):
        raise BrokenPipeError

    monkeypatch.setattr(FakeFfmpeg, "write", refuse)
    monkeypatch.setattr(
        FakeFfmpeg, "close", lambda self: (self.closed.set(), (_ for _ in ()).throw(BrokenPipeError()))[0]
    )
    assert "error" in (loudness.measure(VID) or {})


def test_the_figures_outlive_the_copy(monkeypatch, ffmpeg):
    make_copy(VID, 12)
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    gain = loudness.status(VID, 12)["gain"]
    cache.forget([VID])  # evicted
    assert not os.path.isdir(cache.folder(VID))
    make_copy(VID, 12)  # fetched again
    assert loudness.wanted(VID) is False and loudness.status(VID, 12)["gain"] == gain and len(ffmpeg.runs) == 1


def test_a_prefetched_start_is_measured_when_it_is_kept(monkeypatch):
    make_copy(VID, 40, state="partial", segments=10)  # the first 20 s, kept with no end
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    s = loudness.status(VID, 40)
    # A raise this early is held to 6 dB (3, and 3 more for having twice the minimum), however quiet the start.
    assert (s["measured"], s["final"], s["gain"]) == (20, False, loudness.factor(6.0))


def test_nothing_is_measured_while_too_little_is_there_or_normalising_is_off(monkeypatch, ffmpeg):
    make_copy(VID, 12, state="fetching", segments=3)  # 4 s served
    assert loudness.wanted(VID) is False and loudness.ensure(VID) is False
    make_copy("bbbbbbbbbbb", 12)
    monkeypatch.setenv("TUBES_LOUDNESS_ON", "false")
    assert loudness.wanted("bbbbbbbbbbb") is True and loudness.ensure("bbbbbbbbbbb") is False
    assert loudness.status("bbbbbbbbbbb", 12)["gain"] is None and ffmpeg.runs == []


def test_one_measurement_per_copy_and_at_most_two_at_once(monkeypatch):
    for v in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"):
        make_copy(v, 12)
    held: list[object] = []
    monkeypatch.setattr(loudness, "START", held.append)
    assert [loudness.ensure(v) for v in ("aaaaaaaaaaa", "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc")] == [
        True,
        False,
        True,
        False,
    ]
    for work in held:
        work()  # type: ignore[operator]
    assert loudness.read("aaaaaaaaaaa") and loudness.read("bbbbbbbbbbb") and loudness.ensure("ccccccccccc") is True


def test_measure_all_and_the_command_measure_the_whole_copies_not_measured_yet(capsys):
    from tubes import cli

    make_copy("aaaaaaaaaaa", 12, integrated=-20.5, peak=-4.0)
    make_copy("bbbbbbbbbbb", 12, state="fetching", segments=7)
    make_copy("ccccccccccc", 12, integrated=None)
    with db.connect() as con:  # a whole copy whose files are gone
        con.execute(
            "INSERT INTO copies (video_id, title, channel, state, bytes, started) VALUES ('ddddddddddd', 't', 'c', 'ready', 0, '2026-11-28T00:00:00+00:00')"
        )
    said: list[str] = []
    assert loudness.measure_all(say=said.append) == 2
    assert said == ["aaaaaaaaaaa: -20.5 LUFS, peak -4.0 dBFS", "ccccccccccc: Stream map '0:a:0' matches no streams."]
    assert loudness.read("bbbbbbbbbbb") is None
    loudness.keep(
        "aaaaaaaaaaa", dict(loudness.read("aaaaaaaaaaa") or {}, complete=False)
    )  # measured before it was whole
    assert cli.main(["loudness"]) == 0
    text = capsys.readouterr().out
    assert "aaaaaaaaaaa: -20.5 LUFS" in text and text.rstrip().endswith("measured 1 copy")
    assert cli.main(["loudness", "--json"]) == 0
    assert '"measured": 0' in capsys.readouterr().out


def test_the_stream_status_measures_the_copy_and_gives_the_player_its_gain():
    from fastapi.testclient import TestClient
    from library import seed

    from tubes.server.app import create_app

    seed()
    make_copy(VID, 12)
    client = TestClient(create_app())
    s = client.get(f"/api/videos/{VID}/stream").json()
    assert s["loudness"] == dict(gain=None, measured=0.0, integrated=None, peak=None, final=False)
    assert len(loudness.START.started) == 1  # type: ignore[attr-defined]  (conftest only notes it)
    loudness.START.started[0]()  # type: ignore[attr-defined]
    s = client.get(f"/api/videos/{VID}/stream").json()["loudness"]
    assert s["final"] is True and s["gain"] == loudness.factor(loudness.MAX_RAISE_DB) and s["measured"] == 12


@pytest.mark.parametrize("on", ["true", "false"])
def test_status_without_a_copy(on, monkeypatch):
    monkeypatch.setenv("TUBES_LOUDNESS_ON", on)
    s = loudness.status(VID, None)
    assert s == dict(gain=None, measured=0.0, integrated=None, peak=None, final=on == "false")
    assert loudness.ensure(VID) is False
    assert settings.get("loudness_on") == on


def test_measuring_runs_in_a_thread_of_its_own(monkeypatch):

    done = threading.Event()
    loudness._thread(done.set)
    assert done.wait(5)


def test_a_copy_with_a_listed_segment_missing_is_not_measured():
    os.makedirs(cache.folder(VID))
    with open(os.path.join(cache.folder(VID), cache.PLAYLIST), "w", encoding="utf8") as f:
        f.write('#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4.0,\nseg_00000.m4s\n#EXT-X-ENDLIST\n')
    assert loudness.measure(VID) is None and loudness.read(VID) is None
