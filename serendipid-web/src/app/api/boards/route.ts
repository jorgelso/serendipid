import { NextRequest, NextResponse } from "next/server";
import { createBoard, fetchBoards, SerendipidApiError } from "@/lib/apiClient";

export async function GET() {
  try {
    const boards = await fetchBoards();
    return NextResponse.json({ success: true, data: boards });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  let body: { name?: unknown; icon?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }
  if (typeof body.name !== "string" || !body.name.trim()) {
    return NextResponse.json({ error: "A board 'name' is required." }, { status: 400 });
  }

  try {
    const board = await createBoard(body.name.trim(), typeof body.icon === "string" ? body.icon : undefined);
    return NextResponse.json({ success: true, data: board });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
