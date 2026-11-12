"""related.py: reading what watch pages list next and what channels feature, asking again after a week, and counting it up into the suggestions."""
import datetime
import pytest
from fake_youtube import FakeYoutube, vid
from takeout import chan, watch
from tubes import catalogue, db, history, related

X, Y, P, Q, R, F, Z = (chan(x) for x in 'xypqrfz')
NOW = '2026-11-01T00:00:00+00:00'


def later(days): return (datetime.datetime.fromisoformat(NOW) + datetime.timedelta(days=days)).isoformat(timespec='seconds')


def follow(fake, *cids):
    for c in cids:
        fake.channel(c, f'Channel {c[2]}', videos=5)
        catalogue.add(c, now=NOW)
    catalogue.sync(now=NOW)


def newest(cid, n=related.VIDEOS_PER_SOURCE): return [vid(cid, 4 - i) for i in range(n)]


@pytest.fixture
def two_followed(fake_youtube):
    """X and Y are followed. X's three newest videos each list P (and once Q); of Y's, one lists P and R, one R and Y itself, and the third
    lists nothing (so only two of its pages count); X features F."""
    follow(fake_youtube, X, Y)
    a, b, c = newest(X)
    fake_youtube.watch_next(a, [(P, 'Channel p', '@p'), (Q, 'Channel q', None), (P, 'Channel p', '@p')]).watch_next(b, [(P, 'Channel p', '@p')]).watch_next(c, [(P, 'Channel p', '@p'), (X, 'Channel x', None)])
    a, b, c = newest(Y)
    fake_youtube.watch_next(a, [(P, 'Channel p', '@p'), (R, 'Channel r', None)]).watch_next(b, [(R, 'Channel r', None), (Y, 'Channel y', None)])
    fake_youtube.featuring(X, [F, X])
    return fake_youtube


# Reading a watch page.

def test_parse_next_reads_each_listed_videos_channel_in_order_leaving_out_shelves():
    page = FakeYoutube.answer_next(type('F', (), {'next': {'v': [(P, 'Channel p', '@p'), (Q, 'Channel q', None), (P, 'Channel p', '@p')]}})(), 'v')
    page['contents']['twoColumnWatchNextResults']['secondaryResults']['secondaryResults']['results'] += [
        dict(lockupViewModel=dict(contentType='LOCKUP_CONTENT_TYPE_PLAYLIST', metadata={'browseEndpoint': dict(browseId=R)})),
        dict(compactVideoRenderer=dict(videoId='old', shortBylineText=dict(runs=[dict(text='Channel r', navigationEndpoint=dict(browseEndpoint=dict(browseId=R, canonicalBaseUrl='/@r')))])))]
    assert related.parse_next(page) == [dict(channel_id=P, title='Channel p', handle='@p'), dict(channel_id=Q, title='Channel q', handle=None),
                                        dict(channel_id=P, title='Channel p', handle='@p'), dict(channel_id=R, title='Channel r', handle='@r')]
    assert related.parse_next({}) == [] and related.parse_next(dict(contents={})) == []


def test_watch_next_says_when_a_page_lists_nothing_or_cannot_be_read(fake_youtube):
    with pytest.raises(related.RelatedError, match='listed no videos'): related.watch_next('nothing0000')
    fake_youtube.web_down = True
    with pytest.raises(related.RelatedError, match=r'refused the watch page of nothing0000 \(503\)'): related.watch_next('nothing0000')


def test_watch_next_says_when_youtube_cannot_be_reached(monkeypatch):
    monkeypatch.setenv('TUBES_YOUTUBE_WEB', 'http://127.0.0.1:9')
    with pytest.raises(related.RelatedError, match='could not be reached'): related.watch_next('v0000000000')


def test_featured_reads_multiple_channel_sections_in_either_case(fake_youtube):
    fake_youtube.featuring(X, [P, Q]).featuring(X, [Q, R, X], title='More')
    fake_youtube.sections[X][1]['snippet']['type'] = 'multipleChannels'
    assert related.featured(X) == [P, Q, R]
    assert related.featured(Y) == []


# Asking, and asking again.

