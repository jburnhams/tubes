"""Command line. `doctor` checks the environment; `add`, `remove`, `sync` and `channels` manage the library from YouTube and BBC iPlayer; `history` imports a
watch history that suggestions are made from; `fetch`, `cache`, `evict` the cache; `set` the settings; `serve` starts the web server.
A timer on the server runs `tubes sync; tubes evict` every few hours (docs/deploy.md)."""
import argparse, importlib, json, os, sys

from tubes import __version__, cache, catalogue, fetcher, history, iplayer, library, oslib, settings, youtube, ytdlp

CHECKS = (('fastapi', 'fastapi'), ('uvicorn', 'uvicorn'), ('pydantic', 'pydantic'))


def doctor(args):
    ok = True; print(f'tubes {__version__}, python {sys.version.split()[0]}')
    for label, mod in CHECKS:
        try: m = importlib.import_module(mod); print(f'  ok       {label} {getattr(m, "__version__", "")}'.rstrip())
        except ImportError: ok = False; print(f'  MISSING  {label}: pip install -r requirements.txt')
    for label, version, fix in (('yt-dlp', ytdlp.version(), 'install yt-dlp, or set ytdlp to its path'), ('ffmpeg', fetcher.ffmpeg_version(), 'install ffmpeg, or set ffmpeg to its path')):
        if version: print(f'  ok       {label} {version}')
        else: ok = False; print(f'  MISSING  {label}: {fix}')
    if not oslib.CAN_PASS_FDS: ok = False; print('  MISSING  fetching needs Linux or macOS')
    if youtube.configured(): print('  ok       library: YOUTUBE_API_KEY set' + (' (sent with a Referer)' if os.environ.get('YOUTUBE_API_REFERER') else ''))
    else: ok = False; print('  MISSING  library: YOUTUBE_API_KEY is not in the environment, so nothing can be added or synced')
    here, why = iplayer.reachable()                                              # optional: without it only iPlayer episodes cannot be added or played
    print('  ok       iplayer: answers as in the UK' if here else f'  note     iplayer: {why}')
    lib = library.status()
    print(f"  library    {lib['channels']} channel(s), {lib['videos']} video(s), synced {lib['synced'] or 'never'}")
    print(f'  data       {settings.data_dir()}\n  cache      {settings.cache_dir()} (limit {settings.get("cache_limit_gb"):g} GB)')
    return 0 if ok else 1


def out(args, data, text):
    print(json.dumps(data, indent=1) if args.json else text); return 0


def gb(n): return f'{n / 1e9:.2f} GB'


def cmd_sync(args):
    """Sync the named channels, or every followed one; exits non-zero if any failed (the timer's log then shows it)."""
    if not youtube.configured() and catalogue.needs_youtube(args.channel or None): sys.exit('YOUTUBE_API_KEY is not in the environment, so the library cannot be synced.')
    r = catalogue.sync(args.channel or None)
    lines = [f"  {c['channel']:26} {c['added']:>6} new  {'complete' if c['complete'] else 'backfill continues next sync':30} {c['title'][:40]}" for c in r['channels']]
    lines += [f"  {e['channel'] or 'library':26} FAILED  {'' if e['channel'] else (e['title'] or 'the sync') + ': '}{e['error']}" for e in r['errors']] + [f"  {len(r['channels'])} channel(s) synced, {r['added']} new video(s)"]
    if r['recheck']: lines.append(f"  {r['recheck']['checked']} video(s) rechecked: {r['recheck']['gone']} gone from YouTube and hidden, {r['recheck']['back']} back")
    out(args, r, '\n'.join(lines))
    return 1 if r['errors'] else 0


def cmd_recheck(args):
    """Ask YouTube about the videos checked longest ago (or every one): hides the ones it no longer has and marks live streams, which the
    rolling recheck after each sync would otherwise reach over a few days."""
    if not youtube.configured(): sys.exit('YOUTUBE_API_KEY is not in the environment, so the library cannot be rechecked.')
    r = catalogue.recheck(limit=0 if args.all else args.limit)
    out(args, r, f"  {r['checked']} video(s) rechecked: {r['gone']} gone from YouTube and hidden, {r['back']} back"); return 0


