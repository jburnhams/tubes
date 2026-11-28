"""Command line. `doctor` checks the environment; `add`, `remove`, `sync` and `channels` manage the library from YouTube and BBC iPlayer; `history` imports a
watch history that suggestions are made from; `related` asks YouTube which channels the followed and watched ones point at; `fetch`, `cache`, `evict` the cache; `quota` what the YouTube key has used today; `plays` what was watched here and how much; `set` the settings; `serve` starts the web server.
A timer on the server runs `tubes sync; tubes related; tubes evict` every few hours (docs/deploy.md)."""

import argparse
import json
import os
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from strata_python import cli as strata_cli

from tubes import (
    __version__,
    cache,
    catalogue,
    extents,
    fetcher,
    groups,
    history,
    iplayer,
    iplayer_suggest,
    library,
    loudness,
    quota,
    related,
    settings,
    sorter,
    viewing,
    youtube,
    ytdlp,
)
from tubes.db import Row

if TYPE_CHECKING:
    from fastapi import FastAPI

IMPORTS = ("fastapi", "uvicorn", "pydantic", "sqlalchemy", ("networkx (suggestion groups)", "networkx"))
HINT = "uv sync"


def _tool(version: Callable[[], str | None], fix: str) -> Callable[[], tuple[strata_cli.Status, str]]:
    def check() -> tuple[strata_cli.Status, str]:
        found = version()
        return ("ok", found) if found else ("missing", fix)

    return check


def _youtube() -> tuple[strata_cli.Status, str]:
    if youtube.configured():
        return "ok", "YOUTUBE_API_KEY set" + (" (sent with a Referer)" if os.environ.get("YOUTUBE_API_REFERER") else "")
    return "missing", "YOUTUBE_API_KEY is not in the environment, so nothing can be added or synced"


def _iplayer() -> tuple[strata_cli.Status, str]:
    here, why = iplayer.reachable()  # optional: without it only iPlayer episodes cannot be added or played
    return ("ok", "answers as in the UK") if here else ("missing", why or "iPlayer cannot be reached")


def _library() -> tuple[strata_cli.Status, str]:
    lib = library.status()
    return "ok", f"{lib['channels']} channel(s), {lib['videos']} video(s), synced {lib['synced'] or 'never'}"


# strata-python's doctor prints every app's rows in the same columns; these are what an import cannot tell.
CHECKS = (
    strata_cli.Check("yt-dlp", _tool(lambda: ytdlp.version(), "install yt-dlp, or set ytdlp to its path")),
    strata_cli.Check("ffmpeg", _tool(lambda: fetcher.ffmpeg_version(), "install ffmpeg, or set ffmpeg to its path")),
    strata_cli.Check(
        "fetching",
        lambda: (
            ("ok", "can pass pipes to ffmpeg") if fetcher.CAN_PASS_FDS else ("missing", "fetching needs Linux or macOS")
        ),
    ),
    strata_cli.Check("youtube", _youtube),
    strata_cli.Check("iplayer", _iplayer, optional=True),
    strata_cli.Check("database", _library),
    strata_cli.Check("data", lambda: ("ok", settings.data_dir())),
    strata_cli.Check(
        "cache", lambda: ("ok", f"{settings.cache_dir()} (limit {settings.get_float('cache_limit_gb'):g} GB)")
    ),
)


def out(args: argparse.Namespace, data: object, text: str) -> int:
    print(json.dumps(data, indent=1) if args.json else text)
    return 0


def gb(n: float) -> str:
    return f"{n / 1e9:.2f} GB"


