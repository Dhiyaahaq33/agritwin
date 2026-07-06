import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { zone_id, readings, source = "manual" } = body;
  const rows = Object.entries(readings).map(([sensor_type, value]) => ({
    zone_id,
    sensor_type,
    value,
    source,
    recorded_at: new Date().toISOString(),
  }));
  const { error } = await supabase.from("sensor_readings").insert(rows);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, inserted: rows.length });
}
