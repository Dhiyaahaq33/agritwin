/**
 * AgriTwin API client — Next.js API Routes (no separate backend needed)
 */

export async function fetchHealth() {
  const res = await fetch("/api/health");
  return res.json();
}

export async function fetchWeather(lat: number, lon: number) {
  const res = await fetch(`/api/weather/${lat}/${lon}`);
  return res.json();
}

export async function fetchSensors(zoneId: string, limit = 50) {
  const res = await fetch(`/api/sensors/${zoneId}?limit=${limit}`);
  return res.json();
}

export async function fetchAlerts(zoneId = "", limit = 20) {
  const params = new URLSearchParams();
  if (zoneId) params.set("zone_id", zoneId);
  params.set("limit", String(limit));
  const res = await fetch(`/api/alerts?${params}`);
  return res.json();
}

export async function fetchPrices(crop = "") {
  const q = crop ? `?crop=${crop}` : "";
  const res = await fetch(`/api/market/prices${q}`);
  return res.json();
}

export async function askAI(prompt: string, zoneId?: string) {
  const res = await fetch("/api/ai/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, zone_id: zoneId }),
  });
  return res.json();
}

export async function ingestSensor(
  zoneId: string,
  readings: Record<string, number>,
  source = "manual"
) {
  const res = await fetch("/api/sensors/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zone_id: zoneId, readings, source }),
  });
  return res.json();
}

export async function fetchZones() {
  const res = await fetch("/api/zones");
  return res.json();
}

// WebSocket — only available when backend is running locally
export function connectZoneWS(
  zoneId: string,
  onMessage: (data: unknown) => void
): WebSocket | null {
  if (typeof window === "undefined") return null;
  const ws = new WebSocket(`ws://localhost:8000/ws/zones/${zoneId}/live`);
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)); } catch {}
  };
  return ws;
}
