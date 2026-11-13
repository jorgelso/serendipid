# Configuration

Serendipid has three kinds of settings:

1. **The config file**: your taxonomy and personal lists (categories, languages, trusted creators, folders to skip or hide).
2. **API keys and secrets**: AI provider keys, the Instagram login, the access token.
3. **Environment variables**: runtime switches, mostly used with Docker.

## The config file

Two JSON files are merged at startup:

| File | Tracked in git | Purpose |
|---|---|---|
| `backend/core/default_config.json` | yes | Generic defaults that ship with Serendipid |
| `backend/config/user_config.json` | no | Your overrides |

Any top-level key in `user_config.json` replaces the default for that key entirely (lists are not merged item by item), and keys you leave out keep their default. You can point to a different file with the `SERENDIPID_CONFIG` environment variable.

### Keys

```json
{
  "version": 1,
  "categories": [
    { "name": "food", "keywords": ["recipe", "cooking", "restaurant"] },
    { "name": "fitness", "keywords": ["workout", "gym"] },
    { "name": "other", "keywords": [] }
  ],
  "languages": ["english", "spanish", "other", "no dialogue / visual only"],
  "trusted_authors": ["some_creator"],
  "trusted_creators": { "some_creator": "consistently useful study tips" },
  "excluded_import_folders": ["Send to friends"],
  "sensitive_folders": ["Private"],
  "priority_folder": "Important"
}
```

| Key | Type | Effect |
|---|---|---|
| `categories` | list of `{name, keywords}` | The labels the AI may assign (a post can get up to three). `keywords` are only used as a fallback when the model's answer can't be parsed. Names are lowercased. |
| `languages` | list of strings | The languages the AI may assign to a post's spoken or on-screen content. |
| `trusted_authors` | list of usernames | Posts from these accounts are added automatically to a "Trusted Authors" board when they are saved. |
| `trusted_creators` | object, username to reason | Posts from these accounts get an importance score of at least 4. The reason is stored with the score. |
| `excluded_import_folders` | list of folder names | Instagram collections that are never imported. A post saved only in one of them is skipped. |
| `sensitive_folders` | list of folder names | Collections that are imported but hidden from every client, and never used for recommendations. Start the backend with `--show-sensitive` (or `SERENDIPID_SHOW_SENSITIVE=1`) to show them. |
| `priority_folder` | string or null | The collection imported first in by-collection imports, and preselected on the web app's Admin page. |

Folder names are matched case-insensitively, ignoring surrounding spaces. The category `other` and the languages `other` and `no dialogue / visual only` are always present; they are added automatically if your list leaves them out.

### Exporting and importing

From the command line, in `backend/`:

```bash
.venv/bin/python scripts/config.py show                        # print the effective config
.venv/bin/python scripts/config.py export my-config.json       # save it to a file
.venv/bin/python scripts/config.py validate my-config.json     # check a file without applying it
.venv/bin/python scripts/config.py import my-config.json       # merge into user_config.json
.venv/bin/python scripts/config.py import my-config.json --replace   # make it the whole user config
```

A running server reads the config at startup, so restart it after a CLI import. Imports through the API apply immediately:

| Endpoint | Description |
|---|---|
| `GET /config` | The effective config, in the same shape import accepts |
| `GET /config/export` | The same, as a downloadable `serendipid-config.json` |
| `GET /config/default` | The shipped defaults only |
| `POST /config/import` | Body `{"config": {...}, "replace": false}`. Validates, saves to `user_config.json` and applies it. Returns 400 with a message on invalid input. |

`GET /categories` also returns the configured category and language lists, for clients that offer them in a picker.

### Changing categories on an existing library

Posts keep the categories and languages they were analyzed with. After changing the lists, re-analyze posts to reclassify them; the web app's post menu and `scripts/rescan_post.py` do this without downloading the media again.

## API keys and secrets

When you run the backend with `start.py`, the setup wizard stores keys in `backend/config/.api_keys`. You can also edit that file by hand (see `backend/config/.api_keys.example`) or set the same names as environment variables, which take precedence. With Docker, put them in `backend/.env`.

| Name | Used for |
|---|---|
| `OPENAI_API_KEY` | Analysis (tried first when set), plus study guides, importance scoring, embeddings, eloquence scoring and batch mode, which currently require it |
| `ANTHROPIC_API_KEY` | Analysis, tried after OpenAI |
| `GROQ_API_KEY` | Analysis and audio transcription (Whisper) |
| `GEMINI_API_KEY` | Analysis, vision, YouTube understanding, chat |
| `OPENROUTER_API_KEY` | Analysis through free OpenRouter models |
| `OPENAI_CHAT_API_KEY` | Optional separate key for the chat feature's answer step |
| `INSTAGRAM_USERNAME`, `INSTAGRAM_PASSWORD` | Optional login for downloading posts. Use a secondary account. |

The **access token** lives in `backend/token.txt` (or the path in `SERENDIPID_TOKEN_FILE`). It is generated on first start and is not written to the server log. View or replace it with:

```bash
.venv/bin/python utils/manage_token.py show
.venv/bin/python utils/manage_token.py rotate   # then restart and update every client
```

## Environment variables

### Backend

| Variable | Default | Description |
|---|---|---|
| `DATABASE_PATH` | `backend/serendipid.db` | SQLite database file |
| `MEDIA_DIR` | `backend/media` | Where downloaded videos, audio and images are kept |
| `SERENDIPID_TOKEN_FILE` | `backend/token.txt` | Access token file |
| `SERENDIPID_CONFIG` | `backend/config/user_config.json` | Your config file |
| `ALLOWED_ORIGINS` | any origin, no credentials | Comma-separated browser origins allowed by CORS |
| `ANALYSIS_MODE` | `immediate` | `batch` sends OpenAI calls through the Batch API: about half the cost, results within 24 hours |
| `OPENAI_TEXT_MODEL` | `gpt-4.1` | OpenAI model used by the router |
| `ANTHROPIC_TEXT_MODEL` | `claude-sonnet-5-5` | Anthropic model used by the router |
| `SERENDIPID_PREFERRED_PROVIDER` | none | Rank one provider first: `openai`, `anthropic`, `groq`, `gemini`, `openrouter` or `ollama` (same as `start.py --prefer`) |
| `SERENDIPID_SHOW_SENSITIVE` | `0` | `1` serves posts from sensitive folders (same as `start.py --show-sensitive`) |
| `ANALYSIS_SUBPROCESS_TIMEOUT` | `1200` | Seconds before a single Instagram analysis is stopped |

### Web app

| Variable | Description |
|---|---|
| `SERENDIPID_API_URL` | Backend base URL, as reachable from the web server |
| `SERENDIPID_API_KEY` | The access token |
| `WEB_PASSWORD` | Sign-in password (required) |
