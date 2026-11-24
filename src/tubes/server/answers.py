"""What the API answers, as Pydantic models: declared on each route (`answer(Model)` in app.py) so the OpenAPI schema says what every
endpoint returns, and the web app's types are generated from it (web/openapi.json -> web/src/api.generated.ts, `npm run api-types`).

They describe, they do not filter: a route still returns its dict as it is (no response_model, so nothing is dropped or validated on
the server). The tests hold the two together instead: with `CHECK` on (tests/conftest.py), every 200 answer of a route that declares a
model is validated against it, so a field the server stops sending, or sends as another type, fails the suite. A field the server sends
and no model names is allowed, and invisible to the web app's types until it is declared here.

Written from the types the web app had by hand (web/src/api.ts before 2026-11-15), which were what the pages read."""

from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fastapi import Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.config import JsonDict

from tubes.shape import obj

CHECK = False  # tests/conftest.py turns it on: every answer of a route with a model is validated against it

CacheState = Literal[
    "fetching", "partial", "ready", "failed"
]  # partial: only its first seconds, prefetched so a play starts at once
SkipMode = Literal["off", "ask", "auto"]
Outcome = Literal["none", "short", "partial", "full"]


def _closed(schema: JsonDict) -> None:
    # Extra fields pass the check (an answer may carry more than its model says, such as a source's metadata), but the
    # schema does not say so: openapi-typescript would give every type an index signature, and a typo would type check.
    schema.pop("additionalProperties", None)


class Answer(BaseModel):
    model_config = ConfigDict(extra="allow", json_schema_extra=_closed)


