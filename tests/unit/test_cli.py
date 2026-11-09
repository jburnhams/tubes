import importlib, json
import pytest
from tubes import cache, cli, fetcher, library, oslib, settings, ytdlp
from library import seed
from test_cache import write_playlist


@pytest.fixture(autouse=True)
def tools(monkeypatch):
    monkeypatch.setattr(ytdlp, 'version', lambda: '2026.10.26'); monkeypatch.setattr(fetcher, 'ffmpeg_version', lambda: 'ffmpeg version 7.1')
    monkeypatch.setattr(oslib, 'CAN_PASS_FDS', True)


def test_doctor(capsys, monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a'); monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 't'); monkeypatch.setenv('TUBES_D1_DATABASE', 'd')
    assert cli.main(['doctor']) == 0
    out = capsys.readouterr().out
    assert 'ok       yt-dlp 2026.10.26' in out and 'ok       ffmpeg ffmpeg version 7.1' in out and 'limit 1000 GB' in out and 'ok       library' in out
    assert 'library    0 channel(s), 0 video(s), synced never' in out

    real_import = importlib.import_module
    monkeypatch.setattr(importlib, 'import_module', lambda name: (_ for _ in ()).throw(ImportError(name)) if name == 'uvicorn' else real_import(name))
    monkeypatch.setattr(ytdlp, 'version', lambda: None); monkeypatch.setattr(fetcher, 'ffmpeg_version', lambda: None); monkeypatch.setattr(oslib, 'CAN_PASS_FDS', False)
    monkeypatch.delenv('CLOUDFLARE_API_TOKEN')
    assert cli.main(['doctor']) == 1
    out = capsys.readouterr().out
    assert 'MISSING  uvicorn' in out and 'MISSING  yt-dlp' in out and 'MISSING  ffmpeg' in out and 'MISSING  fetching needs Linux or macOS' in out and 'MISSING  library: The library cannot be read without CLOUDFLARE_API_TOKEN.' in out


def test_sync_and_channels(capsys, monkeypatch):
    assert cli.main(['channels']) == 0 and 'no channels yet' in capsys.readouterr().out
    with pytest.raises(SystemExit, match='cannot be read without'): cli.main(['sync'])
    def fake_sync(): seed(); return dict(channels=2, videos=4, synced='2026-11-09T12:00:00+00:00')
    monkeypatch.setattr(library, 'sync', fake_sync)
    assert cli.main(['sync']) == 0 and capsys.readouterr().out.strip() == '2 channel(s), 4 video(s), synced 2026-11-09T12:00:00+00:00'
    assert cli.main(['channels']) == 0 and 'UCbbbbbbbbbbbbbbbbbbbbbb        2 videos  night sky' in capsys.readouterr().out
    assert cli.main(['channels', '--json']) == 0 and len(json.loads(capsys.readouterr().out)) == 2


def test_fetch_cache_and_evict(capsys, monkeypatch):
    seed()
    def fake_start(vid, title, channel, background=True):
        if vid == 'bbbbbbbbbbb':
            cache.begin(vid, cache.stamp()); cache.finish(vid, cache.stamp(), error='Video unavailable'); return cache.status(vid)
        if vid == 'ccccccccccc': raise fetcher.FetchError('Fetching needs Linux or macOS.')
        cache.begin(vid, cache.stamp(), title); write_playlist(vid, 2, True); cache.finish(vid, cache.stamp()); cache.set_formats(vid, '1080p AV1 + AAC'); return cache.status(vid)
    monkeypatch.setattr(fetcher, 'start', fake_start)
    assert cli.main(['fetch', 'aaaaaaaaaaa']) == 0 and capsys.readouterr().out.strip() == 'aaaaaaaaaaa: ready, 2 segments, 8 s, 1080p AV1 + AAC'
    with pytest.raises(SystemExit, match='bbbbbbbbbbb: Video unavailable'): cli.main(['fetch', 'bbbbbbbbbbb'])
    with pytest.raises(SystemExit, match='Linux or macOS'): cli.main(['fetch', 'ccccccccccc'])
    with pytest.raises(SystemExit, match='zzz is not in the library'): cli.main(['fetch', 'zzz'])

    assert cli.main(['cache']) == 0
    out = capsys.readouterr().out
    assert 'in 2 video(s); eviction runs above 950.00 GB, down to 900.00 GB' in out and 'aaaaaaaaaaa    ready' in out and 'bbbbbbbbbbb    failed' in out
    assert cli.main(['cache', '--json']) == 0 and json.loads(capsys.readouterr().out)['count'] == 2

    settings.save(dict(cache_limit_gb=1e-9))
    assert cli.main(['evict', '--dry-run']) == 0 and 'would free' in capsys.readouterr().out
    assert cli.main(['evict', '--json']) == 0 and [e['video_id'] for e in json.loads(capsys.readouterr().out)['evicted']] == ['bbbbbbbbbbb']   # the fresh, unplayed copy is kept


def test_set_and_serve(capsys, monkeypatch):
    assert cli.main(['set', 'max_height']) == 0 and capsys.readouterr().out.strip() == 'max_height = 1080'
    assert cli.main(['set', 'max_height', '720']) == 0 and capsys.readouterr().out.strip() == 'max_height = 720'
    assert cli.main(['set', 'max_height', 'default']) == 0 and capsys.readouterr().out.strip() == 'max_height = 1080'
    with pytest.raises(SystemExit, match='must be a number'): cli.main(['set', 'max_height', 'tall'])
    with pytest.raises(SystemExit, match='unknown setting'): cli.main(['set', 'colour', 'red'])

    from tubes.server import app as server_app
    called = []
    monkeypatch.setattr(server_app, 'main', lambda argv: called.append(argv))
    assert cli.main(['serve', '--host', '0.0.0.0', '--port', '9000']) == 0
    assert called == [['--host', '0.0.0.0', '--port', '9000']]
