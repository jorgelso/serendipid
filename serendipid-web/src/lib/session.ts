// Server-only. Password login for the web app: one shared password
// (WEB_PASSWORD), exchanged for a signed session token (a compact HS256 JWT)
// stored in an httpOnly cookie that expires after SESSION_MAX_AGE_SECONDS.
//
// The signing key is derived from WEB_PASSWORD plus the backend API key, so
// changing either one invalidates every existing session. Uses only
// node:crypto (src/proxy.ts runs on the Node.js runtime in this Next.js
// version), so no JWT dependency is needed.

import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "serendipid_session";
export const SESSION_MAX_AGE_SECONDS = 21 * 24 * 60 * 60; // 3 weeks

function webPassword(): string {
  return (process.env.WEB_PASSWORD ?? "").trim();
}

export function isAuthConfigured(): boolean {
  return webPassword().length > 0;
}

function signingKey(): Buffer {
  const apiKey = (process.env.SERENDIPID_API_KEY ?? "").trim();
  return createHash("sha256").update(`serendipid-session\0${webPassword()}\0${apiKey}`).digest();
}

function b64url(input: Buffer | string): string {
  return Buffer.from(input).toString("base64url");
}

function sign(data: string): string {
  return createHmac("sha256", signingKey()).update(data).digest("base64url");
}

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

/** Constant-time password check. Hashing both sides first keeps the
 * comparison length-independent. */
export function checkPassword(candidate: string): boolean {
  if (!isAuthConfigured()) return false;
  const a = createHash("sha256").update(candidate).digest();
  const b = createHash("sha256").update(webPassword()).digest();
  return timingSafeEqual(a, b);
}

export function createSessionToken(now = Date.now()): string {
  const iat = Math.floor(now / 1000);
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64url(JSON.stringify({ sub: "owner", iat, exp: iat + SESSION_MAX_AGE_SECONDS }));
  return `${header}.${payload}.${sign(`${header}.${payload}`)}`;
}

export function verifySessionToken(token: string | undefined, now = Date.now()): boolean {
  if (!token || !isAuthConfigured()) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [header, payload, signature] = parts;
  if (!safeEqual(signature, sign(`${header}.${payload}`))) return false;
  try {
    const { exp } = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    return typeof exp === "number" && exp > Math.floor(now / 1000);
  } catch {
    return false;
  }
}
