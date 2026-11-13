"""prefetch.py: how much of a start is prefetched, which videos and when, and going easy on YouTube."""
import pytest
from tubes import cache, fetcher, library, prefetch, segments, settings
from library import seed

DAY = 1_763_000_000.0                                                                          # a fixed clock, mid-day


@pytest.fixture(autouse=True)
def calm(monkeypatch):
    monkeypatch.setattr(fetcher, '_running', {})
    monkeypatch.setattr(segments, 'for_video', lambda vid: dict(segments=[], categories=segments.categories(), error=None))


def found(*segs): return lambda vid: dict(segments=[dict(category=c, start=s, end=e, action=a) for c, s, e, a in segs], categories=segments.categories(), error=None)


def test_length_adds_the_parts_the_player_skips_at_the_start(monkeypatch):
    assert prefetch.length('aaaaaaaaaaa') == 20.0
    settings.save(dict(skip_hook='off', skip_intro='ask', skip_sponsor='auto'))
    monkeypatch.setattr(segments, 'for_video', found(('intro', 0.5, 12.0, 'skip'), ('sponsor', 12.5, 40.0, 'skip'), ('sponsor', 90.0, 120.0, 'skip')))
    assert prefetch.length('aaaaaaaaaaa') == 60.0                                              # intro then sponsor; the later one does not count
    monkeypatch.setattr(segments, 'for_video', found(('hook', 0.0, 30.0, 'skip'), ('sponsor', 0.0, 10.0, 'mute')))
    assert prefetch.length('aaaaaaaaaaa') == 20.0                                              # hooks are not skipped here; a mute is not a skip
    monkeypatch.setattr(segments, 'for_video', found(('intro', 0.0, 900.0, 'skip')))
    assert prefetch.length('aaaaaaaaaaa') == prefetch.MAX_SECONDS
    def broken(vid): raise RuntimeError('no database')
    monkeypatch.setattr(segments, 'for_video', broken); settings.save(dict(prefetch_seconds=12))
    assert prefetch.length('aaaaaaaaaaa') == 12.0


def runs(monkeypatch, answer=None):
    """Record prefetches instead of fetching: each one's (id, until), answered with `answer(id)` (a ready-made status)."""
    done = []
    def start(vid, title=None, channel=None, background=True, until=None):
        assert background is False
        done.append((vid, until))
        if answer: return answer(vid)
        cache.begin(vid, cache.stamp(), title, channel); return dict(cache.status(vid), state='partial', seconds=20.0)
    monkeypatch.setattr(fetcher, 'start', start); return done


def test_home_first_then_nothing_twice(monkeypatch):
    seed(); done = runs(monkeypatch); p = prefetch.Prefetcher(clock=lambda: DAY)
    for _ in range(4): assert p.step() not in ('none', 'off')
    assert [v for v, _ in done] == ['aaaaaaaaaaa', 'ccccccccccc', 'bbbbbbbbbbb', 'ddddddddddd'] and {u for _, u in done} == {20.0}
    assert p.step() == 'none'
    s = p.state()
    assert s['today'] == 4 and s['enabled'] is True and s['last']['video_id'] == 'ddddddddddd' and s['last']['state'] == 'partial' and s['paused_until'] is None


def test_offered_videos_go_first_latest_first(monkeypatch):
    seed(); done = runs(monkeypatch); p = prefetch.Prefetcher(clock=lambda: DAY)
    p.want(['ccccccccccc']); p.want(['ddddddddddd', 'zzzzzzzzzzz'])                              # one not in the library is passed over
    p.step(); p.step(); p.step()
    assert [v for v, _ in done] == ['ddddddddddd', 'ccccccccccc', 'aaaaaaaaaaa']
    p.want([f'x{i:010d}' for i in range(prefetch.ASKED + 5)])
    assert len(p.asked) == prefetch.ASKED and 'x0000000000' not in p.asked


