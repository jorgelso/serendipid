import { notFound } from "next/navigation";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getEmbeddings, getExport } from "@/lib/cache";
import { toDisplayPost } from "@/lib/posts";
import { findRelatedPosts } from "@/lib/clustering";
import type { ClientPost } from "@/types/domain";
import PostDetail from "@/components/PostDetail";
import PostCard from "@/components/PostCard";
import MasonryGrid from "@/components/MasonryGrid";

interface PageData {
  post: ClientPost;
  related: (ClientPost & { similarity: number })[];
}

async function loadPostPage(shortcode: string): Promise<PageData | null> {
  const config = getConfig();
  const { posts } = await getExport();
  const rawPost = posts.find((p) => p.shortcode === shortcode);
  if (!rawPost) return null;

  const relatedScored = findRelatedPosts(rawPost, posts, await getEmbeddings(), 8);
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
          <PostDetail initialPost={data.post} showFullDetails />

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
