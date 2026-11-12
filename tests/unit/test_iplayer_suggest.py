"""iplayer_suggest.py: iPlayer's catalogue kept in bbc_programmes, and programmes suggested by what they are like (stand-in iPlayer: tests/utils/fake_iplayer.py)."""
import pytest
from tubes import cache, catalogue, db, history, iplayer, iplayer_suggest as s, related

NOW = '2026-11-12T05:00:00+00:00'
OCEAN, REEF, ICE, COURT, BAKE = 'b0000001', 'b0000002', 'b0000003', 'b0000004', 'b0000005'


@pytest.fixture
def bbc(fake_iplayer):
    nature = dict(categories=('documentaries', 'science-and-nature', 'documentaries-science-and-nature'), label='Nature', network=('bbc_one', 'BBC One'))
    fake_iplayer.programme(OCEAN, 'Deep Ocean', episodes=2, synopsis='Whales and sharks of the deep ocean, filmed at night.', **nature)
    fake_iplayer.programme(REEF, 'Reef Life', synopsis='Sharks, turtles and coral on the reef.', **nature)
    fake_iplayer.programme(ICE, 'Polar Ice', synopsis='Bears and seals on the polar ice.', **nature)
    fake_iplayer.programme(COURT, 'Night Court', categories=('drama-and-soaps', 'drama-crime'), label='Crime Drama', synopsis='A detective and a judge at night.')
    fake_iplayer.programme(BAKE, 'Bake Off Junior', categories=('cbbc', 'childrens-entertainment', 'food'), label='CBBC', synopsis='Young bakers bake cakes.')
    fake_iplayer.one_off('p0000009', 'A Film About Sharks', categories=('films',))
    return fake_iplayer


def test_the_catalogue_is_read_once_a_day_and_drops_what_iplayer_no_longer_lists(bbc, monkeypatch):
    monkeypatch.setattr(iplayer, 'PAGE', 2)
    r = s.refresh_catalogue(NOW)
    assert r == dict(read=6, new=6, dropped=0)
    with db.connect() as con: row = db.row(con.execute('SELECT * FROM bbc_programmes WHERE id = ?', (OCEAN,)))
    assert (row['title'], row['label'], row['network'], row['kind'], row['categories'], row['seen'], row['thumbnail']) == (
        'Deep Ocean', 'Nature', 'bbc_one', 'brand', 'documentaries|science-and-nature|documentaries-science-and-nature', NOW, f'https://img.test/ic/480x480/{OCEAN}.jpg')
    assert s.refresh_catalogue('2026-11-12T10:00:00+00:00') == dict(skipped=NOW)                  # read 5 hours ago: not again
    del bbc.programmes[ICE]
    assert s.refresh_catalogue('2026-11-13T06:00:00+00:00') == dict(read=5, new=0, dropped=1)
    with db.connect() as con: assert con.execute('SELECT seen FROM bbc_programmes WHERE id = ?', (OCEAN,)).fetchone()[0] == NOW   # first seen, kept
    bbc.atoz_fails = 'd'
    with pytest.raises(iplayer.IplayerError, match='refused'): s.refresh_catalogue('2026-11-14T06:00:00+00:00', force=True)
    with db.connect() as con: assert con.execute('SELECT COUNT(*) FROM bbc_programmes').fetchone()[0] == 5      # a failed read keeps what was there


def test_features_and_likeness():
    p = dict(id='x', title='Deep Ocean', synopsis='The whales of the deep.', categories='documentaries|documentaries-history', label='Nature', network='bbc_two')
    f = s.features(p)
    assert f['c:documentaries'] == 1.0 and f['c:documentaries-history'] == 2.0 and f['l:nature'] == 1.5 and f['n:bbc_two'] == 0.5 and 'w:the' not in f and f['w:whales'] > 0
    assert s.words("It's the deep, deep sea!") == ['deep', 'deep', 'sea']
    assert s.fine(['documentaries', 'documentaries-history', 'science-and-nature']) == {'documentaries-history'}
    empty = dict(id='y', title='Y', synopsis=None, categories=None, label=None, network=None)
    v = s.vectors([p, empty, dict(p, id='z')])
    assert round(s.cosine(v['x'], v['z']), 6) == 1.0 and s.cosine(v['x'], v['y']) == 0.0


