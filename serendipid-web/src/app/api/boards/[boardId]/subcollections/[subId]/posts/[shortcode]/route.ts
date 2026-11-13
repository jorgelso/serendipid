import { NextRequest, NextResponse } from "next/server";
import { addPostToSubcollection, removePostFromSubcollection, SerendipidApiError } from "@/lib/apiClient";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ boardId: string; subId: string; shortcode: string }> }
) {
  const { boardId, subId, shortcode } = await params;
  try {
    const sub = await addPostToSubcollection(boardId, subId, shortcode);
    return NextResponse.json({ success: true, data: sub });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ boardId: string; subId: string; shortcode: string }> }
) {
  const { boardId, subId, shortcode } = await params;
  try {
    const sub = await removePostFromSubcollection(boardId, subId, shortcode);
    return NextResponse.json({ success: true, data: sub });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
