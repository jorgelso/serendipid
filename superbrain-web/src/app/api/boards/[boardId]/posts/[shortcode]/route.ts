import { NextRequest, NextResponse } from "next/server";
import { addPostToBoard, removePostFromBoard, SuperBrainApiError } from "@/lib/apiClient";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ boardId: string; shortcode: string }> }
) {
  const { boardId, shortcode } = await params;
  try {
    const board = await addPostToBoard(boardId, shortcode);
    return NextResponse.json({ success: true, data: board });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ boardId: string; shortcode: string }> }
) {
  const { boardId, shortcode } = await params;
  try {
    const board = await removePostFromBoard(boardId, shortcode);
    return NextResponse.json({ success: true, data: board });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
