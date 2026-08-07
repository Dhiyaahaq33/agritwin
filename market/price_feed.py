"""
market/price_feed.py — Real Market Price Feed for AgriTwin
==========================================================
Sumber harga komoditas pertanian Indonesia (menggantikan np.random):
  1. PIHPS Bank Indonesia (Panel Informasi Harga Pangan Strategis)
  2. World Bank Commodity Prices (global reference)
  3. Hardcoded fallback (data BPS/Kemendag Q1 2026)

Cache di Supabase (market_prices) dengan TTL 6 jam.
Jika Supabase belum setup, cache in-memory.
"""
import datetime
import io
import math
import time
from typing import Dict, Optional, Tuple

import openpyxl
import requests

# ── In-memory cache ──────────────────────────────────────────────────────────
_PRICE_CACHE: Dict[str, Tuple[float, float]] = {}  # key → (expire_ts, price)
_CACHE_TTL = 6 * 3600  # 6 jam


# ══════════════════════════════════════════════════════════════════════════════
# HARDCODED FALLBACK — harga rata-rata nasional Q1 2026 (IDR/kg)
# Sumber: BPS, Kemendag, PIHPS BI
# ══════════════════════════════════════════════════════════════════════════════

FALLBACK_PRICES: Dict[str, Dict] = {
    # Hortikultura
    "tomat":        {"price": 12000, "min": 8000,  "max": 18000, "source": "fallback-bps"},
    "selada":       {"price": 15000, "min": 10000, "max": 22000, "source": "fallback-bps"},
    "cabai_merah":  {"price": 45000, "min": 25000, "max": 80000, "source": "fallback-bps"},
    "cabai_rawit":  {"price": 55000, "min": 30000, "max": 100000,"source": "fallback-bps"},
    "bawang_merah": {"price": 35000, "min": 25000, "max": 50000, "source": "fallback-bps"},
    "bawang_putih": {"price": 40000, "min": 30000, "max": 55000, "source": "fallback-bps"},
    "kangkung":     {"price": 8000,  "min": 5000,  "max": 12000, "source": "fallback-bps"},
    "bayam":        {"price": 10000, "min": 6000,  "max": 15000, "source": "fallback-bps"},
    "timun":        {"price": 7000,  "min": 4000,  "max": 10000, "source": "fallback-bps"},
    "terong":       {"price": 9000,  "min": 5000,  "max": 14000, "source": "fallback-bps"},
    "wortel":       {"price": 12000, "min": 8000,  "max": 18000, "source": "fallback-bps"},
    "kentang":      {"price": 14000, "min": 10000, "max": 20000, "source": "fallback-bps"},
    "brokoli":      {"price": 25000, "min": 18000, "max": 35000, "source": "fallback-bps"},
    "sawi":         {"price": 8000,  "min": 5000,  "max": 12000, "source": "fallback-bps"},
    "paprika":      {"price": 45000, "min": 30000, "max": 65000, "source": "fallback-bps"},
    # Buah
    "strawberry":   {"price": 55000, "min": 35000, "max": 80000, "source": "fallback-bps"},
    "melon":        {"price": 15000, "min": 10000, "max": 22000, "source": "fallback-bps"},
    "semangka":     {"price": 8000,  "min": 5000,  "max": 12000, "source": "fallback-bps"},
    # Pangan pokok
    "padi":         {"price": 6500,  "min": 5500,  "max": 7500,  "source": "fallback-bps"},
    "jagung":       {"price": 5500,  "min": 4500,  "max": 6500,  "source": "fallback-bps"},
    "kedelai":      {"price": 12000, "min": 9000,  "max": 15000, "source": "fallback-bps"},
    # Rempah
    "jahe":         {"price": 25000, "min": 15000, "max": 40000, "source": "fallback-bps"},
    "kunyit":       {"price": 18000, "min": 12000, "max": 28000, "source": "fallback-bps"},
    # Default
    "_default":     {"price": 10000, "min": 5000,  "max": 20000, "source": "fallback-default"},
}

# Mapping nama crop di tumbal.py → key di FALLBACK_PRICES
_CROP_ALIAS: Dict[str, str] = {
    "tomato":       "tomat",
    "lettuce":      "selada",
    "chili":        "cabai_merah",
    "chili_pepper": "cabai_rawit",
    "cucumber":     "timun",
    "potato":       "kentang",
    "carrot":       "wortel",
    "rice":         "padi",
    "corn":         "jagung",
    "soybean":      "kedelai",
    "spinach":      "bayam",
    "pepper":       "paprika",
    "broccoli":     "brokoli",
    "eggplant":     "terong",
    "ginger":       "jahe",
    "turmeric":     "kunyit",
    "onion":        "bawang_merah",
    "garlic":       "bawang_putih",
    "water_spinach":"kangkung",
    "mustard_green":"sawi",
}


