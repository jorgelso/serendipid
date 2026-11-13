import { NextRequest, NextResponse } from "next/server";
import { proxyBackendFile } from "@/lib/apiClient";

// Generated thumbnails from the backend's /static route. Same proxy as
// /api/media: session checked by src/proxy.ts, API key added server-side.
export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  try {
    return await proxyBackendFile("static", path, request.headers);
  } catch {
    return NextResponse.json({ error: "Backend unreachable." }, { status: 502 });
  }
}
