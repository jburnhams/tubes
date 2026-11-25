import json

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from library import VIDEOS, seed, video

from tubes import cli, db, extents, groups, library, viewing
from tubes.server.app import create_app

A, B, C, D = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd"


def text(*gs):
    return json.dumps(dict(groups=[dict(name=n, kind=k, videos=v) for n, k, v in gs]))


def load(*gs):
    return groups.load(text(*gs))


def first(monkeypatch):
    """The picture is always the first video that could picture the group."""
    monkeypatch.setattr(groups.random, "choice", lambda seq: seq[0])


def test_a_load_lists_groups_largest_first_with_the_best_video_as_picture(monkeypatch):
    seed()
    first(monkeypatch)
    assert load(("Stars", "topic", [[C, 0.4]]), ("Shelves", None, [[A, 0.2], [B, 0.9]])) == dict(
        groups=2, videos=3, kept=0
    )
    assert groups.listing() == [
        dict(id=2, name="Shelves", kind=None, videos=2, thumbnail=f"https://img.test/{B}.jpg", thumbnail_video=B),
        dict(id=1, name="Stars", kind="topic", videos=1, thumbnail=f"https://img.test/{C}.jpg", thumbnail_video=C),
    ]


def test_the_picture_is_one_of_the_ten_or_five_percent_that_represent_the_group_best(monkeypatch):
    many = [video(f"v{n:010d}", 0) for n in range(300)]
    seed(videos=many)
    load(
        ("Small", None, [[v["id"], n] for n, v in enumerate(many[:30])]),
        ("Big", None, [[v["id"], n] for n, v in enumerate(many)]),
        ("Tiny", None, [[v["id"], n] for n, v in enumerate(many[:4])]),
    )
    asked = []
    monkeypatch.setattr(groups.random, "choice", lambda seq: (asked.append([r["video_id"] for r in seq]), seq[0])[1])
    assert [g["name"] for g in groups.listing()] == ["Big", "Small", "Tiny"]
    best = lambda n, k: [many[i]["id"] for i in range(n - 1, n - 1 - k, -1)]
    assert asked == [best(300, 15), best(30, 10), best(4, 4)]


def test_five_percent_rounds_up():
    many = [video(f"v{n:010d}", 0) for n in range(221)]
    seed(videos=many)
    load(("Big", None, [[v["id"], n] for n, v in enumerate(many)]))
    assert len(groups._rows(None)) == 12


def test_the_picture_changes_between_reads():
    seed()
    load(("All", None, [[v["id"], 1] for v in VIDEOS]))
    assert {groups.listing()[0]["thumbnail_video"] for _ in range(200)} == {A, B, C, D}


def test_only_videos_that_are_shown_count_or_picture_a_group(monkeypatch):
    seed()
    first(monkeypatch)
    load(("Mixed", None, [[A, 3], [C, 2], ["gone0000000", 9]]), ("Hidden", None, [[D, 1]]))
    with db.connect() as con:
        con.execute("UPDATE videos SET gone = ? WHERE id IN (?, ?)", ("2026-11-01T00:00:00+00:00", A, D))
    assert [(g["name"], g["videos"], g["thumbnail_video"]) for g in groups.listing()] == [("Mixed", 1, C)]
    assert groups.group(2) == dict(id=2, name="Hidden", kind=None, videos=0, thumbnail=None, thumbnail_video=None)
    assert groups.group(99) is None


def test_a_group_whose_best_videos_have_no_picture_has_none():
    seed(videos=[dict(v, thumbnail=None) for v in VIDEOS])
    load(("All", None, [[A, 1]]))
    g = groups.group(1)
    assert (g["videos"], g["thumbnail"], g["thumbnail_video"]) == (1, None, None)


