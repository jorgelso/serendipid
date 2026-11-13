import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, isAuthConfigured, verifySessionToken } from "@/lib/session";

// Every page and API route requires a valid session cookie except the login
// page and the login endpoint. Pages redirect to /login; API routes get a
// 401 so client-side fetches fail clearly instead of receiving HTML.
const PUBLIC_PATHS = new Set(["/login", "/api/auth/login"]);

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isApi = pathname.startsWith("/api/");

  if (!isAuthConfigured()) {
    const message = "WEB_PASSWORD is not set. Add it to .env.local (see .env.example) and restart.";
    return isApi
      ? NextResponse.json({ error: message }, { status: 503 })
      : new NextResponse(message, { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }

  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();

  if (verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value)) {
    return NextResponse.next();
  }

  if (isApi) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const loginUrl = new URL("/login", request.url);
  if (pathname !== "/") loginUrl.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Skip Next's own static assets and the app icon; everything else
  // (pages, API routes, the media proxy) goes through the check.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
