"""paste.py: a pasted list of links, handles and names read into suggestions, from YouTube and iPlayer."""
import pytest
from fake_iplayer import ep_id
from fake_youtube import vid
from tubes import catalogue, db, history, paste, youtube

A, B, C = ('UC' + x * 22 for x in 'abc')
NOW = '2026-11-12T05:00:00+00:00'


@pytest.mark.parametrize('text, expected', [
    ('one\n\n  two  \none\n', ['one', 'two']),
    ('- @first\n* @second\n3. Third name\n4) fourth,\n• fifth', ['@first', '@second', 'Third name', 'fourth', 'fifth']),
    ('https://a.test/1 https://a.test/2\nwww.b.test @c', ['https://a.test/1', 'https://a.test/2', 'www.b.test', '@c']),
    ('Two words https://a.test/1', ['Two words https://a.test/1']),                     # a name with a link in it stays one entry
    ('', []), (None, []),
])
def test_lines(text, expected):
    assert paste.lines(text) == expected


def test_lines_stops_at_the_most_a_paste_takes():
    assert len(paste.lines('\n'.join(f'n{i}' for i in range(150)))) == paste.MAX_LINES


def test_links_handles_ids_and_videos_become_youtube_suggestions(fake_youtube):
    fake_youtube.channel(A, 'Workshop', handle='@workshop', topics=['Hobby']).channel(B, 'Garden', videos=2).channel(C, 'Canal')
    text = f'https://www.youtube.com/@workshop\n{B}\nhttps://youtu.be/{vid(B, 1)}\nhttps://www.youtube.com/channel/{C}\nhttps://www.youtube.com/@nobody\nhttps://example.test/x'
    r = paste.paste(text, now=NOW)
    assert [(f['input'], f['platform'], f['channel_id'], f['title']) for f in r['found']] == [('https://www.youtube.com/@workshop', 'youtube', A, 'Workshop'), (B, 'youtube', B, 'Garden'), (f'https://www.youtube.com/channel/{C}', 'youtube', C, 'Canal')]
    assert r['problems'] == [dict(input='https://www.youtube.com/@nobody', error='YouTube has no such channel or video.'), dict(input='https://example.test/x', error='That link is not to a YouTube channel or video.')]
    items = history.suggestions(pasted=True)['items']
    assert [i['channel_id'] for i in items] == [A, B, C]
    a = history.suggestion(A)
    assert (a['platform'], a['pasted'], a['watches'], a['topics'], a['handle'], a['link']) == ('youtube', NOW, 0, ['Hobby'], '@workshop', f'https://www.youtube.com/channel/{A}')
    assert history.summary()['pasted'] == 3


def test_iplayer_programme_and_episode_links_name_the_programme(fake_iplayer):
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=2).programme('b0000002', 'Night Garden')
    film = fake_iplayer.one_off('m0000099', 'A Film')
    r = paste.paste(f"https://www.bbc.co.uk/iplayer/episodes/b0000001\nhttps://www.bbc.co.uk/iplayer/episode/{ep_id('b0000001', 1)}\nhttps://www.bbc.co.uk/programmes/b0000002\n"
                    f"https://www.bbc.co.uk/iplayer/episode/{film}\nhttps://www.bbc.co.uk/iplayer/episodes/b0000009\nhttps://www.bbc.co.uk/iplayer/episode/m0000088\nhttps://www.bbc.co.uk/news", now=NOW)
    assert [(f['platform'], f['channel_id'], f['title']) for f in r['found']] == [('iplayer', 'b0000001', 'Harbour Lights'), ('iplayer', 'b0000002', 'Night Garden')]
    assert [p['error'] for p in r['problems']] == ['That is a one-off with no programme or category to follow; add it in Library instead.', 'iPlayer has no such programme.',
                                                  'iPlayer does not offer that episode (it may have expired).', 'That BBC link is not to an iPlayer programme, episode or category.']
    h = history.suggestion('b0000001')
    assert (h['platform'], h['link'], h['thumbnail'], h['total_videos']) == ('iplayer', 'https://www.bbc.co.uk/iplayer/episodes/b0000001', 'https://img.test/ic/480x480/b0000001.jpg', 2)
    assert history.look_up(NOW) == dict(looked_up=0, missing=0)              # YouTube is never asked about a programme


def test_names_are_looked_up_on_both_handle_first_then_a_search(fake_youtube, fake_iplayer):
    fake_youtube.channel(A, 'Harbour Lights', handle='@harbourlights').channel(B, 'Garden Birds Daily', handle='@gbd').channel(C, 'Something Else', handle='@gardenbirds')
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=1).programme('b0000003', 'Harbour Lights Revisited')
    r = paste.paste('Harbour Lights\ngarden birds\nNothing Like It', now=NOW)
    assert [(f['input'], f['platform'], f['channel_id']) for f in r['found']] == [('Harbour Lights', 'iplayer', 'b0000001'), ('Harbour Lights', 'youtube', A), ('garden birds', 'youtube', B)]
    assert r['problems'] == [dict(input='Nothing Like It', error='Neither YouTube nor iPlayer has a channel or programme by that name.')]
    assert fake_youtube.count('search') == 2                                   # "harbourlights" was a handle with that title; "@gardenbirds" was not, so searched