def cmd_sync(args: argparse.Namespace) -> int:
    """Sync the named channels, or every followed one; a channel that fails is tried once more after the rest. Exits non-zero only when two
    or more channels still fail, or the quota ran out (catalogue.failed), so one passing hiccup does not set off the timer's alert."""
    if not youtube.configured() and catalogue.needs_youtube(args.channel or None):
        sys.exit("YOUTUBE_API_KEY is not in the environment, so the library cannot be synced.")
    r = catalogue.sync(args.channel or None)
    lines = [
        f"  {c['channel']:26} {c['added']:>6} new  {'complete' if c['complete'] else 'backfill continues next sync':30} {c['title'][:40]}"
        for c in r["channels"]
    ]
    lines += [f"  {e['channel']:26} failed once, then synced: {e['error']}" for e in r["recovered"]]
    lines += [
        f"  {e['channel'] or 'library':26} FAILED  {'' if e['channel'] else (e['title'] or 'the sync') + ': '}{e['error']}"
        for e in r["errors"]
    ] + [f"  {len(r['channels'])} channel(s) synced, {r['added']} new video(s)"]
    if r["recheck"]:
        lines.append(
            f"  {r['recheck']['checked']} video(s) rechecked: {r['recheck']['gone']} gone from YouTube and hidden, {r['recheck']['back']} back"
        )
    out(args, r, "\n".join(lines))
    return 1 if catalogue.failed(r) else 0


def cmd_recheck(args: argparse.Namespace) -> int:
    """Ask YouTube about the videos checked longest ago (or every one): hides the ones it no longer has and marks live streams, which the
    rolling recheck after each sync would otherwise reach over a few days."""
    if not youtube.configured():
        sys.exit("YOUTUBE_API_KEY is not in the environment, so the library cannot be rechecked.")
    r = catalogue.recheck(limit=0 if args.all else args.limit)
    out(args, r, f"  {r['checked']} video(s) rechecked: {r['gone']} gone from YouTube and hidden, {r['back']} back")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    try:
        r = catalogue.add(args.input)
    except (ValueError, catalogue.NotFound, *catalogue.ERRORS) as e:
        sys.exit(str(e))
    if r["kind"] == "video":
        return out(args, r, f"  added video {r['video']['id']}: {r['video']['title']}")
    c = r["channel"]
    print(f"  following {c['id']}: {c['title']}") if not args.json else None
    if args.no_sync:
        return out(args, r, "") if args.json else 0
    return cmd_sync(argparse.Namespace(channel=[c["id"]], json=args.json))


def cmd_remove(args: argparse.Namespace) -> int:
    try:
        r = catalogue.remove(args.channel)
    except catalogue.NotFound as e:
        sys.exit(str(e))
    return out(args, r, f"  removed {r['channel']} and {r['videos']} video(s)")


def cmd_channels(args: argparse.Namespace) -> int:
    items = library.channels()
    if not items and not args.json:
        print("  (no channels yet: ./tubes add <channel link or @handle>)")
        return 0

    def state(c: Row) -> str:
        return "complete" if c["complete"] else "backfilling" if c["follow"] else "not followed"

    return out(
        args,
        items,
        "\n".join(f"  {c['id']:26} {c['videos']:>6} videos  {state(c):12} {c['title'][:50]}" for c in items),
    )


def cmd_groups(args: argparse.Namespace) -> int:
    if args.action != "list":
        if not args.file:
            print("  Name the file of groups.", file=sys.stderr)
            return 2
        try:
            if args.action == "dump":
                text = groups.dump()
                with open(args.file, "w", encoding="utf8") as f:
                    f.write(text)
                return out(args, dict(file=args.file), f"  written to {args.file}")
            with open(args.file, encoding="utf8") as f:
                text = f.read()
            r = groups.renew(text) if args.action == "renew" else groups.load(text)
        except (OSError, UnicodeDecodeError, groups.BadFile, groups.TooDifferent) as e:
            print(f"  {e}", file=sys.stderr)
            return 1
        carried = r.get("carried")
        return out(
            args,
            r,
            f"  {r['groups']} group(s) of {r['videos']} video(s) loaded, {r['kept']} in place of an earlier one"
            + (f", {len(carried)} carried over as they were: {', '.join(carried)}" if carried else ""),
        )
    items = groups.listing()
    return out(
        args,
        items,
        "\n".join(f"  {g['id']:>5} {g['videos']:>6} videos  {(g['kind'] or ''):20} {g['name'][:50]}" for g in items)
        or "  (no groups yet: ./tubes groups load <file>)",
    )


