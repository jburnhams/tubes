import pytest
from hypothesis import given, strategies as st

from library import CHANNELS, seed
from tubes import cache, db, viewing

NOW = '2026-11-12T12:00:00+00:00'
A, B, C, D = 'aaaaaaaaaaa', 'bbbbbbbbbbb', 'ccccccccccc', 'ddddddddddd'      # the sample videos are 600 s long


def day(n): return f'2026-11-{n:02d}T10:00:00+00:00'


def watch(vid, at, watched, position=None, length=600.0, **where):
    p = viewing.start(vid, at, **where)
    viewing.report(p['play_id'], position=watched if position is None else position, watched=watched, length=length, now=at)
    return p


@pytest.mark.parametrize('watched, length, expected', [
    (0, 600, 'none'), (None, 600, 'none'), (59, 600, 'short'), (60, 600, 'partial'), (539, 600, 'partial'), (540, 600, 'full'), (600, 600, 'full'),
    (30, None, 'short'), (60, None, 'partial'), (5, 0, 'short'), (5, 10, 'partial'), (9, 10, 'full')])
def test_outcome_is_how_much_of_the_video_was_seen(watched, length, expected):
    assert viewing.outcome(watched, length) == expected


@given(st.floats(0, 1e5), st.floats(1, 1e5))
def test_outcome_full_exactly_from_ninety_percent(watched, length):
    assert (viewing.outcome(watched, length) == 'full') == (watched > 0 and watched / length >= viewing.FULL)


def test_a_play_keeps_where_it_was_started_from():
    seed()
    p = viewing.start(A, day(10), source='search', detail='shelf', rank=2)
    assert p == dict(play_id=p['play_id'], resume=None)
    viewing.start(B, day(10)); viewing.start(C, day(10), source='newpage', detail='', rank=-1); viewing.start(D, day(10), source='up_next', detail='x' * 500)
    with db.connect() as con:
        got = con.execute('SELECT video_id, source, detail, rank, outcome FROM plays ORDER BY id').fetchall()
    assert [tuple(r) for r in got] == [(A, 'search', 'shelf', 2, 'none'), (B, 'link', None, None, 'none'), (C, 'other', None, None, 'none'), (D, 'up_next', 'x' * viewing.DETAIL_MAX, None, 'none')]
    assert cache.plays(A) == dict(plays=1, last_played=day(10))                  # still a play for the cache's eviction score


def test_reports_only_move_watched_up_and_keep_what_they_leave_out():
    seed()
    p = viewing.start(A, day(10))['play_id']
    assert viewing.report(p, position=30, watched=30, length=600, now=day(10)) == dict(play_id=p, video_id=A, watched=30, position=30, length=600, outcome='short')
    assert viewing.report(p, position=400, watched=300, now=day(10))['outcome'] == 'partial'          # the running time from before
    late = viewing.report(p, position=20, watched=20, length=None, now=day(10))                     # a late report from a page that knew less
    assert (late['watched'], late['position'], late['length'], late['outcome']) == (300, 20, 600, 'partial')
    assert viewing.report(p, watched=5000, now=day(10))['watched'] == 600                           # never more than the whole
    assert viewing.report(p, position=None, now=day(10))['position'] == 20
    with pytest.raises(viewing.NotFound, match='There is no play 999.'): viewing.report(999, watched=1)
    q = viewing.start(B, day(10))['play_id']                                                        # the player has not said how long it is yet
    assert viewing.report(q, position=550, watched=550, now=day(10))['outcome'] == 'full'           # the library's running time (600 s) does
    r = viewing.start('zzzzzzzzzzz', day(10))['play_id']                                            # neither knows: a minute seen is partial
    assert (viewing.report(r, watched=59, now=day(10))['outcome'], viewing.report(r, watched=60, now=day(10))['outcome']) == ('short', 'partial')


def test_continue_watching_is_the_recent_part_watched_most_recent_first():
    seed()
    watch(A, day(5), 300)                                   # partial
    watch(B, day(6), 300); watch(B, day(7), 590)            # then finished: off the list
    watch(C, day(8), 120, position=200)                     # partial, picked up later for a few seconds
    watch(C, day(9), 10, position=215)
    watch(D, day(1), 20)                                    # a short look only
    watch(D, '2026-10-01T10:00:00+00:00', 300)              # partial, but too long ago
    watch('zzzzzzzzzzz', day(9), 300); watch('zzzzzzzzzzz', day(10), 260, position=590)   # finished in two halves: two partial plays
    assert 'zzzzzzzzzzz' not in [p['video_id'] for p in viewing._unfinished(NOW)] and viewing.resume('zzzzzzzzzzz', NOW) is None
    got = viewing.unfinished(now=NOW)
    assert [(v['id'], v['resume'], v['progress']) for v in got] == [(C, 215, round(215 / 600, 4)), (A, 300, 0.5)]
    assert got[0]['title'] == 'Stars in winter' and got[0]['channel'] == 'night sky'                  # rows as the lists give them
    assert [v['id'] for v in viewing.unfinished(limit=1, now=NOW)] == [C]
    assert viewing.unfinished(now='2026-12-30T00:00:00+00:00') == []


def test_continue_watching_leaves_out_what_the_watching_side_hides():
    seed()
    watch(A, day(5), 300); watch(B, day(5), 300)
    with db.connect() as con: con.execute('UPDATE videos SET gone = ? WHERE id = ?', (day(6), A)); con.execute('DELETE FROM videos WHERE id = ?', (B,))
    assert viewing.unfinished(now=NOW) == []


def test_continue_watching_with_no_running_time_known():
    seed()
    with db.connect() as con: con.execute('UPDATE videos SET duration = NULL WHERE id = ?', (A,))
    watch(A, day(5), 90, length=None)
    assert [(v['id'], v['resume'], v['progress']) for v in viewing.unfinished(now=NOW)] == [(A, 90, None)]


