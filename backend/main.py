"""
AgriTwin Backend — FastAPI
==========================
Entry point: uvicorn backend.main:app --reload --port 8000

Endpoints:
  GET  /api/health                        → status semua service
  GET  /api/zones                         → list zones (from Supabase)
  GET  /api/weather/{lat}/{lon}           → cuaca lokasi (Open-Meteo)
  POST /api/ai/query                      → tanya AI agronomist
  GET  /api/sensors/{zone_id}             → historis sensor
  POST /api/sensors/ingest                → terima data dari ESP32/client
  GET  /api/alerts                        → list alerts
  POST /api/alerts/{id}/acknowledge       → acknowledge alert
  GET  /api/market/prices                 → harga komoditas
  POST /api/payments/create-transaction   → buat transaksi Midtrans Snap
  POST /api/payments/webhook              → Midtrans payment notification webhook
  POST /api/webhooks/clerk                → Clerk user lifecycle webhook
  GET  /api/voc/{zone_id}                 → histori pembacaan VOC + klasifikasi stres
  POST /api/voc/train                     → trigger pelatihan ulang VOC classifier
  WS   /ws/zones/{zone_id}/live           → WebSocket realtime sensor
"""
import os
import sys
import time

# Ensure project root is in path for imports
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import json

app = FastAPI(
    title="AgriTwin API",
    version="1.0.0",
    description="AI Greenhouse Digital Twin Backend",
)

# CORS — allow Next.js frontend
_CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    """Status semua service: DB, MQTT, weather API."""
    from db.supabase_client import is_available as sb_ok
    from iot.mqtt_broker import get_broker

    broker = get_broker()
    return {
        "status": "ok",
        "services": {
            "supabase":  {"connected": sb_ok()},
            "mqtt":      broker.status_dict(),
            "weather":   {"provider": "open-meteo", "status": "ok"},
        },
        "uptime_s": time.time() - _START_TIME,
    }

_START_TIME = time.time()


# ══════════════════════════════════════════════════════════════════════════════
# ZONES
# ══════════════════════════════════════════════════════════════════════════════

# Fallback static zones when Supabase isn't configured
_DEFAULT_ZONES = [
    {"zone_id": "ZONE-A", "name": "Zona A", "crop": "tomat", "area_m2": 100},
    {"zone_id": "ZONE-B", "name": "Zona B", "crop": "selada", "area_m2": 80},
]

@app.get("/api/zones")
async def list_zones():
    """List semua zona greenhouse dari Supabase (fallback ke default)."""
    from db.supabase_client import client as sb_client
    c = sb_client()
    if c:
        try:
            result = c.table("zones").select("*").order("zone_id").execute()
            if result.data:
                return {"count": len(result.data), "data": result.data}
        except Exception:
            pass
    return {"count": len(_DEFAULT_ZONES), "data": _DEFAULT_ZONES}


# ══════════════════════════════════════════════════════════════════════════════
# WEATHER
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/weather/{lat}/{lon}")
async def get_weather(lat: float, lon: float, days: int = 3):
    """Cuaca lokasi via Open-Meteo."""
    from weather.open_meteo import fetch_current, fetch_forecast

    current = fetch_current(lat, lon)
    if not current:
        raise HTTPException(502, "Weather service unavailable")

    forecast = fetch_forecast(lat, lon, days=min(days, 16))

    from dataclasses import asdict
    return {
        "current":  asdict(current),
        "forecast": [asdict(f) for f in forecast[:72]],  # max 3 days hourly
    }


# ══════════════════════════════════════════════════════════════════════════════
# SENSORS
# ══════════════════════════════════════════════════════════════════════════════

class SensorIngest(BaseModel):
    zone_id: str
    readings: Dict[str, float]
    source: str = "sensor"

@app.post("/api/sensors/ingest")
async def ingest_sensor(data: SensorIngest):
    """Terima data sensor dari ESP32 atau client."""
    from db.supabase_client import log_sensor
    from alerts.alert_engine import get_alert_engine

    ok = log_sensor(data.zone_id, data.readings, source=data.source)

    # Evaluate alerts
    engine = get_alert_engine()
    alerts = engine.evaluate(data.zone_id, data.readings)

    # Broadcast to WebSocket subscribers
    await _broadcast_ws(data.zone_id, {
        "type": "sensor_update",
        "zone_id": data.zone_id,
        "readings": data.readings,
        "alerts": alerts,
        "ts": time.time(),
    })

    return {
        "ok": ok,
        "alerts_fired": len(alerts),
        "alerts": alerts,
    }


@app.get("/api/sensors/{zone_id}")
async def get_sensors(zone_id: str, param: str = "", limit: int = 100):
    """Historis sensor readings dari Supabase."""
    from db.supabase_client import get_sensor_history
    data = get_sensor_history(zone_id, param=param, limit=limit)
    return {"zone_id": zone_id, "count": len(data), "data": data}


