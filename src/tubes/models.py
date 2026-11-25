"""Tubes' tables, as typed records. They live in the `tubes` schema of the shared PostgreSQL server (strata_python.db: `connect('tubes')`), and on
SQLite in the tests and for a quick local run (`TUBES_DATABASE_URL=data/tubes.db`). Change a field here, then `strata-db revision -m "..."` writes
the migration into migrations/ (review it and commit it); the server applies pending migrations when it starts (db.py).

Everything is portable SQL (no Postgres-only types), so the tests run on SQLite. Times are ISO 8601 strings in UTC, as the library's own rows
carry them, so they sort and compare as text on both engines.

  channels, videos   the library: channels added in Admin (or by `tubes add`) and their videos, filled from the YouTube Data API by
                     catalogue.py. `platform` says where a row comes from: `youtube`, `iplayer` (iplayer.py) or `plex` (plex.py: shows, films and followed filters), where a channel is a
                     programme and a video one of its episodes; ids cannot collide (iPlayer's are 8 characters, YouTube's 11 or 24). An
                     episode also has its `series` title, its `episode` number in it and when iPlayer stops offering it (`expires`). A channel that is `follow`ed has all its uploads fetched and new ones picked up by every sync; one that
                     is not only names the videos added one by one. `uploads` is its uploads playlist, `sync_token` the page a backfill
                     that stopped part way resumes from, and `complete` says every page has been read once (later syncs then read only
                     the newest pages, until one brings nothing new). `total_videos`, `subscribers` and `views` are YouTube's counts.
  meta               single values by key, such as when the library was last synced.
  copies             one row per video that has (or is getting) a copy in the cache folder: fetching, partial (the first seconds only, prefetched), ready or failed, its size, whether it is
                     pinned, and the title and channel the library gave when it was fetched (kept, so a copy still has a name after its video
                     leaves the library). No foreign key to videos for the same reason.
  plays              one row per play, for the eviction score, Continue watching and predicting what to watch or fetch next: where it was
                     started from (home, a channel, a search, Up next...), and as the player reports it, how much was seen and where it
                     stopped, summed up as an `outcome` (short, partial, or full at 90% and more), viewing.py.
  channel_views      one row each time a channel's page is opened, and where from (the rail, the Channels page, a video's card...).
  watches            a viewing history brought in from elsewhere (a Google Takeout watch history, history.py), one row per watch, under the
                     `source` it was imported as: what suggestions are made from. Not plays: they never touch the eviction score.
  suggestions        one row per channel in the history: how often and how lately it was watched (`score` fades a watch by its age), its
                     group, YouTube's topics for it, and whether it was dismissed (kept when the history is imported again).
  api_usage          the YouTube Data API calls made, counted by Pacific day and hour, purpose and endpoint: units, calls, how many failed and
                     how many were refused for want of quota (quota.py). Nothing else in Google's API says how much of the daily quota is left.
  suggestion_groups  groups of channels watched in the same sittings, found from the history; `name` is made up from its channels until
                     someone names it (`named`), and a regrouping keeps a group's id and name for the group that overlaps it most.
                     A channel can also be here only because channels the library follows or the history watches point at it
                     (`suggested_by`, related.py), or because someone pasted it in (`pasted`, paste.py, YouTube or an iPlayer
                     programme): then it has no watches.
  related_sources    one row per channel YouTube was asked about for related channels (related.py), and when; asked again after a week.
  related_links      what each of those pointed at: channels whose videos its watch pages list next (`hits`), or that it features itself.
  bbc_programmes     iPlayer's whole catalogue of programmes (its A to Z), kept a day at a time for iPlayer suggestions (iplayer_suggest.py): title,
                     synopsis, categories, label, network, how many episodes, and when Tubes first saw it.
  bbc_similar        for each iPlayer programme suggested, the followed or played programmes it is most like, and how much (`score`, 0-1).
  images, tags,      a channel's or video's metadata beyond its own row, under `owner` ('channel' or 'video') and `owner_id` (metadata.py, which
  credits, ratings,  holds the shape every source fills as far as it can: Plex's, the richest). `images` every picture of it by `kind` (thumb,
  external_ids,      poster, backdrop, logo, square, banner, avatar, portrait), `tags` its genres, categories, topics, keywords and countries,
  chapters, tracks   `credits` its cast and crew in order, `ratings` scores from elsewhere (IMDb, Rotten Tomatoes, TMDB) out of 10, `external_ids`
                     its ids elsewhere (imdb, tmdb, tvdb, plex), `chapters` (videos only) its named parts and `tracks` (videos only) its audio
                     and subtitle tracks and other versions (audio-described, signed). A source's sync replaces what it gave before.
  video_groups,      groups of videos (groups.py), which may overlap: each with its name, and its videos with how well each represents it. Made
  video_group_       outside and loaded whole (`tubes groups load`); a load keeps a group's id, and the name someone gave it, for the group
  members            that shares most videos with it. No foreign keys: a video that left the library is not counted or shown.
  segments           parts of a video the player can skip (segments.py): from SponsorBlock for YouTube, from iPlayer's own intro and credits
                     points for an episode, under SponsorBlock's categories; `segment_checks` says when each video's source was last asked."""

