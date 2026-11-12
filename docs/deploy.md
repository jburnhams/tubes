# Running Tubes on a server

A Linux or macOS machine with a large disk and a residential connection (fetching needs both; on Windows the app serves cached copies but cannot fetch). The steps below use systemd user units and Caddy; adapt the paths.

## 1. Install

```bash
git clone https://github.com/jburnhams/tubes && cd tubes
./scripts/setup_env.sh                     # .venv, dependencies, web build
dbtool new-app tubes                       # its own role and schema in the shared Postgres (omarchy_db)
./tubes set cache_dir /srv/tubes/cache     # on the big disk
./tubes set cache_limit_gb 1000
```

Signed in to YouTube in a browser on the server (a Premium account has no ad waits before downloads), `./tubes set cookies_from_browser chrome+gnomekeyring` (yt-dlp's `--cookies-from-browser` value; the keyring part is needed where the desktop keyring encrypts cookies, and it must be unlocked, as with autologin).

yt-dlp and ffmpeg must be on the service's `PATH` or set with `./tubes set ytdlp /full/path` (and `ffmpeg`). Keep yt-dlp current (`yt-dlp -U`, or the package manager's update): YouTube changes break old versions within weeks.

## 2. Credentials

The library comes from the YouTube Data API v3: a key from a Google Cloud project with that API enabled (10,000 units a day by default; a sync of an up-to-date channel costs about 2). If the key is restricted to HTTP referrers, `YOUTUBE_API_REFERER` is sent as the Referer header. Google offers no call that says how much of the quota is left, so Tubes counts each call it makes (Admin > YouTube quota, `./tubes quota`); if the key's quota is not 10,000, set `YOUTUBE_API_QUOTA`. Put them in a file only the service user can read, never in the repo or the settings file:

```
# ~/.config/<somewhere>/env  (chmod 600)
YOUTUBE_API_KEY=...
YOUTUBE_API_REFERER=https://<an allowed site>/    # only for a referrer-restricted key
YOUTUBE_API_QUOTA=10000                           # only if Google granted the key a different daily quota
```

Moving over from the storage service needed no import: the tables already held the library copied from it, so the first `./tubes sync` on the new code read each channel back to its first upload (about one quota unit per 50 videos) and added what was missing. Nothing reads storage's D1 any more, so no Cloudflare credentials are needed.

## 3. Service and timer

`~/.config/systemd/user/tubes.service`:

```ini
[Unit]
Description=Tubes video server
After=network-online.target postgresql.service

[Service]
WorkingDirectory=%h/src/tubes
EnvironmentFile=%h/.config/<somewhere>/env
ExecStart=%h/src/tubes/tubes serve --host 127.0.0.1 --port 8367
Restart=on-failure

[Install]
WantedBy=default.target
```

`tubes-sync.service` (`Type=oneshot`, same `WorkingDirectory` and `EnvironmentFile`, `ExecStart=/bin/sh -c './tubes sync; ./tubes evict'`) and `tubes-sync.timer` (`OnCalendar=*-*-* 00/4:00:00`, `Persistent=true`). Then `systemctl --user daemon-reload && systemctl --user enable --now tubes.service tubes-sync.timer`, and `loginctl enable-linger` so they run without a login.

## 4. Reverse proxy

The app works at the root or at a subpath (it writes a relative `<base>` into every page). With Caddy, behind whatever authentication the machine already uses:

```
handle_path /tubes/* {
	reverse_proxy 127.0.0.1:8367
}
```

## 5. Check

`./tubes doctor` (tools, database, the YouTube key, when the library was last synced), then System in the app: every line should say Found, Can fetch, Set and Answering.

## 6. Suggestions from a watch history (optional)

Export "YouTube and YouTube Music" from Google Takeout (history as JSON if offered) for each account, then import each history under its own name, on the server or from Admin > Suggestions:

```
./tubes history import "<takeout>/YouTube and YouTube Music/history/watch-history.json" --source <name>
./tubes history            # what is imported
./tubes history refresh    # regroup and ask YouTube about channels not looked up for 30 days
```

If another database already keeps the history (a table or view with the columns account, at, video_id, title, channel_id, channel_name), point Tubes at it instead and sync it with the library:

```
./tubes set history_url 'postgresql+psycopg:///<database>'
./tubes set history_table '<schema>.<table>'
./tubes history sync       # also worth adding to the sync timer: ./tubes sync; ./tubes history sync; ./tubes evict
```

A Takeout from a second account (a brand account included) is made after switching to it in Takeout; import it under another name. The import asks YouTube about every channel watched at least twice, 50 per quota unit.

