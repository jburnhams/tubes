"""catalogue.py against the stand-in YouTube Data API (tests/utils/fake_youtube.py, a real HTTP server on localhost)."""
import pytest
from fake_youtube import vid
from tubes import catalogue, db, library, youtube

A, B = 'UCaaaaaaaaaaaaaaaaaaaaaa', 'UCbbbbbbbbbbbbbbbbbbbbbb'


def videos_of(cid): return library.videos(channel_id=cid, limit=1000)['videos']


def test_add_a_channel_by_handle_follows_it(fake_youtube):
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=3)
    r = catalogue.add('https://www.youtube.com/@Workshop', now='2026-11-09T10:00:00+00:00')
    c = r['channel']
    assert r['kind'] == 'channel' and (c['id'], c['title'], c['handle'], c['follow'], c['complete'], c['total_videos'], c['videos']) == (A, 'Workshop', '@workshop', True, False, 3, 0)
    assert c['thumbnail'] == f'https://img.test/{A}/l.jpg' and c['added'] == '2026-11-09T10:00:00+00:00' and c['country'] == 'GB'
    fake_youtube.channels[A]['snippet']['title'] = 'Workshop TV'
    assert catalogue.add(A, now='later')['channel']['added'] == '2026-11-09T10:00:00+00:00'                # adding again refreshes, keeps when it came
    assert library.channel(A)['title'] == 'Workshop TV'
    with pytest.raises(catalogue.NotFound, match='YouTube has no channel @nobody'): catalogue.add('@nobody')
    with pytest.raises(ValueError, match='Enter a channel'): catalogue.add('  ')


def test_add_one_video_brings_its_channel_in_unfollowed(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=5)
    r = catalogue.add(f'https://youtu.be/{vid(A, 2)}')
    assert r['kind'] == 'video' and (r['video']['title'], r['video']['channel'], r['video']['duration']) == ('Upload 2 of Workshop', 'Workshop', 245)
    assert library.channel(A)['follow'] is False and catalogue.followed() == []
    catalogue.add(A)                                                                                     # adding the channel itself follows it
    assert catalogue.followed() == [(A, 'Workshop')]
    with pytest.raises(catalogue.NotFound, match='no video xxxxxxxxxxx'): catalogue.add('xxxxxxxxxxx')
    fake_youtube.video('orphan00000', 'UCgonegonegonegonegonego', 'Orphan', '2026-01-01T00:00:00Z')        # its channel is gone: the video still comes
    assert catalogue.add('orphan00000')['video']['channel'] is None


def test_first_sync_reads_every_page_then_later_ones_only_the_newest(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=120); catalogue.add(A)
    r = catalogue.sync_channel(A, now='t1')
    assert r == dict(channel=A, title='Workshop', added=120, pages=3, complete=True)
    assert len(videos_of(A)) == 120 and videos_of(A)[0]['id'] == vid(A, 119)
    c = library.channel(A)
    assert (c['complete'], c['resumable'], c['synced']) == (True, False, 't1')
    v = library.video(vid(A, 0)); assert (v['views'], v['thumbnail']) == (12, f'https://img.test/{vid(A, 0)}/x.jpg')

    fake_youtube.calls.clear(); fake_youtube.uploads(A, 3)
    assert catalogue.sync_channel(A)['added'] == 3
    assert [e for e, _ in fake_youtube.calls] == ['channels', 'playlistItems', 'videos', 'playlistItems']   # page 2 brought nothing new: stop
    fake_youtube.calls.clear()
    assert catalogue.sync_channel(A)['added'] == 0 and fake_youtube.count('videos') == 0 and fake_youtube.count('playlistItems') == 1


def test_a_backfill_that_stops_resumes_from_its_page(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=160); catalogue.add(A)
    fake_youtube.quota_left = 5                                       # channel, page 1, its videos, page 2, its videos; page 3 is refused
    with pytest.raises(youtube.YoutubeError, match='quota'): catalogue.sync_channel(A)
    c = library.channel(A)
    assert (c['videos'], c['complete'], c['resumable']) == (100, False, True)
    fake_youtube.quota_left = None; fake_youtube.calls.clear(); fake_youtube.uploads(A, 2)
    r = catalogue.sync_channel(A)
    assert r['added'] == 62 and r['complete'] is True and len(videos_of(A)) == 162
    pages = [p.get('pageToken') for e, p in fake_youtube.calls if e == 'playlistItems']
    assert pages == [None, 'P50', 'P100', 'P150']                    # the newest pages until one brings nothing new, then on from where it stopped


