import type { ClientPost } from "@/types/domain";

interface Field {
  label: string;
  value: string | number | null;
}

export default function AnalysisDetails({ post }: { post: ClientPost }) {
  const fields: Field[] = [
    { label: "Visual analysis", value: post.visual_analysis },
    { label: "Audio transcription", value: post.audio_transcription },
    { label: "Text analysis", value: post.text_analysis },
    { label: "Music", value: post.music },
    { label: "Posted", value: post.post_date },
    { label: "Likes", value: post.likes },
  ].filter((f) => f.value !== null && f.value !== "");

  if (fields.length === 0) return null;

  return (
    <details className="mt-3 group">
      <summary className="cursor-pointer select-none font-label text-[11px] uppercase tracking-wide text-moss hover:text-ink transition-colors">
        Full analysis
      </summary>
      <dl className="mt-3 space-y-3 border-l-2 border-line pl-4">
        {fields.map((field) => (
          <div key={field.label}>
            <dt className="font-label text-[11px] uppercase tracking-wide text-ink-muted">
              {field.label}
            </dt>
            <dd className="mt-1 text-sm leading-relaxed">{field.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
