import { NextRequest, NextResponse } from "next/server";
import { proxyBackendFile } from "@/lib/apiClient";

// Post media (video/audio/images) from the backend's /media route. The
// browser only ever sees this app's origin; src/proxy.ts has already checked
// the session cookie before this runs.
export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  try {
    return await proxyBackendFile("media", path, request.headers);
  } catch {
    return NextResponse.json({ error: "Backend unreachable." }, { status: 502 });
  }
}
