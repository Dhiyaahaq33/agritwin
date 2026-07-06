import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ zoneId: string }> }
) {
  const { zoneId } = await params;
  const limit = Number(req.nextUrl.searchParams.get("limit") ?? 50);
  const { data, error } = await supabase
    .from("sensor_readings")
    .select("*")
    .eq("zone_id", zoneId)
    .order("recorded_at", { ascending: false })
    .limit(limit);
  if (error) return NextResponse.json({ readings: [] });
  return NextResponse.json({ readings: data ?? [] });
}