def test_refresh_counts_what_the_followed_channels_point_at(two_followed):
    r = related.refresh(NOW, pause=0)
    assert (r['asked'], r['failed'], r['due'], r['suggested'], r['added']) == (2, 0, 0, 4, 4)
    assert two_followed.pages == newest(X) + newest(Y)                         # each one's three newest uploads
    got = {i['channel_id']: i for i in history.suggestions(order='suggested')['items']}
    assert list(got) == [P, R, F, Q]                                            # P from both; then by score: R 2/2, F featured 0.5, Q 1/3
    assert (got[P]['suggested_by'], got[P]['related_score'], got[P]['watches'], got[P]['title'], got[P]['handle']) == (2, 1.5, 0, 'Channel p', '@p')   # every one of X's pages, half of Y's
    assert got[P]['suggested_from'] == ['Channel x', 'Channel y']               # the source whose pages listed it most first
    assert (got[R]['related_score'], got[Q]['related_score'], got[F]['related_score']) == (1.0, round(1 / 3, 4), 0.5)
    assert got[F]['title'] == F and got[F]['suggested_from'] == ['Channel x']   # featured only: no name until YouTube is asked
    assert X not in got and Y not in got                                        # followed channels are never suggested
    s = history.summary()
    assert (s['suggested'], s['unwatched'], s['open'], s['related']['sources'], s['related']['asked'], s['related']['last']) == (4, 4, 4, 2, 2, NOW)
    assert related.status(NOW)['due'] == 0 and related.status(later(8))['due'] == 2


def test_suggested_order_breaks_ties_by_score_and_rejects_others(two_followed):
    related.refresh(NOW, pause=0)
    assert [i['channel_id'] for i in history.suggestions()['items']][0] == P     # watched order: no watches anywhere, so related score decides
    with pytest.raises(ValueError, match='Order by watched or suggested'): history.suggestions(order='newest')


def test_sources_are_asked_again_after_a_week_and_failures_after_a_day(two_followed):
    related.refresh(NOW, pause=0)
    two_followed.pages.clear()
    assert related.refresh(later(3), pause=0)['asked'] == 0 and two_followed.pages == []
    two_followed.web_down = True; two_followed.quota_left = 0                  # nothing answers: a failure, and the links are kept
    r = related.refresh(later(8), pause=0)
    assert (r['asked'], r['failed']) == (2, 2) and 'refused the watch page' in r['errors'][0]['error']
    assert history.suggestion(P)['suggested_by'] == 2 and history.suggestion(P)['related_score'] == 1.5   # the old pages still count, as many as they were
    assert related.status(later(8))['failed'] == 2
    assert related.refresh(later(8.5), pause=0)['asked'] == 0                   # a failure waits a day
    two_followed.web_down = False; two_followed.quota_left = None
    del two_followed.next[newest(Y)[0]]; del two_followed.next[newest(Y)[1]]
    r = related.refresh(later(9.5), pause=0)
    assert (r['asked'], r['failed']) == (2, 1)                                  # Y's pages list nothing now: a failure, whatever it features
    assert related.refresh(later(9.5), force=True, limit=1, pause=0) | dict(errors=[]) == dict(asked=1, failed=0, due=1, links=3, errors=[], suggested=4, added=0)


def test_refresh_asks_at_most_limit_oldest_first(two_followed):
    assert related.refresh(NOW, limit=1, pause=0)['due'] == 1
    assert related.status(NOW)['due'] == 1
    assert related.refresh(NOW, limit=5, pause=0)['asked'] == 1 and two_followed.pages[-1] == newest(Y)[-1]


def test_a_source_no_longer_followed_stops_counting(two_followed):
    related.refresh(NOW, pause=0)
    catalogue.remove(Y)
    assert related.aggregate() == dict(suggested=3, added=0)
    assert history.suggestion(P)['suggested_by'] == 1
    with pytest.raises(history.NotFound): history.suggestion(R)               # only Y pointed at it, and it was never watched


def test_followed_channel_with_no_videos_fails_without_asking(fake_youtube, monkeypatch):
    monkeypatch.delenv('YOUTUBE_API_KEY')
    with db.connect() as con: con.execute("INSERT INTO channels (id, title, follow, complete) VALUES (?, 'Empty', ?, ?)", (X, True, False))
    r = related.refresh(NOW, pause=0)
    assert r['errors'] == [dict(channel=X, error='It has no videos to read the watch pages of.')] and fake_youtube.pages == []


def test_lookup_asks_youtube_about_the_related_channels(two_followed):
    related.refresh(NOW, pause=0)
    two_followed.channel(F, 'Featured friend', handle='@friend', topics=['Hobby'], kids=True)
    assert history.look_up(NOW) == dict(looked_up=4, missing=3)                # P, Q and R are not channels the stand-in API holds
    f = history.suggestion(F)
    assert (f['title'], f['handle'], f['topics'], f['made_for_kids']) == ('Featured friend', '@friend', ['Hobby'], True)


