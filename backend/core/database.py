#!/usr/bin/env python3
"""
SQLite Database Manager for SuperBrain
Handles caching and retrieval of Instagram analysis results
Self-hosted, zero-config, file-based database
"""

import sqlite3
import json
import os
import uuid
from pathlib import Path
from datetime import datetime

# Database file path can be overridden for Docker deployments
DB_PATH = Path(os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parent.parent / 'superbrain.db')))

# Bump this whenever a change to the analysis pipeline is significant enough
# that previously-saved posts are worth a human re-look (e.g. a prompt
# rewrite, a taxonomy overhaul). Every post saved by the pipeline is stamped
# with the version current at save time; any post whose stamped version is
# behind this constant is flagged 'needs_review' so the frontend can surface
# it as a review queue — without forcing a costly automatic re-analysis.
#   1 — 2026-08-08: category taxonomy overhaul (multi-label, ~20 categories
#       replacing the old rigid 9-category forced single-choice).
#   2 — 2026-08-08: added content language detection (English/German/Italian/
#       Spanish/other/no dialogue), derived from audio transcription + on-screen
#       text — explicitly not from the post caption, which is unreliable.
#   3 — 2026-08-08: post media (video/audio/thumbnail) is now relocated to
#       permanent storage under media/<shortcode>/ instead of being left in
#       temp/. Posts stamped below this version have no media_files recorded
#       — their original download still sits in temp/ (or is gone) and needs
#       a migration pass before a "watch original video" screen can use them.
#   4 — 2026-08-09: added 4 categories for conspiracy/surveillance and
#       lifestyle/health content the taxonomy didn't cover: "surveillance,
#       psyops & government conspiracy", "lifestyle & clean living",
#       "ai ethics & tech skepticism", "environment & sustainability".
#   5 — 2026-08-09: added 7 categories for personal/lifestyle content the
#       taxonomy didn't cover: "fashion & style", "beauty & skincare",
#       "money & finance", "home & interior design", "relationships &
#       dating", "pets & animals", "career & productivity".
#   6 — 2026-08-09: added importance scoring — a 1-5 rating of how much
#       lasting/reusable value a post has (see core/importance.py), so posts
#       can be sorted by "worth revisiting" instead of only by recency.
#       Posts stamped below this version have no importance score yet; run
#       scripts/score_importance.py to backfill them without a full re-analysis.
#   7 — 2026-08-09: fixed caption/media mismatch handling in the summary
#       prompt (main.py generate_final_summary). Some accounts pair a caption
#       about one topic with an unrelated "hook" video purely to farm reach;
#       the model now explicitly classifies the caption against the visual/
#       audio/text analysis as CONSISTENT, GENUINE MISMATCH, or UNCLEAR
#       before writing the title/summary/tags, instead of a single buried
#       instruction the model was prone to ignore in favor of the caption.
#       Thin/generic media (a short clip, a single ambient shot) is treated
#       as UNCLEAR and still trusts the caption normally — only media that
#       affirmatively shows a different, specific, self-contained subject
#       counts as a mismatch. On a genuine mismatch, the summary now states
#       the discrepancy instead of silently building the title/tags from an
#       unrelated caption. Posts stamped below this version may have a
#       title/summary built from a mismatched caption without any indication
#       of the mismatch; re-flagged for review, but fixing requires a full
#       re-analysis (re-download + re-run the pipeline), not a cheap backfill.
#   8 — 2026-08-10: fixed importance scoring going out on its own. Importance
#       is now scored in a dedicated LLM call (core/importance.py's
#       build_importance_prompt() + ModelRouter.generate_importance_text())
#       instead of being one field in the combined title/summary/tags/...
#       prompt, and that call is pinned to OpenAI GPT-4.1 specifically rather
#       than whichever provider the latency-ranked router happened to answer
#       fastest. The rubric also gained an explicit guard against charged
#       political/emotional vocabulary reading as depth — a real miss where
#       a meme that only named a political irony scored higher than a video
#       that actually explained a law's mechanism prompted this. Posts
#       stamped below this version have importance scores from the old,
#       demonstrably inconsistent method; run
#       `python scripts/score_importance.py --force` to re-score every post
#       (not just unscored ones) without a full re-analysis.
# This history is also kept queryable in the analysis_changelog table (see
# _seed_changelog() below) rather than only living as a comment.
CURRENT_ANALYSIS_VERSION = 8


