"""Plex's pictures scaled by the real ffmpeg (plex.cached_image), served through the HTTP API, from the stand-in Plex server."""

import os
import shutil

import pytest
from fastapi.testclient import TestClient

from tubes import plex
from tubes.server.app import create_app

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def test_a_picture_is_scaled_by_ffmpeg_and_served(fake_plex):
    fake_plex.film(101, "Harbour Lights")
    r = TestClient(create_app()).get("/api/plex/image?path=/library/metadata/101/thumb/1&w=200")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    p = plex.cached_image("/library/metadata/101/thumb/1", 200)
    assert p.endswith("-320.jpg") and os.path.getsize(p) == len(r.content)
