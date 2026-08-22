import { NextRequest, NextResponse } from "next/server";
import { deleteBoardSubcollection, renameBoardSubcollection, SuperBrainApiError } from "@/lib/apiClient";

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ boardId: string; subId: string }> }
) {
  const { boardId, subId } = await params;
  let body: { name?: unknown; icon?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  try {
    const sub = await renameBoardSubcollection(boardId, subId, {
      ...(typeof body.name === "string" ? { name: body.name } : {}),
      ...(typeof body.icon === "string" ? { icon: body.icon } : {}),
    });
    return NextResponse.json({ success: true, data: sub });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ boardId: string; subId: string }> }
) {
  const { boardId, subId } = await params;
  try {
    await deleteBoardSubcollection(boardId, subId);
    return NextResponse.json({ success: true });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
