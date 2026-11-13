# serendipid-web

The Serendipid web app: browse, search, chat with and organize the posts your backend has analyzed, and run Instagram imports from the browser.

It talks to the backend only from the server side. The backend URL and access token stay on the server, media is streamed through this app, and every page sits behind a password, so the backend never has to be reachable from a browser.

## Setup

Requires Node.js 20 or newer and a running backend (see the [root README](../README.md)).

```bash
npm install
cp .env.example .env.local
```

| Variable | Description |
|---|---|
| `SERENDIPID_API_URL` | Base URL of the backend as seen from this server, for example `http://localhost:5050` or a Tailscale address. |
| `SERENDIPID_API_KEY` | The backend access token (`python utils/manage_token.py show` in `backend/`). |
| `WEB_PASSWORD` | Password for signing in. Required. Sessions last three weeks; changing it signs everyone out. |

```bash
npm run dev        # development server on http://localhost:3000
npm run build      # production build
npm run start      # serve the production build
npm run lint
```

## Pages

| Route | What it shows |
|---|---|
| `/` | Most recently analyzed posts |
| `/browse` | Filter by category, language and Instagram collection; sort by date, save date or importance |
| `/search` | Semantic search, with the option to turn the results into a study guide |
| `/chat` | Ask questions answered from your library |
| `/space` | Every post plotted in 3D by meaning, colored by theme |
| `/insights` | Themes, categories and other statistics |
| `/ideas` | Recurring topics across your posts |
| `/boards` | Your own collections of posts, with optional sub-collections |
| `/study-guides` | Generated study guides, rendered as PDF |
| `/eloquent` | Posts judged well spoken, with a review queue |
| `/versions` | Posts analyzed by older versions of the pipeline |
| `/admin` | Instagram imports, stuck downloads, batch checks and eloquence scoring |

## Deploying

The app can run anywhere Next.js runs: on the same machine as the backend, on a Raspberry Pi, or on a host like Vercel. Set the three variables above in that environment. If it is reachable from the internet, serve it over HTTPS; the session cookie is marked secure automatically when the request arrives over HTTPS.