def test_a_load_keeps_the_id_and_the_given_name_of_the_group_it_is():
    seed()
    load(("Shelves", None, [[A, 1], [B, 1]]), ("Sky", None, [[C, 1], [D, 1]]))
    with db.connect() as con:
        con.execute("UPDATE video_groups SET name = ?, named = ? WHERE id = 2", ("Night sky", True))
    assert load(("Stars", "topic", [[C, 1], [D, 1]]), ("Wood", None, [[A, 1]]), ("New", None, [["x", 1]])) == dict(
        groups=3, videos=4, kept=2
    )
    with db.connect() as con:
        got = con.execute("SELECT id, name, kind, named FROM video_groups ORDER BY id").fetchall()
    assert [(r[0], r[1], r[2], bool(r[3])) for r in got] == [
        (1, "Wood", None, False),
        (2, "Night sky", "topic", True),
        (3, "New", None, False),
    ]


def test_an_id_is_never_used_again():
    seed()
    load(("One", None, [[A, 1]]), ("Two", None, [[C, 1]]))
    load(("One", None, [[A, 1]]))
    load(("One", None, [[A, 1]]), ("Three", None, [[D, 1]]))
    assert sorted(g["id"] for g in groups.listing()) == [1, 3]


def test_same_gives_each_old_group_to_the_one_that_shares_most():
    old = {7: {"a", "b", "c", "d"}, 8: {"x"}}
    assert groups.same([{"a": 1, "b": 1}, {"a": 1, "b": 1, "c": 1}, {"y": 1}], old) == [None, 7, None]
    assert groups.same([{"a": 1, "q": 1, "r": 1, "s": 1}], old) == [None]  # one of seven shared: too few
    assert groups.same([{"a": 1, "b": 1, "q": 1}], old) == [7]


@given(
    st.lists(st.sets(st.sampled_from("abcdefgh"), min_size=1), max_size=5),
    st.lists(st.sets(st.sampled_from("abcdefgh"), min_size=1), max_size=5),
)
def test_same_never_gives_an_id_twice(new, old):
    got = [i for i in groups.same([dict.fromkeys(n, 1.0) for n in new], dict(enumerate(old))) if i is not None]
    assert len(got) == len(set(got))


def test_a_video_listed_twice_keeps_its_best_score_and_an_empty_group_is_left_out():
    got = groups.read(text((" Shelves ", "x" * 50, [[A, 1], [A, 3], [B, 2]]), ("Empty", None, [])))
    assert got == [dict(name="Shelves", kind="x" * 32, videos={A: 3.0, B: 2.0})]


@pytest.mark.parametrize(
    ("content", "why"),
    [
        ("no", "not JSON"),
        ("{}", "no list of groups"),
        ('{"groups": [{"videos": []}]}', "Group 1 has no name"),
        ('{"groups": [{"name": "X"}]}', r"Group 1 \(X\) has no list of videos"),
        ('{"groups": [{"name": "X", "videos": ["a"]}]}', "not \\[id, score\\]"),
        ('{"groups": [{"name": "X", "videos": [["a", "high"]]}]}', "not \\[id, score\\]"),
        ('{"groups": [{"name": "X", "videos": [3]}]}', "not \\[id, score\\]"),
    ],
)
def test_a_file_that_is_not_groups_is_refused_and_changes_nothing(content, why):
    seed()
    load(("Shelves", None, [[A, 1]]))
    with pytest.raises(groups.BadFile, match=why):
        groups.load(content)
    assert [g["name"] for g in groups.listing()] == ["Shelves"]


def test_a_groups_videos_are_a_page_at_a_time_those_that_represent_it_best_first():
    seed()
    load(("Mixed", None, [[A, 0.2], [B, 0.5], [C, 0.9], [D, 0.5]]), ("Other", None, [[A, 9], [B, 0.1]]))
    page = library.videos(group_id=1, limit=2)
    assert ([v["id"] for v in page["videos"]], page["has_more"]) == ([C, B], True)  # B and D score the same: by id
    rest = library.videos(group_id=1, limit=2, after=library.cursor(page["videos"][-1]))
    assert ([v["id"] for v in rest["videos"]], rest["has_more"]) == ([D, A], False)
    assert library.videos(group_id=9)["videos"] == []


