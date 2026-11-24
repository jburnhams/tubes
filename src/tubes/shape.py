"""Reading JSON that other services send (YouTube, iPlayer, Plex, SponsorBlock, yt-dlp) under pyright's strict mode.

`json.loads` gives `Any`, and `isinstance(x, dict)` on it narrows to `dict[Unknown, Unknown]`, which strict mode refuses everywhere it is used.
These give the shape the code expects, or an empty one when the service sent something else, so a parser reads on instead of failing."""

from typing import Any, cast


def obj(x: object) -> dict[str, Any]:
    """`x` when it is a JSON object, else `{}`."""
    return cast(dict[str, Any], x) if isinstance(x, dict) else {}


def arr(x: object) -> list[Any]:
    """`x` when it is a JSON array, else `[]`."""
    return cast(list[Any], x) if isinstance(x, list) else []


def objs(x: object) -> list[dict[str, Any]]:
    """The objects in `x` when it is a JSON array (anything else in it is left out), else `[]`."""
    return [obj(i) for i in arr(x) if _is_obj(i)]


def _is_obj(x: object) -> bool:
    return isinstance(x, dict)  # a bool, not a narrowing: obj() gives the typed view


Json = dict[str, Any]  # a JSON object another service sent, read with .get()


def first(x: object) -> Json:
    """The first object in `x` when it is a JSON array that starts with one, else `{}`."""
    items = arr(x)
    return obj(items[0]) if items else {}
