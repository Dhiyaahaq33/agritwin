"""
db/supabase_client.py — Supabase PostgreSQL client for AgriTwin
================================================================
Menggantikan DataHistorian (SQLite) untuk cloud persistence.
Dual-write: Supabase primary, SQLite local fallback.

Setup:
  1. Buat project di supabase.com (gratis 500MB)
  2. Isi SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY di .env
  3. Jalankan ensure_tables() sekali untuk create schema

Tables (sesuai schema_agritwin.sql):
  - sensor_readings, flow_meter_log, actuator_events
  - alerts, alert_rules, vernalization_log
  - weather_snapshots, market_prices
  - greenhouses, zones, plantings, crops
"""
import datetime
import os
import threading
from typing import Any, Dict, List, Optional

_supabase_client = None
_init_lock = threading.Lock()
_available = False


def _get_client():
    """Lazy-init Supabase client dari env vars."""
    global _supabase_client, _available
    if _supabase_client is not None:
        return _supabase_client

    with _init_lock:
        if _supabase_client is not None:
            return _supabase_client

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "") or \
              os.environ.get("SUPABASE_ANON_KEY", "")

        if not url or not key:
            _available = False
            return None

        try:
            from supabase import create_client
            _supabase_client = create_client(url, key)
            _available = True
            return _supabase_client
        except Exception as e:
            print(f"[Supabase] Init failed: {e}")
            _available = False
            return None


def is_available() -> bool:
    """Check apakah Supabase client tersedia."""
    _get_client()
    return _available


def client():
    """Get the Supabase client instance (or None)."""
    return _get_client()


# ══════════════════════════════════════════════════════════════════════════════
# TABLE CREATION — jalankan sekali untuk setup schema
# ══════════════════════════════════════════════════════════════════════════════

_SCHEMA_SQL = """
-- sensor_readings
CREATE TABLE IF NOT EXISTS sensor_readings (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    param           TEXT NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    unit            TEXT DEFAULT '',
    source          TEXT NOT NULL DEFAULT 'sim',
    quality         TEXT DEFAULT 'good'
);
CREATE INDEX IF NOT EXISTS idx_sensor_zone_param_ts
    ON sensor_readings (zone_id, param, ts DESC);

-- flow_meter_log
CREATE TABLE IF NOT EXISTS flow_meter_log (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    flow_lpm        DOUBLE PRECISION NOT NULL,
    target_lpm      DOUBLE PRECISION NOT NULL,
    pressure_bar    DOUBLE PRECISION DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'normal'
);
CREATE INDEX IF NOT EXISTS idx_flow_zone_ts
    ON flow_meter_log (zone_id, ts DESC);

-- actuator_events
CREATE TABLE IF NOT EXISTS actuator_events (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    actuator        TEXT NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    triggered_by    TEXT NOT NULL DEFAULT 'auto'
);

-- alerts
CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    param           TEXT,
    value           DOUBLE PRECISION,
    acknowledged    BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_alerts_zone_ack
    ON alerts (zone_id, acknowledged, ts DESC);

-- vernalization_log
CREATE TABLE IF NOT EXISTS vernalization_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    crop_id         TEXT NOT NULL,
    temp_c          DOUBLE PRECISION,
    cold_hours      DOUBLE PRECISION,
    target_hours    DOUBLE PRECISION
);

-- weather_snapshots
CREATE TABLE IF NOT EXISTS weather_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    location_key    TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    forecast_for    TIMESTAMPTZ NOT NULL,
    temp_c          DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    wind_ms         DOUBLE PRECISION,
    solar_wm2       DOUBLE PRECISION,
    source          TEXT DEFAULT 'open-meteo',
    is_forecast     BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS idx_weather_loc_ts
    ON weather_snapshots (location_key, forecast_for DESC);

-- market_prices
CREATE TABLE IF NOT EXISTS market_prices (
    id              BIGSERIAL PRIMARY KEY,
    crop_id         TEXT NOT NULL,
    region          TEXT,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    price_per_kg    DOUBLE PRECISION NOT NULL,
    currency        TEXT DEFAULT 'IDR',
    source          TEXT
);
CREATE INDEX IF NOT EXISTS idx_prices_crop_ts
    ON market_prices (crop_id, ts DESC);
"""


