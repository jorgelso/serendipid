import { NextRequest, NextResponse } from "next/server";
import { deleteBoard, fetchBoard, renameBoard, SuperBrainApiError } from "@/lib/apiClient";

export async function GET(request: NextRequest, { params }: { params: Promise<{ boardId: string }> }) {
  const { boardId } = await params;
  try {
    const board = await fetchBoard(boardId);
    return NextResponse.json({ success: true, data: board });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ boardId: string }> }) {
  const { boardId } = await params;
  let body: { name?: unknown; icon?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  try {
    const board = await renameBoard(boardId, {
      ...(typeof body.name === "string" ? { name: body.name } : {}),
      ...(typeof body.icon === "string" ? { icon: body.icon } : {}),
    });
    return NextResponse.json({ success: true, data: board });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ boardId: string }> }) {
  const { boardId } = await params;
  try {
    await deleteBoard(boardId);
    return NextResponse.json({ success: true });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
