import os
from datetime import datetime, timedelta, timezone
import pytest
from hypothesis import given, strategies as st
from tubes import cache, db, settings
from library import seed

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
iso = lambda d: d.isoformat(timespec='seconds')


def write_playlist(vid, segments, complete):
    os.makedirs(cache.folder(vid), exist_ok=True)
    body = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n' + ''.join(f'#EXTINF:4.000000,\nseg_{i:05d}.m4s\n' for i in range(segments)) + ('#EXT-X-ENDLIST\n' if complete else '')
    with open(os.path.join(cache.folder(vid), 'index.m3u8'), 'w') as f: f.write(body)
    for i in range(segments):
        with open(os.path.join(cache.folder(vid), f'seg_{i:05d}.m4s'), 'wb') as f: f.write(b'x' * 1000)


def test_score_mixes_popularity_and_recency():
    played = lambda *days: [NOW - timedelta(days=d) for d in days]
    assert cache.score([], NOW, 30) == 0
    assert cache.score(played(0), NOW, 30) == 1.0
    assert cache.score(played(30), NOW, 30) == pytest.approx(0.5)
    assert cache.score(played(*[60] * 10), NOW, 30) == pytest.approx(2.5)
    assert cache.score(played(2, 3, 4), NOW, 30) == pytest.approx(2.8, abs=0.05)
    assert cache.score([NOW + timedelta(days=1)], NOW, 30) == 1.0                         # a clock skew never scores above a play now


@given(st.lists(st.integers(0, 400), max_size=20), st.integers(0, 400))
def test_one_more_play_never_lowers_the_score(days, extra):
    plays = [NOW - timedelta(days=d) for d in days]
    assert cache.score(plays + [NOW - timedelta(days=extra)], NOW, 30) > cache.score(plays, NOW, 30)


def item(vid, size, score=0.0, plays=0, state='ready', pinned=False, last_played=None, finished=NOW - timedelta(days=30)):
    return dict(video_id=vid, bytes=size, score=score, plays=plays, state=state, pinned=pinned, last_played=last_played and iso(last_played), finished=finished and iso(finished), started=iso(NOW - timedelta(days=31)))


def test_protected():
    assert cache.protected(item('a', 1, state='fetching'), NOW, 7) == 'fetching'
    assert cache.protected(item('a', 1, pinned=True), NOW, 7) == 'pinned'
    assert cache.protected(item('a', 1, plays=1, last_played=NOW - timedelta(hours=3)), NOW, 7) == 'played in the last day'
    assert cache.protected(item('a', 1, finished=NOW - timedelta(days=2)), NOW, 7) == 'not played yet'
    assert cache.protected(item('a', 1, finished=NOW - timedelta(days=8)), NOW, 7) is None
    assert cache.protected(item('a', 1, plays=1, last_played=NOW - timedelta(days=2), finished=NOW - timedelta(days=2)), NOW, 7) is None
    assert cache.protected(item('a', 1, state='failed', finished=NOW), NOW, 7) is None


def test_plan_evicts_failed_then_lowest_scores_down_to_ninety_percent():
    items = [item('hot', 300, score=3.0, plays=5, last_played=NOW - timedelta(days=3)), item('cold', 300, score=0.2, plays=1, last_played=NOW - timedelta(days=60)),
             item('colder', 200, score=0.1, plays=1, last_played=NOW - timedelta(days=90)), item('broken', 10, state='failed'),
             item('pinned', 100, pinned=True), item('new', 100, finished=NOW - timedelta(days=1))]
    assert cache.plan(items, 1100, NOW, 7) == []                                           # 1010 of 1100 is under 95%
    out = cache.plan(items, 1000, NOW, 7)
    assert [e['video_id'] for e in out] == ['broken', 'colder']                            # 1010 -> 800, under 90% of 1000
    assert [e['video_id'] for e in cache.plan(items, 500, NOW, 7)] == ['broken', 'colder', 'cold', 'hot']      # protected ones stay even when the target is missed


