from library import CHANNELS, VIDEOS, seed
from tubes import cache, library


def test_status_before_any_sync(monkeypatch):
    assert library.status() == dict(synced=None, channels=0, videos=0, configured=False)
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
