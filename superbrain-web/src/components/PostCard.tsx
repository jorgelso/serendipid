import type { ClientPost } from "@/types/domain";
import { CategoryBadge, TagChips } from "./Chips";
import AnalysisDetails from "./AnalysisDetails";

interface PostCardProps {
  post: ClientPost & { similarity?: number };
}

export default function PostCard({ post }: PostCardProps) {
  return (
    <article className="rounded-md border border-line bg-paper-raised p-4 flex gap-4">
      {post.thumbnail && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={post.thumbnail}
          alt=""
          className="h-24 w-24 shrink-0 rounded-sm object-cover border border-line"
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-lg leading-snug">
            {post.title || "Untitled reel"}
          </h3>
          {typeof post.similarity === "number" && (
            <span className="shrink-0 font-label text-[11px] px-2 py-0.5 rounded-sm bg-moss-soft text-moss">
              {(post.similarity * 100).toFixed(0)}% match
            </span>
          )}
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
          <a
            href={post.url}
            target="_blank"
            rel="noreferrer"
            className="hover:text-moss underline decoration-line underline-offset-2"
          >
            @{post.username}
          </a>
          <CategoryBadge category={post.category} />
        </div>

        {post.summary && (
          <p className="mt-2 text-sm leading-relaxed text-ink line-clamp-3">{post.summary}</p>
        )}

        <div className="mt-2">
          <TagChips tags={post.tags} limit={8} />
        </div>

        <AnalysisDetails post={post} />
      </div>
    </article>
  );
}
