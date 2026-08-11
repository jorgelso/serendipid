"use client";

import { useState } from "react";
import type { ClientPost } from "@/types/domain";
import { CategoryBadges, LanguageBadges } from "./Chips";
import MediaViewer from "./MediaViewer";
import AnalysisDetails from "./AnalysisDetails";
import ReviewActions from "./ReviewActions";
import EditPostForm from "./EditPostForm";
import DeletePostButton from "./DeletePostButton";

interface PostDetailProps {
  initialPost: ClientPost;
  // The modal stays lean (media + basic info + edit); the dedicated page
  // additionally shows the full AI analysis and review actions — the modal
  // links to the dedicated page for that depth rather than duplicating it.
  showFullDetails?: boolean;
}

export default function PostDetail({ initialPost, showFullDetails = false }: PostDetailProps) {
  const [post, setPost] = useState(initialPost);
  const [editing, setEditing] = useState(false);

  return (
    <div>
      <div className="flex items-start justify-between gap-3 mb-1">
        <h2 className="font-display font-semibold text-lg leading-snug">
          {post.title || "Untitled reel"}
        </h2>
        {!editing && (
          <div className="shrink-0 flex items-center gap-3">
            <button
              onClick={() => setEditing(true)}
              className="text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
            >
              ✏️ Edit
            </button>
            <DeletePostButton shortcode={post.shortcode} title={post.title} variant="button" />
          </div>
        )}
      </div>

      <div className="mt-3">
        <MediaViewer post={post} />
      </div>

      {editing ? (
        <div className="mt-4">
          <EditPostForm
            post={post}
            onCancel={() => setEditing(false)}
            onSaved={(edits) => {
              setPost((prev) => ({ ...prev, ...edits }));
              setEditing(false);
            }}
          />
        </div>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <a
              href={post.url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-ink-muted hover:text-coral-ink transition-colors"
            >
              @{post.username}
            </a>
            <CategoryBadges category={post.category} />
            <LanguageBadges language={post.language} />
          </div>

          {post.summary && (
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">{post.summary}</p>
          )}
        </>
      )}

      {showFullDetails && (
        <>
          <AnalysisDetails post={post} />
          {post.needs_review && (
            <ReviewActions
              shortcode={post.shortcode}
              url={post.url}
              analysisVersion={post.analysis_version}
            />
          )}
        </>
      )}
    </div>
  );
}
