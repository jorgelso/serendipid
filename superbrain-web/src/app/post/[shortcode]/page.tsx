import { notFound } from "next/navigation";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getExport } from "@/lib/cache";
import { toDisplayPost } from "@/lib/posts";
import { findRelatedPosts } from "@/lib/clustering";
import type { ClientPost } from "@/types/domain";
import MediaViewer from "@/components/MediaViewer";
import AnalysisDetails from "@/components/AnalysisDetails";
import ReviewActions from "@/components/ReviewActions";
import PostCard from "@/components/PostCard";
import MasonryGrid from "@/components/MasonryGrid";
import { CategoryBadges, LanguageBadges } from "@/components/Chips";

interface PageData {
  post: ClientPost;
  related: (ClientPost & { similarity: number })[];
}

async function loadPostPage(shortcode: string): Promise<PageData | null> {
  const config = getConfig();
  const { posts } = await getExport();
  const rawPost = posts.find((p) => p.shortcode === shortcode);
  if (!rawPost) return null;

  const relatedScored = findRelatedPosts(rawPost, posts, 8);
  const byShortcode = new Map(posts.map((p) => [p.shortcode, p]));
  const related = relatedScored
    .map((r) => {
      const raw = byShortcode.get(r.shortcode);
      return raw ? { ...toDisplayPost(raw, config.apiUrl), similarity: r.similarity } : null;
    })
    .filter((p): p is ClientPost & { similarity: number } => Boolean(p));

  return { post: toDisplayPost(rawPost, config.apiUrl), related };
}

export default async function PostPage(props: PageProps<"/post/[shortcode]">) {
  const { shortcode } = await props.params;

  let data: PageData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadPostPage(shortcode);
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading this post.";
  }

  if (!errorMessage && !data) {
    notFound();
  }

  return (
    <div className="mx-auto max-w-4xl px-5 py-8">
      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {data && (
        <>
          <h1 className="font-display font-semibold text-2xl mb-4">
            {data.post.title || "Untitled reel"}
          </h1>

          <MediaViewer post={data.post} />

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <a
              href={data.post.url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-ink-muted hover:text-coral-ink transition-colors"
            >
              @{data.post.username}
            </a>
            <CategoryBadges category={data.post.category} />
            <LanguageBadges language={data.post.language} />
          </div>

          {data.post.summary && (
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">{data.post.summary}</p>
          )}

          <AnalysisDetails post={data.post} />

          {data.post.needs_review && (
            <ReviewActions shortcode={data.post.shortcode} url={data.post.url} />
          )}

          {data.related.length > 0 && (
            <section className="mt-10">
              <h2 className="font-display font-semibold text-lg mb-4">Related</h2>
              <MasonryGrid>
                {data.related.map((post) => (
                  <PostCard key={post.shortcode} post={post} />
                ))}
              </MasonryGrid>
            </section>
          )}
        </>
      )}
    </div>
  );
}
