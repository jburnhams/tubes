"""iplayer.py: reading links, BBC times and names, rows, and the catalogue and stream calls against the stand-in (tests/utils/fake_iplayer.py)."""
import urllib.request

import pytest
from fake_iplayer import ep_id
from tubes import iplayer

P = 'b0000001'


@pytest.mark.parametrize('text, expected', [
    ('https://www.bbc.co.uk/iplayer/episodes/b0000001/harbour-lights', ('programme', 'b0000001')),
    ('https://www.bbc.co.uk/iplayer/episodes/b0000001?seriesId=m0000002', ('programme', 'b0000001')),
    ('bbc.co.uk/iplayer/episode/m0000002/harbour-lights-series-1-1-chapter-1', ('episode', 'm0000002')),
    ('https://www.bbc.co.uk/programmes/p0000003', ('pid', 'p0000003')),
    ('https://www.youtube.com/watch?v=aaaaaaaaaaa', None),
    ('@workshop', None),
    ('aaaaaaaaaaa', None),
])
def test_parse(text, expected):
    assert iplayer.parse(text) == expected


def test_parse_refuses_a_bbc_link_to_no_programme():
    with pytest.raises(ValueError, match='not to an iPlayer programme, episode or category'): iplayer.parse('https://www.bbc.co.uk/news')
    with pytest.raises(ValueError, match='not to an iPlayer'): iplayer.parse('https://www.bbc.co.uk/iplayer/episode/NOT-A-PID')


def test_times_durations_and_images():
    assert iplayer.stamp('2026-11-11T19:30:00.000Z') == '2026-11-11T19:30:00+00:00'
    assert iplayer.stamp('2026-11-11T19:30:00') == '2026-11-11T19:30:00+00:00'
    assert iplayer.stamp('2026-11-11T20:30:00+01:00') == '2026-11-11T19:30:00+00:00'
    assert iplayer.stamp('soon') is None and iplayer.stamp(None) is None
    assert iplayer.seconds('PT29M0.117333S') == 1740.117 and iplayer.seconds('PT1H30M') == 5400 and iplayer.seconds('PT6S') == 6
    assert iplayer.seconds('PT') is None and iplayer.seconds('29 mins') is None and iplayer.seconds(None) is None
    assert iplayer.image('https://img.test/ic/{recipe}/x.jpg') == 'https://img.test/ic/1280x720/x.jpg' and iplayer.image(None) is None


def test_the_version_to_play_is_the_original():
    ad, signed, orig, edit = (dict(id=k, kind=k) for k in ('audio-described', 'signed', 'original', 'editorial'))
    assert iplayer.version(dict(versions=[ad, edit, signed, orig]))['id'] == 'original'
    assert iplayer.version(dict(versions=[ad, edit]))['id'] == 'editorial'
    assert iplayer.version(dict(versions=[ad, dict(id='x', kind='technical-replacement')]))['id'] == 'x'
    assert iplayer.version(dict(versions=[signed]))['id'] == 'signed'                    # the only one there is
    assert iplayer.version(dict(versions=[dict(kind='original')])) is None and iplayer.version({}) is None


@pytest.mark.parametrize('episode, expected', [
    (dict(id='m1', subtitle='Series 1: 2. The Deep', parent_position=2), ('The Deep', 'Series 1', 2)),
    (dict(id='m1', subtitle='Series 3: 4. Night', parent_position=None), ('Night', 'Series 3', 4)),
    (dict(id='m1', subtitle='Christmas Special: Part One'), ('Part One', 'Christmas Special', None)),
    (dict(id='m1', subtitle='11/11/2026', parent_position=7433), ('11/11/2026', None, 7433)),
    (dict(id='m1', subtitle='', original_title='A Film', title='A Film'), ('A Film', None, None)),
    (dict(id='m1', title='Brand'), ('Brand', None, None)),
    (dict(id='m1'), ('m1', None, None)),
    (dict(id='m1', subtitle='Series 1:', parent_position='x'), ('Series 1:', None, None)),
])
def test_names(episode, expected):
    assert iplayer.names(episode) == expected


