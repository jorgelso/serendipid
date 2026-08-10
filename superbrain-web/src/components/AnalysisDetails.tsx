import type { ClientPost } from "@/types/domain";
import Markdown from "./Markdown";

export default function AnalysisDetails({ post }: { post: ClientPost }) {
  const markdownFields = [
    { label: "Visual analysis", value: post.visual_analysis },
    { label: "Audio transcription", value: post.audio_transcription },
    { label: "Text analysis", value: post.text_analysis },
  ].filter((f) => f.value);

  const metaFields = [
    { label: "Music", value: post.music },
    { label: "Posted", value: post.post_date },
    { label: "Likes", value: post.likes },
    { label: "Importance", value: post.importance ? `${post.importance}/5` : null },
  ].filter((f) => f.value !== null && f.value !== "");

  if (markdownFields.length === 0 && metaFields.length === 0) return null;

  return (
    <details className="mt-3 group">
      <summary className="cursor-pointer select-none text-[11px] font-bold uppercase tracking-wide text-coral-ink hover:opacity-70 transition-opacity">
        Full analysis
      </summary>
      <div className="mt-3 space-y-4 border-l-2 border-line pl-4">
        {markdownFields.map((field) => (
          <div key={field.label}>
            <p className="text-[11px] font-bold uppercase tracking-wide text-ink-muted mb-1">
              {field.label}
            </p>
            <Markdown text={field.value as string} />
          </div>
        ))}

        {metaFields.length > 0 && (
          <dl className="space-y-2">
            {metaFields.map((field) => (
              <div key={field.label}>
                <dt className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">
                  {field.label}
                </dt>
                <dd className="mt-0.5 text-sm leading-relaxed">{field.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </details>
  );
}
