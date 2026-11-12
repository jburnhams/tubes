"""history.py: reading Takeout watch histories, the suggestions made from them (score, sittings, groups), YouTube's topics, and the list's filters."""
import datetime, json
import pytest
from takeout import as_html, as_json, chan, watch
from tubes import catalogue, db, history, youtube

A, B, C, D, E, F, G = (chan(x) for x in 'abcdefg')
NOW = '2026-11-01T00:00:00+00:00'


def at(day, minute=0, hour=10):
    return (datetime.datetime(2026, 1, 1, hour, tzinfo=datetime.timezone.utc) + datetime.timedelta(days=day, minutes=minute)).isoformat(timespec='seconds')


def sittings_of(groups, days):
    """Watches in sittings: on each day, one sitting per group of channels, its channels taking turns a few minutes apart."""
    out, n = [], 0
    for day in days:
        for g, members in enumerate(groups):
            for i, c in enumerate(members):
                n += 1; out.append(watch(at(day, minute=5 * i, hour=8 + 4 * g), f'v{n:010d}', f'Video {n}', c, f'Channel {c[2]}'))
    return out


def two_crowds():
    """A, B and C are watched together, D, E and F together (never in the same sitting as the first three); G once."""
    return sittings_of([[A, B, C], [D, E, F]], range(0, 60, 10)) + [watch(at(100), 'vg000000001', 'Lone', G, 'Channel g')]


def load(watches, source='one', lookup=False, now=NOW):
    return history.import_text(as_json(watches), source, now=now, lookup=lookup)


# Reading Takeout.

@pytest.mark.parametrize('text, expected', [
    ('9 Oct 2026, 21:57:37 BST', '2026-10-09T20:57:37+00:00'),
    ('Oct 9, 2026, 9:57:37 AM', '2026-10-09T09:57:37+00:00'),
    ('1 Sept 2025, 07:00:00 BST', '2025-09-01T06:00:00+00:00'),
    ('12 Dec 2024, 07:00:00 GMT', '2024-12-12T07:00:00+00:00'),
    ('Oct 9, 2026, 9:57:37 PM EDT', '2026-10-10T01:57:37+00:00'),
    ('3 Mar 2026, 10:00:00 UTC+05:30', '2026-03-03T04:30:00+00:00'),
    ('3 Mar 2026, 10:00:00 GMT-3', '2026-03-03T13:00:00+00:00'),
    ('3 Mar 2026, 10:00:00 XYZT', '2026-03-03T10:00:00+00:00'),           # a zone it does not know counts as UTC
    ('3 Mar 2026, 10:00:00', '2026-03-03T10:00:00+00:00'),
    ('yesterday', None), ('', None), (None, None),
])
def test_when_reads_takeout_times(text, expected):
    assert history.when(text) == expected


def test_json_and_html_read_alike_leaving_out_ads_and_other_activity():
    ws = [watch('2026-05-01T10:00:00Z', 'aaaaaaaaaaa', 'First & best', A, 'Channel <a>'),
          watch('2026-01-02T09:00:00Z', 'bbbbbbbbbbb', 'Gone', None),
          watch('2026-05-03T10:00:00Z', 'ccccccccccc', 'An ad', B, 'Advertiser', ad=True),
          watch('2026-05-04T10:00:00Z', 'ddddddddddd', 'A search', A, 'Channel <a>', action='Searched for')]
    expected = [dict(at='2026-05-01T10:00:00+00:00', video_id='aaaaaaaaaaa', title='First & best', channel_id=A, channel_title='Channel <a>'),
                dict(at='2026-01-02T09:00:00+00:00', video_id='bbbbbbbbbbb', title=None, channel_id=None, channel_title=None)]
    assert history.parse(as_json(ws)) == expected
    assert history.parse('﻿' + as_html(ws)) == expected


