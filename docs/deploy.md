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

The library comes from the YouTube Data API v3: a key from a Google Cloud project with that API enabled (10,000 units a day by default; a sync of an up-to-date channel costs about 2). If the key is restricted to HTTP referrers, `YOUTUBE_API_REFERER` is sent as the Referer header. Put them in a file only the service user can read, never in the repo or the settings file:

```
# ~/.config/<somewhere>/env  (chmod 600)
YOUTUBE_API_KEY=...
YOUTUBE_API_REFERER=https://<an allowed site>/    # only for a referrer-restricted key
```

Moving over from the storage service once: with `CLOUDFLARE_API_TOKEN` (D1 read) and `CLOUDFLARE_ACCOUNT_ID` also in the environment, `./tubes import-d1 --database <D1 id>` merges its `youtube_channels` and `youtube_videos` (each channel keeps how far its sync got), then `./tubes sync`. After that the Cloudflare variables are not needed.

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
