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


def test_the_recheck_fills_language_captions_and_regions_on_videos_added_before_them(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=2); catalogue.add(A); catalogue.sync_channel(A)
    with db.connect() as con: assert con.execute('SELECT COUNT(*) FROM videos WHERE language IS NULL AND captions IS NOT NULL').fetchone()[0] == 2   # the stand-in says no language, and captions false
    v = fake_youtube.videos[vid(A, 1)]
    v['snippet']['defaultAudioLanguage'] = 'en-GB'; v['contentDetails'].update(caption='true', regionRestriction=dict(blocked=['GB']))
    catalogue.recheck(0, now='t1')
    catalogue.save_filters(dict(region='GB'))
    assert vid(A, 1) not in [x['id'] for x in library.videos()['videos']] and dict(code='en', videos=1) in library.languages()     # counted before the filters
    with db.connect() as con: assert con.execute('SELECT language, captions, regions_blocked FROM videos WHERE id = ?', (vid(A, 1),)).fetchone() == ('en-GB', True, 'GB')


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


# iPlayer programmes and episodes (fake_iplayer: tests/utils/fake_iplayer.py).

from fake_iplayer import ep_id  # noqa: E402
from tubes import cache, iplayer  # noqa: E402

P = 'b0000001'


def test_add_an_iplayer_programme_follows_it_and_a_sync_reads_its_episodes(fake_iplayer, monkeypatch):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=5)
    r = catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}/harbour-lights', now='2026-11-12T10:00:00+00:00')
    c = r['channel']
    assert r['kind'] == 'channel' and (c['id'], c['platform'], c['title'], c['follow'], c['total_videos'], c['videos']) == (P, 'iplayer', 'Harbour Lights', True, 5, 0)
    monkeypatch.setattr(iplayer, 'PAGE', 2)
    seen = []
    r = catalogue.sync_channel(P, now='2026-11-12T10:00:00+00:00', progress=seen.append)
    assert r == dict(channel=P, title='Harbour Lights', added=5, pages=3, complete=True) and seen == [2, 4, 5]
    vs = videos_of(P)
    assert [(v['id'], v['title'], v['series'], v['episode'], v['platform']) for v in vs][:2] == [(ep_id(P, 5), 'Chapter 5', 'Series 1', 5, 'iplayer'), (ep_id(P, 4), 'Chapter 4', 'Series 1', 4, 'iplayer')]
    assert library.channel(P)['synced'] == '2026-11-12T10:00:00+00:00' and library.channel(P)['complete'] is True
    fake_iplayer.episode(P, 6); fake_iplayer.drop(ep_id(P, 1))
    fake_iplayer.episodes[ep_id(P, 5)]['subtitle'] = 'Series 1: 5. Chapter Five'
    r = catalogue.sync_channel(P, now='2026-11-13T10:00:00+00:00')
    assert r['added'] == 1 and len(videos_of(P)) == 5 and library.video(ep_id(P, 1))['gone'] == '2026-11-13T10:00:00+00:00'
    assert library.video(ep_id(P, 5))['title'] == 'Chapter Five'                           # every episode is refreshed, not just new ones
    fake_iplayer.episode(P, 1)                                                                # offered again: shown again
    catalogue.sync_channel(P, now='2026-11-14T10:00:00+00:00')
    assert library.video(ep_id(P, 1))['gone'] is None


def test_an_iplayer_sync_marks_nothing_gone_from_a_list_cut_short(fake_iplayer, monkeypatch):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=3); catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}')
    catalogue.sync_channel(P)
    monkeypatch.setattr(iplayer, 'episodes_page', lambda pid, page=1: ([], True))
    assert catalogue.sync_channel(P)['added'] == 0 and len(videos_of(P)) == 3
    monkeypatch.setattr(iplayer, 'programme', lambda pid: None)
    with pytest.raises(catalogue.NotFound, match='no programme b0000001 any more'): catalogue.sync_channel(P)


def test_an_iplayer_programme_removed_while_it_syncs(fake_iplayer, monkeypatch):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=3); catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}')
    real = iplayer.programme
    def removed_after(pid):
        r = real(pid); catalogue.remove(P); return r
    monkeypatch.setattr(iplayer, 'programme', removed_after)
    with pytest.raises(catalogue.NotFound, match='removed while it synced'): catalogue.sync_channel(P)
    monkeypatch.setattr(iplayer, 'programme', real); catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}')
    real_page = iplayer.episodes_page
    def removed_during(pid, page=1):
        r = real_page(pid, page); catalogue.remove(P); return r
    monkeypatch.setattr(iplayer, 'episodes_page', removed_during)
    with pytest.raises(catalogue.NotFound, match='removed while it synced'): catalogue.sync_channel(P)
    assert videos_of(P) == []