# ══════════════════════════════════════════════════════════════════════════════
# PIHPS BANK INDONESIA (harga pangan strategis)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_pihps(crop_id: str) -> Optional[float]:
    """Coba ambil harga dari PIHPS Bank Indonesia.

    PIHPS API tidak resmi/publik. Ini attempt best-effort.
    Jika gagal, return None → fallback ke hardcoded.
    """
    # PIHPS BI endpoint (web scraping target — non-official API)
    # https://www.bi.go.id/hargapangan/TabelHarga/PasarTradisionalKomoditas
    # Karena tidak ada API resmi yang stabil, kita skip untuk sekarang
    # dan langsung pakai fallback. Di Fase 4 bisa ditambahkan scraping.
    return None


# ══════════════════════════════════════════════════════════════════════════════
# LIVE USD/IDR EXCHANGE RATE (buat konversi harga World Bank)
# ══════════════════════════════════════════════════════════════════════════════

_FX_FALLBACK_IDR_PER_USD = 16000.0  # dipakai kalau live rate gagal diambil
_FX_CACHE: Dict[str, float] = {"rate": _FX_FALLBACK_IDR_PER_USD, "expire_ts": 0.0}


def _fetch_usd_idr_rate() -> float:
    """Kurs USD->IDR live dari frankfurter.app (gratis, tanpa API key, data resmi
    dari European Central Bank). Di-cache pakai _CACHE_TTL yang sama kayak harga
    komoditas; kalau fetch gagal, pakai rate terakhir yang berhasil (atau fallback
    hardcoded kalau belum pernah berhasil sama sekali)."""
    now = time.time()
    if now < _FX_CACHE["expire_ts"]:
        return _FX_CACHE["rate"]
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": "USD", "to": "IDR"},
            timeout=8,
            headers={"User-Agent": "AgriTwin/1.0"},
        )
        if r.ok:
            rate = float(r.json()["rates"]["IDR"])
            if rate > 0:
                _FX_CACHE["rate"] = rate
                _FX_CACHE["expire_ts"] = now + _CACHE_TTL
                return rate
    except Exception:
        pass
    # Fetch gagal: pakai rate terakhir yang pernah berhasil (walau cache-nya expired),
    # bukan langsung jatuh ke hardcoded, biar gak "downgrade" akurasi tanpa perlu.
    return _FX_CACHE["rate"]


# ══════════════════════════════════════════════════════════════════════════════
# WORLD BANK COMMODITY PRICES (global reference)
# ══════════════════════════════════════════════════════════════════════════════

# World Bank does not expose commodity prices ("Pink Sheet") through its
# country-indicator REST API (that's WDI/GEM-only data — GDP, poverty, trade,
# etc). The DPRICE.* codes previously used here don't exist in WB's indicator
# catalog, so this always silently returned None. The actual Pink Sheet is
# published monthly as an Excel workbook; column name + the unit it's quoted
# in is what identifies each commodity there.
_WB_PINKSHEET_URL = "https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx"

# crop_id -> (column header text in the "Monthly Prices" sheet, unit)
# "kentang" (potato) has no entry: WB's Pink Sheet doesn't track potatoes at
# all, so it's left to fall straight through to the hardcoded BPS fallback.
_WB_COMMODITY_MAP: Dict[str, Tuple[str, str]] = {
    "padi":    ("Rice, Thai 5%", "$/mt"),
    "jagung":  ("Maize", "$/mt"),
    "kedelai": ("Soybeans", "$/mt"),
    "gula":    ("Sugar, world", "$/kg"),
}

_WB_PINKSHEET_CACHE_TTL = 24 * 3600  # workbook is only published monthly
_WB_PINKSHEET_CACHE: Dict[str, object] = {"rows": None, "expire_ts": 0.0}


def _load_wb_pinksheet_rows() -> Optional[list]:
    """Download + parse the Pink Sheet workbook once, cached 24h (it's a
    ~750KB file republished about once a month, no point refetching per crop
    or per call)."""
    now = time.time()
    if _WB_PINKSHEET_CACHE["rows"] is not None and now < _WB_PINKSHEET_CACHE["expire_ts"]:
        return _WB_PINKSHEET_CACHE["rows"]
    try:
        r = requests.get(_WB_PINKSHEET_URL, timeout=20, headers={"User-Agent": "AgriTwin/1.0"})
        r.raise_for_status()
        wb = openpyxl.load_workbook(io.BytesIO(r.content), data_only=True)
        ws = wb["Monthly Prices"]
        headers = [c.value for c in ws[5]]
        rows = [[c.value for c in row] for row in ws.iter_rows(min_row=7)]
        _WB_PINKSHEET_CACHE["rows"] = (headers, rows)
        _WB_PINKSHEET_CACHE["expire_ts"] = now + _WB_PINKSHEET_CACHE_TTL
        return (headers, rows)
    except Exception:
        return _WB_PINKSHEET_CACHE["rows"]  # stale cache beats no data


