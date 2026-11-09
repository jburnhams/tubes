"""Tubes' tables, as typed records. They live in the `tubes` schema of the shared PostgreSQL server (omarchy_db: `connect('tubes')`), and on
SQLite in the tests and for a quick local run (`TUBES_DATABASE_URL=data/tubes.db`). Change a field here, then `dbtool revision -m "..."` writes
the migration into migrations/ (review it and commit it); the server applies pending migrations when it starts (db.py).

Everything is portable SQL (no Postgres-only types), so the tests run on SQLite. Times are ISO 8601 strings in UTC, as the library's own rows
carry them, so they sort and compare as text on both engines.

  channels, videos   the library: channels added in Admin (or by `tubes add`) and their videos, filled from the YouTube Data API by
                     catalogue.py. A channel that is `follow`ed has all its uploads fetched and new ones picked up by every sync; one that
                     is not only names the videos added one by one. `uploads` is its uploads playlist, `sync_token` the page a backfill
                     that stopped part way resumes from, and `complete` says every page has been read once (later syncs then read only
                     the newest pages, until one brings nothing new). `total_videos`, `subscribers` and `views` are YouTube's counts.
  meta               single values by key, such as when the library was last synced.
  copies             one row per video that has (or is getting) a copy in the cache folder: fetching, ready or failed, its size, whether it is
                     pinned, and the title and channel the library gave when it was fetched (kept, so a copy still has a name after its video
                     leaves the library). No foreign key to videos for the same reason.
  plays              one row per play, for the eviction score and, later, for predicting what to fetch next."""
from sqlalchemy import BigInteger, Index, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column

from omarchy_db import make_base

Base = make_base()


class Channel(Base):
    __tablename__ = 'channels'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str]
    handle: Mapped[str | None] = mapped_column(default=None)
    thumbnail: Mapped[str | None] = mapped_column(default=None)
    synced: Mapped[str | None] = mapped_column(String(40), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    published: Mapped[str | None] = mapped_column(String(40), default=None)
    country: Mapped[str | None] = mapped_column(String(8), default=None)
    subscribers: Mapped[int | None] = mapped_column(BigInteger, default=None)
    total_videos: Mapped[int | None] = mapped_column(BigInteger, default=None)
    views: Mapped[int | None] = mapped_column(BigInteger, default=None)
    uploads: Mapped[str | None] = mapped_column(String(64), default=None)
    sync_token: Mapped[str | None] = mapped_column(String(128), default=None)
    complete: Mapped[bool] = mapped_column(server_default=false(), default=False)
    follow: Mapped[bool] = mapped_column(server_default=true(), default=True)
    added: Mapped[str | None] = mapped_column(String(40), default=None)


class Video(Base):
    __tablename__ = 'videos'
    __table_args__ = (Index('ix_videos_published', 'published', 'id'), Index('ix_videos_channel', 'channel_id', 'published', 'id'))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str]
    published: Mapped[str] = mapped_column(String(40))
    duration: Mapped[float | None] = mapped_column(default=None)
    thumbnail: Mapped[str | None] = mapped_column(default=None)
    views: Mapped[int | None] = mapped_column(BigInteger, default=None)            # 64-bit: the most watched videos pass 2^31
    description: Mapped[str | None] = mapped_column(Text, default=None)
    likes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    comments: Mapped[int | None] = mapped_column(BigInteger, default=None)
    definition: Mapped[str | None] = mapped_column(String(8), default=None)     # hd or sd
    added: Mapped[str | None] = mapped_column(String(40), default=None)


class Meta(Base):
    __tablename__ = 'meta'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(default=None)


class Copy(Base):
    __tablename__ = 'copies'
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))                    # fetching, ready or failed
    started: Mapped[str] = mapped_column(String(40))
    title: Mapped[str | None] = mapped_column(default=None)
    channel: Mapped[str | None] = mapped_column(default=None)
    bytes: Mapped[int] = mapped_column(BigInteger, server_default='0', default=0)    # 64-bit: a long 1080p copy passes 2 GB
    finished: Mapped[str | None] = mapped_column(String(40), default=None)
    formats: Mapped[str | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    pinned: Mapped[bool] = mapped_column(server_default=false(), default=False)


class Play(Base):
    __tablename__ = 'plays'
    __table_args__ = (Index('ix_plays_video', 'video_id', 'at'),)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    video_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[str] = mapped_column(String(40))
