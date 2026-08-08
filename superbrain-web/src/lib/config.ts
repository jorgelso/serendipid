// Server-only. Never import this from a "use client" component — the values
// here (especially the API key) must never reach the browser bundle. Reading
// process.env.SUPERBRAIN_API_URL/KEY directly (rather than NEXT_PUBLIC_-
// prefixed vars) is what keeps them server-only in Next.js.

export interface SuperBrainConfig {
  apiUrl: string;
  apiKey: string;
  requestTimeoutMs: number;
}

export function getConfig(): SuperBrainConfig {
  const apiUrl = (process.env.SUPERBRAIN_API_URL ?? "").trim().replace(/\/+$/, "");
  const apiKey = (process.env.SUPERBRAIN_API_KEY ?? "").trim();

  if (!apiUrl || !apiKey) {
    throw new Error(
      "SUPERBRAIN_API_URL and SUPERBRAIN_API_KEY must both be set in " +
        "superbrain-web/.env.local (copy .env.example to get started)."
    );
  }

  return { apiUrl, apiKey, requestTimeoutMs: 15_000 };
}