def test_name_searches_stop_at_the_limit_and_youtube_is_skipped_without_a_key(fake_youtube, fake_iplayer, monkeypatch):
    monkeypatch.setattr(paste, 'NAME_SEARCHES', 1)
    fake_youtube.channel(A, 'Alpha Things').channel(B, 'Beta Things')
    assert [f['channel_id'] for f in paste.paste('alpha things\nbeta things', now=NOW)['found']] == [A]
    monkeypatch.delenv('YOUTUBE_API_KEY')
    fake_iplayer.programme('b0000001', 'Alpha Things')
    r = paste.paste(f'alpha things\n{A}', now=NOW)
    assert [f['channel_id'] for f in r['found']] == ['b0000001'] and r['problems'] == [dict(input=A, error='YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.')]


def test_a_service_that_fails_is_said_per_line(fake_youtube):
    # iPlayer is unreachable (no fake_iplayer): a name still finds YouTube's; a programme link says why it could not be read.
    fake_youtube.channel(A, 'Workshop', handle='@workshop')
    r = paste.paste('Workshop\nhttps://www.bbc.co.uk/iplayer/episodes/b0000001', now=NOW)
    assert [f['channel_id'] for f in r['found']] == [A] and 'iPlayer could not be reached' in r['problems'][0]['error']
    fake_youtube.quota_left = 0
    r = paste.paste('Workshop', now=NOW)
    assert r['found'] == [] and 'iPlayer could not be reached' in r['problems'][0]['error']
    r = paste.paste('@workshop', now=NOW)
    assert 'quota' in r['problems'][0]['error']


def test_followed_ones_are_said_and_dismissed_ones_come_back(fake_youtube):
    fake_youtube.channel(A, 'Workshop', videos=1).channel(B, 'Garden')
    catalogue.add(A)
    paste.paste(B, now=NOW); history.dismiss(B)
    r = paste.paste(f'{A}\n{B}', now='2026-11-12T06:00:00+00:00')
    assert r['already'] == [dict(input=A, title='Workshop')] and [f['channel_id'] for f in r['found']] == [B]
    b = history.suggestion(B)
    assert (b['dismissed'], b['pasted']) == (None, '2026-11-12T06:00:00+00:00')
    with pytest.raises(ValueError, match='Paste at least one'): paste.paste(' \n ')


def test_pasted_ones_stay_through_a_regroup_and_a_related_count(fake_youtube):
    from tubes import related
    fake_youtube.channel(A, 'Workshop')
    paste.paste(A, now=NOW)
    history.refresh(NOW, lookup=False); related.aggregate()
    assert history.suggestion(A)['pasted'] == NOW
    with db.connect() as con: con.execute("UPDATE suggestions SET watches = 3 WHERE channel_id = ?", (A,))
    history.refresh(NOW, lookup=False)                                         # it left the (empty) history: kept, as it was pasted
    assert history.suggestion(A)['watches'] == 0


def test_youtube_search_channels(fake_youtube):
    fake_youtube.channel(A, 'Garden Birds').channel(B, 'Garden Birds Daily')
    assert youtube.search_channels('garden birds', n=5) == [A, B] and youtube.search_channels('nothing') == []


def test_iplayer_search_gives_the_followable_programme_once_and_leaves_out_one_offs(fake_iplayer):
    fake_iplayer.programme('b0000001', 'Harbour Lights', episodes=2)
    fake_iplayer.one_off('m0000099', 'Harbour Film')
    from tubes import iplayer
    assert iplayer.search('harbour') == [dict(id='b0000001', title='Harbour Lights', kind='programme', thumbnail='https://img.test/ic/480x480/b0000001.jpg')]
    del fake_iplayer.programmes['b0000001']                                     # only its episodes found: they name it
    assert [(x['id'], x['kind']) for x in iplayer.search('harbour')] == [('b0000001', 'episode')]


def test_a_film_or_a_category_link_suggests_the_category(fake_iplayer):
    film = fake_iplayer.one_off('p0000001', 'A Film', categories=('films',))
    r = paste.paste(f'https://www.bbc.co.uk/iplayer/episode/{film}/a-film\nhttps://www.bbc.co.uk/iplayer/browse/documentaries\nhttps://www.bbc.co.uk/iplayer/categories/nope/featured', now=NOW)
    assert [(f['platform'], f['channel_id'], f['title']) for f in r['found']] == [('iplayer', 'iplayer-films', 'Films'), ('iplayer', 'iplayer-documentaries', 'Documentaries')]
    assert [p['error'] for p in r['problems']] == ['iPlayer has no such category.']
    listed = history.suggestions(pasted=True)
    rows = listed['items'] if isinstance(listed, dict) else listed
    assert next(x for x in rows if x['channel_id'] == 'iplayer-films')['link'] == 'https://www.bbc.co.uk/iplayer/categories/films/featured'   # what Follow adds
    catalogue.add('https://www.bbc.co.uk/iplayer/categories/films/featured')                 # followed: a film pasted again is said to be followed
    assert [a['title'] for a in paste.paste(f'https://www.bbc.co.uk/iplayer/episode/{film}', now=NOW)['already']] == ['Films']