def test_rows(fake_iplayer):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=2)
    c = iplayer.channel_row(iplayer.programme(P), 'now')
    assert c == dict(id=P, platform='iplayer', title='Harbour Lights', handle=None, thumbnail=f'https://img.test/ic/480x480/{P}.jpg', description='All about Harbour Lights',
                     published=None, country='GB', language='en', subscribers=None, total_videos=2, views=None, uploads=None, added='now')
    e = ep_id(P, 2)
    v = iplayer.video_row(iplayer.episode(e), 'now')
    assert v == dict(id=e, platform='iplayer', channel_id=P, title='Chapter 2', published='2026-01-02T19:30:00+00:00', duration=6.0, thumbnail=f'https://img.test/ic/1280x720/{e}.jpg',
                     views=None, description='Chapter 2, told', likes=None, comments=None, definition='hd', live=None, expires='2099-01-01T00:00:00+00:00', series='Series 1', episode=2,
                     language='en', captions=None, regions_allowed='GB', regions_blocked=None, added='now')
    film = iplayer.video_row(iplayer.episode(fake_iplayer.one_off('p0000009', 'A Film')), 'now')
    assert (film['channel_id'], film['title'], film['definition'], film['duration'], film['published']) == ('bbc_two', 'A Film', 'sd', 5400, 'now')
    assert iplayer.network_row(fake_iplayer.episodes['p0000009'], 'now')['title'] == 'BBC Two'
    assert iplayer.network_row(dict(id='x'), 'now')['id'] == 'bbc' and iplayer.channel_of(dict(id='x', tleo_id='x')) == 'bbc'
    bare = iplayer.video_row(dict(id='m9', versions=[]), 'now')
    assert (bare['definition'], bare['expires'], bare['duration'], bare['published']) == (None, None, None, 'now')


def test_catalogue_calls(fake_iplayer, monkeypatch):
    fake_iplayer.programme(P, 'Harbour Lights', episodes=5)
    assert iplayer.programme('b0000099') is None and iplayer.episode('m0000099') is None
    assert iplayer.programme(ep_id(P, 1)) is None                                         # an episode's id is no programme
    monkeypatch.setattr(iplayer, 'PAGE', 2)
    pages = [iplayer.episodes_page(P, n) for n in (1, 2, 3, 4)]
    assert [([e['id'] for e in eps], more) for eps, more in pages] == [([ep_id(P, 5), ep_id(P, 4)], True), ([ep_id(P, 3), ep_id(P, 2)], True), ([ep_id(P, 1)], False), ([], False)]
    assert iplayer.episode_url('m0000002') == 'https://www.bbc.co.uk/iplayer/episode/m0000002'


def test_call_failures(fake_iplayer, monkeypatch):
    with pytest.raises(iplayer.IplayerError, match=r'refused the request \(404\)'): iplayer.call('nowhere')
    monkeypatch.setenv('TUBES_IPLAYER_API', 'http://127.0.0.1:9/ibl/v1')
    with pytest.raises(iplayer.IplayerError, match='could not be reached'): iplayer.call('programmes/x')
    monkeypatch.setenv('TUBES_IPLAYER_API', fake_iplayer.ibl.replace('/ibl/v1', '/hls/x'))
    with pytest.raises(iplayer.IplayerError, match='did not answer with JSON'): iplayer.call('master.m3u8')