def test_status_files_and_playlist(monkeypatch):
    seed()
    assert cache.status('aaaaaaaaaaa') == dict(state='none', segments=0, seconds=0.0, complete=False, playable=False, error=None, formats=None)
    cache.begin('aaaaaaaaaaa', iso(NOW)); cache.set_formats('aaaaaaaaaaa', '1080p AV1 + AAC')
    assert cache.status('aaaaaaaaaaa')['state'] == 'fetching' and cache.status('aaaaaaaaaaa')['playable'] is False
    write_playlist('aaaaaaaaaaa', 2, complete=False)
    assert cache.status('aaaaaaaaaaa') == dict(state='fetching', segments=2, seconds=8.0, complete=False, playable=True, error=None, formats='1080p AV1 + AAC')
    assert cache.file_path('aaaaaaaaaaa', 'seg_00001.m4s').endswith('seg_00001.m4s')
    for bad in ('fetch.log', '../x', 'seg_1.m4s', '', None, 'init.mp4'):                   # init.mp4: a name it serves, but not written yet
        assert cache.file_path('aaaaaaaaaaa', bad) is None
    write_playlist('aaaaaaaaaaa', 3, complete=True); cache.finish('aaaaaaaaaaa', iso(NOW))
    e = cache.entry('aaaaaaaaaaa')
    assert (e['state'], e['finished'], e['error']) == ('ready', iso(NOW), None) and e['bytes'] > 3000
    assert cache.status('aaaaaaaaaaa')['complete'] is True


def test_failed_fetch_keeps_its_reason_but_not_its_files(monkeypatch):
    seed()
    cache.begin('aaaaaaaaaaa', iso(NOW)); write_playlist('aaaaaaaaaaa', 1, complete=False)
    cache.finish('aaaaaaaaaaa', iso(NOW), error='Video unavailable')
    assert cache.status('aaaaaaaaaaa') == dict(state='failed', segments=0, seconds=0.0, complete=False, playable=False, error='Video unavailable', formats=None)
    assert not os.path.exists(cache.folder('aaaaaaaaaaa'))
    cache.begin('aaaaaaaaaaa', iso(NOW))                                                   # trying again clears the reason
    assert cache.entry('aaaaaaaaaaa')['error'] is None and cache.entry('aaaaaaaaaaa')['state'] == 'fetching'


def test_recover_pin_forget(monkeypatch):
    seed()
    cache.begin('aaaaaaaaaaa', iso(NOW)); write_playlist('aaaaaaaaaaa', 1, complete=False)
    cache.begin('bbbbbbbbbbb', iso(NOW)); write_playlist('bbbbbbbbbbb', 2, complete=True); cache.finish('bbbbbbbbbbb', iso(NOW))
    assert cache.recover(iso(NOW)) == ['aaaaaaaaaaa']
    assert cache.entry('aaaaaaaaaaa')['state'] == 'failed' and 'server stopped' in cache.entry('aaaaaaaaaaa')['error']
    assert cache.pin('bbbbbbbbbbb', True) is True and bool(cache.entry('bbbbbbbbbbb')['pinned']) is True
    assert cache.pin('zzz', True) is False
    size = cache.folder_bytes(cache.folder('bbbbbbbbbbb'))
    assert size > 2000 and cache.forget(['bbbbbbbbbbb', 'aaaaaaaaaaa']) == size          # the failed one's files were already gone
    assert cache.entry('bbbbbbbbbbb') is None and not os.path.exists(cache.folder('bbbbbbbbbbb'))


