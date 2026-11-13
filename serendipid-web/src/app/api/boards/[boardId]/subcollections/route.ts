import { NextRequest, NextResponse } from "next/server";
import { createBoardSubcollection, SerendipidApiError } from "@/lib/apiClient";

export async function POST(request: NextRequest, { params }: { params: Promise<{ boardId: string }> }) {
  const { boardId } = await params;
  let body: { name?: unknown; icon?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }
  if (typeof body.name !== "string" || !body.name.trim()) {
    return NextResponse.json({ error: "A subcollection 'name' is required." }, { status: 400 });
  }

  try {
    const sub = await createBoardSubcollection(
      boardId,
      body.name.trim(),
      typeof body.icon === "string" ? body.icon : undefined
    );
    return NextResponse.json({ success: true, data: sub });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
