import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(req: NextRequest) {
  const zoneId = req.nextUrl.searchParams.get("zone_id") ?? "";
  const limit = Number(req.nextUrl.searchParams.get("limit") ?? 20);
  let q = supabase
    .from("alerts")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);
  if (zoneId) q = q.eq("zone_id", zoneId);
  const { data, error } = await q;
  if (error) return NextResponse.json({ alerts: [] });
  return NextResponse.json({ alerts: data ?? [] });
}