def test_add_one_iplayer_episode_brings_its_programme_in_unfollowed(fake_iplayer):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=2)
    r = catalogue.add(f'https://www.bbc.co.uk/iplayer/episode/{ep_id(P, 1)}/harbour-lights')
    assert r['kind'] == 'video' and (r['video']['title'], r['video']['channel'], r['video']['platform']) == ('Chapter 1', 'Harbour Lights', 'iplayer')
    assert library.channel(P)['follow'] is False and catalogue.followed() == []
    assert catalogue.add(f'https://www.bbc.co.uk/programmes/{ep_id(P, 2)}')['kind'] == 'video'          # a /programmes link to an episode
    assert catalogue.add(f'https://www.bbc.co.uk/programmes/{P}')['kind'] == 'channel' and catalogue.followed() == [(P, 'Harbour Lights')]
    film = fake_iplayer.one_off('p0000009', 'A Film')
    r = catalogue.add(f'https://www.bbc.co.uk/iplayer/episode/{film}/a-film')
    assert r['video']['channel'] == 'BBC Two' and library.channel('bbc_two')['follow'] is False
    with pytest.raises(catalogue.NotFound, match='iPlayer has no programme b0000099'): catalogue.add('https://www.bbc.co.uk/iplayer/episodes/b0000099')
    with pytest.raises(catalogue.NotFound, match='does not offer m0000099'): catalogue.add('https://www.bbc.co.uk/iplayer/episode/m0000099')


def test_the_youtube_recheck_and_reports_leave_iplayer_episodes_alone(fake_iplayer, fake_youtube):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=2); catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}'); catalogue.sync_channel(P)
    assert catalogue.recheck(limit=0) == dict(checked=0, gone=0, back=0)
    assert catalogue.report([ep_id(P, 1)])['hidden'] == [] and library.video(ep_id(P, 1))['gone'] is None
    assert fake_youtube.calls == []


def test_a_sync_of_everything_notes_an_iplayer_failure_and_goes_on(fake_iplayer, fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=2); catalogue.add(A)
    fake_iplayer.programme(P, 'Harbour Lights', episodes=2); catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}')
    fake_iplayer.region = None; fake_iplayer.programmes[P]['id'] = 'b0000002'                 # iPlayer answers, but not about this programme
    r = catalogue.sync()
    assert [e['channel'] for e in r['errors']] == [P] and [d['channel'] for d in r['channels']] == [A]
    fake_iplayer.close()
    r = catalogue.sync([P])
    assert 'could not be reached' in r['errors'][0]['error']


def test_an_expired_iplayer_episode_is_hidden_unless_it_is_cached(fake_iplayer):
    fake_iplayer.programme(P, 'Harbour Lights')
    fake_iplayer.episode(P, 1, expires='2026-11-12T00:00:00Z'); fake_iplayer.episode(P, 2, expires='2026-11-12T00:00:00Z'); fake_iplayer.episode(P, 3)
    catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}'); catalogue.sync_channel(P)
    before, after = '2026-11-11T00:00:00+00:00', '2026-11-13T00:00:00+00:00'
    assert len(library.videos(P, now=before)['videos']) == 3 and len(library.videos(P, now=after)['videos']) == 1
    cache.begin(ep_id(P, 2), cache.stamp()); cache.finish(ep_id(P, 2), cache.stamp())          # fetched before it expired
    assert [v['id'] for v in library.videos(P, now=after)['videos']] == [ep_id(P, 3), ep_id(P, 2)]
    c = library.channels(now=after)[0]
    assert (c['videos'], c['hidden']) == (2, 1)
    s = library.status(now=after)
    assert (s['videos'], s['hidden']) == (2, 1)
    assert {v['id'] for v in library.shuffle(10, P, now=after)} == {ep_id(P, 3), ep_id(P, 2)}
    assert library.video(ep_id(P, 1))['expires'] == '2026-11-12T00:00:00+00:00'               # still found by id


def test_an_episode_whose_programme_is_not_offered_is_kept_under_its_network(fake_iplayer):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=1); e = ep_id(P, 1)
    del fake_iplayer.programmes[P]
    r = catalogue.add(f'https://www.bbc.co.uk/iplayer/episode/{e}')
    assert r['video']['channel_id'] == 'bbc_one' and r['video']['channel'] == 'BBC One'
    assert [v['id'] for v in videos_of('bbc_one')] == [e] and library.channel(P) is None