def ensure_tables() -> bool:
    """Create semua tabel jika belum ada. Returns True jika sukses."""
    c = _get_client()
    if not c:
        return False
    try:
        # Supabase: execute raw SQL via rpc atau postgrest
        # Kita pakai rpc call ke fungsi SQL, atau langsung via REST
        # Cara paling simple: pakai Supabase SQL Editor manual,
        # atau via postgrest rpc jika ada function.
        # Untuk sekarang, kita coba insert ke tabel — kalau error, tabel belum ada
        # dan user perlu run SQL di Supabase Dashboard.
        c.table("sensor_readings").select("id").limit(1).execute()
        return True
    except Exception:
        print("[Supabase] Tables not found. Please run the schema SQL in Supabase SQL Editor.")
        print("[Supabase] File: docs/schema_agritwin.sql (simplified version)")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CRUD OPERATIONS — drop-in replacement untuk DataHistorian methods
# ══════════════════════════════════════════════════════════════════════════════

def log_sensor(zone_id: str, readings: Dict[str, float],
               source: str = "sim", unit: str = "") -> bool:
    """Insert sensor readings ke Supabase. Returns True jika sukses."""
    c = _get_client()
    if not c:
        return False
    try:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rows = [
            {
                "zone_id": zone_id,
                "ts":      now,
                "param":   param,
                "value":   float(val),
                "unit":    unit,
                "source":  source,
                "quality": "good",
            }
            for param, val in readings.items()
        ]
        if rows:
            c.table("sensor_readings").insert(rows).execute()
        return True
    except Exception as e:
        print(f"[Supabase] log_sensor error: {e}")
        return False


def log_flow(zone_id: str, flow_lpm: float, target_lpm: float,
             pressure_bar: float = 0.0, status: str = "normal") -> bool:
    """Insert flow meter reading."""
    c = _get_client()
    if not c:
        return False
    try:
        c.table("flow_meter_log").insert({
            "zone_id":      zone_id,
            "ts":           datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "flow_lpm":     flow_lpm,
            "target_lpm":   target_lpm,
            "pressure_bar": pressure_bar,
            "status":       status,
        }).execute()
        return True
    except Exception as e:
        print(f"[Supabase] log_flow error: {e}")
        return False


def log_actuator(zone_id: str, actuator: str, value: float,
                 triggered_by: str = "auto") -> bool:
    """Insert actuator event."""
    c = _get_client()
    if not c:
        return False
    try:
        c.table("actuator_events").insert({
            "zone_id":      zone_id,
            "ts":           datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "actuator":     actuator,
            "value":        value,
            "triggered_by": triggered_by,
        }).execute()
        return True
    except Exception as e:
        print(f"[Supabase] log_actuator error: {e}")
        return False


def log_alert(zone_id: str, severity: str, message: str,
              param: str = "", value: float = 0.0) -> bool:
    """Insert alert."""
    c = _get_client()
    if not c:
        return False
    try:
        c.table("alerts").insert({
            "zone_id":      zone_id,
            "ts":           datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "severity":     severity,
            "message":      message,
            "param":        param,
            "value":        value,
            "acknowledged": False,
        }).execute()
        return True
    except Exception as e:
        print(f"[Supabase] log_alert error: {e}")
        return False


def get_sensor_history(zone_id: str, param: str = "",
                       limit: int = 100) -> List[Dict]:
    """Ambil histori sensor readings."""
    c = _get_client()
    if not c:
        return []
    try:
        q = c.table("sensor_readings") \
             .select("*") \
             .eq("zone_id", zone_id) \
             .order("ts", desc=True) \
             .limit(limit)
        if param:
            q = q.eq("param", param)
        result = q.execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"[Supabase] get_sensor_history error: {e}")
        return []


