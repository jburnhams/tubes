"""Fetching the start of the videos the watching side offers, before anyone plays them, so a play starts at once.

A play of a video with no copy waits for yt-dlp's probe and the first segment: about 4 s signed in, longer when YouTube makes the download
wait (fetcher.py). Here, in a background thread of the server, the first `prefetch_seconds` (default 20) of each video Home's first page
lists, and of the ones Up next and a channel's page just offered, are fetched one at a time and kept as partial copies (cache.py). Played,
such a copy starts from its prefix while the whole video is fetched behind it: the download runs at 20-50 times playback speed, so it is
level with the prefix within a few seconds.

How much: a video whose start is a part the player skips or offers to skip (an intro, a hook, a sponsor read: its `skip_<category>` setting
is ask or auto) gets those parts on top, so a skip lands on fetched video too; at most MAX_SECONDS. About 2-3 MB at 1080p for 20 s.

Going easy on YouTube: each prefetch is a probe (two at once when signed in, as for a play) and two short downloads, so they run one at
a time, GAP_SECONDS apart, never while a play's fetch runs, at most `prefetch_per_day` a day; a video whose prefetch failed is not tried
again for RETRY_HOURS, and YouTube asking to slow down ("try again later", "not a bot") pauses prefetching for PAUSE_SECONDS. Only YouTube
videos are prefetched (an iPlayer episode starts in about as long as its first segment takes anyway); live and scheduled streams are not."""
import collections, datetime, re, sys, threading, time

from tubes import cache, fetcher, library, segments, settings, ytdlp

HOME = 24                    # Home's first page (web: useVideos reads 24 at a time)
GAP_SECONDS = 5              # between two prefetches
WAITS = dict(busy=5, none=300, off=300, paused=60, limit=900)    # seconds before looking again, by why nothing was prefetched
PAUSE_SECONDS = 3600         # YouTube asked to slow down
RETRY_HOURS = 24
MAX_SECONDS = 300
ASKED = 100                  # how many recently offered videos are remembered
SLOW_DOWN = re.compile(r'try again later|not a bot|rate.?limit|too many requests|\b429\b', re.I)


def length(video_id):
    """How many seconds of a video's start to prefetch: `prefetch_seconds`, after the parts at the very start that the player skips or offers to skip."""
    base = settings.get('prefetch_seconds')
    try: found = segments.for_video(video_id)
    except Exception: return base                                               # SponsorBlock's answer is a bonus, never a reason not to prefetch
    modes = {c['id']: c['mode'] for c in found.get('categories') or []}
    reach = 0.0
    for s in sorted(found.get('segments') or [], key=lambda s: s['start']):
        if s['action'] != 'skip' or modes.get(s['category'], 'off') == 'off': continue
        if s['start'] > reach + 1: break                                       # not at the start (or right after one that is)
        reach = max(reach, s['end'])
    return min(reach + base, MAX_SECONDS)


class Prefetcher:
    """The background prefetcher: `want(ids)` when the watching side offers videos, `start()` once when the server starts, `state()` for System."""

    def __init__(self, clock=time.time):
        self.clock, self.lock, self.wake, self.thread, self.stopping = clock, threading.Lock(), threading.Event(), None, False
        self.asked = collections.OrderedDict()                                   # recently offered video ids, latest last
        self.tried = {}                                                          # video id -> when its prefetch last ran
        self.day, self.count, self.paused_until, self.last = None, 0, 0.0, None

    def want(self, video_ids):
        """These videos were just offered (Up next, a channel's page): prefetch them first."""
        with self.lock:
            for v in video_ids:
                self.asked.pop(v, None); self.asked[v] = None
            while len(self.asked) > ASKED: self.asked.popitem(last=False)
        self.wake.set()

    def candidates(self):
        """Video ids to consider, in order: the ones offered last first, then Home's first page."""
        with self.lock: ids = list(reversed(self.asked))
        try: ids += [v['id'] for v in library.videos(limit=HOME)['videos']]
        except Exception as e: print(f'tubes: prefetch could not read Home: {e}', file=sys.stderr, flush=True)
        return list(dict.fromkeys(ids))

    def eligible(self, video_id, now):
        if now - self.tried.get(video_id, -1e12) < RETRY_HOURS * 3600: return False
        v = library.video(video_id)
        if not v or (v['platform'] or 'youtube') != 'youtube' or v['live'] in ('live', 'upcoming') or v['gone']: return False
        return cache.entry(video_id) is None                                      # a copy of any kind (even failed, until it is played again) is left alone

    def step(self):
        """Prefetch one video if one is due; returns its id, or why not: off, paused, busy, limit or none."""
        now = self.clock()
        if settings.get('prefetch_seconds') <= 0 or settings.get('prefetch_per_day') <= 0: return 'off'
        if now < self.paused_until: return 'paused'
        if fetcher.running(): return 'busy'                                       # a play's fetch has the line and YouTube's attention
        today = datetime.date.fromtimestamp(now)
        if today != self.day: self.day, self.count = today, 0
        if self.count >= settings.get('prefetch_per_day'): return 'limit'
        vid = next((v for v in self.candidates() if self.eligible(v, now)), None)
        if vid is None: return 'none'
        self.tried[vid] = now; self.count += 1
        with self.lock: self.asked.pop(vid, None)
        v = library.video(vid); want = length(vid)
        try: st = fetcher.start(vid, v['title'], v['channel'], background=False, until=want)
        except fetcher.FetchError as e: st = dict(state='failed', error=str(e), seconds=0)
        error = st.get('error') if st['state'] == 'failed' else None
        if error and SLOW_DOWN.search(error): self.paused_until = now + PAUSE_SECONDS
        if error and not (ytdlp.says_gone(error) or ytdlp.says_blocked(error)) and (cache.entry(vid) or {}).get('state') == 'failed':
            cache.forget([vid])                                                   # nothing to show for it; tried again after RETRY_HOURS
        self.last = dict(video_id=vid, wanted=want, seconds=st.get('seconds', 0), state=st['state'], error=error, at=cache.stamp())
        return vid

    def run(self):
        while not self.stopping:
            try: why = self.step()
            except Exception as e:                                                # the database went away, say: try again later, never die
                print(f'tubes: prefetch failed: {e}', file=sys.stderr, flush=True); why = 'paused'
            self.wake.wait(WAITS.get(why, GAP_SECONDS)); self.wake.clear()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='tubes-prefetch'); self.thread.start()

    def stop(self):
        self.stopping = True; self.wake.set()
        if self.thread: self.thread.join(30)

    def state(self):
        """For the System page: `{enabled, seconds, today, per_day, paused_until, last}`."""
        paused = datetime.datetime.fromtimestamp(self.paused_until, datetime.timezone.utc).isoformat(timespec='seconds') if self.paused_until > self.clock() else None
        return dict(enabled=settings.get('prefetch_seconds') > 0 and settings.get('prefetch_per_day') > 0, seconds=settings.get('prefetch_seconds'),
                    today=self.count if self.day == datetime.date.fromtimestamp(self.clock()) else 0, per_day=settings.get('prefetch_per_day'),
                    paused_until=paused, last=self.last)
