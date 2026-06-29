/**
 * AgriTwin API client — fetches from FastAPI backend
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.json();
}

export async function fetchWeather(lat: number, lon: number) {
  const res = await fetch(`${API_BASE}/api/weather/${lat}/${lon}`);
  return res.json();
}

export async function fetchSensors(zoneId: string, limit = 50) {
  const res = await fetch(`${API_BASE}/api/sensors/${zoneId}?limit=${limit}`);
  return res.json();
}

export async function fetchAlerts(zoneId = "", limit = 20) {
  const params = new URLSearchParams();
  if (zoneId) params.set("zone_id", zoneId);
  params.set("limit", String(limit));
  const res = await fetch(`${API_BASE}/api/alerts?${params}`);
  return res.json();
}

export async function fetchPrices(crop = "") {
  const q = crop ? `?crop=${crop}` : "";
  const res = await fetch(`${API_BASE}/api/market/prices${q}`);
  return res.json();
}

export async function askAI(prompt: string, zoneId?: string) {
  const res = await fetch(`${API_BASE}/api/ai/query`, {
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
  const res = await fetch(`${API_BASE}/api/sensors/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zone_id: zoneId, readings, source }),
  });
  return res.json();
}

/**
 * WebSocket connection untuk realtime sensor data.
 * Otomatis pakai wss:// di production (HTTPS) dan ws:// di localhost.
 */
export function connectZoneWS(
  zoneId: string,
  onMessage: (data: any) => void
): WebSocket {
  const httpBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const wsBase = httpBase.replace(/^https/, "wss").replace(/^http/, "ws");
  const wsUrl = `${wsBase}/ws/zones/${zoneId}/live`;
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {}
  };
  return ws;
}

export async function fetchZones() {
  const res = await fetch(`${API_BASE}/api/zones`);
  return res.json();
}
