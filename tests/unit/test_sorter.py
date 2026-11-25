import re

import pytest
from hypothesis import given
from hypothesis import strategies as st
from library import CHANNELS, seed, video

from tubes import catalogue, cli, db, extents, settings, sorter

WORKSHOP, SKY = (c["id"] for c in CHANNELS)


def vid(n):
    return f"v{n:010d}"


def some(n, channel=0, first=0, part=lambda i: i % 2 == 0):
    """`n` videos: those `part` picks are two-minute scenes, the rest eleven-minute stories."""
    return [
        video(
            vid(first + i),
            channel,
            f"2026-01-01T{i // 3600 % 24:02d}:{i // 60 % 60:02d}:{i % 60:02d}Z",
            f"Scene {i}" if part(i) else f"Story {i}",
            120 if part(i) else 660,
        )
        for i in range(n)
    ]


def held():
    with db.connect() as con:
        return {r[0]: (r[1], r[2]) for r in con.execute("SELECT video_id, extent, said_by FROM video_extents")}


def guesses():
    with db.connect() as con:
        return dict(con.execute("SELECT video_id, guess FROM video_extents WHERE said_by = 'llm'").fetchall())


def answer(params):
    """What a good language model says of `some`: a scene is a clip."""
    lines = params["prompt"].splitlines()
    return dict(
        json=dict(
            videos=[
                dict(
                    i=int(re.match(r"\[(\d+)\]", line)[1]),
                    show="",
                    episode_minutes=11,
                    why="its length",
                    extent="clip" if "title: Scene" in line else "full_episode",
                )
                for line in lines
            ]
        ),
        cost_usd=0.001,
    )


@pytest.fixture
def llm(fake_models):
    fake_models.results["text"] = answer
    settings.save({"sort_model": "a-model", "sort_usd": "5"})
    return fake_models


def asked(fake):
    return [len(j["params"]["prompt"].splitlines()) for j in fake.jobs]


# --- rules and the model ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "length", "live", "expected"),
    [
        ("The Moon, Full Episode", 700, None, "full_episode"),
        ("FULL EPISODE! The Moon", 1800, None, "full_episode"),
        ("The Moon, full episode", 1801, None, None),
        ("The Moon, full episode", None, None, None),
        ("Full Episodes of The Moon", 700, None, None),
        ("The Moon", 3601, None, "several_episodes"),
        ("The Moon", 3600, None, None),
        ("The Moon, live", 1200, "was", "several_episodes"),
        ("The Moon, live", 1199, "was", None),
    ],
)
def test_rules(title, length, live, expected):
    assert sorter.rule(dict(title=title, duration=length, live=live)) == expected


def test_the_model_learns_what_it_is_shown():
    rows = [
        dict(v, extent="clip" if v["title"].startswith("Scene") else "full_episode", description="") for v in some(300)
    ]
    m = sorter.train(rows, {WORKSHOP: 400})
    scene, story = (dict(rows[i], title=t, duration=d) for i, t, d in ((0, "Scene new", 125), (1, "Story new", 640)))
    assert m.guess(sorter.features(scene, 400)) > 0.9
    assert m.guess(sorter.features(story, 400)) < 0.1


def test_there_is_no_model_before_there_is_something_to_learn():
    rows = [dict(v, extent="clip", description=None) for v in some(300)]
    assert sorter.train(rows, {}) is None  # only one kind
    assert (
        sorter.train([dict(r, extent="clip" if i % 2 else "standalone") for i, r in enumerate(rows[:100])], {}) is None
    )


@given(st.text(max_size=60), st.one_of(st.none(), st.floats(0, 1e6)), st.one_of(st.none(), st.text(max_size=60)))
def test_any_video_has_features(title, length, said):
    at = sorter.features(dict(channel_id="c", title=title, duration=length, description=said), 600)
    assert at and at == sorted(set(at)) and at[0] >= 0 and at[-1] < 1 << sorter.BITS


@given(st.lists(st.tuples(st.integers(0, (1 << sorter.BITS) - 1), st.booleans()), min_size=1, max_size=60))
def test_a_guess_is_always_a_share(learned):
    m = sorter.Model()
    for at, part in learned:
        m.learn([at], part)
        assert 0 <= m.guess([at]) <= 1