def test_every_video_of_a_group_comes_once_however_it_is_paged_even_when_scores_are_equal():
    many = [video(f"v{n:010d}", 0) for n in range(23)]
    seed(videos=many)
    load(("Same", None, [[v["id"], 1 / 3 if n % 2 else 0.1 + 0.2] for n, v in enumerate(many)]))
    got, after = [], None
    while True:
        page = library.videos(group_id=1, limit=4, after=after)
        got += [v["id"] for v in page["videos"]]
        if not page["has_more"]:
            break
        after = library.cursor(page["videos"][-1])
    assert len(got) == 23 and set(got) == {v["id"] for v in many}


def test_a_cursor_whose_video_has_left_the_group_ends_the_list():
    seed()
    load(("Mixed", None, [[A, 1], [C, 2]]))
    assert library.videos(group_id=1, after="2026-01-01T00:00:00Z|gone0000000") == dict(videos=[], has_more=False)


def test_the_videos_that_may_picture_a_group_come_first_on_its_page():
    many = [video(f"v{n:010d}", 0) for n in range(60)]
    seed(videos=many)
    load(("Big", None, [[v["id"], (n * 7) % 60] for n, v in enumerate(many)]))
    pictures = [r["video_id"] for r in groups._rows(None)]
    assert [v["id"] for v in library.videos(group_id=1, limit=10)["videos"]] == pictures


def test_the_api_lists_groups_and_their_videos():
    seed()
    load(("Shelves", "topic", [[A, 1], [B, 2]]))
    client = TestClient(create_app())
    (g,) = client.get("/api/groups").json()
    assert (g["id"], g["name"], g["videos"]) == (1, "Shelves", 2) and g["thumbnail_video"] in (A, B)
    assert client.get("/api/groups/1").json()["name"] == "Shelves"
    assert client.get("/api/groups/2").status_code == 404
    assert [v["id"] for v in client.get("/api/videos?group=1").json()["videos"]] == [B, A]


def test_a_play_from_a_group_says_which_group():
    seed()
    load(("Shelves", None, [[A, 1]]))
    viewing.start(A, "2026-11-10T10:00:00+00:00", source="group", detail="1", rank=0)
    (p,) = viewing.recent()["items"]
    assert (p["source"], p["detail"], p["detail_title"]) == ("group", "1", "Shelves")


def test_the_command_loads_and_lists_groups(tmp_path, capsys):
    seed()
    assert cli.main(["groups"]) == 0 and "no groups yet" in capsys.readouterr().out
    f = tmp_path / "g.json"
    f.write_text(text(("Shelves", "topic", [[A, 1], [B, 1]])), encoding="utf8")
    assert cli.main(["groups", "load", str(f)]) == 0
    assert "1 group(s) of 2 video(s) loaded, 0 in place" in capsys.readouterr().out
    assert cli.main(["groups"]) == 0 and "Shelves" in capsys.readouterr().out
    assert cli.main(["groups", "--json"]) == 0 and json.loads(capsys.readouterr().out)[0]["videos"] == 2


def test_the_command_says_what_is_wrong_with_a_file(tmp_path, capsys):
    assert cli.main(["groups", "load"]) == 2 and "Name the file" in capsys.readouterr().err
    assert cli.main(["groups", "load", str(tmp_path / "none.json")]) == 1 and "none.json" in capsys.readouterr().err
    (tmp_path / "bad.json").write_text("{}", encoding="utf8")
    assert (
        cli.main(["groups", "load", str(tmp_path / "bad.json")]) == 1 and "no list of groups" in capsys.readouterr().err
    )


# --- placing new videos -----------------------------------------------------------------------------------------------------------

TIMES = ("2026-11-01T00:00:00+00:00", "2026-11-02T00:00:00+00:00", "2026-11-03T00:00:00+00:00")


def library_of_two():
    """Twenty videos of a programme and twenty of a topic, grouped, as it was before TIMES[0]."""
    odd = [
        "amber",
        "birch",
        "cedar",
        "delta",
        "ember",
        "flint",
        "grove",
        "heron",
        "iris",
        "juniper",
        "kelp",
        "larch",
        "maple",
        "nettle",
        "olive",
        "poplar",
        "quartz",
        "reed",
        "spruce",
        "thorn",
    ]
    shelf = [video(f"s{n:010d}", 0, title=f"Shelf Stories: the {w} and {odd[-n]}") for n, w in enumerate(odd)]
    stars = [video(f"t{n:010d}", 1, title=f"Bright stars {w} {odd[n - 7]}") for n, w in enumerate(odd)]
    seed(videos=shelf + stars)
    load(
        ("Shelf Stories", "show", [[v["id"], 1 - n / 20] for n, v in enumerate(shelf)]),
        ("Bright stars", "topic", [[v["id"], 1 - n / 20] for n, v in enumerate(stars)]),
    )
    groups.place(TIMES[0])


