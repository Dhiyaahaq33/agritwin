import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(req: NextRequest) {
  const crop = req.nextUrl.searchParams.get("crop") ?? "";
  let q = supabase
    .from("market_prices")
    .select("*")
    .order("recorded_at", { ascending: false })
    .limit(50);
  if (crop) q = q.ilike("crop_name", `%${crop}%`);
  const { data, error } = await q;
  if (error) return NextResponse.json({ prices: [] });
  return NextResponse.json({ prices: data ?? [] });
}
