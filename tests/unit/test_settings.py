import os
import pytest
from tubes import settings


def test_defaults_and_env_overrides(tmp_path, monkeypatch):
    monkeypatch.delenv('TUBES_DATA', raising=False); monkeypatch.delenv('TUBES_HOME', raising=False)
    assert settings.home() == os.path.join(os.path.expanduser('~'), '.tubes')
    assert settings.data_dir() == settings.DEFAULT_DATA_DIR
    assert settings.cache_dir() == os.path.join(settings.DEFAULT_DATA_DIR, 'cache')
    assert settings.get('max_height') == 1080 and settings.get('player_client') == 'visionos' and settings.get('ytdlp') == 'yt-dlp'
    assert settings.cache_limit_bytes() == 1000 * 10**9

    monkeypatch.setenv('TUBES_HOME', str(tmp_path / 'home')); monkeypatch.setenv('TUBES_DATA', str(tmp_path / 'data'))
    monkeypatch.setenv('TUBES_CACHE', str(tmp_path / 'cache')); monkeypatch.setenv('TUBES_YTDLP', '/opt/yt-dlp')
    assert settings.home() == str(tmp_path / 'home')
    assert settings.data_dir() == str(tmp_path / 'data') and (tmp_path / 'data').is_dir()
    assert settings.cache_dir() == str(tmp_path / 'cache') and (tmp_path / 'cache').is_dir()
    assert settings.get('ytdlp') == '/opt/yt-dlp'


def test_save_parses_types_and_resets(tmp_path):
    assert settings.load() == {}
    saved = settings.save(dict(cache_limit_gb='500', max_height=720, player_client=' ', cache_dir=str(tmp_path / 'c')))
    assert saved == dict(cache_limit_gb=500.0, max_height=720, player_client='', cache_dir=str(tmp_path / 'c'))
    assert settings.get('cache_limit_gb') == 500.0 and settings.get('player_client') == ''
    assert settings.all_settings()['cache_dir'] == str(tmp_path / 'c')
    assert settings.save(dict(max_height=None)) == dict(cache_limit_gb=500.0, player_client='', cache_dir=str(tmp_path / 'c'))
    assert settings.get('max_height') == 1080


@pytest.mark.parametrize('key, value, message', [
    ('cache_limit_gb', 'lots', 'must be a number'), ('max_height', 0, 'must be more than 0'), ('protect_days', -1, 'must not be negative'),
    ('data_dir', 'relative/path', 'must be an absolute path'), ('cache_dir', '', 'must be an absolute path'),
])
def test_bad_values_are_refused_and_nothing_is_saved(key, value, message):
    with pytest.raises(settings.SettingError, match=message): settings.save({'max_height': 720, key: value})
    assert settings.load() == {}


def test_unknown_keys_and_bad_files(monkeypatch):
    with pytest.raises(KeyError): settings.save(dict(colour='red'))
    with pytest.raises(KeyError): settings.save(dict(colour=None))
    os.makedirs(settings.home(), exist_ok=True)
    with open(os.path.join(settings.home(), 'settings.json'), 'w') as f: f.write('{not json')
    assert settings.load() == {}
    with open(os.path.join(settings.home(), 'settings.json'), 'w') as f: f.write('[1, 2]')
    assert settings.load() == {}
    with open(os.path.join(settings.home(), 'settings.json'), 'w') as f: f.write('{"max_height": "tall", "protect_days": 3}')
    assert settings.get('max_height') == 1080 and settings.get('protect_days') == 3.0      # a bad value in the file falls back to the default