def test_parse_skips_what_it_cannot_use_and_refuses_what_is_not_a_history():
    odd = [dict(title='Watched x', titleUrl='https://www.youtube.com/watch?v=aaaaaaaaaaa', time='never'),            # no time
           dict(title='Watched x', titleUrl='https://www.youtube.com/post/abc', time='2026-01-01T00:00:00Z'),       # not a video
           'junk', dict(title='Visited YouTube Music')]
    assert history.parse(json.dumps(odd)) == []
    cell = '<div class="outer-cell"><div class="mdl-typography--body-1">Watched no link<br>1 Jan 2026, 10:00:00 GMT<br></div></div><div class="outer-cell">nothing</div>'
    assert history.parse(cell) == []
    with pytest.raises(history.ImportProblem, match='cannot be read'): history.parse('[{"broken"')
    with pytest.raises(history.ImportProblem, match='list of watches'): history.parse_json({})
    with pytest.raises(history.ImportProblem, match='not a Google Takeout watch history'): history.parse('<html>my page</html>')


def test_import_replaces_a_source_and_reports_it(tmp_path):
    r = load(two_crowds())
    assert (r['source'], r['watches'], r['first'], r['last']) == ('one', 37, at(0, hour=8), at(100))
    assert r['refresh'] == dict(channels=7, groups=2, grouped=6, looked_up=0, missing=0, error=None)
    f = tmp_path / 'watch-history.html'; f.write_text(as_html(two_crowds()[:3]), encoding='utf8')
    assert history.import_file(str(f), 'two', now=NOW, lookup=False)['watches'] == 3
    load(two_crowds()[:6])                                                      # importing a source again replaces it
    assert [(s['source'], s['watches'], s['channels']) for s in history.sources()] == [('one', 6, 6), ('two', 3, 3)]
    with pytest.raises(history.ImportProblem, match='Name the history'): history.import_text(as_json(two_crowds()), ' ')
    with pytest.raises(history.ImportProblem, match='no watches'): history.import_text('[]', 'one')
    assert history.remove_source('two', now=NOW)['refresh']['channels'] == 6
    with pytest.raises(history.NotFound, match='no history called two'): history.remove_source('two')


# Score, sittings, groups.

def test_score_halves_a_watch_every_half_life():
    now = '2026-01-01T00:00:00+00:00'
    assert history.score([now, now], now) == 2
    assert history.score(['2025-01-01T00:00:00+00:00'], now) == pytest.approx(0.5, rel=1e-3)
    assert history.score(['2027-01-01T00:00:00+00:00'], now) == 1           # a watch after `now` counts as new


def test_sittings_split_on_a_gap_or_another_source():
    rows = [('one', at(0), A), ('one', at(0, 20), B), ('one', at(0, 55), C), ('two', at(0, 56), D), ('two', at(0, 57), A)]
    assert history.sittings(rows) == [{A, B}, {C}, {D, A}]
    assert history.sittings([]) == []


def test_communities_and_groups_that_keep_their_ids():
    sits = [{A, B, C}] * 5 + [{D, E, F}] * 5 + [{A, D}]
    counts = dict.fromkeys([A, B, C, D, E, F], 6) | {G: 1}
    assert history.communities(sits, counts) == [{A, B, C}, {D, E, F}]
    assert history.communities([{A, B}], dict(a=1)) == []                       # nothing shares two sittings
    assert history.match_groups([{A, B, C}, {D, E}, {F, G}], {A: 7, B: 7, D: 3, E: 7}) == [7, 3, 8]
    assert history.match_groups([{A}], {}, taken_ids=[4]) == [5]