def cmd_extents(args: argparse.Namespace) -> int:
    if args.action == "load":
        if not args.file:
            print("  Name the file to load.", file=sys.stderr)
            return 2
        try:
            with open(args.file, encoding="utf8") as f:
                r = extents.load(f.read())
        except (OSError, UnicodeDecodeError, extents.BadFile) as e:
            print(f"  {e}", file=sys.stderr)
            return 1
        return out(args, r, f"  {r['videos']} video(s) read, {r['kept']} kept (the rest have a stronger answer)")
    n = extents.counts()
    return out(args, n, "\n".join(f"  {k.replace('_', ' '):18} {v:>7}" for k, v in n.items()))


def cmd_sort(args: argparse.Namespace) -> int:
    r = dict(extents=sorter.work_out(), groups=groups.place())
    e, g = r["extents"], r["groups"]
    lines = [
        f"  {e['rules']} by a rule, {e['model']} by the model, {e['llm']} by the language model, {e['left']} left"
        f" ({e['trusted']} of {e['channels']} channel(s) are the model's; ${e['spent']:.2f} this month)",
        f"  {g['placed']} of {g['new']} new video(s) placed in groups ({g['memberships']} places)",
    ]
    if e["problem"]:
        lines.append(f"  {e['problem']}")
    return out(args, r, "\n".join(lines))


def cmd_quota(args: argparse.Namespace) -> int:
    u = quota.usage()
    lines = [
        f"  {u['used']:,} of {u['limit']:,} units used on {u['day']} (Pacific), {u['remaining']:,} left; resets {u['resets']}"
    ]
    if u["refused"]:
        lines.append(f"  YouTube refused a call for want of quota at {u['refused']}: nothing more until the reset")
    lines += [
        f"  {p['purpose']:14} {p['units']:>6} units  {p['calls']:>6} calls  {p['failed']:>4} failed"
        for p in u["today"]["purposes"]
    ]
    return out(args, u, "\n".join(lines))


def describe_refresh(r: Row) -> str:
    s = f"  {r['channels']} channel(s) in the history, {r['grouped']} in {r['groups']} group(s)"
    if r["looked_up"]:
        s += f"; YouTube asked about {r['looked_up']} ({r['missing']} no longer there)"
    return s + (f"\n  YouTube could not be asked: {r['error']}" if r["error"] else "")


def cmd_history(args: argparse.Namespace) -> int:
    """Import a Takeout watch history, list or forget the imported ones, or remake the suggestions."""
    try:
        if args.action == "import":
            if not args.file or not args.source:
                sys.exit("usage: tubes history import FILE --source NAME")
            r = history.import_file(args.file, args.source, lookup=not args.no_lookup)
            return out(
                args,
                r,
                f"  {r['source']}: {r['watches']} watch(es) from {r['first'][:10]} to {r['last'][:10]}\n"
                + describe_refresh(r["refresh"]),
            )
        if args.action == "sync":
            r = history.sync_database(lookup=not args.no_lookup)
            return out(
                args,
                r,
                "\n".join(
                    [f"  {k}: {n} watch(es)" for k, n in r["sources"].items()] + [describe_refresh(r["refresh"])]
                ),
            )
        if args.action == "refresh":
            r = history.refresh(lookup=not args.no_lookup)
            return out(args, r, describe_refresh(r))
        if args.action == "remove":
            if not args.source:
                sys.exit("usage: tubes history remove --source NAME")
            r = history.remove_source(args.source)
            return out(args, r, f"  forgot {r['source']}\n" + describe_refresh(r["refresh"]))
    except (history.ImportProblem, history.NotFound, OSError) as e:
        sys.exit(str(e))
    items = history.sources()
    if not items and not args.json:
        print("  (no history yet: ./tubes history import watch-history.json --source NAME)")
        return 0
    return out(
        args,
        items,
        "\n".join(
            f"  {s['source']:20} {s['watches']:>7} watches  {s['channels']:>6} channels  {s['first'][:10]} to {s['last'][:10]}"
            for s in items
        ),
    )


