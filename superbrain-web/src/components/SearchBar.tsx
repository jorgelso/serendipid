"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function SearchBar({ defaultValue = "" }: { defaultValue?: string }) {
  const router = useRouter();
  const [value, setValue] = useState(defaultValue);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="What are you interested in? Try “guitar” or “cooking”…"
        className="flex-1 rounded-full border border-line bg-surface px-5 py-3 text-sm placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-coral"
      />
      <button
        type="submit"
        className="rounded-full bg-coral px-6 py-3 text-sm font-display font-semibold text-white hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-coral focus:ring-offset-2 focus:ring-offset-bg"
      >
        Look up
      </button>
    </form>
  );
}
