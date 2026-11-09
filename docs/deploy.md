# Running Tubes on a server

A Linux or macOS machine with a large disk and a residential connection (fetching needs both; on Windows the app serves cached copies but cannot fetch). The steps below use systemd user units and Caddy; adapt the paths.

## 1. Install

```bash
git clone https://github.com/jburnhams/tubes && cd tubes
./scripts/setup_env.sh                     # .venv, dependencies, web build
dbtool new-app tubes                       # its own role and schema in the shared Postgres (omarchy_db)
./tubes set cache_dir /srv/tubes/cache     # on the big disk
./tubes set cache_limit_gb 1000
./tubes set d1_database <library D1 id>
```

Signed in to YouTube in a browser on the server (a Premium account has no ad waits before downloads), `./tubes set cookies_from_browser chrome+gnomekeyring` (yt-dlp's `--cookies-from-browser` value; the keyring part is needed where the desktop keyring encrypts cookies, and it must be unlocked, as with autologin).

yt-dlp and ffmpeg must be on the service's `PATH` or set with `./tubes set ytdlp /full/path` (and `ffmpeg`). Keep yt-dlp current (`yt-dlp -U`, or the package manager's update): YouTube changes break old versions within weeks.

## 2. Credentials

The library is read with a Cloudflare API token that can read D1. Put it in a file only the service user can read, never in the repo or the settings file:

```
# ~/.config/cloudflare/env  (chmod 600)
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
```

## 3. Service and timer

`~/.config/systemd/user/tubes.service`:

```ini
[Unit]
Description=Tubes video server
After=network-online.target postgresql.service

[Service]
WorkingDirectory=%h/src/tubes
EnvironmentFile=%h/.config/cloudflare/env
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

`./tubes doctor` (tools, database, credentials, the copy's age), then System in the app: every line should say Found, Can fetch, Set and Answering.
