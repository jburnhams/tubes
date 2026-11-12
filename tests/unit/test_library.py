from library import CHANNELS, VIDEOS, seed
from tubes import cache, catalogue, db, library


def test_status_before_any_sync(monkeypatch):
    assert library.status() == dict(synced=None, channels=0, videos=0, hidden=0, live=0, filtered=0, configured=False)
    monkeypatch.setenv('YOUTUBE_API_KEY', 'k')
    assert library.status()['configured'] is True


def test_channels_by_title_with_counts():
    seed(); seed(channels=[dict(CHANNELS[0], id='UCempty', title='Alpha')], videos=[], synced=None)
    got = library.channels()
    assert [(c['title'], c['videos'], c['latest']) for c in got] == [('Alpha', 0, None), ('night sky', 2, '2026-01-02T00:00:00Z'), ('Workshop', 2, '2026-01-03T00:00:00Z')]
    assert library.channel('UCbbbbbbbbbbbbbbbbbbbbbb')['handle'] is None and library.channel('nope') is None
    assert {k: got[1][k] for k in ('follow', 'complete', 'resumable')} == dict(follow=True, complete=False, resumable=False)     # booleans on both engines


def test_videos_newest_first_in_pages_by_cursor():
    seed()
    first = library.videos(limit=2)
    assert [v['id'] for v in first['videos']] == ['aaaaaaaaaaa', 'ccccccccccc'] and first['has_more'] is True    # same day: the higher id first
    assert first['videos'][0]['channel'] == 'Workshop' and first['videos'][0]['cache_state'] is None
    rest = library.videos(after=library.cursor(first['videos'][-1]), limit=2)
    assert [v['id'] for v in rest['videos']] == ['bbbbbbbbbbb', 'ddddddddddd'] and rest['has_more'] is False
    assert [v['id'] for v in library.videos(channel_id='UCbbbbbbbbbbbbbbbbbbbbbb')['videos']] == ['ccccccccccc', 'ddddddddddd']


def test_search_matches_words_in_any_order_and_case():
    seed()
    assert [v['id'] for v in library.videos(search='SHELF')['videos']] == ['aaaaaaaaaaa', 'bbbbbbbbbbb']
    assert [v['id'] for v in library.videos(search='up moon')['videos']] == ['ddddddddddd']
    assert library.videos(search='50%')['videos'][0]['id'] == 'aaaaaaaaaaa'
    assert library.videos(search='5_%')['videos'] == []                                       # wildcards are literal
    assert library.videos(search='  ')['has_more'] is False and len(library.videos(search='  ')['videos']) == 4


def test_shuffle_and_one_video_with_its_copy():
    seed()
    assert sorted(v['id'] for v in library.shuffle()) == sorted(v['id'] for v in VIDEOS)
    assert len(library.shuffle(count=1)) == 1
    assert {v['channel_id'] for v in library.shuffle(channel_id=CHANNELS[1]['id'])} == {CHANNELS[1]['id']}
    cache.begin('ccccccccccc', cache.stamp())
    v = library.video('ccccccccccc')
    assert (v['title'], v['channel'], v['cache_state'], v['cache_bytes']) == ('Stars in winter', 'night sky', 'fetching', 0)


def test_videos_gone_from_youtube_are_hidden_but_still_open():
    seed()
    with db.connect() as con: con.execute("UPDATE videos SET gone = 'then' WHERE id IN ('aaaaaaaaaaa', 'ccccccccccc')")
    assert [v['id'] for v in library.videos()['videos']] == ['bbbbbbbbbbb', 'ddddddddddd']
    assert [v['id'] for v in library.videos(search='shelf')['videos']] == ['bbbbbbbbbbb'] and len(library.shuffle(10)) == 2
    assert [(c['videos'], c['hidden'], c['latest']) for c in library.channels()] == [(1, 1, '2026-01-01T00:00:00Z'), (1, 1, '2026-01-02T00:00:00Z')]
    assert (library.status()['videos'], library.status()['hidden']) == (2, 2) and library.video('aaaaaaaaaaa')['gone'] == 'then'