def cmd_related(args: argparse.Namespace) -> int:
    """Ask YouTube about the channels that are due (all with --all), count up what they point at, then look up the new ones' details.
    Exits non-zero only when every one asked failed (YouTube changed its page, or cannot be reached)."""

    def say(n: int, total: int, cid: str, got: Row) -> None:
        what = got["error"] or f"{len(got['links'])} channel(s) from {got['videos']} page(s)"
        print(f"  {n:>4}/{total} {cid:26} {what}", flush=True)

    r = related.refresh(
        limit=None if args.all or not args.limit else args.limit,
        force=args.all,
        progress=say if args.verbose and not args.json else None,
    )
    r["looked_up"] = r["lookup_error"] = None
    if youtube.configured():
        try:
            r["looked_up"] = history.look_up()["looked_up"]
        except youtube.YoutubeError as e:
            r["lookup_error"] = str(e)
    try:
        r["iplayer"] = iplayer_suggest.run(force=getattr(args, "all", False))
    except iplayer.IplayerError as e:
        r["iplayer"] = dict(error=str(e))
    lines = [f"  {e['channel']:26} FAILED  {e['error']}" for e in r["errors"][:20]]
    lines.append(
        f"  asked about {r['asked']} channel(s) ({r['failed']} failed), {r['due']} still due; {r['suggested']} channel(s) suggested by them, {r['added']} new"
    )
    if r["looked_up"]:
        lines.append(f"  YouTube asked about {r['looked_up']} channel(s)")
    if r["lookup_error"]:
        lines.append(f"  YouTube could not be asked about the channels: {r['lookup_error']}")
    ip: Row = r["iplayer"]
    cat: Row
    if ip.get("error"):
        lines.append(f"  iPlayer's catalogue could not be read: {ip['error']}")
    else:
        cat = ip["catalogue"]
        read = (
            f"read at {cat['skipped']}"
            if "skipped" in cat
            else f"read: {cat['read']} programmes, {cat['new']} new, {cat['dropped']} dropped"
        )
        lines.append(
            f"  iPlayer catalogue {read}; {ip['suggested']} programme(s) suggested from {ip['sources']} source(s), {ip['added']} new"
        )
    out(args, r, "\n".join(lines))
    return 1 if r["asked"] and r["failed"] == r["asked"] else 0


def cmd_fetch(args: argparse.Namespace) -> int:
    v = library.video(args.video)
    if v is None:
        sys.exit(f"{args.video} is not in the library (./tubes add {args.video} first?)")
    try:
        st = fetcher.start(args.video, v["title"], v["channel"], background=False)
    except fetcher.FetchError as e:
        sys.exit(str(e))
    if st["state"] != "ready":
        sys.exit(f"{args.video}: {st['error'] or st['state']}")
    return out(args, st, f"{args.video}: ready, {st['segments']} segments, {st['seconds']:.0f} s, {st['formats']}")


def cmd_cache(args: argparse.Namespace) -> int:
    now = cache.utcnow()
    u = cache.usage(now)
    items = cache.entries(now)
    lines = [
        f"  {gb(u['used'])} of {gb(u['limit'])} in {u['count']} video(s); eviction runs above {gb(u['high'])}, down to {gb(u['low'])}"
    ]
    lines += [
        f"  {e['video_id']:14} {e['state']:8} {gb(e['bytes']):>9}  score {e['score']:<7g} plays {e['plays']:<4} {'pinned' if e['pinned'] else ''} {e['title'][:40]}".rstrip()
        for e in items
    ]
    return out(args, dict(u, items=items), "\n".join(lines))


