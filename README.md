# Serendipid

Serendipid is a self-hosted archive for the things you save online. It is built mainly for Instagram reels: you import your saved posts, and a backend running on your own machine downloads each one, transcribes it, looks at the frames, identifies the music, and writes a summary, tags, categories and an importance score. Everything ends up in a local SQLite database that you can browse, search by meaning, chat with, and turn into study guides.

YouTube videos and regular web pages are supported too, through the same pipeline.

There is no hosted service and no account to create. You run the backend, you bring your own AI provider keys, and your data stays on your disk.

## What it does

- **Analyzes every saved post**: visual analysis of video frames, audio transcription, on-screen text, background music identification, then a combined summary with title, tags, categories, language and a 1 to 5 importance score.
- **Semantic search and chat**: posts are embedded, so you can search by meaning and ask questions answered from your own library.
- **Browse and organize**: filter by category, language and Instagram collection; build your own boards; see your library as clusters of themes or as a 3D map.
- **Study guides**: pick a board, a search result or a cluster and get a single distilled document (rendered as PDF) instead of rewatching dozens of reels.
- **Imports from Instagram's data export**, with resumable bulk import, retry handling for posts Instagram refuses to serve, and manual upload as a last resort.
- **Configurable taxonomy**: categories, languages and a few personal lists live in a JSON config file you can export and import (see [Configuration](docs/CONFIGURATION.md)).

## How it fits together

| Folder | What it is |
|---|---|
| `backend/` | Python / FastAPI server. Runs the analysis pipeline and owns the SQLite database. Everything else talks to it over HTTP. |
| `serendipid-web/` | Next.js web app for browsing, searching, chatting, study guides and running imports. Password protected. |
| `serendipid-ios/` | Native iOS app with a share extension. Currently behind the backend (see [TODO](TODO.md)). |
| `serendipid-extension/` | Chrome extension that imports Instagram saved posts and collections straight from the browser. |
| `docs/` | Architecture, configuration and deployment notes. |

The backend and the web app do not need to run on the same machine. The web app only needs to reach the backend's URL; browsers only ever talk to the web app.

## AI providers

The backend routes every model call through a fallback chain, so a rate limit or an outage on one provider moves on to the next. Faster providers are promoted over time. You only need keys for the providers you want to use.

| Task | Order |
|---|---|
| Text analysis | OpenAI → Anthropic → Groq → Gemini → OpenRouter (curated free models) → OpenRouter (discovered free models) → Ollama |
| Vision | OpenAI → Anthropic → Gemini → Groq → OpenRouter → Ollama |
| Transcription | Groq Whisper API → local Whisper |
| YouTube | Gemini (native video URL understanding) |

OpenAI and Anthropic are only tried when their keys are set. Without them, analysis runs on the free tiers of Groq, Gemini and OpenRouter, with local Ollama as a last resort.

**Some features require an OpenAI key.** Study guides, importance scoring, embeddings (and therefore semantic search, related posts and chat retrieval), eloquence scoring and `ANALYSIS_MODE=batch` currently call OpenAI directly with no fallback. Analysis itself works without it. Removing this requirement is on the [TODO list](TODO.md).

## Requirements

- Python 3.10 or newer, and `ffmpeg`
- Node.js 20 or newer (for the web app)
- At least one AI provider key: OpenAI, Anthropic, Groq, Gemini or OpenRouter. Groq and Gemini have free tiers; Groq is also used for transcription.
- Optional: an Instagram account for downloading. A secondary account is strongly recommended over your main one, since Instagram rate-limits and can flag automated downloads.

## Installation

### 1. Backend

```bash
git clone https://github.com/jorgelso/serendipid.git
cd serendipid/backend
python3 start.py
```

`start.py` is a setup wizard. On the first run it creates a virtual environment, installs dependencies, asks for your AI provider keys, optionally sets up Ollama, local Whisper and remote access, and generates the API access token. Then it starts the server on port 5050. Later runs skip straight to starting the server; `python3 start.py --reset` runs the wizard again.