def test_sync_of_a_channel_youtube_lost_or_without_uploads(fake_youtube):
    with pytest.raises(catalogue.NotFound, match='no channel UCnope'): catalogue.sync_channel('UCnope')
    fake_youtube.channel(A, 'Workshop'); catalogue.add(A)
    fake_youtube.channels[A]['contentDetails'] = {}
    with pytest.raises(catalogue.NotFound, match='no uploads'): catalogue.sync_channel(A)
    del fake_youtube.channels[A]
    with pytest.raises(catalogue.NotFound, match='YouTube has no channel'): catalogue.sync_channel(A)


def test_sync_every_followed_channel(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=3).channel(B, 'Night sky', videos=2)
    catalogue.add(A); catalogue.add(B); catalogue.add(vid(B, 0))
    seen = []
    r = catalogue.sync(now='2026-11-09T12:00:00+00:00', on_channel=lambda cid, title: seen.append(title))
    assert seen == ['Night sky', 'Workshop'] and r['added'] == 4 and r['errors'] == [] and library.status()['synced'] == '2026-11-09T12:00:00+00:00'
    del fake_youtube.channels[B]; fake_youtube.uploads(A, 1)
    r = catalogue.sync(now='later')
    assert r['errors'] == [dict(channel=B, title='Night sky', error=f'YouTube has no channel {B}.', added=0)] and r['added'] == 1
    assert library.status()['synced'] == '2026-11-09T12:00:00+00:00'                                  # not every channel synced: the time stays
    fake_youtube.quota_left = 0
    r = catalogue.sync([A, B, 'UCunknown'])
    assert len(r['errors']) == 1 and 'quota' in r['errors'][0]['error']                               # out of quota: the rest are not tried


def test_a_channel_that_fails_part_way_counts_what_it_added(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=160); catalogue.add(A)
    fake_youtube.quota_left = 5                                                                       # two pages saved, the third refused
    r = catalogue.sync()
    assert r['added'] == 100 and r['errors'][0]['added'] == 100 and 'quota' in r['errors'][0]['error'] and library.status()['videos'] == 100


def test_a_channel_removed_while_it_syncs_stays_removed(fake_youtube, monkeypatch):
    fake_youtube.channel(A, 'Workshop', videos=120); catalogue.add(A)
    page = youtube.uploads_page

    def remove_after_first(playlist, token):                                                          # the person removes it while page 2 is read
        if token: catalogue.remove(A)
        return page(playlist, token)
    monkeypatch.setattr(youtube, 'uploads_page', remove_after_first)
    r = catalogue.sync()
    assert r['errors'][0]['error'] == f'The channel {A} was removed while it synced.' and r['errors'][0]['added'] == 50
    assert library.channel(A) is None and library.status()['videos'] == 0                            # no videos left behind without their channel
    monkeypatch.setattr(youtube, 'uploads_page', page)
    real = youtube.channel_row

    def removed_meanwhile(item, now): catalogue.remove(B); return real(item, now)                    # removed between the lookup and the refresh
    fake_youtube.channel(B, 'Night sky', videos=1); catalogue.add(B)
    monkeypatch.setattr(youtube, 'channel_row', removed_meanwhile)
    with pytest.raises(catalogue.NotFound, match='removed while it synced'): catalogue.sync_channel(B)
    assert library.channel(B) is None


def test_recheck_hides_what_youtube_lost_and_brings_back_what_returns(fake_youtube, monkeypatch):
    monkeypatch.setattr(catalogue, 'RECHECK', 100)
    fake_youtube.channel(A, 'Workshop', videos=120); catalogue.add(A); catalogue.sync_channel(A)
    lost = fake_youtube.videos.pop(vid(A, 5)); fake_youtube.videos[vid(A, 6)]['statistics']['viewCount'] = '99'
    fake_youtube.calls.clear()
    assert catalogue.recheck(now='t1') == dict(checked=100, gone=1, back=0)                        # the default slice (RECHECK, made 100 here), oldest checked first
    assert fake_youtube.count('videos') == 2 and library.video(vid(A, 5))['gone'] == 't1' and library.video(vid(A, 6))['views'] == 99
    assert catalogue.recheck(now='t2') == dict(checked=100, gone=0, back=0)                        # the 20 not yet checked come first, then the oldest checked
    with db.connect() as con: assert con.execute('SELECT COUNT(*) FROM videos WHERE checked IS NULL').fetchone()[0] == 0
    fake_youtube.videos[lost['id']] = lost
    assert catalogue.recheck(0, now='t3') == dict(checked=120, gone=0, back=1) and library.video(vid(A, 5))['gone'] is None
    with db.connect() as con: con.execute('DELETE FROM videos')
    assert catalogue.recheck() == dict(checked=0, gone=0, back=0)