# ══════════════════════════════════════════════════════════════════════════════
# ALERTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/alerts")
async def list_alerts(zone_id: str = "", limit: int = 50):
    """List alerts dari Supabase."""
    from db.supabase_client import get_alerts
    data = get_alerts(zone_id=zone_id, limit=limit)
    return {"count": len(data), "data": data}


@app.post("/api/alerts/{alert_id}/acknowledge")
async def ack_alert(alert_id: int):
    """Acknowledge alert."""
    from db.supabase_client import acknowledge_alert
    ok = acknowledge_alert(alert_id)
    return {"ok": ok}


# ══════════════════════════════════════════════════════════════════════════════
# MARKET PRICES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/market/prices")
async def market_prices(crop: str = ""):
    """Harga komoditas pertanian."""
    from market.price_feed import get_price, get_all_prices

    if crop:
        return get_price(crop)
    return get_all_prices()


# ══════════════════════════════════════════════════════════════════════════════
# AI AGRONOMIST
# ══════════════════════════════════════════════════════════════════════════════

class AIQuery(BaseModel):
    prompt: str
    zone_id: Optional[str] = None
    context: Optional[Dict] = None

@app.post("/api/ai/query")
async def ai_query(query: AIQuery):
    """Tanya AI agronomist (Gemini + RAG / Groq / Stub fallback)."""
    from rag.knowledge_base import build_rag_prompt

    # RAG: inject konteks agronomi relevan ke prompt
    rag_prompt = build_rag_prompt(query.prompt, top_k=3)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        # Stub fallback — tetap pakai RAG context
        from rag.knowledge_base import retrieve
        chunks = retrieve(query.prompt, top_k=2)
        context_text = "\n".join(chunks[:2]) if chunks else "Tidak ada konteks."
        return {
            "response": f"[Stub + RAG] Berdasarkan basis pengetahuan:\n\n{context_text}\n\n"
                        f"Silakan konfigurasi GEMINI_API_KEY di .env untuk jawaban AI lengkap.",
            "provider": "stub+rag",
        }

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))

        response = model.generate_content(rag_prompt)
        return {
            "response": response.text,
            "provider": "gemini+rag",
        }
    except Exception as e:
        return {
            "response": f"[Error] {str(e)[:100]}. Coba lagi nanti.",
            "provider": "error",
        }


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENTS — Midtrans Snap
# ══════════════════════════════════════════════════════════════════════════════

class PaymentCreate(BaseModel):
    order_id:       str
    amount:         int           # IDR, integer tanpa desimal
    item_name:      str
    customer_name:  str
    customer_email: str
    zone_id:        Optional[str] = None
    user_id:        Optional[str] = None  # Clerk user ID — dikirim ke Midtrans custom_field2


