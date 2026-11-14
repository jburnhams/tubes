"""metadata.py: saving and reading the shared metadata tables, on the test's own database."""
import pytest
from tubes import db, metadata


def test_save_replaces_only_the_tables_a_row_names():
    with db.connect() as con:
        metadata.save(con, 'video', [dict(id='v1', meta=dict(images=[dict(kind='thumb', url='a', width=1, height=1), dict(kind='thumb', url='b'), dict(kind='poster', url='p')],
                                                               tags=[dict(kind='genre', value='Drama'), dict(kind='genre', value='Drama'), dict(kind='genre', value='Crime')],
                                                               credits=[dict(role='actor', name='A', character='Someone'), dict(role='director', name='D')],
                                                               ratings=[dict(source='imdb', value=7.5)], external_ids=[dict(source='imdb', value='tt1')],
                                                               chapters=[dict(start=0.0, end=10.0, title='One'), dict(start=10.0)],
                                                               tracks=[dict(kind='audio', language='en', codec='eac3', is_default=True), dict(kind='subtitle', language='fr', forced=True)]))])
    m = metadata.get('video', 'v1')
    assert [(i['kind'], i['rank'], i['url']) for i in m['images']] == [('poster', 2, 'p'), ('thumb', 0, 'a'), ('thumb', 1, 'b')]
    assert [t['value'] for t in m['tags']] == ['Drama', 'Crime']                       # the repeat is dropped, the source's order kept
    assert m['credits'][0] == dict(role='actor', rank=0, name='A', character='Someone', photo=None)
    assert m['ratings'] == [dict(source='imdb', value=7.5)] and m['external_ids'] == [dict(source='imdb', value='tt1')]
    assert m['chapters'] == [dict(start=0.0, end=10.0, title='One', image=None), dict(start=10.0, end=None, title=None, image=None)]
    assert [(t['kind'], t['is_default'], t['forced']) for t in m['tracks']] == [('audio', True, False), ('subtitle', False, True)]
    with db.connect() as con: metadata.save(con, 'video', [dict(id='v1', meta=dict(tags=[dict(kind='topic', value='Music')])), dict(id='v2')])
    m = metadata.get('video', 'v1')
    assert m['tags'] == [dict(kind='topic', value='Music', rank=0)] and len(m['images']) == 3      # images were not named, so kept
    assert metadata.get('video', 'v2') == dict(images=[], tags=[], credits=[], ratings=[], external_ids=[], chapters=[], tracks=[])


def test_channels_have_no_chapters_and_delete_forgets():
    with db.connect() as con:
        metadata.save(con, 'channel', [dict(id='c1', meta=dict(images=[dict(kind='banner', url='b')]))])
        metadata.save(con, 'video', [dict(id='c1', meta=dict(images=[dict(kind='thumb', url='t')]))])      # the same id as a video is its own
        with pytest.raises(ValueError, match='only a video has chapters'): metadata.save(con, 'channel', [dict(id='c1', meta=dict(chapters=[]))])
        with pytest.raises(ValueError, match='not a metadata table'): metadata.save(con, 'video', [dict(id='c1', meta=dict(nonsense=[]))])
    assert set(metadata.get('channel', 'c1')) == {'images', 'tags', 'credits', 'ratings', 'external_ids'}
    assert metadata.get('channel', 'c1')['images'][0]['url'] == 'b' and metadata.get('video', 'c1')['images'][0]['url'] == 't'
    with db.connect() as con: metadata.delete(con, 'channel', ['c1']); metadata.delete(con, 'video', [])
    assert metadata.get('channel', 'c1')['images'] == [] and metadata.get('video', 'c1')['images'][0]['url'] == 't'
    with db.connect() as con: metadata.delete(con, 'video', ['c1'])
    assert metadata.get('video', 'c1')['images'] == []


def test_colours():
    blur = dict(topLeft='012c5e', topRight='152d83', bottomRight='#a42c1c', bottomLeft='103b76')
    assert metadata.colours(blur) == '{"topLeft": "#012c5e", "topRight": "#152d83", "bottomRight": "#a42c1c", "bottomLeft": "#103b76"}'
    assert metadata.colours(dict(topLeft='0')) is None and metadata.colours(None) is None
    assert metadata.strip(dict(id='x', meta={})) == dict(id='x')
