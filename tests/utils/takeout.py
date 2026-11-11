"""Synthetic Google Takeout watch histories (watch-history.json and watch-history.html), in the shapes Takeout writes, for history.py's tests.

    watches = [watch('2026-01-01T10:00:00Z', 'vid00000001', 'A title', CH_A, 'Channel A'), ...]
    as_json(watches), as_html(watches)

`watch(..., ad=True)` marks one as an ad; `channel=None` is a video that has gone (Takeout then names no channel and titles it with its link)."""
import datetime, html, json


def chan(letter): return 'UC' + letter * 22


def watch(at, video, title, channel=None, channel_title=None, ad=False, action='Watched'):
    return dict(at=at, video=video, title=title, channel=channel, channel_title=channel_title, ad=ad, action=action)


def _url(v): return f'https://www.youtube.com/watch?v={v}'


def as_json(watches):
    out = []
    for w in watches:
        e = dict(header='YouTube', title=f"{w['action']} {w['title'] if w['channel'] else _url(w['video'])}", titleUrl=_url(w['video']), time=w['at'].replace('+00:00', 'Z'), products=['YouTube'], activityControls=['YouTube watch history'])
        if w['channel']: e['subtitles'] = [dict(name=w['channel_title'], url=f"https://www.youtube.com/channel/{w['channel']}")]
        if w['ad']: e['details'] = [dict(name='From Google Ads')]
        out.append(e)
    return json.dumps(out)


def uk_time(at):
    """The UK form Takeout's HTML uses (`9 Oct 2026, 21:57:37 BST`): BST from the last Sunday of March to the last Sunday of October, roughly (April to September here)."""
    t = datetime.datetime.fromisoformat(at.replace('Z', '+00:00'))
    summer = 4 <= t.month <= 9
    local = t + datetime.timedelta(hours=1 if summer else 0)
    return f"{local.day} {local.strftime('%b')} {local.year}, {local.strftime('%H:%M:%S')} {'BST' if summer else 'GMT'}"


def as_html(watches, when=uk_time):
    cells = []
    for w in watches:
        link = f'<a href="{_url(w["video"])}">{html.escape(w["title"]) if w["channel"] else _url(w["video"])}</a><br>'
        ch = f'<a href="https://www.youtube.com/channel/{w["channel"]}">{html.escape(w["channel_title"])}</a><br>' if w['channel'] else ''
        ad = '<b>Details:</b><br>&emsp;From Google Ads<br>' if w['ad'] else ''
        cells.append(f'<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid"><div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">YouTube<br></p></div>'
                     f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">{w["action"]} {link}{ch}{when(w["at"])}<br></div>'
                     f'<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption"><b>Products:</b><br>&emsp;YouTube<br>{ad}</div></div></div>')
    return '<html><head><style>p{}</style></head><body><div class="mdl-grid">' + ''.join(cells) + '</div></body></html>'