def test_streams_not_over_are_hidden_but_still_open():
    seed()
    with db.connect() as con:
        con.execute("UPDATE videos SET live = 'live' WHERE id = 'aaaaaaaaaaa'"); con.execute("UPDATE videos SET live = 'upcoming', gone = 'then' WHERE id = 'ccccccccccc'")
        con.execute("UPDATE videos SET live = 'was' WHERE id = 'bbbbbbbbbbb'")                                       # over: shown
    assert [v['id'] for v in library.videos()['videos']] == ['bbbbbbbbbbb', 'ddddddddddd'] and len(library.shuffle(10)) == 2
    assert [(c['videos'], c['hidden']) for c in library.channels()] == [(1, 1), (1, 1)]
    assert {k: library.status()[k] for k in ('videos', 'hidden', 'live')} == dict(videos=2, hidden=1, live=1)      # a gone stream counts once, as gone
    assert library.video('aaaaaaaaaaa')['live'] == 'live'


def test_filters_hide_by_length_and_streams_and_come_back():
    seed()
    with db.connect() as con:
        con.execute("UPDATE videos SET duration = 45 WHERE id = 'aaaaaaaaaaa'"); con.execute("UPDATE videos SET duration = 7200 WHERE id = 'bbbbbbbbbbb'")
        con.execute("UPDATE videos SET duration = NULL, live = 'was' WHERE id = 'ccccccccccc'")                       # length not known: kept by the length limits
        con.execute("UPDATE videos SET gone = 'then', duration = 30 WHERE id = 'ddddddddddd'")                        # gone: counted as gone, not filtered
    assert library.filters() == dict(min_seconds=None, max_seconds=None, streams='current')
    assert catalogue.save_filters(dict(min_seconds=60, max_seconds=3600)) == dict(min_seconds=60, max_seconds=3600, streams='current')
    assert [v['id'] for v in library.videos()['videos']] == ['ccccccccccc'] and [v['id'] for v in library.shuffle(10)] == ['ccccccccccc']
    assert [v['id'] for v in library.videos(search='shelf')['videos']] == []
    assert {k: library.status()[k] for k in ('videos', 'hidden', 'live', 'filtered')} == dict(videos=1, hidden=1, live=0, filtered=2)
    assert [(c['videos'], c['hidden']) for c in library.channels()] == [(1, 1), (0, 2)]
    catalogue.save_filters(dict(streams='all'))                                                                       # past streams too; the lengths stay
    assert library.videos()['videos'] == [] and library.status()['filtered'] == 3
    assert library.video('ccccccccccc')['id'] == 'ccccccccccc'                                                          # a link still opens
    catalogue.save_filters(dict(min_seconds=None, max_seconds=None, streams='current'))
    assert sorted(v['id'] for v in library.videos()['videos']) == ['aaaaaaaaaaa', 'bbbbbbbbbbb', 'ccccccccccc'] and library.status()['filtered'] == 0


def test_filters_refuse_what_cannot_be_used_and_save_nothing():
    for bad, why in [(dict(min_seconds=-1), 'A length must be a number of seconds, 0 or more.'), (dict(max_seconds='long'), 'A length must be a number of seconds, 0 or more.'),
                     (dict(min_seconds=True), 'A length must be a number of seconds, 0 or more.'), (dict(streams='none'), 'streams must be one of current, all.'),
                     (dict(min_seconds=600, max_seconds=60), 'The shortest length must not be longer than the longest.'), (dict(colour='red'), 'There is no filter called colour.')]:
        try: catalogue.save_filters(bad); raise AssertionError(bad)
        except catalogue.FilterError as e: assert str(e) == why
    assert library.filters() == library.FILTERS
    catalogue.save_filters(dict(max_seconds=90.5)); assert library.filters()['max_seconds'] == 90.5
    with db.connect() as con: con.execute("UPDATE meta SET value = 'not json' WHERE key = 'shown'")
    assert library.filters() == library.FILTERS                                                                      # a broken row reads as the defaults