# --- trust -------------------------------------------------------------------------------------------------------------------------


def test_a_channel_is_trusted_by_its_last_answers():
    right, wrong, unsure = (0.95, "clip"), (0.95, "full_episode"), (0.5, "clip")
    assert sorter.trusted([right] * 75)
    assert not sorter.trusted([right] * 74)  # too few answers
    assert not sorter.trusted([right] * 49 + [unsure] * 30)  # too few it was sure of
    assert sorter.trusted([right] * 50 + [unsure] * 30)
    assert not sorter.trusted([wrong] * 4 + [right] * 71)  # 94.7% of the window
    assert sorter.trusted([wrong] * 3 + [right] * 72)  # 96%
    assert sorter.trusted([right] * 75 + [wrong] * 40)  # the old ones are out of the window
    assert not sorter.trusted([(None, "clip")] * 200)  # answers without a guess prove nothing
    assert sorter.trusted([(0.05, "several_episodes")] * 80)


# --- a run -------------------------------------------------------------------------------------------------------------------------


def test_nothing_new_is_nothing_to_do():
    assert sorter.work_out() == dict(rules=0, model=0, llm=0, left=0, trusted=0, channels=0, spent=0.0, problem=None)


def test_without_a_language_model_only_rules_answer():
    seed(videos=[video(vid(1), title="The Moon, full episode"), video(vid(2), duration=4000), video(vid(3))])
    r = sorter.work_out()
    assert (r["rules"], r["model"], r["llm"], r["left"]) == (2, 0, 0, 1)
    assert held() == {vid(1): ("full_episode", "rule"), vid(2): ("several_episodes", "rule")}


def test_only_videos_the_watching_side_shows_are_asked_about_clips_or_not(llm):
    seed(videos=some(6))
    with db.connect() as con:
        con.execute("UPDATE videos SET gone = 'then' WHERE id = ?", (vid(0),))
        con.execute("UPDATE videos SET platform = 'iplayer' WHERE id = ?", (vid(1),))
    catalogue.save_filters(dict(min_seconds=180, clips="hide"))  # leaves out the two-minute scenes
    assert sorter.work_out()["llm"] == 2 and set(held()) == {vid(3), vid(5)}
    catalogue.save_filters(dict(min_seconds=None))
    sorter.work_out()
    assert held()[vid(2)] == ("clip", "llm")  # shown or not is the clips filter's: it is asked about all the same


def test_a_new_channel_goes_to_the_language_model_until_the_model_can_be_trusted(llm):
    seed(videos=some(1200))
    extents.save([(vid(i), "clip" if i % 2 == 0 else "full_episode", "person") for i in range(400)])
    r = sorter.work_out()
    assert r["problem"] is None and r["left"] == 0 and r["trusted"] == 1 and r["channels"] == 1
    assert 75 <= r["llm"] < 250 and r["llm"] + r["model"] == 800
    assert r["spent"] == pytest.approx(0.001 * len(llm.jobs))
    answered = held()
    assert answered[vid(1)] == ("full_episode", "person")
    wrong = [v for v, (e, by) in answered.items() if by == "model" and (e == "clip") != (int(v[1:]) % 2 == 0)]
    assert wrong == [] and {e for e, by in answered.values() if by == "model"} == {"clip", "whole"}
    assert all(g is not None for g in guesses().values())
    audit = [vid(i) for i in range(400, 1200) if sorter.audited(vid(i))]
    assert audit and all(answered[v][1] == "llm" for v in audit)  # some are asked about even so
    assert max(asked(llm)) == sorter.BATCH


def test_a_channel_the_model_is_wrong_about_stays_with_the_language_model(llm):
    seed(videos=some(400) + some(120, channel=1, first=1000))
    extents.save([(vid(i), "clip" if i % 2 == 0 else "full_episode", "person") for i in range(400)])

    def contrary(params):
        r = answer(params)
        for v in r["json"]["videos"]:  # it changes its mind about what is what, so the model is never right for long
            v["extent"] = "clip" if (v["i"] * 7 + len(llm.jobs)) % 3 == 0 else "full_episode"
        return r

    llm.results["text"] = contrary
    r = sorter.work_out()
    assert (r["model"], r["llm"], r["trusted"], r["left"]) == (0, 120, 0, 0)