def test_a_new_play_picks_up_where_the_last_stopped():
    seed()
    watch(A, day(5), 300, position=320)
    assert viewing.start(A, day(6)) == dict(play_id=2, resume=320)
    assert viewing.resume(A, day(6)) == 320                                        # a play just started, nothing seen yet, changes nothing
    watch(B, day(5), 100, position=5)                                              # stopped near the start: from the beginning
    watch(C, day(5), 100, position=580)                                            # as good as over: from the beginning
    assert (viewing.resume(B, NOW), viewing.resume(C, NOW), viewing.resume(D, NOW)) == (None, None, None)
    watch(A, day(7), 560)
    assert viewing.start(A, day(8))['resume'] is None                              # finished since


def test_plays_from_before_outcomes_were_kept_are_left_out_of_continue_watching():
    seed()
    cache.record_play(A, day(5))
    assert viewing.unfinished(now=NOW) == [] and viewing.resume(A, NOW) is None
    assert viewing.summary(now=NOW)['outcomes'] == dict(none=1, short=0, partial=0, full=0)


def test_channel_views_and_the_summary():
    seed()
    assert viewing.channel_view(CHANNELS[0]['id'], day(10), source='rail') == dict(id=1)
    viewing.channel_view(CHANNELS[0]['id'], day(10)); viewing.channel_view(CHANNELS[1]['id'], day(10), source='rail', detail='x')
    watch(A, day(10), 590, source='home', rank=0); watch(B, day(10), 30, source='home', rank=1); watch(C, day(10), 300, source='search', detail='stars')
    viewing.start(D, '2026-01-01T00:00:00+00:00')                                  # outside the 30 days
    s = viewing.summary(now=NOW)
    assert s == dict(since='2026-10-13T12:00:00+00:00', days=30, plays=3, seconds=920.0, videos=3, outcomes=dict(none=0, short=1, partial=1, full=1),
                     sources=dict(home=dict(plays=2, full=1), search=dict(plays=1, full=0)), channel_views=dict(link=1, rail=2))


def test_recent_plays_newest_first_with_titles_even_once_the_video_left_the_library():
    seed()
    watch(A, day(9), 590, source='home'); watch(B, day(10), 30)
    cache.begin('zzzzzzzzzzz', day(1), 'Old copy', 'Gone channel'); viewing.start('zzzzzzzzzzz', day(11))
    got = viewing.recent()
    assert got['has_more'] is False
    items = got['items']
    assert [(p['video_id'], p['title'], p['channel'], p['outcome'], p['source']) for p in items] == [
        ('zzzzzzzzzzz', 'Old copy', 'Gone channel', 'none', 'link'), (B, 'Sanding the shelf', 'Workshop', 'short', 'link'), (A, 'Building a 50% shelf', 'Workshop', 'full', 'home')]
    assert (items[2]['watched'], items[2]['length'], items[2]['position'], items[2]['channel_id'], items[2]['thumbnail']) == (590, 600, 590, CHANNELS[0]['id'], f'https://img.test/{A}.jpg')
    assert items[0]['length'] is None and items[1]['updated'] == day(10)


def test_recent_plays_in_pages_by_cursor_and_filtered():
    seed()
    for n in range(5): viewing.start(A, day(10))                                   # the same moment: the id decides
    first = viewing.recent(limit=2)
    assert [p['id'] for p in first['items']] == [5, 4] and first['has_more'] is True
    rest = viewing.recent(limit=2, after=viewing.cursor(first['items'][-1]))
    assert [p['id'] for p in rest['items']] == [3, 2]
    assert [p['id'] for p in viewing.recent(after=viewing.cursor(rest['items'][-1]))['items']] == [1]
    assert len(viewing.recent(after='nonsense')['items']) == 5                     # a cursor that does not parse: the first page
    watch(B, day(11), 590, source='search', detail='shelf'); cache.record_play(C, day(12))
    assert [p['video_id'] for p in viewing.recent(outcome='full')['items']] == [B]
    assert [p['video_id'] for p in viewing.recent(outcome='none')['items']][:2] == [C, A]           # one from before outcomes were kept too
    assert [p['video_id'] for p in viewing.recent(source='search')['items']] == [B]
    assert len(viewing.recent(source='link')['items']) == 6                                          # with none given too


def test_what_a_source_points_at_is_named():
    seed()
    viewing.start(A, day(10), source='channel', detail=CHANNELS[1]['id']); viewing.start(B, day(11), source='up_next', detail=C)
    viewing.start(C, day(12), source='search', detail='moon'); viewing.start(D, day(13), source='up_next', detail='zzzzzzzzzzz')
    assert [p['detail_title'] for p in viewing.recent()['items']] == [None, None, 'Stars in winter', 'night sky']


def test_channel_visits_newest_first_in_pages():
    seed()
    viewing.channel_view(CHANNELS[0]['id'], day(10), source='rail'); viewing.channel_view(CHANNELS[1]['id'], day(11), source='watch', detail=C); viewing.channel_view('UCgone', day(12))
    got = viewing.channel_visits(limit=2)
    assert [(v['channel_id'], v['title'], v['source'], v['detail_title']) for v in got['items']] == [('UCgone', None, 'link', None), (CHANNELS[1]['id'], 'night sky', 'watch', 'Stars in winter')] and got['has_more'] is True
    rest = viewing.channel_visits(after=viewing.cursor(got['items'][-1]))
    assert [(v['title'], v['source'], v['thumbnail']) for v in rest['items']] == [('Workshop', 'rail', 'https://img.test/ws.jpg')] and rest['has_more'] is False
