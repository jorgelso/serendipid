import Link from "next/link";
import { fetchEloquenceOverrides, SuperBrainApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { toDisplayPost } from "@/lib/posts";
import type { ClientPost, EloquenceOverride } from "@/types/domain";

interface OverridesData {
  overrides: EloquenceOverride[];
  postsByShortcode: Map<string, ClientPost>;
}

async function loadOverridesData(): Promise<OverridesData> {
  const [{ overrides }, { posts }] = await Promise.all([fetchEloquenceOverrides(), getExport()]);
  return {
    overrides,
    postsByShortcode: new Map(posts.map((p) => [p.shortcode, toDisplayPost(p)])),
  };
}

export default async function EloquenceOverridesPage() {
  let data: OverridesData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadOverridesData();
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading the override log.";
  }

  return (
    <div className="mx-auto max-w-3xl px-5 py-8">
      <div className="mb-6">
        <Link href="/eloquent" className="text-sm text-ink-muted hover:text-coral-ink transition-colors">
          ← Back to Eloquent
        </Link>
        <h1 className="mt-2 font-display font-semibold text-3xl">Eloquence overrides</h1>
        <p className="mt-1 text-ink-muted text-sm">
          Posts the AI judge scored eloquent that you manually corrected — kept with its original
          rationale so a recurring pattern here points at what to fix in the eloquence prompt.
        </p>
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {data && data.overrides.length === 0 && (
        <p className="text-sm text-ink-muted py-10 text-center">
          No overrides logged yet — mark a post as not eloquent from /eloquent to start one.
        </p>
      )}

      {data && data.overrides.length > 0 && (
        <ul className="space-y-3">
          {data.overrides.map((entry) => {
            const post = data.postsByShortcode.get(entry.shortcode);
            return (
              <li key={entry.id} className="rounded-2xl border border-line bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    {post ? (
                      <a
                        href={post.url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-display font-semibold text-[15px] hover:text-coral-ink transition-colors"
                      >
                        {post.title || entry.shortcode}
                      </a>
                    ) : (
                      <span className="font-display font-semibold text-[15px] text-ink-muted">
                        {entry.shortcode} (post no longer in library)
                      </span>
                    )}
                    {post?.username && <p className="text-xs text-ink-muted mt-0.5">@{post.username}</p>}
                  </div>
                  <span className="shrink-0 text-[11px] text-ink-muted whitespace-nowrap">
                    {new Date(entry.overridden_at).toLocaleString()}
                  </span>
                </div>

                {entry.ai_rationale && (
                  <p className="mt-2 text-[13px] leading-relaxed text-ink-muted italic">
                    &ldquo;{entry.ai_rationale}&rdquo;
                  </p>
                )}

                {entry.ai_was_tutorial != null && (
                  <p className="mt-1 text-[11px] text-ink-muted">
                    AI marked as {entry.ai_was_tutorial ? "tutorial-style" : "speech/commentary-style"} delivery.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