def cmd_evict(args: argparse.Namespace) -> int:
    r = cache.evict(cache.utcnow(), dry_run=args.dry_run)
    verb = "would free" if args.dry_run else "freed"
    return out(
        args,
        r,
        "\n".join(
            [f"  {verb} {gb(r['freed'])} from {len(r['evicted'])} video(s)"]
            + [
                f"  {e['video_id']:14} {gb(e['bytes']):>9}  score {e['score']:g}  {e['title'][:40]}"
                for e in r["evicted"]
            ]
        ),
    )


def cmd_loudness(args: argparse.Namespace) -> int:
    """Measures the loudness of every whole copy not measured yet (loudness.py), so each plays at the right level from its first second."""
    n = loudness.measure_all(say=(lambda line: None) if args.json else (lambda line: print(f"  {line}", flush=True)))
    return out(args, dict(measured=n), f"  measured {n} cop{'y' if n == 1 else 'ies'}")


def cmd_plays(args: argparse.Namespace) -> int:
    """The latest plays (where each was started from, how much was seen, how it went), then the last 30 days in numbers."""
    items, s = viewing.recent(args.limit)["items"], viewing.summary(args.days)

    def seen(p: Row) -> str:
        return f"{p['watched'] / p['length']:.0%}" if p["watched"] is not None and p["length"] else "–"

    lines = [
        f"  {p['at'][:16].replace('T', ' ')}  {p['outcome'] or '–':8} {seen(p):>4}  {p['source'] or '–':9} {p['video_id']:14} {(p['title'] or '')[:40]}"
        for p in items
    ]
    lines.append(
        f"  last {args.days} days: {s['plays']} play(s), " + ", ".join(f"{n} {k}" for k, n in s["outcomes"].items())
    )
    lines += [
        f"    from {k:9} {v['plays']:>5} play(s), {v['full']} watched to the end" for k, v in s["sources"].items()
    ]
    if s["channel_views"]:
        lines.append("  channel pages opened from " + ", ".join(f"{k} {n}" for k, n in s["channel_views"].items()))
    return out(args, dict(items=items, summary=s), "\n".join(lines))


def create_schema_app() -> "FastAPI":
    from .server.app import create_app

    return create_app(recover=False)  # the schema only: no database or cache touched


