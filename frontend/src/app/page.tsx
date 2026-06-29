"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { UserButton, useUser } from "@clerk/nextjs";
import { track, identifyUser } from "@/lib/posthog";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SensorCard {
  label: string;
  param: string;
  unit: string;
  icon: string;
  color: string;
  min?: number;
  max?: number;
}

const SENSOR_CARDS: SensorCard[] = [
  { label: "Suhu",         param: "temperature",  unit: "°C",    icon: "🌡️", color: "text-red-400",    min: 15,  max: 38   },
  { label: "Kelembapan",   param: "humidity",      unit: "%",     icon: "💧", color: "text-blue-400",   min: 30,  max: 95   },
  { label: "CO2",          param: "co2",           unit: "ppm",   icon: "🫧", color: "text-teal-400",   min: 200, max: 1200 },
  { label: "Soil Moisture",param: "soil_moisture", unit: "%",     icon: "🌱", color: "text-green-400",  min: 20,  max: 90   },
  { label: "pH",           param: "ph",            unit: "",      icon: "🧪", color: "text-purple-400", min: 5.0, max: 7.5  },
  { label: "EC",           param: "ec",            unit: "mS/cm", icon: "⚡", color: "text-yellow-400", min: 0.5, max: 4.0  },
];

function Dashboard() {
  const { user } = useUser();
  const [health,    setHealth]    = useState<any>(null);
  const [weather,   setWeather]   = useState<any>(null);
  const [sensors,   setSensors]   = useState<Record<string, number>>({});
  const [alerts,    setAlerts]    = useState<any[]>([]);
  const [aiPrompt,  setAiPrompt]  = useState("");
  const [aiResponse,setAiResponse]= useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [zoneId]                  = useState("ZONE-A");

  // Identify user in PostHog once Clerk loads
  useEffect(() => {
    if (user) {
      identifyUser(user.id, {
        email:      user.primaryEmailAddress?.emailAddress,
        name:       user.fullName,
        created_at: user.createdAt,
      });
    }
  }, [user]);

  useEffect(() => {
    // Track zone viewed
    track("zone_viewed", { zone_id: zoneId });

    // Fetch initial data
    fetch(`${API}/api/health`).then((r) => r.json()).then(setHealth).catch(() => {});
    fetch(`${API}/api/weather/-6.914/107.609`).then((r) => r.json()).then(setWeather).catch(() => {});
    fetch(`${API}/api/alerts?limit=5`)
      .then((r) => r.json())
      .then((d) => setAlerts(d.data || []))
      .catch(() => {});

    // Fetch latest sensor readings
    fetch(`${API}/api/sensors/${zoneId}?limit=20`)
      .then((r) => r.json())
      .then((d) => {
        const latest: Record<string, number> = {};
        for (const row of d.data || []) {
          if (!latest[row.param]) latest[row.param] = row.value;
        }
        setSensors(latest);
      })
      .catch(() => {});

    // WebSocket for live updates — uses env var, wss:// in production
    let ws: WebSocket | null = null;
    try {
      const httpBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const wsBase   = httpBase.replace(/^https/, "wss").replace(/^http/, "ws");
      ws = new WebSocket(`${wsBase}/ws/zones/${zoneId}/live`);

      ws.onopen = () => {
        track("sensor_connected", { zone_id: zoneId });
      };

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "sensor_update" && msg.readings) {
          setSensors((prev) => ({ ...prev, ...msg.readings }));
          if (msg.alerts?.length) {
            setAlerts((prev) => [...msg.alerts, ...prev].slice(0, 10));
          }
        }
      };
    } catch {}

    return () => { ws?.close(); };
  }, [zoneId]);

  const askAI = async () => {
    if (!aiPrompt.trim()) return;
    setAiLoading(true);
    track("ai_query_sent", { zone_id: zoneId, prompt_length: aiPrompt.length });
    try {
      const res  = await fetch(`${API}/api/ai/query`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ prompt: aiPrompt, zone_id: zoneId }),
      });
      const data = await res.json();
      setAiResponse(data.response || "No response");
    } catch {
      setAiResponse("Error connecting to API");
    }
    setAiLoading(false);
  };

  const acknowledgeAlert = async (alertId: number) => {
    try {
      await fetch(`${API}/api/alerts/${alertId}/acknowledge`, { method: "POST" });
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
      track("alert_acknowledged", { alert_id: alertId, zone_id: zoneId });
    } catch {}
  };

  return (
    <main className="min-h-screen p-4 md:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-green-400">🌱 AgriTwin Dashboard</h1>
          <p className="text-sm text-gray-500">AI Greenhouse Digital Twin</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs ${
            health?.status === "ok"
              ? "bg-green-900/50 text-green-400"
              : "bg-red-900/50 text-red-400"
          }`}>
            <span className={`w-2 h-2 rounded-full ${
              health?.status === "ok" ? "bg-green-400 animate-pulse" : "bg-red-400"
            }`} />
            {health?.status === "ok" ? "LIVE" : "OFFLINE"}
          </span>
          <span className="text-xs text-gray-600">{zoneId}</span>
          <UserButton afterSignOutUrl="/sign-in" />
        </div>
      </header>

      {/* Sensor Cards Grid */}
      <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        {SENSOR_CARDS.map((card) => {
          const val     = sensors[card.param];
          const hasData = val !== undefined;
          const isAlert =
            hasData &&
            ((card.min !== undefined && val < card.min) ||
             (card.max !== undefined && val > card.max));
          return (
            <div
              key={card.param}
              className={`rounded-xl border p-4 transition ${
                isAlert
                  ? "border-red-500/50 bg-red-950/30"
                  : "border-gray-800 bg-gray-900/50"
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">{card.icon}</span>
                <span className="text-xs text-gray-500">{card.label}</span>
              </div>
              <div className={`text-2xl font-bold ${card.color}`}>
                {hasData ? val.toFixed(1) : "—"}
                <span className="text-xs text-gray-500 ml-1">{card.unit}</span>
              </div>
            </div>
          );
        })}
      </section>

      {/* Two-column: Weather + Alerts */}
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        {/* Weather */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3">🌦️ Cuaca (Open-Meteo)</h2>
          {weather?.current ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Suhu</span>
                <span className="text-white">{weather.current.temperature_c}°C</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Kelembapan</span>
                <span className="text-white">{weather.current.humidity_pct}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Angin</span>
                <span className="text-white">{weather.current.wind_speed_ms} m/s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Hujan</span>
                <span className="text-white">{weather.current.precipitation_mm} mm</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Radiasi</span>
                <span className="text-white">{weather.current.solar_radiation_wm2} W/m²</span>
              </div>
              <div className="text-xs text-gray-600 pt-2">
                Forecast: {weather.forecast?.length || 0} titik data
              </div>
            </div>
          ) : (
            <p className="text-gray-600 text-sm">Loading...</p>
          )}
        </div>

        {/* Alerts */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3">🚨 Alerts</h2>
          {alerts.length > 0 ? (
            <div className="space-y-2">
              {alerts.slice(0, 5).map((a, i) => (
                <div
                  key={a.id ?? i}
                  className={`flex items-start justify-between gap-2 text-xs p-2 rounded ${
                    a.severity === "critical"
                      ? "bg-red-950/50 text-red-300 border border-red-800/50"
                      : "bg-yellow-950/50 text-yellow-300 border border-yellow-800/50"
                  }`}
                >
                  <span>
                    {a.severity === "critical" ? "🔴" : "🟡"} {a.message}
                  </span>
                  {a.id && (
                    <button
                      onClick={() => acknowledgeAlert(a.id)}
                      className="shrink-0 opacity-60 hover:opacity-100 transition"
                      title="Tandai sudah dibaca"
                    >
                      ✓
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-green-600 text-sm">✅ Semua parameter normal</p>
          )}
        </div>
      </div>

      {/* AI Agronomist */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">🤖 AI Agronomist</h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && askAI()}
            placeholder="Tanya tentang tanaman, hama, pupuk..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-green-500"
          />
          <button
            onClick={askAI}
            disabled={aiLoading}
            className="px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 text-white text-sm rounded-lg transition"
          >
            {aiLoading ? "..." : "Tanya"}
          </button>
        </div>
        {aiResponse && (
          <div className="mt-3 p-3 bg-gray-800/50 rounded-lg text-sm text-gray-300 whitespace-pre-wrap">
            {aiResponse}
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="mt-8 text-center text-xs text-gray-700">
        AgriTwin v1.0 — AI Greenhouse Digital Twin Platform
      </footer>
    </main>
  );
}

export default dynamic(() => Promise.resolve(Dashboard), { ssr: false });
