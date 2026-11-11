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
