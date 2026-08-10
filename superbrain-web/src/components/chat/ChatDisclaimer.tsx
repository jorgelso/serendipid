export default function ChatDisclaimer() {
  return (
    <div className="rounded-2xl border border-line bg-surface-2 px-4 py-3 text-xs leading-relaxed text-ink-muted">
      <span className="font-bold text-ink">Heads up: </span>
      answers are grounded in each saved post&rsquo;s title, summary, and tags — the same data
      used by search — not a search over full video transcripts. If something was only
      mentioned deep in a video&rsquo;s audio or on-screen text and never made it into the
      summary, the chatbot may miss it or answer as if it doesn&rsquo;t have that post at all.
      Passage-level transcript search isn&rsquo;t implemented yet.
    </div>
  );
}