def serve(host: str, port: int) -> None:
    from tubes.server import app as server_app

    server_app.main(["--host", host, "--port", str(port)])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tubes")
    sub = p.add_subparsers(dest="cmd", required=True)
    strata_cli.add_doctor(sub, "tubes", __version__, IMPORTS, checks=CHECKS, hint=HINT)
    y = sub.add_parser("sync", help="fetch new videos from YouTube for every followed channel (or the ones named)")
    y.add_argument("channel", nargs="*")
    y.add_argument("--json", action="store_true")
    y.set_defaults(fn=cmd_sync)
    k = sub.add_parser(
        "recheck",
        help="ask YouTube about the videos checked longest ago: hide those it no longer has, and live streams",
    )
    k.add_argument("--limit", type=int, default=None, help="how many (default: as many as a sync rechecks)")
    k.add_argument("--all", action="store_true", help="every video in the library (a quota unit per 50)")
    k.add_argument("--json", action="store_true")
    k.set_defaults(fn=cmd_recheck)
    a = sub.add_parser("add", help="add a channel (followed, then synced) or one video: a link, an id or an @handle")
    a.add_argument("input")
    a.add_argument("--no-sync", action="store_true", help="add a channel without fetching its videos yet")
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_add)
    r = sub.add_parser("remove", help="remove a channel and its videos from the library")
    r.add_argument("channel")
    r.add_argument("--json", action="store_true")
    r.set_defaults(fn=cmd_remove)
    h = sub.add_parser("channels", help="list the channels in the library")
    h.add_argument("--json", action="store_true")
    h.set_defaults(fn=cmd_channels)
    v = sub.add_parser(
        "groups",
        help="list the groups of videos; load them from a file in place of those there, renew them (a load that is careful with those there), or dump them to one",
    )
    v.add_argument("action", nargs="?", choices=("list", "load", "renew", "dump"), default="list")
    v.add_argument("file", nargs="?")
    v.add_argument("--json", action="store_true")
    v.set_defaults(fn=cmd_groups)
    x = sub.add_parser(
        "extents", help="count the videos known to be a full episode, a clip, a promo..., or load answers from a file"
    )
    x.add_argument("action", nargs="?", choices=("list", "load"), default="list")
    x.add_argument("file", nargs="?")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=cmd_extents)
    o = sub.add_parser(
        "sort",
        help="work out whether new videos are whole or a clip or promo, and put them in their groups (run after a sync)",
    )
    o.add_argument("--json", action="store_true")
    o.set_defaults(fn=cmd_sort)
    w = sub.add_parser(
        "history",
        help="import a Google Takeout watch history (suggestions are made from it), sync the one in the history database (history_url, history_table), list them, remove one, or refresh the suggestions",
    )
    w.add_argument("action", nargs="?", choices=("list", "import", "sync", "remove", "refresh"), default="list")
    w.add_argument("file", nargs="?")
    w.add_argument("--source", help="a name for the history, say the account it came from")
    w.add_argument("--no-lookup", action="store_true", help="do not ask YouTube about the channels")
    w.add_argument("--json", action="store_true")
    w.set_defaults(fn=cmd_history)
    q = sub.add_parser(
        "related",
        help="ask YouTube which channels the followed and most watched ones point at (each again after a week), and suggest them",
    )
    q.add_argument(
        "--limit",
        type=int,
        default=related.RUN_LIMIT,
        help=f"ask about at most this many channels (default {related.RUN_LIMIT}; 0 for no limit)",
    )
    q.add_argument("--all", action="store_true", help="ask about every one now, due or not")
    q.add_argument("-v", "--verbose", action="store_true", help="a line per channel as it is asked")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_related)
    f = sub.add_parser("fetch", help="fetch one video into the cache now (waits until it is done)")
    f.add_argument("video")
    f.add_argument("--json", action="store_true")
    f.set_defaults(fn=cmd_fetch)
    c = sub.add_parser("cache", help="show the cache: use, limit and every copy with its score")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_cache)
    e = sub.add_parser("evict", help="trim the cache when it is over 95%% of its limit")
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--json", action="store_true")
    e.set_defaults(fn=cmd_evict)
    q = sub.add_parser(
        "quota", help="show how much of the YouTube Data API's daily quota has been used today, and on what"
    )
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_quota)
    n = sub.add_parser(
        "loudness",
        help="measure how loud every cached copy is, for the ones not measured yet (the player evens them out)",
    )
    n.add_argument("--json", action="store_true")
    n.set_defaults(fn=cmd_loudness)
    g = sub.add_parser("plays", help="show the latest plays here, where each was started from and how much was watched")
    g.add_argument("--limit", type=int, default=20)
    g.add_argument("--days", type=int, default=30, help="the summary covers this many days")
    g.add_argument("--json", action="store_true")
    g.set_defaults(fn=cmd_plays)
    strata_cli.add_set(sub, settings.SETTINGS)
    strata_cli.add_openapi(sub, create_schema_app)  # tubes openapi [-o web/openapi.json | -] [--check]
    strata_cli.add_serve(sub, serve, default_port=8367)
    args = p.parse_args(argv)
    if args.cmd == "serve":
        return args.fn(args)  # the server's requests name their own purposes, or count as `other`
    with quota.purpose(args.cmd):
        return args.fn(args)  # YouTube calls a command makes count under its name unless its work names its own
