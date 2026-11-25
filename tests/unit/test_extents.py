import json

import pytest
from fastapi.testclient import TestClient
from library import seed

from tubes import catalogue, cli, db, extents, groups, library
from tubes.server.app import create_app

A, B, C, D = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd"


def held():
    with db.connect() as con:
        return {r[0]: (r[1], r[2]) for r in con.execute("SELECT video_id, extent, said_by FROM video_extents")}


def shown():
    return sorted(v["id"] for v in library.videos()["videos"])


def test_a_stronger_answer_stays_and_an_equal_one_is_replaced():
    assert extents.save([(A, "clip", "model"), (B, "promo", "llm"), (C, "clip", "person")], now="then") == 3
    assert extents.save([(A, "full_episode", "llm"), (B, "clip", "model"), (C, "promo", "rule")]) == 1
    assert held() == {A: ("full_episode", "llm"), B: ("promo", "llm"), C: ("clip", "person")}
    assert extents.save([(B, "clip", "llm"), (C, "standalone", "person")]) == 2
    assert held() == {A: ("full_episode", "llm"), B: ("clip", "llm"), C: ("standalone", "person")}


def test_nothing_to_save_saves_nothing_and_the_last_of_a_video_wins():
    assert extents.save([]) == 0 and held() == {}
    assert extents.save([(A, "clip", "llm"), (A, "promo", "llm")]) == 1
    assert held() == {A: ("promo", "llm")}


def test_clips_and_promos_are_left_out_only_when_chosen():
    seed()
    extents.save([(A, "clip", "llm"), (B, "promo", "llm"), (C, "several_episodes", "llm")])
    assert shown() == [A, B, C, D]
    catalogue.save_filters(dict(clips="hide"))
    assert shown() == [B, C, D] and library.status()["filtered"] == 1
    catalogue.save_filters(dict(promos="hide"))
    assert shown() == [C, D] and library.status()["filtered"] == 2
    assert [(c["videos"], c["hidden"]) for c in library.channels()] == [(2, 0), (0, 2)]
    assert library.video(A)["id"] == A  # a link still opens
    catalogue.save_filters(dict(clips="show"))
    assert shown() == [A, C, D]


def test_a_group_leaves_them_out_too():
    seed()
    groups.load(json.dumps(dict(groups=[dict(name="Shelves", videos=[[A, 2], [B, 1]])])))
    extents.save([(A, "clip", "llm")])
    catalogue.save_filters(dict(clips="hide"))
    (g,) = groups.listing()
    assert (g["videos"], g["thumbnail_video"]) == (1, B)


def test_counts_are_of_videos_still_in_the_library():
    seed()
    extents.save([(A, "clip", "llm"), (B, "clip", "model"), (C, "promo", "llm"), ("notthere000", "clip", "llm")])
    with db.connect() as con:
        con.execute("UPDATE videos SET gone = 'then' WHERE id = ?", (B,))
    assert extents.counts() == dict(full_episode=0, several_episodes=0, clip=1, promo=1, standalone=0, whole=0)


def test_the_api_says_how_many_are_known_and_how_many_are_left_out():
    seed()
    extents.save([(A, "clip", "llm"), (B, "clip", "llm"), (C, "promo", "llm")])
    client = TestClient(create_app())
    r = client.put("/api/library/shown", json=dict(clips="hide")).json()
    assert (r["clips"], r["promos"], r["known_clips"], r["known_promos"], r["filtered"]) == ("hide", "show", 2, 1, 2)
    assert client.put("/api/library/shown", json=dict(promos="never")).status_code == 400


@pytest.mark.parametrize(
    ("content", "why"),
    [
        ("no", "not JSON"),
        ("{}", "no list of videos"),
        ('{"videos": ["a"]}', "Video 1 is not"),
        ('{"videos": [["a", "clip", "llm"], ["b", "half", "llm"]]}', "Video 2 is not"),
        ('{"videos": [["a", "clip", "hearsay"]]}', "by one of model, llm, rule, person"),
    ],
)
def test_a_file_that_is_not_answers_is_refused_and_changes_nothing(content, why):
    with pytest.raises(extents.BadFile, match=why):
        extents.load(content)
    assert held() == {}


def test_the_command_loads_answers_and_counts_them(tmp_path, capsys):
    seed()
    f = tmp_path / "x.json"
    f.write_text(json.dumps(dict(videos=[[A, "clip", "llm"], [B, "full_episode", "rule"]])), encoding="utf8")
    assert cli.main(["extents", "load", str(f)]) == 0
    assert "2 video(s) read, 2 kept" in capsys.readouterr().out
    assert cli.main(["extents"]) == 0 and "full episode" in capsys.readouterr().out
    assert cli.main(["extents", "--json"]) == 0 and json.loads(capsys.readouterr().out)["clip"] == 1
    assert cli.main(["extents", "load"]) == 2 and "Name the file" in capsys.readouterr().err
    f.write_text("{}", encoding="utf8")
    assert cli.main(["extents", "load", str(f)]) == 1 and "no list of videos" in capsys.readouterr().err