The access token is how every client authenticates. To see it:

```bash
.venv/bin/python utils/manage_token.py show
```

Check that the backend is up with `curl http://localhost:5050/ping`. Interactive API docs are at `http://localhost:5050/docs`.

To run it with Docker instead, see [Docker](#docker) below.

### 2. Web app

```bash
cd serendipid/serendipid-web
npm install
cp .env.example .env.local
```

Edit `.env.local`:

```bash
SERENDIPID_API_URL=http://localhost:5050   # wherever the backend is reachable from this machine
SERENDIPID_API_KEY=<the access token>
WEB_PASSWORD=<a password for signing in>
```

Then build and start it:

```bash
npm run build
npm run start      # http://localhost:3000
```

Use `npm run dev` while developing. Sign-in sessions last three weeks; changing `WEB_PASSWORD` signs everyone out.

### 3. Your configuration (optional)

Out of the box Serendipid uses a general-purpose list of categories and languages. To change them, or to set up trusted creators and hidden folders, create `backend/config/user_config.json`. The format, and how to export and import it, is described in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Importing from Instagram

Serendipid reads Instagram's own data export. You only need your saved posts, not a full copy of your account.

1. In Instagram, open **Settings → Accounts Center → Your information and permissions → Export your information**, then **Create export**.
2. Pick your Instagram profile and choose **Export to device**.
3. Under **Customize information**, deselect everything except **Saved** (under *Your Instagram activity*). A full export is much larger and takes far longer for Instagram to prepare.
4. Set **Date range** to **All time**. Any shorter range silently leaves out older saves.
5. Set **Format** to **JSON**. Media quality does not matter.
6. Start the export. Instagram emails you when it is ready, which can take from minutes to a couple of days.

The download contains two files under `your_instagram_activity/saved/`:

- `saved_collections.json`: your saved posts grouped by collection. **This is the file that drives the import.** Only posts that are in at least one collection are analyzed, so put the posts you care about into collections on Instagram first.
- `saved_posts.json`: every saved post with the date you saved it. Optional; when provided, it is used to record real save dates.

Upload both on the web app's **Admin** page. It previews how many posts each collection contains, lets you choose a collection to process first, and runs the import in the background. You can also run it from the command line:

```bash
cd backend
.venv/bin/python scripts/import_saved_instagram.py path/to/saved_collections.json --all-posts-file path/to/saved_posts.json
```

Imports are resumable: running the same files again skips everything already analyzed, so you can stop and restart at any time.

### Keeping it up to date automatically

Instagram can repeat the export on a schedule. Instead of **Export to device**, choose **Export to external service** and connect Google Drive or Dropbox, then set the frequency to **Weekly**. Each week a fresh export lands in that folder. Importing the newest files analyzes only the posts you saved since the last run.

## Docker

The backend ships with a Dockerfile and a compose file. Docker keeps the database, media, token and config on named volumes, so rebuilding the container does not lose anything.

```bash
cd backend
cp .env.example .env          # add your AI provider keys
docker compose up -d --build
docker compose exec serendipid-api python utils/manage_token.py show
```

The image does not include local Whisper or Ollama; transcription uses Groq's API, so set `GROQ_API_KEY`. Settings that `start.py` takes as flags are environment variables in Docker (`SERENDIPID_SHOW_SENSITIVE`, `SERENDIPID_PREFERRED_PROVIDER`); all of them are listed in `backend/.env.example`.

## Hosting on a Raspberry Pi

A Raspberry Pi 4 or 5 with 4 GB of RAM or more works well as an always-on server. Analysis is mostly network calls to AI providers, so the Pi's CPU is rarely the bottleneck; skip local Whisper and Ollama on it and use the cloud providers.

1. **Install the OS.** Flash 64-bit Raspberry Pi OS Lite with Raspberry Pi Imager, enable SSH in the imager's settings, and boot. Then:

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y git python3-venv python3-dev ffmpeg
   ```

2. **Install the backend.**

   ```bash
   git clone https://github.com/jorgelso/serendipid.git ~/serendipid
   cd ~/serendipid/backend
   python3 start.py
   ```

   Answer "no" to the Ollama and local Whisper steps. When the server starts, stop it with Ctrl+C; the next step runs it as a service.

3. **Run it as a service** so it starts on boot and restarts after crashes. Create `/etc/systemd/system/serendipid.service`, replacing `pi` with your username:

   ```ini
   [Unit]
   Description=Serendipid backend
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=pi
   WorkingDirectory=/home/pi/serendipid/backend
   ExecStart=/home/pi/serendipid/backend/.venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 5050
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now serendipid
   journalctl -u serendipid -f        # logs
   ```

4. **Run the web app.** Either on the Pi itself (install Node.js 20+, then follow the web app steps above and add a second unit with `ExecStart=/usr/bin/npm run start` and `WorkingDirectory=/home/pi/serendipid/serendipid-web`), or on any other host such as Vercel, pointing `SERENDIPID_API_URL` at the Pi.

5. **Reach it from outside your home.** The simplest private option is [Tailscale](https://tailscale.com): install it on the Pi and on your devices and use the Pi's Tailscale address, with no ports opened on your router. If you expose the web app publicly, put it behind HTTPS (for example with Caddy or a Cloudflare Tunnel); the backend itself does not need to be public, since only the web app talks to it.

6. **Update** with the included script, which pulls the latest code, refreshes dependencies and restarts the service:

   ```bash
   ~/serendipid/backend/deploy.sh
   # also rebuild and restart the web app if it runs on the Pi:
   SERENDIPID_WEB_SERVICE=serendipid-web ~/serendipid/backend/deploy.sh
   ```

Docker also works on the Pi (`docker compose up -d --build` in `backend/`), if you prefer it to a virtual environment.

## Security model

Serendipid is a single-user app designed for a home network or a private network such as Tailscale.

- Every backend endpoint that reads or changes data, including media files, requires the access token in the `X-API-Key` header.
- The web app is behind a password and holds the token server-side; browsers never see it and never contact the backend directly.
- `GET /connect-info`, which hands out the token for QR-code pairing of the mobile app, only answers direct requests from the local network.
- `ALLOWED_ORIGINS` restricts which browser origins may call the backend directly; it defaults to any origin without credentials.

If you open the backend's port to the internet, anyone who learns the token has full access to your library and your saved provider keys. Prefer a private network or exposing only the web app.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the pieces fit, the analysis pipeline, and the data model
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md): the config file, environment variables and API keys
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): running the backend and web app on separate hosts, Docker details, backups
- [docs/CHANGELOG.md](docs/CHANGELOG.md)
- [TODO.md](TODO.md): known gaps and planned work

## Contributing

Issues and pull requests are welcome.

1. Create a branch (or fork the repository if you don't have write access) and open a pull request against `main`. Direct pushes to `main` are blocked.
2. CI runs on every pull request: the backend is compiled and tested, the web app is linted, type-checked and built, and the backend Docker image is built. All three checks must pass.
3. The maintainer reviews and approves the pull request before it can be merged. New commits pushed after an approval need a fresh review.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, `docs:` and so on).

Every push to `main` that touches the backend publishes a Docker image to `ghcr.io/jorgelso/serendipid` (amd64 and arm64), so a server can pull it instead of building locally.

## Credits and license

Serendipid started as a fork of [SuperBrain](https://github.com/sidinsearch/superbrain) by Siddharth Shinde and has since been substantially extended and rewritten by Jorge Salcedo, beginning in August 2026: the web app, the iOS app, semantic search and chat, study guides, boards, importance and eloquence scoring, the Instagram export importer, the configuration system, and most of the analysis pipeline.

Licensed under the [GNU Affero General Public License v3.0](LICENSE), the same license as the original project. If you run a modified version as a network service, the AGPL requires you to make your source code available to its users.
