"""Sample library data for tests: channel and video rows, and a helper to fill the library without YouTube."""
CHANNELS = [dict(id='UCaaaaaaaaaaaaaaaaaaaaaa', title='Workshop', handle='@workshop', thumbnail='https://img.test/ws.jpg', synced='2026-01-20T10:00:00Z'),
            dict(id='UCbbbbbbbbbbbbbbbbbbbbbb', title='night sky', handle=None, thumbnail=None, synced=None)]


def video(vid, channel=0, published='2026-01-01T00:00:00Z', title=None, duration=600):
    return dict(id=vid, channel_id=CHANNELS[channel]['id'], title=title or f'Video {vid}', published=published, duration=duration, thumbnail=f'https://img.test/{vid}.jpg', views=10)


VIDEOS = [video('aaaaaaaaaaa', 0, '2026-01-03T00:00:00Z', 'Building a 50% shelf'), video('bbbbbbbbbbb', 0, '2026-01-02T00:00:00Z', 'Sanding the shelf'),
          video('ccccccccccc', 1, '2026-01-02T00:00:00Z', 'Stars in winter'), video('ddddddddddd', 1, '2026-01-01T00:00:00Z', 'The Moon, up close')]


def seed(channels=CHANNELS, videos=VIDEOS, synced='2026-11-09T12:00:00+00:00'):
    """Fill the local library copy as a sync would."""
    from tubes import db
    with db.connect() as con:
        con.executemany('INSERT INTO channels (id, title, handle, thumbnail, synced) VALUES (:id, :title, :handle, :thumbnail, :synced)', channels)
        con.executemany('INSERT INTO videos (id, channel_id, title, published, duration, thumbnail, views) VALUES (:id, :channel_id, :title, :published, :duration, :thumbnail, :views)', videos)
        if synced: con.execute("INSERT INTO meta (key, value) VALUES ('library_synced', ?)", (synced,))