def cmd_add(args):
    try: r = catalogue.add(args.input)
    except (ValueError, catalogue.NotFound, *catalogue.ERRORS) as e: sys.exit(str(e))
    if r['kind'] == 'video': return out(args, r, f"  added video {r['video']['id']}: {r['video']['title']}")
    c = r['channel']; print(f"  following {c['id']}: {c['title']}") if not args.json else None
    if args.no_sync: return out(args, r, '') if args.json else 0
    return cmd_sync(argparse.Namespace(channel=[c['id']], json=args.json))


def cmd_remove(args):
    try: r = catalogue.remove(args.channel)
    except catalogue.NotFound as e: sys.exit(str(e))
    return out(args, r, f"  removed {r['channel']} and {r['videos']} video(s)")


def cmd_channels(args):
    items = library.channels()
    if not items and not args.json: print('  (no channels yet: ./tubes add <channel link or @handle>)'); return 0
    state = lambda c: 'complete' if c['complete'] else 'backfilling' if c['follow'] else 'not followed'
    return out(args, items, '\n'.join(f"  {c['id']:26} {c['videos']:>6} videos  {state(c):12} {c['title'][:50]}" for c in items))


def describe_refresh(r):
    s = f"  {r['channels']} channel(s) in the history, {r['grouped']} in {r['groups']} group(s)"
    if r['looked_up']: s += f"; YouTube asked about {r['looked_up']} ({r['missing']} no longer there)"
    return s + (f"\n  YouTube could not be asked: {r['error']}" if r['error'] else '')


def cmd_history(args):
    """Import a Takeout watch history, list or forget the imported ones, or remake the suggestions."""
    try:
        if args.action == 'import':
            if not args.file or not args.source: sys.exit('usage: tubes history import FILE --source NAME')
            r = history.import_file(args.file, args.source, lookup=not args.no_lookup)
            return out(args, r, f"  {r['source']}: {r['watches']} watch(es) from {r['first'][:10]} to {r['last'][:10]}\n" + describe_refresh(r['refresh']))
        if args.action == 'sync':
            r = history.sync_database(lookup=not args.no_lookup)
            return out(args, r, '\n'.join([f'  {k}: {n} watch(es)' for k, n in r['sources'].items()] + [describe_refresh(r['refresh'])]))
        if args.action == 'refresh':
            r = history.refresh(lookup=not args.no_lookup); return out(args, r, describe_refresh(r))
        if args.action == 'remove':
            if not args.source: sys.exit('usage: tubes history remove --source NAME')
            r = history.remove_source(args.source); return out(args, r, f"  forgot {r['source']}\n" + describe_refresh(r['refresh']))
    except (history.ImportProblem, history.NotFound, OSError) as e: sys.exit(str(e))
    items = history.sources()
    if not items and not args.json: print('  (no history yet: ./tubes history import watch-history.json --source NAME)'); return 0
    return out(args, items, '\n'.join(f"  {s['source']:20} {s['watches']:>7} watches  {s['channels']:>6} channels  {s['first'][:10]} to {s['last'][:10]}" for s in items))


def cmd_fetch(args):
    v = library.video(args.video)
    if v is None: sys.exit(f'{args.video} is not in the library (./tubes add {args.video} first?)')
    try: st = fetcher.start(args.video, v['title'], v['channel'], background=False)
    except fetcher.FetchError as e: sys.exit(str(e))
    if st['state'] != 'ready': sys.exit(f"{args.video}: {st['error'] or st['state']}")
    return out(args, st, f"{args.video}: ready, {st['segments']} segments, {st['seconds']:.0f} s, {st['formats']}")


def cmd_cache(args):
    now = cache.utcnow(); u = cache.usage(now); items = cache.entries(now)
    lines = [f"  {gb(u['used'])} of {gb(u['limit'])} in {u['count']} video(s); eviction runs above {gb(u['high'])}, down to {gb(u['low'])}"]
    lines += [f"  {e['video_id']:14} {e['state']:8} {gb(e['bytes']):>9}  score {e['score']:<7g} plays {e['plays']:<4} {'pinned' if e['pinned'] else ''} {e['title'][:40]}".rstrip() for e in items]
    return out(args, dict(u, items=items), '\n'.join(lines))