def get_alerts(zone_id: str = "", acknowledged: Optional[bool] = None,
               limit: int = 50) -> List[Dict]:
    """Ambil daftar alerts."""
    c = _get_client()
    if not c:
        return []
    try:
        q = c.table("alerts") \
             .select("*") \
             .order("ts", desc=True) \
             .limit(limit)
        if zone_id:
            q = q.eq("zone_id", zone_id)
        if acknowledged is not None:
            q = q.eq("acknowledged", acknowledged)
        result = q.execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"[Supabase] get_alerts error: {e}")
        return []


def acknowledge_alert(alert_id: int) -> bool:
    """Mark alert sebagai acknowledged."""
    c = _get_client()
    if not c:
        return False
    try:
        c.table("alerts") \
         .update({"acknowledged": True}) \
         .eq("id", alert_id) \
         .execute()
        return True
    except Exception:
        return False


# ── Market prices ────────────────────────────────────────────────────────────

def save_market_price(crop_id: str, price_per_kg: float,
                      region: str = "", source: str = "",
                      currency: str = "IDR") -> bool:
    """Simpan harga pasar ke Supabase."""
    c = _get_client()
    if not c:
        return False
    try:
        c.table("market_prices").insert({
            "crop_id":      crop_id,
            "ts":           datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "price_per_kg": price_per_kg,
            "region":       region,
            "currency":     currency,
            "source":       source,
        }).execute()
        return True
    except Exception:
        return False


def get_latest_price(crop_id: str, region: str = "") -> Optional[Dict]:
    """Ambil harga terbaru untuk crop tertentu."""
    c = _get_client()
    if not c:
        return None
    try:
        q = c.table("market_prices") \
             .select("*") \
             .eq("crop_id", crop_id) \
             .order("ts", desc=True) \
             .limit(1)
        if region:
            q = q.eq("region", region)
        result = q.execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


# ── Weather snapshots ────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# PAYMENTS — event log + subscription status
# ══════════════════════════════════════════════════════════════════════════════

