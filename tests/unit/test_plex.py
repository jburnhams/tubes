"""plex.py, and the Plex parts of catalogue.py, fetcher.py and the server, against the stand-in Plex server (tests/utils/fake_plex.py)."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from tubes import catalogue, db, fetcher, library, metadata, plex, segments
from tubes.server.app import create_app

NOW = "2026-11-14T12:00:00+00:00"


def test_not_set_up_and_a_wrong_token(monkeypatch, fake_plex):
    monkeypatch.delenv("PLEX_TOKEN")
    assert not plex.configured()
    with pytest.raises(plex.PlexError, match="needs PLEX_URL and PLEX_TOKEN"):
        plex.sections()
    assert plex.reachable() == (
        False,
        "Plex is not set up: the server needs PLEX_URL and PLEX_TOKEN in its environment.",
    )
    monkeypatch.setenv("PLEX_TOKEN", "wrong")
    with pytest.raises(plex.PlexError, match="refused the token"):
        plex.sections()
    monkeypatch.setenv("PLEX_URL", "http://127.0.0.1:9")
    with pytest.raises(plex.PlexError, match="could not be reached"):
        plex.sections()


def test_libraries_filters_search_and_browse(fake_plex):
    fake_plex.film(101, "Harbour Lights", genres=("Animation", "Family"), rating="gb/U", age=5).film(
        102, "Dark Harbour", genres=("Drama",), rating="gb/15", age=15
    ).show(200, "The Lighthouse", episodes=2)
    assert plex.reachable() == (True, "1.43.5")
    assert plex.sections() == [
        dict(key="1", title="Films", type="movie", locations=["G:\\Films"]),
        dict(key="2", title="TV shows", type="show", locations=["D:\\TV"]),
    ]
    assert plex.filters("1")[0] == dict(filter="genre", title="Genre", type="string") and plex.choices("1", "genre")[
        1
    ] == dict(key="1", title="Animation")
    with pytest.raises(plex.PlexError, match="not a filter"):
        plex.choices("1", "nonsense")
    assert [i["title"] for i in plex.search("harbour")] == [
        "Harbour Lights",
        "Dark Harbour",
    ]  # an actor hub is left out
    page = plex.browse("1", dict(genre="1", contentRating="gb/U,gb/PG", bogus="x"))
    assert page["total"] == 1 and page["items"][0] == dict(
        key="101",
        type="movie",
        title="Harbour Lights",
        year=2023,
        thumb="api/plex/image?path=%2Flibrary%2Fmetadata%2F101%2Fthumb%2F1&w=300",
        summary="All about Harbour Lights",
        content_rating="gb/U",
        episodes=None,
        section="1",
    )
    assert plex.clean({"year>>=": 2000, "genre": "", "title": "x", "evil": "1", "contentRating!": "gb/18"}) == {
        "year>>=": "2000",
        "title": "x",
        "contentRating!": "gb/18",
    }
    assert plex.item(999) is None and [e["title"] for e in plex.episodes(200)] == ["Episode 1", "Episode 2"]
    with pytest.raises(plex.PlexError, match="no such item"):
        plex.episodes(999)


def test_everything_reads_page_after_page(fake_plex, monkeypatch):
    for k in range(5):
        fake_plex.film(110 + k, f"Film {k}")
    monkeypatch.setattr(plex, "PAGE", 2)
    assert [m["title"] for m in plex.everything("1")] == [f"Film {k}" for k in range(5)]


def test_rows_carry_plexs_metadata(fake_plex):
    fake_plex.film(101, "Harbour Lights", genres=("Animation",), rating="gb/U", age=5, codec="hevc", hdr=True).show(
        200, "The Lighthouse", episodes=1
    )
    v = plex.video_row(plex.item(101), plex.FILMS, NOW)
    assert (
        v["id"],
        v["kind"],
        v["year"],
        v["published"],
        v["duration"],
        v["content_rating"],
        v["min_age"],
        v["kids"],
        v["width"],
        v["height"],
        v["hdr"],
        v["definition"],
    ) == ("plex-101", "film", 2023, "2023-09-21T00:00:00+00:00", 5400.0, "gb/U", 5, True, 1920, 1080, True, "hd")
    assert (v["source"], v["language"], v["captions"], v["network"], v["tagline"], v["gone"], v["checked"]) == (
        "/library/parts/101/1700000000/file.mkv",
        "en",
        True,
        "Harbour Studios",
        "Harbour Lights, the film",
        None,
        "1",
    )
    assert (
        json.loads(v["colours"])["topLeft"] == "#012c5e"
        and v["thumbnail"] == "api/plex/image?path=%2Flibrary%2Fmetadata%2F101%2Fart%2F1&w=1280"
    )
    m = v["meta"]
    assert [i["kind"] for i in m["images"]] == ["thumb", "poster", "backdrop"]
    assert m["tags"] == [dict(kind="genre", value="Animation"), dict(kind="country", value="Canada")]
    assert m["credits"] == [
        dict(role="actor", rank=0, name="Ann Actor", character="Skye (voice)", photo="https://people.test/ann.jpg"),
        dict(role="actor", rank=1, name="Bob Actor", character=None, photo=None),
        dict(role="director", rank=0, name="Dee Rector", character=None, photo=None),
    ]
    assert m["ratings"] == [dict(source="imdb", value=5.9), dict(source="rottentomatoes_critic", value=7.1)]
    assert m["external_ids"] == [
        dict(source="imdb", value="tt0000101"),
        dict(source="tmdb", value="101"),
        dict(source="plex", value="movie/65"),
    ]
    assert m["chapters"] == [
        dict(
            start=0.0,
            end=60.0,
            title=None,
            image="api/plex/image?path=%2Flibrary%2Fmedia%2F101%2FchapterImages%2F1&w=320",
        ),
        dict(start=60.0, end=5400.0, title="Credits", image=None),
    ]
    assert m["tracks"] == [
        dict(
            kind="audio",
            rank=0,
            language="en",
            label="English (EAC3 5.1)",
            codec="eac3",
            ref="1",
            is_default=True,
            forced=False,
        ),
        dict(
            kind="subtitle",
            rank=0,
            language="fr",
            label="Français",
            codec="srt",
            ref="2",
            is_default=False,
            forced=True,
        ),
    ]
    thin = plex.video_row(plex.episodes(200)[0], "plex-200", NOW, details=False)
    assert (thin["kind"], thin["series"], thin["season"], thin["episode"], thin["captions"], thin["kids"]) == (
        "episode",
        "Season 1",
        1,
        1,
        None,
        None,
    ) and set(thin["meta"]) == {"images", "tags"}
    assert thin["meta"]["images"][0] == dict(
        kind="thumb", url="api/plex/image?path=%2Flibrary%2Fmetadata%2F201%2Fthumb%2F1&w=1280"
    )
    c = plex.channel_row(plex.item(200), NOW)
    assert (c["id"], c["kind"], c["kids"], c["thumbnail"], c["total_videos"]) == (
        "plex-200",
        "show",
        True,
        "api/plex/image?path=%2Flibrary%2Fmetadata%2F200%2FsquareArt%2F1&w=640",
        1,
    )
    assert plex.picture([dict(videoDynamicRange="HDR10", width=10, height=5)]) == (10, 5, True) and plex.picture(
        None
    ) == (None, None, None)
    assert (
        plex.image_path("/elsewhere/x") is None
        and plex.rating_key("plex-12") == "12"
        and plex.rating_key("abc") is None
    )


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("plex:21394", "21394"),
        ("PLEX:7", "7"),
        ("https://app.plex.tv/desktop/#!/server/abc/details?key=%2Flibrary%2Fmetadata%2F21394", "21394"),
        ("http://server.lan:32400/web/index.html#!/server/x/details?key=/library/metadata/55", "55"),
        ("@workshop", None),
        ("https://example.test/library/metadata/5", None),
    ],
)
def test_parse(text, key):
    assert plex.parse(text) == key


def test_follow_a_film_and_a_show_and_sync_them(fake_plex):
    fake_plex.film(101, "Harbour Lights").show(200, "The Lighthouse", episodes=2)
    r = catalogue.add("plex:101", now=NOW)
    assert (
        r["kind"] == "video"
        and (r["video"]["channel"], r["video"]["kind"]) == ("Films", "film")
        and library.channel(plex.FILMS)["follow"] is True
    )
    r = catalogue.add("plex:201", now=NOW)  # an episode brings its show in, followed
    assert r["kind"] == "channel" and (r["channel"]["id"], r["channel"]["kind"], r["channel"]["follow"]) == (
        "plex-200",
        "show",
        True,
    )
    s = catalogue.sync_channel("plex-200", now=NOW)
    assert (s["added"], s["title"]) == (2, "The Lighthouse") and [
        v["title"] for v in library.videos("plex-200")["videos"]
    ] == ["Episode 2", "Episode 1"]
    assert library.video("plex-201", meta=True)["meta"]["tracks"][0]["codec"] == "eac3"
    calls = len(fake_plex.calls)
    fake_plex.episode(200, 3)
    fake_plex.episode(200, 1, deleted=1700000500)
    fake_plex.items[201]["addedAt"] = 1  # a new one, and one whose file went
    assert catalogue.sync_channel("plex-200", now=NOW)["added"] == 1
    assert fake_plex.calls[calls:].count("/library/metadata/202") == 0  # unchanged: not read again
    assert library.video("plex-201")["gone"] is not None and [
        v["title"] for v in library.videos("plex-200")["videos"]
    ] == ["Episode 3", "Episode 2"]
    fake_plex.drop(202)
    catalogue.sync_channel("plex-200", now=NOW)
    assert library.video("plex-202")["gone"] == NOW
    fake_plex.items[101]["title"] = "Harbour Lights (2023)"
    fake_plex.items[101]["updatedAt"] = 2
    assert (
        catalogue.sync_channel(plex.FILMS, now=NOW)["added"] == 0
        and library.video("plex-101")["title"] == "Harbour Lights (2023)"
    )
    fake_plex.drop(101)
    catalogue.sync_channel(plex.FILMS, now=NOW)
    assert library.video("plex-101")["gone"] == NOW
    fake_plex.drop(200)
    with pytest.raises(catalogue.NotFound, match="no show plex-200"):
        catalogue.sync_channel("plex-200")
    with pytest.raises(catalogue.NotFound, match="no item 999"):
        catalogue.add_plex("999")
    fake_plex.items[300] = dict(ratingKey="300", type="artist", title="Band")
    with pytest.raises(catalogue.NotFound, match="not a film or a show"):
        catalogue.add_plex("300")


def test_a_followed_filter_is_a_channel_of_its_own(fake_plex):
    fake_plex.film(101, "Harbour Lights", genres=("Animation",), rating="gb/U").film(
        102, "Dark Harbour", genres=("Animation",), rating="gb/15"
    ).show(200, "The Lighthouse", episodes=2)
    c = catalogue.add_plex_filter("1", dict(genre="1", contentRating="gb/U,gb/PG"), " Animated films ", now=NOW)[
        "channel"
    ]
    assert (c["id"], c["title"], c["kind"], c["follow"]) == ("plex-filter-1", "Animated films", "filter", True)
    assert (
        catalogue.add_plex_filter("1", dict(contentRating="gb/U,gb/PG", genre="1"), "Cartoons")["channel"]["id"]
        == "plex-filter-1"
    )  # the same filters: the same channel, renamed
    assert library.channel("plex-filter-1")["title"] == "Cartoons"
    assert catalogue.sync_channel("plex-filter-1", now=NOW)["added"] == 1 and [
        v["id"] for v in library.videos("plex-filter-1")["videos"]
    ] == ["plex-101"]
    fake_plex.items[102]["contentRating"] = "gb/PG"
    fake_plex.items[101]["contentRating"] = "gb/18"  # one comes to match, one stops
    catalogue.sync_channel("plex-filter-1", now=NOW)
    assert [v["id"] for v in library.videos("plex-filter-1")["videos"]] == ["plex-102"] and library.video("plex-101")[
        "gone"
    ] == NOW
    tv = catalogue.add_plex_filter("2", {}, "", now=NOW)["channel"]
    assert (tv["id"], tv["title"]) == ("plex-filter-2", "TV shows")
    catalogue.add("plex:200")
    catalogue.sync_channel("plex-200")
    assert catalogue.sync_channel("plex-filter-2")["added"] == 0  # the show's episodes stay with the show
    assert library.video("plex-201")["channel_id"] == "plex-200"
    with pytest.raises(catalogue.NotFound, match="no film or TV library 9"):
        catalogue.add_plex_filter("9", {}, "Music")
    with db.connect() as con:
        con.execute(
            "UPDATE channels SET source = ? WHERE id = 'plex-filter-2'", (json.dumps(dict(section="7", params={})),)
        )
    with pytest.raises(catalogue.NotFound, match="no library 7"):
        catalogue.sync_channel("plex-filter-2")
    catalogue.remove("plex-filter-1")
    assert metadata.get("video", "plex-102")["images"] == []


def test_which_copy_and_how_it_is_made(fake_plex):
    fake_plex.film(101, "Harbour Lights").film(102, "Bright Harbour", codec="hevc", hdr=True).show(
        200, "The Lighthouse", episodes=1, codec="hevc"
    )
    for k in ("plex:101", "plex:102"):
        catalogue.add(k)
    catalogue.add("plex:200")
    catalogue.sync_channel("plex-200")
    assert fetcher.plex_copy("plex-101", ["h264", "hevc"]) == "plex-101"  # H.264 already: one copy for every browser
    assert fetcher.plex_copy("plex-201", ["h264", "hevc"]) == "plex-201~native"
    assert fetcher.plex_copy("plex-201", ["h264"]) == "plex-201" and fetcher.plex_copy("plex-201", None) == "plex-201"
    assert (
        fetcher.plex_copy("plex-102", ["hevc"]) == "plex-102"
        and fetcher.plex_copy("plex-102", ["hevc", "HDR"]) == "plex-102~native"
    )  # HDR only to a browser that says so
    assert fetcher.plex_copy("nothere", ["hevc"]) == "nothere"
    assert fetcher.base_id("plex-201~native") == "plex-201" and fetcher.platform("plex-201~native") == "plex"
    where, url = fetcher.source_url("plex-201~native")
    assert (
        where == "plex" and url == f"{fake_plex.url}/library/parts/201/1700000000/file.mkv"
    )  # the token goes as a header, never in an address an error could repeat
    assert (
        plex.headers() == "X-Plex-Token: test-token\r\n"
        and plex.redact("GET /x?X-Plex-Token=test-token failed") == "GET /x?X-Plex-Token=*** failed"
        and plex.redact(None) is None
    )
    with db.connect() as con:
        con.execute("UPDATE videos SET source = '/etc/passwd' WHERE id = 'plex-101'")
    with pytest.raises(fetcher.FetchError, match="is not a Plex file"):
        fetcher.source_url("plex-101")
    native = fetcher.plex_command("U", "hevc", True, 1080)
    assert (
        native[native.index("-headers") + 1] == "X-Plex-Token: test-token\r\n" and native[native.index("-i") + 1] == "U"
    )
    assert (
        native[native.index("-c:v") + 1 : native.index("-c:v") + 4] == ["copy", "-tag:v", "hvc1"]
        and native[native.index("-c:a") + 1] == "aac"
    )
    plain = fetcher.plex_command("U", "h264", False, 1080)
    assert plain[plain.index("-c:v") + 1] == "copy" and "-tag:v" not in plain
    made = fetcher.plex_command("U", "mpeg4", False, 720)
    assert (
        made[made.index("-c:v") + 1] == "libx264"
        and made[made.index("-vf") + 1] == "scale=-2:'min(ih,720)',format=yuv420p"
    )
    assert (
        "tonemap=hable"
        in fetcher.plex_command("U", "hevc", False, 1080, hdr=True)[
            fetcher.plex_command("U", "hevc", False, 1080, hdr=True).index("-vf") + 1
        ]
    )
    assert (
        fetcher.browser_plays("h264", None)
        and not fetcher.browser_plays("hevc", None)
        and fetcher.browser_plays("av1", ["AV1"])
    )
    assert segments.for_video("plex-201")["segments"] == []  # no skip points from Plex, and SponsorBlock is not asked


def test_a_plex_fetch_runs_ffmpeg_on_the_file(fake_plex, monkeypatch):
    fake_plex.film(101, "Harbour Lights", codec="mpeg4")
    catalogue.add("plex:101")
    ran = []

    def pipeline(job, url, duration=None, command=None):
        ran.append((url, command))
        return None

    monkeypatch.setattr(fetcher, "direct_pipeline", pipeline)
    monkeypatch.setattr(fetcher.cache, "evict", lambda *a, **k: None)
    fetcher.start("plex-101", "Harbour Lights", "Films", background=False)
    st = fetcher.cache.entry("plex-101")
    assert (
        st["formats"] == "mpeg4 converted to H.264, eac3 converted to AAC (Plex mkv)"
        and ran[0][1][ran[0][1].index("-c:v") + 1] == "libx264"
    )
    fake_plex.drop(101)
    fetcher.start("plex-101", "Harbour Lights", "Films", background=False)
    assert (
        fetcher.cache.entry("plex-101") is None
        or fetcher.cache.entry("plex-101")["error"] == "Plex no longer has this item."
    )


def fake_scaler(monkeypatch):
    """ffmpeg as a stand-in (unit tests run no other processes): writes the picture it was given, and records how it was asked."""
    import subprocess

    asked = []

    def run(cmd, input=None, **kw):
        asked.append(cmd)
        with open(cmd[-1], "wb") as f:
            f.write(input)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", run)
    return asked


def test_pictures_are_scaled_once_and_kept(fake_plex, monkeypatch):
    asked = fake_scaler(monkeypatch)
    p = plex.cached_image("/library/metadata/101/thumb/1", 300)
    assert p.endswith("-320.jpg") and os.path.getsize(p) > 0 and "scale='min(320,iw)':-2" in asked[0]
    n = len(fake_plex.calls)
    assert (
        plex.cached_image("/library/metadata/101/thumb/1", 320) == p and len(fake_plex.calls) == n and len(asked) == 1
    )
    assert os.listdir(os.path.dirname(p)) == [os.path.basename(p)]  # no temporary file left behind
    with pytest.raises(plex.PlexError, match="not a Plex picture"):
        plex.cached_image("/etc/passwd", 300)
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""))
    with pytest.raises(plex.PlexError, match="could not be scaled"):
        plex.cached_image("/library/metadata/102/thumb/1", 300)
    assert os.listdir(os.path.dirname(p)) == [os.path.basename(p)]


def test_overlapping_filters_leave_a_film_to_the_one_it_belongs_to(fake_plex):
    fake_plex.film(101, "Harbour Lights", genres=("Animation",), rating="gb/U")
    a = catalogue.add_plex_filter("1", dict(genre="1"), "Cartoons")["channel"]["id"]
    b = catalogue.add_plex_filter("1", dict(contentRating="gb/U"), "For everyone")["channel"]["id"]
    catalogue.sync_channel(a, now=NOW)
    catalogue.sync_channel(b, now=NOW)
    assert library.video("plex-101")["channel_id"] == a
    fake_plex.items[101]["Genre"] = []  # it leaves A, still matches B
    catalogue.sync_channel(a, now=NOW)
    catalogue.sync_channel(b, now=NOW)
    assert library.video("plex-101")["gone"] == NOW  # B does not bring back what A hid


def test_server_endpoints(fake_plex, monkeypatch):
    c = TestClient(create_app())
    monkeypatch.delenv("PLEX_URL")
    assert c.get("/api/plex").json() == dict(configured=False, reachable=False, version=None, sections=[])
    assert c.get("/api/plex/search?q=x").status_code == 503
    monkeypatch.setenv("PLEX_URL", fake_plex.url)
    fake_plex.film(101, "Harbour Lights", genres=("Animation",)).show(200, "The Lighthouse", episodes=1)
    r = c.get("/api/plex").json()
    assert (r["configured"], r["reachable"], r["version"], [s["key"] for s in r["sections"]]) == (
        True,
        True,
        "1.43.5",
        ["1", "2"],
    )
    assert (
        c.get("/api/plex/sections/1/filters").json()[0]["filter"] == "genre"
        and c.get("/api/plex/sections/1/filters/genre").json()[0]["title"] == "Action"
    )
    assert c.post("/api/plex/follow", json=dict(key="101")).json()["kind"] == "video"
    b = c.get("/api/plex/browse?section=1&genre=1&evil=1").json()
    assert (b["total"], b["items"][0]["followed"], b["params"]) == (1, True, dict(genre="1"))
    assert [(i["title"], i["followed"]) for i in c.get("/api/plex/search?q=the").json()] == [("The Lighthouse", False)]
    f = c.post("/api/plex/follow", json=dict(section="1", params=dict(genre="1"), title="Cartoons")).json()
    assert f["channel"]["id"] == "plex-filter-1" and "sync" in f
    assert c.post("/api/plex/follow", json={}).status_code == 400
    assert c.post("/api/plex/follow", json=dict(key="999")).status_code == 404
    monkeypatch.setattr(fetcher, "start", lambda *a, **k: None)
    p = c.post("/api/videos/plex-101/play", json=dict(decodes=["h264", "hevc"])).json()
    assert p["copy"] == "plex-101"
    fake_scaler(monkeypatch)
    img = c.get("/api/plex/image?path=/library/metadata/101/thumb/1&w=200")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert c.get("/api/plex/image?path=/etc/passwd").status_code == 502


def test_an_id_that_is_not_plex_s_is_no_item():
    assert plex.item(plex.rating_key("aaaaaaaaaaa")) is None  # a YouTube id: Plex is not asked