def test_refresh_groups_names_and_keeps_choices_across_imports():
    load(two_crowds())
    s = history.summary()
    g1, g2 = s['groups']
    assert sorted(g['name'] for g in s['groups']) == ['Channel c, Channel b, Channel a', 'Channel f, Channel e, Channel d'] and (g1['channels'], s['ungrouped']) == (3, 1)   # best score first
    abc = next(g for g in s['groups'] if 'Channel a' in g['name'])
    assert g2['channels'] == 3
    assert history.rename_group(abc['id'], '  Workshop  ') == dict(id=abc['id'], name='Workshop', named=True)
    history.dismiss(E, now='2026-11-02T00:00:00+00:00')
    load(two_crowds() + sittings_of([[A, B, C]], [70]))                           # a newer export: same groups, the name and the dismissal kept
    s = history.summary()
    assert [g['name'] for g in s['groups'] if g['id'] == abc['id']] == ['Workshop'] and (s['open'], s['dismissed']) == (6, 1)
    assert history.suggestion(E)['dismissed'] == '2026-11-02T00:00:00+00:00'
    assert history.rename_group(abc['id'], '') == dict(id=abc['id'], name='Workshop', named=False)
    history.refresh(NOW, lookup=False)
    assert [g['name'] for g in history.summary()['groups'] if g['id'] == abc['id']] == ['Channel c, Channel b, Channel a']   # unnamed: made up again
    with pytest.raises(history.NotFound, match='no group 99'): history.rename_group(99, 'x')
    with pytest.raises(ValueError, match='at most 80'): history.rename_group(abc['id'], 'x' * 81)
    load([watch(at(1), 'only0000001', 'Only', G, 'Channel g')])                  # channels no longer in any history leave
    assert [i['channel_id'] for i in history.suggestions()['items']] == [G] and history.summary()['groups'] == []


# YouTube's topics.

def test_refresh_asks_youtube_about_channels_it_has_not_lately(fake_youtube):
    fake_youtube.channel(A, 'Channel A', handle='@a', topics=['Music', 'Lifestyle_(sociology)'], kids=False).channel(B, 'Channel B', kids=True)
    for c in (C, D, E, F): fake_youtube.channel(c, f'Channel {c[2]}', topics=['Hobby'])
    r = load(two_crowds(), lookup=True)['refresh']
    assert (r['looked_up'], r['missing'], r['error']) == (6, 0, None)               # G was watched once: not asked about
    a = history.suggestion(A)
    assert (a['title'], a['handle'], a['topics'], a['made_for_kids'], a['subscribers'], a['total_videos'], a['thumbnail']) == ('Channel A', '@a', ['Lifestyle', 'Music'], False, 50, 0, f'https://img.test/{A}/l.jpg')
    assert history.suggestion(C)['made_for_kids'] is None and history.suggestion(B)['made_for_kids'] is True
    fake_youtube.calls.clear()
    assert history.refresh(NOW)['looked_up'] == 0 and fake_youtube.calls == []        # asked lately: not again
    later = (datetime.datetime.fromisoformat(NOW) + datetime.timedelta(days=history.LOOKUP_DAYS + 1)).isoformat()
    del fake_youtube.channels[F]
    assert history.look_up(later, limit=10) == dict(looked_up=6, missing=1)
    assert history.suggestion(F)['missing'] is True and F not in [i['channel_id'] for i in history.suggestions()['items']]
    fake_youtube.quota_left = 0
    assert 'quota' in history.refresh((datetime.datetime.fromisoformat(later) + datetime.timedelta(days=60)).isoformat())['error']


def test_youtube_topic_names():
    assert [youtube.topic_name(u) for u in ('https://en.wikipedia.org/wiki/Lifestyle_(sociology)', 'https://en.wikipedia.org/wiki/Hip_hop_music/', 'https://en.wikipedia.org/wiki/Caf%C3%A9', '', None)] == ['Lifestyle', 'Hip hop music', 'Café', None, None]


# The list.

