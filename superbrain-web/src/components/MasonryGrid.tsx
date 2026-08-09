// CSS Grid, not CSS multi-column: multi-column fills column 1 top-to-bottom
// completely before starting column 2, which visually scrambles left-to-right
// reading order — a real problem for ranked results (search similarity,
// related posts) where order carries meaning. Grid lays out in row-major
// order (left-to-right, then wrap), matching the underlying data order.
export default function MasonryGrid({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="grid gap-5"
      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}
    >
      {children}
    </div>
  );
}
