import { NextRequest, NextResponse } from "next/server";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ lat: string; lon: string }> }
) {
  const { lat, lon } = await params;
  const url =
    `https://api.open-meteo.com/v1/forecast` +
    `?latitude=${lat}&longitude=${lon}` +
    `&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,shortwave_radiation` +
    `&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode` +
    `&forecast_days=7&timezone=auto`;

  const res = await fetch(url, { next: { revalidate: 1800 } });
  if (!res.ok) return NextResponse.json({ error: "weather fetch failed" }, { status: 502 });

  const raw = await res.json();
  const c = raw.current;
  const d = raw.daily ?? {};
  const forecast = (d.time ?? []).map((date: string, i: number) => ({
    date,
    temp_max: d.temperature_2m_max?.[i] ?? 0,
    temp_min: d.temperature_2m_min?.[i] ?? 0,
    rain_mm:  d.precipitation_sum?.[i]  ?? 0,
    code:     d.weathercode?.[i]        ?? 0,
  }));

  return NextResponse.json({
    current: {
      temperature_c:       c.temperature_2m,
      humidity_pct:        c.relative_humidity_2m,
      wind_speed_ms:       c.wind_speed_10m,
      precipitation_mm:    c.precipitation,
      solar_radiation_wm2: c.shortwave_radiation ?? 0,
    },
    forecast,
  });
}