def test_the_list_filters_and_leaves_out_what_is_followed(fake_youtube):
    fake_youtube.channel(A, 'Channel A', topics=['Music'], kids=True).channel(B, 'Channel B', topics=['Music']).channel(D, 'Channel D', videos=2)
    for c in (C, E, F): fake_youtube.channel(c, f'Channel {c[2]}')
    load(two_crowds(), lookup=True)
    ids = lambda **kw: [i['channel_id'] for i in history.suggestions(**kw)['items']]
    assert len(ids()) == 7 and history.suggestions(limit=2)['total'] == 7
    abc = next(g['id'] for g in history.summary()['groups'] if 'Channel a' in g['name'])
    assert sorted(ids(group=str(abc))) == [A, B, C] and ids(group='none') == [G]
    assert sorted(ids(topic='Music')) == [A, B] and ids(kids=True) == [A] and A not in ids(kids=False) and len(ids(kids=False)) == 6
    assert ids(q='channel g') == [G] and ids(q='100%_') == []
    with pytest.raises(history.NotFound, match='no group x'): history.suggestions(group='x')

    catalogue.add(D)                                                                 # followed: accepted, so off the list
    catalogue.add_videos([f'{D[2:6]}0000000'])
    assert D not in ids()
    with db.connect() as con: con.execute('UPDATE channels SET follow = ? WHERE id = ?', (False, D))
    assert history.suggestion(D)['in_library'] is True and D in ids()               # only there for a video: still a suggestion
    history.dismiss(B)
    assert ids(dismissed=True) == [B] and B not in ids()
    assert history.dismiss(B, False)['dismissed'] is None and B in ids()
    with pytest.raises(history.NotFound, match='no suggestion UCzz'): history.dismiss('UCzz')
    with pytest.raises(history.NotFound, match='no suggestion UCzz'): history.suggestion('UCzz')
    s = history.summary()
    assert (s['open'], s['dismissed'], s['followed'], s['kids'], s['configured']) == (7, 0, 0, 1, True)
    assert s['topics'] == [dict(name='Music', channels=2)] and s['refreshed'] == NOW and [x['source'] for x in s['sources']] == ['one']


def test_watched_videos_newest_first():
    load([watch(at(1), 'old00000001', 'Old', A, 'Channel a'), watch(at(3), 'new00000001', 'New', A, 'Channel a'), watch(at(2), 'old00000001', 'Old', A, 'Channel a'), watch(at(4), 'other000001', 'Other', B, 'Channel b')])
    assert history.watched_videos(A) == ['new00000001', 'old00000001']


# A history kept in another database.

def history_db(tmp_path, rows):
    """A SQLite database with a `kept` table as a history database would have it; returns its URL."""
    import sqlite3
    path = tmp_path / 'kept.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE kept (account TEXT, at TEXT, video_id TEXT, title TEXT, channel_id TEXT, channel_name TEXT)')
        con.executemany('INSERT INTO kept VALUES (?, ?, ?, ?, ?, ?)', rows)
    return f'sqlite:///{path}'


def test_sync_database_copies_each_account_in_and_leaves_imports_alone(tmp_path, monkeypatch):
    load([watch(at(1), 'imported001', 'Imported', A, 'Channel a')], source='takeout')
    url = history_db(tmp_path, [('main', '2026-01-01T10:00:00Z', 'v0000000001', 'One', B, 'Channel b'), ('main', '2026-01-02 10:00:00', 'v0000000002', 'Two', None, 'ignored'),
                                ('second', '2026-01-03T10:00:00+01:00', 'v0000000003', 'Three', B, 'Channel b'), ('second', 'not a time', 'v0000000004', 'Bad', B, 'Channel b'), (None, '2026-01-01T00:00:00Z', 'v0000000005', 'No account', B, 'x')])
    assert history.database_configured() is False
    with pytest.raises(history.ImportProblem, match='No history database is set'): history.sync_database()
    monkeypatch.setenv('TUBES_HISTORY_URL', url); monkeypatch.setenv('TUBES_HISTORY_TABLE', 'kept')
    assert history.database_configured() is True
    r = history.sync_database(now=NOW, lookup=False)
    assert r['sources'] == dict(main=2, second=1) and r['refresh']['channels'] == 2
    with db.connect() as con: rows = [tuple(x) for x in con.execute('SELECT source, at, video_id, channel_id, channel_title FROM watches ORDER BY at, source')]
    assert rows == [('main', '2026-01-01T10:00:00+00:00', 'v0000000001', B, 'Channel b'), ('main', '2026-01-02T10:00:00+00:00', 'v0000000002', None, None),
                    ('takeout', at(1), 'imported001', A, 'Channel a'), ('second', '2026-01-03T09:00:00+00:00', 'v0000000003', B, 'Channel b')]
    with pytest.raises(history.ImportProblem, match='not a table name'): history.sync_database(table='kept; DROP TABLE x')
    with pytest.raises(history.ImportProblem, match='could not be read'): history.sync_database(table='missing.kept')


