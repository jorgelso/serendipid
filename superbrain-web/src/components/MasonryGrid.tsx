export default function MasonryGrid({ children }: { children: React.ReactNode }) {
  return <div className="[column-width:260px] [column-gap:1.25rem]">{children}</div>;
}
