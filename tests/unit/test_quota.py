"""quota.py: the Pacific day and its reset, counting calls by purpose, and what the Quota page reads; then the real calls through the stand-in YouTube."""
import pytest
from fake_youtube import vid
from tubes import catalogue, db, quota, youtube

A = 'UCaaaaaaaaaaaaaaaaaaaaaa'


@pytest.mark.parametrize('utc, local', [
    ('2026-01-15T07:59:00+00:00', '2026-01-14T23:59:00'),        # winter: UTC-8
    ('2026-07-01T07:00:00+00:00', '2026-07-01T00:00:00'),        # summer: UTC-7
    ('2026-03-08T09:59:00+00:00', '2026-03-08T01:59:00'),        # a minute before the spring change (2 am PST)
    ('2026-03-08T10:00:00+00:00', '2026-03-08T03:00:00'),        # ...and at it
    ('2026-11-01T08:59:00+00:00', '2026-11-01T01:59:00'),        # a minute before the autumn change (2 am PDT)
    ('2026-11-01T09:00:00+00:00', '2026-11-01T01:00:00'),        # ...and at it: 1 am again
    ('2026-11-12T05:00:00Z', '2026-11-11T21:00:00'),
])
def test_pacific_time_follows_the_us_clock_changes(utc, local):
    assert quota.pacific(utc).isoformat() == local


@pytest.mark.parametrize('utc, at', [
    ('2026-11-12T05:00:00+00:00', '2026-11-12T08:00:00+00:00'),  # 9 pm PST: midnight is 08:00 UTC
    ('2026-07-01T06:59:00+00:00', '2026-07-01T07:00:00+00:00'),  # a minute before midnight PDT
    ('2026-07-01T07:00:00+00:00', '2026-07-02T07:00:00+00:00'),  # at midnight: the next one
    ('2026-03-08T08:30:00+00:00', '2026-03-09T07:00:00+00:00'),  # 00:30 PST on the change day: midnight comes in PDT, 23 hours on
    ('2026-11-01T07:30:00+00:00', '2026-11-02T08:00:00+00:00'),  # 00:30 PDT on the change day: 25 hours on
])
def test_resets_at_the_next_pacific_midnight(utc, at):
    assert quota.resets(utc) == at


def test_limit_from_the_environment(monkeypatch):
    assert quota.limit() == 10_000
    monkeypatch.setenv('YOUTUBE_API_QUOTA', '50000'); assert quota.limit() == 50_000
    for bad in ('lots', '0', '-5'): monkeypatch.setenv('YOUTUBE_API_QUOTA', bad); assert quota.limit() == 10_000


def test_calls_are_counted_by_purpose_endpoint_and_hour(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'k')
    at = '2026-11-12T05:10:00+00:00'                                            # 9 pm on the 11th, Pacific
    quota.record('videos', now=at)
    with quota.purpose('sync'):
        quota.record('playlistItems', now=at); quota.record('playlistItems', now='2026-11-12T06:00:00+00:00')
        with quota.purpose('recheck'): quota.record('videos', failed=True, now=at)
        assert quota.current() == 'sync'
    quota.record('search', now=at)                                              # 100 units
    quota.record('videos', now='2026-11-12T08:00:00+00:00')                     # the next Pacific day
    u = quota.usage(now='2026-11-12T07:00:00+00:00')
    assert (u['day'], u['used'], u['limit'], u['remaining'], u['resets'], u['refused'], u['configured']) == ('2026-11-11', 104, 10_000, 9_896, '2026-11-12T08:00:00+00:00', None, True)
    assert u['today']['purposes'] == [dict(purpose='other', calls=2, units=101, failed=0, refused=0), dict(purpose='sync', calls=2, units=2, failed=0, refused=0), dict(purpose='recheck', calls=1, units=1, failed=1, refused=0)]
    assert [(e['endpoint'], e['units']) for e in u['today']['endpoints']] == [('search', 100), ('playlistItems', 2), ('videos', 2)]
    assert [(h['hour'], h['units']) for h in u['today']['hours']] == [(21, 103), (22, 1)]
    assert len(u['days']) == quota.HISTORY_DAYS and u['days'][0]['day'] == '2026-11-11' and u['days'][0]['purposes'] == dict(other=101, sync=2, recheck=1)
    assert u['days'][1] == dict(day='2026-11-10', calls=0, units=0, failed=0, refused=0, purposes={})
    nxt = quota.usage(now='2026-11-12T09:00:00+00:00')
    assert (nxt['day'], nxt['used'], nxt['days'][1]['units']) == ('2026-11-12', 1, 104)


