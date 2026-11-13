import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, checkPassword, createSessionToken } from "@/lib/session";

// Small fixed delay on a wrong password to slow down guessing.
const FAILURE_DELAY_MS = 1000;

function isHttps(request: NextRequest): boolean {
  const forwarded = request.headers.get("x-forwarded-proto");
  return (forwarded ?? request.nextUrl.protocol.replace(":", "")) === "https";
}

export async function POST(request: NextRequest) {
  let password = "";
  try {
    const body = await request.json();
    password = typeof body?.password === "string" ? body.password : "";
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  if (!checkPassword(password)) {
    await new Promise((r) => setTimeout(r, FAILURE_DELAY_MS));
    return NextResponse.json({ error: "Wrong password." }, { status: 401 });
  }

  const res = NextResponse.json({ success: true });
  res.cookies.set(SESSION_COOKIE, createSessionToken(), {
    httpOnly: true,
    sameSite: "lax",
    // Secure only over HTTPS so plain-HTTP use on a home network still works.
    secure: isHttps(request),
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
  return res;
}