def _fetch_world_bank(crop_id: str) -> Optional[float]:
    """Ambil harga komoditas dari World Bank Pink Sheet (monthly Excel).

    Returns harga dalam IDR/kg (converted dari USD/ton atau USD/kg).
    """
    mapping = _WB_COMMODITY_MAP.get(crop_id)
    if not mapping:
        return None
    col_name, unit = mapping

    parsed = _load_wb_pinksheet_rows()
    if not parsed:
        return None
    headers, rows = parsed

    normalized = [(h.strip() if isinstance(h, str) else h) for h in headers]
    try:
        col_idx = normalized.index(col_name)
    except ValueError:
        return None

    # Walk backward from the most recent month until a non-empty value is found
    for row in reversed(rows):
        val = row[col_idx] if col_idx < len(row) else None
        if isinstance(val, (int, float)):
            idr_per_usd = _fetch_usd_idr_rate()
            if unit == "$/kg":
                idr_per_kg = float(val) * idr_per_usd
            else:  # $/mt
                idr_per_kg = float(val) * idr_per_usd / 1000.0
            return round(idr_per_kg)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — fungsi utama yang dipakai tumbal.py
# ══════════════════════════════════════════════════════════════════════════════

def get_price(crop_id: str, region: str = "") -> Dict:
    """Ambil harga terbaru untuk crop tertentu.

    Returns dict: {"price": float, "min": float, "max": float,
                   "source": str, "currency": "IDR"}

    Priority chain:
      1. In-memory/Supabase cache (TTL 6 jam)
      2. PIHPS Bank Indonesia (real, jika tersedia)
      3. World Bank (global commodities)
      4. Hardcoded fallback (BPS Q1 2026)
    """
    # Normalize crop name
    key = _normalize_crop(crop_id)

    # Check cache
    cache_key = f"price:{key}:{region}"
    cached = _PRICE_CACHE.get(cache_key)
    if cached and cached[0] > time.time():
        fb = FALLBACK_PRICES.get(key, FALLBACK_PRICES["_default"])
        return {"price": cached[1], "min": fb["min"], "max": fb["max"],
                "source": "cached", "currency": "IDR"}

    # Try PIHPS
    pihps_price = _fetch_pihps(key)
    if pihps_price:
        _PRICE_CACHE[cache_key] = (time.time() + _CACHE_TTL, pihps_price)
        _try_save_supabase(key, pihps_price, region, "pihps_bi")
        fb = FALLBACK_PRICES.get(key, FALLBACK_PRICES["_default"])
        return {"price": pihps_price, "min": fb["min"], "max": fb["max"],
                "source": "pihps_bi", "currency": "IDR"}

    # Try World Bank
    wb_price = _fetch_world_bank(key)
    if wb_price:
        _PRICE_CACHE[cache_key] = (time.time() + _CACHE_TTL, wb_price)
        _try_save_supabase(key, wb_price, region, "world_bank")
        fb = FALLBACK_PRICES.get(key, FALLBACK_PRICES["_default"])
        return {"price": wb_price, "min": fb["min"], "max": fb["max"],
                "source": "world_bank", "currency": "IDR"}

    # Hardcoded fallback
    fb = FALLBACK_PRICES.get(key, FALLBACK_PRICES["_default"])
    _PRICE_CACHE[cache_key] = (time.time() + _CACHE_TTL, fb["price"])
    return {"price": fb["price"], "min": fb["min"], "max": fb["max"],
            "source": fb["source"], "currency": "IDR"}


def get_all_prices() -> Dict[str, Dict]:
    """Ambil semua harga yang tersedia. Returns {crop_id: {price, source, ...}}."""
    result = {}
    for crop_id in FALLBACK_PRICES:
        if crop_id == "_default":
            continue
        result[crop_id] = get_price(crop_id)
    return result


def _normalize_crop(crop_id: str) -> str:
    """Normalize crop name ke key standar."""
    key = crop_id.lower().strip().replace(" ", "_")
    return _CROP_ALIAS.get(key, key)


def _try_save_supabase(crop_id: str, price: float,
                        region: str, source: str):
    """Best-effort save ke Supabase (non-blocking)."""
    try:
        from db.supabase_client import save_market_price
        save_market_price(crop_id, price, region=region, source=source)
    except Exception:
        pass