def test_utc_times():
    assert history._utc(datetime.datetime(2026, 1, 1, 10)) == '2026-01-01T10:00:00+00:00'
    assert history._utc(datetime.datetime(2026, 1, 1, 10, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))) == '2026-01-01T08:00:00+00:00'
    assert history._utc('soon') is None


# What was watched when.

def test_stats_count_rank_and_bucket():
    ws = [watch(at(d), f'v{d % 3:010d}', f'Video {d % 3}', A if d % 3 else B, f'Channel {"a" if d % 3 else "b"}') for d in range(0, 200, 5)]
    load(ws + [watch(at(7), 'gone0000001', 'Gone', None)], source='one')
    load([watch(at(3), 'w0000000001', 'Other', C, 'Channel c')], source='two')
    s = history.stats()
    assert (s['watches'], s['videos'], s['channels'], s['first'], s['by']) == (42, 5, 3, at(0), 'month')
    assert s['periods'][0] == dict(period='2026-01', watches=9) and sum(p['watches'] for p in s['periods']) == 42
    assert [(c['channel_id'], c['watches'], c['videos'], c['followed']) for c in s['channels_top']] == [(A, 26, 2, False), (B, 14, 1, False), (C, 1, 1, False)]
    assert [(v['video_id'], v['watches'], v['channel_id']) for v in s['videos_top'][:1]] == [('v0000000000', 14, B)] and sorted(v['watches'] for v in s['videos_top']) == [1, 1, 13, 13, 14]
    d = history.stats(at(0), at(30), 'one', top=1)
    assert (d['by'], d['watches'], len(d['channels_top']), len(d['videos_top'])) == ('day', 7, 1, 1) and d['periods'][0] == dict(period=at(0)[:10], watches=1)
    e = history.stats(at(500))
    assert (e['watches'], e['first'], e['periods'], e['channels_top'], e['by']) == (0, None, [], [], 'day')


def test_overview_brings_library_history_and_suggestion_together(fake_youtube):
    from fake_youtube import vid
    fake_youtube.channel(A, 'Channel A', topics=['Music'], videos=3)
    load(two_crowds() + [watch(at(70), vid(A, 0), 'Upload 0', A, 'Channel a')], source='one', lookup=True)
    load([watch(at(80), vid(A, 0), 'Upload 0', A, 'Channel a')], source='two')
    o = history.overview(A)
    assert (o['title'], o['library'], o['suggestion']['topics'], o['group']['named'], o['configured']) == ('Channel a', None, ['Music'], False, True)
    h = o['history']
    assert (h['watches'], h['first'], h['sources'], [p['period'] for p in h['periods']]) == (8, at(0, hour=8), [dict(source='one', watches=7), dict(source='two', watches=1)], ['2026-01', '2026-02', '2026-03'])
    assert h['videos_top'][0] == dict(video_id=vid(A, 0), title='Upload 0', watches=2, last=at(80), in_library=False)
    catalogue.add_videos([vid(A, 0)])
    o = history.overview(A)
    assert o['library']['follow'] is False and o['history']['videos_top'][0]['in_library'] is True and o['thumbnail'] == f'https://img.test/{A}/l.jpg'
    fake_youtube.channel(D[:-1] + 'x', 'Only in the library')
    catalogue.add(D[:-1] + 'x')
    assert history.overview(D[:-1] + 'x')['history']['watches'] == 0 and history.overview(D[:-1] + 'x')['suggestion'] is None and history.overview(D[:-1] + 'x')['group'] is None
    with pytest.raises(history.NotFound, match='Nothing is known of channel UCnone'): history.overview('UCnone')
