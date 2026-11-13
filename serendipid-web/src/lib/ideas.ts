// "Ideas" — recurring-topic surfacing across the library, powering /ideas.
//
// THIS IS v1, AND IT IS DELIBERATELY THE CHEAP VERSION. It aggregates
// already-stored Post.tags by exact/normalized string match — it does NOT
// cluster by meaning. Two tags that mean the same thing but are phrased
// differently ("cold email" vs. "cold outreach") show up as two separate
// ideas here, not one. This was a conscious tradeoff, not an oversight: the
// real version needs new spend (AI-extracted atomic claims per post,
// embedded and clustered the way src/lib/clustering.ts already clusters
// whole-post embeddings today — a v2 already agreed on with the user) and
// the user explicitly did not want to pay for new embeddings right now. Tag
// frequency over data that's already stored costs nothing extra to compute.
//
// When the v2 lands, this file's computeIdeas() should be replaced (not
// just tweaked) by a claim-cluster read, and backend/core/study_guide.py's
// module docstring has the matching note on that side.
//
// The MIN_IDEA_IMPORTANCE floor below is intentionally the same rule as
// backend/core/study_guide.py's MIN_STUDY_GUIDE_IMPORTANCE (posts scoring
// below 3 on the 1-5 importance rubric are excluded) — duplicated, not
// shared, since this runs in the Next.js app and that runs in the Python
// backend. Keep both in sync by hand if the threshold ever changes.

import type { Idea, Post } from "@/types/domain";
import { GENERIC_TAGS, normalizeTag } from "./clustering";

const MIN_IDEA_IMPORTANCE = 3;

interface ComputeIdeasOptions {
  // Restrict counting to only these shortcodes (e.g. one theme's member
  // posts) instead of the whole library.
  scopeShortcodes?: string[];
}

export function computeIdeas(posts: Post[], options: ComputeIdeasOptions = {}): Idea[] {
  const scopeSet = options.scopeShortcodes ? new Set(options.scopeShortcodes) : null;

  const byTag = new Map<string, { original: string; shortcodes: string[] }>();

  for (const post of posts) {
    if (scopeSet && !scopeSet.has(post.shortcode)) continue;
    // Same low-value exclusion as study-guide generation — see module
    // comment above. Unscored posts (importance === null) are kept.
    if (post.importance !== null && post.importance < MIN_IDEA_IMPORTANCE) continue;

    for (const rawTag of post.tags ?? []) {
      const trimmed = rawTag.trim();
      const key = normalizeTag(trimmed);
      if (!trimmed || GENERIC_TAGS.has(key)) continue;

      const entry = byTag.get(key);
      if (entry) {
        entry.shortcodes.push(post.shortcode);
      } else {
        byTag.set(key, { original: trimmed, shortcodes: [post.shortcode] });
      }
    }
  }

  return Array.from(byTag.entries())
    .map(([tag, { original, shortcodes }]) => ({
      tag,
      label: original,
      count: shortcodes.length,
      shortcodes,
    }))
    .filter((idea) => idea.count >= 2) // a "recurring" idea implies more than one source
    .sort((a, b) => b.count - a.count);
}