def test_entries_usage_and_evict(monkeypatch):
    seed()
    old = iso(NOW - timedelta(days=40))
    for vid, segs in (('aaaaaaaaaaa', 5), ('bbbbbbbbbbb', 6)):
        cache.begin(vid, old); write_playlist(vid, segs, complete=True); cache.finish(vid, old)
    with db.connect() as con:
        con.execute('INSERT INTO plays (video_id, at) VALUES (?, ?)', ('bbbbbbbbbbb', iso(NOW - timedelta(days=2))))
        con.execute('INSERT INTO plays (video_id, at) VALUES (?, ?)', ('aaaaaaaaaaa', iso(NOW - timedelta(days=30))))
    items = cache.entries(NOW)
    assert [(e['video_id'], e['plays'], e['score']) for e in items] == [('bbbbbbbbbbb', 1, pytest.approx(0.9548, abs=1e-3)), ('aaaaaaaaaaa', 1, 0.5)]
    u = cache.usage(NOW)
    assert u['count'] == 2 and u['by_state'] == dict(fetching=0, partial=0, ready=2, failed=0) and u['used'] == sum(e['bytes'] for e in items)
    settings.save(dict(cache_limit_gb=u['used'] / 1e9 * 1.2))
    assert cache.evict(NOW) == dict(evicted=[], freed=0, dry_run=False)
    settings.save(dict(cache_limit_gb=u['used'] / 1e9))                                     # over 95%: the lower score goes
    dry = cache.evict(NOW, dry_run=True)
    assert [e['video_id'] for e in dry['evicted']] == ['aaaaaaaaaaa'] and dry['dry_run'] is True and cache.entry('aaaaaaaaaaa')
    real = cache.evict(NOW)
    assert real['freed'] == dry['freed'] and cache.entry('aaaaaaaaaaa') is None
    cache.begin('aaaaaaaaaaa', iso(NOW)); write_playlist('aaaaaaaaaaa', 1, complete=False)
    assert next(e for e in cache.entries(NOW) if e['video_id'] == 'aaaaaaaaaaa')['bytes'] == 1000 + os.path.getsize(os.path.join(cache.folder('aaaaaaaaaaa'), 'index.m3u8'))     # a running fetch is measured on disk


def test_copies_keep_the_library_title_and_plays_are_counted():
    cache.begin('aaaaaaaaaaa', iso(NOW), 'A title', 'A channel')
    cache.begin('aaaaaaaaaaa', iso(NOW))                                                   # a retry without names keeps the ones it had
    assert (cache.entry('aaaaaaaaaaa')['title'], cache.entry('aaaaaaaaaaa')['channel']) == ('A title', 'A channel')
    cache.begin('zzzzzzzzzzz', iso(NOW))
    assert {e['video_id']: e['title'] for e in cache.entries(NOW)} == {'aaaaaaaaaaa': 'A title', 'zzzzzzzzzzz': 'zzzzzzzzzzz'}     # no name: the id
    assert cache.plays('aaaaaaaaaaa') == dict(plays=0, last_played=None)
    cache.record_play('aaaaaaaaaaa', iso(NOW - timedelta(days=1))); cache.record_play('aaaaaaaaaaa', iso(NOW))
    assert cache.plays('aaaaaaaaaaa') == dict(plays=2, last_played=iso(NOW))
    assert cache.stamp().endswith('+00:00')


def test_folder_names_are_safe(monkeypatch, tmp_path):
    assert cache.folder_name('abc_DEF-12') == 'abc_DEF-12'
    odd = cache.folder_name('bbc:p0abc/1')
    assert odd.startswith('h') and len(odd) == 17 and odd == cache.folder_name('bbc:p0abc/1')
    d = tmp_path / 'd'; d.mkdir(); (d / 'a').write_bytes(b'12')
    monkeypatch.setattr(os.path, 'getsize', lambda p: (_ for _ in ()).throw(OSError('gone')))
    assert cache.folder_bytes(str(d)) == 0                                                  # a file that vanishes mid-walk is skipped


def test_a_copy_over_2_gb_is_recorded(monkeypatch):
    # Postgres' INTEGER stops at 2^31 - 1 bytes; a long 1080p copy is bigger (SQLite never noticed: run with --pg).
    cache.begin('aaaaaaaaaaa', cache.stamp())
    monkeypatch.setattr(cache, 'folder_bytes', lambda path: 5_000_000_000)
    cache.finish('aaaaaaaaaaa', cache.stamp())
    assert cache.entry('aaaaaaaaaaa')['bytes'] == 5_000_000_000