def test_mediaselector(fake_iplayer, monkeypatch):
    e = fake_iplayer.episode(fake_iplayer.programme(P, 'Harbour Lights') and P, 1)
    vpid = 'v' + e[1:]
    assert iplayer.mediaselector(vpid) == [f'{fake_iplayer.ms.replace("/ms", "")}/hls/{vpid}/master.m3u8?at=token']
    with pytest.raises(iplayer.IplayerError, match='has no stream of this episode'): iplayer.mediaselector('v0000099')
    fake_iplayer.region = 'geolocation'
    with pytest.raises(iplayer.IplayerError, match='only plays in the UK'): iplayer.mediaselector(vpid)
    fake_iplayer.region = 'notavailable'
    with pytest.raises(iplayer.IplayerError, match=r'would not play this episode \(notavailable\)'): iplayer.mediaselector(vpid)
    fake_iplayer.region = None
    monkeypatch.setattr(iplayer, '_get', lambda url, **kw: b'{"media": [{"kind": "video", "connection": [{"transferFormat": "dash", "href": "x"}]}]}')
    with pytest.raises(iplayer.IplayerError, match='no HLS stream'): iplayer.mediaselector(vpid)
    monkeypatch.setattr(iplayer, '_get', lambda url, **kw: b'<html>')
    with pytest.raises(iplayer.IplayerError, match='did not answer with JSON'): iplayer.mediaselector(vpid)


def test_an_error_body_that_cannot_be_read_is_a_refusal(monkeypatch):
    import urllib.error

    class Broken(urllib.error.HTTPError):
        def read(self): raise OSError('reset')
    def refuse(req, timeout): raise Broken('http://x', 403, 'Forbidden', {}, None)
    monkeypatch.setattr(urllib.request, 'urlopen', refuse)
    with pytest.raises(iplayer.IplayerError, match=r'refused the request \(403\)'): iplayer._get('http://x', error_body=True)


def test_variants_and_the_1080p_address():
    text = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=5198000,CODECS="mp4a.40.2,avc1.640020",RESOLUTION=1280x720,FRAME-RATE=50\nv-audio=128000-video=5070000.m3u8\n' \
           '#EXT-X-STREAM-INF:BANDWIDTH=96000,CODECS="mp4a.40.5"\nhttps://cdn.test/audio.m3u8\n\n'
    assert iplayer.variants('https://cdn.test/a/master.m3u8?at=t', text) == [
        dict(url='https://cdn.test/a/v-audio=128000-video=5070000.m3u8', height=720, fps=50.0, bandwidth=5198000, codecs='mp4a.40.2,avc1.640020'),
        dict(url='https://cdn.test/audio.m3u8', height=0, fps=0.0, bandwidth=96000, codecs='mp4a.40.5')]
    assert iplayer.fhd_url('https://cdn.test/a/v-audio=128000-video=5070000.m3u8') == 'https://cdn.test/a/v-audio=128000-video=12000000.m3u8'
    assert iplayer.fhd_url('https://cdn.test/a/v.m3u8') is None


def test_stream_prefers_1080p50_then_the_best_listed(fake_iplayer):
    fake_iplayer.programme(P, 'Harbour Lights'); e = fake_iplayer.episode(P, 1)
    s = iplayer.stream(e)
    assert (s['height'], s['fps'], s['label']) == (1080, 50, '1080p50 H.264 + AAC') and s['url'].endswith('-video=12000000.m3u8')
    fake_iplayer.fhd = False
    s = iplayer.stream(e)
    assert (s['height'], s['label']) == (720, '720p50 H.264 + AAC') and s['url'].endswith('-video=5070000.m3u8')
    fake_iplayer.fhd = True
    assert iplayer.stream(e, max_height=720)['label'] == '720p50 H.264 + AAC'
    assert iplayer.stream(e, max_height=540)['label'] == '540p50 H.264 + AAC'
    with pytest.raises(iplayer.IplayerError, match='no stream at or under 200p'): iplayer.stream(e, max_height=200)
    sd = fake_iplayer.episode(P, 2, hd=False)
    assert iplayer.stream(sd)['label'] == '720p50 H.264 + AAC'                             # not HD: no 1080p is asked for


