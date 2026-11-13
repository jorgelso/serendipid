#!/usr/bin/env python3
"""
SQLite Database Manager for SuperBrain
Handles caching and retrieval of Instagram analysis results
Self-hosted, zero-config, file-based database
"""

import sqlite3
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from datetime import datetime

from core.sensitive import SENSITIVE_COLLECTION_NAMES, is_excluded_folder, show_sensitive

# Database file path can be overridden for Docker deployments
DB_PATH = Path(os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parent.parent / 'superbrain.db')))

# Shortcodes of every post in a sensitive Instagram folder (core/sensitive.py),
# as a subquery — membership lives in collections.post_ids (a JSON array), so
# this is computed live from that table on every query rather than stored on
# the analyses row, and a folder import picks it up with no extra write.
_SENSITIVE_NAMES_SQL = ", ".join("'" + n.replace("'", "''") + "'" for n in sorted(SENSITIVE_COLLECTION_NAMES))
SENSITIVE_SHORTCODES_SQL = (
    "SELECT j.value FROM collections c, "
    "json_each(CASE WHEN json_valid(c.post_ids) THEN c.post_ids ELSE '[]' END) j "
    f"WHERE lower(trim(c.name)) IN ({_SENSITIVE_NAMES_SQL})"
)
IS_SENSITIVE_COLUMN = f"(shortcode IN ({SENSITIVE_SHORTCODES_SQL})) AS is_sensitive"

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
#   9 — 2026-10-30: the combined-summary prompt (core/summary_parser.py
#       build_final_summary_prompt()) only passed the first 400 characters
#       of the audio transcript to the model, so most talking-head reels got
#       summaries/titles/tags built from speech cut off mid-sentence (the full
#       transcript was always stored — only the prompt was truncated). Now
#       3000. Unlike earlier bumps, only actually-affected posts are flagged:
#       on startup, version-8 posts whose stored transcript fits within the
#       old cap are restamped to 9 (see the migration in _create_tables), so
#       only truncated ones land in needs_review. Their rescan rebuilds the
#       summary from the stored transcript and re-scores importance, since
#       the old score was judged from the truncated summary.
# This history is also kept queryable in the analysis_changelog table (see
# _seed_changelog() below) rather than only living as a comment.
CURRENT_ANALYSIS_VERSION = 9

# The transcript cap build_final_summary_prompt() used through version 8 —
# a post whose stored audio_transcription is longer than this had its
# summary built from a truncated transcript.
PRE_V9_TRANSCRIPT_PROMPT_CAP = 400