from sqlalchemy import BigInteger, Float, Index, MetaData, String, Text, false, true
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column
from strata_python.db import NAMING_CONVENTION


class Base(MappedAsDataclass, DeclarativeBase):
    """Written out rather than `make_base()`, as strata_python.db asks (a base made by a call is not a class to type checkers). The naming
    convention is byte-identical to omarchy_db's, so the existing revisions and the deployed schema do not drift."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str]
    platform: Mapped[str] = mapped_column(String(16), server_default="youtube", default="youtube")
    handle: Mapped[str | None] = mapped_column(default=None)
    thumbnail: Mapped[str | None] = mapped_column(default=None)
    synced: Mapped[str | None] = mapped_column(String(40), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    published: Mapped[str | None] = mapped_column(String(40), default=None)
    country: Mapped[str | None] = mapped_column(String(8), default=None)
    language: Mapped[str | None] = mapped_column(
        String(16), default=None
    )  # the channel's default language (BCP-47, `en-GB`); a video without its own falls back to it
    subscribers: Mapped[int | None] = mapped_column(BigInteger, default=None)
    total_videos: Mapped[int | None] = mapped_column(BigInteger, default=None)
    views: Mapped[int | None] = mapped_column(BigInteger, default=None)
    uploads: Mapped[str | None] = mapped_column(String(64), default=None)
    sync_token: Mapped[str | None] = mapped_column(String(128), default=None)
    complete: Mapped[bool] = mapped_column(server_default=false(), default=False)
    follow: Mapped[bool] = mapped_column(server_default=true(), default=True)
    added: Mapped[str | None] = mapped_column(String(40), default=None)
    # The shared metadata (metadata.py's notes): None wherever a source does not say.
    kind: Mapped[str | None] = mapped_column(
        String(16), default=None
    )  # channel (YouTube), programme, network or category (iPlayer), show or filter (Plex)
    tagline: Mapped[str | None] = mapped_column(Text, default=None)  # a line about it, shorter than its description
    network: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # who makes or shows it: iPlayer's network, Plex's studio
    content_rating: Mapped[str | None] = mapped_column(
        String(32), default=None
    )  # `gb/U`, `gb/PG`, `TV-Y` (Plex's form: an optional country and its rating)
    min_age: Mapped[int | None] = mapped_column(default=None)  # the youngest age it is rated for
    kids: Mapped[bool | None] = mapped_column(
        default=None
    )  # made for children: YouTube's madeForKids, iPlayer's childrens, a Plex age up to 7
    colours: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # JSON {topLeft, topRight, bottomRight, bottomLeft} hex colours for a backdrop behind it
    source: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # Plex: a followed filter's JSON {section, params} (plex.py)


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        Index("ix_videos_published", "published", "id"),
        Index("ix_videos_channel", "channel_id", "published", "id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str]
    published: Mapped[str] = mapped_column(String(40))
    duration: Mapped[float | None] = mapped_column(default=None)
    thumbnail: Mapped[str | None] = mapped_column(default=None)
    views: Mapped[int | None] = mapped_column(BigInteger, default=None)  # 64-bit: the most watched videos pass 2^31
    description: Mapped[str | None] = mapped_column(Text, default=None)
    likes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    comments: Mapped[int | None] = mapped_column(BigInteger, default=None)
    definition: Mapped[str | None] = mapped_column(String(8), default=None)  # hd or sd
    added: Mapped[str | None] = mapped_column(String(40), default=None)
    gone: Mapped[str | None] = mapped_column(
        String(40), default=None
    )  # when YouTube was first found not to have it (catalogue.recheck); hidden while set
    checked: Mapped[str | None] = mapped_column(
        String(40), default=None
    )  # when the recheck last asked YouTube about it
    live: Mapped[str | None] = mapped_column(
        String(16), default=None
    )  # live, upcoming or was (a past stream): hidden while set, see youtube.live
    platform: Mapped[str] = mapped_column(String(16), server_default="youtube", default="youtube")
    expires: Mapped[str | None] = mapped_column(
        String(40), default=None
    )  # iPlayer: when it stops being offered; hidden after that unless it is cached
    series: Mapped[str | None] = mapped_column(Text, default=None)  # iPlayer: the series' title, such as `Series 2`
    episode: Mapped[int | None] = mapped_column(default=None)  # iPlayer: its number within the series
    language: Mapped[str | None] = mapped_column(
        String(16), default=None
    )  # spoken language (BCP-47, `en`, `en-GB`): YouTube's defaultAudioLanguage, else defaultLanguage
    captions: Mapped[bool | None] = mapped_column(
        default=None
    )  # YouTube: the uploader added captions (automatic ones are not counted); None when not known
    regions_allowed: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # comma-separated country codes it plays in only (YouTube's regionRestriction; `GB` for iPlayer)
    regions_blocked: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # comma-separated country codes it does not play in
    blocked: Mapped[str | None] = mapped_column(
        String(40), default=None
    )  # when a fetch was refused as not available in this server's country; hidden while set
    # The shared metadata (metadata.py's notes): None wherever a source does not say.
    kind: Mapped[str | None] = mapped_column(String(16), default=None)  # video, episode or film
    tagline: Mapped[str | None] = mapped_column(Text, default=None)  # a line about it, shorter than its description
    year: Mapped[int | None] = mapped_column(
        default=None
    )  # the year it came out (a film's release, an episode's first showing)
    network: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # who makes or shows it: iPlayer's network, Plex's studio
    season: Mapped[int | None] = mapped_column(
        default=None
    )  # the number of its series or season (`series` keeps the series' title)
    content_rating: Mapped[str | None] = mapped_column(
        String(32), default=None
    )  # `gb/U`, `gb/PG`, `TV-Y`; `18` for a video YouTube restricts by age
    min_age: Mapped[int | None] = mapped_column(default=None)  # the youngest age it is rated for
    kids: Mapped[bool | None] = mapped_column(
        default=None
    )  # made for children: YouTube's madeForKids, iPlayer's childrens, a Plex age up to 7
    width: Mapped[int | None] = mapped_column(
        default=None
    )  # the picture's size and range at its best, so the player can choose before a fetch
    height: Mapped[int | None] = mapped_column(default=None)
    hdr: Mapped[bool | None] = mapped_column(default=None)
    colours: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # JSON {topLeft, topRight, bottomRight, bottomLeft} hex colours for a backdrop behind it
    source: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # Plex: its file's part key, what ffmpeg reads (plex.py)


class Meta(Base):
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(default=None)


class Copy(Base):
    __tablename__ = "copies"
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))  # fetching, partial (only its start, prefetched), ready or failed
    started: Mapped[str] = mapped_column(String(40))
    title: Mapped[str | None] = mapped_column(default=None)
    channel: Mapped[str | None] = mapped_column(default=None)
    bytes: Mapped[int] = mapped_column(
        BigInteger, server_default="0", default=0
    )  # 64-bit: a long 1080p copy passes 2 GB
    finished: Mapped[str | None] = mapped_column(String(40), default=None)
    formats: Mapped[str | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    pinned: Mapped[bool] = mapped_column(server_default=false(), default=False)


class Play(Base):
    __tablename__ = "plays"
    __table_args__ = (Index("ix_plays_video", "video_id", "at"), Index("ix_plays_at", "at"))
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    video_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[str] = mapped_column(String(40))
    # How the play went (viewing.py); every one is None on a play from before these were kept (2026-11-12) or recorded by cache.record_play.
    source: Mapped[str | None] = mapped_column(
        String(32), default=None
    )  # where it was started: home, continue, channel, search, up_next, link (viewing.SOURCES)
    detail: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # which one: the channel's id, the search words, the video Up next was beside
    rank: Mapped[int | None] = mapped_column(default=None)  # its place in that list, from 0
    length: Mapped[float | None] = mapped_column(
        Float, default=None
    )  # the video's running time in seconds, as the player found it
    watched: Mapped[float | None] = mapped_column(
        Float, default=None
    )  # seconds of it seen, each second once (a part played again counts once; a part skipped counts as seen)
    position: Mapped[float | None] = mapped_column(
        Float, default=None
    )  # where the player was at the last report: where a later play picks up
    outcome: Mapped[str | None] = mapped_column(
        String(16), default=None
    )  # none, short, partial or full (90% and more seen), viewing.outcome
    updated: Mapped[str | None] = mapped_column(String(40), default=None)  # the last report


class ChannelView(Base):
    __tablename__ = "channel_views"
    __table_args__ = (Index("ix_channel_views_channel", "channel_id", "at"), Index("ix_channel_views_at", "at"))
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    channel_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[str] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(
        String(32), default=None
    )  # where it was opened from: rail, chips, channels, home, watch... (viewing.SOURCES)
    detail: Mapped[str | None] = mapped_column(Text, default=None)


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (Index("ix_watches_source", "source", "at"), Index("ix_watches_channel", "channel_id", "at"))
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    source: Mapped[str] = mapped_column(String(64))
    at: Mapped[str] = mapped_column(String(40))
    video_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text, default=None)
    channel_id: Mapped[str | None] = mapped_column(
        String(64), default=None
    )  # None when the video has gone (the history names no channel then)
    channel_title: Mapped[str | None] = mapped_column(Text, default=None)


class Suggestion(Base):
    __tablename__ = "suggestions"
    __table_args__ = (
        Index("ix_suggestions_score", "score", "channel_id"),
        Index("ix_suggestions_group", "group_id", "score"),
    )
    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str]
    watches: Mapped[int] = mapped_column(server_default="0", default=0)
    videos: Mapped[int] = mapped_column(server_default="0", default=0)  # different videos watched
    first: Mapped[str | None] = mapped_column(String(40), default=None)
    last: Mapped[str | None] = mapped_column(String(40), default=None)
    score: Mapped[float] = mapped_column(Float, server_default="0", default=0.0)
    group_id: Mapped[int | None] = mapped_column(default=None)
    thumbnail: Mapped[str | None] = mapped_column(default=None)
    handle: Mapped[str | None] = mapped_column(default=None)
    subscribers: Mapped[int | None] = mapped_column(BigInteger, default=None)
    total_videos: Mapped[int | None] = mapped_column(BigInteger, default=None)
    topics: Mapped[str | None] = mapped_column(Text, default=None)  # YouTube's topic names, joined by '|'
    made_for_kids: Mapped[bool | None] = mapped_column(default=None)
    looked_up: Mapped[str | None] = mapped_column(
        String(40), default=None
    )  # when YouTube was last asked about the channel
    missing: Mapped[bool] = mapped_column(
        server_default=false(), default=False
    )  # YouTube has no such channel any more: it cannot be followed
    dismissed: Mapped[str | None] = mapped_column(String(40), default=None)
    suggested_by: Mapped[int] = mapped_column(
        server_default="0", default=0
    )  # how many of the library's and the history's channels point at it (related.py)
    related_score: Mapped[float] = mapped_column(Float, server_default="0", default=0.0)
    platform: Mapped[str] = mapped_column(
        String(16), server_default="youtube", default="youtube"
    )  # an iPlayer programme only comes in pasted
    pasted: Mapped[str | None] = mapped_column(
        String(40), default=None
    )  # when someone pasted it into the page (paste.py)


class RelatedSource(Base):
    __tablename__ = "related_sources"
    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fetched: Mapped[str] = mapped_column(String(40))  # when YouTube was last asked (whether or not it answered)
    videos: Mapped[int] = mapped_column(server_default="0", default=0)  # watch pages read for it that answered
    error: Mapped[str | None] = mapped_column(Text, default=None)  # why the last ask failed; it is asked again sooner


class RelatedLink(Base):
    __tablename__ = "related_links"
    __table_args__ = (Index("ix_related_links_channel", "channel_id"),)
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    handle: Mapped[str | None] = mapped_column(default=None)
    hits: Mapped[int] = mapped_column(
        server_default="0", default=0
    )  # how many of the source's watch pages listed one of its videos
    featured: Mapped[bool] = mapped_column(
        server_default=false(), default=False
    )  # the source lists it among its own channels (channelSections)


class BbcProgramme(Base):
    __tablename__ = "bbc_programmes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    seen: Mapped[str] = mapped_column(String(40))  # when Tubes first saw it in the catalogue
    refreshed: Mapped[str] = mapped_column(String(40))
    synopsis: Mapped[str | None] = mapped_column(Text, default=None)
    categories: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # iPlayer's category ids, joined by '|' (`documentaries|documentaries-history`)
    label: Mapped[str | None] = mapped_column(Text, default=None)  # its own one-word genre (`Nature`, `Crime Drama`)
    network: Mapped[str | None] = mapped_column(String(64), default=None)  # `bbc_two`
    kind: Mapped[str | None] = mapped_column(String(32), default=None)  # `brand`, `series` or `episode` (a one-off)
    episodes: Mapped[int | None] = mapped_column(default=None)
    thumbnail: Mapped[str | None] = mapped_column(default=None)


class BbcSimilar(Base):
    __tablename__ = "bbc_similar"
    __table_args__ = (Index("ix_bbc_similar_channel", "channel_id", "score"),)
    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # the programme suggested
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # a followed or played programme it is like
    score: Mapped[float] = mapped_column(Float, server_default="0", default=0.0)


class Segment(Base):
    __tablename__ = "segments"
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    start: Mapped[float] = mapped_column(Float, primary_key=True)
    category: Mapped[str] = mapped_column(
        String(32), primary_key=True
    )  # SponsorBlock's: sponsor, selfpromo, intro, outro ...
    end: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))  # sponsorblock or iplayer
    action: Mapped[str] = mapped_column(
        String(16), server_default="skip", default="skip"
    )  # skip, or mute (SponsorBlock's actionType)
    votes: Mapped[int | None] = mapped_column(default=None)


class Image(Base):
    __tablename__ = "images"
    owner: Mapped[str] = mapped_column(String(8), primary_key=True)  # channel or video
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(16), primary_key=True
    )  # thumb, poster, backdrop, logo, square, banner, avatar, portrait (metadata.IMAGE_KINDS)
    rank: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=False
    )  # 0 is the one to show; more sizes or choices follow
    url: Mapped[str] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(default=None)
    height: Mapped[int | None] = mapped_column(default=None)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (Index("ix_tags_value", "kind", "value"),)
    owner: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(16), primary_key=True
    )  # genre, category, topic, keyword, label, country (metadata.TAG_KINDS)
    value: Mapped[str] = mapped_column(String(200), primary_key=True)
    rank: Mapped[int] = mapped_column(server_default="0", default=0)  # the source's order


class Credit(Base):
    __tablename__ = "credits"
    owner: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)  # actor, director, writer, producer, presenter
    rank: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # billing order within the role
    name: Mapped[str] = mapped_column(Text)
    character: Mapped[str | None] = mapped_column(Text, default=None)  # who an actor plays
    photo: Mapped[str | None] = mapped_column(Text, default=None)


class Rating(Base):
    __tablename__ = "ratings"
    owner: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(
        String(32), primary_key=True
    )  # imdb, rottentomatoes_critic, rottentomatoes_audience, tmdb
    value: Mapped[float] = mapped_column(Float)  # out of 10


class ExternalId(Base):
    __tablename__ = "external_ids"
    __table_args__ = (Index("ix_external_ids_value", "source", "value"),)
    owner: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), primary_key=True)  # imdb, tmdb, tvdb, plex
    value: Mapped[str] = mapped_column(String(128))


class Chapter(Base):
    __tablename__ = "chapters"
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    start: Mapped[float] = mapped_column(Float, primary_key=True)  # seconds
    end: Mapped[float | None] = mapped_column(Float, default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    image: Mapped[str | None] = mapped_column(Text, default=None)


class Track(Base):
    __tablename__ = "tracks"
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(16), primary_key=True
    )  # audio, subtitle, or version (another cut: audio-described, signed)
    rank: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # the source's order within the kind
    language: Mapped[str | None] = mapped_column(String(16), default=None)
    label: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # as the source names it: `English (EAC3 5.1)`, `Audio described`
    codec: Mapped[str | None] = mapped_column(String(32), default=None)
    ref: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # how the source finds it again: a stream index, a version id
    is_default: Mapped[bool] = mapped_column(server_default=false(), default=False)
    forced: Mapped[bool] = mapped_column(server_default=false(), default=False)


class SegmentCheck(Base):
    __tablename__ = "segment_checks"
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    checked: Mapped[str] = mapped_column(String(40))  # when its source was last asked (whether or not it answered)
    error: Mapped[str | None] = mapped_column(Text, default=None)


class SuggestionGroup(Base):
    __tablename__ = "suggestion_groups"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    named: Mapped[bool] = mapped_column(server_default=false(), default=False)


class VideoGroup(Base):
    __tablename__ = "video_groups"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    kind: Mapped[str | None] = mapped_column(String(32), default=None)  # what it is of, in the words of whoever made it
    named: Mapped[bool] = mapped_column(
        server_default=false(), default=False
    )  # someone named it: a load keeps the name


class VideoGroupMember(Base):
    __tablename__ = "video_group_members"
    __table_args__ = (Index("ix_video_group_members_video", "video_id"),)
    group_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    score: Mapped[float] = mapped_column(
        Float, server_default="0", default=0.0
    )  # how well it represents the group: higher is better, compared only within the group


class ApiUsage(Base):
    __tablename__ = "api_usage"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD in Pacific time, the quota's day
    hour: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # 0-23, Pacific
    purpose: Mapped[str] = mapped_column(String(32), primary_key=True)  # sync, recheck, add... (quota.purpose)
    endpoint: Mapped[str] = mapped_column(String(32), primary_key=True)  # channels, videos, playlistItems...
    calls: Mapped[int] = mapped_column(server_default="0", default=0)
    units: Mapped[int] = mapped_column(server_default="0", default=0)
    failed: Mapped[int] = mapped_column(server_default="0", default=0)
    refused: Mapped[int] = mapped_column(server_default="0", default=0)