def test_live_streams_are_marked_as_they_are_added_and_by_the_recheck(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=3)
    fake_youtube.videos[vid(A, 0)]['snippet']['liveBroadcastContent'] = 'upcoming'
    catalogue.add(A); catalogue.sync_channel(A)
    assert library.video(vid(A, 0))['live'] == 'upcoming' and library.status()['live'] == 1 and library.status()['videos'] == 2
    fake_youtube.videos[vid(A, 0)]['snippet']['liveBroadcastContent'] = 'none'; fake_youtube.videos[vid(A, 0)]['liveStreamingDetails'] = dict(actualEndTime='t')
    fake_youtube.videos[vid(A, 1)]['liveStreamingDetails'] = dict(actualEndTime='t')                # a past stream added before the mark existed
    assert catalogue.recheck(0, now='2026-11-01T00:00:00')['checked'] == 3
    assert [library.video(vid(A, n))['live'] for n in range(3)] == ['was', 'was', None] and library.status()['videos'] == 3 and library.status()['live'] == 0   # over: shown


def test_running_streams_are_rechecked_first_and_past_ones_when_shown_daily(fake_youtube, monkeypatch):
    monkeypatch.setattr(catalogue, 'RECHECK', 1)
    fake_youtube.channel(A, 'Workshop', videos=6)
    fake_youtube.videos[vid(A, 5)]['snippet']['liveBroadcastContent'] = 'live'                       # not the first in the slice's order
    for n in (1, 2): fake_youtube.videos[vid(A, n)]['liveStreamingDetails'] = dict(actualEndTime='t')
    catalogue.add(A); catalogue.sync_channel(A)
    assert catalogue.recheck(0, now='2026-11-01T00:00:00')['checked'] == 6
    assert catalogue.recheck(now='2026-11-01T04:00:00')['checked'] == 2                                # the running stream, then the slice of 1
    rows = library.videos()['videos']; fake_youtube.calls.clear()
    del fake_youtube.videos[vid(A, 2)]                                                                  # a past stream's recording taken down
    assert catalogue.recheck_past(rows, now='2026-11-01T12:00:00') == set() and fake_youtube.count('videos') == 0   # asked about within the day
    assert catalogue.recheck_past(rows, now='2026-11-02T12:00:00') == {vid(A, 2)} and fake_youtube.count('videos') == 1   # a day on: both past ones, one call
    assert library.video(vid(A, 2))['gone'] == '2026-11-02T12:00:00' and library.video(vid(A, 1))['gone'] is None
    assert catalogue.recheck_past(rows, now='2026-11-02T13:00:00') == {vid(A, 2)} and fake_youtube.count('videos') == 1   # an old read: still left out, nothing asked
    fake_youtube.quota_left = 0
    assert catalogue.recheck_past(library.videos()['videos'], now='2026-11-05T00:00:00') == set()    # YouTube refuses: shown as they are
    monkeypatch.delenv('YOUTUBE_API_KEY')
    assert catalogue.recheck_past(rows) == set()


def test_a_sync_of_everything_ends_with_a_recheck(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=3); catalogue.add(A); catalogue.sync()
    del fake_youtube.videos[vid(A, 0)]
    r = catalogue.sync()
    assert r['recheck'] == dict(checked=3, gone=1, back=0) and r['errors'] == []
    assert catalogue.sync([A])['recheck'] is None                                                  # only a sync of every followed channel rechecks
    fake_youtube.quota_left = 2                                                                    # the channel and its page; the recheck is refused
    r = catalogue.sync()
    assert r['errors'] == [dict(channel=None, title='The recheck for videos gone from YouTube', error=r['errors'][0]['error'], added=0)] and 'quota' in r['errors'][0]['error']
    fake_youtube.quota_left = 0
    assert catalogue.sync()['recheck'] is None                                                     # out of quota on the channels: no recheck either
    fake_youtube.quota_left = None
    job = catalogue.Job(); fake_youtube.videos.pop(vid(A, 1)); job.start(); job.wait(30)
    assert job.state()['gone'] == 1