def add(vid, title, channel=1, at=TIMES[1], description=None):
    v = video(vid, channel, title=title)
    with db.connect() as con:
        con.execute(
            "INSERT INTO videos (id, channel_id, title, published, duration, thumbnail, views, added, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vid, v["channel_id"], title, v["published"], 600, v["thumbnail"], 10, at, description),
        )


def where(vid):
    with db.connect() as con:
        return sorted(r[0] for r in con.execute("SELECT group_id FROM video_group_members WHERE video_id = ?", (vid,)))


def test_a_new_video_goes_where_its_words_or_its_title_say():
    library_of_two()
    add("n1", "Bright stars maple tonight")
    add(
        "n2", "Shelf Stories: an unlikely tale of glue", channel=1
    )  # says the name its group's titles say, from another channel
    add("n3", "Cooking a pie")
    assert groups.place(TIMES[2]) == dict(new=3, placed=2, memberships=2, waiting=0)
    assert (where("n1"), where("n2"), where("n3")) == ([2], [1], [])


def test_a_video_can_go_into_two_groups():
    library_of_two()
    add("n1", "Bright stars over Shelf Stories")
    groups.place(TIMES[2])
    assert where("n1") == [1, 2]


def test_a_video_is_placed_with_a_score_its_group_has():
    library_of_two()
    add("n1", "Bright stars maple")
    groups.place(TIMES[2])
    with db.connect() as con:
        (score,) = con.execute("SELECT score FROM video_group_members WHERE video_id = 'n1'").fetchone()
    assert 0 < score <= 1


def test_only_new_shown_videos_that_are_not_clips_are_placed():
    library_of_two()
    title = "Bright stars maple tonight"
    add("old", title, at="2026-10-01T00:00:00+00:00")
    add("gone", title)
    add("clip", title)
    add("promo", title)
    add("whole", title)
    with db.connect() as con:
        con.execute("UPDATE videos SET gone = 'then' WHERE id = 'gone'")
    extents.save([("clip", "clip", "llm"), ("promo", "promo", "llm"), ("whole", "whole", "model")])
    assert groups.place(TIMES[2])["new"] == 1
    assert [v for v in ("old", "gone", "clip", "promo", "whole") if where(v)] == ["whole"]
    assert groups.place("2026-11-04T00:00:00+00:00") == dict(new=0, placed=0, memberships=0, waiting=0)


def test_a_premiere_waits_until_it_is_shown_and_not_for_ever():
    library_of_two()
    for v in ("soon", "never"):
        add(v, "Bright stars maple tonight")
    with db.connect() as con:
        con.execute("UPDATE videos SET live = 'upcoming' WHERE id IN ('soon', 'never')")
    assert groups.place(TIMES[2]) == dict(new=0, placed=0, memberships=0, waiting=2)
    with db.connect() as con:
        con.execute("UPDATE videos SET live = 'was' WHERE id = 'soon'")
    assert groups.place("2026-11-20T00:00:00+00:00") == dict(new=1, placed=1, memberships=1, waiting=1)
    assert where("soon") == [2]
    assert groups.place("2027-01-20T00:00:00+00:00")["waiting"] == 0
    with db.connect() as con:
        con.execute("UPDATE videos SET live = 'was' WHERE id = 'never'")
    assert groups.place("2027-01-21T00:00:00+00:00")["new"] == 0


def test_the_first_time_only_the_time_is_noted():
    seed()
    add("n1", "Bright stars")
    assert groups.place(TIMES[2]) == dict(new=0, placed=0, memberships=0, waiting=0)
    with db.connect() as con:
        assert con.execute("SELECT value FROM meta WHERE key = ?", (groups.PLACED,)).fetchone()[0] == TIMES[2]