def test_programmes_like_those_followed_are_suggested_with_why(bbc):
    catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{OCEAN}')
    r = s.run(NOW)
    assert r['catalogue']['read'] == 6 and r['sources'] == 1
    items = {x['channel_id']: x for x in history.suggestions(order='suggested')['items'] if x['platform'] == 'iplayer'}
    assert list(items)[:2] == [REEF, ICE] and OCEAN not in items and 'p0000009' not in items                # followed and one-offs are not suggested
    reef = items[REEF]
    assert reef['suggested_from'] == ['Deep Ocean'] and reef['topics'] == ['Nature', 'Documentaries', 'Science and nature'] and reef['made_for_kids'] is False
    assert reef['link'] == f'https://www.bbc.co.uk/iplayer/episodes/{REEF}' and reef['related_score'] > items.get(COURT, dict(related_score=0))['related_score']
    assert history.suggestion(REEF)['suggested_from'] == ['Deep Ocean']
    if BAKE in items: assert items[BAKE]['made_for_kids'] is True


def test_plays_count_and_the_youtube_history_bridges(bbc):
    s.refresh_catalogue(NOW)
    assert s.score(NOW) == dict(sources=0, suggested=0, added=0)                                          # nothing to go on yet
    with db.connect() as con:
        con.execute("INSERT INTO suggestions (channel_id, title, watches, score, topics) VALUES ('UCcrime', 'Crime channel', 40, 9.0, 'Society|Hobby')")
        con.execute("INSERT INTO suggestions (channel_id, title, watches, score, topics) VALUES ('UCfood', 'Food channel', 3, 1.0, 'Food')")
    w, bridge = s.sources()
    assert w == {} and bridge == {'documentaries': 9.0, 'food': 1.0}                                   # Hobby says too little to map
    s.score(NOW)
    items = {x['channel_id']: x for x in history.suggestions(order='suggested')['items'] if x['platform'] == 'iplayer'}
    assert items and all(x['suggested_from'] == ['your YouTube history'] for x in items.values())
    catalogue.add(f'https://www.bbc.co.uk/iplayer/episode/m0000001')                                    # an episode of Deep Ocean, played 4 times but not followed: 0.5 + 0.25 log2(4)
    for _ in range(4): cache.record_play('m0000001', NOW)
    w, _ = s.sources()
    assert w == {OCEAN: 1.0}
    catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{OCEAN}')
    assert s.sources()[0] == {OCEAN: 2.0}
    catalogue.add('https://www.bbc.co.uk/iplayer/categories/films/featured')                              # a category channel is no source
    assert s.sources()[0] == {OCEAN: 2.0}


def test_a_suggestion_no_longer_found_goes_unless_kept_and_youtube_s_count_leaves_it_alone(bbc):
    catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{OCEAN}'); s.run(NOW)
    history.dismiss(ICE, now=NOW)
    with db.connect() as con: con.execute("UPDATE suggestions SET pasted = ? WHERE channel_id = ?", (NOW, REEF))
    related.aggregate()                                                                                  # YouTube's count does not touch iPlayer's
    with db.connect() as con: assert con.execute("SELECT suggested_by FROM suggestions WHERE channel_id = ?", (REEF,)).fetchone()[0] >= 1
    catalogue.remove(OCEAN); s.score(NOW)
    with db.connect() as con:
        left = {r[0]: (r[1], r[2]) for r in con.execute("SELECT channel_id, suggested_by, related_score FROM suggestions WHERE platform = 'iplayer'")}
        assert con.execute('SELECT COUNT(*) FROM bbc_similar').fetchone()[0] == 0
    assert left == {REEF: (0, 0.0), ICE: (0, 0.0)}                                                        # pasted and dismissed stay; the rest went
    assert s.pointers([]) == {}


def test_tubes_related_runs_iplayer_too(bbc, capsys, monkeypatch):
    from tubes import cli
    catalogue.add(f'https://www.bbc.co.uk/iplayer/episodes/{OCEAN}')
    assert cli.main(['related']) == 0
    out = capsys.readouterr().out
    assert 'iPlayer catalogue read: 6 programmes, 6 new, 0 dropped;' in out and 'programme(s) suggested from 1 source(s)' in out
    assert cli.main(['related']) == 0 and 'iPlayer catalogue read at ' in capsys.readouterr().out
    bbc.close()
    assert cli.main(['related', '--all']) == 0 and "iPlayer's catalogue could not be read: iPlayer could not be reached" in capsys.readouterr().out


def test_suggestions_are_taken_in_turn_from_each_source():
    found = {'a1': (0.9, [(0.9, 'A')], 1), 'a2': (0.8, [(0.8, 'A')], 1), 'a3': (0.7, [(0.7, 'A')], 1), 'b1': (0.5, [(0.5, 'B'), (0.4, 'A')], 2)}
    assert [pid for pid, _ in s.spread(found, 3)] == ['a1', 'b1', 'a2'] and s.spread({}, 3) == []