def test_stream_refusals(fake_iplayer, monkeypatch):
    fake_iplayer.programme(P, 'Harbour Lights'); e = fake_iplayer.episode(P, 1)
    with pytest.raises(iplayer.IplayerError, match='no longer offers'): iplayer.stream('m0000099')
    bare = fake_iplayer.episode(P, 2, versions=[])
    with pytest.raises(iplayer.IplayerError, match='no playable version'): iplayer.stream(bare)
    monkeypatch.setattr(iplayer, 'mediaselector', lambda vpid: [fake_iplayer.ms + '/nothing.m3u8'])
    with pytest.raises(iplayer.IplayerError, match=r'refused the request \(404\)'): iplayer.stream(e)


def test_a_1080p_playlist_that_lists_no_segments_is_not_taken(monkeypatch):
    monkeypatch.setattr(iplayer, '_get', lambda url, **kw: b'<html>sorry</html>')
    assert iplayer._answers('https://cdn.test/x-video=12000000.m3u8') is False
    monkeypatch.setattr(iplayer, '_get', lambda url, **kw: b'#EXTM3U\n#EXTINF:8,\nx-video=12000000-1.ts\n')
    assert iplayer._answers('https://cdn.test/x-video=12000000.m3u8') is True


def test_reachable(fake_iplayer, monkeypatch):
    assert iplayer.reachable() == (True, None)
    fake_iplayer.region = 'geolocation'
    assert iplayer.reachable() == (False, 'iPlayer only plays in the UK, and this server is not seen as in the UK.')
    monkeypatch.setenv('TUBES_MEDIASELECTOR', 'http://127.0.0.1:9')
    here, why = iplayer.reachable()
    assert here is False and 'could not be reached' in why
    monkeypatch.setattr(iplayer, 'mediaselector', lambda vpid: ['x'])
    assert iplayer.reachable() == (True, None)


def test_categories(fake_iplayer, monkeypatch):
    assert iplayer.parse('https://www.bbc.co.uk/iplayer/categories/films/featured') == ('category', 'films')
    assert iplayer.parse('https://www.bbc.co.uk/iplayer/browse/documentaries') == ('category', 'documentaries')
    with pytest.raises(ValueError, match='programme, episode or category'): iplayer.parse('https://www.bbc.co.uk/iplayer/categories/NOPE')
    assert iplayer.category('films') == dict(id='films', title='Films', type='category', kind='genre') and iplayer.category('nope') is None
    row = iplayer.category_row(dict(id='films', title='Films'), 'now')
    assert (row['id'], row['title'], row['platform'], row['description']) == ('iplayer-films', 'Films', 'iplayer', "Every one-off in iPlayer's Films, as iPlayer offers them.")
    assert iplayer.category_row(dict(id='x'), 'now')['title'] == 'x'
    assert iplayer.category_id('iplayer-films') == 'films' and iplayer.category_id('b0000001') is None and iplayer.category_id(None) is None
    assert iplayer.programme_url('iplayer-films') == 'https://www.bbc.co.uk/iplayer/categories/films/featured'
    fake_iplayer.programme(P, 'Harbour Lights', episodes=1); fake_iplayer.categories['films'][1].append(P)           # a series filed under Films
    for n in range(3): fake_iplayer.one_off(f'p000000{n}', f'Film {n}', categories=('films',))
    monkeypatch.setattr(iplayer, 'PAGE', 2)
    (a, more, n), (b, more2, n2) = iplayer.category_page('films', 1), iplayer.category_page('films', 2)
    assert [e['id'] for e in a] == ['p0000002', 'p0000001'] and (more, n) == (True, 2)
    assert [e['id'] for e in b] == ['p0000000'] and (more2, n2) == (False, 2)                       # the series it also lists is left out
    assert iplayer.category_page('films', 3) == ([], False, 0)


def test_a_film_is_filed_under_films_and_another_one_off_under_its_network(fake_iplayer):
    film = iplayer.episode(fake_iplayer.one_off('p0000001', 'A Film', categories=('films',)))
    doc = iplayer.episode(fake_iplayer.one_off('p0000002', 'A Documentary', categories=('documentaries',)))
    assert iplayer.channel_of(film) == 'iplayer-films' and iplayer.channel_of(doc) == 'bbc_two'