class CheckedRoute(APIRoute):
    """A route that, while `CHECK` is on, validates each 200 JSON answer against the model its `responses` declare (a mismatch raises)."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        model = obj(self.responses.get(200)).get("model")
        if model is None:
            return handler
        adapter: TypeAdapter[Any] = TypeAdapter(model)

        async def checked(request: Request) -> Response:
            response = await handler(request)
            if CHECK and response.status_code == 200 and response.media_type == "application/json":
                adapter.validate_json(bytes(response.body))
            return response

        return checked


def answer(model: Any, description: str = "OK") -> dict[int | str, dict[str, Any]]:
    """A route's `responses=`: its 200 answer is `model` (a class, or `list[Model]`), for the schema and the tests' check."""
    return {200: {"model": model, "description": description}}


# --- the library -------------------------------------------------------------------------------------------------------------------


class Channel(Answer):
    id: str
    platform: Literal["youtube", "iplayer", "plex"] = Field(
        description="Where it comes from: 'youtube', 'iplayer' for a BBC iPlayer programme, 'plex'."
    )
    kind: str | None = Field(
        description="What it is (metadata.py): channel (YouTube), programme, network or category (iPlayer), show or filter (Plex)."
    )
    title: str
    handle: str | None
    thumbnail: str | None
    synced: str | None = Field(description="When this channel was last synced.")
    videos: int = Field(description="Videos held here that can be watched.")
    hidden: int = Field(
        description="Videos hidden because YouTube no longer has them or they are streams not over yet."
    )
    latest: str | None
    total_videos: int | None = Field(description="YouTube's own count (null when it hides it).")
    subscribers: int | None
    follow: bool = Field(
        description="Its uploads are synced. False for a channel only here for videos added one by one."
    )
    complete: bool = Field(description="Every page of its uploads has been read once.")
    resumable: bool = Field(description="A first sync stopped part way and resumes from where it got to.")
    added: str | None


class Video(Answer):
    id: str
    platform: Literal["youtube", "iplayer", "plex"]
    channel_id: str
    channel: str | None
    title: str
    published: str
    duration: float | None
    thumbnail: str | None
    views: int | None
    cache_state: CacheState | None
    cache_bytes: int | None
    gone: str | None = Field(
        description="Since when YouTube has not had it (removed or made private). The lists leave such a video out; its own page still opens."
    )
    expires: str | None = Field(description="iPlayer: when it stops being offered (a copy already saved here stays).")
    series: str | None
    episode: int | None


class ContinueVideo(Video):
    resume: float | None = Field(description="Where the last play stopped, in seconds.")
    progress: float | None = Field(
        description="How far through the video that is (0-1, null when its length is not known)."
    )


class VideoDetail(Video):
    plays: int
    last_played: str | None


class VideoPage(Answer):
    videos: list[Video]
    has_more: bool


class LibraryStatus(Answer):
    synced: str | None = Field(description="When every followed channel was last synced, null before the first.")
    channels: int
    videos: int = Field(description="Videos that can be watched.")
    hidden: int = Field(description="Those YouTube no longer has (deleted or made private), left out of every list.")
    live: int = Field(description="Streams live now or scheduled, hidden from every list until they end.")
    filtered: int = Field(description="Videos Admin's filters (Settings, Shown videos) leave out.")
    configured: bool = Field(
        description="The YouTube key is in the server's environment, so YouTube channels can be added and synced."
    )


class LanguageCount(Answer):
    code: str | None
    videos: int


class ShownFilters(Answer):
    """Which videos the watching side shows. Lengths in seconds, null for no limit."""

    min_seconds: int | None
    max_seconds: int | None
    streams: Literal["current", "all"]
    region: str | None = Field(
        description="The country the server watches from (GB): a video YouTube says does not play there is left out. Null: not checked."
    )
    languages: list[str] = Field(
        description="Base language codes a video's spoken language must be one of; empty for every language."
    )
    unknown_language: Literal["show", "hide"]
    captions: Literal["any", "only"]
    filtered: int = Field(description="How many videos these leave out now.")
    language_counts: list[LanguageCount]


class SyncError(Answer):
    channel: str | None
    title: str | None
    error: str
    added: int | None = None


class SyncJob(Answer):
    running: bool
    total: int
    done: int
    current: str | None = Field(description="The channel being synced now, by title.")
    added: int = Field(description="New videos so far.")
    gone: int = Field(description="Videos the recheck after a sync of every channel found gone from YouTube, and hid.")
    errors: list[SyncError]
    started: str | None
    finished: str | None


class AddedChannel(Answer):
    kind: Literal["channel"]
    channel: Channel
    sync: SyncJob


class AddedVideo(Answer):
    kind: Literal["video"]
    video: Video


Added = AddedChannel | AddedVideo


class Removed(Answer):
    channel: str
    videos: int


class Restarted(Removed):
    sync: SyncJob


class Checked(Answer):
    checked: int
    gone: int
    back: int
    hidden: list[str]


# --- playing ---------------------------------------------------------------------------------------------------------------------


class Stream(Answer):
    state: CacheState | Literal["none"] = Field(description="none: there is no copy and no fetch.")
    segments: int
    seconds: float
    complete: bool
    playable: bool
    error: str | None
    formats: str | None
    plays: int
    last_played: str | None


class Started(Stream):
    play_id: int
    copy_: str = Field(
        alias="copy",
        description="The id the copy's files are under: the video's own, or `<id>~native` for a Plex file kept as it is (fetcher.plex_copy).",
    )
    resume: float | None = Field(
        description="Where the last part-watched play stopped, in seconds, or null to start from the beginning."
    )


class Reported(Answer):
    outcome: Outcome


class Segment(Answer):
    category: str
    start: float
    end: float
    action: Literal["skip", "mute"]


class Break(Answer):
    """A break the watching side takes from playing: a page shown over the paused video (settings break_*)."""

    url: str | None = Field(description="The page to show: an http(s) link or a path on this server. Null: no breaks.")
    minutes: float = Field(description="Minutes of playing between two breaks, counted in each browser across videos.")
    limit_minutes: float = Field(description="The longest a break lasts when its page never says it is done.")


class SegmentKind(Answer):
    id: str
    label: str
    detail: str
    mode: SkipMode


class Segments(Answer):
    segments: list[Segment]
    categories: list[SegmentKind]
    error: str | None = Field(
        description="Set when the source could not be asked just now (what it had is still sent)."
    )


# --- viewing ---------------------------------------------------------------------------------------------------------------------


class Play(Answer):
    id: int
    video_id: str
    title: str | None
    channel_id: str | None
    channel: str | None
    thumbnail: str | None
    at: str
    updated: str | None
    source: str
    detail: str | None
    detail_title: str | None
    rank: int | None
    length: float | None
    watched: float | None
    position: float | None
    outcome: Outcome


class PlayPage(Answer):
    items: list[Play]
    has_more: bool


class SourceCount(Answer):
    plays: int
    full: int


class PlaySummary(Answer):
    since: str
    days: int
    plays: int
    seconds: float
    videos: int
    outcomes: dict[Outcome, int]
    sources: dict[str, SourceCount]
    channel_views: dict[str, int]


class ChannelVisit(Answer):
    id: int
    channel_id: str
    title: str | None
    thumbnail: str | None
    at: str
    source: str
    detail: str | None
    detail_title: str | None


class ChannelVisitPage(Answer):
    items: list[ChannelVisit]
    has_more: bool


class Visited(Answer):
    id: int


# --- the cache and the server ------------------------------------------------------------------------------------------------------


class CacheItem(Answer):
    video_id: str
    title: str
    channel: str | None
    state: CacheState
    bytes: int
    started: str
    finished: str | None
    formats: str | None
    error: str | None
    pinned: bool
    plays: int
    last_played: str | None
    score: float
    protected: str | None


class CacheUsage(Answer):
    """Sizes are bytes; eviction starts above `high` and stops under `low`."""

    used: int
    limit: int
    high: int
    low: int
    count: int
    by_state: dict[CacheState, int]
    bytes_by_state: dict[CacheState, int]


class CacheReport(CacheUsage):
    items: list[CacheItem]


class EvictedItem(Answer):
    video_id: str
    title: str
    bytes: int
    score: float


class Evicted(Answer):
    evicted: list[EvictedItem]
    freed: int
    dry_run: bool


class Dropped(Answer):
    video_id: str
    freed: int


class Disk(Answer):
    total: int
    used: int
    free: int


class SystemStatus(Answer):
    version: str
    python: str
    platform: str
    ytdlp: str | None
    ffmpeg: str | None
    can_fetch: bool
    data_dir: str
    cache_dir: str
    cache: CacheUsage
    fetching: list[str]
    disk: Disk
    library: LibraryStatus


class QuotaTotals(Answer):
    calls: int
    units: int
    failed: int = Field(description="Calls YouTube answered with an error (they still cost their units).")
    refused: int = Field(description="Of those, the ones refused because the quota was spent.")


class QuotaPurpose(QuotaTotals):
    purpose: str


class QuotaEndpoint(QuotaTotals):
    endpoint: str


class QuotaHour(QuotaTotals):
    hour: int


class QuotaToday(QuotaTotals):
    purposes: list[QuotaPurpose]
    endpoints: list[QuotaEndpoint]
    hours: list[QuotaHour]


class QuotaDay(QuotaTotals):
    day: str
    purposes: dict[str, int]


class QuotaUsage(Answer):
    """The YouTube key's daily quota as this server has counted it. Google has no call that says how much is left."""

    configured: bool
    limit: int
    day: str = Field(description="Today, as the quota counts days: YYYY-MM-DD in Pacific time.")
    used: int
    remaining: int
    resets: str
    refused: str | None
    today: QuotaToday
    days: list[QuotaDay]


