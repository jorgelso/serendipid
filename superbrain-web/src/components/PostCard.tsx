import type { ClientPost } from "@/types/domain";
import { CategoryBadge, CategoryBadges, LanguageBadges, TagChips } from "./Chips";
import AnalysisDetails from "./AnalysisDetails";
import ReviewActions from "./ReviewActions";

interface PostCardProps {
  post: ClientPost & { similarity?: number };
}

export default function PostCard({ post }: PostCardProps) {
  return (
    <article className="break-inside-avoid mb-5 rounded-3xl bg-surface border border-line overflow-hidden shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] transition-transform duration-200 hover:-translate-y-1 hover:rotate-[-0.3deg]">
      {post.thumbnail && (
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={post.thumbnail} alt="" className="w-full block" loading="lazy" />
          <div className="absolute top-3 left-3">
            <CategoryBadge category={post.category} />
          </div>
          {typeof post.similarity === "number" && (
            <div className="absolute top-3 right-3 bg-ink/70 text-bg text-[11px] font-bold px-2.5 py-1 rounded-full backdrop-blur-sm">
              {(post.similarity * 100).toFixed(0)}% match
            </div>
          )}
        </div>
      )}

      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-display font-semibold text-[15px] leading-snug">
            {post.title || "Untitled reel"}
          </h3>
          {post.needs_review && (
            <span
              title="Categorized under the old system"
              className="shrink-0 mt-0.5 text-[11px] font-bold px-2 py-0.5 rounded-full bg-yellow-soft text-yellow-ink"
            >
              needs review
            </span>
          )}
        </div>

        <a
          href={post.url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-block text-xs text-ink-muted hover:text-coral-ink transition-colors"
        >
          @{post.username}
        </a>

        {(post.category.length > 1 || post.language.length > 0) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {post.category.length > 1 && <CategoryBadges category={post.category} />}
            <LanguageBadges language={post.language} />
          </div>
        )}

        {post.summary && (
          <p className="mt-2 text-[13px] leading-relaxed text-ink-muted line-clamp-3">
            {post.summary}
          </p>
        )}

        <div className="mt-3">
          <TagChips tags={post.tags} limit={6} />
        </div>

        <AnalysisDetails post={post} />

        {post.needs_review && <ReviewActions shortcode={post.shortcode} url={post.url} />}
      </div>
    </article>
  );
}