def test_a_fetching_copy_is_never_served_as_ended():
    assert cache.served_playlist('aaaaaaaaaaa') is None
    cache.begin('aaaaaaaaaaa', cache.stamp()); write_playlist('aaaaaaaaaaa', 2, True)     # a first attempt that ended short; the fetcher may run it again
    held = cache.served_playlist('aaaaaaaaaaa')
    assert '#EXT-X-ENDLIST' not in held and 'seg_00000.m4s' in held and 'seg_00001.m4s' not in held and held.count('#EXTINF') == 1   # its last segment may be short: held back
    write_playlist('aaaaaaaaaaa', 3, False); assert 'seg_00002.m4s' in cache.served_playlist('aaaaaaaaaaa')       # still growing: all of it
    write_playlist('aaaaaaaaaaa', 0, True); assert '#EXT-X-ENDLIST' not in cache.served_playlist('aaaaaaaaaaa')
    write_playlist('aaaaaaaaaaa', 1, True)        # an attempt that ended after one segment: nothing to play yet, so the player is not started on an empty playlist
    assert '#EXTINF' not in cache.served_playlist('aaaaaaaaaaa') and (cache.status('aaaaaaaaaaa')['segments'], cache.status('aaaaaaaaaaa')['playable']) == (0, False)
    write_playlist('aaaaaaaaaaa', 2, True)
    assert cache.status('aaaaaaaaaaa')['complete'] is False and cache.read_playlist('aaaaaaaaaaa')['complete'] is True
    cache.finish('aaaaaaaaaaa', cache.stamp())
    assert cache.served_playlist('aaaaaaaaaaa').endswith('#EXT-X-ENDLIST\n') and cache.status('aaaaaaaaaaa')['complete'] is True


def cut(vid, lengths, complete=False):
    """A fetch stopped part way: a playlist listing these segment lengths, their files, an init segment, a half-written segment and a log."""
    d = cache.folder(vid); os.makedirs(d, exist_ok=True)
    body = '#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-MAP:URI="init.mp4"\n' + ''.join(f'#EXTINF:{n:.6f},\nseg_{i:05d}.m4s\n' for i, n in enumerate(lengths)) + ('#EXT-X-ENDLIST\n' if complete else '')
    with open(os.path.join(d, 'index.m3u8'), 'w') as f: f.write(body)
    for name in [f'seg_{i:05d}.m4s' for i in range(len(lengths))] + ['init.mp4', f'seg_{len(lengths):05d}.m4s.tmp', 'fetch.log', 'probe.json']:
        with open(os.path.join(d, name), 'wb') as f: f.write(b'i' if name == 'init.mp4' else b'x' * 100)


def test_a_prefix_keeps_what_reaches_its_length_but_never_the_last_listed_segment():
    seed(); cache.begin('aaaaaaaaaaa', cache.stamp(), 'Building a shelf')
    cut('aaaaaaaaaaa', [4.0, 6.0, 4.0, 8.0, 4.0, 3.0], complete=True)
    assert cache.keep_prefix('aaaaaaaaaaa', 13, cache.stamp(), dict(video='399', audio='140')) == 14.0
    d = cache.folder('aaaaaaaaaaa')
    assert sorted(os.listdir(d)) == ['index.m3u8', 'init.mp4', 'prefix-init.mp4', 'prefix.json', 'prefix.m3u8', 'seg_00000.m4s', 'seg_00001.m4s', 'seg_00002.m4s']
    text = open(os.path.join(d, 'index.m3u8')).read()
    assert text == open(os.path.join(d, 'prefix.m3u8')).read() and '#EXT-X-ENDLIST' not in text and '#EXT-X-VERSION:7' in text
    assert cache.lengths(text) == [(4.0, 'seg_00000.m4s'), (6.0, 'seg_00001.m4s'), (4.0, 'seg_00002.m4s')]
    assert cache.prefix('aaaaaaaaaaa') == dict(video='399', audio='140', seconds=14.0)
    st = cache.status('aaaaaaaaaaa')
    assert (st['state'], st['segments'], st['seconds'], st['complete'], st['playable']) == ('partial', 3, 14.0, False, True)
    assert cache.entry('aaaaaaaaaaa')['bytes'] == cache.folder_bytes(d) > 0


