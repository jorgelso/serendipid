"use client";

import { useEffect, useState } from "react";
import type { ClientPost } from "@/types/domain";

interface TagEditorProps {
  label: string;
  values: string[];
  options: string[];
  onChange: (next: string[]) => void;
}

function TagEditor({ label, values, options, onChange }: TagEditorProps) {
  const [newValue, setNewValue] = useState("");
  const available = options.filter((o) => !values.includes(o));

  function addTag(tag: string) {
    const trimmed = tag.trim();
    if (!trimmed || values.includes(trimmed)) return;
    onChange([...values, trimmed]);
  }

  return (
    <div>
      <label className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">{label}</label>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {values.map((v) => (
          <span
            key={v}
            className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-surface-2 text-ink flex items-center gap-1.5"
          >
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((x) => x !== v))}
              aria-label={`Remove ${v}`}
              className="text-ink-muted hover:text-danger leading-none"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <select
          value=""
          onChange={(e) => {
            if (e.target.value) addTag(e.target.value);
          }}
          disabled={available.length === 0}
          className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-coral disabled:opacity-50"
        >
          <option value="">
            {available.length > 0 ? "Choose existing…" : "No more existing options"}
          </option>
          {available.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <div className="flex gap-2">
          <input
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addTag(newValue);
                setNewValue("");
              }
            }}
            placeholder="Or type a new one…"
            className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-coral"
          />
          <button
            type="button"
            onClick={() => {
              addTag(newValue);
              setNewValue("");
            }}
            className="rounded-full border border-line px-3 py-1.5 text-xs font-bold hover:bg-surface-2"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

interface EditPostFormProps {
  post: ClientPost;
  onSaved: (edits: { title: string; summary: string; category: string[]; language: string[] }) => void;
  onCancel: () => void;
}

export default function EditPostForm({ post, onSaved, onCancel }: EditPostFormProps) {
  const [title, setTitle] = useState(post.title ?? "");
  const [summary, setSummary] = useState(post.summary ?? "");
  const [category, setCategory] = useState(post.category);
  const [language, setLanguage] = useState(post.language);
  const [taxonomy, setTaxonomy] = useState<{ categories: string[]; languages: string[] }>({
    categories: [],
    languages: [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/taxonomy")
      .then((res) => res.json())
      .then((data) => setTaxonomy({ categories: data.categories ?? [], languages: data.languages ?? [] }))
      .catch(() => {
        // Autocomplete suggestions are a nice-to-have — editing still works
        // with an empty list, just without suggestions.
      });
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/update-post", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shortcode: post.shortcode, title, summary, category, language }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't save changes.");
      onSaved({ title, summary, category, language });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save changes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface-2 p-4">
      <div>
        <label className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Title</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-coral"
        />
      </div>

      <div>
        <label className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">Summary</label>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={4}
          className="mt-1.5 w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-coral"
        />
      </div>

      <TagEditor label="Category" values={category} options={taxonomy.categories} onChange={setCategory} />
      <TagEditor label="Language" values={language} options={taxonomy.languages} onChange={setLanguage} />

      {error && <p className="text-xs text-danger">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-full bg-ink text-bg font-display font-semibold text-sm px-5 py-2.5 hover:opacity-85 transition-opacity disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button
          onClick={onCancel}
          disabled={saving}
          className="rounded-full border border-line text-sm font-bold px-5 py-2.5 hover:bg-surface disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
