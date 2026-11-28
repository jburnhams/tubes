"""Loudness measured by the real ffmpeg (ebur128) over real HLS copies ffmpeg makes here: what tests/unit/test_loudness.py checks against
a stand-in ffmpeg. Skipped where ffmpeg is not on PATH (CI installs it on Linux)."""

import os
import shutil
import subprocess

import pytest

from tubes import cache, db, loudness

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="measuring needs ffmpeg on PATH")
VID = "aaaaaaaaaaa"
TARGET = -16.0


def make_copy(vid, seconds, volume=0.4, state="ready", segments=None):
    """A real copy: ffmpeg's HLS of a test pattern and a tone at `volume`, in the cache with a row, as a fetch leaves it. `segments` keeps
    only that many listed, without the end, as while it is fetched."""
    d = cache.folder(vid)
    os.makedirs(d, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=10:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds},volume={volume}",
            "-c:v", "libx264", "-preset", "ultrafast", "-g", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-f", "hls", "-hls_time", "2", "-hls_list_size", "0", "-hls_segment_type", "fmp4",
            "-hls_playlist_type", "event", "-hls_segment_filename", os.path.join(d, "seg_%05d.m4s"),
            os.path.join(d, cache.PLAYLIST),
        ],
        check=True,
    )  # fmt: skip
    if segments is not None:
        p = os.path.join(d, cache.PLAYLIST)
        with open(p, encoding="utf8") as f:
            lines = f.read().replace("#EXT-X-ENDLIST\n", "").splitlines(keepends=True)
        head = [ln for ln in lines if ln.startswith("#") and not ln.startswith("#EXTINF")]
        body = [ln for ln in lines if ln not in head]
        with open(p, "w", encoding="utf8") as f:
            f.writelines(head + body[: 2 * segments])
    with db.connect() as con:
        con.execute(
            "INSERT INTO copies (video_id, title, channel, state, bytes, started) VALUES (?, 't', 'c', ?, 0, '2026-11-28T00:00:00+00:00')",
            (vid, state),
        )


def run_now(monkeypatch):
    monkeypatch.setattr(loudness, "START", lambda work: work())


def test_a_whole_copy_is_measured_and_its_gain_given(monkeypatch):
    make_copy(VID, 12)
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    r = loudness.read(VID)
    assert r is not None and r["complete"] is True and r["segments"] == 6
    assert r["seconds"] == pytest.approx(12, abs=0.2)
    assert r["integrated"] == pytest.approx(
        -29.7, abs=1.0
    )  # a 440 Hz tone peaking at 0.05 (lavfi's sine is 1/8, times 0.4)
    # The tone peaks at -26 dBFS; how far the decoded AAC overshoots it depends on the ffmpeg build (-25 here, -21 on CI's Ubuntu).
    assert -27 < r["peak"] < -15
    s = loudness.status(VID, 12)
    assert s["final"] is True and s["gain"] == loudness.factor(loudness.gain_db(r, 12, TARGET))
    assert 3 < s["gain"] < 4.5  # raised about 12 dB, short of the ceiling
    assert loudness.ensure(VID) is False  # final: never measured again


def test_a_copy_being_fetched_is_measured_again_as_it_doubles(monkeypatch):
    make_copy(VID, 40, state="fetching", segments=7)  # 14 s listed
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    first = loudness.read(VID)
    assert first is not None and first["complete"] is False and first["seconds"] == cache.status(VID)["seconds"] == 14
    s = loudness.status(VID, 40)
    # 13.7 dB short of the target, but this early a raise is capped: 3 dB at 10 s, 4.46 at 14 s.
    assert s["final"] is False and s["gain"] == loudness.factor(4.46)
    assert loudness.wanted(VID) is False  # not doubled yet
    with db.connect() as con:
        con.execute("UPDATE copies SET state = 'ready' WHERE video_id = ?", (VID,))
    with open(os.path.join(cache.folder(VID), cache.PLAYLIST), "a", encoding="utf8") as f:
        f.write("".join(f"#EXTINF:2.000000,\nseg_{i:05d}.m4s\n" for i in range(7, 20)) + "#EXT-X-ENDLIST\n")
    assert loudness.wanted(VID) is True
    assert loudness.ensure(VID) is True
    last = loudness.read(VID)
    assert last is not None and last["complete"] is True and last["seconds"] == pytest.approx(40, abs=0.2)
    whole = loudness.status(VID, 40)
    assert whole["final"] is True and whole["gain"] == loudness.factor(
        loudness.MAX_RAISE_DB
    )  # quiet peaks: the whole 12 dB


