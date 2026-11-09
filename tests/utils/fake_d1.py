"""A stand-in for Cloudflare's D1 HTTP API, for the integration suite: a real HTTP server on localhost answering
`POST /accounts/<account>/d1/database/<database>/query` by running the SQL on an in-memory SQLite database with the library's two tables
(the columns storage's migrations give `youtube_channels` and `youtube_videos` that Tubes reads, plus the NOT NULL ones it does not).
Use through the `fake_d1` fixture (tests/conftest.py): `fake_d1.channel(...)`, `fake_d1.video(...)`, then `tubes sync`."""
import json, re, sqlite3, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCHEMA = """
CREATE TABLE youtube_channels (youtube_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', custom_url TEXT, thumbnail_url TEXT NOT NULL DEFAULT '',
    best_thumbnail_url TEXT, published_at TEXT NOT NULL DEFAULT '', statistics TEXT NOT NULL DEFAULT '{}', raw_json TEXT NOT NULL DEFAULT '{}', last_sync_at TEXT,
    created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '');
CREATE TABLE youtube_videos (youtube_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', published_at TEXT NOT NULL, channel_id TEXT NOT NULL,
    thumbnail_url TEXT NOT NULL DEFAULT '', best_thumbnail_url TEXT, duration TEXT NOT NULL DEFAULT 'PT0S', duration_seconds INTEGER, view_count INTEGER,
    statistics TEXT NOT NULL DEFAULT '{}', raw_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '');
"""
PATH = re.compile(r'^/accounts/([^/]+)/d1/database/([^/]+)/query$')


class FakeD1:
    def __init__(self, account='acct', database='db-id', token='token'):
        self.account, self.database, self.token, self.queries = account, database, token, []
        self.db = sqlite3.connect(':memory:', check_same_thread=False); self.db.row_factory = sqlite3.Row; self.db.executescript(SCHEMA); self.lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                m = PATH.match(self.path); body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.headers.get('Authorization') != f'Bearer {fake.token}': return self.answer(403, dict(success=False, errors=[dict(code=10000, message='Authentication error')]))
                if not m or m.groups() != (fake.account, fake.database): return self.answer(404, dict(success=False, errors=[dict(code=7404, message='not found')]))
                fake.queries.append(body)
                try:
                    with fake.lock: rows = [dict(r) for r in fake.db.execute(body['sql'], body.get('params') or [])]
                except sqlite3.Error as e: return self.answer(400, dict(success=False, errors=[dict(code=7500, message=str(e))]))
                self.answer(200, dict(success=True, errors=[], result=[dict(results=rows, success=True, meta=dict(rows_read=len(rows)))]))

            def answer(self, code, data):
                b = json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.api = f'http://127.0.0.1:{self.server.server_port}/accounts/{{account}}/d1/database/{{database}}/query'

    def channel(self, cid, title, **kw):
        with self.lock, self.db: self.db.execute(f'INSERT INTO youtube_channels (youtube_id, title{"".join(", " + k for k in kw)}) VALUES (?, ?{", ?" * len(kw)})', (cid, title, *kw.values()))
        return self

    def video(self, vid, channel_id, title, published, seconds=6, **kw):
        with self.lock, self.db:
            self.db.execute(f'INSERT INTO youtube_videos (youtube_id, channel_id, title, published_at, duration_seconds{"".join(", " + k for k in kw)}) VALUES (?, ?, ?, ?, ?{", ?" * len(kw)})', (vid, channel_id, title, published, seconds, *kw.values()))
        return self

    def remove_video(self, vid):
        with self.lock, self.db: self.db.execute('DELETE FROM youtube_videos WHERE youtube_id = ?', (vid,))
        return self

    def close(self): self.server.shutdown(); self.server.server_close()