@app.post("/api/payments/create-transaction")
async def create_payment(data: PaymentCreate):
    """Buat transaksi Midtrans Snap. Returns snap token + redirect_url."""
    from payments.midtrans_client import create_snap_transaction
    result = create_snap_transaction(
        order_id=data.order_id,
        amount=data.amount,
        item_name=data.item_name,
        customer_name=data.customer_name,
        customer_email=data.customer_email,
        zone_id=data.zone_id,
        user_id=data.user_id,
    )
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@app.post("/api/payments/webhook")
async def midtrans_webhook(request: Request):
    """Midtrans payment notification webhook.

    Validasi signature SHA-512, log semua event ke payment_events,
    dan update subscription_active berdasarkan status transaksi.
    Selalu return 200 jika signature valid — bahkan untuk transaksi gagal.
    """
    import hashlib
    from db.supabase_client import log_payment_event, update_subscription_status

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body bukan JSON valid")

    order_id           = str(body.get("order_id", ""))
    status_code        = str(body.get("status_code", ""))
    gross_amount       = str(body.get("gross_amount", ""))
    signature_key      = str(body.get("signature_key", ""))
    transaction_status = str(body.get("transaction_status", ""))
    payment_type       = str(body.get("payment_type", ""))
    transaction_id     = str(body.get("transaction_id", ""))
    user_id            = str(body.get("custom_field2", ""))

    # Validasi signature: SHA512(order_id + status_code + gross_amount + server_key)
    server_key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    if not server_key:
        raise HTTPException(status_code=403, detail="MIDTRANS_SERVER_KEY tidak dikonfigurasi")

    expected_sig = hashlib.sha512(
        f"{order_id}{status_code}{gross_amount}{server_key}".encode("utf-8")
    ).hexdigest()

    if signature_key != expected_sig:
        raise HTTPException(status_code=403, detail="Signature tidak valid")

    # Log event — selalu, termasuk transaksi gagal
    log_payment_event(
        order_id=order_id,
        transaction_status=transaction_status,
        payment_type=payment_type,
        gross_amount=gross_amount,
        transaction_id=transaction_id,
        user_id=user_id,
        raw_payload=body,
    )

    # Update subscription status berdasarkan hasil transaksi
    if user_id:
        _ACTIVE   = {"settlement", "capture"}
        _INACTIVE = {"cancel", "deny", "expire"}
        if transaction_status in _ACTIVE:
            update_subscription_status(user_id, True)
        elif transaction_status in _INACTIVE:
            update_subscription_status(user_id, False)

    return {"ok": True, "transaction_status": transaction_status}


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOKS — Clerk user lifecycle
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/webhooks/clerk")
async def clerk_webhook(request: Request):
    """Clerk user lifecycle webhook — sinkronisasi user ke Supabase.

    Memvalidasi signature Svix, lalu memproses event:
    - user.created → upsert_user() dengan subscription_active=False (default)
    - user.updated → upsert_user() — hanya email, name, updated_at yang berubah
    - user.deleted → soft_delete_user() — set deleted_at, baris tidak dihapus
    - event lain   → log & return 200 (tidak crash)
    """
    from db.supabase_client import upsert_user, soft_delete_user

    secret = os.environ.get("CLERK_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=403, detail="CLERK_WEBHOOK_SECRET tidak dikonfigurasi")

    svix_id        = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=403, detail="Svix headers tidak lengkap")

    try:
        body_bytes = await request.body()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca request body: {str(e)[:80]}")

    try:
        from svix.webhooks import Webhook, WebhookVerificationError
        wh      = Webhook(secret)
        payload = wh.verify(body_bytes, {
            "svix-id":        svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature,
        })
    except Exception:
        raise HTTPException(status_code=403, detail="Svix signature tidak valid")

    event_type = payload.get("type", "")
    data       = payload.get("data", {})

    try:
        if event_type in ("user.created", "user.updated"):
            clerk_id = data.get("id", "")
            emails   = data.get("email_addresses") or []
            email    = emails[0].get("email_address", "") if emails else ""
            name     = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            upsert_user(clerk_id=clerk_id, email=email, name=name)

        elif event_type == "user.deleted":
            clerk_id = data.get("id", "")
            soft_delete_user(clerk_id=clerk_id)

        else:
            print(f"[Clerk] Unknown event type: {event_type!r} — ignored")

    except Exception as e:
        print(f"[Clerk] Error processing {event_type}: {e}")
        return {"ok": False, "event_type": event_type, "error": str(e)[:100]}

    return {"ok": True, "event_type": event_type}


# ══════════════════════════════════════════════════════════════════════════════
# VOC — AgriVOC plant stress detection
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/voc/{zone_id}")
async def get_voc_readings(zone_id: str, limit: int = 20):
    """Return histori pembacaan VOC + hasil klasifikasi stres tanaman."""
    from db.supabase_client import get_voc_history
    data = get_voc_history(zone_id, limit=limit)
    return {"zone_id": zone_id, "count": len(data), "data": data}


@app.post("/api/voc/train")
async def train_voc_model():
    """Trigger pelatihan ulang VOC classifier dari data historis Supabase.

    Jika data Supabase tidak mencukupi (<100 sampel per kelas), dataset sintetis
    ditambahkan secara otomatis sebagai pelengkap.
    Memerlukan lightgbm dan numpy terinstal di environment.
    """
    from iot.voc_classifier import get_classifier
    try:
        classifier = get_classifier()
        result     = classifier.train_from_supabase()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training error: {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET — Realtime sensor updates
# ══════════════════════════════════════════════════════════════════════════════

_ws_connections: Dict[str, List[WebSocket]] = {}


async def _broadcast_ws(zone_id: str, data: dict):
    """Broadcast ke semua WebSocket subscribers untuk zone tertentu."""
    conns = _ws_connections.get(zone_id, [])
    dead = []
    for ws in conns:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        conns.remove(ws)


@app.websocket("/ws/zones/{zone_id}/live")
async def websocket_zone(websocket: WebSocket, zone_id: str):
    """WebSocket endpoint untuk realtime sensor data per zone."""
    await websocket.accept()

    if zone_id not in _ws_connections:
        _ws_connections[zone_id] = []
    _ws_connections[zone_id].append(websocket)

    try:
        # Send initial state
        await websocket.send_json({
            "type": "connected",
            "zone_id": zone_id,
            "ts": time.time(),
        })

        # Keep alive — listen for client messages
        while True:
            data = await websocket.receive_text()
            # Client can send commands (future: actuator control)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        if zone_id in _ws_connections:
            try:
                _ws_connections[zone_id].remove(websocket)
            except ValueError:
                pass