def test_a_copy_without_sound_is_final_with_no_gain(monkeypatch, tmp_path):
    d = cache.folder(VID)
    os.makedirs(d)
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=12",
            "-c:v", "libx264", "-preset", "ultrafast", "-g", "20", "-f", "hls", "-hls_time", "2", "-hls_list_size", "0",
            "-hls_segment_type", "fmp4", "-hls_segment_filename", os.path.join(d, "seg_%05d.m4s"), os.path.join(d, cache.PLAYLIST),
        ],
        check=True,
    )  # fmt: skip
    with db.connect() as con:
        con.execute(
            "INSERT INTO copies (video_id, title, channel, state, bytes, started) VALUES (?, 't', 'c', 'ready', 0, '2026-11-28T00:00:00+00:00')",
            (VID,),
        )
    r = loudness.measure(VID)
    assert r is not None and r["complete"] is True and "error" in r
    assert loudness.status(VID, 12) == dict(gain=None, measured=r["seconds"], integrated=None, peak=None, final=True)


def test_the_figures_outlive_the_copy(monkeypatch):
    make_copy(VID, 12)
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    gain = loudness.status(VID, 12)["gain"]
    cache.forget([VID])  # evicted
    assert not os.path.isdir(cache.folder(VID))
    make_copy(VID, 12)  # fetched again
    assert loudness.wanted(VID) is False and loudness.status(VID, 12) == dict(
        loudness.status(VID, 12), gain=gain, final=True
    )


def test_a_prefetched_start_is_measured_when_it_is_kept(monkeypatch):
    make_copy(VID, 40, state="partial", segments=10)  # the first 20 s, kept with no end
    run_now(monkeypatch)
    assert loudness.ensure(VID) is True
    s = loudness.status(VID, 40)
    # A raise this early is held to 6 dB (3, and 3 more for having twice the minimum), however quiet the start.
    assert (s["measured"], s["final"], s["gain"]) == (20, False, loudness.factor(6.0))


def test_nothing_is_measured_while_too_little_is_there_or_normalising_is_off(monkeypatch):
    make_copy(VID, 12, state="fetching", segments=3)  # 4 s served
    assert loudness.wanted(VID) is False and loudness.ensure(VID) is False
    make_copy("bbbbbbbbbbb", 12)
    monkeypatch.setenv("TUBES_LOUDNESS_ON", "false")
    assert loudness.wanted("bbbbbbbbbbb") is True and loudness.ensure("bbbbbbbbbbb") is False
    assert loudness.status("bbbbbbbbbbb", 12)["gain"] is None


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


def test_measure_all_measures_the_whole_copies_not_measured_yet():
    make_copy("aaaaaaaaaaa", 12)
    make_copy("bbbbbbbbbbb", 12, state="fetching", segments=7)
    said: list[str] = []
    assert loudness.measure_all(say=said.append) == 1
    assert said[0].startswith("aaaaaaaaaaa: -") and "LUFS, peak -" in said[0]
    assert loudness.read("bbbbbbbbbbb") is None
    assert loudness.measure_all(say=said.append) == 0


def test_the_stream_status_measures_the_copy_and_gives_the_player_its_gain(monkeypatch):
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


def test_measure_all_passes_over_copies_with_nothing_to_measure_and_the_command_says_how_many(capsys):
    from tubes import cli

    make_copy("aaaaaaaaaaa", 12)
    with db.connect() as con:  # a whole copy whose files are gone
        con.execute(
            "INSERT INTO copies (video_id, title, channel, state, bytes, started) VALUES ('bbbbbbbbbbb', 't', 'c', 'ready', 0, '2026-11-28T00:00:00+00:00')"
        )
    assert cli.main(["loudness"]) == 0
    text = capsys.readouterr().out
    assert "aaaaaaaaaaa: -" in text and text.rstrip().endswith("measured 1 copy")
    assert cli.main(["loudness", "--json"]) == 0
    assert '"measured": 0' in capsys.readouterr().out