def test_remove_and_restart(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=3); catalogue.add(A); catalogue.sync_channel(A)
    assert catalogue.restart(A) == dict(channel=A, videos=3)
    c = library.channel(A); assert (c['videos'], c['complete'], c['synced']) == (0, False, None)
    assert catalogue.sync_channel(A)['added'] == 3
    assert catalogue.remove(A) == dict(channel=A, videos=3) and library.channel(A) is None and library.status()['videos'] == 0
    for fn in (catalogue.remove, catalogue.restart):
        with pytest.raises(catalogue.NotFound, match='no channel'): fn(A)


def test_job_runs_in_the_background_and_reports(fake_youtube, monkeypatch):
    fake_youtube.channel(A, 'Workshop', videos=60).channel(B, 'Night sky', videos=1)
    catalogue.add(A); catalogue.add(B)
    job = catalogue.Job()
    assert job.state()['running'] is False
    started = job.start()
    assert started['running'] is True and started['total'] == 2
    with pytest.raises(catalogue.Job.Busy): job.start()
    job.wait(30)
    s = job.state()
    assert (s['running'], s['done'], s['total'], s['added'], s['errors'], s['current']) == (False, 2, 2, 61, [], None) and s['finished']
    job.start([A]); job.wait(30)
    assert job.state()['total'] == 1 and job.state()['added'] == 0
    assert job.follow_up([B])['total'] == 1; job.wait(30)                                   # nothing running: it starts one
    assert job.state()['done'] == 1

    def broken(*a, **kw): raise RuntimeError('database gone')
    monkeypatch.setattr(catalogue, 'sync', broken)
    job.start([A]); job.wait(30)
    assert job.state()['errors'] == [dict(channel=None, title=None, error='The sync stopped: database gone')] and job.state()['running'] is False


def test_booleans_survive_both_engines(fake_youtube):
    fake_youtube.channel(A, 'Workshop'); catalogue.add(A)
    with db.connect() as con: con.execute('UPDATE channels SET complete = ? WHERE id = ?', (True, A))
    assert library.channel(A)['complete'] is True


def test_a_report_from_the_watching_side_is_rechecked_not_trusted(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=3); catalogue.add(A); catalogue.sync_channel(A)
    v0, v1, v2 = (vid(A, n) for n in range(3))
    del fake_youtube.videos[v0]; fake_youtube.calls.clear()
    r = catalogue.report([v0, v1, v1, 'notinlibrary'], now='2026-11-09T12:00:00+00:00')
    assert r == dict(checked=2, gone=1, back=0, hidden=[v0]) and fake_youtube.count('videos') == 1     # one call; only the library's videos, each once
    assert [v['id'] for v in videos_of(A)] == [v2, v1]
    fake_youtube.calls.clear()
    assert catalogue.report([v0, v1], now='2026-11-09T12:09:00+00:00') == dict(checked=0, gone=0, back=0, hidden=[v0]) and fake_youtube.calls == []   # just asked: not again, still hidden
    catalogue.mark_gone(v2)                                                                                 # a failed fetch hid it; YouTube still has it
    assert catalogue.report([v2], now='2026-11-09T12:09:00+00:00') == dict(checked=1, gone=0, back=1, hidden=[])
    assert catalogue.report([]) == dict(checked=0, gone=0, back=0, hidden=[])


def test_add_videos_brings_their_channels_in_unfollowed(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=3).channel(B, 'Garden', videos=2)
    catalogue.add(B)                                                                         # followed already: stays followed
    r = catalogue.add_videos([vid(A, 0), vid(A, 1), vid(A, 1), vid(B, 0), 'gonegonegon'], now='t1')
    assert r == dict(added=3, already=0, missing=1)
    assert library.channel(A)['follow'] is False and library.channel(B)['follow'] is True and catalogue.followed() == [(B, 'Garden')]
    assert sorted(v['id'] for v in videos_of(A)) == [vid(A, 0), vid(A, 1)]
    assert catalogue.add_videos([vid(A, 0), vid(A, 2)]) == dict(added=1, already=1, missing=0)
    assert catalogue.add_videos([]) == dict(added=0, already=0, missing=0)
