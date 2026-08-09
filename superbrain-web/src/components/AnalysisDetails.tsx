import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ClientPost } from "@/types/domain";

// The AI-generated analysis fields are genuinely markdown (headers, bold,
// lists, blockquotes) — these overrides keep that formatting on-theme
// instead of pulling in a generic prose plugin with its own gray palette.
const markdownComponents: Components = {
  h1: ({ children }) => (
    <p className="font-display font-semibold text-sm mt-3 first:mt-0">{children}</p>
  ),
  h2: ({ children }) => (
    <p className="font-display font-semibold text-sm mt-3 first:mt-0">{children}</p>
  ),
  h3: ({ children }) => (
    <p className="font-display font-semibold text-sm mt-3 first:mt-0">{children}</p>
  ),
  h4: ({ children }) => <p className="font-bold text-sm mt-2 first:mt-0">{children}</p>,
  h5: ({ children }) => <p className="font-bold text-sm mt-2 first:mt-0">{children}</p>,
  h6: ({ children }) => <p className="font-bold text-sm mt-2 first:mt-0">{children}</p>,
  p: ({ children }) => <p className="text-sm leading-relaxed mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-bold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 mb-2 text-sm">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 mb-2 text-sm">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-coral pl-3 italic text-ink-muted my-2">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-line" />,
  code: ({ children }) => (
    <code className="bg-surface-2 rounded px-1 py-0.5 text-[12px]">{children}</code>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="underline text-coral-ink">
      {children}
    </a>
  ),
};

function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {text}
    </ReactMarkdown>
  );
}

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