def test_videos_that_cannot_or_need_not_be_prefetched_are_passed_over(monkeypatch):
    seed(); done = runs(monkeypatch); p = prefetch.Prefetcher(clock=lambda: DAY)
    from tubes import db
    with db.connect() as con:
        con.execute("UPDATE videos SET platform = 'iplayer' WHERE id = 'aaaaaaaaaaa'")
        con.execute("UPDATE videos SET live = 'upcoming' WHERE id = 'bbbbbbbbbbb'")
    cache.begin('ccccccccccc', cache.stamp())                                                   # already has a copy
    p.want(['aaaaaaaaaaa', 'bbbbbbbbbbb'])
    assert p.step() == 'ddddddddddd' and p.step() == 'none'


def test_it_waits_while_a_play_is_fetched_and_stops_at_the_days_limit(monkeypatch):
    seed(); done = runs(monkeypatch); t = [DAY]; p = prefetch.Prefetcher(clock=lambda: t[0])
    fetcher._running['eeeeeeeeeee'] = fetcher.Job('eeeeeeeeeee')
    assert p.step() == 'busy'
    del fetcher._running['eeeeeeeeeee']
    settings.save(dict(prefetch_per_day=2))
    assert p.step() == 'aaaaaaaaaaa' and p.step() == 'ccccccccccc' and p.step() == 'limit'
    t[0] += 86400
    assert p.step() == 'bbbbbbbbbbb'
    settings.save(dict(prefetch_seconds=0))
    assert p.step() == 'off' and p.state()['enabled'] is False and len(done) == 3


def test_a_failure_is_forgotten_and_tried_again_a_day_later_and_a_slow_down_pauses(monkeypatch):
    seed(); t = [DAY]; p = prefetch.Prefetcher(clock=lambda: t[0])
    def failing(vid):
        cache.begin(vid, cache.stamp()); cache.finish(vid, cache.stamp(), 'Sign in to confirm you’re not a bot'); return cache.status(vid)
    done = runs(monkeypatch, failing)
    assert p.step() == 'aaaaaaaaaaa' and cache.entry('aaaaaaaaaaa') is None
    assert p.step() == 'paused' and p.state()['paused_until'] is not None
    t[0] += prefetch.PAUSE_SECONDS + 1
    assert p.step() == 'ccccccccccc'
    def gone(vid):
        cache.begin(vid, cache.stamp()); cache.finish(vid, cache.stamp(), 'Video unavailable. This video has been removed by the uploader'); return cache.status(vid)
    runs(monkeypatch, gone)
    t[0] += prefetch.PAUSE_SECONDS + 1
    assert p.step() == 'bbbbbbbbbbb' and cache.entry('bbbbbbbbbbb')['state'] == 'failed'      # kept: the player says why
    t[0] += prefetch.RETRY_HOURS * 3600 - 2 * prefetch.PAUSE_SECONDS
    def refused(vid): raise fetcher.FetchError('Fetching needs Linux or macOS.')
    monkeypatch.setattr(fetcher, 'start', lambda vid, *a, **kw: refused(vid))
    assert p.step() == 'aaaaaaaaaaa' and p.last['error'] == 'Fetching needs Linux or macOS.' and len(done) == 2


def test_the_thread_runs_steps_until_stopped(monkeypatch):
    p = prefetch.Prefetcher(); calls = []
    def step():
        calls.append(1)
        if len(calls) == 1: raise RuntimeError('the database went away')
        p.stopping = True; return 'none'
    monkeypatch.setattr(p, 'step', step); monkeypatch.setattr(prefetch, 'WAITS', dict(paused=0, none=0))
    p.start(); p.thread.join(10)
    assert len(calls) == 2 and not p.thread.is_alive()
    p.stop()


def test_home_that_cannot_be_read_still_leaves_the_offered_ones(monkeypatch):
    def broken(**kw): raise RuntimeError('no database')
    monkeypatch.setattr(library, 'videos', broken)
    p = prefetch.Prefetcher(); p.want(['aaaaaaaaaaa'])
    assert p.candidates() == ['aaaaaaaaaaa']