# With a watch history.

def sittings(day):
    """A and B watched together in one sitting (five minutes apart)."""
    return [watch(f'2026-01-{day:02d}T10:00:00Z', f'a{day:010d}', 'A video', A, 'Channel a'), watch(f'2026-01-{day:02d}T10:05:00Z', f'b{day:010d}', 'B video', B, 'Channel b')]


A, B = chan('a'), chan('b')


def test_history_channels_are_sources_and_lend_their_group(fake_youtube):
    from takeout import as_json
    history.import_text(as_json([w for d in range(1, 8) for w in sittings(d)]), 'one', now=NOW, lookup=False)
    assert related.source_ids() == {A, B}
    assert related.sources()[A] == ['a0000000007', 'a0000000006', 'a0000000005']   # the ones watched last
    fake_youtube.watch_next('a0000000007', [(Z, 'Channel z', None), (B, 'Channel b', None)])
    related.refresh(NOW, pause=0)
    z, b = history.suggestion(Z), history.suggestion(B)
    assert z['watches'] == 0 and z['group_id'] == history.suggestion(A)['group_id'] is not None
    assert (b['watches'], b['suggested_by'], b['suggested_from']) == (7, 1, ['Channel a'])   # watched and pointed at: keeps both
    history.refresh(NOW, lookup=False)                                          # a regroup keeps the related ones
    assert history.suggestion(Z)['suggested_by'] == 1 and history.suggestion(Z)['group_id'] == history.suggestion(A)['group_id']
    history.remove_source('one', now=NOW)                                       # A is no longer watched: what it pointed at goes
    with pytest.raises(history.NotFound): history.suggestion(Z)


def test_a_watched_channel_that_leaves_the_history_stays_while_pointed_at(two_followed):
    from takeout import as_json
    history.import_text(as_json([watch('2026-01-01T10:00:00Z', 'p0000000001', 'P video', P, 'Channel p')]), 'one', now=NOW, lookup=False)
    related.refresh(NOW, pause=0)
    assert history.suggestion(P)['watches'] == 1
    history.remove_source('one', now=NOW)
    p = history.suggestion(P)
    assert (p['watches'], p['score'], p['first'], p['suggested_by']) == (0, 0.0, None, 2)


def test_watch_next_says_when_youtube_answers_with_something_else(fake_youtube, monkeypatch):
    import urllib.request
    from fakes import FakeResponse
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: FakeResponse(b'<html>consent</html>'))
    with pytest.raises(related.RelatedError, match='did not answer with JSON'): related.watch_next('v0000000000')


def test_parse_next_takes_no_name_where_the_listing_gives_none():
    item = dict(lockupViewModel=dict(metadata=dict(rows=[dict(metadataRows=[dict(metadataParts=[dict(text=dict(content=' '))]), dict()])], browseEndpoint=dict(browseId=P, canonicalBaseUrl='/channel/x'))))
    by = dict(compactVideoRenderer=dict(shortBylineText=dict(runs=[]), longBylineText=dict(runs=[dict(navigationEndpoint=dict(browseEndpoint=dict(browseId='FEwhat'))), dict(navigationEndpoint=dict(browseEndpoint=dict(browseId=Q)))])))
    page = dict(secondaryResults=dict(results=[item, by, dict(compactVideoRenderer=dict(title='no channel'))]))
    assert related.parse_next(page) == [dict(channel_id=P, title=None, handle=None), dict(channel_id=Q, title=None, handle=None)]


def test_a_dismissed_channel_stays_dismissed_when_it_drops_out_and_comes_back(two_followed):
    related.refresh(NOW, pause=0)
    history.dismiss(Q)
    del two_followed.next[newest(X)[0]]                                         # the only page that listed Q
    two_followed.watch_next(newest(X)[0], [(P, 'Channel p', '@p')])
    related.refresh(later(8), pause=0)
    assert history.suggestion(Q)['suggested_by'] == 0 and history.suggestion(Q)['dismissed'] is not None
    two_followed.watch_next(newest(X)[0], [(Q, 'Channel q', None)])
    related.refresh(later(16), pause=0)
    assert history.suggestion(Q)['suggested_by'] == 1 and history.suggestion(Q)['dismissed'] is not None