class Database:
    """SQLite database manager with caching functionality"""

    def __init__(self):
        self.db_path = DB_PATH
        self._conn = None
        # Guards execute()+commit() sequences on the shared connection
        # (check_same_thread=False lets multiple threads use it, but doesn't
        # by itself make an interleaved execute/commit pair from two threads
        # safe — a second thread's commit() can land between another
        # thread's execute() and its own commit(), raising "cannot commit -
        # no transaction is active"). Only methods actually called
        # concurrently (by scripts/rescan_post.py's bounded worker pool —
        # see backend/CLAUDE.md's "Rescan pipeline" section) take this lock;
        # it's not applied blanket-wide across every method in this class.
        self._write_lock = threading.Lock()
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
            # Same idea for date_saved (see AnalyzeRequest.date_saved) — the
            # real Instagram save date the import scripts look up per-post
            # from saved_posts.json, threaded through exactly like
            # caption/hashtags so it isn't lost if this request has to wait
            # in the queue before queue_worker spawns main.py for it.
            ("date_saved",   "TEXT"),
            # Manually uploaded media (POST /manual-upload, core/manual_media.py):
            # the temp/ folder to analyze *instead of* downloading from
            # Instagram. Persisted for the same reason as caption/hashtags
            # above — max_concurrent is 1, so a manual upload arriving while
            # anything else is analyzing has to wait in the queue, and a
            # queued row that lost this would come back as a plain download
            # attempt: the exact attempt that already failed.
            ("media_folder", "TEXT"),
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

        # Migration: version 9 only affects posts whose transcript exceeded
        # PRE_V9_TRANSCRIPT_PROMPT_CAP — restamp every other version-8 post
        # so it doesn't show up in needs_review for a gap it never had.
        # Idempotent: a version-8 row with a short transcript is unaffected
        # whenever it appears (including one restored from a backup).
        try:
            self._conn.execute(
                "UPDATE analyses SET analysis_version = 9 "
                "WHERE analysis_version = 8 AND length(coalesce(audio_transcription, '')) <= ?",
                (PRE_V9_TRANSCRIPT_PROMPT_CAP,),
            )
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

        # Migration: add importance_reason — the model's justification for
        # the importance score above (see core/importance.py's
        # IMPORTANCE_PROMPT, which now requires a justification alongside
        # the 1-5 number rather than treating it as optional). NULL for
        # posts scored before this was tracked; not a CURRENT_ANALYSIS_VERSION
        # bump on its own since the score itself is unchanged, only whether
        # its reasoning is retained.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN importance_reason TEXT DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add model_used — the AI Model Router key (e.g.
        # "openai_gpt41", "groq_llama33_70b") that generated this post's
        # title/summary/tags. Empty for posts saved before this was tracked,
        # and for YouTube/webpage posts (not yet wired up to pass it).
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN model_used TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add transcription_backend — which Whisper backend
        # produced audio_transcription ("Groq Whisper API" or "Local Whisper
        # (<model>)"). Empty for posts with no audio track or saved before
        # this was tracked.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN transcription_backend TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: enjoyment_rating / perceived_importance_rating — user-driven
        # Netflix-style tri-state ratings (NULL | 'liked' | 'loved'), distinct from
        # the AI-scored `importance` column above. Not a CURRENT_ANALYSIS_VERSION
        # bump — these are user judgments, not pipeline output.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN enjoyment_rating TEXT DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN perceived_importance_rating TEXT DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: should_revisit — a manual per-post flag (superbrain-web's
        # /boards pages) distinct from every AI-scored signal above. Overrides
        # the "already seen" (post_views-derived) white thumbnail overlay with
        # a pink one + label, so a post the user has viewed but wants to come
        # back to doesn't visually disappear into "already handled."
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN should_revisit INTEGER DEFAULT 0")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: is_eloquent / eloquence_rationale — AI-judged verdict on
        # whether audio_transcription reads as oratory-eloquent (see
        # core/eloquence.py), independent of the `importance` rating above.
        # NULL is_eloquent for posts not yet scored, so "not scored" stays
        # distinguishable from "scored not eloquent" (0).
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN is_eloquent INTEGER DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN eloquence_rationale TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: is_tutorial — whether an eloquent post is delivered as a
        # tutorial/how-to (vs. a speech/commentary), see core/eloquence.py's
        # neuroscience/self-improvement domain carve-out. NULL for posts not
        # yet scored.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN is_tutorial INTEGER DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: eloquence_reviewed — a human has looked at this post on
        # the web /eloquent page and confirmed the AI's "eloquent" verdict
        # (POST /eloquence/approve). Distinct from the override log, which is
        # the opposite decision: this exists so a fresh scoring run's new
        # arrivals can be told apart from posts already reviewed, instead of
        # the two blending into one undifferentiated list. NULL = not yet
        # reviewed. Cleared when a post is overridden to not eloquent.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN eloquence_reviewed INTEGER DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: add caption — the raw Instagram post caption (scraped by
        # instaloader into media/<shortcode>/info.txt), stored verbatim for
        # display under the AI summary. Empty for posts with no caption, non-
        # Instagram posts, or saved before this was tracked (backfilled via
        # scripts/backfill_captions.py from each post's info.txt).
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN caption TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: saved_order (RETIRED — column kept for backwards
        # compatibility with this codebase's additive-only migration
        # convention, but no longer populated or read anywhere; every row
        # has been reset to NULL). It was a reconstructed relative rank,
        # useful only because Instagram's collection export has no per-post
        # timestamp. Superseded by date_saved below, a real date sourced
        # from saved_posts.json (Instagram's flat "every saved post" export,
        # which does have a real per-post timestamp) — see
        # scripts/backfill_date_saved.py and backend/CLAUDE.md's "Instagram
        # export import" section for the full story.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN saved_order INTEGER DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: date_saved — the real date a post was saved to
        # Instagram (NOT its content publish date, which is `post_date`
        # above, scraped independently from Instagram's own post metadata).
        # Sourced from saved_posts.json's per-post `timestamp` field —
        # verified against post_date to actually be a save date, not a
        # duplicate publish date: it's always later than post_date, by a
        # wildly varying amount (a day to several months), which is the
        # signature of "whenever I happened to see and save this," not a
        # second copy of the same publish fact. Backfilled once for
        # existing rows via scripts/backfill_date_saved.py; set for future
        # imports by import_saved_instagram.py passing it straight into
        # POST /analyze (see AnalyzeRequest.date_saved), same pipeline path
        # as caption/hashtags. NULL for posts saved individually (not via
        # the collections-file import flow) or not found in the all-posts
        # lookup file at backfill/import time — never coerced to a fake
        # value.
        try:
            self._conn.execute("ALTER TABLE analyses ADD COLUMN date_saved TEXT DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # import_jobs — tracks a background run of scripts/import_saved_instagram.py
        # (or its _by_collection sibling) kicked off from superbrain-web's
        # /import page. Deliberately a separate table/prefix from
        # /import & /import/file (which restore a SuperBrain-format /export
        # backup, a completely different operation) — see api.py's
        # /instagram-export/* routes. A run can take hours (rate-limited,
        # one URL at a time), so it's spawned in a background thread and
        # polled via GET /instagram-export/jobs/{id}, same shape as
        # study_guide_collections' "create row, update as it progresses,
        # poll" pattern.
        try:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS import_jobs (
                    id                  TEXT PRIMARY KEY,
                    mode                TEXT,
                    priority_folder     TEXT,
                    reverse_collections INTEGER DEFAULT 1,
                    export_filename     TEXT,
                    status              TEXT DEFAULT 'running',
                    log_tail            TEXT DEFAULT '',
                    error               TEXT,
                    started_at          TEXT,
                    finished_at         TEXT
                )
            """)
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # batch_jobs — resume state for ANALYSIS_MODE=batch (see main.py /
        # core/batch_processor.py). main.py runs as a subprocess and exits
        # right after submitting an OpenAI Batch API job, so everything
        # needed to finish the pipeline later (visual/audio/text extracts,
        # caption/hashtags, thumbnail, media_files, and — once phase 1
        # resolves — the parsed title/summary/tags/category) has to be
        # persisted here rather than kept in memory. Deliberately a separate
        # table rather than extra columns on processing_queue: every existing
        # processing_queue caller (add_to_queue, get_queue, mark_processing,
        # recover_interrupted_items, ...) assumes a small flat row, and this
        # needs a multi-KB JSON blob plus a two-phase / two-sub-batch-id state
        # machine. processing_queue still gets one lightweight row per
        # in-flight item (status='batch', set by enqueue_batch_job below) so
        # existing queue-status visibility keeps working; that status is
        # deliberately distinct from 'processing' so recover_interrupted_items()
        # (which unconditionally resets 'processing' rows back to 'queued' on
        # every startup) never touches an in-flight batch job.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS batch_jobs (
                shortcode            TEXT PRIMARY KEY,
                url                  TEXT,
                content_type         TEXT DEFAULT 'instagram',
                phase                TEXT DEFAULT 'summary_pending',
                summary_batch_id     TEXT,
                importance_batch_id  TEXT,
                embedding_batch_id   TEXT,
                state_json           TEXT,
                created_at           TEXT,
                updated_at           TEXT,
                last_error           TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_batch_jobs_phase ON batch_jobs (phase);
        """)
        self._conn.commit()

        # Migration: analysis_batch_id — the visual+text analysis batch job
        # (one job per reel, bundling one vision request per video/image
        # file plus one text-analysis request), a phase added after
        # batch_jobs' initial ('summary_pending' -> 'scoring_pending')
        # design. A reel now normally starts at phase='analysis_pending'
        # (this column set), advancing to 'summary_pending' once resolved.
        try:
            self._conn.execute("ALTER TABLE batch_jobs ADD COLUMN analysis_batch_id TEXT")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # rescan_batch_jobs — same two-phase shape as batch_jobs above, but
        # for the rescan pipeline (core/rescan_batch_processor.py,
        # scripts/rescan_post.py --batch), which is deliberately separate
        # from first-time analysis (see backend/CLAUDE.md's "Rescan
        # pipeline" section). A SEPARATE table rather than a discriminator
        # column on batch_jobs: every existing batch_jobs caller
        # (get_batch_jobs, advance_batch_job, check_and_advance_batches's two
        # loops) assumes one row per shortcode with a summary_batch_id
        # unique to it. A rescan of a whole version cohort needs many
        # shortcodes sharing ONE summary_batch_id (one shared OpenAI batch
        # job covering the whole cohort, not one job per post) — reusing
        # batch_jobs would force every existing caller to filter around rows
        # shaped differently than they expect, exactly what keeping the two
        # pipelines separate is meant to avoid.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS rescan_batch_jobs (
                shortcode            TEXT PRIMARY KEY,
                url                  TEXT,
                content_type         TEXT DEFAULT 'instagram',
                phase                TEXT DEFAULT 'summary_pending',
                summary_batch_id     TEXT,
                importance_batch_id  TEXT,
                embedding_batch_id   TEXT,
                state_json           TEXT,
                created_at           TEXT,
                updated_at           TEXT,
                last_error           TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_rescan_batch_jobs_phase ON rescan_batch_jobs (phase);
            CREATE INDEX IF NOT EXISTS idx_rescan_batch_jobs_summary_batch_id ON rescan_batch_jobs (summary_batch_id);
        """)
        self._conn.commit()

        # eloquence_batch_jobs — resume state for scripts/score_eloquence.py
        # --batch under ANALYSIS_MODE=batch (core/eloquence_batch_processor.py).
        # Single-phase, unlike batch_jobs/rescan_batch_jobs' two-phase shape:
        # eloquence scoring is one LLM call per post with nothing downstream
        # (no importance/embedding follow-up), so there's only "submitted" ->
        # "resolved", tracked by presence/absence of the row rather than a
        # phase column. Many shortcodes share one batch_id (one shared OpenAI
        # batch job per chunk, same rationale as rescan_batch_jobs above) —
        # that's why this is its own table rather than a column on analyses.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS eloquence_batch_jobs (
                shortcode   TEXT PRIMARY KEY,
                batch_id    TEXT,
                created_at  TEXT,
                updated_at  TEXT,
                last_error  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_eloquence_batch_jobs_batch_id ON eloquence_batch_jobs (batch_id);
        """)
        self._conn.commit()

        # eloquence_overrides — append-only audit log of human corrections
        # made from superbrain-web's /eloquent page ("Select" -> "Mark as not
        # eloquent"): every time a post the AI judge scored eloquent gets
        # manually flipped to not-eloquent, the AI's original rationale is
        # kept here (not overwritten) specifically so these can be reviewed
        # later — a cluster of overrides with a similar rationale pattern is
        # a signal that ELOQUENCE_PROMPT (core/eloquence.py) needs
        # refinement, not just that individual posts were wrong. Insert-only,
        # never updated/deleted; multiple rows for the same shortcode are
        # possible in principle (re-scored eloquent again, overridden again)
        # and are all kept.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS eloquence_overrides (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                shortcode        TEXT NOT NULL,
                ai_rationale     TEXT,
                ai_was_tutorial  INTEGER,
                overridden_at    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_eloquence_overrides_shortcode ON eloquence_overrides (shortcode);
        """)
        self._conn.commit()

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

        # Seed the "iPhone" collection if missing — same permanent,
        # never-deletable-by-convention pattern as Watch Later above. Target
        # for shares that came in through superbrain-ios's Share Extension
        # offline queue (PendingShareStore/PendingShareSyncer): a post shared
        # straight from Instagram was never actually saved to a real
        # Instagram collection first, so there's no folder to assign it to
        # yet. `ensure_post_in_collection()` (scripts/import_saved_instagram.py)
        # is purely additive and never removes a shortcode from a collection
        # it's already in, so a later real Instagram export import that does
        # find this post in a real folder just adds that folder too — this
        # collection is never cleared out for a post, only ever gained more
        # siblings.
        cur.execute("SELECT id FROM collections WHERE id = 'iphone_shares'")
        if cur.fetchone() is None:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO collections (id, name, icon, post_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ('iphone_shares', 'iPhone', '📱', '[]', now, now)
            )
            self._conn.commit()

        # Boards — user-curated groupings of posts created by hand from
        # superbrain-web's /boards page. Deliberately a separate table from
        # `collections` above, not an extension of it: `collections` mirrors
        # Instagram's own saved-post folders (one row per imported folder,
        # auto-populated by scripts/import_saved_instagram(_by_collection).py)
        # and is never created or edited by a person, whereas `boards` are
        # made by hand and never touched by the import scripts. See
        # backend/CLAUDE.md's "Boards vs collections" section.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS boards (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                icon        TEXT DEFAULT '🗂️',
                post_ids    TEXT DEFAULT '[]',
                created_at  TEXT,
                updated_at  TEXT
            );

            -- A second, optional grouping level nested under one board (e.g.
            -- a "Home renovation" board with "Kitchen" / "Bathroom"
            -- sub-collections underneath it). Same flat JSON-array post_ids
            -- shape as `boards`/`collections`, not a join table — membership
            -- here doesn't imply membership in the parent board's own
            -- post_ids, and vice versa; a post can be in the board directly,
            -- in one of its sub-collections, both, or neither.
            CREATE TABLE IF NOT EXISTS board_subcollections (
                id          TEXT PRIMARY KEY,
                board_id    TEXT NOT NULL,
                name        TEXT NOT NULL,
                icon        TEXT DEFAULT '📁',
                post_ids    TEXT DEFAULT '[]',
                created_at  TEXT,
                updated_at  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_board_subcollections_board_id ON board_subcollections (board_id);
        """)
        self._conn.commit()

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

        # eloquence_stash — force re-analysis (see hard_delete_post) removes
        # a post's whole row and lets the pipeline INSERT a brand-new one
        # (main.py short-circuits on a cached row via check_cache(), so
        # force-reanalysis can't just UPSERT over the existing row the way a
        # normal re-save does — the row genuinely has to be gone first for
        # the pipeline to actually redo the work). Eloquence scoring
        # (core/eloquence.py) is a separate, deliberately-decoupled batch
        # pass, not part of the live pipeline, so nothing would ever
        # re-populate is_eloquent/eloquence_rationale/is_tutorial after that
        # delete+reinsert — hard_delete_post stashes them here first, and
        # save_analysis() restores (and clears) the stash right after
        # inserting the fresh row, so a reanalysis never silently reverts an
        # eloquence score back to "unscored".
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS eloquence_stash (
                shortcode            TEXT PRIMARY KEY,
                is_eloquent          INTEGER,
                eloquence_rationale  TEXT,
                is_tutorial          INTEGER,
                stashed_at           TEXT
            );
        """)
        # Additive migration for the stash: carry the human approval flag
        # across a force re-analysis too, for the same reason as the verdict.
        try:
            self._conn.execute("ALTER TABLE eloquence_stash ADD COLUMN eloquence_reviewed INTEGER DEFAULT NULL")
        except sqlite3.OperationalError:
            pass
        self._conn.commit()

        # post_views — one row per qualifying view (video >=60% watched, non-video
        # open >=20s — see superbrain-web's useQualifyingView hook). Repeat views
        # across separate opens are NOT deduped: each open logs its own row, and
        # recency-weighted summation in the web recommendation engine
        # (superbrain-web/src/lib/recommendations.ts) is what turns "viewed many
        # times, recently" into a stronger signal than "viewed once" while still
        # letting old views decay away individually.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS post_views (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                shortcode   TEXT NOT NULL,
                viewed_at   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_post_views_shortcode ON post_views (shortcode);
            CREATE INDEX IF NOT EXISTS idx_post_views_viewed_at ON post_views (viewed_at DESC);
        """)
        self._conn.commit()

        # Migration: client_env — 'dev' | 'prod', tags which build logged this
        # view so a local `next dev` session testing the UI never pollutes the
        # recommendation engine's real signal. Defaults to 'prod' so anything
        # that doesn't send an env (the iOS app, which has no dev/prod build
        # distinction, and any pre-migration row) counts as real usage.
        # get_view_history() only ever returns 'prod' rows — see there.
        try:
            self._conn.execute("ALTER TABLE post_views ADD COLUMN client_env TEXT DEFAULT 'prod'")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # embeddings — deduplicated cache of generated embedding vectors,
        # keyed by normalized (trimmed + lowercased) query text. Split out
        # from search_queries below (which used to store the embedding
        # inline on every row) so the same text's embedding is stored once no
        # matter how many times it's searched, and so search_queries — the
        # recommendation-history signal — can be wiped independently (e.g. to
        # clear out dev/test traffic) without losing the embedding cache that
        # GET /search/semantic and the chat RAG pipeline (core/rag.py) rely on
        # to skip redundant embedding-API calls. See get_cached_query_embedding.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT NOT NULL,
                embedding   TEXT NOT NULL,
                created_at  TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_text ON embeddings (text);
        """)
        self._conn.commit()

        # search_queries — one row per semantic-search query or chat question
        # *instance*, so the web app can build a rolling "interest vector"
        # (superbrain-web/src/lib/recommendations.ts) without re-embedding.
        # source distinguishes GET /search/semantic from chat. embedding_id
        # points at the shared vector in `embeddings` above — repeating the
        # same query text adds another row here (another usage instance, with
        # its own created_at for recency-weighting) but never another
        # `embeddings` row, so this table doubles as "how many times, and
        # when, each embedding has been used" for the recommendation engine.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS search_queries (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text    TEXT,
                embedding_id  INTEGER REFERENCES embeddings (id),
                source        TEXT DEFAULT 'search',
                created_at    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_search_queries_created_at ON search_queries (created_at DESC);
        """)
        self._conn.commit()

        # Migration: client_env — see the identical migration on post_views
        # above for the full rationale. Same default ('prod'), same
        # dev-traffic-never-pollutes-recommendations intent.
        try:
            self._conn.execute("ALTER TABLE search_queries ADD COLUMN client_env TEXT DEFAULT 'prod'")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migration: embedding_id — pre-2026-08-22 databases predate this
        # column (CREATE TABLE IF NOT EXISTS above is a no-op once the table
        # already exists, so it never reaches existing databases). Added
        # before the index below and before the query_embedding-split
        # migration, both of which depend on it existing.
        try:
            self._conn.execute("ALTER TABLE search_queries ADD COLUMN embedding_id INTEGER REFERENCES embeddings (id)")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_search_queries_embedding_id ON search_queries (embedding_id)")
        self._conn.commit()

        # Migration: pre-2026-08-22 databases store the embedding inline in
        # search_queries.query_embedding. Split it out into `embeddings`
        # above (deduped by normalized text) and repoint each row at it via
        # embedding_id, then drop the now-redundant column. Guarded on that
        # column still existing so this only ever runs once per database.
        try:
            cols = [row[1] for row in self._conn.execute("PRAGMA table_info(search_queries)").fetchall()]
            if "query_embedding" in cols:
                rows = self._conn.execute(
                    "SELECT id, query_text, query_embedding FROM search_queries "
                    "WHERE query_embedding IS NOT NULL AND query_embedding != ''"
                ).fetchall()
                now = datetime.utcnow().isoformat()
                for row_id, query_text, emb_json in rows:
                    key = (query_text or "").strip().lower()
                    existing = self._conn.execute(
                        "SELECT id FROM embeddings WHERE text = ?", (key,)
                    ).fetchone()
                    if existing:
                        embedding_id = existing[0]
                    else:
                        cur = self._conn.execute(
                            "INSERT INTO embeddings (text, embedding, created_at) VALUES (?, ?, ?)",
                            (key, emb_json, now),
                        )
                        embedding_id = cur.lastrowid
                    self._conn.execute(
                        "UPDATE search_queries SET embedding_id = ? WHERE id = ?",
                        (embedding_id, row_id),
                    )
                self._conn.execute("ALTER TABLE search_queries DROP COLUMN query_embedding")
                self._conn.commit()
        except sqlite3.OperationalError:
            pass

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

        # Study guides — persisted on-demand synthesis docs (superbrain-web's
        # /study-guides), generated from a user-picked set of posts (a
        # selection, search result, or theme/cluster) via one LLM call over
        # their stored content — see core/study_guide.py. v1 only: dedup of
        # repeated points across source posts happens implicitly inside that
        # single prompt, not via a separate claim-extraction/embedding
        # pipeline (see core/study_guide.py's module docstring for the
        # planned v2, already agreed with the user).
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS study_guides (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                title                 TEXT,
                content               TEXT NOT NULL,
                shortcodes            TEXT NOT NULL,
                excluded_shortcodes   TEXT DEFAULT '[]',
                source_label          TEXT,
                created_at            TEXT
            );
        """)
        self._conn.commit()

        # study_guide_collections — one row per generation *request* (a
        # single selection/theme/cluster the user asked to synthesize), so
        # the frontend has one uniform thing to render ("every generation is
        # a collection you can expand") whether it produced one guide or
        # several. core/study_guide.py's generate_study_guide_pipeline()
        # populates a collection with more than one guide (role
        # 'full'/'merge'/'chunk' alongside the primary 'final' guide) once a
        # request exceeds MAX_STUDY_GUIDE_POSTS — both a whole-selection
        # pass and a chunked-then-merged pass are run and reconciled into
        # 'final', by explicit user request, and NONE of the intermediate
        # guides are deleted afterward; they're kept as siblings so the user
        # can inspect how the final guide was actually built.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS study_guide_collections (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                source_label  TEXT,
                created_at    TEXT
            );
        """)
        self._conn.commit()

        for stmt in (
            "ALTER TABLE study_guides ADD COLUMN collection_id INTEGER",
            "ALTER TABLE study_guides ADD COLUMN role TEXT DEFAULT 'final'",
            "ALTER TABLE study_guides ADD COLUMN position INTEGER DEFAULT 0",
            # The exact OpenAI model that generated this guide (e.g.
            # "gpt-5.6-luna") — core/study_guide.py pins a specific model
            # rather than letting the router pick, so this is worth
            # recording per-guide rather than just trusting whatever
            # STUDY_GUIDE_MODEL happens to be set to today.
            "ALTER TABLE study_guides ADD COLUMN model TEXT",
        ):
            try:
                self._conn.execute(stmt)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass

        # status/error/expected_guide_count: POST /study-guide (api.py) now
        # creates the collection row and returns immediately, running
        # core/study_guide.py's pipeline in a background thread that
        # persists each guide (db.create_study_guide()) the moment it's
        # generated rather than batching everything until the pipeline
        # finishes — so a crash/restart mid-generation only loses whatever
        # guide was actively in flight, not every guide already completed.
        # 'generating' -> 'complete' (all guides done) or 'failed' (error
        # set) in the normal case. A collection can also get stuck at
        # 'generating' forever if the whole backend process dies mid-run —
        # see the startup sweep right below, which relabels those
        # 'interrupted' so the UI doesn't lie about work that's not actually
        # still happening. expected_guide_count is computed synchronously,
        # cheaply, before the background thread starts (see
        # core/study_guide.py's expected_guide_count()) so the frontend can
        # show real progress ("3 of 7") instead of just a spinner.
        for stmt in (
            "ALTER TABLE study_guide_collections ADD COLUMN status TEXT DEFAULT 'complete'",
            "ALTER TABLE study_guide_collections ADD COLUMN error TEXT",
            "ALTER TABLE study_guide_collections ADD COLUMN expected_guide_count INTEGER",
            # Retired on arrival — a machine-readable "what kind of thing is
            # this" tag, meant to drive superbrain-web's /study-guides
            # corkboard coloring, turned out to be pure redundancy with
            # source_label (every writer that would set this also stamps a
            # label with a recognizable prefix — "Board: ...", "Search: ...",
            # etc. — so it never carried information the label didn't;
            # superbrain-web parses that prefix directly instead, see
            # src/lib/studyGuideSource.ts). Column kept, never populated or
            # read anywhere (this codebase's migrations are additive-only,
            # same treatment as analyses.saved_order above).
            "ALTER TABLE study_guide_collections ADD COLUMN source_type TEXT",
            # Stamped by POST /study-guide-collections/{id}/opened, fired
            # from superbrain-web's /study-guides/[id] page every time it's
            # actually opened (not on generation) — see reels_study_guide
            # below for why this lives on the collection.
            "ALTER TABLE study_guide_collections ADD COLUMN last_opened_at TEXT",
        ):
            try:
                self._conn.execute(stmt)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass

        # reels_study_guide — many-to-many link between a post and the study
        # guide *collection* (not an individual final/full/merge/chunk
        # guide row — those all draw from ~the same request-level shortcode
        # set, and double/triple-counting one collection's reels across its
        # sibling guides would overweight exactly the requests that needed
        # chunking) it was used to generate. This is a deliberately weaker,
        # separate signal from post_views for the Home recommendation engine
        # (superbrain-web/src/lib/recommendations.ts): choosing a reel as
        # study-guide source material means you cared about its *topic*
        # enough to synthesize it, even if you never actually watched it
        # again through this UI — it must never be logged as a post_views
        # row, which is reserved for an actual qualifying view. One row per
        # (shortcode, collection) is inserted synchronously in POST
        # /study-guide, from the original request's shortcode list — not
        # per generated guide, and not from the background pipeline thread.
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS reels_study_guide (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                shortcode      TEXT NOT NULL,
                collection_id  INTEGER NOT NULL,
                created_at     TEXT,
                client_env     TEXT DEFAULT 'prod'
            );
            CREATE INDEX IF NOT EXISTS idx_reels_study_guide_shortcode ON reels_study_guide (shortcode);
            CREATE INDEX IF NOT EXISTS idx_reels_study_guide_collection_id ON reels_study_guide (collection_id);
        """)
        self._conn.commit()

        # Startup sweep: any collection still marked 'generating' belonged
        # to a background thread that died with the previous process — it
        # is definitely not still running (this codebase has no
        # cross-restart job resumption for this pipeline, unlike the
        # OpenAI-Batch-API-backed pipelines elsewhere in this file). Relabel
        # rather than delete: whatever guides it already saved via on_guide
        # before the process died are real, valid, and kept.
        try:
            self._conn.execute(
                "UPDATE study_guide_collections SET status = 'interrupted' WHERE status = 'generating'"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

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
            (9, "2026-10-30", "Full transcripts in summaries",
             "The summary prompt only passed the first 400 characters of the "
             "audio transcript to the model, so reels with a lot of speech "
             "(lists, tutorials, \"N types of...\" videos) got summaries, "
             "titles and tags built from speech cut off mid-sentence — the "
             "full transcript was always stored, only the prompt truncated "
             "it. Now 3000 characters. Only posts whose transcript was "
             "actually longer than 400 characters are flagged; rescanning "
             "them rebuilds the summary from the stored transcript and "
             "re-scores importance (the old score was judged from the "
             "truncated summary); boards and ratings are kept."),
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
        "language, is_hidden, analysis_version, media_files, importance, "
        "enjoyment_rating, perceived_importance_rating, caption, date_saved, "
        + IS_SENSITIVE_COLUMN
    )

    def _visible_sql(self):
        """WHERE-clause fragment for "posts a client may see": not
        soft-deleted, and — unless the backend was started with
        --show-sensitive — not in a sensitive Instagram folder (see
        core/sensitive.py). Every client-facing read path filters on this."""
        clause = "(is_hidden IS NULL OR is_hidden = 0)"
        if not show_sensitive():
            clause += f" AND shortcode NOT IN ({SENSITIVE_SHORTCODES_SQL})"
        return f"({clause})"

    def get_sensitive_shortcodes(self) -> set:
        """Shortcodes in a sensitive Instagram folder, regardless of
        --show-sensitive — for the recommendation-signal exclusions, which
        apply even when those posts are being shown."""
        if not self.is_connected():
            return set()
        try:
            return {r[0] for r in self._conn.execute(SENSITIVE_SHORTCODES_SQL).fetchall()}
        except Exception as e:
            print(f"[WARNING]  Error fetching sensitive shortcodes: {e}")
            return set()

    def is_post_visible(self, shortcode) -> bool:
        """Single-post form of _visible_sql() for API routes that look one
        post up by shortcode (check_cache() itself stays unfiltered — main.py
        and the rescan pipeline rely on it seeing every row)."""
        if not self.is_connected():
            return False
        try:
            return self._conn.execute(
                f"SELECT 1 FROM analyses WHERE shortcode = ? AND {self._visible_sql()}", (shortcode,)
            ).fetchone() is not None
        except Exception as e:
            print(f"[WARNING]  Error checking post visibility: {e}")
            return False

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
        d['should_revisit'] = bool(d.get('should_revisit'))
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
                      language=None, media_files=None, importance=None,
                      model_used=None, transcription_backend=None, caption=None,
                      date_saved=None, importance_reason=None):
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

        importance_reason: the model's justification for the importance
        score above, or None if unscored/unparseable. Same protect-from-
        blanking treatment as importance itself (see the ON CONFLICT clause
        below) — a rescan that skips re-scoring must not wipe a prior
        justification.

        model_used: AI Model Router key that generated this post's summary
        (e.g. "openai_gpt41"), or None/"" if not tracked for this call site.

        transcription_backend: which Whisper backend produced
        audio_transcription ("Groq Whisper API" / "Local Whisper (base)"),
        or None/"" if there was no audio track.

        caption: the raw Instagram post caption as scraped by instaloader
        (see instagram/instagram_downloader.py), stored verbatim — distinct
        from the AI-generated `summary`. None/"" for non-Instagram content
        or posts with no caption.

        date_saved: the real date this post was saved to Instagram (NOT its
        publish date, which is `post_date` above) — looked up by
        scripts/import_saved_instagram.py from saved_posts.json and passed
        through /analyze same as caption/hashtags. None for posts saved
        individually (not via that import flow) or not found in the
        lookup file. Never coerced to a fake value — see the date_saved
        migration comment in _create_tables for the full story.
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

            with self._write_lock:
                self._conn.execute("""
                    INSERT INTO analyses
                        (shortcode, url, username, content_type, analyzed_at, updated_at, post_date, likes,
                         thumbnail, title, summary, tags, music, category,
                         visual_analysis, audio_transcription, text_analysis, source_hashtags, embedding,
                         analysis_version, language, media_files, importance, model_used, transcription_backend,
                         caption, date_saved, importance_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(shortcode) DO UPDATE SET
                        url                   = excluded.url,
                        username              = excluded.username,
                        content_type          = excluded.content_type,
                        updated_at            = excluded.updated_at,
                        post_date             = excluded.post_date,
                        likes                 = excluded.likes,
                        thumbnail             = excluded.thumbnail,
                        title                 = excluded.title,
                        summary               = excluded.summary,
                        tags                  = excluded.tags,
                        music                 = excluded.music,
                        category              = excluded.category,
                        visual_analysis       = excluded.visual_analysis,
                        audio_transcription   = excluded.audio_transcription,
                        text_analysis         = excluded.text_analysis,
                        source_hashtags       = excluded.source_hashtags,
                        embedding             = CASE WHEN excluded.embedding != '' THEN excluded.embedding ELSE analyses.embedding END,
                        analysis_version      = excluded.analysis_version,
                        language              = excluded.language,
                        media_files           = CASE WHEN excluded.media_files != '[]' THEN excluded.media_files ELSE analyses.media_files END,
                        importance            = CASE WHEN excluded.importance IS NOT NULL THEN excluded.importance ELSE analyses.importance END,
                        model_used            = excluded.model_used,
                        transcription_backend = excluded.transcription_backend,
                        caption               = CASE WHEN excluded.caption != '' THEN excluded.caption ELSE analyses.caption END,
                        date_saved            = CASE WHEN excluded.date_saved IS NOT NULL THEN excluded.date_saved ELSE analyses.date_saved END,
                        importance_reason     = CASE WHEN excluded.importance_reason IS NOT NULL THEN excluded.importance_reason ELSE analyses.importance_reason END
                """, (shortcode, url, username, content_type, now, now, post_date, likes,
                      thumbnail, title, summary, tags_json, music, category_json,
                      visual_analysis, audio_transcription, text_analysis, source_hashtags_json, embedding_json,
                      version, language_json, media_files_json, importance,
                      model_used or "", transcription_backend or "", caption or "", date_saved, importance_reason))

                # Restore any eloquence score stashed by hard_delete_post() (force
                # re-analysis) — see that method and eloquence_stash's comment in
                # _create_tables. No-op for a normal first-time save/UPSERT where
                # nothing was ever stashed for this shortcode.
                stashed = self._conn.execute(
                    "SELECT is_eloquent, eloquence_rationale, is_tutorial, eloquence_reviewed "
                    "FROM eloquence_stash WHERE shortcode = ?",
                    (shortcode,)
                ).fetchone()
                if stashed:
                    self._conn.execute(
                        "UPDATE analyses SET is_eloquent = ?, eloquence_rationale = ?, is_tutorial = ?, "
                        "eloquence_reviewed = ? WHERE shortcode = ?",
                        (stashed[0], stashed[1], stashed[2], stashed[3], shortcode),
                    )
                    self._conn.execute("DELETE FROM eloquence_stash WHERE shortcode = ?", (shortcode,))

                self._conn.commit()
            self._sync_trusted_authors_board(username, shortcode)
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

    def update_caption(self, shortcode, caption) -> bool:
        """Set just the raw Instagram caption for an existing post — used by
        scripts/backfill_captions.py so it doesn't need to re-run analysis."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute(
                "UPDATE analyses SET caption = ? WHERE shortcode = ?",
                (caption, shortcode),
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error updating caption: {e}")
            return False

    def update_date_saved(self, shortcode, date_saved) -> bool:
        """Set the real Instagram save date for an existing post — used by
        scripts/backfill_date_saved.py. (Live imports set this at analysis
        time instead, via save_analysis()'s date_saved param — see
        AnalyzeRequest.date_saved in api.py.)"""
        if not self.is_connected():
            return False
        try:
            self._conn.execute(
                "UPDATE analyses SET date_saved = ? WHERE shortcode = ?",
                (date_saved, shortcode),
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error updating date_saved: {e}")
            return False

    # ------------------------------------------------------------------
    # import_jobs — background runs of scripts/import_saved_instagram.py
    # (or _by_collection.py) kicked off from superbrain-web's /import page.
    # See api.py's /instagram-export/* routes.
    # ------------------------------------------------------------------

    def create_import_job(self, job_id, mode, priority_folder, reverse_collections, export_filename):
        """Create a new 'running' import job row. Returns the saved dict, or None on failure."""
        if not self.is_connected():
            return None
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO import_jobs "
                "(id, mode, priority_folder, reverse_collections, export_filename, status, started_at) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?)",
                (job_id, mode, priority_folder, int(reverse_collections), export_filename, now)
            )
            self._conn.commit()
            return self.get_import_job(job_id)
        except Exception as e:
            print(f"[WARNING]  Error creating import job: {e}")
            return None

    def update_import_job(self, job_id, **fields) -> bool:
        """Generic column setter for an import job — used both to append to
        log_tail as the subprocess streams output and to set the terminal
        status/error/finished_at once it exits."""
        if not self.is_connected() or not fields:
            return False
        try:
            columns = ", ".join(f"{col} = ?" for col in fields)
            values = list(fields.values()) + [job_id]
            cur = self._conn.execute(f"UPDATE import_jobs SET {columns} WHERE id = ?", values)
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error updating import job: {e}")
            return False

    def get_import_job(self, job_id):
        """Return a single import job row, or None."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM import_jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"[WARNING]  Error getting import job: {e}")
            return None

    def list_import_jobs(self, limit=20) -> list:
        """Return the most recent import jobs, newest first."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM import_jobs ORDER BY started_at DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error listing import jobs: {e}")
            return []

    def mark_stale_import_jobs_failed(self) -> int:
        """Flip any job still 'running' from before the last server restart
        to 'failed' — the OS subprocess dies with the parent process, so a
        'running' row surviving a restart is always stale. The underlying
        scripts/import_state.json resumable state isn't touched, so simply
        starting a new job against the same export file picks up right
        where it left off. Called once on backend startup. Returns the
        number of rows updated."""
        if not self.is_connected():
            return 0
        try:
            now = datetime.utcnow().isoformat()
            cur = self._conn.execute(
                "UPDATE import_jobs SET status = 'failed', error = ?, finished_at = ? "
                "WHERE status = 'running'",
                ("Interrupted by server restart", now)
            )
            self._conn.commit()
            return cur.rowcount
        except Exception as e:
            print(f"[WARNING]  Error marking stale import jobs failed: {e}")
            return 0

    def update_importance(self, shortcode, importance, importance_reason=None) -> bool:
        """Set the importance score (and its justification) for an existing
        post and stamp it as reviewed under CURRENT_ANALYSIS_VERSION — used
        by the backfill script so it doesn't need to re-run full analysis.
        Bumping the version here is what clears the post from the
        'needs_review' queue the version-6 bump otherwise flagged it into."""
        if not self.is_connected():
            return False
        try:
            with self._write_lock:
                self._conn.execute(
                    "UPDATE analyses SET importance = ?, importance_reason = ?, analysis_version = ? WHERE shortcode = ?",
                    (importance, importance_reason, CURRENT_ANALYSIS_VERSION, shortcode),
                )
                self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error updating importance: {e}")
            return False

    def update_eloquence(self, shortcode, is_eloquent: bool, rationale: str, is_tutorial=None) -> bool:
        """Set the eloquence verdict/rationale (and optionally is_tutorial)
        for an existing post (see core/eloquence.py). Does not touch
        analysis_version — eloquence is a separate scored dimension, not
        part of the core analysis pipeline. is_tutorial is only written when
        explicitly passed (not None), so callers that score eloquence and
        tutorial-ness separately can still each write just their own field."""
        if not self.is_connected():
            return False
        try:
            if is_tutorial is None:
                cur = self._conn.execute(
                    "UPDATE analyses SET is_eloquent = ?, eloquence_rationale = ? WHERE shortcode = ?",
                    (1 if is_eloquent else 0, rationale, shortcode),
                )
            else:
                cur = self._conn.execute(
                    "UPDATE analyses SET is_eloquent = ?, eloquence_rationale = ?, is_tutorial = ? WHERE shortcode = ?",
                    (1 if is_eloquent else 0, rationale, 1 if is_tutorial else 0, shortcode),
                )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error updating eloquence: {e}")
            return False

    # ── eloquence_overrides (manual human corrections — see the table's
    # comment in _create_tables for why this log exists) ──

    def override_eloquence_not_eloquent(self, shortcode: str) -> str:
        """Flip one post's is_eloquent to False as a manual human correction,
        logging the AI's prior verdict/rationale to eloquence_overrides
        first. Only logs (and only updates) when the post was actually
        eloquent — calling this on a post that's already not eloquent is a
        genuine no-op, not a fresh "correction" worth logging again.

        Returns 'overridden', 'already_not_eloquent', or 'not_found'.
        """
        if not self.is_connected():
            return "not_found"
        try:
            row = self._conn.execute(
                "SELECT is_eloquent, eloquence_rationale, is_tutorial FROM analyses WHERE shortcode = ?",
                (shortcode,)
            ).fetchone()
            if row is None:
                return "not_found"
            if row["is_eloquent"] != 1:
                return "already_not_eloquent"

            self._conn.execute(
                "INSERT INTO eloquence_overrides (shortcode, ai_rationale, ai_was_tutorial, overridden_at) "
                "VALUES (?, ?, ?, ?)",
                (shortcode, row["eloquence_rationale"], row["is_tutorial"], datetime.utcnow().isoformat()),
            )
            self._conn.execute(
                "UPDATE analyses SET is_eloquent = 0, eloquence_rationale = ?, eloquence_reviewed = NULL "
                "WHERE shortcode = ?",
                ("Manually overridden: marked not eloquent from the web UI.", shortcode),
            )
            self._conn.commit()
            return "overridden"
        except Exception as e:
            print(f"[WARNING]  Error overriding eloquence for {shortcode}: {e}")
            return "not_found"

    def approve_eloquence(self, shortcode: str) -> str:
        """Stamp one post as human-reviewed-and-confirmed eloquent
        (eloquence_reviewed = 1) — the "approve" half of the /eloquent
        page's per-card review, the other half being
        override_eloquence_not_eloquent(). Only meaningful for a post that
        is currently eloquent; approving anything else is refused rather
        than silently stamping a post the page would never show.

        Returns 'approved', 'already_approved', 'not_eloquent', or 'not_found'.
        """
        if not self.is_connected():
            return "not_found"
        try:
            row = self._conn.execute(
                "SELECT is_eloquent, eloquence_reviewed FROM analyses WHERE shortcode = ?",
                (shortcode,)
            ).fetchone()
            if row is None:
                return "not_found"
            if row["is_eloquent"] != 1:
                return "not_eloquent"
            if row["eloquence_reviewed"] == 1:
                return "already_approved"
            self._conn.execute(
                "UPDATE analyses SET eloquence_reviewed = 1 WHERE shortcode = ?", (shortcode,)
            )
            self._conn.commit()
            return "approved"
        except Exception as e:
            print(f"[WARNING]  Error approving eloquence for {shortcode}: {e}")
            return "not_found"

    def get_eloquence_overrides(self):
        """All logged manual eloquence corrections, newest first — for
        reviewing AI false positives to refine ELOQUENCE_PROMPT."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.execute("SELECT * FROM eloquence_overrides ORDER BY overridden_at DESC")
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error fetching eloquence overrides: {e}")
            return []

    def update_is_tutorial(self, shortcode, is_tutorial: bool) -> bool:
        """Set whether an eloquent post is delivered as a tutorial/how-to vs.
        a speech/commentary (see core/eloquence.py's domain carve-out)."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute(
                "UPDATE analyses SET is_tutorial = ? WHERE shortcode = ?",
                (1 if is_tutorial else 0, shortcode),
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error updating is_tutorial: {e}")
            return False

    def get_posts_for_eloquence_scoring(self, min_length: int, include_scored: bool = False):
        """Return [{shortcode, title, audio_transcription}, ...] for posts
        long enough to be eloquence-scoring candidates (length filtering
        only — the filler-ratio pre-filter is applied in Python by the
        caller, see core/eloquence.py's passes_prefilter()). Skips posts
        already scored (is_eloquent IS NOT NULL) unless include_scored."""
        if not self.is_connected():
            return []
        try:
            query = "SELECT shortcode, title, audio_transcription FROM analyses WHERE LENGTH(audio_transcription) > ?"
            params = [min_length]
            if not include_scored:
                query += " AND is_eloquent IS NULL"
            cur = self._conn.execute(query, params)
            return [{"shortcode": r[0], "title": r[1], "audio_transcription": r[2]} for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting eloquence-scoring candidates: {e}")
            return []

    # ── eloquence_batch_jobs (scripts/score_eloquence.py --batch, ANALYSIS_MODE=batch) ──
    # See eloquence_batch_jobs' comment in _create_tables for why this is a
    # single-phase table with many shortcodes sharing one batch_id.

    def enqueue_eloquence_batch_jobs(self, shortcodes: list, batch_id: str) -> bool:
        """Record one shared OpenAI batch job covering all of `shortcodes`."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.executemany("""
                INSERT INTO eloquence_batch_jobs (shortcode, batch_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    batch_id   = excluded.batch_id,
                    updated_at = excluded.updated_at,
                    last_error = NULL
            """, [(sc, batch_id, now, now) for sc in shortcodes])
            self._conn.commit()
            print(f"📦 Submitted eloquence batch job for {len(shortcodes)} post(s): {batch_id}")
            return True
        except Exception as e:
            print(f"[WARNING]  Error enqueuing eloquence batch jobs: {e}")
            return False

    def get_eloquence_batch_jobs(self, batch_id: str = None):
        """Return eloquence_batch_jobs rows, optionally filtered to one shared batch_id
        (the grouping query core/eloquence_batch_processor.py uses to advance every
        shortcode sharing one OpenAI batch job together)."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            if batch_id:
                cur.execute("SELECT * FROM eloquence_batch_jobs WHERE batch_id = ? ORDER BY created_at", (batch_id,))
            else:
                cur.execute("SELECT * FROM eloquence_batch_jobs ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting eloquence batch jobs: {e}")
            return []

    def mark_eloquence_batch_job_error(self, shortcode: str, error: str) -> bool:
        """Best-effort observability write — does not delete the row."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE eloquence_batch_jobs SET last_error = ?, updated_at = ? WHERE shortcode = ?",
                (error, now, shortcode)
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error recording eloquence batch job error: {e}")
            return False

    def delete_eloquence_batch_job(self, shortcode: str) -> bool:
        """Remove an eloquence_batch_jobs row on final success or failure. On
        failure this deliberately does NOT touch the analyses row — is_eloquent
        stays NULL, so the post is simply picked up again as an unscored
        candidate on the next scripts/score_eloquence.py run."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute("DELETE FROM eloquence_batch_jobs WHERE shortcode = ?", (shortcode,))
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error deleting eloquence batch job: {e}")
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
                f"AND {self._visible_sql()}"
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

    def get_embeddings_fingerprint(self) -> str:
        """Cheap change-detector for the set returned by get_all_embeddings().

        Reads only each vector's length and first 64 characters of JSON text
        (its first few floats at full precision) in SQL, never the full ~30 KB
        vectors, so it's safe to compute on every /export. Changes whenever a
        post gains, loses (deleted/hidden) or changes its embedding — how
        GET /embeddings and superbrain-web decide whether their cached vectors
        are stale.
        """
        if not self.is_connected():
            return ""
        try:
            cur = self._conn.execute(
                "SELECT shortcode, length(embedding), substr(embedding, 1, 64) FROM analyses "
                "WHERE embedding IS NOT NULL AND embedding != '' "
                f"AND {self._visible_sql()} ORDER BY shortcode"
            )
            h = hashlib.sha256()
            for shortcode, length, prefix in cur.fetchall():
                h.update(f"{shortcode}\0{length}\0{prefix}\n".encode("utf-8"))
            return h.hexdigest()[:32]
        except Exception as e:
            print(f"[WARNING]  Error fingerprinting embeddings: {e}")
            return ""

    # ------------------------------------------------------------------
    # Personalization signals — view/search history + embedding cache
    # (backs superbrain-web's Home recommendation engine, src/lib/recommendations.ts)
    # ------------------------------------------------------------------

    def log_post_view(self, shortcode, client_env="prod") -> bool:
        """Insert a qualifying-view row. Best-effort — callers (POST
        /post/{shortcode}/view) must not let a failure here surface to the
        user. No existence check against `analyses`: an orphaned row is
        harmless, the web engine drops unmatched shortcodes when hydrating.
        client_env should be 'dev' or 'prod' (api.py normalizes anything else
        to 'prod') — see the client_env migration above post_views' CREATE
        TABLE for why. A sensitive-folder post (core/sensitive.py) is never
        logged — it must never become a recommendation signal."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute(
                "INSERT INTO post_views (shortcode, viewed_at, client_env) "
                f"SELECT ?, ?, ? WHERE ? NOT IN ({SENSITIVE_SHORTCODES_SQL})",
                (shortcode, datetime.utcnow().isoformat(), client_env, shortcode),
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error logging post view: {e}")
            return False

    def get_view_history(self, since=None, limit=5000):
        """Return [{shortcode, viewed_at}], newest first. Only 'prod'-tagged
        rows — this feeds the recommendation engine exclusively, so dev-build
        testing traffic must never appear here (see the client_env
        migration). Sensitive-folder posts are always left out, including
        views logged before the post landed in that folder."""
        if not self.is_connected():
            return []
        try:
            if since:
                cur = self._conn.execute(
                    "SELECT shortcode, viewed_at FROM post_views "
                    "WHERE viewed_at >= ? AND client_env = 'prod' "
                    f"AND shortcode NOT IN ({SENSITIVE_SHORTCODES_SQL}) ORDER BY viewed_at DESC LIMIT ?",
                    (since, limit),
                )
            else:
                cur = self._conn.execute(
                    "SELECT shortcode, viewed_at FROM post_views "
                    "WHERE client_env = 'prod' "
                    f"AND shortcode NOT IN ({SENSITIVE_SHORTCODES_SQL}) ORDER BY viewed_at DESC LIMIT ?",
                    (limit,),
                )
            return [{"shortcode": s, "viewed_at": v} for s, v in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error fetching view history: {e}")
            return []

    def get_cached_query_embedding(self, query_text):
        """Return a previously-generated embedding for this exact query text
        (normalized: trimmed + lowercased), if one exists in the `embeddings`
        cache — lets GET /search/semantic and the chat RAG pipeline skip a
        redundant embedding-API call when a query repeats (e.g. the /space
        search box re-submitting the same term). Independent of
        search_queries (the usage/recommendation-history table), so clearing
        that table never invalidates this cache. Returns None on no match."""
        if not self.is_connected() or not query_text:
            return None
        try:
            cur = self._conn.execute(
                "SELECT embedding FROM embeddings WHERE text = LOWER(TRIM(?))",
                (query_text,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            return json.loads(row[0])
        except Exception as e:
            print(f"[WARNING]  Error fetching cached query embedding: {e}")
            return None

    def log_search_query(self, query_text, query_embedding, source="search", client_env="prod") -> bool:
        """Record one search/chat query usage instance. Upserts the embedding
        into the `embeddings` cache (deduped by normalized text) and always
        inserts a fresh search_queries row pointing at it — even when the
        embedding was reused from get_cached_query_embedding — so the event's
        own timestamp is available for recency-weighting. Best-effort — must
        never break the search/chat request it's attached to. client_env
        should be 'dev' or 'prod' (api.py normalizes anything else to 'prod')
        — see the client_env migration above search_queries' CREATE TABLE for
        why."""
        if not self.is_connected():
            return False
        try:
            embedding_id = None
            if query_embedding and query_text:
                key = query_text.strip().lower()
                cur = self._conn.execute("SELECT id FROM embeddings WHERE text = ?", (key,))
                row = cur.fetchone()
                if row:
                    embedding_id = row[0]
                else:
                    cur = self._conn.execute(
                        "INSERT INTO embeddings (text, embedding, created_at) VALUES (?, ?, ?)",
                        (key, json.dumps(query_embedding), datetime.utcnow().isoformat()),
                    )
                    embedding_id = cur.lastrowid
            self._conn.execute(
                "INSERT INTO search_queries (query_text, embedding_id, source, created_at, client_env) "
                "VALUES (?, ?, ?, ?, ?)",
                (query_text, embedding_id, source, datetime.utcnow().isoformat(), client_env),
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error logging search query: {e}")
            return False

    def get_search_history(self, since=None, limit=2000):
        """Return [{query_text, query_embedding: [float,...] | None, source, created_at}],
        newest first. Only 'prod'-tagged rows — same reasoning as
        get_view_history above. Embedding is joined in live from the
        `embeddings` cache via embedding_id."""
        if not self.is_connected():
            return []
        try:
            if since:
                cur = self._conn.execute(
                    "SELECT sq.query_text, e.embedding, sq.source, sq.created_at "
                    "FROM search_queries sq LEFT JOIN embeddings e ON e.id = sq.embedding_id "
                    "WHERE sq.created_at >= ? AND sq.client_env = 'prod' ORDER BY sq.created_at DESC LIMIT ?",
                    (since, limit),
                )
            else:
                cur = self._conn.execute(
                    "SELECT sq.query_text, e.embedding, sq.source, sq.created_at "
                    "FROM search_queries sq LEFT JOIN embeddings e ON e.id = sq.embedding_id "
                    "WHERE sq.client_env = 'prod' ORDER BY sq.created_at DESC LIMIT ?",
                    (limit,),
                )
            out = []
            for query_text, emb_json, source, created_at in cur.fetchall():
                try:
                    embedding = json.loads(emb_json) if emb_json else None
                except Exception:
                    embedding = None
                out.append({
                    "query_text": query_text,
                    "query_embedding": embedding,
                    "source": source,
                    "created_at": created_at,
                })
            return out
        except Exception as e:
            print(f"[WARNING]  Error fetching search history: {e}")
            return []

    def get_recent(self, limit=10):
        """Return the most recently analysed posts (excludes soft-deleted)."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT *, {IS_SENSITIVE_COLUMN} FROM analyses WHERE {self._visible_sql()} ORDER BY analyzed_at DESC LIMIT ?", (limit,)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error retrieving recent: {e}")
            return []

    def get_recent_light(self, limit=50, offset=0, sort="recent"):
        """Return recent posts with only UI-essential fields (no analysis blobs).

        sort: "recent" (default, analyzed_at DESC), "importance" (importance
        DESC, unscored posts last, analyzed_at DESC as tie-breaker),
        "date_saved" (real Instagram save date, oldest first — see
        scripts/backfill_date_saved.py; posts without a known date_saved
        continue by analyzed_at ASC, forming one continuous oldest-to-newest
        timeline), or "post_date" (the content's own publish date, oldest
        first, same analyzed_at ASC fallback for posts with no post_date —
        a distinct axis from date_saved: "when was this posted" vs. "when
        did I save it").
        """
        if not self.is_connected():
            return []
        order_clause = (
            "ORDER BY importance IS NULL, importance DESC, analyzed_at DESC"
            if sort == "importance" else
            "ORDER BY date_saved IS NULL, date_saved ASC, analyzed_at ASC"
            if sort == "date_saved" else
            "ORDER BY post_date IS NULL, post_date ASC, analyzed_at ASC"
            if sort == "post_date" else
            "ORDER BY analyzed_at DESC"
        )
        try:
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT {self.LIGHT_COLUMNS} FROM analyses "
                f"WHERE {self._visible_sql()} "
                f"{order_clause} LIMIT ? OFFSET ?",
                (limit, offset)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error retrieving recent (light): {e}")
            return []

    def get_posts_since(self, updated_after: str, limit=1000):
        """Return posts updated after the given ISO timestamp (delta sync).
        Includes soft-deleted posts so the app knows to hide them, but never
        sensitive-folder posts unless --show-sensitive (core/sensitive.py)."""
        if not self.is_connected():
            return []
        sensitive_filter = "" if show_sensitive() else f"AND shortcode NOT IN ({SENSITIVE_SHORTCODES_SQL}) "
        try:
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT {self.LIGHT_COLUMNS} FROM analyses "
                "WHERE updated_at > ? "
                f"{sensitive_filter}"
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
            cur.execute(f"SELECT COUNT(*) FROM analyses WHERE {self._visible_sql()}")
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
                f"SELECT *, {IS_SENSITIVE_COLUMN} FROM analyses WHERE (category = ? OR category LIKE ?) "
                f"AND {self._visible_sql()} ORDER BY analyzed_at DESC LIMIT ?",
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
                f"SELECT *, {IS_SENSITIVE_COLUMN} FROM analyses WHERE ({conditions}) AND {self._visible_sql()} ORDER BY analyzed_at DESC LIMIT ?",
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

            cur.execute(f"SELECT COUNT(*) FROM analyses WHERE {self._visible_sql()}")
            total = cur.fetchone()[0]

            if show_sensitive():
                cur.execute("SELECT COUNT(*) FROM collections")
            else:
                cur.execute(f"SELECT COUNT(*) FROM collections WHERE lower(trim(name)) NOT IN ({_SENSITIVE_NAMES_SQL})")
            total_collections = cur.fetchone()[0]

            # category is stored as a JSON array (or a legacy plain string) —
            # tally each label a post carries rather than grouping on the raw
            # column value, since one post can now have multiple categories.
            cur.execute(
                f"SELECT category FROM analyses WHERE {self._visible_sql()}"
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
                f"SELECT *, {IS_SENSITIVE_COLUMN} FROM analyses WHERE {self._visible_sql()} ORDER BY analyzed_at DESC LIMIT ? OFFSET ?",
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

            with self._write_lock:
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

    def get_queue_overview(self):
        """Every processing_queue row that hasn't finished, with the full
        context the admin "needs attention" view needs in one query.

        get_processing()/get_queue()/get_retry_queue() each return a
        different subset with a different column list (and get_processing()
        returns bare shortcodes, no URL), which is fine for their callers
        but can't answer "show me everything that is stuck". This returns
        every non-terminal status in one pass instead — a finished item is
        deleted from this table by remove_from_queue(), so "still here" is
        exactly "not done".
        """
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("""
                SELECT shortcode, url, status, content_type, reason, attempts,
                       retry_after, added_at, updated_at, started_at, position
                FROM processing_queue
                WHERE status IN ('queued', 'processing', 'retry', 'batch')
                ORDER BY
                    CASE status
                        WHEN 'processing' THEN 0
                        WHEN 'queued'     THEN 1
                        WHEN 'batch'      THEN 2
                        ELSE 3
                    END,
                    position, retry_after
            """)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting queue overview: {e}")
            return []

    def get_queue_status(self, shortcode: str):
        """Return one shortcode's processing_queue status, or None if absent.

        A PK lookup, deliberately cheaper than get_processing()/get_queue()/
        get_batch_jobs() for the "is this specific reel already in flight?"
        admission check — which runs on every /analyze request.
        """
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT status FROM processing_queue WHERE shortcode = ?", (shortcode,)
            )
            row = cur.fetchone()
            return row["status"] if row else None
        except Exception as e:
            print(f"[WARNING]  Error getting queue status for {shortcode}: {e}")
            return None

    def get_analyzed_shortcodes(self) -> set:
        """Every shortcode that has a saved row in `analyses`.

        Used to tell "still stuck" apart from "already analyzed by some
        other path" when reconciling the resumable importer's state file
        against reality — that file only learns a post succeeded on the
        next run of the import script that touches it.
        """
        if not self.is_connected():
            return set()
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT shortcode FROM analyses")
            return {r["shortcode"] for r in cur.fetchall()}
        except Exception as e:
            print(f"[WARNING]  Error getting analyzed shortcodes: {e}")
            return set()

    def get_deleted_shortcodes(self) -> set:
        """Every shortcode the user has deleted (soft-delete sync log).

        A deleted post that a stale import-state file still lists as
        pending must not be presented as work to redo.
        """
        if not self.is_connected():
            return set()
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT shortcode FROM deleted_log")
            return {r["shortcode"] for r in cur.fetchall()}
        except Exception as e:
            print(f"[WARNING]  Error getting deleted shortcodes: {e}")
            return set()

    # ==================== QUEUE MANAGEMENT ====================

    def add_to_queue(self, shortcode, url, caption=None, hashtags=None, date_saved=None,
                     media_folder=None):
        """Add item to processing queue. Returns queue position (1-based), or -1 on error.

        caption/hashtags/date_saved: optional client-supplied hint (see
        AnalyzeRequest), persisted so queue_worker can still forward it to
        main.py once this item is eventually picked up — otherwise it's
        silently lost for any request that arrives while the server is busy.

        media_folder: manually uploaded media to analyze instead of
        downloading (POST /manual-upload). Unlike the fields above, an
        omitted value here does NOT clear a stored one — the retry drain
        re-queues with `add_to_queue(shortcode, url)` and nothing else, and
        wiping the folder there would turn a queued manual upload back into
        the download attempt it was meant to replace.
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
                INSERT INTO processing_queue (shortcode, url, status, position, added_at, updated_at, caption, hashtags, date_saved, media_folder)
                VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    url          = excluded.url,
                    status       = 'queued',
                    position     = excluded.position,
                    updated_at   = excluded.updated_at,
                    caption      = excluded.caption,
                    hashtags     = excluded.hashtags,
                    date_saved   = excluded.date_saved,
                    media_folder = CASE
                        WHEN excluded.media_folder IS NOT NULL THEN excluded.media_folder
                        ELSE processing_queue.media_folder
                    END
            """, (shortcode, url, position, now, now, caption or '', hashtags_json, date_saved,
                  media_folder))
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
                "SELECT shortcode, url, position, caption, hashtags, date_saved, media_folder "
                "FROM processing_queue WHERE status = 'queued' ORDER BY position"
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
                    "date_saved": r["date_saved"] or None,
                    "media_folder": r["media_folder"] or None,
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
            with self._write_lock:
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
            with self._write_lock:
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

    # ==================== BATCH PROCESSING (ANALYSIS_MODE=batch) ====================

    def _enqueue_batch_job_entry(self, shortcode: str, url: str, content_type: str,
                                  phase: str, batch_id_column: str, batch_id: str,
                                  state_json: str) -> bool:
        """
        Shared implementation for the two possible entry points into the
        batch_jobs state machine (enqueue_analysis_batch_job /
        enqueue_batch_job below) — both record a freshly-submitted OpenAI
        Batch API job and mark the item as in-flight in processing_queue
        (status='batch') so it's excluded from get_queue()/get_processing()
        without being lost from view entirely.
        """
        if not self.is_connected():
            return False
        if batch_id_column not in ("analysis_batch_id", "summary_batch_id"):
            raise ValueError(f"Invalid entry-point batch id column: {batch_id_column}")
        # batch_id_column is a fixed, code-controlled value (never user input,
        # validated above), so it's safe to interpolate as a column name.
        # analysis_val/summary_val are computed here (not via SQL CASE WHEN)
        # since batch_id_column is already known in Python at this point.
        analysis_val = batch_id if batch_id_column == "analysis_batch_id" else None
        summary_val = batch_id if batch_id_column == "summary_batch_id" else None
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute("""
                INSERT INTO batch_jobs
                    (shortcode, url, content_type, phase, analysis_batch_id,
                     summary_batch_id, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    url                  = excluded.url,
                    content_type         = excluded.content_type,
                    phase                = excluded.phase,
                    analysis_batch_id    = excluded.analysis_batch_id,
                    summary_batch_id     = excluded.summary_batch_id,
                    importance_batch_id  = NULL,
                    embedding_batch_id   = NULL,
                    state_json           = excluded.state_json,
                    updated_at           = excluded.updated_at,
                    last_error           = NULL
            """, (shortcode, url, content_type, phase, analysis_val, summary_val,
                  state_json, now, now))
            self._conn.execute("""
                INSERT INTO processing_queue
                    (shortcode, url, content_type, status, position, added_at, started_at, updated_at)
                VALUES (?, ?, ?, 'batch', 0, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    status     = 'batch',
                    started_at = excluded.started_at,
                    updated_at = excluded.updated_at
            """, (shortcode, url, content_type, now, now, now))
            self._conn.commit()
            print(f"📦 Submitted batch job for {shortcode} ({phase}): {batch_id}")
            return True
        except Exception as e:
            print(f"[WARNING]  Error enqueuing batch job: {e}")
            return False

    def enqueue_analysis_batch_job(self, shortcode: str, url: str, content_type: str,
                                    analysis_batch_id: str, state_json: str) -> bool:
        """Entry point when a reel has video/image files and/or an info.txt
        to analyze: one bundled batch job (one vision request per file, plus
        one text-analysis request), phase='analysis_pending'."""
        return self._enqueue_batch_job_entry(
            shortcode, url, content_type, "analysis_pending",
            "analysis_batch_id", analysis_batch_id, state_json
        )

    def enqueue_batch_job(self, shortcode: str, url: str, content_type: str,
                           summary_batch_id: str, state_json: str) -> bool:
        """Entry point for the rare reel with nothing to visually/textually
        analyze (no media, no info.txt) — skips straight to
        phase='summary_pending' with empty visual/text content, same as the
        immediate pipeline would produce for such a post."""
        return self._enqueue_batch_job_entry(
            shortcode, url, content_type, "summary_pending",
            "summary_batch_id", summary_batch_id, state_json
        )

    def get_batch_jobs(self, phase: str = None):
        """Return batch_jobs rows, optionally filtered by phase."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            if phase:
                cur.execute("SELECT * FROM batch_jobs WHERE phase = ? ORDER BY created_at", (phase,))
            else:
                cur.execute("SELECT * FROM batch_jobs ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting batch jobs: {e}")
            return []

    def advance_batch_job(self, shortcode: str, phase: str,
                           summary_batch_id: str = None,
                           importance_batch_id: str = None,
                           embedding_batch_id: str = None,
                           state_json: str = None) -> bool:
        """Move a batch job to a new phase — either 'analysis_pending' ->
        'summary_pending' (pass summary_batch_id) or 'summary_pending' ->
        'scoring_pending' (pass importance_batch_id/embedding_batch_id) —
        recording whichever follow-up batch id(s) this transition produced
        and the enriched resume state. Each id column is only touched when
        explicitly passed (COALESCE against its current value), so advancing
        to scoring_pending doesn't clobber the summary_batch_id already set
        by the previous transition."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute("""
                UPDATE batch_jobs
                SET phase = ?,
                    summary_batch_id = COALESCE(?, summary_batch_id),
                    importance_batch_id = COALESCE(?, importance_batch_id),
                    embedding_batch_id = COALESCE(?, embedding_batch_id),
                    state_json = COALESCE(?, state_json),
                    updated_at = ?
                WHERE shortcode = ?
            """, (phase, summary_batch_id, importance_batch_id, embedding_batch_id,
                  state_json, now, shortcode))
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error advancing batch job: {e}")
            return False

    def mark_batch_job_error(self, shortcode: str, error: str) -> bool:
        """Best-effort observability write — does not change phase."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE batch_jobs SET last_error = ?, updated_at = ? WHERE shortcode = ?",
                (error, now, shortcode)
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error recording batch job error: {e}")
            return False

    def delete_batch_job(self, shortcode: str) -> bool:
        """Remove a batch_jobs row on final success or hard failure."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute("DELETE FROM batch_jobs WHERE shortcode = ?", (shortcode,))
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error deleting batch job: {e}")
            return False

    # ==================== RESCAN BATCH PROCESSING ====================
    # Mirrors the batch_jobs methods above exactly in shape — see
    # rescan_batch_jobs's comment in _create_tables for why this is a
    # separate table rather than a variant of batch_jobs. Unlike
    # enqueue_batch_job(), this does NOT touch processing_queue: a rescan
    # never put the shortcode in processing_queue as status='batch' (it
    # isn't first-analysis machinery), it was there as plain
    # status='processing' while scripts/rescan_post.py did its local work —
    # so this instead just removes that row (remove_from_queue), and
    # GET /queue-status surfaces in-flight rescan batches from
    # get_rescan_batch_jobs() directly instead.

    def enqueue_rescan_batch_job(self, shortcode: str, url: str, content_type: str,
                                  summary_batch_id: str, state_json: str) -> bool:
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute("""
                INSERT INTO rescan_batch_jobs
                    (shortcode, url, content_type, phase, summary_batch_id,
                     state_json, created_at, updated_at)
                VALUES (?, ?, ?, 'summary_pending', ?, ?, ?, ?)
                ON CONFLICT(shortcode) DO UPDATE SET
                    url                 = excluded.url,
                    content_type        = excluded.content_type,
                    phase               = 'summary_pending',
                    summary_batch_id    = excluded.summary_batch_id,
                    importance_batch_id = NULL,
                    embedding_batch_id  = NULL,
                    state_json          = excluded.state_json,
                    updated_at          = excluded.updated_at,
                    last_error          = NULL
            """, (shortcode, url, content_type, summary_batch_id, state_json, now, now))
            self._conn.commit()
            self.remove_from_queue(shortcode)
            print(f"📦 Submitted rescan batch job for {shortcode}: {summary_batch_id}")
            return True
        except Exception as e:
            print(f"[WARNING]  Error enqueuing rescan batch job: {e}")
            return False

    def get_rescan_batch_jobs(self, phase: str = None):
        """Return rescan_batch_jobs rows, optionally filtered by phase."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            if phase:
                cur.execute("SELECT * FROM rescan_batch_jobs WHERE phase = ? ORDER BY created_at", (phase,))
            else:
                cur.execute("SELECT * FROM rescan_batch_jobs ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting rescan batch jobs: {e}")
            return []

    def get_rescan_batch_jobs_by_summary_batch_id(self, summary_batch_id: str):
        """The grouping query core/rescan_batch_processor.py uses to advance
        every shortcode sharing one OpenAI batch job together, rather than
        one at a time."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM rescan_batch_jobs WHERE summary_batch_id = ? ORDER BY created_at",
                (summary_batch_id,)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting rescan batch jobs by summary_batch_id: {e}")
            return []

    def advance_rescan_batch_job(self, shortcode: str, phase: str,
                                  importance_batch_id: str = None,
                                  embedding_batch_id: str = None,
                                  state_json: str = None) -> bool:
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute("""
                UPDATE rescan_batch_jobs
                SET phase = ?, importance_batch_id = ?, embedding_batch_id = ?,
                    state_json = COALESCE(?, state_json), updated_at = ?
                WHERE shortcode = ?
            """, (phase, importance_batch_id, embedding_batch_id, state_json, now, shortcode))
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error advancing rescan batch job: {e}")
            return False

    def mark_rescan_batch_job_error(self, shortcode: str, error: str) -> bool:
        """Best-effort observability write — does not change phase."""
        if not self.is_connected():
            return False
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE rescan_batch_jobs SET last_error = ?, updated_at = ? WHERE shortcode = ?",
                (error, now, shortcode)
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error recording rescan batch job error: {e}")
            return False

    def delete_rescan_batch_job(self, shortcode: str) -> bool:
        """Remove a rescan_batch_jobs row on final success or failure. On
        failure this deliberately does NOT touch the analyses row — see
        backend/CLAUDE.md's "Rescan pipeline" section for why that's correct
        here even though delete_batch_job's first-analysis equivalent
        re-queues a real retry."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute("DELETE FROM rescan_batch_jobs WHERE shortcode = ?", (shortcode,))
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error deleting rescan batch job: {e}")
            return False

    def get_posts_by_shortcodes(self, shortcodes: list) -> list:
        """Batch-fetch full analyses rows for a list of shortcodes (used by
        the rescan endpoints instead of N separate check_cache() calls)."""
        if not self.is_connected() or not shortcodes:
            return []
        try:
            placeholders = ",".join("?" for _ in shortcodes)
            cur = self._conn.cursor()
            cur.execute(f"SELECT * FROM analyses WHERE shortcode IN ({placeholders})", shortcodes)
            return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting posts by shortcodes: {e}")
            return []

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
        """Permanently remove a post row — used for force re-analysis. Returns True if deleted.

        Stashes is_eloquent/eloquence_rationale/is_tutorial into
        eloquence_stash first (if the post had actually been scored) — see
        that table's comment in _create_tables for why this is needed.
        save_analysis() restores from the stash right after the fresh row
        is inserted."""
        if not self.is_connected():
            return False
        try:
            row = self._conn.execute(
                "SELECT is_eloquent, eloquence_rationale, is_tutorial, eloquence_reviewed "
                "FROM analyses WHERE shortcode = ?",
                (shortcode,)
            ).fetchone()
            if row and row[0] is not None:
                self._conn.execute(
                    """INSERT OR REPLACE INTO eloquence_stash
                       (shortcode, is_eloquent, eloquence_rationale, is_tutorial, eloquence_reviewed, stashed_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (shortcode, row[0], row[1], row[2], row[3], datetime.utcnow().isoformat()),
                )
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
        """Insert or fully replace a collection. Returns the saved dict, or
        None for an Instagram folder that's never stored (core/sensitive.py's
        EXCLUDED_IMPORT_FOLDERS)."""
        if not self.is_connected() or is_excluded_folder(name):
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
    # Boards — user-curated collections (see the schema comment above the
    # `boards`/`board_subcollections` tables for how this differs from the
    # Instagram-import-driven `collections` above).
    # ------------------------------------------------------------------

    # Instagram usernames whose posts get auto-added to the "Trusted Authors"
    # board the moment they're saved/re-saved — a deliberate, explicit
    # exception to "the import scripts never read or write these tables"
    # (see Boards vs collections in CLAUDE.md), asked for by the user rather
    # than something boards normally do on their own. Applied from
    # save_analysis() below, which every pipeline (immediate main.py,
    # ANALYSIS_MODE=batch, the rescan pipeline, and bulk Instagram-export
    # imports via scripts/import_saved_instagram.py's POST /analyze calls)
    # writes through — so this is the one place it needs to live. Keyed
    # lowercase; extend as the user confirms more trusted authors. Separate
    # from core/importance.py's TRUSTED_CREATORS (importance-score floor) —
    # same "explicit code-level allowlist" shape, different purpose, so kept
    # as two independent lists rather than conflated.
    TRUSTED_AUTHORS_BOARD_ID = "trusted_authors"
    TRUSTED_AUTHORS_BOARD_NAME = "Trusted Authors"
    TRUSTED_AUTHORS_BOARD_ICON = "⭐"
    TRUSTED_AUTHOR_USERNAMES = {
        "linaseiche",
        "erinmerylstudy",
        "kylascan",
        "zowi.fit.feliz",
        "emmieedit",
        "yourinvestmenthq",
        "olamolam8",
    }

    def _sync_trusted_authors_board(self, username, shortcode):
        """If `username` is a trusted author, make sure `shortcode` is on the
        Trusted Authors board — creating the board itself on first use.
        No-op for every other username. Best-effort: never raises, since
        this runs as a side effect of save_analysis() and must not turn a
        successful analysis save into a failure."""
        if not username:
            return
        try:
            if username.strip().lower() not in self.TRUSTED_AUTHOR_USERNAMES:
                return
            if self.get_board(self.TRUSTED_AUTHORS_BOARD_ID) is None:
                self.create_board(
                    self.TRUSTED_AUTHORS_BOARD_ID,
                    self.TRUSTED_AUTHORS_BOARD_NAME,
                    self.TRUSTED_AUTHORS_BOARD_ICON,
                )
            self.add_post_to_board(self.TRUSTED_AUTHORS_BOARD_ID, shortcode)
        except Exception as e:
            print(f"[WARNING]  Error syncing trusted authors board: {e}")

    def _board_row_to_dict(self, row, subcollections=None):
        if row is None:
            return None
        d = dict(row)
        try:
            d['post_ids'] = json.loads(d.get('post_ids') or '[]')
        except Exception:
            d['post_ids'] = []
        d['subcollections'] = subcollections if subcollections is not None else []
        return d

    def _subcollection_row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        try:
            d['post_ids'] = json.loads(d.get('post_ids') or '[]')
        except Exception:
            d['post_ids'] = []
        return d

    def get_board_subcollections(self, board_id):
        """Return every subcollection belonging to one board, oldest first."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM board_subcollections WHERE board_id = ? ORDER BY created_at ASC",
                (board_id,)
            )
            return [self._subcollection_row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error getting board subcollections: {e}")
            return []

    def get_boards(self):
        """Return all boards ordered by created_at, each with its subcollections attached."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM boards ORDER BY created_at ASC")
            rows = cur.fetchall()
            return [self._board_row_to_dict(r, self.get_board_subcollections(r['id'])) for r in rows]
        except Exception as e:
            print(f"[WARNING]  Error getting boards: {e}")
            return []

    def get_board(self, board_id):
        """Return a single board (with its subcollections attached) by id, or None."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM boards WHERE id = ?", (board_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._board_row_to_dict(row, self.get_board_subcollections(board_id))
        except Exception as e:
            print(f"[WARNING]  Error getting board: {e}")
            return None

    def create_board(self, board_id, name, icon):
        """Insert a new, empty board. Returns the saved dict."""
        if not self.is_connected():
            return None
        try:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO boards (id, name, icon, post_ids, created_at, updated_at) VALUES (?, ?, ?, '[]', ?, ?)",
                (board_id, name, icon, now, now)
            )
            self._conn.commit()
            return self.get_board(board_id)
        except Exception as e:
            print(f"[WARNING]  Error creating board: {e}")
            return None

    def rename_board(self, board_id, name=None, icon=None):
        """Update a board's name/icon (whichever is provided). Returns the saved dict."""
        if not self.is_connected():
            return None
        try:
            existing = self.get_board(board_id)
            if existing is None:
                return None
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE boards SET name = ?, icon = ?, updated_at = ? WHERE id = ?",
                (
                    name if name is not None else existing['name'],
                    icon if icon is not None else existing['icon'],
                    now, board_id
                )
            )
            self._conn.commit()
            return self.get_board(board_id)
        except Exception as e:
            print(f"[WARNING]  Error renaming board: {e}")
            return None

    def delete_board(self, board_id):
        """Delete a board and every subcollection nested under it. Returns True if the board existed."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))
            deleted = cur.rowcount > 0
            self._conn.execute("DELETE FROM board_subcollections WHERE board_id = ?", (board_id,))
            self._conn.commit()
            return deleted
        except Exception as e:
            print(f"[WARNING]  Error deleting board: {e}")
            return False

    def add_post_to_board(self, board_id, shortcode):
        """Add one post to a board's direct post_ids (no-op if already present). Returns the saved dict, or None if the board doesn't exist."""
        if not self.is_connected():
            return None
        try:
            board = self.get_board(board_id)
            if board is None:
                return None
            post_ids = board['post_ids']
            if shortcode not in post_ids:
                post_ids.append(shortcode)
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE boards SET post_ids = ?, updated_at = ? WHERE id = ?",
                (json.dumps(post_ids), now, board_id)
            )
            self._conn.commit()
            return self.get_board(board_id)
        except Exception as e:
            print(f"[WARNING]  Error adding post to board: {e}")
            return None

    def remove_post_from_board(self, board_id, shortcode):
        """Remove one post from a board's direct post_ids. Returns the saved dict, or None if the board doesn't exist."""
        if not self.is_connected():
            return None
        try:
            board = self.get_board(board_id)
            if board is None:
                return None
            post_ids = [s for s in board['post_ids'] if s != shortcode]
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE boards SET post_ids = ?, updated_at = ? WHERE id = ?",
                (json.dumps(post_ids), now, board_id)
            )
            self._conn.commit()
            return self.get_board(board_id)
        except Exception as e:
            print(f"[WARNING]  Error removing post from board: {e}")
            return None

    def get_board_subcollection(self, sub_id):
        """Return a single subcollection by id, or None."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM board_subcollections WHERE id = ?", (sub_id,))
            return self._subcollection_row_to_dict(cur.fetchone())
        except Exception as e:
            print(f"[WARNING]  Error getting board subcollection: {e}")
            return None

    def create_board_subcollection(self, sub_id, board_id, name, icon):
        """Insert a new, empty subcollection under a board. Returns the saved dict, or None if the board doesn't exist."""
        if not self.is_connected():
            return None
        try:
            if self.get_board(board_id) is None:
                return None
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO board_subcollections (id, board_id, name, icon, post_ids, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, '[]', ?, ?)",
                (sub_id, board_id, name, icon, now, now)
            )
            self._conn.commit()
            return self.get_board_subcollection(sub_id)
        except Exception as e:
            print(f"[WARNING]  Error creating board subcollection: {e}")
            return None

    def rename_board_subcollection(self, sub_id, name=None, icon=None):
        """Update a subcollection's name/icon (whichever is provided). Returns the saved dict."""
        if not self.is_connected():
            return None
        try:
            existing = self.get_board_subcollection(sub_id)
            if existing is None:
                return None
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE board_subcollections SET name = ?, icon = ?, updated_at = ? WHERE id = ?",
                (
                    name if name is not None else existing['name'],
                    icon if icon is not None else existing['icon'],
                    now, sub_id
                )
            )
            self._conn.commit()
            return self.get_board_subcollection(sub_id)
        except Exception as e:
            print(f"[WARNING]  Error renaming board subcollection: {e}")
            return None

    def delete_board_subcollection(self, sub_id):
        """Delete a single subcollection (its parent board and sibling subcollections are untouched)."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute("DELETE FROM board_subcollections WHERE id = ?", (sub_id,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error deleting board subcollection: {e}")
            return False

    def add_post_to_subcollection(self, sub_id, shortcode):
        """Add one post to a subcollection's post_ids (no-op if already present)."""
        if not self.is_connected():
            return None
        try:
            sub = self.get_board_subcollection(sub_id)
            if sub is None:
                return None
            post_ids = sub['post_ids']
            if shortcode not in post_ids:
                post_ids.append(shortcode)
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE board_subcollections SET post_ids = ?, updated_at = ? WHERE id = ?",
                (json.dumps(post_ids), now, sub_id)
            )
            self._conn.commit()
            return self.get_board_subcollection(sub_id)
        except Exception as e:
            print(f"[WARNING]  Error adding post to board subcollection: {e}")
            return None

    def remove_post_from_subcollection(self, sub_id, shortcode):
        """Remove one post from a subcollection's post_ids."""
        if not self.is_connected():
            return None
        try:
            sub = self.get_board_subcollection(sub_id)
            if sub is None:
                return None
            post_ids = [s for s in sub['post_ids'] if s != shortcode]
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                "UPDATE board_subcollections SET post_ids = ?, updated_at = ? WHERE id = ?",
                (json.dumps(post_ids), now, sub_id)
            )
            self._conn.commit()
            return self.get_board_subcollection(sub_id)
        except Exception as e:
            print(f"[WARNING]  Error removing post from board subcollection: {e}")
            return None

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
    # Study guides
    # ------------------------------------------------------------------

    def _study_guide_row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        try:
            d['shortcodes'] = json.loads(d.get('shortcodes') or '[]')
        except Exception:
            d['shortcodes'] = []
        try:
            d['excluded_shortcodes'] = json.loads(d.get('excluded_shortcodes') or '[]')
        except Exception:
            d['excluded_shortcodes'] = []
        return d

    def create_study_guide(self, title, content, shortcodes, excluded_shortcodes=None, source_label=None,
                            collection_id=None, role='final', position=0, model=None):
        """Persist a generated study guide. Returns the saved dict, or None on failure."""
        if not self.is_connected():
            return None
        try:
            now = datetime.utcnow().isoformat()
            cur = self._conn.execute(
                "INSERT INTO study_guides "
                "(title, content, shortcodes, excluded_shortcodes, source_label, created_at, collection_id, role, position, model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (title, content, json.dumps(shortcodes), json.dumps(excluded_shortcodes or []), source_label, now,
                 collection_id, role, position, model)
            )
            self._conn.commit()
            return self.get_study_guide(cur.lastrowid)
        except Exception as e:
            print(f"[WARNING]  Error creating study guide: {e}")
            return None

    def get_study_guides(self):
        """Return all study guides (across every collection), newest first."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM study_guides ORDER BY created_at DESC")
            return [self._study_guide_row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[WARNING]  Error listing study guides: {e}")
            return []

    def get_study_guide(self, study_guide_id):
        """Return a single study guide by id, or None."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM study_guides WHERE id = ?", (study_guide_id,))
            return self._study_guide_row_to_dict(cur.fetchone())
        except Exception as e:
            print(f"[WARNING]  Error getting study guide: {e}")
            return None

    def delete_study_guide(self, study_guide_id):
        """Delete a single study guide (not its collection or siblings). Returns True if it existed."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute("DELETE FROM study_guides WHERE id = ?", (study_guide_id,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error deleting study guide: {e}")
            return False

    # ------------------------------------------------------------------
    # Study guide collections
    # ------------------------------------------------------------------

    def create_study_guide_collection(self, source_label=None, status='generating', expected_guide_count=None):
        """Create a new (initially empty) study guide collection — one per
        generation request. Returns the saved dict, or None on failure."""
        if not self.is_connected():
            return None
        try:
            now = datetime.utcnow().isoformat()
            cur = self._conn.execute(
                "INSERT INTO study_guide_collections (source_label, created_at, status, expected_guide_count) "
                "VALUES (?, ?, ?, ?)",
                (source_label, now, status, expected_guide_count)
            )
            self._conn.commit()
            return self.get_study_guide_collection(cur.lastrowid)
        except Exception as e:
            print(f"[WARNING]  Error creating study guide collection: {e}")
            return None

    def update_study_guide_collection_status(self, collection_id, status, error=None):
        """Mark a collection 'complete' or 'failed' once its background
        pipeline (api.py's POST /study-guide) finishes or raises. Returns
        True if the collection existed."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute(
                "UPDATE study_guide_collections SET status = ?, error = ? WHERE id = ?",
                (status, error, collection_id)
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error updating study guide collection status: {e}")
            return False

    def get_study_guide_collections(self):
        """Return every collection (newest first), each with its member
        guides already attached and ordered by position — 'final' first,
        then 'full', 'merge', and the individual 'chunk' guides."""
        if not self.is_connected():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM study_guide_collections ORDER BY created_at DESC")
            collections = [dict(r) for r in cur.fetchall()]
            for collection in collections:
                cur2 = self._conn.cursor()
                cur2.execute(
                    "SELECT * FROM study_guides WHERE collection_id = ? ORDER BY position ASC",
                    (collection["id"],)
                )
                collection["guides"] = [self._study_guide_row_to_dict(r) for r in cur2.fetchall()]
            return collections
        except Exception as e:
            print(f"[WARNING]  Error listing study guide collections: {e}")
            return []

    def get_study_guide_collection(self, collection_id):
        """Return a single collection with its member guides attached (see
        get_study_guide_collections()), or None."""
        if not self.is_connected():
            return None
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM study_guide_collections WHERE id = ?", (collection_id,))
            row = cur.fetchone()
            if row is None:
                return None
            collection = dict(row)
            cur2 = self._conn.cursor()
            cur2.execute(
                "SELECT * FROM study_guides WHERE collection_id = ? ORDER BY position ASC",
                (collection_id,)
            )
            collection["guides"] = [self._study_guide_row_to_dict(r) for r in cur2.fetchall()]
            return collection
        except Exception as e:
            print(f"[WARNING]  Error getting study guide collection: {e}")
            return None

    def delete_study_guide_collection(self, collection_id):
        """Delete a collection and every guide in it. Returns True if the collection existed."""
        if not self.is_connected():
            return False
        try:
            self._conn.execute("DELETE FROM study_guides WHERE collection_id = ?", (collection_id,))
            self._conn.execute("DELETE FROM reels_study_guide WHERE collection_id = ?", (collection_id,))
            cur = self._conn.execute("DELETE FROM study_guide_collections WHERE id = ?", (collection_id,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error deleting study guide collection: {e}")
            return False

    # ------------------------------------------------------------------
    # Study guide reel signals — feed superbrain-web's Home recommendation
    # engine as a weaker, separate-from-post_views "I cared enough to
    # synthesize this" signal. See the reels_study_guide CREATE TABLE
    # comment above for why this is keyed to a collection, not a guide.
    # ------------------------------------------------------------------

    def record_study_guide_reels(self, collection_id, shortcodes, client_env="prod") -> bool:
        """Insert one reels_study_guide row per shortcode a just-submitted
        generation request was built from (deduped). Called synchronously
        from POST /study-guide, before the background pipeline thread even
        starts — so it reflects what was requested, not what a particular
        final/full/merge/chunk guide happened to include. Sensitive-folder
        posts (core/sensitive.py) are skipped. Best-effort."""
        if not self.is_connected() or not shortcodes:
            return False
        try:
            now = datetime.utcnow().isoformat()
            sensitive = self.get_sensitive_shortcodes()
            rows = [
                (sc, collection_id, now, client_env)
                for sc in dict.fromkeys(shortcodes) if sc not in sensitive
            ]
            self._conn.executemany(
                "INSERT INTO reels_study_guide (shortcode, collection_id, created_at, client_env) VALUES (?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
            return True
        except Exception as e:
            print(f"[WARNING]  Error recording study guide reels: {e}")
            return False

    def mark_study_guide_collection_opened(self, collection_id) -> bool:
        """Stamp last_opened_at on a collection the moment one of its guides
        is actually opened (POST /study-guide-collections/{id}/opened,
        fired from superbrain-web's /study-guides/[id] page) — a fresh
        'opened' event nudges this collection's reels_study_guide-derived
        recommendation signal back up, the same way rewatching a post does
        for a real view. Returns True if the collection existed."""
        if not self.is_connected():
            return False
        try:
            cur = self._conn.execute(
                "UPDATE study_guide_collections SET last_opened_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), collection_id),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[WARNING]  Error marking study guide collection opened: {e}")
            return False

    def get_study_guide_reel_history(self, since=None, limit=20000):
        """Return [{shortcode, collection_id, created_at, opened_at}],
        newest link first. Only 'prod'-tagged rows, same dev/prod split as
        get_view_history(). opened_at is the owning collection's
        last_opened_at (NULL if none of its guides have been reopened since
        generation)."""
        if not self.is_connected():
            return []
        try:
            query = (
                "SELECT r.shortcode, r.collection_id, r.created_at, c.last_opened_at "
                "FROM reels_study_guide r JOIN study_guide_collections c ON c.id = r.collection_id "
                "WHERE r.client_env = 'prod' "
                f"AND r.shortcode NOT IN ({SENSITIVE_SHORTCODES_SQL})"
            )
            params = []
            if since:
                query += " AND r.created_at >= ?"
                params.append(since)
            query += " ORDER BY r.created_at DESC LIMIT ?"
            params.append(limit)
            cur = self._conn.execute(query, params)
            return [
                {"shortcode": s, "collection_id": cid, "created_at": c, "opened_at": o}
                for s, cid, c, o in cur.fetchall()
            ]
        except Exception as e:
            print(f"[WARNING]  Error fetching study guide reel history: {e}")
            return []


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
