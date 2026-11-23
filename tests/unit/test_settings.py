"""Tubes' settings: the declaration in settings.py over strata-python's Settings (file, environment, validation), plus what is Tubes' own:
the folders' defaults, the older environment names, the numbers an older settings file holds, and the API's typed shape."""
import json, os
import pytest
from tubes import settings


def test_defaults_and_env_overrides(tmp_path, monkeypatch):
    monkeypatch.delenv('TUBES_DATA', raising=False); monkeypatch.delenv('TUBES_HOME', raising=False)
    assert settings.home() == os.path.join(os.path.expanduser('~'), '.tubes')
    assert settings.data_dir() == settings.DEFAULT_DATA_DIR
    assert settings.cache_dir() == os.path.join(settings.DEFAULT_DATA_DIR, 'cache')
    assert settings.get_int('max_height') == 1080 and settings.get('player_client') == 'visionos' and settings.get('ytdlp') == 'yt-dlp'
    assert settings.cache_limit_bytes() == 1000 * 10**9

    monkeypatch.setenv('TUBES_HOME', str(tmp_path / 'home')); monkeypatch.setenv('TUBES_DATA', str(tmp_path / 'data'))
    monkeypatch.setenv('TUBES_CACHE', str(tmp_path / 'cache')); monkeypatch.setenv('TUBES_YTDLP', '/opt/yt-dlp')
    assert settings.home() == str(tmp_path / 'home')
    assert settings.data_dir() == str(tmp_path / 'data') and (tmp_path / 'data').is_dir()
    assert settings.cache_dir() == str(tmp_path / 'cache') and (tmp_path / 'cache').is_dir()
    assert settings.get('ytdlp') == '/opt/yt-dlp'
    monkeypatch.delenv('TUBES_CACHE')
    assert settings.cache_dir() == str(tmp_path / 'data' / 'cache')                       # follows the data folder until set itself
    monkeypatch.setenv('TUBES_MAX_HEIGHT', '720'); assert settings.get_int('max_height') == 720      # every setting has TUBES_<KEY>


def test_save_normalises_and_resets(tmp_path):
    assert settings.load() == {}
    saved = settings.save(dict(cache_limit_gb='500', max_height=720, player_client=' ', cache_dir=str(tmp_path / 'c')))
    assert saved == dict(cache_limit_gb='500', max_height='720', player_client='', cache_dir=str(tmp_path / 'c'))
    assert settings.get_float('cache_limit_gb') == 500.0 and settings.get('player_client') == ''
    assert settings.SETTINGS.all()['cache_dir'] == str(tmp_path / 'c')
    assert settings.save(dict(max_height=None)) == dict(cache_limit_gb='500', player_client='', cache_dir=str(tmp_path / 'c'))
    assert settings.get_int('max_height') == 1080
    assert settings.save(dict(cache_limit_gb=1e-9))['cache_limit_gb'] == '1e-09'       # tiny, but more than 0 (the tests evict with it)


@pytest.mark.parametrize('key, value, message', [
    ('cache_limit_gb', 'lots', 'must be a number'), ('cache_limit_gb', 0, 'must be more than 0'), ('half_life_days', -1, 'must be more than 0'),
    ('max_height', 0, 'must be a whole number from 1'), ('protect_days', -1, 'must be a number from 0'),
    ('data_dir', 'relative/path', 'must be an absolute path'), ('cache_dir', '', 'must be an absolute path'), ('ytdlp', ' ', 'must not be blank'),
    ('skip_intro', 'sometimes', 'must be one of off, ask, auto'),
])
def test_bad_values_are_refused_and_nothing_is_saved(key, value, message):
    with pytest.raises(ValueError, match=f'{key}: {message}'): settings.save({'max_height': 720, key: value})
    assert settings.load() == {}


def test_unknown_keys_and_bad_files():
    with pytest.raises(KeyError): settings.save(dict(colour='red'))
    with pytest.raises(KeyError): settings.save(dict(colour=None))
    os.makedirs(settings.home(), exist_ok=True)
    with open(os.path.join(settings.home(), 'settings.json'), 'w') as f: f.write('{not json')
    assert settings.load() == {}
    with open(os.path.join(settings.home(), 'settings.json'), 'w') as f: f.write('[1, 2]')
    assert settings.load() == {}
    with open(os.path.join(settings.home(), 'settings.json'), 'w') as f: f.write('{"max_height": "tall", "protect_days": "3"}')
    assert settings.get_int('max_height') == 1080 and settings.get_float('protect_days') == 3.0      # a bad value in the file falls back to the default


def test_a_file_written_before_strata_python_keeps_its_numbers():
    # Tubes used to write numbers as JSON numbers; strata-python's Settings would ignore them as not text, so a deployed file is read as text.
    os.makedirs(settings.home(), exist_ok=True)
    with open(os.path.join(settings.home(), 'settings.json'), 'w') as f: json.dump(dict(cache_limit_gb=750.0, max_height=720, protect_days=0, prefetch_per_day=10, ytdlp='/opt/yt-dlp'), f)
    assert (settings.get_float('cache_limit_gb'), settings.get_int('max_height'), settings.get_float('protect_days'), settings.get_int('prefetch_per_day')) == (750.0, 720, 0.0, 10)
    settings.save(dict(player_client='mweb'))                                                   # the next save writes every value as text
    with open(os.path.join(settings.home(), 'settings.json')) as f: assert json.load(f) == dict(cache_limit_gb='750.0', max_height='720', protect_days='0', prefetch_per_day='10', ytdlp='/opt/yt-dlp', player_client='mweb')


def test_the_api_shape_types_numbers_and_choices():
    fields = settings.SETTINGS.model().model_json_schema()['properties']
    assert fields['max_height']['type'] == 'integer' and fields['cache_limit_gb']['type'] == 'number' and fields['ytdlp']['type'] == 'string'
    assert fields['skip_sponsor']['enum'] == list(settings.SKIP_MODES) and set(fields) == set(settings.KNOWN)
