// A small "pin" dot at the top of a corkboard card — deliberately not
// theme-aware (a physical pin doesn't change color with light/dark mode);
// `color` is a real CSS color value (e.g. "var(--color-coral)"), not a token name.
export default function PushPin({ color = "var(--color-coral)" }: { color?: string }) {
  return (
    <span
      aria-hidden
      className="absolute -top-1 left-1/2 z-20 h-3.5 w-3.5 -translate-x-1/2 rounded-full shadow-[0_2px_3px_rgba(0,0,0,0.45)]"
      style={{ background: `radial-gradient(circle at 32% 30%, rgba(255,255,255,0.9), ${color} 65%)` }}
    />
  );
}