def test_needs_youtube(fake_iplayer, fake_youtube):
    assert catalogue.needs_youtube() is False and catalogue.needs_youtube([]) is False
    fake_iplayer.programme(P, 'Harbour Lights'); catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{P}')
    assert catalogue.needs_youtube() is False and catalogue.needs_youtube([P]) is False
    assert catalogue.needs_youtube(['UCnotinthelibraryatallxxx']) is True
    fake_youtube.channel(A, 'Workshop'); catalogue.add(A)
    assert catalogue.needs_youtube() is True and catalogue.needs_youtube([P, A]) is True and catalogue.needs_youtube([P]) is False


def test_follow_an_iplayer_category_takes_its_one_offs(fake_iplayer, monkeypatch):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=2); fake_iplayer.categories['films'][1].append(P)       # a series filed under Films: left to be followed itself
    for n in range(3): fake_iplayer.one_off(f'p000000{n}', f'Film {n}', categories=('films',))
    r = catalogue.add('https://www.bbc.co.uk/iplayer/categories/films/featured', now='2026-11-12T10:00:00+00:00')
    assert r['kind'] == 'channel' and (r['channel']['id'], r['channel']['title'], r['channel']['follow']) == ('iplayer-films', 'Films', True)
    monkeypatch.setattr(iplayer, 'PAGE', 2)
    assert catalogue.sync_channel('iplayer-films', now='2026-11-12T10:00:00+00:00')['added'] == 3
    assert sorted(v['id'] for v in videos_of('iplayer-films')) == ['p0000000', 'p0000001', 'p0000002'] and library.channel(P) is None
    fake_iplayer.drop('p0000000'); fake_iplayer.categories['films'][1].remove('p0000000'); fake_iplayer.one_off('p0000009', 'Film 9', categories=('films',))
    r = catalogue.sync_channel('iplayer-films', now='2026-11-13T10:00:00+00:00')
    assert r['added'] == 1 and library.video('p0000000')['gone'] == '2026-11-13T10:00:00+00:00'
    with pytest.raises(catalogue.NotFound, match='iPlayer has no category nope'): catalogue.add('https://www.bbc.co.uk/iplayer/browse/nope')
    del fake_iplayer.categories['films']
    with pytest.raises(catalogue.NotFound, match='no category films any more'): catalogue.sync_channel('iplayer-films')


def test_a_category_keeps_every_one_off_it_lists(fake_iplayer):
    fake_iplayer.one_off('p0000001', 'A Documentary', categories=('documentaries',))
    catalogue.add('https://www.bbc.co.uk/iplayer/browse/documentaries'); catalogue.sync_channel('iplayer-documentaries')
    assert [v['channel_id'] for v in videos_of('iplayer-documentaries')] == ['iplayer-documentaries']


def test_one_film_added_on_its_own_goes_under_films(fake_iplayer):
    film = fake_iplayer.one_off('p0000001', 'A Film', categories=('films',))
    r = catalogue.add(f'https://www.bbc.co.uk/iplayer/episode/{film}/a-film')
    assert r['video']['channel'] == 'Films' and library.channel('iplayer-films')['follow'] is False
    catalogue.add('https://www.bbc.co.uk/iplayer/categories/films/featured')                     # following Films later keeps the film where it is
    assert library.channel('iplayer-films')['follow'] is True and [v['id'] for v in videos_of('iplayer-films')] == [film]


def test_a_category_page_of_series_only_does_not_end_its_sync(fake_iplayer, monkeypatch):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=1).programme('b0000002', 'Night Garden', episodes=1)
    fake_iplayer.one_off('p0000001', 'Film 1', categories=('films',)); fake_iplayer.one_off('p0000002', 'Film 2', categories=('films',))
    fake_iplayer.categories['films'][1][:] = [P, 'b0000002', 'p0000001', 'p0000002', 'b0000002', P]    # pages of 2: series only, films, series only
    monkeypatch.setattr(iplayer, 'PAGE', 2)
    catalogue.add('https://www.bbc.co.uk/iplayer/categories/films/featured')
    assert catalogue.sync_channel('iplayer-films', now='t1')['added'] == 2 and sorted(v['id'] for v in videos_of('iplayer-films')) == ['p0000001', 'p0000002']
    fake_iplayer.categories['films'][1].remove('p0000002'); fake_iplayer.drop('p0000002')
    catalogue.sync_channel('iplayer-films', now='t2')                                            # the last page is series only: the list was still read whole
    assert library.video('p0000002')['gone'] == 't2'