class Database:
    """SQLite database manager with caching functionality"""

    def __init__(self):
        self.db_path = DB_PATH
        self._conn = None
        self._connect()

    def _connect(self):
        try:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # WAL mode for better concurrent read performance
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._create_tables()
            print(f"[OK] Connected to SQLite database: {self.db_path}")
        except Exception as e:
            print(f"[WARNING] SQLite connection failed: {e}")
            self._conn = None

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS analyses (
                shortcode           TEXT PRIMARY KEY,
                url                 TEXT,
                username            TEXT,
                content_type        TEXT DEFAULT 'instagram',
                analyzed_at         TEXT,
                updated_at          TEXT,
                post_date           TEXT,
                likes               INTEGER DEFAULT 0,
                thumbnail           TEXT DEFAULT '',
                title               TEXT,
                summary             TEXT,
                tags                TEXT,
                music               TEXT,
                category            TEXT,
                visual_analysis     TEXT,
                audio_transcription TEXT,
                text_analysis       TEXT
            );

            CREATE TABLE IF NOT EXISTS processing_queue (
                shortcode   TEXT PRIMARY KEY,
                url         TEXT,
                status      TEXT DEFAULT 'queued',
                position    INTEGER,
                added_at    TEXT,
                started_at  TEXT,
                updated_at  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_analyses_category    ON analyses (category);
            CREATE INDEX IF NOT EXISTS idx_analyses_analyzed_at ON analyses (analyzed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_queue_status         ON processing_queue (status);
            CREATE INDEX IF NOT EXISTS idx_queue_position       ON processing_queue (position);
        """)
        self._conn.commit()

        # Migration: add content_type to databases that predate this column
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN content_type TEXT DEFAULT 'instagram'")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists – expected on most runs

        # Migration: add thumbnail column
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN thumbnail TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add source_hashtags column — original hashtags from the
        # source platform (e.g. Instagram export), kept separate from the
        # AI-generated 'tags' column so both are independently searchable.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN source_hashtags TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add embedding column — JSON-encoded float vector
        # (OpenAI text-embedding-3-small) generated from title+summary+tags,
        # used for semantic search / similarity. Brute-force cosine
        # similarity in Python is fast enough at this dataset's scale, so no
        # vector-search extension (e.g. sqlite-vec) is needed.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN embedding TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add retry columns to processing_queue
        for _col, _dflt in [
            ("retry_after",  "TEXT"),
            ("attempts",     "INTEGER DEFAULT 0"),
            ("reason",       "TEXT"),
            ("content_type", "TEXT"),
            # Client-supplied caption/hashtags hint (see AnalyzeRequest) — kept
            # on the queue row so a busy server queuing the request doesn't
            # drop this context before queue_worker eventually spawns main.py.
            ("caption",      "TEXT"),
            ("hashtags",     "TEXT"),
        ]:
            try:
                self._conn.execute(
                    f"ALTER TABLE processing_queue ADD COLUMN {_col} {_dflt}"
                )
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # already exists

        try:
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_retry ON processing_queue (status, retry_after)"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Create content_type index only after the column is guaranteed to exist
        try:
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analyses_content_type ON analyses (content_type)"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add is_hidden for soft-delete support
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN is_hidden INTEGER DEFAULT 0")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add analysis_version — see CURRENT_ANALYSIS_VERSION above.
        # Existing rows default to 0, so they're automatically flagged
        # 'needs_review' relative to any versioned pipeline change.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN analysis_version INTEGER DEFAULT 0")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add language — JSON array of content language(s), same
        # storage pattern as category. See core/languages.py.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN language TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add media_files — JSON array of filenames permanently
        # stored under media/<shortcode>/ (video, extracted audio, thumbnail,
        # or numbered carousel items). See core/media_store.py. Empty for
        # posts with no locally-downloaded media (YouTube, web pages).
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN media_files TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add importance — 1-5 rating of how much lasting/reusable
        # value a post has (see core/importance.py). NULL (not 0) for posts
        # saved before this feature existed or where the model's field was
        # unparseable, so "no score yet" is distinguishable from "scored low".
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN importance INTEGER DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Collections table
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS collections (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                icon        TEXT DEFAULT '📁',
                post_ids    TEXT DEFAULT '[]',
                created_at  TEXT,
                updated_at  TEXT
            );
        """)
        self._conn.commit()
        # Seed default Watch Later if missing
        cur = self._conn.cursor()
        cur.execute("SELECT id FROM collections WHERE id = 'default_watch_later'")
        if cur.fetchone() is None:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO collections (id, name, icon, post_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ('default_watch_later', 'Watch Later', 'time', '[]', now, now)
            )
            self._conn.commit()

        # Migration: normalize Watch Later icon to Ionicons-safe name
        try:
            self._conn.execute(
                "UPDATE collections SET icon = 'time' WHERE id = 'default_watch_later' AND (icon IS NULL OR icon = '' OR icon = '⏰' OR icon = 'clock')"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Deleted-log table — tracks when posts are soft-deleted so the
        # mobile app can sync deletions via /sync/deleted.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS deleted_log (
                shortcode   TEXT PRIMARY KEY,
                deleted_at  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_deleted_log_at ON deleted_log (deleted_at);
        """)
        self._conn.commit()

        # Analysis changelog — queryable "what's new" history for the
        # analysis pipeline/taxonomy, keyed by ANALYSIS_VERSION. Mirrors the
        # comment block above CURRENT_ANALYSIS_VERSION so the history can be
        # served over the API instead of only living in source comments.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS analysis_changelog (
                version      INTEGER PRIMARY KEY,
                released_at  TEXT,
                title        TEXT,
                description  TEXT
            );
        """)
        self._conn.commit()
        self._seed_changelog()

        # RAG chatbot — persisted multi-turn conversations. sources is a
        # JSON-encoded array of {shortcode, similarity, title, url, username,
        # thumbnail} for the posts an assistant reply drew on (empty for user
        # messages).
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_threads (
                id          TEXT PRIMARY KEY,
                title       TEXT,
                created_at  TEXT,
                updated_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          TEXT PRIMARY KEY,
                thread_id   TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                sources     TEXT DEFAULT '[]',
                created_at  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages (thread_id, created_at);
        """)
        self._conn.commit()

    def _seed_changelog(self):
        """Seed analysis_changelog with the known version history. Uses
        INSERT OR IGNORE so re-running on an existing DB is a no-op, and new
        versions can just be appended here going forward."""
        entries = [
            (0, None, "Original single-choice taxonomy",
             "Baseline pipeline, predating the analysis_version column itself "
             "(existing rows default to this version). Category was a single "
             "plain-string value, auto-picked by keyword-count scoring from a "
             "fixed 10-item set: product, places, software, book, tv shows, "
             "fitness, film, event, food, other. No language detection; no "
             "permanent media storage (downloads stayed in temp/)."),
            (1, "2026-08-08", "Multi-label category taxonomy overhaul",
             "Replaced the old rigid 9-category forced single-choice system "
             "with a multi-label taxonomy of ~20 categories — a post can now "
             "genuinely belong to more than one category."),
            (2, "2026-08-08", "Content language detection",
             "Added content language detection (English/German/Italian/"
             "Spanish/other/no dialogue), derived from audio transcription + "
             "on-screen text — explicitly not from the post caption, which is "
             "unreliable."),
            (3, "2026-08-08", "Permanent media storage",
             "Post media (video/audio/thumbnail) is now relocated to permanent "
             "storage under media/<shortcode>/ instead of being left in temp/. "
             "Posts stamped below this version have no media_files recorded — "
             "their original download still sits in temp/ (or is gone) and "
             "needs a migration pass before a \"watch original video\" screen "
             "can use them."),
            (4, "2026-08-09", "Conspiracy/surveillance and lifestyle categories",
             "Added 4 categories for content the taxonomy didn't cover: "
             "\"surveillance, psyops & government conspiracy\", \"lifestyle & "
             "clean living\", \"ai ethics & tech skepticism\", \"environment & "
             "sustainability\"."),
            (5, "2026-08-09", "Fashion, beauty and lifestyle categories",
             "Added 7 categories for personal/lifestyle content the taxonomy "
             "didn't cover: \"fashion & style\", \"beauty & skincare\", "
             "\"money & finance\", \"home & interior design\", "
             "\"relationships & dating\", \"pets & animals\", \"career & "
             "productivity\"."),
            (6, "2026-08-09", "Importance scoring",
             "Added a 1-5 importance score rating how much lasting/reusable "
             "value a post has, judged on depth of payload (a fully-explained "
             "technique or a genuinely developed idea) rather than topic or "
             "format — a meme can score high if real insight can be drawn "
             "from it, and a \"serious\"-sounding post can score low if it "
             "only shows off or namedrops. Posts stamped below this version "
             "have no score yet; run scripts/score_importance.py to backfill "
             "them from already-stored data without a full re-analysis."),
            (7, "2026-08-09", "Caption/media mismatch detection",
             "Some accounts pair a caption about one topic with an unrelated "
             "\"hook\" video purely to farm reach (e.g. a caption about a "
             "celebrity event on a video that actually shows an unrelated "
             "screenshot). The summary prompt now explicitly classifies the "
             "caption against the visual/audio/text analysis as CONSISTENT, "
             "GENUINE MISMATCH, or UNCLEAR before writing anything — a short "
             "or generic clip with the real info in the caption (very common "
             "and legitimate) is UNCLEAR/CONSISTENT and still trusts the "
             "caption normally; only media that affirmatively shows a "
             "different, specific, self-contained subject counts as a "
             "mismatch. On a genuine mismatch the summary now states the "
             "discrepancy instead of silently building the title/tags from "
             "an unrelated caption. Posts stamped below this version may "
             "have a title/summary built from a mismatched caption with no "
             "indication of the mismatch; fixing them needs a full "
             "re-analysis (re-download + re-run), not a cheap backfill."),
            (8, "2026-08-10", "Importance scoring fix",
             "Importance is now scored in its own dedicated LLM call (see "
             "core/importance.py) instead of being one field in the combined "
             "title/summary/tags/... prompt, and that call is pinned to "
             "OpenAI GPT-4.1 specifically instead of whichever provider the "
             "latency-ranked router happened to answer fastest. The rubric "
             "also gained an explicit guard against charged political/"
             "emotional vocabulary reading as depth — a real miss where a "
             "meme that only named a political irony scored higher than a "
             "video that actually explained a law's mechanism prompted this "
             "change. Posts stamped below this version have importance "
             "scores from the old, demonstrably inconsistent method; run "
             "`python scripts/score_importance.py --force` to re-score "
             "every post (not just unscored ones) without a full "
             "re-analysis."),
        ]
        for version, released_at, title, description in entries:
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO analysis_changelog (version, released_at, title, description) VALUES (?, ?, ?, ?)",
                    (version, released_at, title, description)
                )
            except sqlite3.OperationalError:
                pass
        self._conn.commit()

    def get_changelog(self) -> list:
        """Return the analysis pipeline/taxonomy changelog, newest version first."""
        cur = self._conn.cursor()
        cur.execute("SELECT version, released_at, title, description FROM analysis_changelog ORDER BY version DESC")
        return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Columns safe to send to the mobile app (excludes heavy analysis blobs)
    LIGHT_COLUMNS = (
        "shortcode, url, username, content_type, analyzed_at, updated_at, "
        "post_date, likes, thumbnail, title, summary, tags, music, category, "
        "language, is_hidden, analysis_version, media_files, importance"
    )

    def _row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        if d.get('tags'):
            try:
                d['tags'] = json.loads(d['tags'])
            except Exception:
                d['tags'] = []
        else:
            d['tags'] = []
        if d.get('source_hashtags'):
            try:
                d['source_hashtags'] = json.loads(d['source_hashtags'])
            except Exception:
                d['source_hashtags'] = []
        else:
            d['source_hashtags'] = []
        if d.get('category'):
            try:
                parsed_cat = json.loads(d['category'])
                d['category'] = parsed_cat if isinstance(parsed_cat, list) else [str(parsed_cat)]
            except Exception:
                # Legacy rows: category was stored as a plain string before
                # multi-category support — treat it as a single-item list.
                d['category'] = [d['category']]
        else:
            d['category'] = []
        if d.get('language'):
            try:
                parsed_lang = json.loads(d['language'])
                d['language'] = parsed_lang if isinstance(parsed_lang, list) else [str(parsed_lang)]
            except Exception:
                d['language'] = [d['language']]
        else:
            d['language'] = []
        if d.get('media_files'):
            try:
                parsed_media = json.loads(d['media_files'])
                d['media_files'] = parsed_media if isinstance(parsed_media, list) else [str(parsed_media)]
            except Exception:
                d['media_files'] = []
        else:
            d['media_files'] = []
        _sc = d.get('shortcode', '')
        d['media_urls'] = [f"/media/{_sc}/{f}" for f in d['media_files']] if _sc else []
        d['analysis_version'] = d.get('analysis_version') or 0
        d['needs_review'] = d['analysis_version'] < CURRENT_ANALYSIS_VERSION
        return d
    
    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def is_connected(self):
        return self._conn is not None

    # ------------------------------------------------------------------
    # Cache / Analyses
    # ------------------------------------------------------------------

    def check_cache(self, shortcode):
        """Return cached analysis dict or None."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM analyses WHERE shortcode = ?", (shortcode,))
            return self._row_to_dict(cur.fetchone())
        except Exception as e:
            print(f"[WARNING]  Cache lookup error: {e}")
            return None

    def save_analysis(self, shortcode, url, username, title, summary, tags, music, category,
                      visual_analysis="", audio_transcription="", text_analysis="",
                      likes=0, post_date=None, content_type="instagram", thumbnail="",
                      source_hashtags=None, embedding=None, analysis_version=None,
                      language=None, media_files=None, importance=None):
        """Insert or update an analysis record. Returns True on success.

        source_hashtags: original hashtags from the source platform (e.g. an
        Instagram export), stored separately from the AI-generated 'tags'
        column. Accepts a list or a pre-joined string.

        embedding: list of floats (OpenAI text-embedding-3-small output) or
        None if embedding generation wasn't available/failed for this post.

        analysis_version: defaults to CURRENT_ANALYSIS_VERSION — pass this
        default when the pipeline just produced this result. Bulk-import /
        restore callers should pass through the original stamped version (or
        0 if unknown) instead, so restoring an old backup doesn't silently
        mark posts as reviewed under the current pipeline.

        language: content language(s), e.g. ["german"] — see core/languages.py.
        Same list-or-comma-string acceptance as category.

        media_files: filenames now sitting under media/<shortcode>/ (from
        core.media_store.relocate_to_media_store), e.g. ["video.mp4",
        "audio.mp3", "thumbnail.jpg"]. Empty/None for posts with no locally
        downloaded media (YouTube, web pages).

        importance: 1-5 rating of lasting/reusable value (see
        core/importance.py), or None if unscored/unparseable — left NULL
        rather than guessed, same reasoning as language.
        """
        if not self.is_connected():
            print("[WARNING] Database not connected. Analysis not saved.")
            return False
        try:
            print(f"📝 Saving to database with shortcode: {shortcode}")
            now = datetime.utcnow().isoformat()
            tags_json = json.dumps(tags if isinstance(tags, list) else tags.split())
            source_hashtags_json = json.dumps(
                source_hashtags if isinstance(source_hashtags, list)
                else (source_hashtags.split() if source_hashtags else [])
            )
            embedding_json = json.dumps(embedding) if embedding else ""
            version = CURRENT_ANALYSIS_VERSION if analysis_version is None else analysis_version

            # category: a post can belong to more than one. Accept a list
            # (current pipeline) or a comma-separated/plain string (legacy
            # callers, bulk import) and store as a JSON array either way.
            if isinstance(category, list):
                category_list = [c.strip() for c in category if c and str(c).strip()]
            elif category:
                category_list = [c.strip() for c in str(category).split(',') if c.strip()]
            else:
                category_list = []
            category_json = json.dumps(category_list)

            # language: same shape as category — accept a list or a
            # comma-separated/plain string, store as a JSON array.
            if isinstance(language, list):
                language_list = [l.strip() for l in language if l and str(l).strip()]
            elif language:
                language_list = [l.strip() for l in str(language).split(',') if l.strip()]
            else:
                language_list = []
            language_json = json.dumps(language_list)

            # media_files: filenames relocated under media/<shortcode>/. Same
            # list-or-comma-string acceptance; empty/absent on this call
            # doesn't wipe out media a previous save already recorded (same
            # protective pattern as embedding below) — a metadata-only re-save
            # shouldn't look like the media disappeared.
            if isinstance(media_files, list):
                media_files_list = [m.strip() for m in media_files if m and str(m).strip()]
            elif media_files:
                media_files_list = [m.strip() for m in str(media_files).split(',') if m.strip()]
            else:
                media_files_list = []
            media_files_json = json.dumps(media_files_list)

            self._conn.execute("""
                INSERT INTO analyses
                    (shortcode, url, username, content_type, analyzed_at, updated_at, post_date, likes,
                     thumbnail, title, summary, tags, music, category,
                     visual_analysis, audio_transcription, text_analysis, source_hashtags, embedding,
                     analysis_version, language, media_files, importance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    url                 = excluded.url,
                    username            = excluded.username,
                    content_type        = excluded.content_type,
                    updated_at          = excluded.updated_at,
                    post_date           = excluded.post_date,
                    likes               = excluded.likes,
                    thumbnail           = excluded.thumbnail,
                    title               = excluded.title,
                    summary             = excluded.summary,
                    tags                = excluded.tags,
                    music               = excluded.music,
                    category            = excluded.category,
                    visual_analysis     = excluded.visual_analysis,
                    audio_transcription = excluded.audio_transcription,
                    text_analysis       = excluded.text_analysis,
                    source_hashtags     = excluded.source_hashtags,
                    embedding           = CASE WHEN excluded.embedding != '' THEN excluded.embedding ELSE analyses.embedding END,
                    analysis_version    = excluded.analysis_version,
                    language            = excluded.language,
                    media_files         = CASE WHEN excluded.media_files != '[]' THEN excluded.media_files ELSE analyses.media_files END,
                    importance          = CASE WHEN excluded.importance IS NOT NULL THEN excluded.importance ELSE analyses.importance END
            """, (shortcode, url, username, content_type, now, now, post_date, likes,
                  thumbnail, title, summary, tags_json, music, category_json,
                  visual_analysis, audio_transcription, text_analysis, source_hashtags_json, embedding_json,
                  version, language_json, media_files_json, importance))
            self._conn.commit()
            print(f"[OK] Analysis saved to database ({shortcode})")
            return True
        except Exception as e:
            print(f"[WARNING]  Error saving to database: {e}")
            import traceback
            traceback.print_exc()
            return False

    def update_embedding(self, shortcode, embedding) -> bool:
        """Set (or overwrite) just the embedding for an existing post — used
        by the backfill script so it doesn't need to re-run full analysis."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute(
                "UPDATE analyses SET embedding = ? WHERE shortcode = ?",
                (json.dumps(embedding), shortcode),
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error updating embedding: {e}")
            return False

    def update_importance(self, shortcode, importance) -> bool:
        """Set the importance score for an existing post and stamp it as
        reviewed under CURRENT_ANALYSIS_VERSION — used by the backfill
        script so it doesn't need to re-run full analysis. Bumping the
        version here is what clears the post from the 'needs_review' queue
        the version-6 bump otherwise flagged it into."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute(
                "UPDATE analyses SET importance = ?, analysis_version = ? WHERE shortcode = ?",
                (importance, CURRENT_ANALYSIS_VERSION, shortcode),
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error updating importance: {e}")
            return False

    def get_posts_missing_importance(self, include_scored: bool = False):
        """Return [{shortcode, username, title, summary, tags, category}, ...]
        for posts to (re-)score — used by the backfill script.

        By default only posts with no score yet (importance IS NULL).
        Pass include_scored=True to return every post, e.g. to re-score the
        whole library after a rubric/prompt change (see CURRENT_ANALYSIS_VERSION
        history) rather than only filling in gaps.
        """
        if not self.is_connected():
            return []
        try:
            query = "SELECT shortcode, username, title, summary, tags, category FROM analyses"
            if not include_scored:
                query += " WHERE importance IS NULL"
            cur = self._conn.execute(query)
            out = []
            for shortcode, username, title, summary, tags_json, category_json in cur.fetchall():
                try:
                    tags = json.loads(tags_json) if tags_json else []
                except Exception:
                    tags = []
                try:
                    category = json.loads(category_json) if category_json else []
                except Exception:
                    category = []
                out.append({
                    "shortcode": shortcode, "username": username, "title": title,
                    "summary": summary, "tags": tags, "category": category,
                })
            return out
        except Exception as e:
            print(f"[WARNING]  Error fetching posts missing importance: {e}")
            return []

    def get_posts_missing_embedding(self):
        """Return [{shortcode, title, summary, tags: [...]}, ...] for every
        post that doesn't have an embedding yet — used by the backfill script."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.execute(
                "SELECT shortcode, title, summary, tags FROM analyses "
                "WHERE embedding IS NULL OR embedding = ''"
            )
            out = []
            for shortcode, title, summary, tags_json in cur.fetchall():
                try:
                    tags = json.loads(tags_json) if tags_json else []
                except Exception:
                    tags = []
                out.append({"shortcode": shortcode, "title": title, "summary": summary, "tags": tags})
            return out
        except Exception as e:
            print(f"[WARNING]  Error fetching posts missing embedding: {e}")
            return []

    def get_all_embeddings(self):
        """Return [{shortcode, embedding: [float,...]}] for every post that
        has one — used by the semantic search endpoint."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.execute(
                "SELECT shortcode, embedding FROM analyses "
                "WHERE embedding IS NOT NULL AND embedding != '' "
                "AND (is_hidden IS NULL OR is_hidden = 0)"
            )
            out = []
            for shortcode, emb_json in cur.fetchall():
                try:
                    out.append({"shortcode": shortcode, "embedding": json.loads(emb_json)})
                except Exception:
                    continue
            return out
        except Exception as e:
            print(f"[WARNING]  Error fetching embeddings: {e}")
            return []
    
    def get_recent(self, limit=10):
        """Return the most recently analysed posts (excludes soft-deleted)."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM analyses WHERE (is_hidden IS NULL OR is_hidden = 0) ORDER BY analyzed_at DESC LIMIT ?", (limit,)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error retrieving recent: {e}")
            return []

    def get_recent_light(self, limit=50, offset=0, sort="recent"):
        """Return recent posts with only UI-essential fields (no analysis blobs).

        sort: "recent" (default, analyzed_at DESC) or "importance" (importance
        DESC, unscored posts last, analyzed_at DESC as tie-breaker).
        """
        if not self.is_connected():
            return []
        order_clause = (
            "ORDER BY importance IS NULL, importance DESC, analyzed_at DESC"
            if sort == "importance" else
            "ORDER BY analyzed_at DESC"
        )
        try:
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT {self.LIGHT_COLUMNS} FROM analyses "
                "WHERE (is_hidden IS NULL OR is_hidden = 0) "
                f"{order_clause} LIMIT ? OFFSET ?",
                (limit, offset)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error retrieving recent (light): {e}")
            return []

    def get_posts_since(self, updated_after: str, limit=1000):
        """Return posts updated after the given ISO timestamp (delta sync).
        Includes soft-deleted posts so the app knows to hide them."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT {self.LIGHT_COLUMNS} FROM analyses "
                "WHERE updated_at > ? "
                "ORDER BY updated_at ASC LIMIT ?",
                (updated_after, limit)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting posts since {updated_after}: {e}")
            return []

    def get_deleted_since(self, since: str):
        """Return shortcodes of posts deleted after the given ISO timestamp."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT shortcode, deleted_at FROM deleted_log WHERE deleted_at > ? ORDER BY deleted_at ASC",
                (since,)
            )
            return [{"shortcode": r["shortcode"], "deleted_at": r["deleted_at"]} for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting deleted since {since}: {e}")
            return []

    def get_total_count(self):
        """Return total number of visible (non-hidden) posts."""
        if not self.is_connected():
            return 0
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM analyses WHERE (is_hidden IS NULL OR is_hidden = 0)")
            return cur.fetchone()[0]
        except Exception as e:
            print(f"[WARNING]  Error getting total count: {e}")
            return 0

    def get_by_category(self, category, limit=20):
        """Return all analyses tagged with the given category (a post can have
        more than one). Matches new JSON-array rows via substring containment
        and old plain-string rows via exact match. Excludes soft-deleted."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            like_pattern = f'%"{category}"%'
            cur.execute(
                "SELECT * FROM analyses WHERE (category = ? OR category LIKE ?) "
                "AND (is_hidden IS NULL OR is_hidden = 0) ORDER BY analyzed_at DESC LIMIT ?",
                (category, like_pattern, limit)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error retrieving by category: {e}")
            return []

    def search_tags(self, tags, limit=20):
        """
        Search analyses by one or more tags (case-insensitive substring match
        against the JSON-encoded tags column).

        Args:
            tags: str or list[str]
            limit: int
        """
        if not self.is_connected():
            return []
        try:
            if isinstance(tags, str):
                tags = [tags]
            cur = self._conn.cursor()
            conditions = " OR ".join(["LOWER(tags) LIKE ?" for _ in tags])
            params = [f"%{t.lower()}%" for t in tags] + [limit]
            cur.execute(
                f"SELECT * FROM analyses WHERE ({conditions}) AND (is_hidden IS NULL OR is_hidden = 0) ORDER BY analyzed_at DESC LIMIT ?",
                params
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error searching tags: {e}")
            return []

    def get_stats(self):
        """Return basic statistics about the database."""
        if not self.is_connected():
            return {
                "document_count": 0,
                "total_posts": 0,
                "total_collections": 0,
                "storage_mb": 0,
                "categories": {},
                "capacity_used": "N/A",
            }
        try:
            cur = self._conn.cursor()

            cur.execute("SELECT COUNT(*) FROM analyses WHERE (is_hidden IS NULL OR is_hidden = 0)")
            total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM collections")
            total_collections = cur.fetchone()[0]

            # category is stored as a JSON array (or a legacy plain string) —
            # tally each label a post carries rather than grouping on the raw
            # column value, since one post can now have multiple categories.
            cur.execute(
                "SELECT category FROM analyses WHERE (is_hidden IS NULL OR is_hidden = 0)"
            )
            category_counts = {}
            for r in cur.fetchall():
                raw_cat = r["category"]
                if not raw_cat:
                    category_counts["Uncategorized"] = category_counts.get("Uncategorized", 0) + 1
                    continue
                try:
                    labels = json.loads(raw_cat)
                    if not isinstance(labels, list):
                        labels = [str(labels)]
                except Exception:
                    labels = [raw_cat]
                if not labels:
                    category_counts["Uncategorized"] = category_counts.get("Uncategorized", 0) + 1
                for label in labels:
                    category_counts[label] = category_counts.get(label, 0) + 1

            storage_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
            storage_mb = round(storage_bytes / (1024 * 1024), 2)

            return {
                "document_count": total,
                "total_posts": total,
                "total_collections": total_collections,
                "storage_mb": storage_mb,
                "categories": category_counts,
                "capacity_used": "N/A (local SQLite)"
            }
        except Exception as e:
            print(f"[WARNING]  Error getting stats: {e}")
            return {
                "document_count": 0,
                "total_posts": 0,
                "total_collections": 0,
                "storage_mb": 0,
                "categories": {},
                "capacity_used": "N/A",
            }

    def get_all_posts(self, limit: int = 50000, offset: int = 0) -> list:
        """Return all posts for export (excludes soft-deleted)."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM analyses WHERE (is_hidden IS NULL OR is_hidden = 0) ORDER BY analyzed_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting all posts for export: {e}")
            return []

    def get_all_collections(self) -> list:
        """Return all collections for export."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM collections ORDER BY created_at DESC")
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting collections for export: {e}")
            return []

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
    
    # ==================== RETRY QUEUE ====================

    def queue_for_retry(self, shortcode: str, url: str, content_type: str,
                        reason: str, retry_hours: float = 24.0) -> bool:
        """
        Schedule an item to be retried after `retry_hours` from now.
        Sets status='retry' and populates retry_after, reason, content_type.
        Returns True on success.
        """
        if not self.is_connected():
            return False
        try:
            from datetime import timezone, timedelta
            now      = datetime.utcnow()
            retry_at = (now + timedelta(hours=retry_hours)).isoformat()
            now_str  = now.isoformat()

            # Get current attempts count
            cur = self._conn.cursor()
            cur.execute(
                "SELECT attempts FROM processing_queue WHERE shortcode = ?", (shortcode,)
            )
            row = cur.fetchone()
            attempts = (row["attempts"] or 0) + 1 if row else 1

            self._conn.execute("""
                INSERT INTO processing_queue
                    (shortcode, url, content_type, status, position,
                     added_at, updated_at, retry_after, attempts, reason)
                VALUES (?, ?, ?, 'retry', 0, ?, ?, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    url          = excluded.url,
                    content_type = excluded.content_type,
                    status       = 'retry',
                    updated_at   = excluded.updated_at,
                    retry_after  = excluded.retry_after,
                    attempts     = excluded.attempts,
                    reason       = excluded.reason
            """, (shortcode, url, content_type, now_str, now_str,
                  retry_at, attempts, reason))
            self._conn.commit()
            print(f"⏰ Queued for retry in {retry_hours:.0f}h: {shortcode} ({reason})")
            return True
        except Exception as e:
            print(f"[WARNING]  Error queuing for retry: {e}")
            return False

    def get_retry_ready(self):
        """Return retry items whose retry_after time has passed."""
        if not self.is_connected():
            return []
        try:
            now = datetime.utcnow().isoformat()
            cur = self._conn.cursor()
            cur.execute("""
                SELECT shortcode, url, content_type, reason, attempts, retry_after
                FROM processing_queue
                WHERE status = 'retry' AND retry_after <= ?
                ORDER BY retry_after
            """, (now,))
            return [
                {
                    "shortcode":    r["shortcode"],
                    "url":          r["url"],
                    "content_type": r["content_type"],
                    "reason":       r["reason"],
                    "attempts":     r["attempts"],
                    "retry_after":  r["retry_after"],
                }
                for r in cur.fetchall()
            ]
        except Exception as e:
            print(f"[WARNING]  Error getting retry-ready items: {e}")
            return []

    def get_retry_queue(self):
        """Return all items currently awaiting retry (status='retry')."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("""
                SELECT shortcode, url, content_type, reason, attempts,
                       retry_after, added_at
                FROM processing_queue
                WHERE status = 'retry'
                ORDER BY retry_after
            """)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting retry queue: {e}")
            return []

    # ==================== QUEUE MANAGEMENT ====================

    def add_to_queue(self, shortcode, url, caption=None, hashtags=None):
        """Add item to processing queue. Returns queue position (1-based), or -1 on error.

        caption/hashtags: optional client-supplied hint (see AnalyzeRequest),
        persisted so queue_worker can still forward it to main.py once this
        item is eventually picked up — otherwise it's silently lost for any
        request that arrives while the server is busy.
        """
        if not self.is_connected():
            return -1
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT status, position FROM processing_queue WHERE shortcode = ?", (shortcode,)
            )
            existing = cur.fetchone()
            if existing:
                if existing["status"] == "queued":
                    return existing["position"]
                if existing["status"] == "processing":
                    return 0

            cur.execute(
                "SELECT MAX(position) FROM processing_queue WHERE status = 'queued'"
            )
            row = cur.fetchone()
            position = (row[0] + 1) if row[0] is not None else 1

            now = datetime.utcnow().isoformat()
            hashtags_json = json.dumps(hashtags) if hashtags else ''
            self._conn.execute("""
                INSERT INTO processing_queue (shortcode, url, status, position, added_at, updated_at, caption, hashtags)
                VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    url        = excluded.url,
                    status     = 'queued',
                    position   = excluded.position,
                    updated_at = excluded.updated_at,
                    caption    = excluded.caption,
                    hashtags   = excluded.hashtags
            """, (shortcode, url, position, now, now, caption or '', hashtags_json))
            self._conn.commit()
            return position
        except Exception as e:
            print(f"[WARNING]  Error adding to queue: {e}")
            return -1

    def get_queue(self):
        """Return list of queued items ordered by position."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT shortcode, url, position, caption, hashtags FROM processing_queue "
                "WHERE status = 'queued' ORDER BY position"
            )
            result = []
            for r in cur.fetchall():
                try:
                    hashtags = json.loads(r["hashtags"]) if r["hashtags"] else []
                except (json.JSONDecodeError, TypeError):
                    hashtags = []
                result.append({
                    "shortcode": r["shortcode"],
                    "url": r["url"],
                    "position": r["position"],
                    "caption": r["caption"] or '',
                    "hashtags": hashtags,
                })
            return result
        except Exception as e:
            print(f"[WARNING]  Error getting queue: {e}")
            return []

    def get_processing(self):
        """Return list of shortcodes currently being processed."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT shortcode FROM processing_queue WHERE status = 'processing'"
            )
            return [r["shortcode"] for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting processing items: {e}")
            return []

    def mark_processing(self, shortcode, url=None, content_type=None):
        """Mark an item as currently processing.

        Upserts rather than plain-UPDATEs: the caller may not have gone
        through add_to_queue() first (e.g. the fast path that processes a
        request immediately when the server is idle), in which case no row
        exists yet and a bare UPDATE would silently match zero rows — leaving
        get_processing() blind to it. url/content_type are only used to seed
        a new row; an existing row's url/content_type/position are left
        untouched.
        """
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute("""
                INSERT INTO processing_queue
                    (shortcode, url, content_type, status, position, added_at, started_at, updated_at)
                VALUES (?, ?, ?, 'processing', 0, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    status     = 'processing',
                    started_at = excluded.started_at,
                    updated_at = excluded.updated_at
            """, (shortcode, url or '', content_type or '', now, now, now))
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error marking as processing: {e}")
            return False

    def remove_from_queue(self, shortcode):
        """Remove an item from the queue and compact positions."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute(
                "DELETE FROM processing_queue WHERE shortcode = ?", (shortcode,)
            )
            self._conn.commit()

            cur = self._conn.cursor()
            cur.execute(
                "SELECT shortcode FROM processing_queue "
                "WHERE status = 'queued' ORDER BY position"
            )
            for idx, item in enumerate(cur.fetchall(), 1):
                self._conn.execute(
                    "UPDATE processing_queue SET position = ? WHERE shortcode = ?",
                    (idx, item["shortcode"])
                )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error removing from queue: {e}")
            return False

    def recover_interrupted_items(self):
        """
        Move items stuck in 'processing' back to 'queued' (e.g. after a crash).
        Returns the number of items recovered.
        """
        if not self.is_connected():
            return 0
        try:
            now = datetime.utcnow().isoformat()
            cur = self._conn.cursor()
            cur.execute("""
                UPDATE processing_queue
                SET status = 'queued', updated_at = ?
                WHERE status = 'processing'
            """, (now,))
            count = cur.rowcount
            self._conn.commit()

            cur.execute(
                "SELECT shortcode FROM processing_queue "
                "WHERE status = 'queued' ORDER BY added_at"
            )
            for idx, item in enumerate(cur.fetchall(), 1):
                self._conn.execute(
                    "UPDATE processing_queue SET position = ? WHERE shortcode = ?",
                    (idx, item["shortcode"])
                )
            self._conn.commit()

            if count > 0:
                print(f"[RECOVERED] Recovered {count} interrupted items")
            return count
        except Exception as e:
            print(f"[WARNING]  Error recovering items: {e}")
            return 0
    
    # ------------------------------------------------------------------
    # Post management
    # ------------------------------------------------------------------

    def delete_post(self, shortcode):
        """Soft-delete a post (is_hidden=1). Data kept for re-add reuse. Returns True if updated."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            cur = self._conn.execute(
                "UPDATE analyses SET is_hidden = 1, updated_at = ? WHERE shortcode = ?",
                (now, shortcode)
            )
            if cur.rowcount > 0:
                # Record in deleted_log so mobile app can sync deletions
                self._conn.execute(
                    "INSERT OR REPLACE INTO deleted_log (shortcode, deleted_at) VALUES (?, ?)",
                    (shortcode, now)
                )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error soft-deleting post: {e}")
            return False

    def hard_delete_post(self, shortcode):
        """Permanently remove a post row — used for force re-analysis. Returns True if deleted."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute(
                "DELETE FROM analyses WHERE shortcode = ?",
                (shortcode,)
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error hard-deleting post: {e}")
            return False

    def restore_post(self, shortcode):
        """Restore a soft-deleted post (is_hidden=0). Returns True if updated."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute(
                "UPDATE analyses SET is_hidden = 0, updated_at = ? WHERE shortcode = ?",
                (datetime.utcnow().isoformat(), shortcode)
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error restoring post: {e}")
            return False

    def update_post(self, shortcode, updates):
        """
        Update specific fields of a post.

        Args:
            shortcode: Instagram post shortcode
            updates: dict of allowed fields (category, language, media_files, title, summary, reviewed)

            'reviewed': True is a write-only shorthand — it doesn't map to a
            real column. It means "I looked at this post and the existing
            analysis is good enough, don't flag it again" without re-running
            the (costly) analysis pipeline. It's translated into stamping
            analysis_version = CURRENT_ANALYSIS_VERSION, which is exactly
            what a real re-analysis would have stamped anyway.

        Returns:
            bool: True if updated
        """
        if not self.is_connected():
            return False
        try:
            if updates.pop("reviewed", False):
                updates["analysis_version"] = CURRENT_ANALYSIS_VERSION
            if "category" in updates:
                cat = updates["category"]
                if isinstance(cat, list):
                    updates["category"] = json.dumps([c.strip() for c in cat if c and str(c).strip()])
                elif cat:
                    updates["category"] = json.dumps([c.strip() for c in str(cat).split(',') if c.strip()])
                else:
                    updates["category"] = json.dumps([])
            if "language" in updates:
                lang = updates["language"]
                if isinstance(lang, list):
                    updates["language"] = json.dumps([l.strip() for l in lang if l and str(l).strip()])
                elif lang:
                    updates["language"] = json.dumps([l.strip() for l in str(lang).split(',') if l.strip()])
                else:
                    updates["language"] = json.dumps([])
            if "media_files" in updates:
                mf = updates["media_files"]
                if isinstance(mf, list):
                    updates["media_files"] = json.dumps([m.strip() for m in mf if m and str(m).strip()])
                elif mf:
                    updates["media_files"] = json.dumps([m.strip() for m in str(mf).split(',') if m.strip()])
                else:
                    updates["media_files"] = json.dumps([])
            updates["updated_at"] = datetime.utcnow().isoformat()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [shortcode]
            cur = self._conn.execute(
                f"UPDATE analyses SET {set_clause} WHERE shortcode = ?", values
            )
            self._conn.commit()
            if cur.rowcount == 0:
                print(f"[WARNING]  Post not found: {shortcode}")
                return False
            print(f"[OK] Updated post: {shortcode}")
            return True
        except Exception as e:
            print(f"[WARNING]  Error updating post: {e}")
            return False

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def _collection_row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        try:
            d['post_ids'] = json.loads(d.get('post_ids') or '[]')
        except Exception:
            d['post_ids'] = []
        return d

    def get_collections(self):
        """Return all collections ordered by created_at."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM collections ORDER BY created_at ASC")
            return [self._collection_row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting collections: {e}")
            return []

    def get_collection(self, collection_id):
        """Return a single collection by id."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
            return self._collection_row_to_dict(cur.fetchone())
        except Exception as e:
            print(f"[WARNING]  Error getting collection: {e}")
            return None

    def upsert_collection(self, collection_id, name, icon, post_ids, created_at=None, updated_at=None):
        """Insert or fully replace a collection. Returns the saved dict."""
        if not self.is_connected():
            return None
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute("""
                INSERT INTO collections (id, name, icon, post_ids, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name       = excluded.name,
                    icon       = excluded.icon,
                    post_ids   = excluded.post_ids,
                    updated_at = excluded.updated_at
            """, (
                collection_id, name, icon,
                json.dumps(post_ids if isinstance(post_ids, list) else []),
                created_at or now, updated_at or now
            ))
            self._conn.commit()
            return self.get_collection(collection_id)
        except Exception as e:
            print(f"[WARNING]  Error upserting collection: {e}")
            return None

    def update_collection_posts(self, collection_id, post_ids):
        """Replace the post_ids list for a collection."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            cur = self._conn.execute(
                "UPDATE collections SET post_ids = ?, updated_at = ? WHERE id = ?",
                (json.dumps(post_ids), now, collection_id)
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error updating collection posts: {e}")
            return False

    def delete_collection(self, collection_id):
        """Delete a collection. Returns True if deleted."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error deleting collection: {e}")
            return False

    # ------------------------------------------------------------------
    # RAG chatbot — chat_threads / chat_messages
    # ------------------------------------------------------------------

    def _chat_message_row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        try:
            d['sources'] = json.loads(d.get('sources') or '[]')
        except Exception:
            d['sources'] = []
        return d

    def create_chat_thread(self, title=None):
        """Create a new chat thread. Returns the saved dict, or None on failure."""
        if not self.is_connected():
            return None
        try:
            thread_id = uuid.uuid4().hex
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO chat_threads (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (thread_id, title, now, now)
            )
            self._conn.commit()
            return self.get_chat_thread(thread_id)
        except Exception as e:
            print(f"[WARNING]  Error creating chat thread: {e}")
            return None

    def list_chat_threads(self):
        """Return all chat threads, most-recently-updated first."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM chat_threads ORDER BY updated_at DESC")
            return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error listing chat threads: {e}")
            return []

    def get_chat_thread(self, thread_id):
        """Return a single chat thread by id, or None."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM chat_threads WHERE id = ?", (thread_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"[WARNING]  Error getting chat thread: {e}")
            return None

    def touch_chat_thread(self, thread_id, title=None):
        """Update a thread's updated_at (and title, if given and not already set)."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            if title:
                cur = self._conn.execute(
                    "UPDATE chat_threads SET updated_at = ?, title = COALESCE(title, ?) WHERE id = ?",
                    (now, title, thread_id)
                )
            else:
                cur = self._conn.execute(
                    "UPDATE chat_threads SET updated_at = ? WHERE id = ?",
                    (now, thread_id)
                )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error touching chat thread: {e}")
            return False

    def delete_chat_thread(self, thread_id):
        """Delete a thread and its messages. Returns True if the thread existed."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute("DELETE FROM chat_messages WHERE thread_id = ?", (thread_id,))
            cur = self._conn.execute("DELETE FROM chat_threads WHERE id = ?", (thread_id,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error deleting chat thread: {e}")
            return False

    def get_chat_messages(self, thread_id):
        """Return all messages for a thread, oldest first."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,)
            )
            return [self._chat_message_row_to_dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting chat messages: {e}")
            return []

    def add_chat_message(self, thread_id, role, content, sources=None):
        """Append a message to a thread. Returns the saved dict, or None on failure."""
        if not self.is_connected():
            return None
        try:
            message_id = uuid.uuid4().hex
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO chat_messages (id, thread_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, thread_id, role, content, json.dumps(sources or []), now)
            )
            self._conn.commit()
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,))
            return self._chat_message_row_to_dict(cur.fetchone())
        except Exception as e:
            print(f"[WARNING]  Error adding chat message: {e}")
            return None


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_db_instance = None


def get_db():
    """Get or create the shared Database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