def test_a_library_without_groups_places_nothing():
    seed()
    groups.place(TIMES[0])
    add("n1", "Bright stars")
    assert groups.place(TIMES[2]) == dict(new=1, placed=0, memberships=0, waiting=0)


def test_a_group_whose_videos_have_gone_is_no_place():
    places = groups.Places({1: "Gone", 2: "!"}, {1: {"x": 1.0}, 2: {"y": 1.0}}, {"y": ("A shelf of oak", None)})
    assert set(places.centres) == {2} and places.named == {}  # a name with no words is in no title
    assert places.of("Nothing alike", None) == {}


# --- groups made again --------------------------------------------------------------------------------------------------------------


def big(name, first, n=80, kind="show"):
    return (name, kind, [[f"v{i:010d}", 1 - i / 1000] for i in range(first, first + n)])


def listed():
    with db.connect() as con:
        return [tuple(r) for r in con.execute("SELECT id, name FROM video_groups ORDER BY id").fetchall()]


def test_renew_is_a_load_when_the_new_groups_hold_the_old_ones():
    load(big("One", 0), big("Two", 200))
    r = groups.renew(text(big("One", 0, 90), big("Two", 200), big("Three", 400)))
    assert r == dict(groups=3, videos=250, kept=2, carried=[])
    assert listed() == [(1, "One"), (2, "Two"), (3, "Three")]


def test_a_group_cut_in_pieces_is_carried_over_and_a_piece_of_its_name_goes_back_into_it():
    load(big("One", 0), big("Two", 200), ("Small", None, [[f"v{i:010d}", 1] for i in range(300, 325)]))
    pieces = [big("One", 0, 30), ("One toys", "topic", [[f"v{i:010d}", 1] for i in range(30, 60)])]
    fresh = ("ONE", None, [[f"v{i:010d}", 0.5] for i in range(60, 95)])
    r = groups.renew(text(big("Two", 200), *pieces, fresh))
    assert r["carried"] == ["One"] and r["groups"] == 3  # Small is too small to carry
    got = groups.members()
    assert listed() == [(1, "One"), (2, "Two"), (4, "One toys")]
    assert len(got[1]) == 95 and len(got[4]) == 30


def test_groups_that_share_too_little_with_those_there_are_refused():
    load(big("One", 0), big("Two", 200), big("Three", 400))
    with pytest.raises(groups.TooDifferent, match="Only 1 of the 3"):
        groups.renew(text(big("One", 0), big("Other", 600), big("Another", 800)))
    assert [n for _, n in listed()] == ["One", "Two", "Three"]


def test_renew_where_there_are_none_is_a_load():
    assert groups.renew(text(big("One", 0))) == dict(groups=1, videos=80, kept=0, carried=[])


def test_a_dump_loads_back_to_the_same_groups():
    load(big("One", 0), ("Two", None, [["a", 0.25], ["b", 0.75]]))
    before, kept = groups.dump(), groups.members()
    load(big("Other", 500))
    groups.load(before)
    assert groups.dump() == before and list(groups.members().values()) == list(kept.values())
    assert [(g["name"], g["kind"]) for g in groups.every()] == [("One", "show"), ("Two", None)]


def test_the_command_renews_and_dumps(tmp_path, capsys):
    load(big("One", 0), big("Two", 200))
    f = tmp_path / "g.json"
    assert cli.main(["groups", "dump", str(f)]) == 0 and f.read_text(encoding="utf8") == groups.dump()
    f.write_text(text(big("Two", 200), big("New", 400)), encoding="utf8")
    assert cli.main(["groups", "renew", str(f)]) == 0
    said = capsys.readouterr().out
    assert "3 group(s)" in said and "1 carried over as they were: One" in said
    f.write_text(text(big("Elsewhere", 5000)), encoding="utf8")
    assert cli.main(["groups", "renew", str(f)]) == 1 and "nothing is changed" in capsys.readouterr().err
    assert cli.main(["groups", "dump"]) == 2
    assert cli.main(["groups", "dump", str(tmp_path / "no" / "g.json")]) == 1