# --- suggestions and history -----------------------------------------------------------------------------------------------------


class HistorySource(Answer):
    source: str
    watches: int
    channels: int
    first: str
    last: str


class Suggestion(Answer):
    channel_id: str
    title: str
    handle: str | None
    thumbnail: str | None
    watches: int
    videos: int
    first: str | None
    last: str | None
    score: float
    group_id: int | None
    subscribers: int | None
    total_videos: int | None
    topics: list[str]
    made_for_kids: bool | None
    missing: bool
    dismissed: str | None
    in_library: bool
    suggested_by: int
    related_score: float
    suggested_from: list[str]
    platform: str
    pasted: str | None
    link: str


class SuggestionPage(Answer):
    items: list[Suggestion]
    total: int


class SuggestionGroup(Answer):
    id: int
    name: str
    named: bool
    channels: int


class Topic(Answer):
    name: str
    channels: int


class RelatedStatus(Answer):
    sources: int
    asked: int
    due: int
    failed: int
    last: str | None


class SuggestionSummary(Answer):
    sources: list[HistorySource]
    groups: list[SuggestionGroup]
    ungrouped: int
    topics: list[Topic]
    kids: int
    open: int
    dismissed: int
    followed: int
    refreshed: str | None
    configured: bool
    database: bool = Field(description="A history database is set on the server: Regroup reads it again first.")
    suggested: int
    unwatched: int
    pasted: int
    related: RelatedStatus