def test_with_nothing_to_learn_from_every_video_is_asked_about(llm):
    seed(videos=some(25))
    r = sorter.work_out()
    assert (r["llm"], r["model"], r["left"]) == (25, 0, 0)
    assert set(guesses().values()) == {None}  # no guess yet


def test_the_model_answers_a_trusted_channel_without_a_language_model(llm):
    seed(videos=some(900))
    extents.save([(vid(i), "clip" if i % 2 == 0 else "full_episode", "person") for i in range(300)])
    extents.save(
        [(vid(i), "clip" if i % 2 == 0 else "full_episode", "llm") for i in range(300, 400)],
        guesses={vid(i): 0.95 if i % 2 == 0 else 0.05 for i in range(300, 400)},
    )
    settings.save({"sort_model": ""})
    r = sorter.work_out()
    assert (r["llm"], r["trusted"], r["channels"]) == (0, 1, 1) and r["model"] > 450  # more than one turn of ALONE
    assert llm.jobs == []


def test_an_unclear_video_is_kept_as_such_and_one_left_out_waits_for_another_run(llm):
    seed(videos=some(3, part=lambda i: False))

    def vague(params):
        n = len(params["prompt"].splitlines())
        vs = [dict(i=0, extent="unclear"), dict(i=1, extent="full_episode"), dict(i=9, extent="clip"), dict(i=1.5)]
        return dict(json=dict(videos=vs[: 4 if n == 3 else 0]), cost_usd=None)

    llm.results["text"] = vague
    r = sorter.work_out()
    assert (r["llm"], r["left"], r["problem"]) == (2, 1, None) and len(llm.jobs) == 1
    assert sorted(e for e, _ in held().values()) == ["full_episode", "unclear"]


def test_a_service_that_is_down_leaves_the_rest_for_another_run(llm):
    seed(videos=some(25))
    llm.fail("no such model")
    r = sorter.work_out()
    assert "did not answer" in r["problem"] and "no such model" in r["problem"] and r["left"] == 25
    llm.down = True
    assert "did not answer" in sorter.work_out()["problem"]
    llm.down = False
    assert sorter.work_out()["left"] == 0


def test_the_months_money_is_a_limit_and_starts_again_next_month(llm):
    seed(videos=some(45))
    settings.save({"sort_usd": "0.0025"})
    r = sorter.work_out()
    assert (r["llm"], r["left"]) == (30, 15) and "0.0025 dollars" in r["problem"]
    assert sorter.spent("2026-01-05T00:00:00+00:00") == 0.0
    with db.connect() as con:
        con.execute("UPDATE meta SET value = '2020-01 4.5' WHERE key = ?", (sorter.SPENT,))
    assert sorter.spent() == 0.0 and sorter.work_out()["left"] == 0


def test_the_question_names_the_channel_its_typical_length_and_the_video():
    v = dict(
        id="x",
        channel_id="c",
        channel="Workshop",
        title="A shelf",
        duration=125,
        live="was",
        description="Built  in a day.\nhttps://example.test/shop more",
    )
    assert sorter.question([v, dict(v, channel=None, live=None, description=None, duration=None)], {"c": 600}) == (
        "[0] channel: Workshop (typical length 10m) | title: A shelf | 2m05s | past live stream | desc: Built in a day. more\n"
        "[1] channel: c (typical length 10m) | title: A shelf | 0m00s | desc: "
    )


def test_the_command_works_out_and_places(llm, capsys):
    seed(videos=some(4))
    assert cli.main(["sort"]) == 0
    said = capsys.readouterr().out
    assert "0 by a rule, 0 by the model, 4 by the language model, 0 left" in said and "placed in groups" in said
    llm.down = True
    seed(channels=[], videos=some(2, first=50), synced=None)
    assert cli.main(["sort"]) == 0 and "did not answer" in capsys.readouterr().out
    assert cli.main(["sort", "--json"]) == 0 and '"extents"' in capsys.readouterr().out