def test_a_prefix_with_nothing_worth_keeping_is_forgotten():
    seed(); cache.begin('aaaaaaaaaaa', cache.stamp())
    cut('aaaaaaaaaaa', [4.0])                                                                  # only the last one, which may be cut short
    assert cache.keep_prefix('aaaaaaaaaaa', 20, cache.stamp(), dict(video='399', audio='140')) == 0
    assert cache.entry('aaaaaaaaaaa') is None and not os.path.exists(cache.folder('aaaaaaaaaaa'))
    assert cache.prefix('bbbbbbbbbbb') is None
    cache.begin('bbbbbbbbbbb', cache.stamp())                                                  # stopped before ffmpeg wrote a playlist
    assert cache.keep_prefix('bbbbbbbbbbb', 20, cache.stamp(), dict(video='399', audio='140')) == 0 and cache.entry('bbbbbbbbbbb') is None


def keep(vid='aaaaaaaaaaa', lengths=(4.0, 4.0, 4.0, 4.0)):
    seed(); cache.begin(vid, cache.stamp()); cut(vid, list(lengths))
    cache.keep_prefix(vid, 10, cache.stamp(), dict(video='399', audio='140'))


def test_a_fetch_from_a_prefix_serves_the_prefix_until_it_has_more():
    keep(); cache.resume('aaaaaaaaaaa', cache.stamp())
    assert cache.entry('aaaaaaaaaaa')['state'] == 'fetching'
    d = cache.folder('aaaaaaaaaaa')
    with open(os.path.join(d, 'index.m3u8'), 'w') as f: f.write('#EXTM3U\n')        # ffmpeg starts the playlist again
    assert cache.served_playlist('aaaaaaaaaaa') == open(os.path.join(d, 'prefix.m3u8')).read()
    assert cache.status('aaaaaaaaaaa')['segments'] == 3
    with open(os.path.join(d, 'init.mp4'), 'wb') as f: f.write(b'')                     # being written again
    assert cache.served_file('aaaaaaaaaaa', 'init.mp4') == os.path.join(d, 'prefix-init.mp4')
    assert cache.served_file('aaaaaaaaaaa', 'seg_00000.m4s') == os.path.join(d, 'seg_00000.m4s') and cache.served_file('aaaaaaaaaaa', 'prefix.json') is None
    write_playlist('aaaaaaaaaaa', 5, False)
    assert cache.summary(cache.served_playlist('aaaaaaaaaaa'))['segments'] == 5
    cache.finish('aaaaaaaaaaa', cache.stamp())
    assert cache.prefix('aaaaaaaaaaa') is None and not os.path.exists(os.path.join(d, 'prefix-init.mp4'))
    assert cache.served_file('aaaaaaaaaaa', 'init.mp4') == os.path.join(d, 'init.mp4')


def test_a_restart_during_a_fetch_from_a_prefix_goes_back_to_the_prefix():
    keep(); cache.resume('aaaaaaaaaaa', cache.stamp())
    write_playlist('aaaaaaaaaaa', 6, False)
    open(os.path.join(cache.folder('aaaaaaaaaaa'), 'seg_00006.m4s.tmp'), 'wb').close()
    cache.begin('bbbbbbbbbbb', cache.stamp())                                                  # a fetch with no prefix fails as before
    assert sorted(cache.recover(cache.stamp())) == ['aaaaaaaaaaa', 'bbbbbbbbbbb']
    assert cache.entry('bbbbbbbbbbb')['state'] == 'failed'
    st = cache.status('aaaaaaaaaaa')
    assert (st['state'], st['segments']) == ('partial', 3)
    assert sorted(f for f in os.listdir(cache.folder('aaaaaaaaaaa')) if f.startswith('seg_')) == ['seg_00000.m4s', 'seg_00001.m4s', 'seg_00002.m4s']
    assert cache.back_to_prefix('ccccccccccc', cache.stamp()) is False


def test_an_unplayed_prefix_is_kept_like_an_unplayed_copy():
    e = dict(state='partial', pinned=False, last_played=None, plays=0, finished=(NOW - timedelta(days=1)).isoformat(), started=None)
    assert cache.protected(e, NOW, 7) == 'not played yet'
    assert cache.protected(dict(e, finished=(NOW - timedelta(days=8)).isoformat()), NOW, 7) is None
