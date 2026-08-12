"use client";

import { useState } from "react";
import type { ClientPost } from "@/types/domain";
import { isMissingVideo } from "@/lib/media";
import { useChangelog } from "@/lib/useChangelog";
import {
  CategoryBadge,
  CategoryBadges,
  EloquentBadge,
  ImportanceBadge,
  LanguageBadges,
  MissingVideoBadge,
  TagChips,
  VersionBehindBadge,
} from "./Chips";
import VersionChangelogBadge from "./VersionChangelogBadge";
import AnalysisDetails from "./AnalysisDetails";
import ReviewActions from "./ReviewActions";
import PostModal from "./PostModal";
import DeletePostButton from "./DeletePostButton";

interface PostCardProps {
  post: ClientPost & { similarity?: number };
  // Forwarded to ReviewActions — see its doc comment. Every caller outside
  // the /versions page omits this and keeps the existing full-reanalysis
  // behavior.
  rescanMode?: "full" | "cheap";
}

export default function PostCard({ post, rescanMode }: PostCardProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const missingVideo = isMissingVideo(post);
  const changelog = useChangelog();

  return (
    <article className="self-start rounded-3xl bg-surface border border-line overflow-hidden shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] transition-transform duration-200 hover:-translate-y-1 hover:rotate-[-0.3deg]">
      {post.thumbnail && (
        <div className="relative w-full group/thumb">
          {/* Only wraps the image itself — the version badges below include
             a real <button> (the "?"), and a <button> can't validly nest
             inside another <button> (React/Next would warn on hydration and
             browsers reparent it when parsing SSR'd HTML). The overlay badges
             are positioned as siblings instead, with pointer-events-none
             where there's nothing interactive so a click still reaches this
             button and opens the post. */}
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="relative w-full block cursor-pointer"
            aria-label="Open post"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={post.thumbnail} alt="" className="w-full block" loading="lazy" />
            <div className="absolute inset-0 bg-ink/0 group-hover/thumb:bg-ink/20 transition-colors flex items-center justify-center">
              <span className="opacity-0 group-hover/thumb:opacity-100 transition-opacity text-bg text-3xl drop-shadow">
                ▶
              </span>
            </div>
          </button>

          <div className="absolute top-3 left-3 pointer-events-none">
            <CategoryBadge category={post.category} />
          </div>
          {(post.importance != null || post.is_eloquent === 1) && (
            <div className="absolute bottom-3 left-3 flex flex-col items-start gap-1.5 pointer-events-none">
              {post.importance != null && <ImportanceBadge importance={post.importance} />}
              {post.is_eloquent === 1 && <EloquentBadge isTutorial={post.is_tutorial} />}
            </div>
          )}
          <div className="absolute top-3 right-3 flex flex-col items-end gap-1.5 pointer-events-none">
            {typeof post.similarity === "number" && (
              <span className="bg-ink/70 text-bg text-[11px] font-bold px-2.5 py-1 rounded-full backdrop-blur-sm">
                {(post.similarity * 100).toFixed(0)}% match
              </span>
            )}
            {missingVideo && <MissingVideoBadge />}
          </div>
          {post.needs_review && (
            <div className="absolute bottom-3 right-3 flex items-center gap-1 pointer-events-none">
              <VersionBehindBadge analysisVersion={post.analysis_version} changelog={changelog} />
              <div className="pointer-events-auto">
                <VersionChangelogBadge analysisVersion={post.analysis_version} />
              </div>
            </div>
          )}
        </div>
      )}

      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-display font-semibold text-[15px] leading-snug">
            {post.title || "Untitled reel"}
          </h3>
          <DeletePostButton shortcode={post.shortcode} title={post.title} />
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

        {post.needs_review && (
          <ReviewActions
            shortcode={post.shortcode}
            url={post.url}
            analysisVersion={post.analysis_version}
            rescanMode={rescanMode}
          />
        )}
      </div>

      {modalOpen && <PostModal post={post} onClose={() => setModalOpen(false)} />}
    </article>
  );
}