class Refreshed(Answer):
    channels: int
    groups: int
    grouped: int
    looked_up: int
    missing: int
    error: str | None


class RefreshedWithSummary(Refreshed):
    summary: SuggestionSummary


class PastedFound(Answer):
    input: str
    platform: str
    channel_id: str
    title: str


class PastedAlready(Answer):
    input: str
    title: str


class PastedProblem(Answer):
    input: str
    error: str


class Pasted(Answer):
    found: list[PastedFound]
    already: list[PastedAlready]
    problems: list[PastedProblem]


class Imported(Answer):
    source: str
    watches: int
    first: str
    last: str
    refresh: Refreshed


class SourceRemoved(Answer):
    source: str
    refresh: Refreshed


class AddedWatched(Answer):
    added: int
    already: int
    missing: int


class Period(Answer):
    period: str
    watches: int


class TopChannel(Answer):
    channel_id: str
    title: str | None
    watches: int
    videos: int
    last: str
    followed: bool


class TopVideo(Answer):
    video_id: str
    title: str | None
    channel_id: str | None
    channel: str | None
    watches: int
    last: str


class HistoryStats(Answer):
    watches: int
    videos: int
    channels: int
    first: str | None
    last: str | None
    by: Literal["day", "month"]
    periods: list[Period]
    channels_top: list[TopChannel]
    videos_top: list[TopVideo]
    sources: list[HistorySource]
    configured: bool


class OverviewGroup(Answer):
    id: int
    name: str
    named: bool


class OverviewSource(Answer):
    source: str
    watches: int


class OverviewVideo(Answer):
    video_id: str
    title: str | None
    watches: int
    last: str
    in_library: bool


class OverviewHistory(Answer):
    watches: int
    videos: int
    first: str | None
    last: str | None
    sources: list[OverviewSource]
    periods: list[Period]
    videos_top: list[OverviewVideo]


class ChannelOverview(Answer):
    channel_id: str
    title: str
    thumbnail: str | None
    handle: str | None
    library: Channel | None
    suggestion: Suggestion | None
    group: OverviewGroup | None
    configured: bool
    history: OverviewHistory


# --- Plex --------------------------------------------------------------------------------------------------------------------------


class PlexSection(Answer):
    key: str
    title: str
    type: Literal["movie", "show"]
    locations: list[str]


class PlexStatus(Answer):
    configured: bool
    reachable: bool
    version: str | None
    error: str | None = None
    sections: list[PlexSection]


class PlexItem(Answer):
    key: str
    type: str
    title: str
    year: int | None
    thumb: str | None = Field(description="A Tubes picture address (the token stays on the server).")
    summary: str | None
    content_rating: str | None
    episodes: int | None
    section: str | None
    followed: bool | None = None


class PlexPage(Answer):
    items: list[PlexItem]
    total: int
    params: dict[str, str] = Field(description="The filters the server passed on to Plex (the rest were left out).")


class PlexFilterKind(Answer):
    filter: str | None
    title: str | None
    type: str | None


class PlexChoice(Answer):
    key: str
    title: str
