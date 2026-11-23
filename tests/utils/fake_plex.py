"""A stand-in for a Plex Media Server (plex.py): its libraries, items with Plex's metadata, a show's episodes, search, filters and pictures.
A real HTTP server on localhost, answering from what a test puts in it, and refusing (401) a request without the token. Use through the
`fake_plex` fixture (tests/conftest.py), which sets PLEX_URL and PLEX_TOKEN:

    fake_plex.film(101, 'Harbour Lights', genres=('Animation',), rating='gb/U', age=5)
    fake_plex.show(200, 'The Lighthouse', episodes=3)                  # episodes 201-203, Season 1
    fake_plex.calls                                                     # each path asked for

Films are in section 1 (Films), shows in section 2 (TV shows). `/library/sections/<n>/all` filters by `genre` (a genre's id is its
position in GENRES), `contentRating` (comma-separated) and `title` (a substring), and pages with X-Plex-Container-Start/Size."""

import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "test-token"
GENRES = ("Action", "Animation", "Comedy", "Drama", "Family")
JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fbd3ffd9"
)


class FakePlex:
    def __init__(self):
        self.items, self.children, self.calls, self.lock = {}, {}, [], threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                with fake.lock:
                    fake.calls.append(u.path)
                if self.headers.get("X-Plex-Token") != TOKEN and q.get("X-Plex-Token") != TOKEN:
                    status, ctype, body = 401, "text/html", b"<html>Unauthorized</html>"
                else:
                    status, ctype, body = fake.answer(u.path, q)
                b = body if isinstance(body, bytes) else json.dumps(dict(MediaContainer=body)).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    # What Plex holds.

    @staticmethod
    def media(key, codec="h264", audio="eac3", height=1080, hdr=False):
        return [
            dict(
                id=key,
                videoCodec=codec,
                audioCodec=audio,
                container="mkv",
                width=height * 16 // 9,
                height=height,
                Part=[
                    dict(
                        id=key,
                        key=f"/library/parts/{key}/1700000000/file.mkv",
                        size=1000,
                        container="mkv",
                        Stream=[
                            dict(
                                streamType=1,
                                index=0,
                                codec=codec,
                                profile="high",
                                bitDepth=10 if hdr else 8,
                                colorTrc="smpte2084" if hdr else None,
                            ),
                            dict(
                                streamType=2,
                                index=1,
                                codec=audio,
                                languageTag="en",
                                displayTitle="English (EAC3 5.1)",
                                default=True,
                            ),
                            dict(
                                streamType=3,
                                index=2,
                                codec="srt",
                                languageTag="fr",
                                displayTitle="Français",
                                forced=True,
                            ),
                        ],
                    )
                ],
            )
        ]

    def film(self, key, title, genres=(), rating=None, age=None, year=2023, codec="h264", hdr=False, updated=1):
        self.items[key] = dict(
            ratingKey=str(key),
            key=f"/library/metadata/{key}",
            guid=f"plex://movie/{key:x}",
            type="movie",
            title=title,
            librarySectionID=1,
            summary=f"All about {title}",
            tagline=f"{title}, the film",
            year=year,
            studio="Harbour Studios",
            contentRating=rating,
            contentRatingAge=age,
            originallyAvailableAt=f"{year}-09-21",
            addedAt=1700000000,
            updatedAt=updated,
            duration=5400000,
            thumb=f"/library/metadata/{key}/thumb/{updated}",
            art=f"/library/metadata/{key}/art/{updated}",
            Genre=[dict(tag=g) for g in genres],
            Country=[dict(tag="Canada")],
            Image=[
                dict(type="coverPoster", url=f"/library/metadata/{key}/thumb/{updated}"),
                dict(type="background", url=f"/library/metadata/{key}/art/{updated}"),
            ],
            UltraBlurColors=dict(topLeft="012c5e", topRight="152d83", bottomRight="a42c1c", bottomLeft="103b76"),
            Media=self.media(key, codec=codec, hdr=hdr),
            _details=dict(
                Role=[
                    dict(tag="Ann Actor", role="Skye (voice)", thumb="https://people.test/ann.jpg"),
                    dict(tag="Bob Actor"),
                ],
                Director=[dict(tag="Dee Rector")],
                Rating=[
                    dict(image="imdb://image.rating", value=5.9, type="audience"),
                    dict(image="rottentomatoes://image.rating.ripe", value=7.1, type="critic"),
                ],
                Guid=[dict(id="imdb://tt0000101"), dict(id="tmdb://101")],
                Chapter=[
                    dict(startTimeOffset=0, endTimeOffset=60000, thumb=f"/library/media/{key}/chapterImages/1"),
                    dict(startTimeOffset=60000, endTimeOffset=5400000, tag="Credits"),
                ],
            ),
        )
        return self

    def show(self, key, title, episodes=0, rating="gb/U", age=4, codec="h264"):
        self.items[key] = dict(
            ratingKey=str(key),
            key=f"/library/metadata/{key}/children",
            guid=f"plex://show/{key:x}",
            type="show",
            title=title,
            librarySectionID=2,
            summary=f"All about {title}",
            year=2018,
            studio="Harbour TV",
            contentRating=rating,
            contentRatingAge=age,
            leafCount=episodes,
            updatedAt=1,
            thumb=f"/library/metadata/{key}/thumb/1",
            art=f"/library/metadata/{key}/art/1",
            Genre=[dict(tag="Animation")],
            Image=[
                dict(type="coverPoster", url=f"/library/metadata/{key}/thumb/1"),
                dict(type="backgroundSquare", url=f"/library/metadata/{key}/squareArt/1"),
            ],
            _details=dict(Role=[dict(tag="Cal Voice", role="Dad (voice)")], Guid=[dict(id="tvdb://200")]),
        )
        self.children[key] = []
        for n in range(1, episodes + 1):
            self.episode(key, n, codec=codec)
        return self

    def episode(self, show, n, codec="h264", deleted=None):
        key = show + n
        self.items[key] = dict(
            ratingKey=str(key),
            key=f"/library/metadata/{key}",
            type="episode",
            title=f"Episode {n}",
            grandparentTitle=self.items[show]["title"],
            grandparentRatingKey=str(show),
            parentTitle="Season 1",
            parentIndex=1,
            index=n,
            librarySectionID=2,
            summary=f"Episode {n}, told",
            contentRating="gb/U",
            year=2018,
            originallyAvailableAt=f"2018-10-{n:02d}",
            addedAt=1700000000 + n,
            duration=420000,
            thumb=f"/library/metadata/{key}/thumb/1",
            art=f"/library/metadata/{show}/art/1",
            Media=self.media(key, codec=codec, height=2160 if codec == "hevc" else 1080),
            **(dict(deletedAt=deleted) if deleted else {}),
        )
        if key not in self.children[show]:
            self.children[show].append(key)
        return key

    def drop(self, key):
        self.items.pop(key, None)
        for kids in self.children.values():
            if key in kids:
                kids.remove(key)

    # The answers.

    def thin(self, m):
        return {k: v for k, v in m.items() if k != "_details"}

    def full(self, m):
        return dict(self.thin(m), **m.get("_details", {}))

    def answer(self, path, q):
        if path == "/identity":
            return 200, "application/json", dict(version="1.43.5", machineIdentifier="fake")
        if path == "/library/sections":
            return (
                200,
                "application/json",
                dict(
                    Directory=[
                        dict(key="1", type="movie", title="Films", Location=[dict(path="G:\\Films")]),
                        dict(key="2", type="show", title="TV shows", Location=[dict(path="D:\\TV")]),
                        dict(key="9", type="artist", title="Music"),
                    ]
                ),
            )
        m = re.match(r"^/library/sections/(\d+)/all$", path)
        if m:
            kind = {"1": "movie", "2": "show"}.get(m[1])
            items = [i for i in self.items.values() if i["type"] == kind]
            if "genre" in q:
                items = [
                    i
                    for i in items
                    if any(
                        GENRES.index(g["tag"]) == int(q["genre"]) for g in i.get("Genre") or [] if g["tag"] in GENRES
                    )
                ]
            if "contentRating" in q:
                items = [i for i in items if i.get("contentRating") in q["contentRating"].split(",")]
            if "title" in q:
                items = [i for i in items if q["title"].lower() in i["title"].lower()]
            items.sort(key=lambda i: i["title"])
            start, size = int(q.get("X-Plex-Container-Start", 0)), int(q.get("X-Plex-Container-Size", 50))
            return (
                200,
                "application/json",
                dict(
                    totalSize=len(items),
                    size=len(items[start : start + size]),
                    Metadata=[self.thin(i) for i in items[start : start + size]],
                ),
            )
        m = re.match(r"^/library/sections/(\d+)/filters$", path)
        if m:
            return (
                200,
                "application/json",
                dict(
                    Directory=[
                        dict(filter="genre", title="Genre", filterType="string"),
                        dict(filter="unwatched", title="Unwatched", filterType="boolean"),
                    ]
                ),
            )
        m = re.match(r"^/library/sections/(\d+)/genre$", path)
        if m:
            return 200, "application/json", dict(Directory=[dict(key=i, title=g) for i, g in enumerate(GENRES)])
        if path == "/hubs/search":
            words = q.get("query", "").lower()
            hit = [i for i in self.items.values() if i["type"] in ("movie", "show") and words in i["title"].lower()]
            return (
                200,
                "application/json",
                dict(
                    Hub=[
                        dict(type="movie", Metadata=[self.thin(i) for i in hit if i["type"] == "movie"]),
                        dict(type="show", Metadata=[self.thin(i) for i in hit if i["type"] == "show"]),
                        dict(type="actor", Metadata=[dict(title="Someone")]),
                    ]
                ),
            )
        m = re.match(r"^/library/metadata/(\d+)/allLeaves$", path)
        if m:
            kids = self.children.get(int(m[1]))
            if kids is None:
                return 404, "text/html", b"<html>Not Found</html>"
            return 200, "application/json", dict(Metadata=[self.thin(self.items[k]) for k in kids])
        m = re.match(r"^/library/metadata/(\d+)$", path)
        if m:
            it = self.items.get(int(m[1]))
            if it is None:
                return 404, "text/html", b"<html>Not Found</html>"
            return (
                200,
                "application/json",
                dict(Metadata=[self.full(it) if q.get("includeChapters") else self.thin(it)]),
            )
        if re.match(r"^/library/(metadata|media)/\d+/[A-Za-z]+(/\d+){1,2}$", path):
            return 200, "image/jpeg", JPEG
        return 404, "text/html", b"<html>Not Found</html>"
