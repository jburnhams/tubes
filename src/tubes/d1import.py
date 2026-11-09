"""`tubes import-d1`, run once: carry the library over from the Cloudflare D1 database the storage service kept it in (`youtube_channels`,
`youtube_videos`) into Tubes' own tables, where catalogue.py manages it from now on. Read only on D1 (SELECT only). Rows are merged, not
replaced: a channel or video already here is updated with D1's fuller columns (description, counts, how far its sync got) and nothing here
is deleted, so it is safe to run again. Remove this module once every deployment has run it.

Each channel keeps storage's sync state: its uploads playlist and its backfill page token (a page token of the same playlist stays valid), and
counts as `complete` when storage had synced it and had no page left to read. Every imported channel is followed, as storage synced them all.

The credentials are Cloudflare's own environment variables, `CLOUDFLARE_API_TOKEN` (with D1 read) and `CLOUDFLARE_ACCOUNT_ID`; the database
id is `--database`, else `TUBES_D1_DATABASE`, else the `d1_database` key that older settings files hold. `TUBES_D1_API` points the queries at
another address (the tests' stand-in D1). A D1 query costs 0.4-0.5 s from the home server, so videos come 5,000 a query."""
import json, os, urllib.error, urllib.request

from tubes import cache, catalogue, db, settings

API = 'https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query'
TIMEOUT = 60
PAGE = 5000
CHANNEL_SQL = """SELECT youtube_id AS id, title, custom_url AS handle, COALESCE(best_thumbnail_url, thumbnail_url) AS thumbnail, description, published_at AS published,
                        country, subscriber_count AS subscribers, video_count AS total_videos, view_count AS views, upload_playlist_id AS uploads,
                        last_sync_token AS sync_token, last_sync_at AS synced, created_at AS added
                 FROM youtube_channels ORDER BY youtube_id"""
VIDEO_SQL = """SELECT youtube_id AS id, channel_id, title, published_at AS published, duration_seconds AS duration, COALESCE(best_thumbnail_url, thumbnail_url) AS thumbnail,
                      view_count AS views, description, like_count AS likes, comment_count AS comments, definition, created_at AS added
               FROM youtube_videos WHERE youtube_id > ? ORDER BY youtube_id LIMIT ?"""


class D1Error(RuntimeError):
    """D1 could not be read; the message says why, in a sentence."""


def credentials(database=None):
    """(account, token, database), or D1Error naming what is missing."""
    database = database or os.environ.get('TUBES_D1_DATABASE') or settings.load().get('d1_database') or ''
    account, token = os.environ.get('CLOUDFLARE_ACCOUNT_ID', ''), os.environ.get('CLOUDFLARE_API_TOKEN', '')
    missing = [name for name, v in (('the D1 database id (--database)', database), ('CLOUDFLARE_ACCOUNT_ID', account), ('CLOUDFLARE_API_TOKEN', token)) if not v]
    if missing: raise D1Error(f'D1 cannot be read without {" and ".join(missing)}.')
    return account, token, database


def query(creds, sql, params=()):
    """Run one read on the D1 database; returns its rows as dicts."""
    account, token, database = creds
    req = urllib.request.Request(os.environ.get('TUBES_D1_API', API).format(account=account, database=database), data=json.dumps(dict(sql=sql, params=list(params))).encode(), method='POST',
                                 headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r: body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: why = '; '.join(err.get('message', '') for err in json.loads(e.read()).get('errors', [])) or None
        except ValueError: why = None
        raise D1Error(f'D1 refused the query ({e.code}{": " + why if why else ""}).') from None
    except (urllib.error.URLError, OSError) as e: raise D1Error(f'D1 could not be reached: {getattr(e, "reason", e)}.') from None
    except ValueError: raise D1Error('D1 did not answer with JSON.') from None
    if not body.get('success') or not body.get('result'): raise D1Error('D1 said the query failed: ' + ('; '.join(e.get('message', '') for e in body.get('errors') or []) or 'no reason given') + '.')
    return body['result'][0].get('results') or []


def run(database=None, now=None):
    """Read every channel and video from D1 and merge them in; returns `{channels, videos}` (how many were read). Nothing is written unless
    every read succeeds."""
    creds = credentials(database); now = now or cache.stamp()
    channels, videos, after = query(creds, CHANNEL_SQL), [], ''
    while True:
        page = query(creds, VIDEO_SQL, (after, PAGE)); videos += page
        if len(page) < PAGE: break
        after = page[-1]['id']
    for c in channels: c.update(added=c['added'] or now, complete=bool(c['synced']) and not c['sync_token'])
    for v in videos: v.update(added=v['added'] or now)
    with db.connect() as con:
        catalogue._upsert(con, 'channels', catalogue.CHANNEL_FIELDS + ('sync_token', 'synced', 'complete'), channels, keep=('added',))
        con.executemany('UPDATE channels SET follow = :follow WHERE id = :id', [dict(id=c['id'], follow=True) for c in channels])
        for i in range(0, len(videos), PAGE): catalogue.save_videos(con, videos[i:i + PAGE])
    return dict(channels=len(channels), videos=len(videos))