def cmd_evict(args):
    r = cache.evict(cache.utcnow(), dry_run=args.dry_run)
    verb = 'would free' if args.dry_run else 'freed'
    return out(args, r, '\n'.join([f"  {verb} {gb(r['freed'])} from {len(r['evicted'])} video(s)"] + [f"  {e['video_id']:14} {gb(e['bytes']):>9}  score {e['score']:g}  {e['title'][:40]}" for e in r['evicted']]))


def cmd_set(args):
    if args.key not in settings.KNOWN: sys.exit(f'unknown setting {args.key!r}; known: {", ".join(settings.KNOWN)}')
    if args.value is not None:
        try: settings.save({args.key: None if args.value == 'default' else args.value})
        except settings.SettingError as e: sys.exit(str(e))
    print(f'{args.key} = {settings.all_settings()[args.key]}'); return 0


def cmd_serve(args):
    from tubes.server import app as server_app
    server_app.main(['--host', args.host, '--port', str(args.port)]); return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog='tubes'); sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor', help='check the environment').set_defaults(fn=doctor)
    y = sub.add_parser('sync', help="fetch new videos from YouTube for every followed channel (or the ones named)"); y.add_argument('channel', nargs='*'); y.add_argument('--json', action='store_true'); y.set_defaults(fn=cmd_sync)
    k = sub.add_parser('recheck', help='ask YouTube about the videos checked longest ago: hide those it no longer has, and live streams'); k.add_argument('--limit', type=int, default=None, help='how many (default: as many as a sync rechecks)'); k.add_argument('--all', action='store_true', help='every video in the library (a quota unit per 50)'); k.add_argument('--json', action='store_true'); k.set_defaults(fn=cmd_recheck)
    a = sub.add_parser('add', help='add a channel (followed, then synced) or one video: a link, an id or an @handle'); a.add_argument('input'); a.add_argument('--no-sync', action='store_true', help='add a channel without fetching its videos yet'); a.add_argument('--json', action='store_true'); a.set_defaults(fn=cmd_add)
    r = sub.add_parser('remove', help='remove a channel and its videos from the library'); r.add_argument('channel'); r.add_argument('--json', action='store_true'); r.set_defaults(fn=cmd_remove)
    h = sub.add_parser('channels', help='list the channels in the library'); h.add_argument('--json', action='store_true'); h.set_defaults(fn=cmd_channels)
    w = sub.add_parser('history', help='import a Google Takeout watch history (suggestions are made from it), sync the one in the history database (history_url, history_table), list them, remove one, or refresh the suggestions')
    w.add_argument('action', nargs='?', choices=('list', 'import', 'sync', 'remove', 'refresh'), default='list'); w.add_argument('file', nargs='?'); w.add_argument('--source', help='a name for the history, say the account it came from')
    w.add_argument('--no-lookup', action='store_true', help='do not ask YouTube about the channels'); w.add_argument('--json', action='store_true'); w.set_defaults(fn=cmd_history)
    f = sub.add_parser('fetch', help='fetch one video into the cache now (waits until it is done)'); f.add_argument('video'); f.add_argument('--json', action='store_true'); f.set_defaults(fn=cmd_fetch)
    c = sub.add_parser('cache', help='show the cache: use, limit and every copy with its score'); c.add_argument('--json', action='store_true'); c.set_defaults(fn=cmd_cache)
    e = sub.add_parser('evict', help='trim the cache when it is over 95%% of its limit'); e.add_argument('--dry-run', action='store_true'); e.add_argument('--json', action='store_true'); e.set_defaults(fn=cmd_evict)
    t = sub.add_parser('set', help='show or change a setting; value "default" resets it'); t.add_argument('key'); t.add_argument('value', nargs='?'); t.set_defaults(fn=cmd_set)
    v = sub.add_parser('serve', help='start the web server'); v.add_argument('--host', default='127.0.0.1'); v.add_argument('--port', type=int, default=8367); v.set_defaults(fn=cmd_serve)
    args = p.parse_args(argv); return args.fn(args)