def test_a_refusal_means_nothing_left_until_the_reset(monkeypatch):
    quota.record('videos', failed=True, refused=True, now='2026-11-12T05:00:00+00:00')
    quota.record('videos', failed=True, refused=True, now='2026-11-12T05:30:00+00:00')
    u = quota.usage(now='2026-11-12T06:00:00+00:00')
    assert (u['used'], u['remaining'], u['refused'], u['today']['refused'], u['configured']) == (2, 0, '2026-11-12T05:30:00+00:00', 2, False)
    assert quota.usage(now='2026-11-12T08:00:00+00:00')['refused'] is None      # a new day: the quota is back


def test_old_days_are_dropped():
    quota.record('videos', now='2026-01-01T12:00:00+00:00')
    quota.record('videos', now='2026-11-12T12:00:00+00:00')
    with db.connect() as con: assert [r['day'] for r in db.rows(con.execute('SELECT day FROM api_usage'))] == ['2026-11-12']


def test_counting_never_breaks_a_call(monkeypatch, caplog):
    def broken(*a): raise RuntimeError('the database is away')
    monkeypatch.setattr(quota, '_record', broken)
    quota.record('videos'); assert 'could not count a YouTube call (videos): the database is away' in caplog.text


def test_another_process_inserting_first_is_counted_once_more(monkeypatch):
    """The hour's row may appear between this process's update and its insert: the insert then fails and the update runs again."""
    real = db.connect
    quota.record('videos', now='2026-11-12T05:00:00+00:00')                    # warm the engine
    with db.connect() as con: con.execute('DELETE FROM api_usage')
    calls = []
    orig_bump = db.Connection.execute

    def execute(self, sql, params=None):
        if sql.startswith('INSERT INTO api_usage') and not calls:              # the update found nothing; the row appears before this insert
            calls.append(1)
            with real() as con: orig_bump(con, "INSERT INTO api_usage (day, hour, purpose, endpoint, calls, units, failed, refused) VALUES ('2026-11-11', 21, 'other', 'videos', 1, 1, 0, 0)")
        return orig_bump(self, sql, params)
    monkeypatch.setattr(db.Connection, 'execute', execute)
    quota.record('videos', now='2026-11-12T05:00:00+00:00')
    assert quota.usage(now='2026-11-12T05:00:00+00:00')['today']['purposes'] == [dict(purpose='other', calls=2, units=2, failed=0, refused=0)]


def test_real_calls_count_under_the_work_they_were_for(fake_youtube):
    fake_youtube.channel(A, 'Workshop', handle='@workshop', videos=60).uploads(A, 60)
    catalogue.add('@workshop'); catalogue.sync([A]); catalogue.recheck()
    with quota.purpose('history'): youtube.channels([A])
    fake_youtube.quota_left = 0
    with pytest.raises(youtube.YoutubeError, match='used its quota'): youtube.videos([vid(A, 0)])
    u = quota.usage()
    got = {p['purpose']: (p['calls'], p['failed'], p['refused']) for p in u['today']['purposes']}
    assert got['add'] == (1, 0, 0) and got['history'] == (1, 0, 0) and got['other'] == (1, 1, 1)
    assert got['sync'][0] >= 4 and got['recheck'][0] >= 1                       # the channel, two pages of uploads and their details; the recheck's batches
    assert u['used'] == len(fake_youtube.calls) and u['remaining'] == 0 and u['refused']