def log_payment_event(
    order_id: str,
    transaction_status: str,
    payment_type: str = "",
    gross_amount: str = "",
    transaction_id: str = "",
    user_id: str = "",
    raw_payload: Optional[Dict] = None,
) -> bool:
    """Log satu event pembayaran Midtrans ke tabel payment_events.

    Selalu dipanggil terlepas dari status transaksi (settlement, deny, expire, dll).
    Merupakan audit trail yang tidak boleh dilewati.
    """
    c = _get_client()
    if not c:
        return False
    try:
        c.table("payment_events").insert({
            "order_id":           order_id,
            "transaction_id":     transaction_id,
            "transaction_status": transaction_status,
            "payment_type":       payment_type,
            "gross_amount":       gross_amount,
            "user_id":            user_id,
            "raw_payload":        raw_payload or {},
            "created_at":         datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as e:
        print(f"[Supabase] log_payment_event error: {e}")
        return False


def update_subscription_status(user_id: str, active: bool) -> bool:
    """Update kolom subscription_active di tabel users berdasarkan clerk_id.

    Dipanggil setelah webhook Midtrans diterima:
    - active=True  → status settlement atau capture
    - active=False → status cancel, deny, atau expire
    """
    c = _get_client()
    if not c or not user_id:
        return False
    try:
        c.table("users").update({
            "subscription_active": active,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }).eq("clerk_id", user_id).execute()
        return True
    except Exception as e:
        print(f"[Supabase] update_subscription_status error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# USERS — Clerk user sync via webhook
# ══════════════════════════════════════════════════════════════════════════════

def upsert_user(
    clerk_id: str,
    email: str,
    name: str = "",
) -> bool:
    """Insert atau update user berdasarkan clerk_id.

    Dipanggil dari Clerk webhook untuk event user.created dan user.updated.
    Pada INSERT: subscription_active menggunakan DEFAULT false dari DB.
    Pada UPDATE (conflict clerk_id): hanya email, name, updated_at yang berubah —
    subscription_active tidak ikut di-reset.
    """
    c = _get_client()
    if not c or not clerk_id:
        return False
    try:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        c.table("users").upsert({
            "clerk_id":   clerk_id,
            "email":      email,
            "name":       name,
            "updated_at": now,
        }, on_conflict="clerk_id").execute()
        return True
    except Exception as e:
        print(f"[Supabase] upsert_user error: {e}")
        return False


def soft_delete_user(clerk_id: str) -> bool:
    """Soft delete user dengan mengisi deleted_at=now(). Baris TIDAK dihapus.

    Dipanggil dari Clerk webhook untuk event user.deleted.
    Data historis tetap tersimpan untuk audit trail.
    """
    c = _get_client()
    if not c or not clerk_id:
        return False
    try:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        c.table("users").update({
            "deleted_at": now,
            "updated_at": now,
        }).eq("clerk_id", clerk_id).execute()
        return True
    except Exception as e:
        print(f"[Supabase] soft_delete_user error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# VOC READINGS — AgriVOC module
# ══════════════════════════════════════════════════════════════════════════════

def log_voc_reading(
    zone_id: str,
    mq135_value: float,
    mq9_value: float,
    mq2_value: float,
    stress_type: str,
    confidence_score: float,
    recommended_action: str,
    raw_payload: Optional[Dict] = None,
) -> bool:
    """Insert satu baris pembacaan sensor VOC + hasil klasifikasi ke Supabase.

    Dipanggil oleh mqtt_broker setiap kali data VOC diterima dari ESP32.
    """
    c = _get_client()
    if not c:
        return False
    try:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        c.table("voc_readings").insert({
            "zone_id":            zone_id,
            "timestamp":          now,
            "mq135_value":        mq135_value,
            "mq9_value":          mq9_value,
            "mq2_value":          mq2_value,
            "stress_type":        stress_type,
            "confidence_score":   confidence_score,
            "recommended_action": recommended_action,
            "raw_payload":        raw_payload or {},
            "created_at":         now,
        }).execute()
        return True
    except Exception as e:
        print(f"[Supabase] log_voc_reading error: {e}")
        return False


def get_voc_history(zone_id: str, limit: int = 50) -> List[Dict]:
    """Ambil histori pembacaan VOC dari Supabase.

    Args:
        zone_id: ID zona. String kosong ("") untuk mengambil semua zona.
        limit:   Maksimum jumlah baris yang dikembalikan.

    Returns:
        List dict baris voc_readings, diurutkan terbaru lebih dulu.
    """
    c = _get_client()
    if not c:
        return []
    try:
        q = c.table("voc_readings") \
             .select("*") \
             .order("timestamp", desc=True) \
             .limit(limit)
        if zone_id:
            q = q.eq("zone_id", zone_id)
        result = q.execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"[Supabase] get_voc_history error: {e}")
        return []


def save_weather_snapshot(location_key: str, forecast_for: str,
                          temp_c: float, humidity_pct: float,
                          precipitation_mm: float, wind_ms: float,
                          solar_wm2: float, source: str = "open-meteo",
                          is_forecast: bool = True) -> bool:
    """Simpan snapshot cuaca ke Supabase."""
    c = _get_client()
    if not c:
        return False
    try:
        c.table("weather_snapshots").insert({
            "location_key":    location_key,
            "ts":              datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "forecast_for":    forecast_for,
            "temp_c":          temp_c,
            "humidity_pct":    humidity_pct,
            "precipitation_mm": precipitation_mm,
            "wind_ms":         wind_ms,
            "solar_wm2":       solar_wm2,
            "source":          source,
            "is_forecast":     is_forecast,
        }).execute()
        return True
    except Exception:
        return False
