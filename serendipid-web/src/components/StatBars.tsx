import { colorFor } from "./Chips";

export default function StatBars({ entries }: { entries: [string, number][] }) {
  if (entries.length === 0) {
    return <p className="text-sm text-ink-muted">Nothing to show yet.</p>;
  }
  const max = Math.max(...entries.map(([, count]) => count));

  return (
    <div className="space-y-2.5">
      {entries.map(([label, count]) => {
        const { bg, fg } = colorFor(label);
        const widthPct = Math.max(6, Math.round((count / max) * 100));
        return (
          <div key={label} className="flex items-center gap-3">
            <span className="w-32 shrink-0 truncate text-sm font-bold" title={label}>
              {label}
            </span>
            <div className="flex-1 h-6 rounded-full bg-surface-2 overflow-hidden">
              <div
                className="h-full rounded-full flex items-center justify-end px-2.5"
                style={{ width: `${widthPct}%`, backgroundColor: bg }}
              >
                <span className="text-[11px] font-bold" style={{ color: fg }}>
                  {count}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
