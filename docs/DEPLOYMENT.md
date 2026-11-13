# Deployment

The root [README](../README.md) covers installing on one machine, Docker, and a Raspberry Pi. This page covers the choices around those setups.

## Where each piece can run

- **Backend**: anywhere with Python 3.10+ and `ffmpeg` that stays on: a home PC, a Raspberry Pi, a small VPS. It listens on port 5050.
- **Web app**: anywhere Next.js runs. It only needs to reach the backend's URL (`SERENDIPID_API_URL`); browsers only reach the web app.
- **iOS app and browser extension**: connect to the backend directly, so the backend must be reachable from those devices.

Common layouts:

| Layout | Backend reachable from | Notes |
|---|---|---|
| Everything on one home machine or Pi | your home network, or Tailscale | Simplest. Use Tailscale to reach it from outside. |
| Backend at home, web app on Vercel | the web app's servers | Expose the backend through Tailscale Funnel, a Cloudflare Tunnel or a reverse proxy with HTTPS. Only the web app needs it, so you can restrict access to it. |
| Everything on a VPS | the internet | Put both behind HTTPS with a reverse proxy (Caddy, nginx). Consider not publishing the backend port at all and letting only the web app reach it on localhost. |

## Running the backend

`python start.py` runs the setup wizard on first launch and then starts uvicorn with auto-reload, which is convenient on a development machine. On a server, run uvicorn directly under a process manager instead, as in the systemd unit in the README:

```bash
.venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 5050
```

Run a single worker. The analysis queue, batch checks and background jobs live in the server process, and several workers would each run their own copy.

Flags that `start.py` and `api.py` accept have environment-variable equivalents, which is what to use under systemd or Docker:

| Flag | Environment variable |
|---|---|
| `--show-sensitive` | `SERENDIPID_SHOW_SENSITIVE=1` |
| `--prefer <provider>` | `SERENDIPID_PREFERRED_PROVIDER=<provider>` |

## Docker

`backend/docker-compose.yml` builds the image from `backend/Dockerfile` and keeps state on named volumes:

| Volume | Mounted at | Contents |
|---|---|---|
| `serendipid-data` | `/app/data` | database, media, access token |
| `serendipid-config` | `/app/config` | `user_config.json`, keys saved from the web app, router state |
| `serendipid-thumbnails` | `/app/static/thumbnails` | generated thumbnails |
| `serendipid-uploads` | `/app/uploads` | Instagram export files uploaded for import |
| `serendipid-temp`, `serendipid-logs` | `/app/temp`, `/app/logs` | scratch space and logs |

To use your own config file, copy it into the config volume:

```bash
docker compose cp my-config.json serendipid-api:/app/config/user_config.json
docker compose restart
```

The image has no local Whisper or Ollama. Transcription uses Groq's API (`GROQ_API_KEY`).

`start-docker.sh` and `start-docker-prod.sh` are convenience wrappers: the first creates `.env` if missing and runs `docker compose up -d --build`; the second also does a clean rebuild and waits for the health check.

## Updating

From a git checkout, `backend/deploy.sh` pulls the latest code, reinstalls dependencies and restarts the systemd service (`SERENDIPID_SERVICE`, default `serendipid`). Set `SERENDIPID_WEB_SERVICE` to also rebuild and restart the web app. With Docker, `git pull` then `docker compose up -d --build`.

Database schema changes are applied automatically at startup.

## Backups

Everything worth keeping is in the backend:

- the database (`backend/serendipid.db`, or `/app/data/serendipid.db` in Docker)
- downloaded media (`backend/media/`), which can be large but avoids downloading posts again
- `backend/config/user_config.json`, `backend/config/.api_keys` and `backend/token.txt`

For a consistent copy of the database while the server is running, use SQLite's backup command instead of copying the file:

```bash
sqlite3 backend/serendipid.db ".backup 'serendipid-backup.db'"
```

`GET /export` returns posts and collections as JSON, and `POST /import` restores such a file. Boards are not included in that export yet.
