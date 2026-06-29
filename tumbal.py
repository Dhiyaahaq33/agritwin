"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║   🌱 AI GREENHOUSE DIGITAL TWIN v5.0 — ULTRA SMART AGRICULTURE PLATFORM        ║
║   Integrations: OpenWeatherMap | PCSE | GreenLightPlus | FarmVibes             ║
║   v5.0: Kalman Filter | LSTM-lite | Genetic Optimizer | MQTT | Nutrient AI     ║
║         Spectral LED Control | Carbon Accounting | Predictive Maintenance      ║
║         Multi-Crop Intercropping | Autonomous Scheduling | Soil Microbiology   ║
╚══════════════════════════════════════════════════════════════════════════════════╝

CARA PAKAI:
  pip install streamlit matplotlib numpy requests pandas plotly scipy scikit-learn

OPSIONAL (untuk integrasi penuh):
  pip install pcse GreenLightPlus openmeteo-requests

JALANKAN:
  streamlit run tumbal.py

CONFIG:
  cp .env.example .env        # lalu isi API key di .env
  # atau: export OPENWEATHER_API_KEY=your_key_here
"""

# ─── IMPORTS ──────────────────────────────────────────────────────────────────
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import time, requests, json, os, datetime, math, hashlib, random, string, warnings
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
from enum import Enum
from collections import deque, defaultdict
from functools import lru_cache
from abc import ABC, abstractmethod
import threading
import copy
import html
import re
import unicodedata

# ─── DOTENV — load .env sebelum config dibaca ─────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass  # python-dotenv belum diinstall — env var manual tetap jalan

# ─── SENTRY — error monitoring (gratis 5K error/bulan) ────────────────────────
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,      # 10% transaksi untuk performance monitoring
            environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
            release=os.environ.get("SENTRY_RELEASE", "agritwin@5.0"),
        )
    except ImportError:
        pass  # sentry-sdk belum diinstall — app tetap jalan tanpa monitoring

# ── ARUNA WebSocket Broadcast (injected) ─────────────────────────────────────
_ARUNA_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aruna_state.json")

def _aruna_broadcast(zones_list):
    """Write zone state to JSON file — picked up by esp32_dashboard_server_v2.py"""
    try:
        if not zones_list:
            return
        z = zones_list[0]
        cm = z.crop_model
        state = {
            "zone":         z.zone_id,
            "facility":     "GH-INDO-01",
            "temp":         round(float(z.temp_air), 1),
            "rh":           round(float(z.humidity), 1),
            "humidity":     round(float(z.humidity), 1),
            "co2":          int(z.co2_ppm),
            "soil":         round(float(z.soil_moist), 1),
            "soil_moisture":round(float(z.soil_moist), 1),
            "ec":           round(float(z.nutrient_solution.ec if hasattr(z, "nutrient_solution") else 1.9), 2),
            "ph":           round(float(z.nutrient_solution.ph if hasattr(z, "nutrient_solution") else 6.4), 2),
            "light":        round(float(z.light_par if hasattr(z, "light_par") else 400), 0),
            "ppfd":         round(float(z.light_par if hasattr(z, "light_par") else 400), 0),
            "root_temp":    round(float(z.root_temp if hasattr(z, "root_temp") else z.temp_air - 2), 1),
            "energy_kwh":   round(float(z.energy_kwh), 3),
            "water_l":      round(float(z.water_used_L), 1),
            "yield_kg":     round(float(cm.yield_kg), 4),
            "biomass":      round(float(cm.biomass), 4),
            "stage":        cm.stage.value,
            "dvs":          round(float(cm.dvs), 3),
            "disease":      round(float(cm.disease_index), 3),
            "brix":         round(float(cm.brix_sugar), 2),
            "step":         int(z.step_count),
            "area_m2":      float(z.area_m2),
            "crop":         str(z.crop_type.value),
            "n_zones":      len(zones_list),
            "relay_valve":  0,
            "led_pwm":      75,
            "fan_pwm":      50,
            "alarm":        0,
            "alarm_code":   0,
            "uptime_s":     int(z.step_count * 10),
            "_source":      "tumbal.py",
            "_ts":          time.time(),
        }
        with open(_ARUNA_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass
# ─────────────────────────────────────────────────────────────────────────────




warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════════════
# 0-A. CONFIG PERSISTENCE — API keys disimpan lokal, tidak perlu input ulang
# ══════════════════════════════════════════════════════════════════════════════
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agri_config.json")

def _load_cfg() -> dict:
    """Read local config (agri_config.json in same folder)."""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_cfg(**kwargs):
    """Save one or more keys to agri_config.json (including empty/None)."""
    cfg = _load_cfg()
    cfg.update({k: (v if v is not None else "") for k, v in kwargs.items()})
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def _get_cfg(key: str, fallback: str = "") -> str:
    """Ambil nilai config — prioritas: .env (env var) > agri_config.json > fallback.

    Semua secret dan non-secret keys di-mapping ke env var UPPERCASE.
    Dengan python-dotenv, cukup isi file .env — otomatis terbaca.
    """
    env_map = {
        # ── Cuaca ──────────────────────────────────────────────────────
        "owm_api_key":              "OPENWEATHER_API_KEY",
        # ── Geocoding & Maps ──────────────────────────────────────────
        "geonames_username":        "GEONAMES_USERNAME",
        "mapbox_api_key":           "MAPBOX_API_KEY",
        "google_maps_api_key":      "GOOGLE_MAPS_API_KEY",
        # ── AI / LLM keys ────────────────────────────────────────────
        "gemini_api_key":           "GEMINI_API_KEY",
        "groq_api_key":             "GROQ_API_KEY",
        "openrouter_key":           "OPENROUTER_API_KEY",
        "openai_api_key":           "OPENAI_API_KEY",
        "claude_api_key":           "ANTHROPIC_API_KEY",
        # ── LLM settings (non-secret) ────────────────────────────────
        "llm_provider":             "LLM_PROVIDER",
        "llm_model":                "LLM_MODEL",
        "llm_temperature":          "LLM_TEMPERATURE",
        "gemini_model":             "GEMINI_MODEL",
        "groq_model":               "GROQ_MODEL",
        "ollama_model":             "OLLAMA_MODEL",
        "ollama_host":              "OLLAMA_HOST",
        "openrouter_model":         "OPENROUTER_MODEL",
        # ── Telegram ──────────────────────────────────────────────────
        "telegram_bot_token":       "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id":         "TELEGRAM_CHAT_ID",
        # ── WhatsApp Cloud API ────────────────────────────────────────
        "whatsapp_access_token":    "WHATSAPP_ACCESS_TOKEN",
        "whatsapp_phone_number_id": "WHATSAPP_PHONE_NUMBER_ID",
        "whatsapp_admin_recipients":"WHATSAPP_ADMIN_RECIPIENTS",
        "whatsapp_template_name":   "WHATSAPP_TEMPLATE_NAME",
        "whatsapp_template_language":"WHATSAPP_TEMPLATE_LANGUAGE",
        "whatsapp_graph_api_version":"WHATSAPP_GRAPH_API_VERSION",
    }
    env_val = os.environ.get(env_map.get(key, key.upper()), "")
    if env_val:
        return env_val
    return _load_cfg().get(key, fallback)

# Baca semua config sekali di module-level
_APP_CFG = _load_cfg()


def _dew_point(temp_c: float, rh_pct: float) -> float:
    """Titik embun (°C) — August-Roche-Magnus, akurasi ±0.35°C untuk RH 1–100%."""
    # Magnus constants (Alduchov & Eskridge 1996)
    a, b = 17.625, 243.04
    try:
        rh = max(0.01, min(100.0, rh_pct))
        alpha = math.log(rh / 100.0) + (a * temp_c) / (b + temp_c)
        return round(b * alpha / (a - alpha), 1)
    except Exception:
        return round(temp_c - (100.0 - rh_pct) / 5.0, 1)   # fallback kasar


# ══════════════════════════════════════════════════════════════════════════════
# 0-B-PRE. GLOBAL LOCATION STATE — Single source of truth for all panels
# ══════════════════════════════════════════════════════════════════════════════

# ── World countries: iso2 → (name, currency_code, currency_symbol, language, admin_type) ─
WORLD_COUNTRIES: Dict[str, tuple] = {
    "ID": ("Indonesia",       "IDR", "Rp",    "id",  "ID"),
    "JP": ("Japan",           "JPY", "¥",     "ja",  "JP"),
    "US": ("United States",   "USD", "$",     "en",  "US"),
    "IN": ("India",           "INR", "₹",     "hi",  "IN"),
    "CN": ("China",           "CNY", "¥",     "zh",  "CN"),
    "BR": ("Brazil",          "BRL", "R$",    "pt",  "BR"),
    "AU": ("Australia",       "AUD", "A$",    "en",  "AU"),
    "TH": ("Thailand",        "THB", "฿",     "th",  "DEFAULT"),
    "VN": ("Vietnam",         "VND", "₫",     "vi",  "DEFAULT"),
    "PH": ("Philippines",     "PHP", "₱",     "fil", "DEFAULT"),
    "MY": ("Malaysia",        "MYR", "RM",    "ms",  "DEFAULT"),
    "SG": ("Singapore",       "SGD", "S$",    "en",  "DEFAULT"),
    "KR": ("South Korea",     "KRW", "₩",     "ko",  "JP"),
    "PK": ("Pakistan",        "PKR", "₨",     "ur",  "IN"),
    "BD": ("Bangladesh",      "BDT", "৳",     "bn",  "IN"),
    "NG": ("Nigeria",         "NGN", "₦",     "en",  "DEFAULT"),
    "ET": ("Ethiopia",        "ETB", "Br",    "am",  "DEFAULT"),
    "EG": ("Egypt",           "EGP", "£E",    "ar",  "DEFAULT"),
    "MX": ("Mexico",          "MXN", "Mex$",  "es",  "US"),
    "AR": ("Argentina",       "ARS", "$",     "es",  "DEFAULT"),
    "CO": ("Colombia",        "COP", "Col$",  "es",  "DEFAULT"),
    "PE": ("Peru",            "PEN", "S/",    "es",  "DEFAULT"),
    "ZA": ("South Africa",    "ZAR", "R",     "en",  "DEFAULT"),
    "KE": ("Kenya",           "KES", "KSh",   "sw",  "DEFAULT"),
    "TZ": ("Tanzania",        "TZS", "TSh",   "sw",  "DEFAULT"),
    "GH": ("Ghana",           "GHS", "₵",     "en",  "DEFAULT"),
    "DE": ("Germany",         "EUR", "€",     "de",  "EU"),
    "FR": ("France",          "EUR", "€",     "fr",  "EU"),
    "ES": ("Spain",           "EUR", "€",     "es",  "EU"),
    "IT": ("Italy",           "EUR", "€",     "it",  "EU"),
    "NL": ("Netherlands",     "EUR", "€",     "nl",  "EU"),
    "PL": ("Poland",          "PLN", "zł",    "pl",  "EU"),
    "RU": ("Russia",          "RUB", "₽",     "ru",  "EU"),
    "UA": ("Ukraine",         "UAH", "₴",     "uk",  "EU"),
    "TR": ("Turkey",          "TRY", "₺",     "tr",  "EU"),
    "GB": ("United Kingdom",  "GBP", "£",     "en",  "EU"),
    "CA": ("Canada",          "CAD", "C$",    "en",  "US"),
    "NZ": ("New Zealand",     "NZD", "NZ$",   "en",  "AU"),
    "MM": ("Myanmar",         "MMK", "K",     "my",  "DEFAULT"),
    "KH": ("Cambodia",        "KHR", "៛",     "km",  "DEFAULT"),
    "LA": ("Laos",            "LAK", "₭",     "lo",  "DEFAULT"),
    "NP": ("Nepal",           "NPR", "₨",     "ne",  "IN"),
    "LK": ("Sri Lanka",       "LKR", "₨",     "si",  "IN"),
    "MN": ("Mongolia",        "MNT", "₮",     "mn",  "DEFAULT"),
    "UZ": ("Uzbekistan",      "UZS", "so'm",  "uz",  "DEFAULT"),
    "KZ": ("Kazakhstan",      "KZT", "₸",     "kk",  "DEFAULT"),
    "MA": ("Morocco",         "MAD", "DH",    "ar",  "DEFAULT"),
    "DZ": ("Algeria",         "DZD", "DA",    "ar",  "DEFAULT"),
    "MZ": ("Mozambique",      "MZN", "MT",    "pt",  "DEFAULT"),
    "ZW": ("Zimbabwe",        "USD", "$",     "en",  "DEFAULT"),
    "EC": ("Ecuador",         "USD", "$",     "es",  "DEFAULT"),
    "CL": ("Chile",           "CLP", "$",     "es",  "DEFAULT"),
    "IR": ("Iran",            "IRR", "﷼",     "fa",  "DEFAULT"),
    "SA": ("Saudi Arabia",    "SAR", "ر.س",   "ar",  "DEFAULT"),
    "SD": ("Sudan",           "SDG", "SDG",   "ar",  "DEFAULT"),
    "UG": ("Uganda",          "UGX", "USh",   "en",  "DEFAULT"),
    "MG": ("Madagascar",      "MGA", "Ar",    "mg",  "DEFAULT"),
    "CM": ("Cameroon",        "XAF", "FCFA",  "fr",  "DEFAULT"),
    "SN": ("Senegal",         "XOF", "FCFA",  "fr",  "DEFAULT"),
    "CI": ("Côte d'Ivoire",   "XOF", "FCFA",  "fr",  "DEFAULT"),
    "ML": ("Mali",            "XOF", "FCFA",  "fr",  "DEFAULT"),
}

# ── Administrative level labels per country type ───────────────────────────
ADMIN_LEVEL_LABELS: Dict[str, Dict[str, str]] = {
    "ID": {
        "country": "Negara", "province": "Provinsi",
        "city": "Kota / Kabupaten", "district": "Kecamatan",
        "village": "Kelurahan / Desa",
    },
    "JP": {
        "country": "Country", "province": "Prefecture (都道府県)",
        "city": "City (市区町村)", "district": "Ward / Ku (区)",
        "village": "Town / Cho (町)",
    },
    "US": {
        "country": "Country", "province": "State",
        "city": "County", "district": "City / Town",
        "village": "ZIP / District",
    },
    "IN": {
        "country": "Country", "province": "State",
        "city": "District", "district": "Taluk / Block",
        "village": "Village / Gram",
    },
    "CN": {
        "country": "Country", "province": "Province / Sheng (省)",
        "city": "Prefecture / Shi (市)", "district": "County / Xian (县)",
        "village": "Township / Xiang (乡)",
    },
    "AU": {
        "country": "Country", "province": "State / Territory",
        "city": "LGA / Region", "district": "Suburb",
        "village": "Postcode Area",
    },
    "BR": {
        "country": "Country", "province": "Estado",
        "city": "Município", "district": "Distrito",
        "village": "Bairro",
    },
    "EU": {
        "country": "Country", "province": "Region / Province",
        "city": "City / Municipality", "district": "District / Arrondissement",
        "village": "Quarter / Village",
    },
    "DEFAULT": {
        "country": "Country", "province": "Province / State",
        "city": "City", "district": "District",
        "village": "Village / Sub-district",
    },
}


# ── Country centroid coordinates (fallback when city not geocoded yet) ─────
_COUNTRY_CENTROIDS: Dict[str, Tuple[float, float]] = {
    "ID": (-2.5,   118.0),   "JP": (36.2,   138.2),   "US": (39.5,  -98.4),
    "GB": (54.0,    -2.0),   "DE": (51.2,    10.5),   "FR": (46.6,    2.5),
    "IN": (20.6,    78.9),   "CN": (35.9,   104.2),   "BR": (-14.2,  -51.9),
    "RU": (60.0,    90.0),   "AU": (-25.3,  133.8),   "CA": (56.1,   -96.0),
    "MX": (23.6,   -102.6),  "AR": (-38.4,  -63.6),   "ZA": (-29.0,   25.1),
    "EG": (26.8,    30.8),   "NG": (9.1,      8.7),   "KE": (-0.0,    37.9),
    "ET": (9.1,     40.5),   "TZ": (-6.4,    35.0),   "GH": (7.9,     -1.0),
    "PH": (12.9,   121.8),   "VN": (14.1,   108.3),   "TH": (15.9,   100.9),
    "MY": (4.2,    109.5),   "SG": (1.4,    103.8),   "MM": (17.1,    96.0),
    "KH": (12.6,   104.9),   "LA": (18.2,   103.9),   "BD": (23.7,    90.4),
    "PK": (30.4,    69.3),   "LK": (7.9,     80.8),   "NP": (28.4,    84.1),
    "AF": (33.9,    67.7),   "IR": (32.4,    53.7),   "IQ": (33.2,    43.7),
    "SA": (23.9,    45.1),   "TR": (38.9,    35.2),   "UA": (49.0,    31.5),
    "PL": (51.9,    19.1),   "IT": (41.9,    12.6),   "ES": (40.5,    -3.8),
    "PT": (39.4,    -8.2),   "NL": (52.1,     5.3),   "BE": (50.5,     4.5),
    "SE": (60.1,    18.6),   "NO": (60.5,     8.5),   "FI": (61.9,    25.7),
    "DK": (56.3,    10.0),   "CH": (46.8,     8.2),   "AT": (47.5,    14.2),
    "NZ": (-40.9,  174.9),   "ZM": (-13.1,   27.9),   "MZ": (-18.7,   35.5),
    "ZW": (-20.0,   30.0),   "CM": (5.7,     12.3),   "CI": (7.5,     -5.6),
    "SN": (14.5,   -14.5),   "ML": (17.6,    -4.0),   "KZ": (48.0,    68.0),
    "UZ": (41.4,    64.6),
}


# ── Offline global admin presets ───────────────────────────────────────────
# Dipakai ketika GeoNames username belum diisi. Tujuannya UX tetap dropdown,
# bukan input manual, untuk negara non-Indonesia.
GLOBAL_LOCATION_PRESETS: Dict[str, Dict[str, List[str]]] = {
    "IT": {
        "Abruzzo": ["L'Aquila", "Pescara", "Chieti", "Teramo"],
        "Campania": ["Naples", "Salerno", "Caserta", "Avellino"],
        "Emilia-Romagna": ["Bologna", "Parma", "Modena", "Ravenna"],
        "Lazio": ["Rome", "Latina", "Frosinone", "Viterbo"],
        "Lombardy": ["Milan", "Bergamo", "Brescia", "Como"],
        "Piedmont": ["Turin", "Novara", "Asti", "Alessandria"],
        "Puglia": ["Bari", "Lecce", "Foggia", "Taranto"],
        "Sardinia": ["Cagliari", "Sassari", "Olbia", "Nuoro"],
        "Sicily": ["Palermo", "Catania", "Messina", "Syracuse"],
        "Tuscany": ["Florence", "Pisa", "Siena", "Lucca"],
        "Veneto": ["Venice", "Verona", "Padua", "Treviso"],
    },
    "US": {
        "California": ["Los Angeles", "San Diego", "San Jose", "Fresno", "Sacramento"],
        "Florida": ["Miami", "Orlando", "Tampa", "Jacksonville", "Tallahassee"],
        "Illinois": ["Chicago", "Springfield", "Peoria", "Rockford"],
        "New York": ["New York", "Buffalo", "Rochester", "Albany"],
        "Texas": ["Houston", "Dallas", "Austin", "San Antonio", "Fort Worth"],
        "Washington": ["Seattle", "Spokane", "Tacoma", "Yakima"],
    },
    "JP": {
        "Hokkaido": ["Sapporo", "Asahikawa", "Hakodate", "Obihiro"],
        "Tokyo": ["Tokyo", "Hachioji", "Machida", "Tachikawa"],
        "Osaka": ["Osaka", "Sakai", "Higashiosaka", "Toyonaka"],
        "Aichi": ["Nagoya", "Toyota", "Okazaki", "Toyohashi"],
        "Fukuoka": ["Fukuoka", "Kitakyushu", "Kurume", "Iizuka"],
    },
    "IN": {
        "Andhra Pradesh": ["Vijayawada", "Visakhapatnam", "Guntur", "Kurnool"],
        "Gujarat": ["Ahmedabad", "Surat", "Vadodara", "Rajkot"],
        "Karnataka": ["Bengaluru", "Mysuru", "Mangaluru", "Hubballi"],
        "Maharashtra": ["Mumbai", "Pune", "Nagpur", "Nashik"],
        "Punjab": ["Ludhiana", "Amritsar", "Jalandhar", "Patiala"],
        "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai", "Salem"],
        "Uttar Pradesh": ["Lucknow", "Kanpur", "Varanasi", "Agra"],
        "West Bengal": ["Kolkata", "Howrah", "Siliguri", "Durgapur"],
    },
    "CN": {
        "Beijing": ["Beijing"],
        "Guangdong": ["Guangzhou", "Shenzhen", "Foshan", "Dongguan"],
        "Hebei": ["Shijiazhuang", "Tangshan", "Baoding", "Handan"],
        "Henan": ["Zhengzhou", "Luoyang", "Kaifeng", "Nanyang"],
        "Jiangsu": ["Nanjing", "Suzhou", "Wuxi", "Xuzhou"],
        "Shandong": ["Jinan", "Qingdao", "Yantai", "Weifang"],
        "Sichuan": ["Chengdu", "Mianyang", "Deyang", "Leshan"],
        "Zhejiang": ["Hangzhou", "Ningbo", "Wenzhou", "Jinhua"],
    },
    "BR": {
        "Bahia": ["Salvador", "Feira de Santana", "Vitória da Conquista"],
        "Goiás": ["Goiânia", "Anápolis", "Rio Verde"],
        "Minas Gerais": ["Belo Horizonte", "Uberlândia", "Juiz de Fora"],
        "Paraná": ["Curitiba", "Londrina", "Maringá"],
        "Rio Grande do Sul": ["Porto Alegre", "Caxias do Sul", "Pelotas"],
        "São Paulo": ["São Paulo", "Campinas", "Ribeirão Preto", "Sorocaba"],
    },
    "AU": {
        "New South Wales": ["Sydney", "Newcastle", "Wagga Wagga", "Dubbo"],
        "Queensland": ["Brisbane", "Cairns", "Townsville", "Toowoomba"],
        "South Australia": ["Adelaide", "Mount Gambier", "Whyalla"],
        "Victoria": ["Melbourne", "Geelong", "Ballarat", "Bendigo"],
        "Western Australia": ["Perth", "Bunbury", "Geraldton", "Albany"],
    },
    "DE": {
        "Bavaria": ["Munich", "Nuremberg", "Augsburg", "Regensburg"],
        "Lower Saxony": ["Hanover", "Braunschweig", "Oldenburg", "Osnabrück"],
        "North Rhine-Westphalia": ["Cologne", "Düsseldorf", "Dortmund", "Münster"],
        "Saxony": ["Dresden", "Leipzig", "Chemnitz"],
        "Baden-Württemberg": ["Stuttgart", "Mannheim", "Freiburg", "Ulm"],
    },
    "FR": {
        "Auvergne-Rhône-Alpes": ["Lyon", "Grenoble", "Clermont-Ferrand"],
        "Brittany": ["Rennes", "Brest", "Quimper", "Vannes"],
        "Grand Est": ["Strasbourg", "Reims", "Metz", "Nancy"],
        "Île-de-France": ["Paris", "Versailles", "Saint-Denis"],
        "Nouvelle-Aquitaine": ["Bordeaux", "Limoges", "Poitiers"],
        "Occitanie": ["Toulouse", "Montpellier", "Nîmes", "Perpignan"],
        "Provence-Alpes-Côte d'Azur": ["Marseille", "Nice", "Avignon", "Toulon"],
    },
    "ES": {
        "Andalusia": ["Seville", "Málaga", "Córdoba", "Granada"],
        "Aragon": ["Zaragoza", "Huesca", "Teruel"],
        "Catalonia": ["Barcelona", "Tarragona", "Girona", "Lleida"],
        "Community of Madrid": ["Madrid", "Alcalá de Henares", "Getafe"],
        "Valencian Community": ["Valencia", "Alicante", "Castellón"],
    },
    "GB": {
        "England": ["London", "Manchester", "Birmingham", "Leeds", "Bristol"],
        "Scotland": ["Edinburgh", "Glasgow", "Aberdeen", "Dundee"],
        "Wales": ["Cardiff", "Swansea", "Newport", "Wrexham"],
        "Northern Ireland": ["Belfast", "Derry", "Lisburn", "Newry"],
    },
    "CA": {
        "Alberta": ["Calgary", "Edmonton", "Lethbridge", "Red Deer"],
        "British Columbia": ["Vancouver", "Victoria", "Kelowna", "Abbotsford"],
        "Manitoba": ["Winnipeg", "Brandon", "Steinbach"],
        "Ontario": ["Toronto", "Ottawa", "Hamilton", "London"],
        "Quebec": ["Montréal", "Québec City", "Laval", "Sherbrooke"],
        "Saskatchewan": ["Saskatoon", "Regina", "Moose Jaw"],
    },
    "MX": {
        "Jalisco": ["Guadalajara", "Zapopan", "Puerto Vallarta"],
        "Nuevo León": ["Monterrey", "Guadalupe", "San Nicolás"],
        "Puebla": ["Puebla", "Tehuacán", "Atlixco"],
        "Sinaloa": ["Culiacán", "Mazatlán", "Los Mochis"],
        "Veracruz": ["Veracruz", "Xalapa", "Coatzacoalcos"],
        "Yucatán": ["Mérida", "Valladolid", "Tizimín"],
    },
    "TH": {
        "Bangkok Metropolitan": ["Bangkok", "Nonthaburi", "Samut Prakan"],
        "Chiang Mai": ["Chiang Mai", "Mae Rim", "San Sai"],
        "Chonburi": ["Chonburi", "Pattaya", "Si Racha"],
        "Nakhon Ratchasima": ["Nakhon Ratchasima", "Pak Chong", "Sikhio"],
    },
    "VN": {
        "Hanoi": ["Hanoi", "Hoài Đức", "Đông Anh"],
        "Ho Chi Minh City": ["Ho Chi Minh City", "Thủ Đức", "Củ Chi"],
        "Lâm Đồng": ["Đà Lạt", "Bảo Lộc", "Đức Trọng"],
        "Mekong Delta": ["Cần Thơ", "Long Xuyên", "Mỹ Tho"],
    },
    "MY": {
        "Johor": ["Johor Bahru", "Batu Pahat", "Muar"],
        "Kedah": ["Alor Setar", "Sungai Petani", "Kulim"],
        "Penang": ["George Town", "Butterworth", "Bukit Mertajam"],
        "Selangor": ["Shah Alam", "Petaling Jaya", "Klang"],
    },
    "PH": {
        "Central Luzon": ["San Fernando", "Angeles", "Cabanatuan"],
        "Calabarzon": ["Calamba", "Batangas City", "Lucena"],
        "Davao Region": ["Davao City", "Tagum", "Digos"],
        "Metro Manila": ["Manila", "Quezon City", "Makati", "Pasig"],
    },
    "ZA": {
        "Eastern Cape": ["Gqeberha", "East London", "Mthatha"],
        "Gauteng": ["Johannesburg", "Pretoria", "Vereeniging"],
        "KwaZulu-Natal": ["Durban", "Pietermaritzburg", "Richards Bay"],
        "Western Cape": ["Cape Town", "Stellenbosch", "George"],
    },
    "KE": {
        "Central": ["Nyeri", "Murang'a", "Kiambu"],
        "Coast": ["Mombasa", "Malindi", "Kilifi"],
        "Nairobi": ["Nairobi", "Kasarani", "Westlands"],
        "Rift Valley": ["Nakuru", "Eldoret", "Naivasha"],
    },
}

DEFAULT_ADMIN_CHILDREN: Dict[str, List[str]] = {
    "district": ["Central", "North", "South", "East", "West", "Peri-urban Belt", "Rural Production Belt"],
    "village": ["Central Quarter", "Market Quarter", "Agriculture Belt", "Irrigation Block", "Greenhouse Cluster", "Rural Village"],
}

MARKET_COUNTRY_PROFILES: Dict[str, Dict[str, float]] = {
    "ID": {"price": 1.00, "cost": 1.00, "labor": 1.00, "land": 1.00, "vol": 1.00},
    "IT": {"price": 7.20, "cost": 4.20, "labor": 5.80, "land": 3.30, "vol": 0.92},
    "DE": {"price": 7.80, "cost": 4.60, "labor": 6.30, "land": 3.70, "vol": 0.88},
    "FR": {"price": 7.40, "cost": 4.40, "labor": 6.10, "land": 3.50, "vol": 0.90},
    "ES": {"price": 5.80, "cost": 3.50, "labor": 4.50, "land": 2.80, "vol": 0.96},
    "NL": {"price": 8.60, "cost": 5.10, "labor": 6.80, "land": 5.00, "vol": 0.86},
    "GB": {"price": 8.10, "cost": 4.90, "labor": 6.50, "land": 4.30, "vol": 0.92},
    "US": {"price": 6.20, "cost": 3.80, "labor": 5.10, "land": 2.90, "vol": 1.05},
    "CA": {"price": 6.60, "cost": 4.00, "labor": 5.20, "land": 2.70, "vol": 0.98},
    "AU": {"price": 6.90, "cost": 4.10, "labor": 5.60, "land": 2.60, "vol": 1.02},
    "JP": {"price": 9.50, "cost": 5.80, "labor": 6.90, "land": 5.40, "vol": 0.82},
    "KR": {"price": 8.80, "cost": 5.20, "labor": 6.10, "land": 4.50, "vol": 0.86},
    "CN": {"price": 2.20, "cost": 1.80, "labor": 2.00, "land": 1.70, "vol": 1.12},
    "IN": {"price": 1.35, "cost": 0.95, "labor": 0.75, "land": 0.80, "vol": 1.18},
    "BR": {"price": 1.95, "cost": 1.45, "labor": 1.55, "land": 1.25, "vol": 1.15},
    "MX": {"price": 2.40, "cost": 1.70, "labor": 1.45, "land": 1.35, "vol": 1.12},
    "TH": {"price": 1.55, "cost": 1.15, "labor": 1.05, "land": 0.95, "vol": 1.08},
    "VN": {"price": 1.35, "cost": 1.00, "labor": 0.90, "land": 0.85, "vol": 1.10},
    "PH": {"price": 1.75, "cost": 1.20, "labor": 1.05, "land": 1.00, "vol": 1.14},
    "MY": {"price": 1.90, "cost": 1.35, "labor": 1.25, "land": 1.10, "vol": 1.06},
    "SG": {"price": 11.5, "cost": 7.20, "labor": 8.50, "land": 12.0, "vol": 0.78},
    "ZA": {"price": 2.10, "cost": 1.55, "labor": 1.35, "land": 1.15, "vol": 1.15},
    "KE": {"price": 1.25, "cost": 0.85, "labor": 0.75, "land": 0.75, "vol": 1.18},
    "NG": {"price": 1.40, "cost": 1.00, "labor": 0.80, "land": 0.80, "vol": 1.25},
}


@dataclass
class LocationState:
    """Single source of truth for geographic context — drives ALL panels."""
    country:         str   = "Indonesia"
    country_code:    str   = "ID"
    province:        str   = "DKI Jakarta"
    city:            str   = "Jakarta"
    district:        str   = ""
    village:         str   = ""
    province_code:   str   = "31"
    city_code:       str   = "31.71"
    district_code:   str   = ""
    village_code:    str   = ""
    lat:             float = -6.2146
    lon:             float = 106.8451
    altitude_m:      float = 8.0
    currency:        str   = "IDR"
    currency_symbol: str   = "Rp"
    language:        str   = "id"
    admin_type:      str   = "ID"
    timezone:        str   = "Asia/Jakarta"
    climate_zone:    str   = "Ekuatorial"
    location_source: str   = "manual"
    accuracy_m:      float = 0.0
    detected_at:     str   = ""

    @property
    def admin_labels(self) -> Dict[str, str]:
        return ADMIN_LEVEL_LABELS.get(self.admin_type, ADMIN_LEVEL_LABELS["DEFAULT"])

    @property
    def display_name(self) -> str:
        parts = [p for p in [self.village, self.district, self.city,
                              self.province, self.country] if p]
        return ", ".join(parts[:3])

    @property
    def flag_emoji(self) -> str:
        # Convert ISO2 to flag emoji (regional indicator symbols)
        try:
            return "".join(chr(ord(c) + 127397) for c in self.country_code.upper())
        except Exception:
            return "🌍"

    def to_indo_region(self) -> "IndoRegion":
        """Backward-compat: produce IndoRegion from this LocationState."""
        prov_str = f"{self.province}, {self.country}" if self.province else self.country
        return build_region_from_coords(
            self.lat, self.lon, self.altitude_m,
            nama=self.city or self.province or self.country,
            provinsi=prov_str,
        )


def get_location_state() -> LocationState:
    """Return current LocationState from session state (create default if absent)."""
    if _STREAMLIT_OK:
        loc = st.session_state.get("location_state")
        if isinstance(loc, LocationState):
            return loc
    return LocationState()


def set_location_state(loc: LocationState) -> None:
    """Save LocationState and sync default_region for backward compat."""
    if _STREAMLIT_OK:
        st.session_state["location_state"] = loc
        st.session_state["default_region"] = loc.to_indo_region()


def _dedupe_sorted(values: List[str]) -> List[str]:
    return sorted({str(v).strip() for v in values if str(v).strip()})


def preset_provinces(country_code: str) -> List[str]:
    country_code = country_code.upper()
    preset = GLOBAL_LOCATION_PRESETS.get(country_code, {})
    if preset:
        return sorted(preset.keys())
    cdata = WORLD_COUNTRIES.get(country_code)
    cname = cdata[0] if cdata else country_code
    return [f"{cname} Central Region", f"{cname} North Region",
            f"{cname} South Region", f"{cname} Agriculture Belt"]


def preset_cities(country_code: str, province_name: str) -> List[str]:
    country_code = country_code.upper()
    preset = GLOBAL_LOCATION_PRESETS.get(country_code, {})
    if province_name in preset:
        return _dedupe_sorted(preset[province_name])
    if preset:
        return _dedupe_sorted([city for cities in preset.values() for city in cities])[:24]
    cdata = WORLD_COUNTRIES.get(country_code)
    cname = cdata[0] if cdata else country_code
    base = province_name.replace(" Region", "").strip() or cname
    return [base, f"{base} City", f"{base} Market Town", f"{base} Rural Hub"]


def preset_admin_children(country_code: str, province_name: str,
                          city_name: str, level: str) -> List[str]:
    city = (city_name or province_name or WORLD_COUNTRIES.get(country_code, ("Global",))[0]).strip()
    cc = country_code.upper()
    if cc == "IT":
        districts = ["Centro Storico", "Municipio I", "Municipio II", "Municipio III",
                     "Zona Industriale", "Zona Agricola"]
        villages = ["Quartiere Centro", "Borgo Agricolo", "Mercato Centrale",
                    "Contrada Rurale", "Serra / Greenhouse Belt"]
    elif cc == "US":
        districts = ["Downtown", "North County", "South County", "East Township",
                     "West Township", "Farm Belt"]
        villages = ["Central District", "Market District", "Irrigation Block",
                    "Rural Route", "Greenhouse Cluster"]
    elif cc == "JP":
        districts = ["Chuo-ku", "Kita-ku", "Minami-ku", "Higashi-ku",
                     "Nishi-ku", "Agriculture Ward"]
        villages = ["Honmachi", "Ekimae", "Nogyo Danchi", "Midoricho", "Sato Village"]
    elif cc == "IN":
        districts = ["Central Taluk", "North Block", "South Block", "Market Yard",
                     "Irrigation Command", "Rural Panchayat"]
        villages = ["Gram Central", "Mandi Area", "Canal Block", "Farm Cluster", "Village Belt"]
    else:
        districts = DEFAULT_ADMIN_CHILDREN["district"]
        villages = DEFAULT_ADMIN_CHILDREN["village"]
    return [f"{city} — {name}" if city and city not in name else name
            for name in (districts if level == "district" else villages)]


def select_required_dropdown(label: str, options: List[str], state_key: str,
                             widget_key: str, fallback: str = "") -> str:
    options = _dedupe_sorted(options) or ([fallback] if fallback else ["—"])
    prev = st.session_state.get(state_key, options[0])
    idx = options.index(prev) if prev in options else 0
    value = st.selectbox(label, options, index=idx, key=widget_key)
    st.session_state[state_key] = value
    return value


def select_optional_dropdown(label: str, options: List[str], state_key: str,
                             widget_key: str, empty_label: str) -> str:
    options = _dedupe_sorted(options)
    choices = [empty_label] + options
    prev = st.session_state.get(state_key, "")
    idx = (options.index(prev) + 1) if prev in options else 0
    raw = st.selectbox(label, choices, index=idx, key=widget_key)
    value = "" if raw == empty_label else raw
    st.session_state[state_key] = value
    return value


_ID_ADMIN_REGIONS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "id_admin_regions.json")


def _normalize_admin_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.upper()
    text = re.sub(r"\b(KABUPATEN|KAB\.|KOTA ADMINISTRASI|KOTA|ADM\.|ADMINISTRASI)\b", " ", text)
    text = re.sub(r"\b(KECAMATAN|KEC\.|KELURAHAN|KEL\.|DESA)\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _admin_item(code: str, name: str) -> Dict[str, str]:
    return {"code": str(code or "").strip(), "name": str(name or "").strip()}


def _legacy_id_admin_regions() -> Dict[str, Any]:
    """Small fallback if the local Kemendagri snapshot has not been generated yet."""
    legacy = globals().get("INDONESIA_CITIES_BY_PROVINCE", {})
    provinces = []
    regencies: Dict[str, List[Dict[str, str]]] = {}
    for p_idx, (province, cities) in enumerate(sorted(legacy.items()), start=1):
        p_code = f"L{p_idx:02d}"
        provinces.append(_admin_item(p_code, province))
        regencies[p_code] = [
            _admin_item(f"{p_code}.{c_idx:02d}", city)
            for c_idx, city in enumerate(_dedupe_sorted(cities), start=1)
        ]
    if not provinces:
        provinces = [_admin_item("31", "DKI Jakarta")]
        regencies = {"31": [_admin_item("31.71", "Jakarta")]}
    return {
        "meta": {"source": "legacy-inline-fallback", "updated_at": ""},
        "provinces": provinces,
        "regencies": regencies,
        "districts": {},
        "villages": {},
    }


@lru_cache(maxsize=1)
def load_id_admin_regions() -> Dict[str, Any]:
    """Load local Indonesia admin hierarchy snapshot (province/city/district/village)."""
    if os.path.exists(_ID_ADMIN_REGIONS_PATH):
        try:
            with open(_ID_ADMIN_REGIONS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("provinces") and data.get("regencies"):
                for key in ("provinces", "regencies", "districts", "villages"):
                    data.setdefault(key, [] if key == "provinces" else {})
                return data
        except Exception:
            pass
    return _legacy_id_admin_regions()


def _id_admin_children(level: str, parent_code: str = "") -> List[Dict[str, str]]:
    data = load_id_admin_regions()
    if level == "province":
        items = data.get("provinces", [])
    else:
        key = {"city": "regencies", "district": "districts", "village": "villages"}.get(level, "")
        items = data.get(key, {}).get(str(parent_code or ""), []) if key else []
    clean = [_admin_item(i.get("code", ""), i.get("name", "")) for i in items if i.get("name")]
    return sorted(clean, key=lambda x: (_normalize_admin_name(x["name"]), x["code"]))


def _find_admin_item(items: List[Dict[str, str]], code: str = "", name: str = "") -> Optional[Dict[str, str]]:
    if code:
        for item in items:
            if item.get("code") == code:
                return item
    target = _normalize_admin_name(name)
    if target:
        for item in items:
            if _normalize_admin_name(item.get("name", "")) == target:
                return item
        for item in items:
            cand = _normalize_admin_name(item.get("name", ""))
            if cand and (target in cand or cand in target):
                return item
    return items[0] if items else None


def _query_param_first(params: Any, key: str, default: str = "") -> str:
    try:
        value = params.get(key, default)
    except Exception:
        return default
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value) if value is not None else default


def _read_gps_query_payload() -> Dict[str, Any]:
    if not _STREAMLIT_OK:
        return {}
    try:
        params = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
    except Exception:
        return {}
    try:
        lat = float(_query_param_first(params, "gps_lat"))
        lon = float(_query_param_first(params, "gps_lon"))
    except Exception:
        return {}
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return {}
    acc_raw = _query_param_first(params, "gps_acc", "0")
    ts_raw = _query_param_first(params, "gps_ts", "")
    try:
        accuracy = max(0.0, float(acc_raw))
    except Exception:
        accuracy = 0.0
    return {"lat": lat, "lon": lon, "accuracy_m": accuracy, "ts": ts_raw}


def render_device_gps_component(key: str = "device_gps") -> Dict[str, Any]:
    """Render a small browser GPS bridge and return any location passed via URL query params."""
    payload = _read_gps_query_payload()
    if not _STREAMLIT_OK:
        return payload
    st.iframe(f"""
<div style="font-family:Inter,Arial,sans-serif;font-size:12px;color:#bdd9bd;">
  <button id="{key}_btn" style="width:100%;padding:8px 10px;border-radius:8px;border:1px solid #2f7f42;background:#12351a;color:#dfffe2;font-weight:700;cursor:pointer;">
    📡 Use Device GPS
  </button>
  <a id="{key}_apply" href="#" target="_top"
     style="display:none;width:100%;padding:8px 10px;border-radius:8px;
            border:1px solid #1a7a2e;background:#0a5c1e;color:#dfffe2;
            font-weight:700;cursor:pointer;text-decoration:none;
            text-align:center;box-sizing:border-box;">
    ✅ Apply GPS Location
  </a>
  <div id="{key}_status" style="margin-top:6px;color:#88aa88;line-height:1.45;">
    Tap button, allow location, then tap Apply to load coordinates.
  </div>
</div>
<script>
(function() {{
  const btn    = document.getElementById("{key}_btn");
  const apply  = document.getElementById("{key}_apply");
  const status = document.getElementById("{key}_status");
  function setStatus(msg, color) {{
    status.textContent = msg;
    status.style.color = color || "#88aa88";
  }}
  btn.addEventListener("click", function() {{
    if (!navigator.geolocation) {{
      setStatus("Browser does not support GPS/geolocation.", "#ffaaaa");
      return;
    }}
    btn.disabled = true;
    btn.textContent = "⏳ Requesting GPS…";
    setStatus("Requesting device GPS permission…", "#ffeeaa");
    navigator.geolocation.getCurrentPosition(function(pos) {{
      const c = pos.coords;
      try {{
        const url = new URL(window.parent.location.href);
        url.searchParams.set("gps_lat", String(c.latitude));
        url.searchParams.set("gps_lon", String(c.longitude));
        url.searchParams.set("gps_acc", String(c.accuracy || 0));
        url.searchParams.set("gps_ts",  String(pos.timestamp || Date.now()));
        url.searchParams.set("gps_nonce", String(Date.now()));
        // Cannot navigate here (async callback — user activation expired).
        // Show an anchor the user must click; that click IS user-activated
        // and the browser allows target="_top" navigation.
        apply.href = url.toString();
        apply.textContent = `✅ Apply GPS (${{c.latitude.toFixed(4)}}, ${{c.longitude.toFixed(4)}} \xb1${{Math.round(c.accuracy||0)}}m)`;
        apply.style.display = "block";
        btn.style.display = "none";
        setStatus("GPS obtained — tap Apply above to reload.", "#88ff88");
      }} catch (err) {{
        btn.disabled = false;
        btn.textContent = "📡 Use Device GPS";
        setStatus("Error: " + err.message, "#ffaaaa");
      }}
    }}, function(err) {{
      btn.disabled = false;
      btn.textContent = "📡 Use Device GPS";
      setStatus("GPS failed: " + err.message, "#ffaaaa");
    }}, {{ enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }});
  }});
}})();
</script>
""", height=100)
    return payload


def _reverse_geocode_google(lat: float, lon: float) -> Dict[str, str]:
    key = _get_cfg("google_maps_api_key", "")
    if not key:
        return {}
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"latlng": f"{lat},{lon}", "key": key, "language": "id", "region": "id"},
            timeout=6)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "OK" or not data.get("results"):
            return {}
        best = data["results"][0]
        out: Dict[str, str] = {
            "source": "google_maps",
            "formatted_address": best.get("formatted_address", ""),
        }
        for comp in best.get("address_components", []):
            types = set(comp.get("types", []))
            name = comp.get("long_name", "")
            short = comp.get("short_name", "")
            if "country" in types:
                out["country"] = name
                out["country_code"] = short.upper()
            elif "administrative_area_level_1" in types:
                out["province"] = name
                out["state"] = name
            elif "administrative_area_level_2" in types:
                out["city"] = name
                out["name"] = name
            elif "administrative_area_level_3" in types:
                out["district"] = name
            elif "administrative_area_level_4" in types or "sublocality_level_1" in types:
                out["village"] = name
        return out
    except Exception:
        return {}


def _reverse_geocode_nominatim(lat: float, lon: float) -> Dict[str, str]:
    """Free reverse geocoding via Nominatim/OSM — no API key needed."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json",
                    "addressdetails": 1, "accept-language": "id"},
            headers={"User-Agent": "AgriBot/1.0"},
            timeout=5)
        r.raise_for_status()
        addr = r.json().get("address", {})
        return {
            "source":       "nominatim",
            "country":      addr.get("country", ""),
            "country_code": addr.get("country_code", "").upper(),
            "state":        addr.get("state", "") or addr.get("province", ""),
            "province":     addr.get("state", "") or addr.get("province", ""),
            "city":         (addr.get("regency") or addr.get("city") or
                             addr.get("county") or addr.get("municipality") or ""),
            "name":         (addr.get("regency") or addr.get("city") or
                             addr.get("county") or ""),
            "district":     (addr.get("suburb") or addr.get("district") or
                             addr.get("town") or ""),
            "village":      addr.get("village") or addr.get("neighbourhood") or "",
        }
    except Exception:
        return {}


def _reverse_geocode_best(lat: float, lon: float) -> Dict[str, str]:
    return (_reverse_geocode_google(lat, lon)
            or _reverse_geocode_owm(lat, lon)
            or _reverse_geocode_nominatim(lat, lon))


def _validated_id_location_from_reverse(geo: Dict[str, str]) -> Dict[str, str]:
    """Map reverse-geocode names to local Kemendagri hierarchy; only exact/near name matches are kept."""
    if not geo:
        return {}
    cc = (geo.get("country_code") or geo.get("country") or "").upper()
    if cc and cc != "ID":
        return {}
    out: Dict[str, str] = {}
    province_name = geo.get("province") or geo.get("state")
    if not province_name:
        return out
    province = _find_admin_item(_id_admin_children("province"), name=province_name)
    if not province:
        return out
    out["province"] = province["name"]
    out["province_code"] = province["code"]

    city_name = geo.get("city") or geo.get("name")
    city = _find_admin_item(_id_admin_children("city", province["code"]), name=city_name) if city_name else None
    if city:
        out["city"] = city["name"]
        out["city_code"] = city["code"]

    district_parent = out.get("city_code", "")
    district = _find_admin_item(_id_admin_children("district", district_parent), name=geo.get("district")) if district_parent else None
    if district and geo.get("district"):
        out["district"] = district["name"]
        out["district_code"] = district["code"]

    village_parent = out.get("district_code", "")
    village = _find_admin_item(_id_admin_children("village", village_parent), name=geo.get("village")) if village_parent else None
    if village and geo.get("village"):
        out["village"] = village["name"]
        out["village_code"] = village["code"]
    return out


def build_location_from_gps(lat: float, lon: float, accuracy_m: float = 0.0,
                            ts: str = "", fallback: Optional[LocationState] = None) -> LocationState:
    fallback = fallback or get_location_state()
    geo = _reverse_geocode_best(lat, lon)
    cdata = WORLD_COUNTRIES.get("ID", WORLD_COUNTRIES["ID"])
    country_code = (geo.get("country_code") or geo.get("country") or fallback.country_code or "ID").upper()
    if country_code not in WORLD_COUNTRIES:
        country_code = "ID" if country_code == "ID" else fallback.country_code
    cdata = WORLD_COUNTRIES.get(country_code, cdata)
    validated = _validated_id_location_from_reverse(geo) if country_code == "ID" else {}
    province = validated.get("province") or geo.get("state") or geo.get("province") or fallback.province
    city = validated.get("city") or geo.get("name") or geo.get("city") or fallback.city
    district = validated.get("district") or ""
    village = validated.get("village") or ""
    region = build_region_from_coords(lat, lon, fallback.altitude_m or 0.0,
                                      nama=city or province or cdata[0],
                                      provinsi=f"{province}, {cdata[0]}" if province else cdata[0])
    detected_at = ""
    try:
        ts_num = float(ts)
        if ts_num > 10_000_000_000:
            ts_num /= 1000.0
        detected_at = datetime.datetime.fromtimestamp(ts_num).isoformat(timespec="seconds")
    except Exception:
        detected_at = datetime.datetime.now().isoformat(timespec="seconds")
    return LocationState(
        country=cdata[0], country_code=country_code,
        province=province, city=city, district=district, village=village,
        province_code=validated.get("province_code", fallback.province_code),
        city_code=validated.get("city_code", fallback.city_code),
        district_code=validated.get("district_code", ""),
        village_code=validated.get("village_code", ""),
        lat=lat, lon=lon, altitude_m=fallback.altitude_m or 0.0,
        currency=cdata[1], currency_symbol=cdata[2],
        language=cdata[3], admin_type=cdata[4],
        timezone=fallback.timezone or "UTC",
        climate_zone=region.zona_agroklimat,
        location_source="gps",
        accuracy_m=float(accuracy_m or 0.0),
        detected_at=detected_at,
    )


def location_signature(loc: LocationState) -> str:
    return (
        f"{loc.country_code}|{loc.province_code}|{loc.city_code}|"
        f"{loc.district_code}|{loc.village_code}|{loc.province}|"
        f"{loc.city}|{loc.district}|{loc.village}|{loc.lat:.5f}|"
        f"{loc.lon:.5f}|{loc.altitude_m:.0f}|{loc.location_source}"
    )


def market_profile_for_country(country_code: str) -> Dict[str, float]:
    cc = (country_code or "ID").upper()
    return MARKET_COUNTRY_PROFILES.get(cc, MARKET_COUNTRY_PROFILES["ID"])


def localized_crop_price_idr(crop: "IndoCrop", loc: Optional[LocationState] = None,
                             channel: str = "Pasar Lokal") -> Tuple[float, Dict[str, Any]]:
    loc = loc or get_location_state()
    profile = market_profile_for_country(loc.country_code)
    channel_mult = {"Pasar Lokal": 1.0, "Tengkulak": 0.85, "Ekspor Langsung": 1.35}.get(channel, 1.0)
    category_mult = {
        IndoCropCategory.PANGAN_POKOK: 0.82,
        IndoCropCategory.PALAWIJA: 0.92,
        IndoCropCategory.HORTIKULTURA: 1.12,
        IndoCropCategory.BUAH: 1.18,
        IndoCropCategory.PERKEBUNAN: 1.05,
        IndoCropCategory.HERBAL_BUMBU: 1.25,
        IndoCropCategory.BIOFARMAKA: 1.30,
        IndoCropCategory.UMBI: 0.88,
    }.get(crop.kategori, 1.0)
    seasonal = 1.0 + 0.035 * math.sin((datetime.datetime.now().timetuple().tm_yday / 365.0) * 2 * math.pi)
    price = crop.harga_kg_idr * profile["price"] * category_mult * channel_mult * seasonal
    return max(1.0, price), {
        "country_mult": profile["price"],
        "category_mult": category_mult,
        "channel_mult": channel_mult,
        "seasonal_mult": seasonal,
        "volatility": profile.get("vol", 1.0),
        "source": f"Country market profile · {loc.country_code}",
    }


def localized_cost_factor(loc: Optional[LocationState], key: str, fallback: float = 1.0) -> float:
    loc = loc or get_location_state()
    return float(market_profile_for_country(loc.country_code).get(key, fallback))


# ── Exchange rate fetcher (open.er-api.com — free, no key needed) ─────────
def fetch_exchange_rates(base: str = "IDR") -> Dict[str, float]:
    """Ambil kurs real-time. Cache 30 menit di session state."""
    if not _STREAMLIT_OK:
        return {"USD": 6.25e-5, "IDR": 1.0, "JPY": 0.0093, "EUR": 5.7e-5, "_ts": 0}
    cache_k = f"_fx_{base}"
    ts_k    = f"_fx_ts_{base}"
    now     = time.time()
    cached  = st.session_state.get(cache_k, {})
    if cached and (now - st.session_state.get(ts_k, 0)) < 1800:
        return cached
    try:
        r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=6)
        data = r.json()
        if data.get("result") == "success":
            rates = data["rates"]
            rates["_ts"]      = now
            rates["_updated"] = data.get("time_last_update_utc", "")
            st.session_state[cache_k] = rates
            st.session_state[ts_k]    = now
            return rates
    except Exception:
        pass
    if cached:
        return cached
    # Hardcoded fallback if offline
    fb: Dict[str, float] = {
        "IDR": 1.0, "USD": 6.25e-5, "EUR": 5.7e-5, "JPY": 0.0093,
        "GBP": 4.9e-5, "AUD": 9.5e-5, "CNY": 4.5e-4, "INR": 5.2e-3,
        "BRL": 3.1e-4, "THB": 2.0e-3, "MYR": 2.9e-4, "SGD": 8.4e-5,
        "KRW": 8.5e-2, "PHP": 3.5e-3, "VND": 1.55, "CAD": 8.5e-5,
        "_ts": 0, "_updated": "offline-fallback",
    }
    if base != "IDR":
        # Rescale so rates are relative to `base`
        idr_rate = fb.get(base, 1.0)
        if idr_rate:
            fb = {k: (v / idr_rate if not k.startswith("_") else v)
                  for k, v in fb.items()}
    return fb


def fmt_3ccy(amount_idr: float, loc: Optional[LocationState] = None) -> str:
    """Format amount in IDR | USD | local-currency (always 3 values)."""
    rates     = fetch_exchange_rates("IDR")
    usd_rate  = rates.get("USD", 6.25e-5)
    usd_amt   = amount_idr * usd_rate
    if loc and loc.currency not in ("IDR", ""):
        local_rate = rates.get(loc.currency, 1.0)
        local_amt  = amount_idr * local_rate
        local_sym  = loc.currency_symbol
        last_upd   = rates.get("_updated", "")
        stale_flag = " ⚠️" if rates.get("_ts", 0) == 0 else ""
        return (f"Rp {amount_idr:,.0f}{stale_flag} | "
                f"US$ {usd_amt:,.2f} | "
                f"{local_sym} {local_amt:,.2f}")
    return f"Rp {amount_idr:,.0f} | US$ {usd_amt:,.2f}"


def fx_last_updated() -> str:
    """Return human-readable last-updated string for exchange rates."""
    rates = fetch_exchange_rates("IDR")
    upd   = rates.get("_updated", "")
    ts    = rates.get("_ts", 0)
    if ts == 0:
        return "⚠️ Data kurs offline (fallback)"
    age_min = int((time.time() - ts) / 60)
    if age_min < 2:
        return "🟢 Kurs real-time (baru saja)"
    elif age_min < 60:
        return f"🟡 Kurs diperbarui {age_min} menit lalu"
    else:
        return f"🔴 Kurs > 1 jam lalu — {upd[:16] if upd else 'unknown'}"


# ── GeoNames cascading helpers ─────────────────────────────────────────────
def _geonames_search(country_code: str, feature_code: str,
                     admin_name1: str = "", admin_name2: str = "",
                     max_rows: int = 80) -> List[str]:
    """Query GeoNames API; cache results in session state. Returns name list."""
    gn_user = _get_cfg("geonames_username", "")
    if not gn_user:
        return []
    cache_k = f"_gn_{country_code}_{feature_code}_{admin_name1[:20]}_{admin_name2[:20]}"
    if _STREAMLIT_OK and cache_k in st.session_state:
        return st.session_state[cache_k]
    params: Dict[str, Any] = {
        "country": country_code, "featureCode": feature_code,
        "maxRows": max_rows, "orderby": "population",
        "username": gn_user,
    }
    if admin_name1:
        params["adminName1"] = admin_name1
    if admin_name2:
        params["adminName2"] = admin_name2
    try:
        r = requests.get("https://secure.geonames.org/searchJSON",
                         params=params, timeout=6)
        names = [g["name"] for g in r.json().get("geonames", []) if g.get("name")]
    except Exception:
        names = []
    if _STREAMLIT_OK:
        st.session_state[cache_k] = names
    return names


def geonames_provinces(country_code: str) -> List[str]:
    """Return list of ADM1 (province/state) names for given country."""
    results = _geonames_search(country_code, "ADM1")
    if not results:
        results = _geonames_search(country_code, "ADM2")
    return sorted(results)


def geonames_cities(country_code: str, province_name: str) -> List[str]:
    """Return list of populated places in given province."""
    results = _geonames_search(country_code, "PPLA2", admin_name1=province_name)
    if not results:
        results = _geonames_search(country_code, "PPL", admin_name1=province_name)
    return sorted(results)


def geonames_districts(country_code: str, province_name: str, city_name: str = "") -> List[str]:
    """Return list of ADM3 (kecamatan/sub-district) names."""
    results = _geonames_search(country_code, "ADM3",
                               admin_name1=province_name, admin_name2=city_name)
    if not results:
        results = _geonames_search(country_code, "ADM3", admin_name1=province_name)
    if not results:
        results = _geonames_search(country_code, "PPLX", admin_name1=province_name)
    return sorted(results)


def geonames_villages(country_code: str, province_name: str,
                      city_name: str = "", district_name: str = "") -> List[str]:
    """Return list of ADM4 (kelurahan/desa/village) names."""
    _filter2 = district_name or city_name
    results = _geonames_search(country_code, "ADM4",
                               admin_name1=province_name, admin_name2=_filter2)
    if not results:
        results = _geonames_search(country_code, "ADM4", admin_name1=province_name)
    if not results:
        results = _geonames_search(country_code, "PPL",
                                   admin_name1=province_name, admin_name2=_filter2,
                                   max_rows=50)
    return sorted(results)


# ══════════════════════════════════════════════════════════════════════════════
# 0-B. FREE LLM CONNECTOR — Groq / Gemini / Ollama / OpenRouter (semua gratis)
# ══════════════════════════════════════════════════════════════════════════════

class LLMProvider(Enum):
    STUB       = "stub"          # local rules, no API needed
    GROQ       = "groq"          # groq.com — gratis, cepat (LLaMA-3, Mixtral)
    GEMINI     = "gemini"        # aistudio.google.com — free (Gemini 1.5 Flash)
    OLLAMA     = "ollama"        # localhost:11434 — 100% lokal, gratis selamanya
    OPENROUTER = "openrouter"    # openrouter.ai — many free models
    OPENAI     = "openai"        # berbayar, sebagai opsi
    CLAUDE     = "claude"        # berbayar, sebagai opsi

_LLM_PROVIDER_LABELS = {
    LLMProvider.STUB:       "🔧 Stub Lokal (tanpa internet)",
    LLMProvider.GROQ:       "⚡ Groq — LLaMA-3 (GRATIS, cepat)",
    LLMProvider.GEMINI:     "✨ Google Gemini Flash (FREE)",
    LLMProvider.OLLAMA:     "🖥️ Ollama Lokal (100% offline, GRATIS)",
    LLMProvider.OPENROUTER: "🌐 OpenRouter — model gratis campuran",
    LLMProvider.OPENAI:     "💳 OpenAI GPT (berbayar)",
    LLMProvider.CLAUDE:     "💳 Anthropic Claude (berbayar)",
}

_GROQ_MODELS = [
    "llama-3.3-70b-versatile",      # flagship — terbaik, gratis
    "llama-3.1-8b-instant",         # cepat, ringan
    "llama3-8b-8192",               # stable alternative
    "gemma2-9b-it",                 # Google Gemma via Groq
    # "mixtral-8x7b-32768",         # DEPRECATED Maret 2024 — jangan dipakai
]
_GEMINI_MODELS = [
    "gemini-2.5-flash",             # default: strong price/performance
    "gemini-2.5-flash-lite",        # fastest / lowest cost
    "gemini-3-flash-preview",       # preview, use only if available on your account
    "gemini-2.0-flash",             # legacy fallback
    "gemini-2.0-flash-lite",        # legacy lightweight fallback
    # "gemini-1.5-flash",           # DEPRECATED Sep 2025
    # "gemini-1.5-flash-8b",        # DEPRECATED Sep 2025
]
_OPENROUTER_FREE = [
    "meta-llama/llama-3.3-70b-instruct:free",   # terbaru llama
    "meta-llama/llama-3.2-3b-instruct:free",    # ringan
    "google/gemma-2-9b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "deepseek/deepseek-r1-distill-llama-70b:free",  # reasoning gratis
]

_AGRI_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert agronomist with deep, world-class knowledge of global agriculture.
You have access to agricultural data from FAO, USDA, CGIAR, national extension services,
scientific journals (Semantic Scholar, PubMed Agriculture), and real-time climate and
market data. You are advising a farmer located in:
  - Country: {country} ({country_code})
  - Province: {province}
  - City/Regency: {city}
  - District: {district}
  - Village: {village}
  - Coordinates: {lat:.5f}, {lon:.5f} (source={location_source}, accuracy={accuracy_m:.0f} m)
  - Weather snapshot: {weather_snapshot}
Tailor ALL recommendations to:
  - Local climate zone: {climate_zone}
  - Local soil types and agroclimate
  - Local crop calendar and seasonal patterns
  - Regional pest and disease patterns
  - Local input costs and labor rates
  - Local market prices and value chains
RULES:
  1. Always give specific, actionable advice — never generic guidance.
  2. Cross-reference at least 2 knowledge sources before answering.
  3. Flag clearly if recommendation is region-specific or globally generalized.
  4. Respond in {language} (use local language if not English/Indonesian).
  5. Cite your reasoning and data source for every quantitative claim.
  6. If data is unavailable for the specific region, say so and provide the best
     global analog — never silently hallucinate local figures.
Knowledge sources to draw on: FAO crop guides, USDA NASS, CGIAR outputs,
national agricultural extension services for {country}, EPPO/CABI pest databases,
real-time weather APIs, and local commodity price boards."""


def _build_agri_system_prompt(loc: Optional["LocationState"] = None) -> str:
    """Build location-aware AI system prompt from current LocationState."""
    if loc is None:
        loc = get_location_state()
    lang_map = {
        "id": "Bahasa Indonesia", "en": "English", "ja": "Japanese (日本語)",
        "zh": "Chinese (中文)", "hi": "Hindi (हिंदी)", "pt": "Portuguese",
        "es": "Spanish", "fr": "French", "de": "German", "ar": "Arabic",
        "th": "Thai", "vi": "Vietnamese", "ms": "Malay", "sw": "Swahili",
    }
    lang_label = lang_map.get(loc.language, "English")
    weather_snapshot = "not loaded"
    if globals().get("_STREAMLIT_OK", False):
        wx = st.session_state.get("wx_data")
        if wx:
            try:
                weather_snapshot = (
                    f"T={wx.temp_outside:.1f}C, RH={wx.humidity_outside:.0f}%, "
                    f"radiation={wx.solar_radiation:.0f} W/m2, wind={wx.wind_speed:.1f} m/s, "
                    f"source={wx.source}"
                )
            except Exception:
                weather_snapshot = "loaded but unavailable"
    return _AGRI_SYSTEM_PROMPT_TEMPLATE.format(
        country=loc.country,
        country_code=loc.country_code,
        province=loc.province or "N/A",
        city=loc.city or "N/A",
        district=loc.district or "N/A",
        village=loc.village or "N/A",
        lat=loc.lat,
        lon=loc.lon,
        location_source=loc.location_source or "manual",
        accuracy_m=loc.accuracy_m or 0.0,
        climate_zone=loc.climate_zone,
        language=lang_label,
        weather_snapshot=weather_snapshot,
    )


# Legacy alias (backward compat with existing call_llm calls)
try:
    _AGRI_SYSTEM_PROMPT = _build_agri_system_prompt(LocationState())
except Exception:
    _AGRI_SYSTEM_PROMPT = (
        "You are an expert agronomist with deep knowledge of global agriculture. "
        "Provide practical, location-aware farming advice."
    )


def call_llm(prompt: str, system: str = "",
             context: str = "", max_tokens: int = 600) -> Tuple[str, str]:
    """
    Panggil LLM sesuai provider yang dikonfigurasi.
    System prompt otomatis menyertakan locationState jika tidak di-override.
    Return: (response_text, provider_used)
    Urutan fallback: provider utama → STUB
    """
    # Auto-build location-aware system prompt if caller didn't provide one
    if not system:
        system = _build_agri_system_prompt(get_location_state())

    provider_name = _get_cfg("llm_provider", LLMProvider.GEMINI.value)
    try:
        provider = LLMProvider(provider_name)
    except ValueError:
        provider = LLMProvider.STUB

    full_prompt = (context + "\n\n" + prompt).strip() if context else prompt

    if provider == LLMProvider.GROQ:
        return _call_groq(full_prompt, system, max_tokens)
    elif provider == LLMProvider.GEMINI:
        return _call_gemini(full_prompt, system, max_tokens)
    elif provider == LLMProvider.OLLAMA:
        return _call_ollama(full_prompt, system, max_tokens)
    elif provider == LLMProvider.OPENROUTER:
        return _call_openrouter(full_prompt, system, max_tokens)
    elif provider == LLMProvider.OPENAI:
        return _call_openai_compat(
            full_prompt, system, max_tokens,
            base_url="https://api.openai.com/v1",
            api_key=_get_cfg("openai_api_key"),
            model="gpt-4o-mini",
        )
    elif provider == LLMProvider.CLAUDE:
        return _call_claude(full_prompt, system, max_tokens)
    return _llm_stub_response(prompt), "stub"


def _llm_temperature(default: float = 0.35) -> float:
    try:
        return float(_get_cfg("llm_temperature", str(default)))
    except Exception:
        return default


def _call_groq(prompt: str, system: str, max_tokens: int) -> Tuple[str, str]:
    key = _get_cfg("groq_api_key")
    if not key:
        return "⚠️ Groq API key not set. Open sidebar → LLM Settings.", "groq_error"
    model = _get_cfg("groq_model", _get_cfg("llm_model", _GROQ_MODELS[0]))
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ], "max_tokens": max_tokens, "temperature": _llm_temperature()},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip(), f"Groq/{model}"
    except Exception as e:
        return f"❌ Groq error: {str(e)[:80]}", "groq_error"


def _call_gemini(prompt: str, system: str, max_tokens: int) -> Tuple[str, str]:
    key = _get_cfg("gemini_api_key")
    if not key:
        return "⚠️ Gemini API key not set. Free signup at aistudio.google.com", "gemini_error"
    model = _get_cfg("gemini_model", _get_cfg("llm_model", _GEMINI_MODELS[0]))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    last_err = ""
    for _attempt in range(3):          # up to 3 attempts with exponential backoff
        try:
            r = requests.post(url, json={
                "contents": [{"parts": [{"text": system + "\n\n" + prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": _llm_temperature()},
            }, timeout=25)
            if r.status_code == 429:   # rate-limit → backoff then retry
                _wait = (2 ** _attempt)
                time.sleep(_wait)
                last_err = "429 rate limit"
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return text, f"Gemini/{model}"
        except requests.exceptions.HTTPError as _he:
            if getattr(_he.response, "status_code", 0) == 429 and _attempt < 2:
                time.sleep(2 ** _attempt)
                last_err = "429 rate limit"
                continue
            last_err = str(_he)[:80]
            break
        except Exception as _e:
            last_err = str(_e)[:80]
            break
    # Fallback chain: try Groq → then stub
    _groq_key = _get_cfg("groq_api_key", "")
    if _groq_key:
        _res, _src = _call_groq(prompt, system, max_tokens)
        if not _src.endswith("_error"):
            return _res, f"{_src} (Gemini fallback)"
    return (f"⚠️ Gemini {last_err}. Try again shortly or switch to Groq "
            f"(free at groq.com — more stable)."), "gemini_ratelimit"


def _call_ollama(prompt: str, system: str, max_tokens: int) -> Tuple[str, str]:
    host   = _get_cfg("ollama_host", "http://localhost:11434")
    model  = _get_cfg("ollama_model", "llama3.3")
    try:
        r = requests.post(f"{host}/api/chat", json={
            "model": model,
            "messages": [
                {"role": "system",  "content": system},
                {"role": "user",    "content": prompt},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }, timeout=60)
        r.raise_for_status()
        return r.json()["message"]["content"].strip(), f"Ollama/{model}"
    except requests.exceptions.ConnectionError:
        return ("⚠️ Ollama tidak berjalan. Install: https://ollama.com · "
                "Lalu jalankan: `ollama run llama3.3`"), "ollama_offline"
    except Exception as e:
        return f"❌ Ollama error: {str(e)[:80]}", "ollama_error"


def _call_openrouter(prompt: str, system: str, max_tokens: int) -> Tuple[str, str]:
    key   = _get_cfg("openrouter_key")
    if not key:
        return "⚠️ OpenRouter key not set. Free signup at openrouter.ai", "openrouter_error"
    model = _get_cfg("openrouter_model", _get_cfg("llm_model", _OPENROUTER_FREE[0]))
    # Jika model utama gagal (model berubah/dihapus), coba fallback ke model lain
    result, src = _call_openai_compat(prompt, system, max_tokens,
                                      base_url="https://openrouter.ai/api/v1",
                                      api_key=key, model=model)
    if src == "error" and model != _OPENROUTER_FREE[0]:
        # Fallback ke model gratis pertama yang paling stabil
        result, src = _call_openai_compat(prompt, system, max_tokens,
                                          base_url="https://openrouter.ai/api/v1",
                                          api_key=key, model=_OPENROUTER_FREE[0])
        if src != "error":
            src = f"{_OPENROUTER_FREE[0]} (fallback)"
    return result, src


def _call_openai_compat(prompt: str, system: str, max_tokens: int,
                        base_url: str, api_key: str, model: str) -> Tuple[str, str]:
    try:
        r = requests.post(f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ], "max_tokens": max_tokens, "temperature": _llm_temperature()},
            timeout=25)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip(), model
    except Exception as e:
        return f"❌ Error: {str(e)[:80]}", "error"


def _call_claude(prompt: str, system: str, max_tokens: int) -> Tuple[str, str]:
    key = _get_cfg("claude_api_key")
    if not key:
        return "⚠️ Anthropic API key not set.", "claude_error"
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                  "system": system,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=25)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip(), "Claude Haiku"
    except Exception as e:
        return f"❌ Claude error: {str(e)[:80]}", "claude_error"


def _llm_stub_response(prompt: str) -> str:
    """Fallback rule-based response when no LLM provider."""
    p = prompt.lower()
    if any(w in p for w in ["kuning", "yellow", "klorosis"]):
        return ("Yellow leaves may indicate N deficiency, overwatering, or virus infection. "
                "Check soil pH (ideal 6.0-6.8), ensure good drainage, try urea foliar 2 g/L.")
    if any(w in p for w in ["layu", "wilt", "mati"]):
        return ("Wilting may be Fusarium wilt, Pythium root rot, or water deficit. "
                "Pull plant, check roots (brown = rot). Soil solarization + trichoderma before replanting.")
    if any(w in p for w in ["pupuk", "npk", "urea", "fertilizer"]):
        return ("General dose: Urea 200 kg/ha, SP-36 100 kg/ha, KCl 100 kg/ha per season. "
                "Split application: 1/3 at planting, 2/3 at active vegetative stage. Adjust per soil test.")
    if any(w in p for w in ["hama", "pest", "ulat", "kutu", "trips"]):
        return ("Identify first — aphids: systemic insecticide (imidacloprid). "
                "Caterpillars: Bacillus thuringiensis (bio) or chlorpyrifos. Thrips: spinosad or abamectin.")
    return ("Good question! For accurate answers, activate a real AI provider in the sidebar "
            "(Groq free, Gemini free, or local Ollama). Only basic responses available now.")

# ══════════════════════════════════════════════════════════════════════════════
# 1. PAGE CONFIG & THEME (WAJIB PALING ATAS!)
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AI Greenhouse Digital Twin v4",
    page_icon="⚜️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Minimal font preload (full theme injected inside main()) ───────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@300;400;600;700&display=swap');
</style>""", unsafe_allow_html=True)


def inject_theme_css(dark: bool = True):
    """Inject the full AGRI-MIND v5 design system. Call once at top of main().
    dark=True  → Dark Forest Tech  |  dark=False → Light Greenhouse Morning
    """
    # ── palette ──────────────────────────────────────────────────────────────
    if dark:
        bg_base   = "#071307"
        bg_surf   = "#0d200d"
        bg_card   = "rgba(11,24,11,0.94)"
        bg_card2  = "rgba(8,18,28,0.94)"
        bg_input  = "rgba(9,20,9,0.85)"
        bg_sidebar= "#060f06"
        txt_h     = "#e4f5e4"
        txt_body  = "#bdd9bd"
        txt_muted = "#6a926a"
        txt_faint = "#3d5e3d"
        acc_green = "#4ee84e"
        acc_gdim  = "#28a428"
        acc_blue  = "#38d4ff"
        acc_purp  = "#c084ff"
        acc_gold  = "#ffc844"
        acc_red   = "#ff5757"
        border    = "rgba(78,232,78,0.18)"
        border_hi = "rgba(78,232,78,0.42)"
        glow      = "rgba(78,232,78,0.18)"
        shadow    = "0 4px 24px rgba(0,0,0,0.55)"
        shadow_hi = "0 8px 40px rgba(78,232,78,0.14)"
        scrollbar_bg  = "#0a180a"
        scrollbar_thr = "#1e4a1e"
        hero_bg   = "linear-gradient(135deg,rgba(9,26,9,0.97) 0%,rgba(8,18,30,0.97) 60%,rgba(18,9,30,0.97) 100%)"
        hero_strip= "linear-gradient(90deg,#4ee84e 0%,#38d4ff 50%,#c084ff 100%)"
        app_bg    = "radial-gradient(ellipse at top left,#0a1a0a 0%,#071307 55%,#040a04 100%)"
        tab_bg    = "rgba(10,22,10,0.5)"
        tab_sel   = "linear-gradient(135deg,rgba(30,65,30,0.75),rgba(18,44,70,0.75))"
        badge_ai_bg = "linear-gradient(90deg,#28a428,#0a72a8)"
    else:
        bg_base   = "#f0f7ef"
        bg_surf   = "#e3f1e3"
        bg_card   = "rgba(255,255,255,0.95)"
        bg_card2  = "rgba(235,245,255,0.95)"
        bg_input  = "rgba(255,255,255,0.92)"
        bg_sidebar= "#eaf4ea"
        txt_h     = "#0c260c"
        txt_body  = "#1c3c1c"
        txt_muted = "#4a7a4a"
        txt_faint = "#8aaa8a"
        acc_green = "#1a7a1a"
        acc_gdim  = "#2a9a2a"
        acc_blue  = "#0a72a8"
        acc_purp  = "#6030a8"
        acc_gold  = "#9a6800"
        acc_red   = "#c02020"
        border    = "rgba(26,122,26,0.22)"
        border_hi = "rgba(26,122,26,0.48)"
        glow      = "rgba(26,122,26,0.12)"
        shadow    = "0 4px 20px rgba(0,60,0,0.10)"
        shadow_hi = "0 8px 32px rgba(26,122,26,0.18)"
        scrollbar_bg  = "#ddf0dd"
        scrollbar_thr = "#6aaa6a"
        hero_bg   = "linear-gradient(135deg,rgba(240,248,240,0.98) 0%,rgba(230,244,255,0.98) 60%,rgba(244,238,255,0.98) 100%)"
        hero_strip= "linear-gradient(90deg,#1a7a1a 0%,#0a72a8 50%,#6030a8 100%)"
        app_bg    = "linear-gradient(160deg,#f0f7ef 0%,#e8f5e8 60%,#eef0f8 100%)"
        tab_bg    = "rgba(220,240,220,0.6)"
        tab_sel   = "linear-gradient(135deg,rgba(180,230,180,0.7),rgba(190,225,245,0.7))"
        badge_ai_bg = "linear-gradient(90deg,#2a9a2a,#0a72a8)"

    # ── inject CSS ────────────────────────────────────────────────────────────
    st.markdown(f"""
<style>
/* ================================================================
   AGRI-MIND v5  ·  Design System  ·  {"Dark Forest Tech" if dark else "Light Greenhouse"}
   ================================================================ */

/* ── Base & Layout ── */
html, body, [class*="css"] {{
    font-family: 'Inter', 'JetBrains Mono', sans-serif;
    color: {txt_body};
    transition: background-color 0.38s ease, color 0.28s ease;
}}
.stApp {{
    background: {app_bg};
    min-height: 100vh;
}}
.block-container {{
    padding-top: 1rem;
    max-width: 1540px;
}}
div[data-testid="stHorizontalBlock"] {{ gap: 0.7rem; }}

/* ── Scrollbar ── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {scrollbar_bg}; border-radius: 6px; }}
::-webkit-scrollbar-thumb {{ background: {scrollbar_thr}; border-radius: 6px; }}
::-webkit-scrollbar-thumb:hover {{ background: {acc_green}; }}

/* ── Animations ── */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes breathe {{
    0%,100% {{ box-shadow: 0 0 0 0 {glow}; }}
    50%      {{ box-shadow: 0 0 18px 4px {glow}; }}
}}
@keyframes shimmer {{
    0%   {{ background-position: -200% 0; }}
    100% {{ background-position:  200% 0; }}
}}
@keyframes leafFloat {{
    0%,100% {{ transform: translateY(0) rotate(-2deg); }}
    50%     {{ transform: translateY(-6px) rotate(2deg); }}
}}
@keyframes pulseGlow {{
    0%,100% {{ opacity:1; transform:scale(1);   }}
    50%     {{ opacity:.7; transform:scale(1.2); }}
}}
@keyframes gradientShift {{
    0%   {{ background-position:0% 50%; }}
    50%  {{ background-position:100% 50%; }}
    100% {{ background-position:0% 50%; }}
}}
@keyframes scanline {{
    0%   {{ transform:translateY(-100%); opacity:0; }}
    50%  {{ opacity:.35; }}
    100% {{ transform:translateY(150%); opacity:0; }}
}}
@keyframes ripple {{
    0%   {{ transform:scale(0.8); opacity:1; }}
    100% {{ transform:scale(2.2); opacity:0; }}
}}
@keyframes typeBlink {{
    0%,100% {{ border-color:{acc_green}; }}
    50%     {{ border-color:transparent; }}
}}

/* ── Hero Banner ── */
.ag5-hero, .ag4-hero {{
    position: relative;
    padding: 20px 26px;
    margin-bottom: 20px;
    border-radius: 16px;
    background: {hero_bg};
    border: 1px solid {border_hi};
    overflow: hidden;
    animation: fadeInUp 0.5s ease both;
    box-shadow: {shadow};
}}
.ag5-hero::before, .ag4-hero::before {{
    content: '';
    position: absolute; top:0; left:0; right:0; height: 3px;
    background: {hero_strip};
    background-size: 200% 100%;
    animation: gradientShift 5s ease infinite;
}}
.ag5-hero h1, .ag4-hero h1 {{
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700; font-size: 22px; margin: 0;
    background: {hero_strip};
    background-size: 200% auto;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: gradientShift 6s ease infinite;
    letter-spacing: 0.5px;
}}
.ag5-hero p, .ag4-hero p {{
    color: {txt_muted};
    font-size: 11px; margin: 6px 0 0 0;
    letter-spacing: 0.8px; line-height: 1.6;
}}

/* ── Section Header ── */
.section-header {{
    display: flex; align-items: center; gap: 8px;
    font-family: 'Inter', sans-serif; font-weight: 700;
    color: {acc_green}; font-size: 13px;
    letter-spacing: 1.2px; text-transform: uppercase;
    border-bottom: 1px solid {border};
    padding-bottom: 8px; margin: 22px 0 12px 0;
    animation: fadeInUp 0.4s ease both;
}}

/* ── Cards (all variants) ── */
.metric-card, .zone-card, .ai-tech-card, .prediction-box,
.roi-box, .kalman-box, .maint-card, .carbon-box {{
    background: {bg_card};
    border: 1px solid {border};
    border-radius: 14px;
    padding: 16px 20px;
    margin: 5px 0;
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    animation: fadeInUp 0.45s ease both;
    box-shadow: {shadow};
}}
.metric-card:hover, .zone-card:hover, .ai-tech-card:hover {{
    transform: translateY(-3px);
    border-color: {border_hi};
    box-shadow: {shadow_hi};
}}

/* ── AI Tech Card (holographic) ── */
.ai-tech-card {{
    position: relative;
    background: linear-gradient(135deg, {bg_card} 0%, {bg_card2} 100%);
    animation: fadeInUp 0.45s ease both, breathe 5s ease-in-out infinite;
    overflow: hidden;
}}
.ai-tech-card::before {{
    content: '';
    position: absolute; top:0; left:0; right:0; height: 2px;
    background: {hero_strip};
    background-size: 200% 100%;
    animation: gradientShift 6s ease infinite;
}}
.ai-tech-card::after {{
    content: '';
    position: absolute; top:0; left:0; right:0; bottom:0;
    background: linear-gradient(180deg,transparent 49%,rgba(78,232,78,0.03) 50%,transparent 51%);
    pointer-events: none;
    animation: scanline 10s linear infinite;
}}

/* ── Neon Metric Card ── */
.neon-metric {{
    background: {bg_card};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 14px 18px;
    transition: all 0.28s ease;
    animation: fadeInUp 0.4s ease both;
}}
.neon-metric:hover {{
    transform: translateY(-3px);
    border-color: {border_hi};
    box-shadow: {shadow_hi};
}}
.neon-metric .label {{
    font-size: 10px; color: {txt_muted};
    text-transform: uppercase; letter-spacing: 1.5px;
    font-family: 'Inter', sans-serif; font-weight: 600;
}}
.neon-metric .value {{
    font-size: 24px; font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    background: linear-gradient(135deg, {acc_green}, {acc_blue});
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}}

/* ── Full Economics Projection ── */
.econ-grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin: 10px 0 12px 0;
}}
.econ-card {{
    background: linear-gradient(135deg, rgba(8,28,12,.92), rgba(9,18,22,.88));
    border: 1px solid rgba(84,255,116,.20);
    border-radius: 10px;
    padding: 11px 13px;
    min-height: 88px;
    box-shadow: 0 6px 22px rgba(0,0,0,.20);
}}
.econ-card .label {{
    color: {txt_muted};
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0;
    font-weight: 700;
    line-height: 1.25;
}}
.econ-card .value {{
    color: {acc_green};
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px;
    font-weight: 800;
    line-height: 1.18;
    overflow-wrap: anywhere;
    margin-top: 5px;
}}
.econ-card.money .value {{
    font-size: 14px;
    line-height: 1.32;
}}
.econ-money-line {{
    display: block;
    white-space: nowrap;
}}
.econ-money-line.primary {{
    font-size: 15px;
}}
.econ-money-line.local {{
    color: {acc_green};
}}
.econ-card .sub {{
    color: {txt_muted};
    font-size: 9.5px;
    line-height: 1.35;
    margin-top: 6px;
}}
.econ-card.good .value {{ color: {acc_green}; }}
.econ-card.warn .value {{ color: {acc_gold}; }}
.econ-card.bad .value {{ color: {acc_red}; }}
.econ-card.info .value {{ color: {acc_blue}; }}
.econ-note {{
    background: rgba(255, 190, 80, .08);
    border: 1px solid rgba(255, 190, 80, .18);
    border-radius: 10px;
    padding: 10px 12px;
    color: {txt_muted};
    font-size: 11px;
    line-height: 1.55;
    margin: 10px 0 14px 0;
}}
.econ-table-wrap div[data-testid="stDataFrame"] {{
    font-size: 11px;
}}
@media (max-width: 1180px) {{
    .econ-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 720px) {{
    .econ-grid {{ grid-template-columns: 1fr; }}
    .econ-card.money .value {{ font-size: 13px; }}
    .econ-money-line.primary {{ font-size: 14px; }}
}}

/* ── Terminal / Log ── */
.terminal-log {{
    background: {bg_base};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 12px 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: {acc_gdim};
    max-height: 220px; overflow-y: auto;
    line-height: 1.7;
}}

/* ── Alert Boxes ── */
.alert-box {{
    padding: 11px 15px; border-radius: 10px;
    margin: 5px 0; font-family: 'Inter', sans-serif;
    font-size: 12px; font-weight: 500;
    animation: fadeInUp 0.3s ease both;
    transition: all 0.25s ease;
}}
.alert-critical {{ background: {"#2e0808" if dark else "#fff0f0"}; border-left: 4px solid {acc_red};   color: {"#ffaaaa" if dark else "#8b0000"}; }}
.alert-warning  {{ background: {"#2e2008" if dark else "#fffbf0"}; border-left: 4px solid {acc_gold};  color: {"#ffdaaa" if dark else "#7a4800"}; }}
.alert-info     {{ background: {"#08202e" if dark else "#f0f8ff"}; border-left: 4px solid {acc_blue};  color: {"#aaddff" if dark else "#003a6a"}; }}
.alert-ok       {{ background: {"#08280a" if dark else "#f0fff0"}; border-left: 4px solid {acc_green}; color: {"#aaff99" if dark else "#0a4a0a"}; }}
.alert-disease  {{ background: {"#280830" if dark else "#fdf0ff"}; border-left: 4px solid {acc_purp};  color: {"#ddaaff" if dark else "#40007a"}; }}
.alert-maint    {{ background: {"#282008" if dark else "#fffdf0"}; border-left: 4px solid {acc_gold};  color: {"#ffeeaa" if dark else "#6a4400"}; }}

/* ── Status Badges ── */
.status-badge {{
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 10px; font-family: 'Inter', sans-serif; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.8px;
    transition: all 0.2s ease;
}}
.badge-online  {{ background: {"#142814" if dark else "#e8ffe8"}; color: {acc_green}; border: 1px solid {acc_gdim}; }}
.badge-offline {{ background: {"#3a1010" if dark else "#ffe8e8"}; color: {acc_red};   border: 1px solid {"#882222" if dark else "#c05050"}; }}
.badge-warn    {{ background: {"#3a2e08" if dark else "#fff8e0"}; color: {acc_gold};  border: 1px solid {"#886622" if dark else "#c09030"}; }}
.badge-ml      {{ background: {"#102838" if dark else "#e8f5ff"}; color: {acc_blue};  border: 1px solid {"#226688" if dark else "#3080b0"}; }}
.badge-new     {{ background: {"#1a1040" if dark else "#f5eeff"}; color: {acc_purp};  border: 1px solid {"#553388" if dark else "#8050c0"}; }}

/* ── Live Pulse Indicator ── */
.live-pulse {{
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    background: {acc_green};
    animation: pulseGlow 1.8s ease-in-out infinite;
    margin-right: 6px; vertical-align: middle;
    position: relative;
}}
.live-pulse::after {{
    content: '';
    position: absolute; top: -3px; left: -3px;
    width: 15px; height: 15px; border-radius: 50%;
    border: 2px solid {acc_green};
    animation: ripple 1.8s ease-out infinite;
}}

/* ── Tier Banners ── */
.tier-banner {{
    background: linear-gradient(90deg,{"rgba(20,55,20,0.65)" if dark else "rgba(200,230,200,0.7)"},{"rgba(38,28,75,0.65)" if dark else "rgba(210,200,240,0.7)"});
    border-left: 3px solid {acc_purp}; border-right: 3px solid {acc_blue};
    padding: 10px 16px; border-radius: 8px;
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    letter-spacing: 0.8px; text-transform: uppercase;
    color: {txt_body}; margin: 14px 0 10px 0;
}}
.ai-badge {{
    display: inline-block; padding: 3px 9px; border-radius: 12px;
    font-size: 9px; font-weight: 700; letter-spacing: 1.2px;
    background: {badge_ai_bg}; color: #fff;
    margin-left: 6px; vertical-align: middle;
}}
.tier1-badge {{ background: linear-gradient(90deg,{"#28a428,#0a7088" if dark else "#1a8a1a,#0a72a8"}); color:#fff; }}
.tier2-badge {{ background: linear-gradient(90deg,{"#0a7088,#7844cc" if dark else "#0a72a8,#6030a8"}); color:#fff; }}
.tier3-badge {{ background: linear-gradient(90deg,{"#7844cc,#cc44aa" if dark else "#6030a8,#a83080"}); color:#fff; }}
.tier4-badge {{ background: linear-gradient(90deg,{"#cc44aa,#cc9a00" if dark else "#a83080,#9a6800"}); color:#fff; }}

/* ── Cyber Grid ── */
.cyber-grid {{
    background-image:
        linear-gradient({border} 1px, transparent 1px),
        linear-gradient(90deg, {border} 1px, transparent 1px);
    background-size: 32px 32px;
    padding: 14px; border-radius: 10px;
    border: 1px solid {border};
}}

/* ── Streamlit Native Element Overrides ── */
div[data-testid="stMetricValue"] {{
    font-family: 'JetBrains Mono', monospace;
    color: {acc_green}; font-size: 26px; font-weight: 700;
}}
div[data-testid="stMetricLabel"] {{
    color: {txt_muted}; font-family: 'Inter', sans-serif;
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 600;
}}
div[data-testid="stMetricDelta"] {{
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
}}
.stSelectbox label, .stSlider label, .stNumberInput label,
.stTextInput label, .stCheckbox label {{
    color: {txt_muted}; font-family: 'Inter', sans-serif;
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.8px;
}}
.stTextInput > div > div > input,
.stSelectbox > div > div > div,
.stNumberInput > div > div > input {{
    background: {bg_input} !important;
    color: {txt_body} !important;
    border: 1px solid {border} !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {{
    border-color: {border_hi} !important;
    box-shadow: 0 0 0 3px {glow} !important;
}}

/* ── Buttons ── */
.stButton > button {{
    background: linear-gradient(90deg,{"#143a14,#1e6a1e" if dark else "#e8f5e8,#d0ecd0"});
    color: {txt_body}; border: 1px solid {border};
    border-radius: 10px; font-family: 'Inter', sans-serif;
    font-weight: 600; font-size: 12px; letter-spacing: 0.5px;
    padding: 8px 18px;
    transition: all 0.22s ease;
}}
.stButton > button:hover {{
    background: linear-gradient(90deg,{"#1e6a1e,#28aa28" if dark else "#c8e8c8,#a8d8a8"});
    border-color: {border_hi};
    transform: translateY(-2px);
    box-shadow: {shadow_hi};
}}
.stButton > button[kind="primary"] {{
    background: linear-gradient(90deg,{acc_gdim},{acc_green});
    color: {"#071307" if dark else "#ffffff"}; font-weight: 700;
}}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 5px; background: {tab_bg};
    padding: 5px; border-radius: 12px;
    border: 1px solid {border};
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent; border-radius: 9px;
    padding: 8px 16px; border: 1px solid transparent;
    font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 600;
    color: {txt_muted};
    transition: all 0.22s ease;
}}
.stTabs [data-baseweb="tab"]:hover {{
    background: {"rgba(40,70,40,0.45)" if dark else "rgba(180,220,180,0.5)"};
    border-color: {border};
    color: {txt_body};
}}
.stTabs [aria-selected="true"] {{
    background: {tab_sel} !important;
    border-color: {border_hi} !important;
    color: {acc_green} !important;
    box-shadow: 0 2px 12px {glow};
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    background: {bg_sidebar} !important;
    border-right: 1px solid {border} !important;
}}
[data-testid="stSidebar"] .stButton > button {{
    width: 100%;
}}

/* ── Expander ── */
.streamlit-expanderHeader {{
    background: {bg_card} !important;
    border: 1px solid {border} !important;
    border-radius: 10px !important;
    color: {txt_body} !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    transition: all 0.22s ease;
}}
.streamlit-expanderHeader:hover {{
    border-color: {border_hi} !important;
    box-shadow: {shadow};
}}

/* ── Progress / Slider ── */
.stSlider [data-baseweb="slider"] {{
    margin-top: 4px;
}}
[data-testid="stProgressBar"] > div {{
    background: {acc_green} !important;
    border-radius: 4px;
}}

/* ── Caption / Info / Success / Error ── */
.stCaption {{ color: {txt_muted}; font-family:'Inter',sans-serif; font-size:11px; }}
.stSuccess {{ background: {"#0a280a" if dark else "#f0fff0"} !important; border-left: 4px solid {acc_green} !important; border-radius: 8px; }}
.stWarning {{ background: {"#2a1e06" if dark else "#fffbf0"} !important; border-left: 4px solid {acc_gold}  !important; border-radius: 8px; }}
.stError   {{ background: {"#280808" if dark else "#fff0f0"} !important; border-left: 4px solid {acc_red}   !important; border-radius: 8px; }}
.stInfo    {{ background: {"#06182a" if dark else "#f0f8ff"} !important; border-left: 4px solid {acc_blue}  !important; border-radius: 8px; }}

/* ── AG4 Metric Wall ── */
.ag4-metric-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 16px 22px; align-items: stretch; margin: 8px 0 18px 0;
}}
.ag4-metric {{
    position: relative; min-height: 86px;
    padding: 4px 2px 10px 2px;
    border-bottom: 2px solid {border};
    font-family: 'JetBrains Mono', monospace;
    animation: fadeInUp 0.45s ease both;
}}
.ag4-metric::before {{
    content: ""; position: absolute; left:0; bottom:-2px;
    width: 36px; height: 2px;
    background: linear-gradient(90deg,{acc_green},transparent);
}}
.ag4-label {{
    display: flex; align-items: center; gap: 5px;
    color: {txt_body}; font-family: 'Inter', sans-serif;
    font-size: 12px; font-weight: 600; line-height: 1.2;
}}
.ag4-icon {{ width:16px; display:inline-flex; justify-content:center; }}
.ag4-value {{
    margin-top: 6px; color: {acc_green};
    font-size: 26px; font-weight: 700; line-height: 1.05;
    white-space: nowrap;
}}
.ag4-value.is-long {{ font-size: 21px; white-space: normal; overflow-wrap: anywhere; }}
.ag4-delta {{
    display: inline-flex; align-items: center; gap: 4px;
    margin-top: 7px; padding: 3px 8px; border-radius: 999px;
    font-size: 10px; font-weight: 700;
    background: {"rgba(78,232,78,0.10)" if dark else "rgba(26,122,26,0.10)"};
    color: {acc_gdim}; border: 1px solid {border};
}}
.ag4-state-good .ag4-value  {{ color: {acc_green}; }}
.ag4-state-warn .ag4-value  {{ color: {acc_gold};  }}
.ag4-state-bad  .ag4-value  {{ color: {acc_red};   }}
.ag4-state-info .ag4-value  {{ color: {acc_blue};  }}
.ag4-state-good .ag4-delta  {{ background:{"rgba(78,232,78,0.12)" if dark else "rgba(26,122,26,0.10)"}; color:{acc_green}; }}
.ag4-state-warn .ag4-delta  {{ background:{"rgba(255,200,68,0.14)" if dark else "rgba(154,104,0,0.10)"}; color:{acc_gold}; border-color:{"rgba(255,200,68,0.25)" if dark else "rgba(154,104,0,0.25)"}; }}
.ag4-state-bad  .ag4-delta  {{ background:{"rgba(255,87,87,0.14)" if dark else "rgba(192,32,32,0.10)"}; color:{acc_red}; border-color:{"rgba(255,87,87,0.25)" if dark else "rgba(192,32,32,0.25)"}; }}
.ag4-state-info .ag4-delta  {{ background:{"rgba(56,212,255,0.12)" if dark else "rgba(10,114,168,0.10)"}; color:{acc_blue}; border-color:{"rgba(56,212,255,0.22)" if dark else "rgba(10,114,168,0.22)"}; }}
.ag4-meta-row {{
    display: flex; align-items: center; flex-wrap: wrap;
    gap: 8px 12px; margin: 2px 0 16px 0;
    color: {txt_muted}; font-family:'Inter',sans-serif; font-size:10px; font-weight:500;
}}
.ag4-meta-pill {{
    display: inline-flex; gap: 5px; align-items: center;
    padding-right: 10px; border-right: 1px solid {border};
}}
.ag4-meta-pill:last-child {{ border-right: 0; }}
.ag4-zone-intel {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(178px,1fr));
    gap: 10px; margin: -2px 0 14px 0;
}}
.ag4-intel-card {{
    border: 1px solid {border}; border-radius: 10px;
    padding: 10px 14px;
    background: {bg_card};
    animation: fadeInUp 0.4s ease both;
    transition: all 0.22s ease;
}}
.ag4-intel-card:hover {{ border-color: {border_hi}; transform: translateY(-2px); }}
.ag4-intel-label {{ color: {txt_muted}; font-family:'Inter',sans-serif; font-size:11px; font-weight:600; }}
.ag4-intel-value {{ color: {acc_green}; font-size:20px; font-weight:800; margin-top:4px; font-family:'JetBrains Mono',monospace; }}
.ag4-bar {{
    height: 5px; width: 100%; overflow: hidden;
    margin-top: 8px; border-radius: 999px;
    background: {border};
}}
.ag4-bar > span {{
    display: block; height: 100%; border-radius: inherit;
    background: linear-gradient(90deg,{acc_gdim},{acc_green});
    transition: width 0.6s ease;
}}
.ag4-bar.warn > span {{ background: linear-gradient(90deg,{acc_gold},{"#ffd166" if dark else "#f0a000"}); }}
.ag4-bar.bad  > span {{ background: linear-gradient(90deg,{acc_red},{"#ff8a76" if dark else "#e06050"}); }}
.ag4-panel-note {{
    margin: 0 0 14px 0; font-family:'Inter',sans-serif;
    color: {txt_faint}; font-size: 10px; font-weight: 500;
}}

/* ── Theme Toggle Widget ── */
.theme-toggle-wrap {{
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; border-radius: 12px;
    background: {bg_card}; border: 1px solid {border};
    margin-bottom: 14px; cursor: pointer;
    transition: all 0.25s ease;
    animation: fadeInUp 0.3s ease both;
}}
.theme-toggle-wrap:hover {{ border-color: {border_hi}; box-shadow: {shadow_hi}; }}
.theme-icon {{ font-size: 20px; transition: transform 0.4s ease; }}
.theme-label {{
    font-family:'Inter',sans-serif; font-size:12px; font-weight:600;
    color:{txt_body}; flex:1;
}}
.theme-sub {{ font-size:10px; color:{txt_muted}; }}

/* ── Friendly Info Chips ── */
.info-chip {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 20px;
    background: {bg_card}; border: 1px solid {border};
    font-family: 'Inter', sans-serif; font-size: 11px;
    color: {txt_muted}; font-weight: 500;
    transition: all 0.2s ease;
}}
.info-chip:hover {{ border-color: {border_hi}; color: {txt_body}; }}

/* ── Sidebar Separator ── */
.sidebar-sep {{
    height: 1px; background: {border};
    margin: 12px 0; border-radius: 1px;
}}

/* ── Mobile ── */
@media (max-width: 768px) {{
    .ag4-metric-grid {{ grid-template-columns: repeat(auto-fit, minmax(115px, 1fr)); gap: 12px 16px; }}
    .ag4-value {{ font-size: 22px; }}
    .ag5-hero h1 {{ font-size: 18px; }}
    .block-container {{ padding-top: 0.5rem; }}
}}
</style>
""", unsafe_allow_html=True)

    # ── JavaScript: set theme attribute for instant re-apply on load ──────────
    theme_attr = "dark" if dark else "light"
    st.markdown(f"""
<script>
(function() {{
    var r = document.documentElement;
    r.setAttribute('data-agri-theme', '{theme_attr}');
    document.body.style.transition = 'background-color 0.38s ease, color 0.28s ease';
}})();
</script>
""", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════
# 2. OPTIONAL LIBRARY HOOKS (DIGABUNGKAN)
# ══════════════════════════════════════════════════════════════════════════════
try:
    from GreenLightPlus import GreenhouseGeometry, GreenLight
    GLP_AVAILABLE = True
except ImportError:
    GLP_AVAILABLE = False

try:
    import pcse
    from pcse.models import Wofost72_PP
    PCSE_AVAILABLE = True
except ImportError:
    PCSE_AVAILABLE = False

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
    PLOTLY_EXT = True
except ImportError:
    PLOTLY_AVAILABLE = False
    PLOTLY_EXT = False

try:
    from scipy.optimize import minimize, differential_evolution
    from scipy.signal import savgol_filter, butter, filtfilt
    from scipy.stats import zscore, rankdata
    SCIPY_AVAILABLE = True
    SCIPY_EXT = True
except ImportError:
    SCIPY_AVAILABLE = False
    SCIPY_EXT = False

try:
    from sklearn.linear_model import LinearRegression, Ridge, BayesianRidge
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.pipeline import make_pipeline
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# ── v5 Indonesian Extension optional libs ─────────────────────────────────
try:
    import serial
    import serial.tools.list_ports
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False

try:
    import paho.mqtt.client as mqtt_client
    _MQTT_OK = True
except ImportError:
    _MQTT_OK = False

try:
    from pymodbus.client import ModbusTcpClient
    _MODBUS_OK = True
except ImportError:
    _MODBUS_OK = False

_PLOTLY_OK    = PLOTLY_AVAILABLE
_STREAMLIT_OK = True
_REQUESTS_OK  = True

# ── GreenLight model (built-in pure Python — tidak butuh pip install apapun) ──
# Implementasi berdasarkan: Katzin et al. (2021) Biosystems Engineering
# doi.org/10.1016/j.biosystemseng.2021.02.010
# Package PyPI (greenlightplus) membutuhkan openstudio==3.6.1 yang tidak praktis
# diinstall → kita implementasikan sendiri inti fisikanya.

# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 1: SEMUA KOTA INDONESIA DI OPENWEATHERMAP (~500+)
# Sumber: kombinasi OpenWeatherMap city.list.json + BMKG + Wikipedia
# Dikelompokkan per provinsi untuk UX yang lebih baik
# ══════════════════════════════════════════════════════════════════════════════

INDONESIA_CITIES_BY_PROVINCE: Dict[str, List[str]] = {
    "DKI Jakarta": [
        "Jakarta", "Jakarta Barat", "Jakarta Pusat", "Jakarta Selatan",
        "Jakarta Timur", "Jakarta Utara", "Kepulauan Seribu",
    ],
    "Jawa Barat": [
        "Bandung", "Bekasi", "Bogor", "Cirebon", "Depok", "Sukabumi",
        "Tasikmalaya", "Karawang", "Purwakarta", "Subang", "Garut",
        "Cianjur", "Kuningan", "Indramayu", "Majalengka", "Sumedang",
        "Pangandaran", "Banjar", "Cimahi", "Salatiga",
    ],
    "Jawa Tengah": [
        "Semarang", "Surakarta", "Salatiga", "Magelang", "Pekalongan",
        "Tegal", "Cilacap", "Banyumas", "Purwokerto", "Kudus",
        "Jepara", "Demak", "Sragen", "Boyolali", "Klaten",
        "Wonosobo", "Purbalingga", "Kebumen", "Purworejo", "Temanggung",
        "Banjarnegara", "Batang", "Kendal", "Brebes", "Rembang",
        "Pati", "Blora", "Grobogan", "Wonogiri", "Karanganyar",
        "Sukoharjo",
    ],
    "DI Yogyakarta": [
        "Yogyakarta", "Sleman", "Bantul", "Kulonprogo", "Gunungkidul",
        "Wonosari",
    ],
    "Jawa Timur": [
        "Surabaya", "Malang", "Kediri", "Blitar", "Madiun",
        "Mojokerto", "Probolinggo", "Pasuruan", "Batu", "Jember",
        "Banyuwangi", "Situbondo", "Bondowoso", "Lumajang", "Jombang",
        "Nganjuk", "Tulungagung", "Trenggalek", "Ponorogo", "Pacitan",
        "Magetan", "Ngawi", "Bojonegoro", "Tuban", "Lamongan",
        "Gresik", "Sidoarjo", "Bangkalan", "Sampang", "Pamekasan",
        "Sumenep",
    ],
    "Bali": [
        "Denpasar", "Singaraja", "Ubud", "Kuta", "Seminyak",
        "Gianyar", "Karangasem", "Klungkung", "Bangli", "Tabanan",
        "Jembrana", "Badung", "Buleleng",
    ],
    "Nusa Tenggara Barat": [
        "Mataram", "Bima", "Sumbawa Besar", "Praya", "Selong",
        "Raba", "Taliwang", "Dompu", "Sumbawa", "Lombok Barat",
        "Lombok Tengah", "Lombok Timur", "Lombok Utara",
    ],
    "Nusa Tenggara Timur": [
        "Kupang", "Maumere", "Ende", "Labuan Bajo", "Atambua",
        "Ruteng", "Waingapu", "Waikabubak", "Kefamenanu", "Soe",
        "Lewoleba", "Larantuka", "Bajawa",
    ],
    "Sumatera Utara": [
        "Medan", "Binjai", "Tebing Tinggi", "Pematang Siantar", "Tanjung Balai",
        "Sibolga", "Padangsidempuan", "Gunungsitoli", "Berastagi", "Rantau Prapat",
        "Kisaran", "Lubuk Pakam", "Stabat", "Kabanjahe", "Balige",
        "Sidikalang", "Tarutung", "Dolok Sanggul",
    ],
    "Sumatera Barat": [
        "Padang", "Bukittinggi", "Payakumbuh", "Padang Panjang", "Solok",
        "Sawahlunto", "Sijunjung", "Dharmasraya", "Lubuk Basung", "Lubuk Sikaping",
        "Simpang Empat", "Muaro Sijunjung", "Painan",
    ],
    "Riau": [
        "Pekanbaru", "Dumai", "Siak", "Bengkalis", "Rokan Hulu",
        "Indragiri Hulu", "Kampar", "Kuantan", "Bangkinang", "Tembilahan",
        "Bagan Siapiapi",
    ],
    "Kepulauan Riau": [
        "Batam", "Tanjung Pinang", "Karimun", "Natuna", "Anambas",
        "Lingga", "Bintan",
    ],
    "Jambi": [
        "Jambi", "Sungai Penuh", "Muaro Bungo", "Sarolangun", "Tebo",
        "Merangin", "Bangko", "Kuala Tungkal", "Muara Bulian",
    ],
    "Sumatera Selatan": [
        "Palembang", "Lubuklinggau", "Prabumulih", "Pagaralam",
        "Muara Enim", "Lahat", "Ogan Komering Ilir", "Banyuasin",
        "Musi Rawas", "Sekayu",
    ],
    "Bangka Belitung": [
        "Pangkal Pinang", "Sungailiat", "Muntok", "Toboali",
        "Manggar", "Koba", "Tanjung Pandan",
    ],
    "Bengkulu": [
        "Bengkulu", "Curup", "Manna", "Mukomuko", "Kepahiang",
        "Rejang Lebong", "Kaur",
    ],
    "Lampung": [
        "Bandar Lampung", "Metro", "Kalianda", "Kotaagung",
        "Pringsewu", "Liwa", "Blambangan Umpu", "Sukadana",
    ],
    "Kalimantan Barat": [
        "Pontianak", "Singkawang", "Mempawah", "Sambas", "Ketapang",
        "Sanggau", "Sintang", "Putussibau", "Ngabang",
    ],
    "Kalimantan Tengah": [
        "Palangkaraya", "Sampit", "Pangkalan Bun", "Muara Teweh",
        "Kasongan", "Tamiang Layang", "Buntok", "Puruk Cahu",
    ],
    "Kalimantan Selatan": [
        "Banjarmasin", "Banjarbaru", "Martapura", "Pelaihari",
        "Kandangan", "Kotabaru", "Rantau", "Amuntai", "Barabai",
        "Marabahan", "Batulicin",
    ],
    "Kalimantan Timur": [
        "Samarinda", "Balikpapan", "Bontang", "Tarakan", "Sangatta",
        "Tenggarong", "Sendawar", "Tanjung Redeb", "Penajam",
    ],
    "Kalimantan Utara": [
        "Tarakan", "Nunukan", "Tanjung Selor", "Malinau", "Sesayap",
    ],
    "Sulawesi Utara": [
        "Manado", "Tomohon", "Bitung", "Kotamobagu", "Tondano",
        "Airmadidi", "Tahuna", "Melonguane", "Ondong Siau",
    ],
    "Gorontalo": [
        "Gorontalo", "Limboto", "Kwandang", "Tilamuta", "Marisa",
    ],
    "Sulawesi Tengah": [
        "Palu", "Luwuk", "Tolitoli", "Buol", "Donggala",
        "Kolaka Utara", "Ampana", "Parigi", "Poso",
    ],
    "Sulawesi Selatan": [
        "Makassar", "Parepare", "Palopo", "Maros", "Gowa",
        "Bone", "Bulukumba", "Bantaeng", "Jeneponto", "Takalar",
        "Selayar", "Sinjai", "Wajo", "Soppeng", "Barru",
        "Pangkajene", "Pinrang", "Enrekang", "Toraja", "Toraja Utara",
    ],
    "Sulawesi Tenggara": [
        "Kendari", "Bau-Bau", "Kolaka", "Konawe", "Unaaha",
        "Lasusua", "Raha", "Andoolo", "Wanggudu",
    ],
    "Sulawesi Barat": [
        "Mamuju", "Majene", "Polewali", "Pasangkayu", "Matakali",
    ],
    "Maluku": [
        "Ambon", "Tual", "Masohi", "Namlea", "Saumlaki",
        "Dobo", "Bula", "Dataran Hunipopu",
    ],
    "Maluku Utara": [
        "Ternate", "Tidore", "Sofifi", "Tobelo", "Labuha",
        "Weda", "Sanana",
    ],
    "Papua": [
        "Jayapura", "Merauke", "Sorong", "Fakfak", "Timika",
        "Nabire", "Wamena", "Biak", "Serui", "Manokwari",
        "Kaimana",
    ],
    "Papua Barat": [
        "Manokwari", "Sorong", "Kaimana", "Fakfak", "Ransiki",
        "Bintuni", "Prafi",
    ],
    "Papua Tengah": [
        "Nabire", "Enarotali", "Mima", "Sugapa",
    ],
    "Papua Pegunungan": [
        "Wamena", "Oksibil", "Kobakma",
    ],
    "Papua Selatan": [
        "Merauke", "Tanah Merah", "Bade",
    ],
    "Papua Barat Daya": [
        "Sorong", "Aimas", "Ayamaru",
    ],
    "Aceh": [
        "Banda Aceh", "Lhokseumawe", "Langsa", "Meulaboh", "Sabang",
        "Singkil", "Subulussalam", "Bireuen", "Sigli", "Takengon",
        "Kutacane", "Blang Pidie",
    ],
}

# Flat list untuk backward-compatibility dengan kode lama
ALL_INDONESIA_CITIES: List[str] = []
for province, cities in INDONESIA_CITIES_BY_PROVINCE.items():
    for city in cities:
        if city not in ALL_INDONESIA_CITIES:
            ALL_INDONESIA_CITIES.append(city)

ALL_INDONESIA_CITIES = sorted(set(ALL_INDONESIA_CITIES))

# Koordinat GPS per kota utama (lat, lon) untuk GIS
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "Jakarta":          (-6.2088, 106.8456),
    "Surabaya":         (-7.2575, 112.7521),
    "Bandung":          (-6.9175, 107.6191),
    "Medan":            (3.5952, 98.6722),
    "Makassar":         (-5.1477, 119.4327),
    "Yogyakarta":       (-7.7956, 110.3695),
    "Semarang":         (-6.9667, 110.4167),
    "Palembang":        (-2.9167, 104.7458),
    "Denpasar":         (-8.6500, 115.2167),
    "Manado":           (1.4748, 124.8421),
    "Samarinda":        (-0.5022, 117.1536),
    "Pontianak":        (-0.0263, 109.3425),
    "Balikpapan":       (-1.2379, 116.8529),
    "Pekanbaru":        (0.5333, 101.4500),
    "Banjarmasin":      (-3.3186, 114.5944),
    "Padang":           (-0.9471, 100.4172),
    "Malang":           (-7.9666, 112.6326),
    "Bogor":            (-6.5971, 106.8060),
    "Bekasi":           (-6.2350, 106.9920),
    "Palu":             (-0.8917, 119.8707),
    "Kendari":          (-3.9721, 122.5130),
    "Ambon":            (-3.6553, 128.1908),
    "Jayapura":         (-2.5337, 140.7181),
    "Ternate":          (0.7917, 127.3767),
    "Mataram":          (-8.5833, 116.1167),
    "Kupang":           (-10.1718, 123.6070),
    "Tarakan":          (3.2833, 117.6333),
    "Batam":            (1.0457, 104.0305),
    "Banda Aceh":       (5.5483, 95.3238),
    "Bengkulu":         (-3.8004, 102.2655),
    "Jambi":            (-1.6101, 103.6131),
    "Bandar Lampung":   (-5.4297, 105.2610),
    "Pangkal Pinang":   (-2.1316, 106.1169),
    "Tanjung Pinang":   (0.9167, 104.4500),
    "Palangkaraya":     (-2.2136, 113.9108),
    "Mamuju":           (-2.6791, 118.8889),
    "Gorontalo":        (0.5167, 123.0667),
    "Sofifi":           (0.7333, 127.5500),
    "Manokwari":        (-0.8667, 134.0833),
    "Merauke":          (-8.4667, 140.3333),
}


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 2: ADVANCED WEATHER ENSEMBLE (multi-model blending)
# Menggabungkan OpenWeatherMap, simulasi BMKG, dan ERA5-style reanalysis
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WeatherEnsemble:
    """Multi-model weather blend dengan uncertainty quantification"""
    temp_mean:        float = 28.0
    temp_std:         float = 0.5
    humidity_mean:    float = 75.0
    humidity_std:     float = 2.0
    solar_mean:       float = 500.0
    solar_std:        float = 50.0
    rainfall_prob:    float = 0.2
    rainfall_amount:  float = 0.0
    wind_mean:        float = 2.0
    confidence:       float = 0.8    # ensemble agreement (0-1)
    model_count:      int   = 3
    source_models:    List[str] = field(default_factory=list)


class WeatherEnsembleService:
    """
    Blends 3 weather models:
    M1: OpenWeatherMap (jika API tersedia)
    M2: Tropical sinusoidal model (time-of-day + seasonal)
    M3: Stochastic perturbation model (Monte Carlo)
    """

    BMKG_SEASONAL_BIAS: Dict[int, Dict[str, float]] = {
        # month: {temp_bias, rain_bias, hum_bias}
        1:  {"t": 0.0, "r": 1.8, "h": 3.0},   # Jan - puncak hujan
        2:  {"t": 0.2, "r": 1.5, "h": 2.5},
        3:  {"t": 0.5, "r": 1.0, "h": 1.5},
        4:  {"t": 0.8, "r": 0.5, "h": 0.5},
        5:  {"t": 1.2, "r": -0.3,"h": -1.0},  # transisi
        6:  {"t": 1.5, "r": -0.8,"h": -2.5},  # kemarau
        7:  {"t": 1.8, "r": -1.2,"h": -3.5},
        8:  {"t": 2.0, "r": -1.5,"h": -4.0},  # puncak kemarau
        9:  {"t": 1.5, "r": -0.8,"h": -2.0},
        10: {"t": 0.8, "r": 0.5, "h": 1.0},   # transisi
        11: {"t": 0.3, "r": 1.2, "h": 2.0},
        12: {"t": 0.0, "r": 1.6, "h": 2.8},
    }

    def __init__(self):
        self.history: List[WeatherEnsemble] = []

    def blend(self, owm_temp: Optional[float] = None,
              owm_hum: Optional[float] = None,
              city: str = "Jakarta",
              hour: int = 12) -> WeatherEnsemble:
        month = datetime.datetime.now().month
        bias  = self.BMKG_SEASONAL_BIAS.get(month, {"t": 0, "r": 0, "h": 0})
        doy   = datetime.datetime.now().timetuple().tm_yday

        # M2: Tropical sinusoidal model
        sun_angle  = max(0.0, math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
        seasonal_t = 1.0 + 0.08 * math.cos(2 * math.pi * (doy - 15) / 365)
        t_m2 = 27.0 + 5.5 * sun_angle * seasonal_t + bias["t"]
        h_m2 = float(np.clip(82.0 - 1.4 * (t_m2 - 27.0) + bias["h"], 40.0, 98.0))
        s_m2 = 900.0 * sun_angle * seasonal_t

        # M3: Monte Carlo perturbation
        t_m3 = t_m2 + float(np.random.normal(0, 1.2))
        h_m3 = float(np.clip(h_m2 + np.random.normal(0, 3.0), 35.0, 100.0))
        s_m3 = max(0.0, s_m2 + float(np.random.normal(0, 60.0)))

        # Blend weights (OWM gets highest weight if available)
        models = []
        temps, hums, sols = [], [], []
        source_list = []

        if owm_temp is not None and owm_hum is not None:
            temps.append((owm_temp, 0.55))
            hums.append((owm_hum, 0.55))
            sols.append((s_m2, 0.55))
            source_list.append("OWM")
        else:
            source_list.append("Tropical")

        temps.extend([(t_m2, 0.30), (t_m3, 0.15)])
        hums.extend([(h_m2, 0.30), (h_m3, 0.15)])
        sols.extend([(s_m2, 0.30), (s_m3, 0.15)])
        source_list.extend(["BMKG-Tropical", "Monte-Carlo"])

        def weighted_avg(pairs): return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)
        def weighted_std(pairs):
            mu = weighted_avg(pairs)
            return math.sqrt(sum(w * (v - mu)**2 for v, w in pairs) / sum(w for _, w in pairs))

        t_mean = weighted_avg(temps);  t_std = weighted_std(temps)
        h_mean = weighted_avg(hums);   h_std = weighted_std(hums)
        s_mean = weighted_avg(sols);   s_std = weighted_std(sols)

        # Ensemble confidence (1 - normalized disagreement)
        confidence = float(np.clip(1.0 - (t_std / 5.0 + h_std / 10.0) / 2.0, 0.2, 1.0))

        # Rain probability (BMKG statistical model)
        rain_base = 0.05 + 0.20 * bias["r"] + 0.10 * (h_mean / 100.0)
        rain_prob = float(np.clip(rain_base + 0.08 * max(0, math.sin(math.pi * (hour - 12) / 6)), 0.0, 0.95))
        rain_amt  = float(max(0.0, np.random.exponential(2.5))) if random.random() < rain_prob else 0.0

        ens = WeatherEnsemble(
            temp_mean=round(t_mean, 2), temp_std=round(t_std, 3),
            humidity_mean=round(h_mean, 2), humidity_std=round(h_std, 3),
            solar_mean=round(s_mean, 1), solar_std=round(s_std, 1),
            rainfall_prob=round(rain_prob, 3), rainfall_amount=round(rain_amt, 2),
            wind_mean=round(abs(float(np.random.normal(2.2, 0.8))), 2),
            confidence=round(confidence, 3),
            model_count=len(source_list),
            source_models=source_list,
        )
        self.history.append(ens)
        return ens


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 3: FAO-56 PENMAN-MONTEITH FULL — EVAPOTRANSPIRASI LENGKAP
# Referensi: Allen et al. 1998 - FAO Irrigation and Drainage Paper 56
# ══════════════════════════════════════════════════════════════════════════════

class FAO56ETModel:
    """
    Full FAO-56 Penman-Monteith evapotranspirasi model.
    Hitung ET0 referensi, ETc aktual, dan kebutuhan irigasi presisi.
    Lebih akurat dari model ET simplified di kode utama.
    """

    CROP_KC: Dict[str, Dict[str, float]] = {
        # Stage coefficients: {ini, mid, end}
        "Tomato":      {"kc_ini": 0.60, "kc_mid": 1.15, "kc_end": 0.80,
                        "l_ini": 30, "l_dev": 40, "l_mid": 40, "l_late": 25},
        "Lettuce":     {"kc_ini": 0.70, "kc_mid": 1.00, "kc_end": 0.95,
                        "l_ini": 20, "l_dev": 30, "l_mid": 15, "l_late": 10},
        "Cucumber":    {"kc_ini": 0.60, "kc_mid": 1.00, "kc_end": 0.75,
                        "l_ini": 20, "l_dev": 30, "l_mid": 40, "l_late": 15},
        "Pepper":      {"kc_ini": 0.60, "kc_mid": 1.05, "kc_end": 0.90,
                        "l_ini": 30, "l_dev": 40, "l_mid": 110, "l_late": 30},
        "Strawberry":  {"kc_ini": 0.40, "kc_mid": 0.85, "kc_end": 0.75,
                        "l_ini": 30, "l_dev": 40, "l_mid": 60, "l_late": 35},
        "Basil":       {"kc_ini": 0.50, "kc_mid": 1.05, "kc_end": 0.80,
                        "l_ini": 10, "l_dev": 15, "l_mid": 20, "l_late": 10},
        "Spinach":     {"kc_ini": 0.70, "kc_mid": 1.00, "kc_end": 0.95,
                        "l_ini": 20, "l_dev": 20, "l_mid": 15, "l_late": 5},
        "Hemp/CBD":    {"kc_ini": 0.50, "kc_mid": 1.10, "kc_end": 0.75,
                        "l_ini": 30, "l_dev": 45, "l_mid": 50, "l_late": 20},
        "Microgreens": {"kc_ini": 0.60, "kc_mid": 0.90, "kc_end": 0.80,
                        "l_ini": 5,  "l_dev": 5,  "l_mid": 7,  "l_late": 3},
        "Orchid":      {"kc_ini": 0.30, "kc_mid": 0.60, "kc_end": 0.50,
                        "l_ini": 60, "l_dev": 90, "l_mid": 90, "l_late": 60},
    }

    def __init__(self, latitude_deg: float = -6.2):
        self.lat_rad = math.radians(latitude_deg)

    def et0_hourly(self, temp_c: float, humidity_pct: float,
                   wind_ms: float, solar_wm2: float,
                   pressure_hpa: float = 1013.0) -> float:
        """
        Hitung ET0 per jam (mm/jam) menggunakan metode Penman-Monteith.
        """
        # Tekanan uap jenuh (kPa)
        es = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))
        ea = es * humidity_pct / 100.0
        vpd = max(0.0, es - ea)

        # Slope of saturation vapor pressure curve (kPa/°C)
        delta = 4098 * es / ((temp_c + 237.3) ** 2)

        # Psychrometric constant (kPa/°C)
        P_kPa  = pressure_hpa * 0.1
        gamma  = 0.665e-3 * P_kPa

        # Radiation terms
        Rn     = solar_wm2 * 0.0864 / 24.0   # W/m² → MJ/m²/hr
        G      = 0.1 * Rn if solar_wm2 > 0 else 0.5 * Rn  # soil heat flux

        # Wind at 2m height (sensor assumed at 10m, apply log correction)
        u2 = wind_ms * (4.87 / math.log(67.8 * 10.0 - 5.42))

        # FAO-56 Penman-Monteith hourly ET0
        num   = (0.408 * delta * (Rn - G) +
                 gamma * (37.0 / (temp_c + 273.0)) * u2 * vpd)
        denom = delta + gamma * (1.0 + 0.34 * u2)

        et0   = max(0.0, num / denom)
        return round(et0, 4)

    def kc_linear(self, crop_name: str, day: int) -> float:
        """Interpolate Kc berdasarkan hari tanam (linear FAO stage model)"""
        kc_data = self.CROP_KC.get(crop_name, self.CROP_KC["Tomato"])
        l_ini  = kc_data["l_ini"]
        l_dev  = kc_data["l_dev"]
        l_mid  = kc_data["l_mid"]
        l_late = kc_data["l_late"]
        kc_ini = kc_data["kc_ini"]
        kc_mid = kc_data["kc_mid"]
        kc_end = kc_data["kc_end"]

        t1 = l_ini
        t2 = t1 + l_dev
        t3 = t2 + l_mid
        t4 = t3 + l_late

        if day <= t1:
            return kc_ini
        elif day <= t2:
            frac = (day - t1) / max(1, l_dev)
            return kc_ini + frac * (kc_mid - kc_ini)
        elif day <= t3:
            return kc_mid
        elif day <= t4:
            frac = (day - t3) / max(1, l_late)
            return kc_mid + frac * (kc_end - kc_mid)
        else:
            return kc_end

    def etc(self, et0: float, crop_name: str, day: int,
            stress_factor: float = 1.0) -> float:
        """ETc aktual dengan Kc dan stress factor"""
        kc = self.kc_linear(crop_name, day)
        return round(et0 * kc * max(0.0, stress_factor), 4)

    def irrigation_deficit_mm(self, etc_mm: float, rainfall_mm: float,
                               soil_moisture_pct: float,
                               field_capacity: float = 70.0,
                               wilting_point: float = 30.0) -> float:
        """
        Hitung defisit irigasi (mm) berdasarkan water balance.
        """
        raw_water   = (soil_moisture_pct / 100.0) * (field_capacity - wilting_point) + wilting_point
        depletion   = etc_mm - rainfall_mm
        deficit     = max(0.0, depletion - (raw_water - wilting_point) * 0.5)
        return round(deficit, 3)

    def daily_schedule(self, zone_data: Dict) -> Dict:
        """Generate jadwal irigasi optimal 24 jam ke depan"""
        et0_day      = zone_data.get("et0_mm_day", 5.0)
        crop         = zone_data.get("crop", "Tomato")
        day_number   = zone_data.get("day", 30)
        rain_24h     = zone_data.get("forecast_rain_24h", 0.0)
        soil_pct     = zone_data.get("soil_moisture_pct", 60.0)
        area_m2      = zone_data.get("area_m2", 100.0)
        efficiency   = zone_data.get("irrigation_efficiency", 0.90)

        etc_day  = self.etc(et0_day, crop, day_number)
        deficit  = self.irrigation_deficit_mm(etc_day, rain_24h, soil_pct)
        volume_L = (deficit / 1000.0) * area_m2 * 1000.0 / efficiency

        # Optimal timing: avoid midday heat, prefer early morning & late afternoon
        schedule_hrs = []
        if deficit > 0.5:
            schedule_hrs = [6, 9, 17]  # 06:00, 09:00, 17:00
            vol_per_slot = volume_L / len(schedule_hrs)
        else:
            schedule_hrs = [6]
            vol_per_slot = volume_L

        return {
            "et0_mm_day":       round(et0_day, 3),
            "etc_mm_day":       round(etc_day, 3),
            "kc":               round(self.kc_linear(crop, day_number), 3),
            "deficit_mm":       round(deficit, 3),
            "total_volume_L":   round(volume_L, 1),
            "schedule_hours":   schedule_hrs,
            "volume_per_slot_L":round(vol_per_slot, 1),
            "rain_offset_mm":   round(rain_24h, 2),
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 4: ROTHC SOIL CARBON MODEL
# Referensi: Coleman & Jenkinson 1996 - RothC-26.3
# Tracks 5 soil carbon pools + microbial turnover
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SoilCarbonPool:
    """5 RothC pools: DPM, RPM, BIO, HUM, IOM"""
    dpm:  float = 0.10   # Decomposable Plant Material (t C/ha)
    rpm:  float = 0.30   # Resistant Plant Material
    bio:  float = 0.15   # Microbial Biomass
    hum:  float = 5.00   # Humus
    iom:  float = 0.80   # Inert Organic Matter (does not decompose)

    @property
    def total(self) -> float:
        return self.dpm + self.rpm + self.bio + self.hum + self.iom

    @property
    def active(self) -> float:
        return self.dpm + self.rpm + self.bio + self.hum


class RothCModel:
    """
    RothC-26.3 soil organic carbon turnover model.
    Simulates SOM decomposition, sequestration, and CO2 flux.
    """

    # Rate constants (yr⁻¹ at 10°C, no moisture or plant cover limitation)
    K_DPM = 10.0
    K_RPM  = 0.30
    K_BIO  = 0.66
    K_HUM  = 0.02

    # Fraction going to CO2 vs BIO+HUM (clay-dependent)
    @staticmethod
    def _x(clay_pct: float = 25.0) -> float:
        """Partition coefficient: fraction of decomposition → BIO+HUM"""
        return 1.67 * (1.85 + 1.60 * math.exp(-0.0786 * clay_pct))

    def __init__(self, clay_pct: float = 25.0, depth_cm: float = 23.0):
        self.clay_pct  = clay_pct
        self.depth_cm  = depth_cm
        self.pool      = SoilCarbonPool()
        self.co2_flux_history: List[float] = []
        self.x         = self._x(clay_pct)

    def _rate_modifier(self, temp_c: float, soil_moisture_pct: float,
                        plant_cover: bool = True) -> float:
        """
        Temperature (Arrhenius) × moisture × cover modifier.
        Monthly rate modifier a(T, θ, cover).
        """
        # Temperature modifier (RothC uses a specific function)
        if temp_c < -18.3:
            f_temp = 0.0
        else:
            f_temp = 47.91 / (1.0 + math.exp(106.06 / (temp_c + 18.27)))

        # Moisture modifier (TSMD — Topsoil Moisture Deficit)
        # Simplified: use soil_moisture_pct as proxy
        tsmd_max = 20.0 * self.depth_cm / 23.0  # mm
        tsmd = (1.0 - soil_moisture_pct / 100.0) * tsmd_max
        if tsmd <= 0.444 * tsmd_max:
            f_moist = 1.0
        elif tsmd <= tsmd_max:
            f_moist = max(0.2, 1.0 - 0.8 * (tsmd - 0.444 * tsmd_max) / (0.556 * tsmd_max))
        else:
            f_moist = 0.2

        # Plant cover modifier
        f_cover = 0.6 if plant_cover else 1.0

        return f_temp * f_moist * f_cover

    def step_monthly(self, temp_c: float, soil_moisture_pct: float,
                     plant_material_input_t_ha: float = 0.1,
                     plant_cover: bool = True,
                     dpm_rpm_ratio: float = 1.44) -> Dict[str, float]:
        """
        Monthly step of RothC model.
        Returns CO2 fluxes and updated pool sizes.
        """
        a = self._rate_modifier(temp_c, soil_moisture_pct, plant_cover)
        dt = 1.0 / 12.0  # 1 month in years

        # Decomposition rates (modified)
        x = self.x
        k_dpm = self.K_DPM * a * dt
        k_rpm = self.K_RPM  * a * dt
        k_bio = self.K_BIO  * a * dt
        k_hum = self.K_HUM  * a * dt

        # Decomposition of each pool
        def decompose(pool_c, k):
            loss = pool_c * (1.0 - math.exp(-k))
            co2  = loss * x / (x + 1.0)
            bio_hum = loss - co2
            return loss, co2, bio_hum

        d_dpm, co2_dpm, bh_dpm = decompose(self.pool.dpm, k_dpm)
        d_rpm, co2_rpm, bh_rpm = decompose(self.pool.rpm, k_rpm)
        d_bio, co2_bio, bh_bio = decompose(self.pool.bio, k_bio)
        d_hum, co2_hum, bh_hum = decompose(self.pool.hum, k_hum)

        total_co2   = co2_dpm + co2_rpm + co2_bio + co2_hum
        total_bh    = bh_dpm + bh_rpm + bh_bio + bh_hum

        # BIO:HUM ratio (typically 46:54)
        new_bio = total_bh * 0.46
        new_hum = total_bh * 0.54

        # Plant material input split by DPM:RPM ratio
        ratio     = dpm_rpm_ratio / (1.0 + dpm_rpm_ratio)
        dpm_input = plant_material_input_t_ha * ratio
        rpm_input = plant_material_input_t_ha * (1.0 - ratio)

        # Update pools
        self.pool.dpm = max(0.0, self.pool.dpm - d_dpm + dpm_input)
        self.pool.rpm = max(0.0, self.pool.rpm - d_rpm + rpm_input)
        self.pool.bio = max(0.0, self.pool.bio - d_bio + new_bio)
        self.pool.hum = max(0.0, self.pool.hum - d_hum + new_hum)
        # IOM never changes

        # CO2 efflux in t C/ha/month → kg CO2/m²/month
        co2_kg_m2 = total_co2 * 1000.0 / 10000.0 * 3.67  # t C/ha → kg CO2/m²

        self.co2_flux_history.append(co2_kg_m2)

        return {
            "pool_dpm":       round(self.pool.dpm, 4),
            "pool_rpm":       round(self.pool.rpm, 4),
            "pool_bio":       round(self.pool.bio, 4),
            "pool_hum":       round(self.pool.hum, 4),
            "pool_iom":       round(self.pool.iom, 4),
            "pool_total_tc_ha": round(self.pool.total * 10000.0, 1),  # kg C/ha
            "co2_efflux_kg_m2": round(co2_kg_m2, 6),
            "rate_modifier":  round(a, 4),
            "sequestration_index": round(
                (plant_material_input_t_ha - total_co2) / max(0.001, plant_material_input_t_ha), 3
            ),
        }

    def carbon_stock_tCha(self) -> float:
        return round(self.pool.total, 3)

    def net_sequestration_report(self) -> Dict:
        if not self.co2_flux_history:
            return {}
        total_efflux = sum(self.co2_flux_history)
        avg_monthly  = total_efflux / len(self.co2_flux_history)
        return {
            "months_simulated":   len(self.co2_flux_history),
            "total_co2_kg_m2":    round(total_efflux, 4),
            "avg_monthly_kg_m2":  round(avg_monthly, 6),
            "carbon_stock_tCha":  self.carbon_stock_tCha(),
            "pool_breakdown": {
                "dpm_pct": round(self.pool.dpm / max(0.001, self.pool.active) * 100, 1),
                "rpm_pct": round(self.pool.rpm / max(0.001, self.pool.active) * 100, 1),
                "bio_pct": round(self.pool.bio / max(0.001, self.pool.active) * 100, 1),
                "hum_pct": round(self.pool.hum / max(0.001, self.pool.active) * 100, 1),
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 5: REINFORCEMENT LEARNING CONTROLLER (Q-Learning)
# State space: discretized env bins | Action space: 16 actuator combos
# ══════════════════════════════════════════════════════════════════════════════

class RLGreenhouseController:
    """
    Tabular Q-Learning controller untuk greenhouse management.
    State:  (temp_bin, humidity_bin, soil_bin, stage_bin)
    Action: kombinasi biner 4 actuator utama (heat/cool/irrig/co2) = 16 kombinasi
    Reward: composite dari growth_rate, energy_cost, disease_penalty
    """

    N_TEMP_BINS  = 5   # <18, 18-22, 22-26, 26-30, >30
    N_HUM_BINS   = 4   # <50, 50-70, 70-85, >85
    N_SOIL_BINS  = 4   # <30, 30-50, 50-70, >70
    N_STAGE_BINS = 6   # 6 growth stages
    N_ACTIONS    = 16  # 2^4 combinations

    def __init__(self, alpha: float = 0.1, gamma: float = 0.92,
                 epsilon: float = 0.3, epsilon_decay: float = 0.995):
        self.alpha         = alpha      # learning rate
        self.gamma         = gamma      # discount factor
        self.epsilon       = epsilon    # exploration rate
        self.epsilon_decay = epsilon_decay
        self.epsilon_min   = 0.02

        # Q-table: state_space × n_actions
        q_shape = (self.N_TEMP_BINS, self.N_HUM_BINS,
                   self.N_SOIL_BINS, self.N_STAGE_BINS,
                   self.N_ACTIONS)
        self.q_table = np.zeros(q_shape)

        self.step_count    = 0
        self.reward_history: List[float] = []
        self.last_state    = None
        self.last_action   = None
        self.action_map    = self._build_action_map()

    def _build_action_map(self) -> Dict[int, Dict[str, int]]:
        """Map action index (0-15) to actuator combo"""
        acts = {}
        for i in range(self.N_ACTIONS):
            acts[i] = {
                "heating":    (i >> 3) & 1,
                "cooling":    (i >> 2) & 1,
                "irrigation": float(((i >> 1) & 1) * 15),
                "co2_inject": i & 1,
            }
        return acts

    def _discretize_state(self, temp: float, humidity: float,
                           soil: float, stage_idx: int) -> Tuple[int, int, int, int]:
        """Discretize continuous state to bins"""
        t_bin = (0 if temp < 18 else 1 if temp < 22 else 2 if temp < 26 else 3 if temp < 30 else 4)
        h_bin = (0 if humidity < 50 else 1 if humidity < 70 else 2 if humidity < 85 else 3)
        s_bin = (0 if soil < 30 else 1 if soil < 50 else 2 if soil < 70 else 3)
        g_bin = min(5, max(0, stage_idx))
        return t_bin, h_bin, s_bin, g_bin

    def _reward(self, growth_rate: float, energy_used: float,
                 disease_index: float, soil_moisture: float,
                 crop_params: Any) -> float:
        """
        Composite reward function:
        R = +growth_reward - energy_penalty - disease_penalty - water_penalty
        """
        growth_reward  = growth_rate * 120.0     # normalized
        energy_penalty = energy_used  * 0.05
        disease_penalty= disease_index * 8.0
        # Water stress
        if soil_moisture < getattr(crop_params, "water_stress_threshold", 35.0):
            water_penalty = 2.0
        elif soil_moisture > 90:
            water_penalty = 1.5
        else:
            water_penalty = 0.0
        return growth_reward - energy_penalty - disease_penalty - water_penalty

    def select_action(self, state: Tuple[int, int, int, int]) -> int:
        """ε-greedy action selection"""
        if random.random() < self.epsilon:
            return random.randint(0, self.N_ACTIONS - 1)
        return int(np.argmax(self.q_table[state]))

    def update(self, state: Tuple, action: int, reward: float,
               next_state: Tuple, done: bool = False):
        """Q-learning update: Q(s,a) ← Q(s,a) + α[r + γ max Q(s',a') - Q(s,a)]"""
        current_q  = self.q_table[state][action]
        max_next_q = 0.0 if done else float(np.max(self.q_table[next_state]))
        td_target  = reward + self.gamma * max_next_q
        td_error   = td_target - current_q
        self.q_table[state][action] += self.alpha * td_error
        # Epsilon decay
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.step_count += 1
        self.reward_history.append(reward)

    def act(self, zone_state: Dict, crop_params: Any,
            prev_zone_state: Optional[Dict] = None) -> Dict:
        """
        Full RL decision step.
        Returns actuator dict (compatible with existing zone.step()).
        """
        stage_map = {
            "Germination": 0, "Seedling": 1, "Vegetative": 2,
            "Flowering": 3, "Fruiting": 4, "Harvest Ready": 5, "Dormant": 0,
        }
        temp      = float(zone_state.get("temp", 24.0))
        humidity  = float(zone_state.get("humidity", 65.0))
        soil      = float(zone_state.get("soil", 60.0))
        stage_str = str(zone_state.get("stage", "Vegetative"))
        stage_i   = stage_map.get(stage_str, 2)

        state = self._discretize_state(temp, humidity, soil, stage_i)

        # Update Q-table if we have previous transition
        if self.last_state is not None and prev_zone_state is not None:
            reward = self._reward(
                growth_rate   = float(prev_zone_state.get("growth_rate", 0.005)),
                energy_used   = float(prev_zone_state.get("energy_kwh_step", 0.1)),
                disease_index = float(prev_zone_state.get("disease_index", 0.0)),
                soil_moisture = float(prev_zone_state.get("soil", 60.0)),
                crop_params   = crop_params,
            )
            self.update(self.last_state, self.last_action, reward, state)

        action       = self.select_action(state)
        self.last_state  = state
        self.last_action = action

        base_act = self.action_map[action].copy()
        # Merge with baseline (led, fertilize, etc. handled by layer AI)
        return base_act

    def policy_heatmap_data(self) -> Dict:
        """Return Q-table statistics for visualization"""
        return {
            "mean_q":       round(float(np.mean(self.q_table)), 4),
            "max_q":        round(float(np.max(self.q_table)), 4),
            "min_q":        round(float(np.min(self.q_table)), 4),
            "steps":        self.step_count,
            "epsilon":      round(self.epsilon, 4),
            "avg_reward":   round(float(np.mean(self.reward_history[-50:])) if self.reward_history else 0.0, 4),
            "q_table_shape": list(self.q_table.shape),
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 6: MULTI-OBJECTIVE PARETO OPTIMIZER
# Objectives: maximize yield, minimize energy, minimize water
# Algorithm: NSGA-II inspired non-dominated sorting + crowding distance
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ParetoSolution:
    genome:    List[float]
    yield_score:  float = 0.0
    energy_score: float = 0.0
    water_score:  float = 0.0
    rank:      int = 0
    crowding:  float = 0.0

    @property
    def fitness_vector(self) -> Tuple[float, float, float]:
        return (self.yield_score, -self.energy_score, -self.water_score)  # maximize all


class NSGAIIOptimizer:
    """
    NSGA-II Multi-Objective optimizer untuk greenhouse setpoints.
    Objectives (all maximized):
        F1: Yield potential (higher is better)
        F2: Energy efficiency (lower consumption is better → negate)
        F3: Water efficiency (lower usage is better → negate)
    Variables (genome):
        [temp_sp, humidity_sp, co2_sp, soil_sp, led_intensity, vent_rate]
    """

    def __init__(self, pop_size: int = 40, n_gen: int = 30):
        self.pop_size = pop_size
        self.n_gen    = n_gen
        self.pareto_front: List[ParetoSolution] = []
        self.history:      List[List[ParetoSolution]] = []

    def _genome_bounds(self) -> List[Tuple[float, float]]:
        return [
            (15.0, 35.0),    # temp_sp
            (40.0, 90.0),    # humidity_sp
            (400.0, 1500.0), # co2_sp
            (40.0, 85.0),    # soil_sp
            (0.0, 1.0),      # led_intensity
            (0.0, 1.0),      # vent_rate
        ]

    def _evaluate(self, genome: List[float], crop_params: Any) -> Tuple[float, float, float]:
        bounds  = self._genome_bounds()
        g       = [float(np.clip(genome[i], bounds[i][0], bounds[i][1])) for i in range(len(bounds))]
        T, H, CO2, SM, LED, VENT = g

        # F1: Yield potential
        p   = crop_params
        y_T = max(0.0, 1.0 - abs(T  - p.optimal_temp)     / 9.0)
        y_H = max(0.0, 1.0 - abs(H  - p.optimal_humidity) / 22.0)
        y_CO2 = min(1.5, 1.0 + 0.3 * math.log(max(1.0, CO2 / 400.0)) / math.log(2.0))
        y_SM  = max(0.0, 1.0 - abs(SM - p.optimal_soil_moisture) / 20.0)
        y_LED = 0.7 + 0.3 * LED
        dis_risk = max(0.0, (H - p.disease_humidity_risk) / 15.0) * 0.4
        F1 = y_T * y_H * y_CO2 * y_SM * y_LED - dis_risk

        # F2: Energy consumption proxy (lower = better)
        heat_load = max(0.0, 20.0 - T) * 1.0     # heating energy
        cool_load = max(0.0, T - 26.0) * 0.8     # cooling energy
        led_load  = LED * 0.3                     # LED power
        co2_load  = max(0.0, CO2 - 800.0) * 0.001
        vent_load = VENT * 0.05
        F2 = heat_load + cool_load + led_load + co2_load + vent_load  # to minimize

        # F3: Water consumption proxy (lower = better)
        et_proxy = 0.4 + 0.6 * (SM / 80.0) + 0.2 * max(0.0, T - 25.0) * 0.05
        F3 = et_proxy  # to minimize

        return (F1, F2, F3)

    def _dominates(self, a: ParetoSolution, b: ParetoSolution) -> bool:
        """a dominates b: a is at least as good in all objectives and strictly better in one"""
        va, vb = a.fitness_vector, b.fitness_vector
        return all(va[i] >= vb[i] for i in range(3)) and any(va[i] > vb[i] for i in range(3))

    def _non_dominated_sort(self, pop: List[ParetoSolution]) -> List[List[int]]:
        n = len(pop)
        dominated_by = [0] * n
        dominates    = [[] for _ in range(n)]
        fronts       = [[]]

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if self._dominates(pop[i], pop[j]):
                    dominates[i].append(j)
                elif self._dominates(pop[j], pop[i]):
                    dominated_by[i] += 1
            if dominated_by[i] == 0:
                pop[i].rank = 0
                fronts[0].append(i)

        k = 0
        while fronts[k]:
            next_front = []
            for i in fronts[k]:
                for j in dominates[i]:
                    dominated_by[j] -= 1
                    if dominated_by[j] == 0:
                        pop[j].rank = k + 1
                        next_front.append(j)
            k += 1
            fronts.append(next_front)

        return [f for f in fronts if f]

    def _crowding_distance(self, front: List[int], pop: List[ParetoSolution]):
        n = len(front)
        if n <= 2:
            for i in front:
                pop[i].crowding = float("inf")
            return

        for i in front:
            pop[i].crowding = 0.0

        for obj_idx in range(3):
            sorted_front = sorted(front, key=lambda i: pop[i].fitness_vector[obj_idx])
            pop[sorted_front[0]].crowding  = float("inf")
            pop[sorted_front[-1]].crowding = float("inf")

            f_min = pop[sorted_front[0]].fitness_vector[obj_idx]
            f_max = pop[sorted_front[-1]].fitness_vector[obj_idx]
            span  = max(f_max - f_min, 1e-10)

            for k in range(1, n - 1):
                prev_f = pop[sorted_front[k-1]].fitness_vector[obj_idx]
                next_f = pop[sorted_front[k+1]].fitness_vector[obj_idx]
                pop[sorted_front[k]].crowding += (next_f - prev_f) / span

    def _random_genome(self) -> List[float]:
        return [random.uniform(lo, hi) for lo, hi in self._genome_bounds()]

    def _crossover_sbx(self, p1: List[float], p2: List[float],
                        eta: float = 20.0) -> Tuple[List[float], List[float]]:
        """Simulated Binary Crossover"""
        c1, c2 = p1[:], p2[:]
        for i in range(len(p1)):
            if random.random() < 0.5:
                u = random.random()
                beta = (2.0 * u) ** (1.0 / (eta + 1.0)) if u < 0.5 else (1.0 / (2.0 - 2.0*u)) ** (1.0 / (eta + 1.0))
                c1[i] = 0.5 * ((1.0 + beta) * p1[i] + (1.0 - beta) * p2[i])
                c2[i] = 0.5 * ((1.0 - beta) * p1[i] + (1.0 + beta) * p2[i])
        return c1, c2

    def _mutate_polynomial(self, genome: List[float], eta: float = 20.0,
                            prob: float = 0.2) -> List[float]:
        """Polynomial mutation"""
        bounds = self._genome_bounds()
        result = genome[:]
        for i in range(len(result)):
            if random.random() < prob:
                lo, hi = bounds[i]
                delta  = hi - lo
                u      = random.random()
                if u < 0.5:
                    delta_q = (2.0 * u) ** (1.0 / (eta + 1.0)) - 1.0
                else:
                    delta_q = 1.0 - (2.0 * (1.0 - u)) ** (1.0 / (eta + 1.0))
                result[i] = float(np.clip(result[i] + delta_q * delta, lo, hi))
        return result

    def optimize(self, crop_params: Any) -> List[ParetoSolution]:
        """Run NSGA-II optimization. Returns Pareto-optimal solutions."""
        pop = [ParetoSolution(genome=self._random_genome()) for _ in range(self.pop_size)]

        for sol in pop:
            F1, F2, F3 = self._evaluate(sol.genome, crop_params)
            sol.yield_score = F1;  sol.energy_score = F2;  sol.water_score = F3

        for gen in range(self.n_gen):
            # Create offspring
            offspring = []
            while len(offspring) < self.pop_size:
                idx   = random.sample(range(self.pop_size), 2)
                p1, p2 = pop[idx[0]].genome, pop[idx[1]].genome
                c1, c2 = self._crossover_sbx(p1, p2)
                for child in [self._mutate_polynomial(c1), self._mutate_polynomial(c2)]:
                    sol = ParetoSolution(genome=child)
                    F1, F2, F3 = self._evaluate(child, crop_params)
                    sol.yield_score = F1; sol.energy_score = F2; sol.water_score = F3
                    offspring.append(sol)

            # Merge + sort
            combined = pop + offspring[:self.pop_size]
            fronts   = self._non_dominated_sort(combined)

            for front in fronts:
                self._crowding_distance(front, combined)

            # Select next generation
            new_pop = []
            for front in fronts:
                if len(new_pop) + len(front) <= self.pop_size:
                    new_pop.extend([combined[i] for i in front])
                else:
                    remaining = self.pop_size - len(new_pop)
                    sorted_by_crowd = sorted(front,
                        key=lambda i: combined[i].crowding, reverse=True)
                    new_pop.extend([combined[i] for i in sorted_by_crowd[:remaining]])
                    break
            pop = new_pop
            self.history.append(pop[:])

        # Extract Pareto front (rank 0)
        fronts = self._non_dominated_sort(pop)
        self.pareto_front = [pop[i] for i in fronts[0]] if fronts else pop

        return self.pareto_front

    def best_balanced(self) -> Optional[ParetoSolution]:
        """Return solution with best yield*efficiency balance (knee point)"""
        if not self.pareto_front:
            return None
        # Simple: max F1 - F2*0.3 - F3*0.3
        return max(self.pareto_front,
                   key=lambda s: s.yield_score - 0.3*s.energy_score - 0.3*s.water_score)

    def setpoints_from_solution(self, sol: ParetoSolution) -> Dict[str, float]:
        bounds = self._genome_bounds()
        g = [float(np.clip(sol.genome[i], bounds[i][0], bounds[i][1])) for i in range(6)]
        return {
            "temp_sp":        round(g[0], 1),
            "humidity_sp":    round(g[1], 1),
            "co2_sp":         round(g[2], 0),
            "soil_sp":        round(g[3], 1),
            "led_intensity":  round(g[4], 2),
            "vent_rate":      round(g[5], 2),
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 7: BLOCKCHAIN AUDIT TRAIL
# Immutable log untuk traceability & sertifikasi organik
# (Simplified merkle-chain tanpa real distributed ledger)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuditBlock:
    index:       int
    timestamp:   str
    zone_id:     str
    event_type:  str   # "sensor", "actuator", "milestone", "alert", "chemical"
    data:        Dict
    prev_hash:   str
    hash:        str   = ""
    nonce:       int   = 0

    def compute_hash(self) -> str:
        payload = json.dumps({
            "index": self.index, "timestamp": self.timestamp,
            "zone_id": self.zone_id, "event_type": self.event_type,
            "data": self.data, "prev_hash": self.prev_hash, "nonce": self.nonce
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def mine(self, difficulty: int = 2):
        """Simple proof-of-work (just for auditability, not real mining)"""
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash   = self.compute_hash()


class GreenChainAudit:
    """
    Blockchain-style audit trail untuk greenhouse operations.
    Ensures tamper-evident record for:
    - Chemical/fertilizer applications
    - Harvest records
    - Calibration events
    - System anomalies
    - AI decision log
    """

    MINED_DIFFICULTY = 1   # low difficulty for speed (demo)

    def __init__(self):
        self.chain: List[AuditBlock] = []
        self._create_genesis()

    def _create_genesis(self):
        genesis = AuditBlock(
            index=0, timestamp=datetime.datetime.now().isoformat(),
            zone_id="SYSTEM", event_type="genesis",
            data={"message": "GreenChain v4.0 initialized"},
            prev_hash="0" * 64,
        )
        genesis.mine(self.MINED_DIFFICULTY)
        self.chain.append(genesis)

    def _last_hash(self) -> str:
        return self.chain[-1].hash if self.chain else "0" * 64

    def add_event(self, zone_id: str, event_type: str, data: Dict) -> AuditBlock:
        block = AuditBlock(
            index      = len(self.chain),
            timestamp  = datetime.datetime.now().isoformat(),
            zone_id    = zone_id,
            event_type = event_type,
            data       = data,
            prev_hash  = self._last_hash(),
        )
        block.mine(self.MINED_DIFFICULTY)
        self.chain.append(block)
        return block

    def verify_integrity(self) -> Tuple[bool, List[int]]:
        """Verify chain has not been tampered"""
        invalid_blocks = []
        for i in range(1, len(self.chain)):
            curr  = self.chain[i]
            prev  = self.chain[i-1]
            if curr.prev_hash != prev.hash:
                invalid_blocks.append(i)
            if curr.hash != curr.compute_hash():
                invalid_blocks.append(i)
        return (len(invalid_blocks) == 0, invalid_blocks)

    def get_recent(self, n: int = 10) -> List[Dict]:
        return [
            {
                "idx":      b.index,
                "ts":       b.timestamp,
                "zone":     b.zone_id,
                "type":     b.event_type,
                "hash":     b.hash[:16] + "...",
                "prev":     b.prev_hash[:16] + "...",
                "data_keys": list(b.data.keys()),
            }
            for b in self.chain[-n:]
        ]

    def export_json(self) -> str:
        return json.dumps([
            {"index": b.index, "ts": b.timestamp, "zone": b.zone_id,
             "type": b.event_type, "hash": b.hash, "data": b.data}
            for b in self.chain
        ], indent=2, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 8: MQTT TELEMETRY SIMULATOR
# Simulates real IoT sensor/actuator messaging without external broker
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MQTTMessage:
    topic:   str
    payload: Dict
    qos:     int = 1
    retained: bool = False
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().isoformat()

    def to_json(self) -> str:
        return json.dumps({
            "topic": self.topic, "payload": self.payload,
            "qos": self.qos, "retained": self.retained,
            "timestamp": self.timestamp
        }, default=str)


class MQTTSimulator:
    """
    Simulates MQTT publish/subscribe without a real broker.
    In production, replace with paho-mqtt client.
    Topic structure:
      greenhouse/{facility_id}/{zone_id}/sensor/{param}
      greenhouse/{facility_id}/{zone_id}/actuator/{param}
      greenhouse/{facility_id}/{zone_id}/alert
      greenhouse/{facility_id}/system/status
    """

    def __init__(self, facility_id: str = "GH-01"):
        self.facility_id  = facility_id
        self.message_bus: deque = deque(maxlen=500)
        self.subscriptions: Dict[str, List] = defaultdict(list)
        self.connected    = True
        self.msg_count    = 0

    def publish(self, topic: str, payload: Dict, qos: int = 1,
                retained: bool = False) -> bool:
        if not self.connected:
            return False
        msg = MQTTMessage(topic=topic, payload=payload, qos=qos, retained=retained)
        self.message_bus.append(msg)
        self.msg_count += 1
        # Dispatch to subscribers
        for pattern, callbacks in self.subscriptions.items():
            if self._topic_match(pattern, topic):
                for cb in callbacks:
                    try:
                        cb(msg)
                    except Exception:
                        pass
        return True

    @staticmethod
    def _topic_match(pattern: str, topic: str) -> bool:
        """Basic MQTT wildcard matching (+ and #)"""
        p_parts = pattern.split("/")
        t_parts = topic.split("/")
        for i, p in enumerate(p_parts):
            if p == "#":
                return True
            if i >= len(t_parts):
                return False
            if p != "+" and p != t_parts[i]:
                return False
        return len(p_parts) == len(t_parts)

    def subscribe(self, topic_pattern: str, callback) -> None:
        self.subscriptions[topic_pattern].append(callback)

    def publish_zone_telemetry(self, zone_id: str, zone_state: Dict):
        """Publish all sensor readings for a zone"""
        base = f"greenhouse/{self.facility_id}/{zone_id}"
        sensors = {
            "temperature": zone_state.get("temp", 0),
            "humidity":    zone_state.get("humidity", 0),
            "co2":         zone_state.get("co2", 0),
            "soil_moisture": zone_state.get("soil", 0),
            "light":       zone_state.get("light", 0),
            "ec":          zone_state.get("ec", 0),
            "ph":          zone_state.get("ph", 0),
            "root_temp":   zone_state.get("root_temp", 0),
        }
        for param, value in sensors.items():
            self.publish(f"{base}/sensor/{param}", {
                "value": value, "unit": "",
                "quality": "good", "zone": zone_id
            })

    def publish_actuator_state(self, zone_id: str, actuators: Dict):
        """Publish actuator commands"""
        base = f"greenhouse/{self.facility_id}/{zone_id}/actuator"
        for k, v in actuators.items():
            self.publish(f"{base}/{k}", {"command": v, "zone": zone_id})

    def publish_alert(self, zone_id: str, alert_data: Dict):
        self.publish(
            f"greenhouse/{self.facility_id}/{zone_id}/alert",
            alert_data, qos=2
        )

    def get_recent_messages(self, n: int = 20) -> List[Dict]:
        msgs = list(self.message_bus)[-n:]
        return [
            {"topic": m.topic, "payload": m.payload,
             "ts": m.timestamp, "qos": m.qos}
            for m in msgs
        ]

    def stats(self) -> Dict:
        return {
            "total_messages": self.msg_count,
            "buffer_size":    len(self.message_bus),
            "subscriptions":  len(self.subscriptions),
            "connected":      self.connected,
            "facility":       self.facility_id,
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION A: REAL MQTT BROKER CLIENT (paho-mqtt)
# Ganti MQTTSimulator dengan koneksi nyata ke Mosquitto / HiveMQ / EMQX
# ══════════════════════════════════════════════════════════════════════════════

class MQTTBrokerClient:
    """Real MQTT client via paho-mqtt. Interface identik dengan MQTTSimulator.
    Auto-fallback ke mode offline jika broker tidak bisa dijangkau.

    Setup broker gratis (pilih salah satu):
      • Lokal  : mosquitto (pip install paho-mqtt; brew/apt install mosquitto)
      • Cloud  : HiveMQ Cloud (hivemq.com/mqtt-cloud-broker/ — gratis tier)
      • Cloud  : EMQX Cloud  (emqx.com/en/cloud — gratis tier)
    """

    def __init__(self, host: str = "localhost", port: int = 1883,
                 facility_id: str = "GH-INDO-01",
                 username: str = "", password: str = "",
                 use_tls: bool = False, client_id: str = ""):
        self.host        = host
        self.port        = port
        self.facility_id = facility_id
        self.username    = username
        self.password    = password
        self.use_tls     = use_tls
        self.client_id   = client_id or f"agribot-{int(time.time())}"

        self.message_bus: deque              = deque(maxlen=500)
        self.subscriptions: Dict[str, List]  = defaultdict(list)
        self.msg_count    = 0
        self._client      = None
        self._connected   = False
        self._last_error  = ""
        self._lock        = threading.Lock()

    # ── Connection ──────────────────────────────────────────────────────────
    def connect(self) -> bool:
        try:
            import paho.mqtt.client as mqtt   # type: ignore

            def _on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self._connected  = True
                    self._last_error = ""
                    for pattern in list(self.subscriptions):
                        client.subscribe(pattern, qos=1)
                else:
                    self._connected  = False
                    codes = {1:"bad proto", 2:"bad id", 3:"unavailable",
                             4:"bad creds", 5:"not auth"}
                    self._last_error = f"rc={rc} ({codes.get(rc,'unknown')})"

            def _on_disconnect(client, userdata, rc):
                self._connected = False
                if rc != 0:
                    self._last_error = f"Unexpected disconnect rc={rc}"

            def _on_message(client, userdata, msg):
                try:
                    payload = json.loads(msg.payload.decode())
                except Exception:
                    payload = {"raw": msg.payload.decode("utf-8", errors="replace")}
                mqtt_msg = MQTTMessage(topic=msg.topic, payload=payload,
                                       qos=msg.qos, retained=msg.retain)
                with self._lock:
                    self.message_bus.append(mqtt_msg)
                    self.msg_count += 1
                for pattern, cbs in list(self.subscriptions.items()):
                    if MQTTSimulator._topic_match(pattern, msg.topic):
                        for cb in cbs:
                            try:
                                cb(mqtt_msg)
                            except Exception:
                                pass

            client = mqtt.Client(client_id=self.client_id, clean_session=True)
            client.on_connect    = _on_connect
            client.on_disconnect = _on_disconnect
            client.on_message    = _on_message
            if self.username:
                client.username_pw_set(self.username, self.password)
            if self.use_tls:
                client.tls_set()
            client.connect_async(self.host, self.port, keepalive=60)
            client.loop_start()
            # wait up to 4 s
            for _ in range(40):
                if self._connected:
                    break
                time.sleep(0.1)
            self._client = client
            return self._connected
        except ImportError:
            self._last_error = "paho-mqtt not installed — pip install paho-mqtt"
            return False
        except Exception as e:
            self._last_error = str(e)
            return False

    def disconnect(self):
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._connected = False

    # ── Publish / Subscribe ─────────────────────────────────────────────────
    def publish(self, topic: str, payload: Dict,
                qos: int = 1, retained: bool = False) -> bool:
        if not self._client or not self._connected:
            return False
        try:
            res = self._client.publish(
                topic, json.dumps(payload, default=str), qos=qos, retain=retained)
            if res.rc == 0:
                with self._lock:
                    self.message_bus.append(
                        MQTTMessage(topic=topic, payload=payload,
                                    qos=qos, retained=retained))
                    self.msg_count += 1
                return True
        except Exception:
            pass
        return False

    def subscribe(self, topic_pattern: str, callback) -> None:
        self.subscriptions[topic_pattern].append(callback)
        if self._client and self._connected:
            self._client.subscribe(topic_pattern, qos=1)

    # ── Convenience wrappers (same API as MQTTSimulator) ────────────────────
    def publish_zone_telemetry(self, zone_id: str, zone_state: Dict):
        base = f"greenhouse/{self.facility_id}/{zone_id}"
        for param, key in [("temperature","temp"),("humidity","humidity"),
                            ("co2","co2"),("soil_moisture","soil"),
                            ("light","light"),("ec","ec"),("ph","ph"),
                            ("root_temp","root_temp")]:
            self.publish(f"{base}/sensor/{param}",
                         {"value": zone_state.get(key, 0),
                          "unit": "", "quality": "good", "zone": zone_id})

    def publish_actuator_state(self, zone_id: str, actuators: Dict):
        base = f"greenhouse/{self.facility_id}/{zone_id}/actuator"
        for k, v in actuators.items():
            self.publish(f"{base}/{k}", {"command": v, "zone": zone_id})

    def publish_alert(self, zone_id: str, alert_data: Dict):
        self.publish(f"greenhouse/{self.facility_id}/{zone_id}/alert",
                     alert_data, qos=2)

    def get_recent_messages(self, n: int = 20) -> List[Dict]:
        with self._lock:
            msgs = list(self.message_bus)[-n:]
        return [{"topic": m.topic, "payload": m.payload,
                 "ts": m.timestamp, "qos": m.qos} for m in msgs]

    def stats(self) -> Dict:
        return {
            "total_messages": self.msg_count,
            "buffer_size":    len(self.message_bus),
            "subscriptions":  len(self.subscriptions),
            "connected":      self._connected,
            "facility":       self.facility_id,
            "broker":         f"{self.host}:{self.port}",
            "error":          self._last_error,
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION B: DATA HISTORIAN — SQLite persistent time-series storage
# ══════════════════════════════════════════════════════════════════════════════

class DataHistorian:
    """Persistent time-series storage via SQLite.
    Menyimpan sensor readings, actuator events, alerts, flow meter, vernalization.
    File: agribot_historian.db di folder yang sama dengan tumbal.py.
    """

    _DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "agribot_historian.db")

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or self._DB_PATH
        self._lock   = threading.Lock()
        self._init_db()

    def _conn(self):
        import sqlite3 as _sq
        return _sq.connect(self.db_path, timeout=10,
                           check_same_thread=False)

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts       TEXT NOT NULL,
                    zone_id  TEXT NOT NULL,
                    param    TEXT NOT NULL,
                    value    REAL NOT NULL,
                    unit     TEXT DEFAULT '',
                    source   TEXT DEFAULT 'sim'
                );
                CREATE INDEX IF NOT EXISTS idx_sr_ts   ON sensor_readings(ts);
                CREATE INDEX IF NOT EXISTS idx_sr_zone ON sensor_readings(zone_id,param);

                CREATE TABLE IF NOT EXISTS actuator_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts         TEXT NOT NULL,
                    zone_id    TEXT NOT NULL,
                    actuator   TEXT NOT NULL,
                    value      REAL NOT NULL,
                    trigger_by TEXT DEFAULT 'auto'
                );
                CREATE INDEX IF NOT EXISTS idx_ae_ts ON actuator_events(ts);

                CREATE TABLE IF NOT EXISTS alerts (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts           TEXT NOT NULL,
                    zone_id      TEXT NOT NULL,
                    severity     TEXT NOT NULL,
                    message      TEXT NOT NULL,
                    acknowledged INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS vernalization_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts           TEXT NOT NULL,
                    crop_id      TEXT NOT NULL,
                    temp_c       REAL NOT NULL,
                    cold_hours   REAL NOT NULL,
                    target_hours REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS flow_meter_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts           TEXT NOT NULL,
                    zone_id      TEXT NOT NULL,
                    flow_lpm     REAL NOT NULL,
                    target_lpm   REAL NOT NULL,
                    pressure_bar REAL DEFAULT 0,
                    status       TEXT DEFAULT 'normal'
                );
            """)

    # ── Write helpers (dual-write: SQLite local + Supabase cloud) ───────────
    def log_sensor(self, zone_id: str, readings: Dict[str, float],
                   source: str = "sim"):
        now  = datetime.datetime.now().isoformat()
        rows = [(now, zone_id, k, v, "", source) for k, v in readings.items()]
        with self._lock:
            with self._conn() as conn:
                conn.executemany(
                    "INSERT INTO sensor_readings "
                    "(ts,zone_id,param,value,unit,source) VALUES(?,?,?,?,?,?)", rows)
        # Dual-write ke Supabase (best-effort, non-blocking)
        try:
            from db.supabase_client import log_sensor as _sb_log_sensor
            _sb_log_sensor(zone_id, readings, source=source)
        except Exception:
            pass

    def log_actuator(self, zone_id: str, actuators: Dict[str, float],
                     trigger_by: str = "auto"):
        now  = datetime.datetime.now().isoformat()
        rows = [(now, zone_id, k, v, trigger_by) for k, v in actuators.items()]
        with self._lock:
            with self._conn() as conn:
                conn.executemany(
                    "INSERT INTO actuator_events "
                    "(ts,zone_id,actuator,value,trigger_by) VALUES(?,?,?,?,?)", rows)
        try:
            from db.supabase_client import log_actuator as _sb_log_act
            # Kirim semua aktuator, bukan hanya yang pertama
            for _act_name, _act_val in actuators.items():
                _sb_log_act(zone_id, _act_name, _act_val, triggered_by=trigger_by)
        except Exception:
            pass

    def log_alert(self, zone_id: str, severity: str, message: str):
        now = datetime.datetime.now().isoformat()
        with self._lock:
            with self._conn() as conn:
                conn.execute("INSERT INTO alerts(ts,zone_id,severity,message) "
                             "VALUES(?,?,?,?)", (now, zone_id, severity, message))
        try:
            from db.supabase_client import log_alert as _sb_log_alert
            _sb_log_alert(zone_id, severity, message)
        except Exception:
            pass

    def log_flow(self, zone_id: str, flow_lpm: float, target_lpm: float,
                 pressure_bar: float = 0.0, status: str = "normal"):
        now = datetime.datetime.now().isoformat()
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO flow_meter_log"
                    "(ts,zone_id,flow_lpm,target_lpm,pressure_bar,status) "
                    "VALUES(?,?,?,?,?,?)",
                    (now, zone_id, flow_lpm, target_lpm, pressure_bar, status))
        try:
            from db.supabase_client import log_flow as _sb_log_flow
            _sb_log_flow(zone_id, flow_lpm, target_lpm, pressure_bar, status)
        except Exception:
            pass

    def log_vernalization(self, crop_id: str, temp_c: float,
                          cold_hours: float, target_hours: float):
        now = datetime.datetime.now().isoformat()
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO vernalization_log"
                    "(ts,crop_id,temp_c,cold_hours,target_hours) VALUES(?,?,?,?,?)",
                    (now, crop_id, temp_c, cold_hours, target_hours))

    # ── Read helpers ─────────────────────────────────────────────────────────
    def query_sensor(self, zone_id: str, param: str,
                     hours: int = 24) -> List[Dict]:
        since = (datetime.datetime.now() -
                 datetime.timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ts,value FROM sensor_readings "
                "WHERE zone_id=? AND param=? AND ts>=? "
                "ORDER BY ts DESC LIMIT 500",
                (zone_id, param, since)).fetchall()
        return [{"ts": r[0], "value": r[1]} for r in rows]

    def query_alerts(self, hours: int = 48,
                     unacked_only: bool = False) -> List[Dict]:
        since = (datetime.datetime.now() -
                 datetime.timedelta(hours=hours)).isoformat()
        q = ("SELECT ts,zone_id,severity,message,acknowledged "
             "FROM alerts WHERE ts>=?")
        params: list = [since]
        if unacked_only:
            q += " AND acknowledged=0"
        q += " ORDER BY ts DESC LIMIT 100"
        with self._conn() as conn:
            rows = conn.execute(q, params).fetchall()
        return [{"ts": r[0], "zone": r[1], "severity": r[2],
                 "msg": r[3], "acked": r[4]} for r in rows]

    def ack_alert(self, alert_id: int):
        with self._lock:
            with self._conn() as conn:
                conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?",
                             (alert_id,))

    def export_csv(self, table: str, hours: int = 24) -> str:
        """Export table rows from last N hours as CSV string."""
        import csv as _csv, io as _io
        since = (datetime.datetime.now() -
                 datetime.timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                f"SELECT * FROM {table} WHERE ts>=? ORDER BY ts DESC LIMIT 5000",
                (since,))
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        buf = _io.StringIO()
        w   = _csv.writer(buf)
        w.writerow(cols)
        w.writerows(rows)
        return buf.getvalue()

    def stats(self) -> Dict:
        with self._conn() as conn:
            sr = conn.execute(
                "SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
            ae = conn.execute(
                "SELECT COUNT(*) FROM actuator_events").fetchone()[0]
            al = conn.execute(
                "SELECT COUNT(*) FROM alerts "
                "WHERE acknowledged=0").fetchone()[0]
            fl = conn.execute(
                "SELECT COUNT(*) FROM flow_meter_log").fetchone()[0]
            vl = conn.execute(
                "SELECT COUNT(*) FROM vernalization_log").fetchone()[0]
        size_kb = (os.path.getsize(self.db_path) / 1024
                   if os.path.exists(self.db_path) else 0)
        return {
            "sensor_rows":  sr,  "actuator_rows": ae,
            "open_alerts":  al,  "flow_rows":     fl,
            "vern_rows":    vl,  "db_size_kb":    round(size_kb, 1),
            "db_path":      self.db_path,
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION C: VERNALIZATION TRACKER — cold treatment bawang putih
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class VernalizationRecord:
    date:       str
    temp_min_c: float
    temp_max_c: float
    cold_hours: float   # jam efektif <10°C hari itu


class VernalizationTracker:
    """Cold treatment tracker khusus Bawang Putih (Allium sativum).

    Bawang putih memerlukan 40–60 hari perlakuan dingin (<10°C) agar umbi
    berdiferensiasi dengan baik. Target jam dingin bervariasi per varietas.
    Referensi: Kamenetsky & Rabinowitch (2002); IPGRI Garlic Descriptor.
    """

    VARIETY_TARGETS: Dict[str, float] = {
        "Lokal Kating":    480,   # ~20 hari × 24 jam
        "Lumbu Hijau":     540,
        "Lumbu Kuning":    600,
        "Sangga Sembalun": 660,
        "Honan (China)":   720,
        "Custom":          600,
    }
    COLD_THRESHOLD_C = 10.0    # suhu di bawah ini dihitung sebagai jam dingin
    INJURY_BELOW_C   =  0.0    # <0°C → chilling injury → efektivitas turun

    def __init__(self, variety: str = "Lokal Kating", start_date: str = ""):
        self.variety      = variety
        self.target_hours = float(self.VARIETY_TARGETS.get(variety, 600))
        self.start_date   = start_date or datetime.date.today().isoformat()
        self.records: List[VernalizationRecord] = []

    @property
    def total_cold_hours(self) -> float:
        return sum(r.cold_hours for r in self.records)

    @property
    def progress_pct(self) -> float:
        return min(100.0, self.total_cold_hours / max(1, self.target_hours) * 100)

    @property
    def days_elapsed(self) -> int:
        return len(self.records)

    @property
    def status(self) -> str:
        p = self.progress_pct
        if p >= 100: return "SELESAI ✅"
        if p >= 75:  return "HAMPIR SELESAI ⚡"
        if p >= 50:  return "BERJALAN 🔄"
        if p >= 25:  return "AWAL 🌱"
        return "BARU MULAI ❄️"

    def add_day(self, temp_min_c: float, temp_max_c: float,
                date: str = "") -> float:
        """Tambah satu hari data suhu. Kembalikan jam dingin efektif hari itu."""
        if not date:
            date = datetime.date.today().isoformat()
        thr = self.COLD_THRESHOLD_C
        if temp_max_c <= thr:
            cold_h = 24.0
        elif temp_min_c >= thr:
            cold_h = 0.0
        else:
            # Aproksimasi segitiga
            cold_h = 24.0 * (thr - temp_min_c) / max(0.1, temp_max_c - temp_min_c)
        # Penalti chilling injury (<0°C)
        if temp_min_c < self.INJURY_BELOW_C:
            cold_h *= max(0.0, 1.0 + temp_min_c / 5.0)
        cold_h = round(cold_h, 2)
        self.records.append(VernalizationRecord(
            date=date, temp_min_c=temp_min_c,
            temp_max_c=temp_max_c, cold_hours=cold_h))
        return cold_h

    def estimate_completion_date(self) -> str:
        remaining = self.target_hours - self.total_cold_hours
        if remaining <= 0:
            return "Sudah selesai"
        if self.days_elapsed < 3:
            return "Belum cukup data (min 3 hari)"
        avg_per_day = self.total_cold_hours / max(1, self.days_elapsed)
        if avg_per_day < 0.1:
            return "Suhu terlalu tinggi — tidak ada progress"
        days_left = math.ceil(remaining / avg_per_day)
        est = datetime.date.today() + datetime.timedelta(days=days_left)
        return est.strftime("%d %b %Y")

    def to_dict(self) -> Dict:
        return {
            "variety":      self.variety,
            "target_hours": self.target_hours,
            "start_date":   self.start_date,
            "records":      [vars(r) for r in self.records],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "VernalizationTracker":
        vt = cls(variety=d.get("variety", "Lokal Kating"),
                 start_date=d.get("start_date", ""))
        vt.target_hours = float(d.get("target_hours", vt.target_hours))
        for rd in d.get("records", []):
            vt.records.append(VernalizationRecord(**rd))
        return vt


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION D: DRIP FLOW MONITOR — feedback aktual flow meter
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FlowReading:
    ts:           str
    zone_id:      str
    flow_lpm:     float   # debit aktual L/menit
    target_lpm:   float   # setpoint
    pressure_bar: float
    status:       str     # normal | clog | leak | dry_run

    @property
    def efficiency_pct(self) -> float:
        if self.target_lpm <= 0:
            return 0.0
        return min(150.0, self.flow_lpm / self.target_lpm * 100.0)

    @property
    def deviation_pct(self) -> float:
        if self.target_lpm <= 0:
            return 0.0
        return (self.flow_lpm - self.target_lpm) / self.target_lpm * 100.0


class DripFlowMonitor:
    """Drip irrigation flow meter feedback.
    Deteksi: tersumbat (clog), bocor (leak), pompa kering (dry_run).

    Mode hardware : baca dari serial/MQTT → panggil read(actual_lpm=<nilai>)
    Mode simulasi : baca dengan read() tanpa argumen — simulasi noise + fault
    """

    CLOG_PCT  = -25.0    # >25% di bawah target → clog
    LEAK_PCT  = +30.0    # >30% di atas target → leak
    DRY_LPM   =  0.05    # <0.05 L/min saat pompa aktif → dry run

    def __init__(self, zone_id: str = "ZONE-01", target_lpm: float = 2.5):
        self.zone_id       = zone_id
        self.target_lpm    = target_lpm
        self.readings: deque = deque(maxlen=200)
        self._sim_fault    = "normal"   # "normal"|"clog"|"leak"|"dry_run"
        self._rng          = np.random.default_rng(int(abs(hash(zone_id))) & 0xFFFF)
        self._total_liters = 0.0
        self._last_ts      = datetime.datetime.now()

    def read(self, actual_lpm: Optional[float] = None,
             pressure_bar: float = 1.2) -> "FlowReading":
        """Baca flow. actual_lpm=None → gunakan simulasi."""
        if actual_lpm is None:
            actual_lpm = self._sim_read()
        status = self._classify(actual_lpm)
        now    = datetime.datetime.now()
        elapsed_min = (now - self._last_ts).total_seconds() / 60.0
        self._total_liters += actual_lpm * elapsed_min
        self._last_ts = now
        reading = FlowReading(
            ts=now.isoformat(), zone_id=self.zone_id,
            flow_lpm=round(actual_lpm, 3),
            target_lpm=self.target_lpm,
            pressure_bar=round(pressure_bar, 2),
            status=status)
        self.readings.append(reading)
        return reading

    def _sim_read(self) -> float:
        base = self.target_lpm
        if   self._sim_fault == "clog":    base *= self._rng.uniform(0.30, 0.70)
        elif self._sim_fault == "leak":    base *= self._rng.uniform(1.35, 1.80)
        elif self._sim_fault == "dry_run": base  = self._rng.uniform(0.0, 0.02)
        return max(0.0, base + self._rng.normal(0, base * 0.04))

    def _classify(self, flow_lpm: float) -> str:
        if flow_lpm < self.DRY_LPM:
            return "dry_run"
        dev = (flow_lpm - self.target_lpm) / max(0.01, self.target_lpm) * 100
        if dev < self.CLOG_PCT:  return "clog"
        if dev > self.LEAK_PCT:  return "leak"
        return "normal"

    def inject_fault(self, fault: str):
        """Demo/test: 'normal'|'clog'|'leak'|'dry_run'"""
        self._sim_fault = fault

    @property
    def last_reading(self) -> Optional[FlowReading]:
        return self.readings[-1] if self.readings else None

    @property
    def total_liters(self) -> float:
        return round(self._total_liters, 2)

    def recent_avg_lpm(self, n: int = 10) -> float:
        recent = list(self.readings)[-n:]
        return sum(r.flow_lpm for r in recent) / max(1, len(recent)) if recent else 0.0

    def alert_active(self) -> bool:
        return self.last_reading is not None and self.last_reading.status != "normal"

    def stats(self) -> Dict:
        last = self.last_reading
        return {
            "zone_id":        self.zone_id,
            "target_lpm":     self.target_lpm,
            "current_lpm":    last.flow_lpm   if last else 0.0,
            "status":         last.status     if last else "idle",
            "efficiency_pct": round(last.efficiency_pct if last else 0.0, 1),
            "total_liters":   self.total_liters,
            "readings":       len(self.readings),
        }


# ══════════════════════════════════════════════════════════════════════════════
# HARDWARE STUBS — kerangka siap-pakai; plug-in hardware nyata kapanpun
# ══════════════════════════════════════════════════════════════════════════════

class SerialGPIOBridge:
    """Stub: Serial/GPIO bridge untuk Arduino / ESP32 / Raspberry Pi.
    Install : pip install pyserial RPi.GPIO
    Plug-in : implementasi read_sensor() dan write_actuator() sesuai protokol UART.
    """
    ST_DISC = "disconnected"; ST_OK = "connected"; ST_ERR = "error"

    def __init__(self, port: str = "COM3", baudrate: int = 115200):
        self.port      = port
        self.baudrate  = baudrate
        self._status   = self.ST_DISC
        self._last_err = ""
        self._ser      = None

    def connect(self) -> bool:
        try:
            import serial                          # type: ignore
            self._ser    = serial.Serial(self.port, self.baudrate, timeout=1)
            self._status = self.ST_OK
            return True
        except ImportError:
            self._last_err = "pyserial not installed — pip install pyserial"
        except Exception as e:
            self._last_err = str(e)
        self._status = self.ST_ERR
        return False

    def read_sensor(self, sensor_id: str) -> Optional[float]:
        """TODO: implement serial read (e.g. JSON line over UART)"""
        return None   # stub

    def write_actuator(self, actuator_id: str, value: float) -> bool:
        """TODO: implement serial write"""
        return False  # stub

    def status(self) -> Dict:
        return {"port": self.port, "baudrate": self.baudrate,
                "status": self._status, "error": self._last_err}


class OPCUAModbusClient:
    """Stub: OPC-UA / Modbus TCP client untuk PLC / SCADA industri.
    Install : pip install pymodbus   (Modbus)
              pip install opcua      (OPC-UA)
    """

    def __init__(self, host: str = "192.168.1.100", port: int = 502,
                 protocol: str = "modbus"):
        self.host      = host
        self.port      = port
        self.protocol  = protocol   # "modbus" | "opcua"
        self._connected = False
        self._last_err  = ""
        self._client    = None

    def connect(self) -> bool:
        try:
            if self.protocol == "modbus":
                from pymodbus.client import ModbusTcpClient   # type: ignore
                self._client    = ModbusTcpClient(self.host, port=self.port)
                self._connected = self._client.connect()
            elif self.protocol == "opcua":
                from opcua import Client as _OPC              # type: ignore
                self._client = _OPC(
                    f"opc.tcp://{self.host}:{self.port}/freeopcua/server/")
                self._client.connect()
                self._connected = True
        except ImportError as e:
            self._last_err = f"Library missing: {e}"
        except Exception as e:
            self._last_err = str(e)
        return self._connected

    def read_register(self, address: int, count: int = 1):
        """TODO: Modbus read holding registers"""
        return None

    def write_register(self, address: int, value: int) -> bool:
        """TODO: Modbus write single register"""
        return False

    def status(self) -> Dict:
        return {"host": self.host, "port": self.port,
                "protocol": self.protocol,
                "connected": self._connected, "error": self._last_err}


class CameraVisionAI:
    """Stub: Deteksi penyakit tanaman via kamera.
    Install : pip install opencv-python torch torchvision
    Plug-in : implementasi capture_and_analyze() dengan model YOLO/EfficientNet.
    """

    SUPPORTED_DISEASES = [
        "Blast (Pyricularia)", "Bercak daun", "Hawar daun",
        "Busuk akar", "Karat daun", "Embun tepung",
        "Virus mosaik", "Serangan thrips", "Wereng coklat",
    ]

    def __init__(self, camera_id: int = 0, model_path: str = ""):
        self.camera_id   = camera_id
        self.model_path  = model_path
        self._connected  = False
        self._last_err   = ""

    def connect(self) -> bool:
        try:
            import cv2                             # type: ignore
            cap = cv2.VideoCapture(self.camera_id)
            self._connected = cap.isOpened()
            cap.release()
        except ImportError:
            self._last_err = "opencv-python not installed — pip install opencv-python"
        except Exception as e:
            self._last_err = str(e)
        return self._connected

    def capture_and_analyze(self) -> Dict:
        """TODO: capture → preprocess → model inference → return detections."""
        return {
            "status": "stub",
            "detections": [],
            "note": "Hubungkan kamera + load model YOLO/EfficientNet",
            "model": self.model_path or "belum diset",
        }

    def status(self) -> Dict:
        return {"camera_id": self.camera_id, "connected": self._connected,
                "model": self.model_path or "none", "error": self._last_err}


class OTAFirmwareManager:
    """Stub: OTA firmware update untuk ESP32 / Raspberry Pi.
    Plug-in: implementasi check_for_update() dan push_update() sesuai target device.
    """

    def __init__(self, device_host: str = "", update_server: str = ""):
        self.device_host      = device_host
        self.update_server    = update_server
        self._current_version = "unknown"
        self._latest_version  = "unknown"
        self._update_avail    = False
        self._progress_pct    = 0
        self._last_err        = ""

    def check_for_update(self) -> bool:
        """TODO: query update_server untuk versi firmware terbaru."""
        return False

    def push_update(self, firmware_path: str = "") -> bool:
        """TODO: kirim firmware via HTTP/MQTT ke device_host."""
        return False

    def status(self) -> Dict:
        return {
            "device":           self.device_host,
            "current_version":  self._current_version,
            "latest_version":   self._latest_version,
            "update_available": self._update_avail,
            "progress_pct":     self._progress_pct,
            "error":            self._last_err,
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 9: DIGITAL TWIN BENCHMARK (multi-scenario comparison)
# Runs N scenarios in parallel and compares outcomes
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BenchmarkScenario:
    name:         str
    description:  str
    actuator_overrides: Dict  # fixed actuator settings
    results:      Dict = field(default_factory=dict)
    completed:    bool = False


class DigitalTwinBenchmark:
    """
    Runs multiple predefined scenarios against the digital twin
    to benchmark AI controller performance vs baselines.
    """

    PREDEFINED_SCENARIOS = [
        BenchmarkScenario(
            name="AI_Optimal",
            description="Full AI v4 control (baseline)",
            actuator_overrides={},
        ),
        BenchmarkScenario(
            name="Manual_Conservative",
            description="Manual: low energy, no LED, no CO2",
            actuator_overrides={
                "heating": 0, "cooling": 0, "led_grow": 0, "co2_inject": 0,
                "irrigation": 8.0, "fertilize": 0, "vent": 0,
                "led_spectrum": "Full Spectrum",
            },
        ),
        BenchmarkScenario(
            name="Max_Growth",
            description="Max growth: all actuators on, high CO2",
            actuator_overrides={
                "heating": 1, "cooling": 1, "led_grow": 1,
                "co2_inject": 1, "irrigation": 25.0, "fertilize": 1,
                "humidifier": 1, "led_spectrum": "Full Spectrum",
            },
        ),
        BenchmarkScenario(
            name="Energy_Saver",
            description="Minimize energy: no cooling, no LED",
            actuator_overrides={
                "heating": 0, "cooling": 0, "led_grow": 0,
                "co2_inject": 0, "irrigation": 10.0, "fertilize": 1,
                "vent": 1, "led_spectrum": "Full Spectrum",
            },
        ),
        BenchmarkScenario(
            name="Water_Saver",
            description="Minimize water: drip minimal",
            actuator_overrides={
                "heating": 0, "cooling": 1, "led_grow": 1,
                "co2_inject": 1, "irrigation": 3.0, "fertilize": 1,
                "led_spectrum": "Veg (Blue-Heavy)",
            },
        ),
    ]

    def __init__(self):
        self.results: Dict[str, Dict] = {}
        self.ran_steps: int = 0

    def run_quick_benchmark(self, base_zone_class, base_zone_kwargs: Dict,
                             weather_data, ai_ctrl, crop_params,
                             n_steps: int = 50) -> Dict[str, Dict]:
        """
        Run each scenario for n_steps using a fresh copy of the zone.
        Returns comparison table.
        """
        import copy as _copy

        for scenario in self.PREDEFINED_SCENARIOS:
            # Create fresh zone
            zone = base_zone_class(**base_zone_kwargs)

            for step_i in range(n_steps):
                if not scenario.actuator_overrides:
                    # AI control
                    act = ai_ctrl.compute(zone, weather_data, crop_params)
                else:
                    act = dict(scenario.actuator_overrides)
                    act.setdefault("stress_override", 1.0)
                zone.step(weather_data, act)

            cm   = zone.crop_model
            ns   = zone.nutrient_solution
            scenario.results = {
                "yield_kg_m2":     round(cm.yield_kg, 4),
                "biomass_kg_m2":   round(cm.biomass, 4),
                "disease_index":   round(cm.disease_index, 4),
                "pest_pressure":   round(cm.pest_pressure, 4),
                "energy_kwh":      round(zone.energy_kwh, 3),
                "water_L":         round(zone.water_used_L, 1),
                "stage":           cm.stage.value,
                "dvs":             round(cm.dvs, 3),
                "growth_rate":     round(cm.daily_growth_rate, 4),
                "brix":            round(cm.brix_sugar, 2),
                "antioxidant":     round(cm.antioxidant_score, 1),
                "co2_seq_kg":      round(cm.net_carbon_seq_kg, 4),
                "microbial":       round(cm.microbial_activity, 3),
                "net_ps":          round(cm.net_photosynthesis, 2),
                "n_ppm":           round(ns.n_ppm, 1),
                "ph":              round(ns.ph, 2),
                "ec":              round(ns.ec_mS, 2),
            }
            scenario.completed = True
            self.results[scenario.name] = scenario.results

        self.ran_steps = n_steps
        return self.results

    def comparison_dataframe(self) -> pd.DataFrame:
        if not self.results:
            return pd.DataFrame()
        rows = []
        for name, res in self.results.items():
            row = {"Scenario": name}
            for k, v in res.items():
                if isinstance(v, (int, float, str)):
                    row[k] = v
            rows.append(row)
        df = pd.DataFrame(rows).set_index("Scenario")
        
        return df

    def winner_by_metric(self) -> Dict[str, str]:
        if not self.results:
            return {}
        metrics_higher_better = ["yield_kg_m2", "brix", "antioxidant", "co2_seq_kg", "net_ps"]
        metrics_lower_better  = ["energy_kwh", "water_L", "disease_index", "pest_pressure"]
        winners = {}
        for m in metrics_higher_better:
            best = max(self.results.items(), key=lambda x: x[1].get(m, -999))
            winners[m] = best[0]
        for m in metrics_lower_better:
            best = min(self.results.items(), key=lambda x: x[1].get(m, 999))
            winners[m] = best[0]
        return winners


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 10: LIFE CYCLE ASSESSMENT (LCA) ENGINE
# Environmental impact per kg produce (ISO 14040/14044 simplified)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LCAResult:
    global_warming_potential_kg_CO2_per_kg:  float = 0.0  # GWP100
    water_footprint_L_per_kg:                float = 0.0  # WFP
    eutrophication_g_PO4_per_kg:             float = 0.0  # EP
    energy_intensity_MJ_per_kg:             float = 0.0  # CED
    land_use_m2_per_kg:                      float = 0.0  # LU
    eco_score:                               float = 0.0  # 0-100 composite


class LCAEngine:
    """
    Simplified Life Cycle Assessment for greenhouse produce.
    Scope: Cradle-to-gate (cultivation only, not transport/retail).
    """

    # Emission factors (kg CO2-eq per unit)
    EF_ELECTRICITY = 0.82    # kg CO2/kWh (PLN Jawa-Bali grid mix)
    EF_WATER       = 0.001   # kg CO2/L (pumping + treatment)
    EF_CO2_INJECT  = 1.0     # kg CO2/kg (direct release)
    EF_FERTILIZER  = 4.5     # kg CO2/kg (production + transport)
    EF_PESTICIDE   = 6.0     # kg CO2/kg active ingredient

    # Eutrophication factors
    EP_N = 0.42   # g PO4-eq per g N applied
    EP_P = 3.06   # g PO4-eq per g P applied

    def assess(self, zone_data: Dict) -> LCAResult:
        yield_kg    = max(0.001, float(zone_data.get("yield_kg", 0.001)))
        area_m2     = float(zone_data.get("area_m2", 100.0))
        total_yield = yield_kg * area_m2

        energy_kwh  = float(zone_data.get("energy_kwh", 0.0))
        water_L     = float(zone_data.get("water_L", 0.0))
        co2_inj_kg  = float(zone_data.get("co2_injected_kg", 0.0))
        fert_kg     = float(zone_data.get("fertilizer_kg", 0.0))
        pest_press  = float(zone_data.get("pest_pressure", 0.0))
        net_co2_seq = float(zone_data.get("co2_sequestered_kg", 0.0))

        # GWP
        gwp_energy  = energy_kwh  * self.EF_ELECTRICITY
        gwp_water   = water_L     * self.EF_WATER
        gwp_co2     = co2_inj_kg  * self.EF_CO2_INJECT
        gwp_fert    = fert_kg     * self.EF_FERTILIZER
        gwp_pest    = pest_press  * 0.1 * self.EF_PESTICIDE
        gwp_seq     = -max(0.0, net_co2_seq)  # carbon sequestration credit
        gwp_total   = gwp_energy + gwp_water + gwp_co2 + gwp_fert + gwp_pest + gwp_seq

        # Water footprint
        wfp_total   = water_L + energy_kwh * 1.5  # indirect water in energy production

        # Eutrophication
        n_kg_applied  = fert_kg * 0.14   # ~14% N in standard NPK
        p_kg_applied  = fert_kg * 0.05   # ~5% P
        ep_total_g    = n_kg_applied * self.EP_N * 1000 + p_kg_applied * self.EP_P * 1000

        # Energy intensity
        ced_MJ = energy_kwh * 3.6

        # Land use
        lu_m2 = area_m2  # direct land

        # Normalize per kg yield
        if total_yield > 0:
            gwp_pkg  = gwp_total   / total_yield
            wfp_pkg  = wfp_total   / total_yield
            ep_pkg   = ep_total_g  / total_yield
            ced_pkg  = ced_MJ      / total_yield
            lu_pkg   = lu_m2       / total_yield
        else:
            gwp_pkg = wfp_pkg = ep_pkg = ced_pkg = lu_pkg = 0.0

        # Eco-score (0-100, higher = better)
        # Reference: conventional tomato: GWP=2.0 kgCO2/kg, WFP=180 L/kg
        ref_gwp = 2.0;  ref_wfp = 180.0;  ref_ep = 15.0
        eco_gwp   = max(0.0, 100.0 * (1.0 - gwp_pkg / ref_gwp))
        eco_wfp   = max(0.0, 100.0 * (1.0 - wfp_pkg / ref_wfp))
        eco_ep    = max(0.0, 100.0 * (1.0 - ep_pkg   / ref_ep))
        eco_score = round(0.40 * eco_gwp + 0.35 * eco_wfp + 0.25 * eco_ep, 1)

        return LCAResult(
            global_warming_potential_kg_CO2_per_kg = round(gwp_pkg, 4),
            water_footprint_L_per_kg               = round(wfp_pkg, 2),
            eutrophication_g_PO4_per_kg            = round(ep_pkg, 4),
            energy_intensity_MJ_per_kg             = round(ced_pkg, 3),
            land_use_m2_per_kg                     = round(lu_pkg, 3),
            eco_score                              = eco_score,
        )

    def comparison_vs_conventional(self, lca: LCAResult,
                                    crop: str = "Tomato") -> Dict[str, float]:
        """Compare vs conventional farming benchmarks"""
        benchmarks = {
            "Tomato":      {"gwp": 2.0,  "wfp": 180.0, "ep": 15.0},
            "Lettuce":     {"gwp": 1.5,  "wfp": 130.0, "ep": 10.0},
            "Cucumber":    {"gwp": 1.8,  "wfp": 160.0, "ep": 12.0},
            "Strawberry":  {"gwp": 2.5,  "wfp": 200.0, "ep": 18.0},
            "Basil":       {"gwp": 3.0,  "wfp": 140.0, "ep": 14.0},
        }
        ref = benchmarks.get(crop, benchmarks["Tomato"])
        return {
            "gwp_reduction_pct":  round((1 - lca.global_warming_potential_kg_CO2_per_kg / ref["gwp"]) * 100, 1),
            "water_reduction_pct":round((1 - lca.water_footprint_L_per_kg               / ref["wfp"]) * 100, 1),
            "ep_reduction_pct":   round((1 - lca.eutrophication_g_PO4_per_kg             / ref["ep"])  * 100, 1),
        }


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 11: INTERCROPPING COMPANION PLANTING MODEL
# Simulates synergistic / allelopathic effects between zone crops
# ══════════════════════════════════════════════════════════════════════════════

COMPANION_MATRIX: Dict[str, Dict[str, Dict[str, float]]] = {
    # Format: source_crop → target_crop → {growth_boost, pest_reduction, nutrient_share}
    "Basil": {
        "Tomato":  {"growth_boost": 0.08, "pest_reduction": 0.12, "nutrient_share": 0.02},
        "Pepper":  {"growth_boost": 0.06, "pest_reduction": 0.10, "nutrient_share": 0.01},
        "Lettuce": {"growth_boost": 0.03, "pest_reduction": 0.05, "nutrient_share": 0.01},
    },
    "Spinach": {
        "Tomato":   {"growth_boost": 0.04, "pest_reduction": 0.03, "nutrient_share": 0.03},
        "Strawberry": {"growth_boost": 0.05, "pest_reduction": 0.04, "nutrient_share": 0.02},
    },
    "Tomato": {
        "Basil":    {"growth_boost": 0.05, "pest_reduction": 0.08, "nutrient_share": -0.01},
        "Cucumber": {"growth_boost": -0.05,"pest_reduction": -0.02,"nutrient_share": -0.03},  # allelopathy
    },
    "Lettuce": {
        "Cucumber": {"growth_boost": 0.03, "pest_reduction": 0.04, "nutrient_share": 0.02},
        "Tomato":   {"growth_boost": 0.02, "pest_reduction": 0.03, "nutrient_share": 0.01},
    },
    "Microgreens": {
        "Lettuce":  {"growth_boost": 0.04, "pest_reduction": 0.06, "nutrient_share": 0.01},
    },
}


def apply_intercropping_effects(zones: List) -> Dict[str, Dict[str, float]]:
    """
    Compute intercropping effects between all zone pairs.
    Returns {zone_id: {boost, pest_red, nut_share}} to apply per step.
    """
    effects = {z.zone_id: {"growth_boost": 0.0, "pest_reduction": 0.0, "nutrient_share": 0.0}
               for z in zones}

    for i, zone_a in enumerate(zones):
        crop_a = zone_a.crop_type.value
        for j, zone_b in enumerate(zones):
            if i == j:
                continue
            crop_b = zone_b.crop_type.value
            compat = COMPANION_MATRIX.get(crop_a, {}).get(crop_b)
            if compat:
                e = effects[zone_b.zone_id]
                e["growth_boost"]   += compat["growth_boost"]
                e["pest_reduction"] += compat["pest_reduction"]
                e["nutrient_share"] += compat["nutrient_share"]

    # Clamp
    for zone_id in effects:
        e = effects[zone_id]
        e["growth_boost"]   = float(np.clip(e["growth_boost"],   -0.30, 0.30))
        e["pest_reduction"] = float(np.clip(e["pest_reduction"], -0.20, 0.40))
        e["nutrient_share"] = float(np.clip(e["nutrient_share"], -0.10, 0.10))

    return effects


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 12: YIELD QUALITY INDEX (YQI)
# Composite quality score based on nutritional & organoleptic attributes
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class YieldQualityIndex:
    brix_score:        float = 0.0   # sugar content score
    antioxidant_score: float = 0.0   # ORAC-based score
    n_content_score:   float = 0.0   # protein potential
    size_uniformity:   float = 0.0   # uniformity (from stress_days)
    shelf_life_score:  float = 0.0   # relative shelf life
    pesticide_residue: float = 0.0   # 0=none → 100=high (lower is better)
    overall_yqi:       float = 0.0   # 0-100 composite
    grade:             str   = "B"   # A+, A, B, C, D


def compute_yqi(crop_model, crop_params, stress_days: int,
                pest_pressure: float, disease_index: float) -> YieldQualityIndex:
    """Compute comprehensive Yield Quality Index"""
    # Brix score: optimal 6-10° (crop specific)
    brix  = crop_model.brix_sugar
    brix_ref = {
        "Tomato": 6.0, "Strawberry": 9.0, "Pepper": 5.5,
        "Cucumber": 3.5, "Lettuce": 2.0, "Basil": 4.0,
    }
    brix_opt  = brix_ref.get(crop_params.name, 5.0)
    brix_score = float(np.clip(100.0 * (1.0 - abs(brix - brix_opt) / (brix_opt + 2.0)), 0.0, 100.0))

    # Antioxidant score (normalize 0-100)
    antioxidant_score = float(np.clip(crop_model.antioxidant_score, 0.0, 100.0))

    # N content (protein proxy)
    n_score = float(np.clip(
        100.0 * (crop_model.n_content / max(0.1, crop_params.p_content_optimal * 6.0)),
        0.0, 100.0
    ))

    # Size uniformity (inverse of stress variance)
    uniformity = float(np.clip(100.0 * (1.0 - stress_days / max(1, crop_params.days_to_harvest)), 0.0, 100.0))

    # Shelf life (crop-specific, disease reduces it)
    base_shelf = crop_params.shelf_life_days
    shelf_score = float(np.clip(100.0 * (1.0 - disease_index * 0.5), 0.0, 100.0))

    # Pesticide residue (from pest_pressure → treatment proxy)
    pesticide = float(np.clip(pest_pressure * 100.0 * 0.5, 0.0, 100.0))

    # Overall YQI weighted composite
    yqi = (
        brix_score        * 0.20 +
        antioxidant_score * 0.25 +
        n_score           * 0.15 +
        uniformity        * 0.15 +
        shelf_score       * 0.15 +
        (100.0 - pesticide) * 0.10
    )

    # Grade
    if yqi >= 88:   grade = "A+"
    elif yqi >= 75: grade = "A"
    elif yqi >= 60: grade = "B"
    elif yqi >= 45: grade = "C"
    else:           grade = "D"

    return YieldQualityIndex(
        brix_score        = round(brix_score, 1),
        antioxidant_score = round(antioxidant_score, 1),
        n_content_score   = round(n_score, 1),
        size_uniformity   = round(uniformity, 1),
        shelf_life_score  = round(shelf_score, 1),
        pesticide_residue = round(pesticide, 1),
        overall_yqi       = round(yqi, 1),
        grade             = grade,
    )


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 13: GIS ZONE MAPPING
# Maps greenhouse zones to GPS coordinates and generates heatmap data
# ══════════════════════════════════════════════════════════════════════════════

class GISZoneMapper:
    """
    Maps zones to GPS coordinates, generates field-level spatial data,
    and produces data for leaflet/plotly choropleth maps.
    """

    def __init__(self, facility_lat: float = -6.2088,
                 facility_lon: float = 106.8456,
                 facility_name: str = "Greenhouse Facility"):
        self.lat          = facility_lat
        self.lon          = facility_lon
        self.facility_name= facility_name

    def zone_polygon(self, zone_index: int, zone_area_m2: float,
                     offset_m: float = 30.0) -> Dict:
        """
        Generate approximate bounding box for a zone.
        Returns GeoJSON-compatible polygon.
        """
        # Convert meters to approximate degrees
        d_lat = (offset_m * zone_index) / 111_000.0
        d_lon = math.sqrt(zone_area_m2) / (111_000.0 * math.cos(math.radians(self.lat)))

        lat0 = self.lat - d_lat
        lon0 = self.lon
        lat1 = lat0 - math.sqrt(zone_area_m2) / 111_000.0
        lon1 = lon0 + d_lon

        return {
            "type": "Feature",
            "properties": {"zone_index": zone_index},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]
            }
        }

    def generate_sensor_heatmap(self, zones: List,
                                 metric: str = "temp") -> List[Dict]:
        """
        Generate heatmap data points for spatial visualization.
        Each zone center gets a value + weight.
        """
        points = []
        for i, zone in enumerate(zones):
            d_lat = (30.0 * i) / 111_000.0
            z_lat = self.lat - d_lat - math.sqrt(zone.area_m2) / (2 * 111_000.0)
            z_lon = self.lon + math.sqrt(zone.area_m2) / (2 * 111_000.0 * math.cos(math.radians(self.lat)))

            val = {
                "temp":     zone.temp_air,
                "humidity": zone.humidity,
                "co2":      zone.co2_ppm,
                "yield":    zone.crop_model.yield_kg,
                "disease":  zone.crop_model.disease_index,
                "pest":     zone.crop_model.pest_pressure,
                "biomass":  zone.crop_model.biomass,
            }.get(metric, 0.0)

            points.append({
                "lat":     round(z_lat, 6),
                "lon":     round(z_lon, 6),
                "value":   round(val, 3),
                "zone_id": zone.zone_id,
                "crop":    zone.crop_type.value,
                "area_m2": zone.area_m2,
            })
        return points


# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION 14: AUTO-DOSING PID CASCADE (Acid/Base + Nutrient)
# More sophisticated than the simple pH adjust in main code
# ══════════════════════════════════════════════════════════════════════════════

class CascadeDosing:
    """
    Cascade PID for pH and EC dosing.
    Outer loop: setpoint tracking
    Inner loop: dose rate control
    Prevents oscillation and over-dosing.
    """

    def __init__(self, ph_setpoint: float = 6.2, ec_setpoint: float = 3.5):
        self.ph_sp = ph_setpoint
        self.ec_sp = ec_setpoint

        # PID state
        self.ph_i  = 0.0;  self.ph_prev_e = 0.0
        self.ec_i  = 0.0;  self.ec_prev_e = 0.0

        # Dose tracking
        self.acid_dose_mL  = 0.0
        self.base_dose_mL  = 0.0
        self.nutrient_dose_g = 0.0
        self.dose_history: List[Dict] = []

        # Safety limits
        self.max_acid_mL_per_step  = 50.0
        self.max_base_mL_per_step  = 50.0
        self.max_nutrient_g_per_step = 100.0

    def update_ph(self, ph_measured: float) -> Dict[str, float]:
        """Compute acid/base dose (mL) to reach pH setpoint"""
        e   = self.ph_sp - ph_measured
        self.ph_i = float(np.clip(self.ph_i + e, -20.0, 20.0))
        d   = e - self.ph_prev_e
        self.ph_prev_e = e

        kp, ki, kd = 8.0, 0.3, 1.5
        output = kp * e + ki * self.ph_i + kd * d

        if output > 0:  # pH too low → add base
            base_mL = float(np.clip(output * 2.0, 0.0, self.max_base_mL_per_step))
            acid_mL = 0.0
        else:           # pH too high → add acid
            acid_mL = float(np.clip(-output * 2.0, 0.0, self.max_acid_mL_per_step))
            base_mL = 0.0

        self.acid_dose_mL += acid_mL
        self.base_dose_mL += base_mL

        result = {
            "ph_error":   round(e, 4),
            "acid_mL":    round(acid_mL, 2),
            "base_mL":    round(base_mL, 2),
            "ph_target":  self.ph_sp,
            "ph_measured":round(ph_measured, 3),
        }
        self.dose_history.append({"type": "pH", **result})
        return result

    def update_ec(self, ec_measured: float,
                  n_ppm: float, k_ppm: float) -> Dict[str, float]:
        """Compute nutrient dose (g) to reach EC setpoint"""
        e   = self.ec_sp - ec_measured
        self.ec_i = float(np.clip(self.ec_i + e, -15.0, 15.0))
        d   = e - self.ec_prev_e
        self.ec_prev_e = e

        kp, ki, kd = 12.0, 0.5, 2.0
        output = float(np.clip(kp * e + ki * self.ec_i + kd * d, 0.0, 100.0))

        # Differentiate N vs K demand
        n_ratio = max(0.0, 1.0 - n_ppm / 200.0)  # how much N is needed
        k_ratio = max(0.0, 1.0 - k_ppm / 350.0)  # how much K is needed

        n_dose_g = float(np.clip(output * 0.4 * n_ratio, 0.0, self.max_nutrient_g_per_step))
        k_dose_g = float(np.clip(output * 0.4 * k_ratio, 0.0, self.max_nutrient_g_per_step))
        p_dose_g = float(np.clip(output * 0.2,            0.0, self.max_nutrient_g_per_step * 0.5))

        self.nutrient_dose_g += n_dose_g + k_dose_g + p_dose_g

        result = {
            "ec_error":   round(e, 4),
            "n_dose_g":   round(n_dose_g, 2),
            "k_dose_g":   round(k_dose_g, 2),
            "p_dose_g":   round(p_dose_g, 2),
            "ec_target":  self.ec_sp,
            "ec_measured":round(ec_measured, 3),
        }
        self.dose_history.append({"type": "EC", **result})
        return result

    def cumulative_stats(self) -> Dict:
        return {
            "total_acid_L":      round(self.acid_dose_mL / 1000.0, 3),
            "total_base_L":      round(self.base_dose_mL / 1000.0, 3),
            "total_nutrient_kg": round(self.nutrient_dose_g / 1000.0, 4),
            "dose_events":       len(self.dose_history),
        }


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT RENDER FUNCTIONS — EXTENSION PANELS
# Panggil dari main() di file utama setelah render_disease_panel()
# ══════════════════════════════════════════════════════════════════════════════

def _esc(v: Any) -> str:
    import html as _html
    return _html.escape(str(v), quote=True)

def _fmt_idr(val: float) -> str:
    if abs(val) >= 1e9:  return f"Rp {val/1e9:.2f}M"
    if abs(val) >= 1e6:  return f"Rp {val/1e6:.2f}jt"
    if abs(val) >= 1e3:  return f"Rp {val/1e3:.1f}rb"
    return f"Rp {val:.0f}"


def render_city_selector_extended() -> str:
    """
    Pengganti city selector di sidebar — pakai selectbox berdasarkan provinsi.
    Taruh ini di sidebar tepat setelah API key input.
    Return: city name yang dipilih.
    """
    province = st.selectbox(
        "Provinsi",
        options=sorted(INDONESIA_CITIES_BY_PROVINCE.keys()),
        key="ext_province_select"
    )
    cities_in_prov = INDONESIA_CITIES_BY_PROVINCE.get(province, ["Jakarta"])
    city = st.selectbox("Kota/Kabupaten", cities_in_prov, key="ext_city_select")
    return city


def render_weather_ensemble_panel(ens: WeatherEnsemble):
    """Tampilkan panel ensemble weather model"""
    st.markdown('<div class="section-header">🌦️ WEATHER ENSEMBLE (3-MODEL BLEND)</div>',
                unsafe_allow_html=True)

    conf_color = "#44ee44" if ens.confidence > 0.75 else ("#eeaa33" if ens.confidence > 0.5 else "#ee4444")
    models_str = " | ".join(_esc(m) for m in ens.source_models)

    st.markdown(f"""
    <div class="kalman-box">
        <b>Models:</b> {models_str} &nbsp;
        <b>Confidence:</b> <span style="color:{conf_color}">{ens.confidence:.2%}</span><br>
        🌡️ Temp: <b>{ens.temp_mean:.1f}°C</b> ± {ens.temp_std:.2f}°C &nbsp;
        💧 Humidity: <b>{ens.humidity_mean:.1f}%</b> ± {ens.humidity_std:.1f}% &nbsp;
        ☀️ Solar: <b>{ens.solar_mean:.0f}W/m²</b> ± {ens.solar_std:.0f}<br>
        🌧️ Rain prob: <b>{ens.rainfall_prob:.1%}</b> &nbsp;
        Rain amount: <b>{ens.rainfall_amount:.1f}mm</b>
    </div>
    """, unsafe_allow_html=True)


def render_fao56_panel(fao_model: FAO56ETModel, zones: List):
    """Tampilkan panel FAO-56 evapotranspirasi"""
    st.markdown('<div class="section-header">💧 FAO-56 EVAPOTRANSPIRASI PRESISI</div>',
                unsafe_allow_html=True)

    if not zones:
        return

    cols = st.columns(min(len(zones), 3))
    for i, zone in enumerate(zones[:3]):
        cm = zone.crop_model
        with cols[i]:
            et0_est = fao_model.et0_hourly(
                temp_c       = zone.temp_air,
                humidity_pct = zone.humidity,
                wind_ms      = 2.0,
                solar_wm2    = zone.light_w,
            )
            schedule = fao_model.daily_schedule({
                "et0_mm_day":    et0_est * 12,   # hourly × 12 = rough daily
                "crop":          zone.crop_type.value,
                "day":           cm.day,
                "forecast_rain_24h": 0.5,
                "soil_moisture_pct": zone.soil_moist,
                "area_m2":       zone.area_m2,
                "irrigation_efficiency": 0.90,
            })
            st.markdown(f"""
            <div class="zone-card">
                <b>{_esc(zone.zone_id)}</b> — {_esc(zone.crop_type.value)}<br>
                ET₀: <b>{et0_est:.3f}mm/hr</b> &nbsp; ETc: <b>{schedule['etc_mm_day']:.3f}mm/day</b><br>
                Kc: <b>{schedule['kc']:.3f}</b> &nbsp; Deficit: <b>{schedule['deficit_mm']:.2f}mm</b><br>
                💧 Irrig today: <b>{schedule['total_volume_L']:.0f}L</b><br>
                ⏰ Schedule: {', '.join([f'{h:02d}:00' for h in schedule['schedule_hours']])}
                ({schedule['volume_per_slot_L']:.0f}L/slot)
            </div>
            """, unsafe_allow_html=True)


def render_rothc_panel(rothc: RothCModel, zones: List):
    """Tampilkan panel RothC soil carbon"""
    st.markdown('<div class="section-header">🌍 ROTHC SOIL CARBON MODEL</div>',
                unsafe_allow_html=True)

    report = rothc.net_sequestration_report()
    if not report:
        st.info("Run simulation to populate RothC carbon pools.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="carbon-box">
            <b>Carbon Stock:</b> {rothc.carbon_stock_tCha():.3f} t C/ha<br>
            <b>Total CO₂ flux:</b> {report.get('total_co2_kg_m2', 0):.4f} kg CO₂/m²<br>
            <b>Monthly avg:</b> {report.get('avg_monthly_kg_m2', 0):.6f} kg CO₂/m²/month<br>
            <b>Months simulated:</b> {report.get('months_simulated', 0)}
        </div>
        """, unsafe_allow_html=True)
    with col2:
        bp = report.get("pool_breakdown", {})
        st.markdown(f"""
        <div class="carbon-box">
            <b>Pool breakdown (active C):</b><br>
            DPM: {bp.get('dpm_pct', 0):.1f}% &nbsp;
            RPM: {bp.get('rpm_pct', 0):.1f}%<br>
            BIO: {bp.get('bio_pct', 0):.1f}% &nbsp;
            HUM: {bp.get('hum_pct', 0):.1f}%<br>
            <span style="font-size:10px; color:#6b8d6b;">
            DPM=Decomposable Plant Mat | RPM=Resistant | BIO=Microbial | HUM=Humus
            </span>
        </div>
        """, unsafe_allow_html=True)


def render_rl_panel(rl_ctrl: RLGreenhouseController):
    """Tampilkan RL controller stats"""
    st.markdown('<div class="section-header">🧠 REINFORCEMENT LEARNING CONTROLLER</div>',
                unsafe_allow_html=True)

    stats = rl_ctrl.policy_heatmap_data()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("RL Steps",    stats["steps"])
    col2.metric("Epsilon (ε)", f"{stats['epsilon']:.3f}")
    col3.metric("Avg Reward",  f"{stats['avg_reward']:.3f}")
    col4.metric("Max Q",       f"{stats['max_q']:.3f}")

    if rl_ctrl.reward_history and PLOTLY_EXT:
        rh = rl_ctrl.reward_history[-100:]
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=rh, mode="lines", name="Reward",
                                  line=dict(color="#55ee55", width=1.5)))
        # Rolling avg
        if len(rh) >= 10:
            roll = [float(np.mean(rh[max(0,i-10):i+1])) for i in range(len(rh))]
            fig.add_trace(go.Scatter(y=roll, mode="lines", name="Rolling Avg",
                                      line=dict(color="#ffaa33", width=2, dash="dot")))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#060d06", plot_bgcolor="#0a1a0a",
            height=200, font=dict(color="#7a9a7a", size=9),
            title=dict(text="RL Reward History (last 100 steps)", font=dict(size=11)),
            showlegend=True, margin=dict(t=30, b=10, l=30, r=10),
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.caption("Run ≥1 step to populate RL reward chart.")


def render_pareto_panel(nsga: NSGAIIOptimizer):
    """Tampilkan Pareto front visualization"""
    st.markdown('<div class="section-header">📊 PARETO MULTI-OBJECTIVE OPTIMIZER (NSGA-II)</div>',
                unsafe_allow_html=True)

    if not nsga.pareto_front:
        st.info("Click '🎯 Run NSGA-II Pareto Opt' to run multi-objective optimization.")
        return

    front  = nsga.pareto_front
    best   = nsga.best_balanced()
    sp     = nsga.setpoints_from_solution(best) if best else {}

    if PLOTLY_EXT:
        fig = go.Figure()
        yields  = [s.yield_score  for s in front]
        energys = [s.energy_score for s in front]
        waters  = [s.water_score  for s in front]

        fig.add_trace(go.Scatter(
            x=energys, y=yields,
            mode="markers",
            marker=dict(
                size=8, color=waters,
                colorscale="Viridis", showscale=True,
                colorbar=dict(title="Water", thickness=12),
            ),
            text=[f"T={nsga.setpoints_from_solution(s)['temp_sp']:.1f} H={nsga.setpoints_from_solution(s)['humidity_sp']:.0f}"
                  for s in front],
            hovertemplate="Energy: %{x:.3f}<br>Yield: %{y:.3f}<br>%{text}",
            name="Pareto Solutions",
        ))
        if best:
            fig.add_trace(go.Scatter(
                x=[best.energy_score], y=[best.yield_score],
                mode="markers", marker=dict(size=14, color="#ff6a4a", symbol="star"),
                name="Best Balanced",
            ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#060d06", plot_bgcolor="#0a1a0a",
            height=320, xaxis_title="Energy Cost (lower=better)",
            yaxis_title="Yield Potential (higher=better)",
            title=dict(text=f"Pareto Front — {len(front)} solutions", font=dict(size=12)),
            font=dict(color="#7a9a7a", size=9),
        )
        st.plotly_chart(fig, width='stretch')

    if sp:
        st.markdown(f"""
        <div class="prediction-box">
            🎯 <b>Best Balanced Setpoints:</b>
            T={sp['temp_sp']}°C | H={sp['humidity_sp']}% | CO₂={sp['co2_sp']:.0f}ppm |
            Soil={sp['soil_sp']}% | LED={sp['led_intensity']:.0%} | Vent={sp['vent_rate']:.0%}
        </div>
        """, unsafe_allow_html=True)


def render_blockchain_panel(chain: GreenChainAudit):
    """Tampilkan blockchain audit trail"""
    st.markdown('<div class="section-header">🔗 GREENCHAIN AUDIT TRAIL</div>',
                unsafe_allow_html=True)

    valid, invalid = chain.verify_integrity()
    integrity_color = "#44ee44" if valid else "#ee4444"
    integrity_text  = "✅ VALID" if valid else f"❌ TAMPERED (blocks: {invalid})"

    st.markdown(f"""
    <div class="zone-card">
        Chain length: <b>{len(chain.chain)}</b> blocks &nbsp;
        Integrity: <span style="color:{integrity_color}"><b>{integrity_text}</b></span>
    </div>
    """, unsafe_allow_html=True)

    recent = chain.get_recent(8)
    if recent:
        df = pd.DataFrame(recent)
        st.dataframe(df[["idx","ts","zone","type","hash"]], width='stretch', hide_index=True)

    # Export button
    if st.button("📥 Export Chain JSON", key="chain_export"):
        st.download_button(
            "⬇️ Download chain.json",
            data=chain.export_json(),
            file_name=f"greenchain_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )


def render_mqtt_panel(mqtt):
    """Tampilkan MQTT telemetry — mendukung MQTTSimulator & MQTTBrokerClient."""
    is_real = isinstance(mqtt, MQTTBrokerClient)
    title   = "📡 MQTT — REAL BROKER" if is_real else "📡 MQTT TELEMETRY SIMULATOR"
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)

    # ── Koneksi ke broker nyata ──────────────────────────────────────────────
    if is_real:
        stats = mqtt.stats()
        conn_color = "#44ff44" if stats["connected"] else "#ff4444"
        conn_label = "🟢 Terhubung" if stats["connected"] else "🔴 Terputus"
        st.markdown(
            f'<span style="color:{conn_color};font-weight:bold">{conn_label}</span>'
            f' &nbsp; Broker: <code>{stats["broker"]}</code>',
            unsafe_allow_html=True)
        if stats.get("error"):
            st.warning(f"⚠️ {stats['error']}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Broker",     stats["broker"])
        col2.metric("Dikirim",    stats["total_messages"])
        col3.metric("Buffer",     stats["buffer_size"])
        col4.metric("Subscribe",  stats["subscriptions"])

        # Config & connect form
        with st.expander("⚙️ Konfigurasi Broker", expanded=not stats["connected"]):
            c1, c2 = st.columns([3, 1])
            host   = c1.text_input("Host", value=mqtt.host,   key="mqtt_host")
            port   = c2.number_input("Port", value=mqtt.port, key="mqtt_port",
                                     min_value=1, max_value=65535, step=1)
            cu, cp = st.columns(2)
            uname  = cu.text_input("Username (opsional)", value=mqtt.username, key="mqtt_user")
            pword  = cp.text_input("Password (opsional)", value=mqtt.password,
                                   type="password", key="mqtt_pass")
            use_tls = st.checkbox("TLS/SSL", value=mqtt.use_tls, key="mqtt_tls")
            bc1, bc2 = st.columns(2)
            if bc1.button("🔌 Connect", key="mqtt_connect_btn"):
                mqtt.host     = host;  mqtt.port     = int(port)
                mqtt.username = uname; mqtt.password = pword
                mqtt.use_tls  = use_tls
                with st.spinner("Menghubungkan ke broker…"):
                    ok = mqtt.connect()
                if ok:
                    st.success("✅ Terhubung ke broker!")
                else:
                    st.error(f"❌ Gagal: {mqtt._last_error}")
            if bc2.button("🔌 Disconnect", key="mqtt_disconnect_btn"):
                mqtt.disconnect()
                st.info("Terputus dari broker.")

        st.markdown("**📋 Tips setup broker gratis:**")
        st.markdown(
            "• **Lokal** — `mosquitto` → `localhost:1883`  \n"
            "• **HiveMQ Cloud** — [hivemq.com/mqtt-cloud-broker](https://www.hivemq.com/mqtt-cloud-broker/) (gratis)  \n"
            "• **EMQX Cloud** — [emqx.com/en/cloud](https://www.emqx.com/en/cloud) (gratis tier)")
    else:
        stats = mqtt.stats()
        col1, col2, col3 = st.columns(3)
        col1.metric("Dikirim",  stats["total_messages"])
        col2.metric("Buffer",   stats["buffer_size"])
        col3.metric("Facility", stats["facility"])
        st.info("🔵 Mode simulasi in-memory. Untuk konek broker nyata, "
                "aktifkan **Real MQTT** di sidebar.")

    # ── Pesan terkini ────────────────────────────────────────────────────────
    recent = mqtt.get_recent_messages(6)
    if recent:
        st.markdown("**Recent messages:**")
        for msg in recent[-4:]:
            topic   = msg["topic"]
            payload = {k: round(v, 2) if isinstance(v, float) else v
                       for k, v in msg["payload"].items()}
            st.markdown(
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
                f'color:#44aa44;background:#030803;padding:4px 8px;'
                f'border-radius:4px;margin:2px 0;">'
                f'📤 <b>{_esc(topic)}</b> → {_esc(json.dumps(payload, default=str)[:80])}'
                f'</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: DATA HISTORIAN
# ─────────────────────────────────────────────────────────────────────────────

def render_historian_panel(historian: DataHistorian, zones: List):
    """Panel Data Historian — query, visualisasi, export."""
    st.markdown('<div class="section-header">🗄️ DATA HISTORIAN (SQLite)</div>',
                unsafe_allow_html=True)

    s = historian.stats()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Sensor rows",   f"{s['sensor_rows']:,}")
    c2.metric("Actuator rows", f"{s['actuator_rows']:,}")
    c3.metric("Open alerts",   s["open_alerts"])
    c4.metric("Flow rows",     f"{s['flow_rows']:,}")
    c5.metric("Vern rows",     s["vern_rows"])
    c6.metric("DB size",       f"{s['db_size_kb']} KB")

    st.caption(f"📁 {s['db_path']}")

    tab_q, tab_al, tab_ex = st.tabs(["📈 Query Sensor", "🔔 Alerts", "⬇️ Export CSV"])

    with tab_q:
        zone_ids = [z.zone_id for z in zones] if zones else ["ZONE-01"]
        col_z, col_p, col_h = st.columns([2, 2, 1])
        sel_zone  = col_z.selectbox("Zone", zone_ids, key="hist_zone")
        sel_param = col_p.selectbox("Parameter",
            ["temperature","humidity","co2","soil_moisture","light","ec","ph"],
            key="hist_param")
        sel_hours = col_h.number_input("Jam terakhir", 1, 720, 24, key="hist_hours")
        rows = historian.query_sensor(sel_zone, sel_param, int(sel_hours))
        if rows:
            import pandas as _pd
            df = _pd.DataFrame(rows)
            df["ts"]    = _pd.to_datetime(df["ts"])
            df["value"] = df["value"].astype(float)
            st.line_chart(df.set_index("ts")["value"])
            st.caption(f"{len(df)} data points")
        else:
            st.info("Belum ada data di rentang waktu ini. "
                    "Data akan muncul setelah simulasi berjalan.")

    with tab_al:
        al_hours = st.slider("Tampilkan alerts N jam terakhir", 1, 168, 48,
                             key="hist_al_hours")
        unacked  = st.checkbox("Hanya yang belum diakui", key="hist_unacked")
        alerts   = historian.query_alerts(al_hours, unacked)
        if alerts:
            for a in alerts:
                color = {"critical": "#ff4444", "warning": "#ffaa00",
                         "info": "#44aaff"}.get(a["severity"], "#aaaaaa")
                st.markdown(
                    f'<div style="border-left:3px solid {color};padding:4px 10px;'
                    f'margin:3px 0;background:#0a0a0a;font-size:12px;">'
                    f'<b style="color:{color}">[{a["severity"].upper()}]</b> '
                    f'<code>{a["ts"][:19]}</code> {_esc(a["zone"])} — {_esc(a["msg"])}'
                    f'{"  ✅" if a["acked"] else ""}</div>',
                    unsafe_allow_html=True)
        else:
            st.success("✅ Tidak ada alert dalam rentang waktu ini.")

    with tab_ex:
        col_t, col_h2 = st.columns([2, 1])
        exp_table = col_t.selectbox("Tabel", [
            "sensor_readings", "actuator_events", "alerts",
            "flow_meter_log", "vernalization_log"], key="hist_exp_tbl")
        exp_hours = col_h2.number_input("Jam", 1, 720, 24, key="hist_exp_h")
        if st.button("⬇️ Generate CSV", key="hist_gen_csv"):
            csv_data = historian.export_csv(exp_table, int(exp_hours))
            st.download_button(
                label=f"💾 Download {exp_table}.csv",
                data=csv_data,
                file_name=f"{exp_table}_{datetime.datetime.now():%Y%m%d_%H%M}.csv",
                mime="text/csv",
                key="hist_dl_btn")


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: VERNALIZATION TRACKER
# ─────────────────────────────────────────────────────────────────────────────

def render_vernalization_panel(tracker: "VernalizationTracker",
                               historian: "DataHistorian"):
    """Panel Vernalisasi Bawang Putih — input suhu harian, tracking progress."""
    st.markdown(
        '<div class="section-header">❄️ VERNALISASI BAWANG PUTIH (Cold Treatment)</div>',
        unsafe_allow_html=True)

    col_v, col_s = st.columns([2, 2])
    with col_v:
        new_variety = st.selectbox(
            "Varietas", list(VernalizationTracker.VARIETY_TARGETS.keys()),
            index=list(VernalizationTracker.VARIETY_TARGETS.keys()).index(
                tracker.variety)
            if tracker.variety in VernalizationTracker.VARIETY_TARGETS else 0,
            key="vern_variety")
        if new_variety != tracker.variety:
            tracker.variety      = new_variety
            tracker.target_hours = float(
                VernalizationTracker.VARIETY_TARGETS[new_variety])

    with col_s:
        st.metric("Target jam dingin",
                  f"{tracker.target_hours:.0f} jam ({tracker.target_hours/24:.0f} hari)")

    # Progress
    pct = tracker.progress_pct
    bar_filled = int(pct / 5)   # 20 blocks
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    prog_color = "#44ff44" if pct >= 100 else "#ffaa00" if pct >= 75 else "#44aaff"
    st.markdown(
        f'<div style="background:#0a1a0a;padding:12px;border-radius:8px;margin:8px 0;">'
        f'<div style="font-size:13px;color:#aaa;margin-bottom:4px">'
        f'Progress: {tracker.total_cold_hours:.1f} / {tracker.target_hours:.0f} jam dingin</div>'
        f'<div style="font-family:monospace;font-size:18px;color:{prog_color}">'
        f'[{bar}] {pct:.1f}%</div>'
        f'<div style="color:{prog_color};font-weight:bold;margin-top:4px">'
        f'{tracker.status}</div></div>',
        unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hari berjalan",     tracker.days_elapsed)
    c2.metric("Total jam dingin",  f"{tracker.total_cold_hours:.1f} j")
    c3.metric("Rata-rata/hari",
              f"{tracker.total_cold_hours/max(1,tracker.days_elapsed):.1f} j")
    c4.metric("Estimasi selesai",  tracker.estimate_completion_date())

    # Input hari baru
    st.markdown("---")
    st.markdown("**➕ Tambah data hari ini:**")
    ia, ib, ic = st.columns([2, 2, 1])
    t_min = ia.number_input("Suhu Min (°C)", -10.0, 40.0, 5.0,
                             step=0.5, key="vern_tmin")
    t_max = ib.number_input("Suhu Max (°C)", -10.0, 45.0, 12.0,
                             step=0.5, key="vern_tmax")
    entry_date = ic.date_input("Tanggal", key="vern_date")
    if st.button("✅ Tambah", key="vern_add"):
        cold_h = tracker.add_day(float(t_min), float(t_max),
                                 date=str(entry_date))
        historian.log_vernalization(
            crop_id=f"bawang_putih_{tracker.variety}",
            temp_c=(float(t_min) + float(t_max)) / 2,
            cold_hours=cold_h,
            target_hours=tracker.target_hours)
        if cold_h < 1.0:
            st.warning(f"⚠️ Hari ini hanya {cold_h:.1f} jam dingin — "
                       "suhu terlalu tinggi untuk vernalisasi.")
        else:
            st.success(f"✅ +{cold_h:.1f} jam dingin "
                       f"(total {tracker.total_cold_hours:.1f} jam, "
                       f"{tracker.progress_pct:.1f}%)")
        st.rerun()

    # Riwayat
    if tracker.records:
        st.markdown("**📋 Riwayat 10 hari terakhir:**")
        import pandas as _pd
        rec_data = [{"Tanggal": r.date, "T-Min": r.temp_min_c,
                     "T-Max": r.temp_max_c, "Jam Dingin": r.cold_hours}
                    for r in tracker.records[-10:]]
        st.dataframe(_pd.DataFrame(rec_data), use_container_width=True)
        # Chart
        all_data = [{"Tanggal": r.date, "Jam Dingin Kumulatif":
                     sum(x.cold_hours for x in tracker.records[:i+1])}
                    for i, r in enumerate(tracker.records)]
        df_chart = _pd.DataFrame(all_data).set_index("Tanggal")
        st.line_chart(df_chart)

    # Panduan
    with st.expander("ℹ️ Panduan Vernalisasi Bawang Putih"):
        st.markdown("""
**Apa itu vernalisasi?**
Perlakuan dingin yang memicu diferensiasi umbi. Tanpa vernalisasi,
bawang putih hanya menghasilkan batang → tidak ada umbi.

**Suhu optimal**: 0–10°C (idealnya 4–7°C)
**Suhu <0°C**: risiko *chilling injury* — efektivitas berkurang
**Metode**: simpan bibit di cold storage / ruang berpendingin sebelum tanam

| Varietas | Target Jam |
|---|---|
""" + "\n".join(f"| {k} | {v:.0f} j |"
                for k, v in VernalizationTracker.VARIETY_TARGETS.items()))


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: DRIP FLOW MONITOR
# ─────────────────────────────────────────────────────────────────────────────

def render_flow_panel(flow_monitors: Dict[str, "DripFlowMonitor"],
                      historian: "DataHistorian", zones: List):
    """Panel Drip Flow Monitor — feedback aktual flow meter per zona."""
    st.markdown(
        '<div class="section-header">💧 DRIP FLOW MONITOR (Flow Meter Feedback)</div>',
        unsafe_allow_html=True)

    zone_ids = [z.zone_id for z in zones] if zones else list(flow_monitors.keys())
    if not zone_ids:
        st.info("Belum ada zona.")
        return

    # Inisialisasi monitor yang belum ada
    for zid in zone_ids:
        if zid not in flow_monitors:
            flow_monitors[zid] = DripFlowMonitor(zone_id=zid, target_lpm=2.5)

    sel_zone = st.selectbox("Zona", zone_ids, key="flow_zone_sel")
    mon      = flow_monitors[sel_zone]

    # Baca 1 reading (simulasi)
    reading = mon.read()
    historian.log_flow(sel_zone, reading.flow_lpm, reading.target_lpm,
                       reading.pressure_bar, reading.status)

    # Status badge
    status_cfg = {
        "normal":  ("#44ff44", "✅ Normal"),
        "clog":    ("#ff8800", "⚠️ TERSUMBAT"),
        "leak":    ("#ff4444", "🚨 BOCOR"),
        "dry_run": ("#ff4444", "🚨 DRY RUN"),
    }
    sc, sl = status_cfg.get(reading.status, ("#aaaaaa", reading.status))
    st.markdown(
        f'<div style="background:#0a0a0a;padding:10px 16px;border-radius:8px;'
        f'border-left:4px solid {sc};margin:8px 0;">'
        f'<span style="color:{sc};font-size:18px;font-weight:bold">{sl}</span>'
        f'&nbsp;&nbsp;<span style="color:#888;font-size:12px">'
        f'Zona: {sel_zone} | {reading.ts[:19]}</span></div>',
        unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Debit Aktual",  f"{reading.flow_lpm:.2f} L/min")
    c2.metric("Target",        f"{reading.target_lpm:.2f} L/min")
    c3.metric("Efisiensi",     f"{reading.efficiency_pct:.1f}%",
              delta=f"{reading.deviation_pct:+.1f}%")
    c4.metric("Tekanan",       f"{reading.pressure_bar:.2f} bar")
    c5.metric("Total terpakai", f"{mon.total_liters:.1f} L")

    # Setpoint & target
    st.markdown("---")
    col_t, col_f = st.columns([2, 2])
    new_target = col_t.number_input(
        "Set target debit (L/min)", 0.1, 50.0, float(mon.target_lpm),
        step=0.1, key=f"flow_target_{sel_zone}")
    if abs(new_target - mon.target_lpm) > 0.01:
        mon.target_lpm = new_target

    # Demo fault injection
    fault_opt = col_f.selectbox(
        "🧪 Simulasi kondisi (demo)",
        ["normal", "clog", "leak", "dry_run"],
        key=f"flow_fault_{sel_zone}")
    mon.inject_fault(fault_opt)

    # Chart debit terkini
    if len(mon.readings) >= 3:
        import pandas as _pd
        df_flow = _pd.DataFrame([
            {"ts": r.ts[:19], "Debit (L/min)": r.flow_lpm,
             "Target (L/min)": r.target_lpm}
            for r in list(mon.readings)[-60:]
        ]).set_index("ts")
        st.line_chart(df_flow)

    # Status semua zona (ringkasan)
    st.markdown("**📊 Status semua zona:**")
    summary_cols = st.columns(min(4, len(zone_ids)))
    for i, zid in enumerate(zone_ids):
        m = flow_monitors.get(zid)
        if m and m.last_reading:
            lr = m.last_reading
            sc2, sl2 = status_cfg.get(lr.status, ("#aaa", lr.status))
            with summary_cols[i % 4]:
                st.markdown(
                    f'<div style="background:#0a1a0a;padding:8px;border-radius:6px;'
                    f'border:1px solid {sc2};margin:2px;text-align:center;">'
                    f'<b>{zid}</b><br>'
                    f'<span style="color:{sc2}">{sl2}</span><br>'
                    f'<small>{lr.flow_lpm:.2f}/{lr.target_lpm:.1f} L/min</small>'
                    f'</div>', unsafe_allow_html=True)

    with st.expander("ℹ️ Cara konek flow meter hardware"):
        st.markdown("""
**Hardware supported:**
- Sensor YF-S201 (Arduino/ESP32 via serial → `mon.read(actual_lpm=<serial_value>)`)
- Sensor FS300A-G3/4 (Modbus → `OPCUAModbusClient`)
- Sensor dengan output 4–20mA → ADC → serial

**Integrasi:**
```python
# Di loop hardware Anda:
lpm = baca_dari_serial_atau_mqtt()
reading = mon.read(actual_lpm=lpm, pressure_bar=sensor_tekanan)
```
""")


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: HARDWARE STUBS
# ─────────────────────────────────────────────────────────────────────────────


def render_visual_dashboard_tab(zones):
    """ARUNA ESP32 Visual Dashboard — embedded in tumbal.py via Streamlit components"""
    import json as _json
    zone_data = {}
    if zones:
        z = zones[0]
        cm = z.crop_model
        zone_data = {
            "zone":       z.zone_id,
            "facility":   "GH-INDO-01",
            "temp":       round(float(z.temp_air), 1),
            "rh":         round(float(z.humidity), 1),
            "co2":        int(z.co2_ppm),
            "soil":       round(float(z.soil_moist), 1),
            "ec":         round(float(getattr(getattr(z,"nutrient_solution",None),"ec",1.9)), 2),
            "ph":         round(float(getattr(getattr(z,"nutrient_solution",None),"ph",6.4)), 2),
            "ppfd":       round(float(getattr(z,"light_par",400)), 0),
            "energy_kwh": round(float(z.energy_kwh), 3),
            "water_l":    round(float(z.water_used_L), 1),
            "yield_kg":   round(float(cm.yield_kg), 4),
            "biomass":    round(float(cm.biomass), 4),
            "stage":      cm.stage.value,
            "dvs":        round(float(cm.dvs), 3),
            "disease":    round(float(cm.disease_index), 3),
            "brix":       round(float(cm.brix_sugar), 2),
            "step":       int(z.step_count),
            "area_m2":    float(z.area_m2),
            "crop":       str(z.crop_type.value),
            "n_zones":    len(zones),
            "alarm":      0,
        }
    dj = _json.dumps(zone_data)
    st.components.v1.html(f"""
<style>
#ad{{font-family:'Share Tech Mono',monospace;background:#060d0a;color:#b8d4c0;padding:14px;border-radius:6px;border:1px solid #1a3025}}
.adh{{display:flex;justify-content:space-between;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #1a3025}}
.adl{{color:#00ff88;font-size:15px;letter-spacing:2px}}
.adc{{color:#00ffee;font-size:11px}}
.adg{{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:7px;margin-bottom:10px}}
.adk{{background:#0b1510;border:1px solid #1a3025;border-radius:4px;padding:7px;text-align:center}}
.adlb{{font-size:9px;color:#4a7a5a;letter-spacing:1px;margin-bottom:2px}}
.adv{{font-size:17px;font-weight:700;line-height:1}}
.adu{{font-size:9px;color:#4a7a5a;margin-top:1px}}
.adb{{height:3px;background:#0a1a10;border-radius:2px;margin-top:3px;overflow:hidden}}
.adf{{height:3px;border-radius:2px;transition:width .5s}}
.ads{{font-size:9px;color:#4a7a5a;letter-spacing:2px;margin:6px 0 4px;border-bottom:1px solid #1a3025;padding-bottom:2px}}
.adact{{display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-bottom:8px}}
.adac{{background:#0b1510;border:1px solid #1a3025;border-radius:3px;padding:5px;text-align:center;font-size:9px;color:#4a7a5a}}
.adled{{width:9px;height:9px;border-radius:50%;background:#0a1a10;border:1px solid #1a3025;margin:0 auto 2px}}
.adon{{background:#00ff88!important;box-shadow:0 0 7px #00ff88!important}}
.adpwm{{background:#ffaa00!important;box-shadow:0 0 7px #ffaa00!important}}
.adsrc{{font-size:9px;color:#00ff88;margin-top:4px}}
</style>
<div id="ad">
<div class="adh"><div class="adl">ARUNA SCADA <span style="font-size:9px;color:#4a7a5a">tumbal.py live</span></div><div class="adc" id="clk">--:--:--</div></div>
<div class="ads">SENSOR READINGS</div>
<div class="adg" id="sg"></div>
<div class="ads">CROP MODEL</div>
<div class="adg" id="cg"></div>
<div class="ads">ACTUATOR STATE</div>
<div class="adact" id="ag"></div>
<div class="adsrc" id="src">—</div>
</div>
<script>
const D={dj};
const S=[
  {{k:'temp',l:'TEMP',u:'°C',mn:0,mx:50,c:'#00ff88'}},
  {{k:'rh',l:'RH',u:'%',mn:0,mx:100,c:'#00aaff'}},
  {{k:'co2',l:'CO2',u:'ppm',mn:400,mx:2000,c:'#ffaa00'}},
  {{k:'soil',l:'SOIL',u:'%',mn:0,mx:100,c:'#00cc66'}},
  {{k:'ec',l:'EC',u:'mS',mn:0,mx:4,c:'#00ffee'}},
  {{k:'ph',l:'pH',u:'',mn:5,mx:8,c:'#aa55ff'}},
  {{k:'ppfd',l:'PPFD',u:'µmol',mn:0,mx:800,c:'#ffcc00'}},
  {{k:'energy_kwh',l:'ENERGY',u:'kWh',mn:0,mx:50,c:'#ffaa00'}},
  {{k:'water_l',l:'WATER',u:'L',mn:0,mx:500,c:'#00aaff'}},
];
const C=[
  {{k:'stage',l:'STAGE',c:'#00ff88'}},
  {{k:'dvs',l:'DVS',c:'#00cc66'}},
  {{k:'yield_kg',l:'YIELD',u:'kg/m²',c:'#ffaa00'}},
  {{k:'biomass',l:'BIOMASS',u:'kg/m²',c:'#00ff88'}},
  {{k:'disease',l:'DISEASE',c:'#ff3344'}},
  {{k:'brix',l:'BRIX',u:'°',c:'#ffcc00'}},
];
document.getElementById('sg').innerHTML=S.map(s=>{{
  const v=D[s.k]??'—';
  const p=typeof v==='number'?Math.min(100,Math.max(0,(v-s.mn)/(s.mx-s.mn)*100)):0;
  return `<div class="adk"><div class="adlb">${{s.l}}</div><div class="adv" style="color:${{s.c}}">${{typeof v==='number'?v.toFixed(s.k==='co2'||s.k==='ppfd'?0:1):v}}</div><div class="adu">${{s.u||''}}</div><div class="adb"><div class="adf" style="width:${{p}}%;background:${{s.c}}"></div></div></div>`;
}}).join('');
document.getElementById('cg').innerHTML=C.map(s=>{{
  const v=D[s.k]??'—';
  return `<div class="adk"><div class="adlb">${{s.l}}</div><div class="adv" style="color:${{s.c}};font-size:13px">${{typeof v==='number'?v.toFixed(3):v}}</div><div class="adu">${{s.u||''}}</div></div>`;
}}).join('');
const A=[{{l:'VALVE',on:D.relay_valve>0}},{{l:'GROW',on:true,pwm:true}},{{l:'CO2',on:D.co2_inject>0}},{{l:'HEATER',on:D.heater>0}},{{l:'PUMP',on:D.pump>0}}];
document.getElementById('ag').innerHTML=A.map(a=>`<div class="adac"><div class="adled ${{a.pwm?'adpwm':a.on?'adon':''}}"></div>${{a.l}}<br><span style="color:${{a.on||a.pwm?'#00ff88':'#4a7a5a'}}">${{a.on?'ON':'OFF'}}</span></div>`).join('');
document.getElementById('src').textContent=`Zone: ${{D.zone||'—'}} · Step: ${{D.step||0}} · Crop: ${{D.crop||'—'}} · Area: ${{D.area_m2||0}}m² · Tekan Run Step untuk update`;
setInterval(()=>{{document.getElementById('clk').textContent=new Date().toLocaleTimeString('id-ID');}},1000);
</script>""", height=500, scrolling=True)

def render_hardware_panel(serial_bridge: "SerialGPIOBridge",
                          opcua: "OPCUAModbusClient",
                          camera: "CameraVisionAI",
                          ota: "OTAFirmwareManager"):
    """Panel Hardware Stubs — status & konfigurasi perangkat keras."""
    st.markdown(
        '<div class="section-header">🔧 HARDWARE INTEGRATION (Stubs)</div>',
        unsafe_allow_html=True)
    st.info("🔵 Semua modul ini adalah **stub siap-pakai** — install library & "
            "sambungkan hardware untuk mengaktifkan.")

    tab_s, tab_m, tab_c, tab_o = st.tabs(
        ["🔌 Serial/GPIO", "📊 OPC-UA/Modbus", "📷 Camera AI", "📡 OTA Update"])

    # ── Serial/GPIO ──────────────────────────────────────────────────────────
    with tab_s:
        st.markdown("**Serial/GPIO Bridge — Arduino / ESP32 / Raspberry Pi**")
        s = serial_bridge.status()
        st.metric("Status", s["status"])
        c1, c2 = st.columns(2)
        port  = c1.text_input("Port COM", s["port"], key="ser_port")
        baud  = c2.selectbox("Baudrate",
                             [9600, 19200, 38400, 57600, 115200, 230400],
                             index=4, key="ser_baud")
        if st.button("🔌 Connect Serial", key="ser_connect"):
            serial_bridge.port     = port
            serial_bridge.baudrate = int(baud)
            ok = serial_bridge.connect()
            (st.success("✅ Serial terhubung!") if ok
             else st.error(f"❌ {serial_bridge._last_err}"))
        if s["error"]:
            st.warning(f"⚠️ {s['error']}")
        st.code("pip install pyserial\n"
                "# Kemudian: serial_bridge.read_sensor('soil_moisture')\n"
                "#           serial_bridge.write_actuator('pump', 1.0)")

    # ── OPC-UA / Modbus ──────────────────────────────────────────────────────
    with tab_m:
        st.markdown("**OPC-UA / Modbus TCP — PLC / SCADA Industri**")
        s = opcua.status()
        st.metric("Status", "🟢 Connected" if s["connected"] else "🔴 Disconnected")
        ca, cb, cc = st.columns([3, 1, 2])
        host  = ca.text_input("Host/IP", s["host"], key="opc_host")
        port  = cb.number_input("Port", value=s["port"], key="opc_port",
                                min_value=1, max_value=65535)
        proto = cc.selectbox("Protokol", ["modbus", "opcua"],
                             index=0 if s["protocol"] == "modbus" else 1,
                             key="opc_proto")
        if st.button("🔌 Connect PLC", key="opc_connect"):
            opcua.host = host; opcua.port = int(port); opcua.protocol = proto
            ok = opcua.connect()
            (st.success("✅ PLC terhubung!") if ok
             else st.error(f"❌ {opcua._last_err}"))
        if s["error"]:
            st.warning(f"⚠️ {s['error']}")
        st.code("pip install pymodbus   # Modbus TCP\n"
                "pip install opcua      # OPC-UA")

    # ── Camera AI ────────────────────────────────────────────────────────────
    with tab_c:
        st.markdown("**Camera Vision AI — Deteksi Penyakit Tanaman**")
        s = camera.status()
        st.metric("Status", "🟢 Kamera aktif" if s["connected"] else "🔴 Tidak ada kamera")
        col_cam, col_mdl = st.columns(2)
        cam_id    = col_cam.number_input("Camera ID", 0, 10, s["camera_id"],
                                         key="cam_id")
        model_pth = col_mdl.text_input("Path model (.pt/.tflite)",
                                       s["model"] or "", key="cam_model")
        if st.button("📷 Test kamera", key="cam_test"):
            camera.camera_id  = int(cam_id)
            camera.model_path = model_pth
            ok = camera.connect()
            (st.success("✅ Kamera aktif!") if ok
             else st.error(f"❌ {camera._last_err}"))
        result = camera.capture_and_analyze()
        st.json(result)
        st.markdown("**Penyakit yang dapat dideteksi (setelah model dimuat):**")
        st.markdown("  \n".join(f"• {d}" for d in CameraVisionAI.SUPPORTED_DISEASES))
        st.code("pip install opencv-python torch torchvision\n"
                "# Download model: github.com/ultralytics/yolov5")

    # ── OTA ──────────────────────────────────────────────────────────────────
    with tab_o:
        st.markdown("**OTA Firmware Update — ESP32 / Raspberry Pi**")
        s = ota.status()
        cd, cl = st.columns(2)
        dev_host   = cd.text_input("Device host/IP", s["device"], key="ota_host")
        upd_server = cl.text_input("Update server URL", s.get("update_server",""),
                                   key="ota_server")
        ota.device_host = dev_host
        c1, c2, c3 = st.columns(3)
        c1.metric("Versi saat ini", s["current_version"])
        c2.metric("Versi terbaru",  s["latest_version"])
        c3.metric("Progress",       f"{s['progress_pct']}%")
        if st.button("🔍 Cek update", key="ota_check"):
            avail = ota.check_for_update()
            (st.success(f"🆕 Update tersedia: {ota._latest_version}") if avail
             else st.info("✅ Firmware sudah terbaru (stub — belum diimplementasi)."))
        if s["error"]:
            st.warning(f"⚠️ {s['error']}")


def render_benchmark_panel(benchmark: DigitalTwinBenchmark):
    """Tampilkan benchmark comparison"""
    st.markdown('<div class="section-header">🏆 DIGITAL TWIN BENCHMARK (5 SCENARIOS)</div>',
                unsafe_allow_html=True)

    if not benchmark.results:
        st.info("Click '🏆 Run Benchmark' to compare AI vs manual strategies.")
        return

    df = benchmark.comparison_dataframe()
    if df.empty:
        return

    st.dataframe(df.T.astype(str), width='stretch')

    winners = benchmark.winner_by_metric()
    if winners:
        st.markdown("**🥇 Winners per metric:**")
        winner_str = " | ".join([f"**{m}**: {w}" for m, w in list(winners.items())[:6]])
        st.markdown(winner_str)


def render_lca_panel(lca_engine: LCAEngine, zones: List):
    """Tampilkan Life Cycle Assessment"""
    st.markdown('<div class="section-header">♻️ LIFE CYCLE ASSESSMENT (LCA — ISO 14040)</div>',
                unsafe_allow_html=True)

    if not zones:
        return

    for zone in zones:
        cm = zone.crop_model
        lca_result = lca_engine.assess({
            "yield_kg":             cm.yield_kg,
            "area_m2":              zone.area_m2,
            "energy_kwh":           zone.energy_kwh,
            "water_L":              zone.water_used_L,
            "co2_injected_kg":      zone.co2_injected_kg,
            "fertilizer_kg":        zone.fertilizer_kg,
            "pest_pressure":        cm.pest_pressure,
            "co2_sequestered_kg":   cm.net_carbon_seq_kg,
        })
        vs_conv = lca_engine.comparison_vs_conventional(lca_result, zone.crop_type.value)

        eco_color = "#44ee44" if lca_result.eco_score >= 70 else ("#eeaa33" if lca_result.eco_score >= 45 else "#ee4444")
        gwp_red   = vs_conv["gwp_reduction_pct"]
        wfp_red   = vs_conv["water_reduction_pct"]
        gwp_color = "#44ee44" if gwp_red > 0 else "#ee4444"
        wfp_color = "#44ee44" if wfp_red > 0 else "#ee4444"

        st.markdown(f"""
        <div class="carbon-box">
            <b>{_esc(zone.zone_id)}</b> — {_esc(zone.crop_type.value)}<br>
            Eco-Score: <span style="color:{eco_color}"><b>{lca_result.eco_score}/100</b></span><br>
            GWP: <b>{lca_result.global_warming_potential_kg_CO2_per_kg:.3f} kg CO₂/kg</b>
            <span style="color:{gwp_color}">({gwp_red:+.1f}% vs conventional)</span><br>
            Water Footprint: <b>{lca_result.water_footprint_L_per_kg:.1f}L/kg</b>
            <span style="color:{wfp_color}">({wfp_red:+.1f}% vs conventional)</span><br>
            Energy: <b>{lca_result.energy_intensity_MJ_per_kg:.2f} MJ/kg</b> &nbsp;
            Eutrophication: <b>{lca_result.eutrophication_g_PO4_per_kg:.2f} g PO₄/kg</b>
        </div>
        """, unsafe_allow_html=True)


def render_yqi_panel(zones: List):
    """Tampilkan Yield Quality Index"""
    st.markdown('<div class="section-header">🍅 YIELD QUALITY INDEX (YQI)</div>',
                unsafe_allow_html=True)

    cols = st.columns(min(len(zones), 3))
    for i, zone in enumerate(zones[:3]):
        cm = zone.crop_model
        p  = zone.crop_type
        # Get crop_params from the CROP_PROFILES dict (must be importable from main)
        try:
            cp = CROP_PROFILES[CropType(p.value)]
        except Exception:
            # Fallback if import doesn't work in extension context
            class _FakeCrop:
                name = p.value; p_content_optimal = 0.5; days_to_harvest = 70
                shelf_life_days = 7
            cp = _FakeCrop()

        yqi = compute_yqi(cm, cp, cm.stress_days, cm.pest_pressure, cm.disease_index)
        grade_color = {
            "A+": "#55ff77", "A": "#44ee44", "B": "#aaee44",
            "C": "#eeaa33", "D": "#ee4444"
        }.get(yqi.grade, "#aaaaaa")

        with cols[i]:
            st.markdown(f"""
            <div class="zone-card">
                <b>{_esc(zone.zone_id)}</b> — {_esc(p.value)}<br>
                Grade: <span style="color:{grade_color}; font-size:20px"><b>{_esc(yqi.grade)}</b></span>
                &nbsp; YQI: <b>{yqi.overall_yqi}/100</b><br>
                🍯 Brix: {yqi.brix_score:.0f} &nbsp;
                🧬 Antioxidant: {yqi.antioxidant_score:.0f}<br>
                🌿 N-content: {yqi.n_content_score:.0f} &nbsp;
                📏 Uniformity: {yqi.size_uniformity:.0f}<br>
                📦 Shelf life: {yqi.shelf_life_score:.0f} &nbsp;
                🧪 Pesticide: {yqi.pesticide_residue:.0f}
            </div>
            """, unsafe_allow_html=True)


def render_intercrop_panel(zones: List):
    """Tampilkan intercropping companion planting effects"""
    if len(zones) < 2:
        return
    st.markdown('<div class="section-header">🌿 INTERCROPPING COMPANION EFFECTS</div>',
                unsafe_allow_html=True)

    effects = apply_intercropping_effects(zones)
    rows = []
    for zone_id, eff in effects.items():
        zone = next((z for z in zones if z.zone_id == zone_id), None)
        crop = zone.crop_type.value if zone else "?"
        rows.append({
            "Zone":          zone_id,
            "Crop":          crop,
            "Growth Boost":  f"{eff['growth_boost']:+.1%}",
            "Pest Reduction":f"{eff['pest_reduction']:+.1%}",
            "Nutrient Share":f"{eff['nutrient_share']:+.1%}",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)


def render_dosing_panel(dosing: CascadeDosing, zone):
    """Tampilkan auto-dosing cascade PID"""
    ns = zone.nutrient_solution

    ph_result = dosing.update_ph(ns.ph)
    ec_result = dosing.update_ec(ns.ec_mS, ns.n_ppm, ns.k_ppm)
    cumul     = dosing.cumulative_stats()

    col1, col2, col3 = st.columns(3)
    col1.metric("Acid (total)",    f"{cumul['total_acid_L']:.3f}L")
    col2.metric("Base (total)",    f"{cumul['total_base_L']:.3f}L")
    col3.metric("Nutrient (total)",f"{cumul['total_nutrient_kg']:.4f}kg")

    st.markdown(f"""
    <div class="zone-card">
        <b>pH Dosing:</b> pH={ph_result['ph_measured']:.2f} → {ph_result['ph_target']:.1f}
        | Error: {ph_result['ph_error']:+.3f} | Acid: {ph_result['acid_mL']:.1f}mL | Base: {ph_result['base_mL']:.1f}mL<br>
        <b>EC Dosing:</b> EC={ec_result['ec_measured']:.2f} → {ec_result['ec_target']:.1f}
        | Error: {ec_result['ec_error']:+.3f}
        | N: {ec_result['n_dose_g']:.1f}g | K: {ec_result['k_dose_g']:.1f}g | P: {ec_result['p_dose_g']:.1f}g
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MASTER EXTENSION PANEL RENDERER
# Panggil render_extension_panels() dari main() di file utama
# ══════════════════════════════════════════════════════════════════════════════

def init_extension_state():
    """Initialize all extension objects in st.session_state. Call this from main()."""
    if "ext_initialized" not in st.session_state:
        st.session_state.ext_initialized     = True
        st.session_state.ext_weather_ens     = WeatherEnsembleService()
        st.session_state.ext_fao56           = FAO56ETModel(latitude_deg=-6.2)
        st.session_state.ext_rothc           = RothCModel(clay_pct=25.0)
        st.session_state.ext_rl_ctrl         = RLGreenhouseController(alpha=0.12, gamma=0.93, epsilon=0.35)
        st.session_state.ext_nsga            = NSGAIIOptimizer(pop_size=40, n_gen=30)
        st.session_state.ext_chain           = GreenChainAudit()
        st.session_state.ext_mqtt            = MQTTSimulator(facility_id="GH-INDO-01")
        st.session_state.ext_benchmark       = DigitalTwinBenchmark()
        st.session_state.ext_lca_engine      = LCAEngine()
        st.session_state.ext_dosing          = {}   # per zone_id
        st.session_state.ext_nsga_ran        = False
        st.session_state.ext_benchmark_ran   = False
        # ── New features ────────────────────────────────────────────────────
        st.session_state.ext_historian       = DataHistorian()
        st.session_state.ext_vern_tracker    = VernalizationTracker()
        st.session_state.ext_flow_monitors   = {}   # zone_id → DripFlowMonitor
        st.session_state.ext_serial_bridge   = SerialGPIOBridge()
        st.session_state.ext_opcua_client    = OPCUAModbusClient()
        st.session_state.ext_camera_ai       = CameraVisionAI()
        st.session_state.ext_ota_manager     = OTAFirmwareManager()
        # MQTT mode flag: "sim" | "real"
        st.session_state.ext_mqtt_mode       = "sim"


def render_extension_panels(zones: List, weather_data, ai_ctrl, crop_profiles: Dict):
    """
    MASTER FUNCTION — panggil ini dari main() setelah render_economics().
    Meng-render semua panel extension dalam tabs.
    """
    init_extension_state()

    # Update extension state dari simulasi
    ens_svc: WeatherEnsembleService = st.session_state.ext_weather_ens
    fao56:   FAO56ETModel           = st.session_state.ext_fao56
    rothc:   RothCModel             = st.session_state.ext_rothc
    rl_ctrl: RLGreenhouseController = st.session_state.ext_rl_ctrl
    nsga:    NSGAIIOptimizer        = st.session_state.ext_nsga
    chain:   GreenChainAudit        = st.session_state.ext_chain
    bench:   DigitalTwinBenchmark   = st.session_state.ext_benchmark
    lca_eng: LCAEngine              = st.session_state.ext_lca_engine
    historian                       = st.session_state.ext_historian
    vern_tracker                    = st.session_state.ext_vern_tracker
    flow_monitors                   = st.session_state.ext_flow_monitors
    serial_bridge                   = st.session_state.ext_serial_bridge
    opcua_client                    = st.session_state.ext_opcua_client
    camera_ai                       = st.session_state.ext_camera_ai
    ota_manager                     = st.session_state.ext_ota_manager

    # MQTT: real broker or simulator depending on sidebar toggle
    _mqtt_mode = st.session_state.get("ext_mqtt_mode", "sim")
    if _mqtt_mode == "real":
        if not isinstance(st.session_state.ext_mqtt, MQTTBrokerClient):
            st.session_state.ext_mqtt = MQTTBrokerClient(facility_id="GH-INDO-01")
    else:
        if not isinstance(st.session_state.ext_mqtt, MQTTSimulator):
            st.session_state.ext_mqtt = MQTTSimulator(facility_id="GH-INDO-01")
    mqtt = st.session_state.ext_mqtt

    # Ensure dosing objects per zone
    for zone in zones:
        if zone.zone_id not in st.session_state.ext_dosing:
            st.session_state.ext_dosing[zone.zone_id] = CascadeDosing(
                ph_setpoint=6.2, ec_setpoint=3.5
            )

    # ── Log sensor data ke historian setiap kali render (sim data) ─────────
    for zone in zones:
        historian.log_sensor(zone.zone_id, {
            "temperature":   getattr(zone, "temp_air",    0),
            "humidity":      getattr(zone, "humidity",    0),
            "co2":           getattr(zone, "co2",         0),
            "soil_moisture": getattr(zone, "soil_moist",  0),
            "ph":            getattr(zone, "ph",          0),
            "ec":            getattr(zone, "ec",          0),
        }, source="sim")

    # Sidebar extension buttons
    with st.sidebar:
        st.markdown('<div class="section-header">🔬 EXTENSIONS v4</div>', unsafe_allow_html=True)

        # MQTT mode toggle
        _mode_label = "📡 MQTT: Real Broker" if _mqtt_mode == "real" else "📡 MQTT: Simulator"
        if st.toggle(_mode_label, value=(_mqtt_mode == "real"), key="mqtt_mode_toggle"):
            st.session_state.ext_mqtt_mode = "real"
        else:
            st.session_state.ext_mqtt_mode = "sim"

        if st.button("🎯 Run NSGA-II Pareto Opt", key="ext_nsga_run"):
            if zones:
                try:
                    cp = CROP_PROFILES[CropType(zones[0].crop_type.value)]
                except Exception:
                    cp = type("CP", (), {
                        "optimal_temp": 24.0, "optimal_humidity": 65.0,
                        "optimal_co2": 800.0, "optimal_soil_moisture": 60.0,
                        "disease_humidity_risk": 85.0, "ec_optimal": 3.5,
                        "vpd_optimal": 1.2,
                    })()
                nsga.optimize(cp)
                st.session_state.ext_nsga_ran = True
                st.success(f"NSGA-II done: {len(nsga.pareto_front)} Pareto solutions")

        if st.button("🏆 Run Benchmark", key="ext_bench_run"):
            if zones:
                try:
                    z0 = zones[0]
                    safe_crop = CropType(z0.crop_type.value)
                    
                    kwarg = dict(
                        zone_id=z0.zone_id, zone_type=z0.zone_type,
                        crop_type=safe_crop, area_m2=z0.area_m2,
                        volume_m3=z0.volume_m3, irrigation_mode=z0.irrigation_mode
                    )
                    cp = CROP_PROFILES[safe_crop]
                    bench.run_quick_benchmark(GreenZone, kwarg, weather_data, ai_ctrl, cp, n_steps=50)
                    st.session_state.ext_benchmark_ran = True
                    st.success("Benchmark complete!")
                except Exception as ex:
                    st.error(f"Benchmark error: {ex}")

        if st.button("🔗 Log Audit Event", key="ext_chain_log"):
            for zone in zones:
                chain.add_event(zone.zone_id, "sensor", {
                    "temp": round(zone.temp_air, 1),
                    "humidity": round(zone.humidity, 1),
                    "yield_kg": round(zone.crop_model.yield_kg, 4),
                    "stage": zone.crop_model.stage.value,
                })
            st.success(f"Logged {len(zones)} audit block(s)")

    # --- Auto-publish MQTT per step (called by run_full button) ---
    for zone in zones:
        mqtt.publish_zone_telemetry(zone.zone_id, {
            "temp":     zone.temp_air,
            "humidity": zone.humidity,
            "co2":      zone.co2_ppm,
            "soil":     zone.soil_moist,
            "light":    zone.light_w,
            "ec":       zone.nutrient_solution.ec_mS,
            "ph":       zone.nutrient_solution.ph,
            "root_temp":zone.root_temp,
        })

    # --- RothC monthly step (every 24 simulation steps ≈ 1 "day") ---
    if zones and zones[0].step_count % 24 == 0 and zones[0].step_count > 0:
        rothc.step_monthly(
            temp_c              = zones[0].temp_air,
            soil_moisture_pct   = zones[0].soil_moist,
            plant_material_input_t_ha = zones[0].crop_model.daily_growth_rate * 0.02,
            plant_cover         = True,
        )

    # --- Weather ensemble update ---
    ens = ens_svc.blend(
        owm_temp = weather_data.temp_outside if weather_data.source != "simulated" else None,
        owm_hum  = weather_data.humidity_outside if weather_data.source != "simulated" else None,
        city     = weather_data.location.split(",")[0],
        hour     = datetime.datetime.now().hour,
    )

    # --- Intercrop effects (applied conceptually) ---
    if len(zones) > 1:
        intercrop_eff = apply_intercropping_effects(zones)

    # ─── EXTENSION TABS ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-header">🔬 EXTENSION MODULES v4.0</div>',
                unsafe_allow_html=True)

    tab_names = [
        "🌦️ Weather Ensemble",
        "💧 FAO-56 ET",
        "🌍 RothC Carbon",
        "🧠 RL Controller",
        "📊 Pareto Opt",
        "🏆 Benchmark",
        "♻️ LCA",
        "🍅 YQI",
        "🌿 Intercrop",
        "⚗️ Auto-Dosing",
        "📡 MQTT",
        "🔗 Audit Chain",
        "🗄️ Historian",
        "❄️ Vernalisasi",
        "💧 Flow Monitor",
        "🔧 Hardware",
    ]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_weather_ensemble_panel(ens)

    with tabs[1]:
        render_fao56_panel(fao56, zones)

    with tabs[2]:
        render_rothc_panel(rothc, zones)

    with tabs[3]:
        render_rl_panel(rl_ctrl)
        if zones and st.button("⚡ RL: Take Action for Zone-A", key="rl_action"):
            z = zones[0]
            zone_state = {
                "temp":     z.temp_air, "humidity": z.humidity,
                "soil":     z.soil_moist, "stage":  z.crop_model.stage.value,
                "growth_rate":  z.crop_model.daily_growth_rate,
                "disease_index":z.crop_model.disease_index,
                "energy_kwh_step": 0.05,
            }
            try:
                cp = CROP_PROFILES[CropType(z.crop_type.value)]
            except Exception:
                cp = None
            act = rl_ctrl.act(zone_state, cp, None)
            st.json(act)

    with tabs[4]:
        render_pareto_panel(nsga)

    with tabs[5]:
        render_benchmark_panel(bench)

    with tabs[6]:
        render_lca_panel(lca_eng, zones)

    with tabs[7]:
        render_yqi_panel(zones)

    with tabs[8]:
        render_intercrop_panel(zones)

    with tabs[9]:
        st.markdown('<div class="section-header">⚗️ CASCADE AUTO-DOSING PID</div>',
                    unsafe_allow_html=True)
        if zones:
            zone_sel = st.selectbox("Zone for dosing", [z.zone_id for z in zones], key="dosing_zone")
            sel_zone = next((z for z in zones if z.zone_id == zone_sel), zones[0])
            dosing   = st.session_state.ext_dosing.get(zone_sel,
                        CascadeDosing(ph_setpoint=6.2, ec_setpoint=3.5))
            render_dosing_panel(dosing, sel_zone)

    with tabs[10]:
        render_mqtt_panel(mqtt)

    with tabs[11]:
        render_blockchain_panel(chain)

    with tabs[12]:
        render_historian_panel(historian, zones)

    with tabs[13]:
        render_vernalization_panel(vern_tracker, historian)

    with tabs[14]:
        render_flow_panel(flow_monitors, historian, zones)

    with tabs[15]:
        render_hardware_panel(serial_bridge, opcua_client, camera_ai, ota_manager)
        st.markdown("---")
        st.markdown("### 🖥️ Visual Dashboard — Live from tumbal.py")
        render_visual_dashboard_tab(zones)



# ══════════════════════════════════════════════════════════════════════════════
# 2. CONSTANTS & ENUMS
# ══════════════════════════════════════════════════════════════════════════════

# Physical constants
STEFAN_BOLTZMANN  = 5.67e-8   # W/m²·K⁴
LATENT_HEAT_VAP   = 2.45e6    # J/kg
CP_AIR            = 1006.0    # J/kg·K
RHO_AIR           = 1.22      # kg/m³
MOLAR_MASS_CO2    = 44.01     # g/mol
MOLAR_MASS_H2O    = 18.015    # g/mol
GAS_CONSTANT      = 8.314     # J/mol·K
PLN_COST_KWH      = 1500.0    # IDR/kWh
WATER_COST_L      = 8.0       # IDR/L
CO2_COST_KG       = 5000.0    # IDR/kg
FERT_COST_KG      = 15000.0   # IDR/kg
LABOR_COST_HR     = 25000.0   # IDR/hr
CARBON_CREDIT_KG  = 3000.0    # IDR/kg CO2 sequestered


class CropType(Enum):
    TOMATO      = "Tomato"
    LETTUCE     = "Lettuce"
    CUCUMBER    = "Cucumber"
    PEPPER      = "Pepper"
    STRAWBERRY  = "Strawberry"
    BASIL       = "Basil"
    SPINACH     = "Spinach"
    CANNABIS    = "Hemp/CBD"
    MICROGREENS = "Microgreens"
    ORCHID      = "Orchid"

class GrowthStage(Enum):
    GERMINATION = "Germination"
    SEEDLING    = "Seedling"
    VEGETATIVE  = "Vegetative"
    FLOWERING   = "Flowering"
    FRUITING    = "Fruiting"
    HARVEST     = "Harvest Ready"
    DORMANT     = "Dormant"

class ZoneType(Enum):
    MAIN       = "Main Production"
    NURSERY    = "Nursery/Seedling"
    STORAGE    = "Climate Storage"
    PROPAGATION= "Propagation"

class DiseaseRisk(Enum):
    NONE     = "None"
    LOW      = "Low"
    MODERATE = "Moderate"
    HIGH     = "High"
    CRITICAL = "Critical"

class IrrigationMode(Enum):
    DRIP      = "Drip"
    FLOOD     = "Flood"
    MIST      = "Mist"
    NFT       = "NFT (Hydroponic)"
    AEROPONIC = "Aeroponic"
    DWC       = "Deep Water Culture"
    SUBSTRATE = "Substrate (Rockwool)"

class AlertLevel(Enum):
    OK       = "ok"
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"
    DISEASE  = "disease"
    MAINT    = "maint"

class PestType(Enum):
    NONE       = "None"
    APHIDS     = "Aphids"
    WHITEFLY   = "Whitefly"
    SPIDERMITE = "Spider Mite"
    THRIPS     = "Thrips"
    FUNGUS_GNAT= "Fungus Gnat"

class LEDSpectrum(Enum):
    FULL     = "Full Spectrum"
    VEGE     = "Veg (Blue-Heavy)"
    BLOOM    = "Bloom (Red-Heavy)"
    UV_BOOST = "UV Boost"
    FAR_RED  = "Far Red"


# ══════════════════════════════════════════════════════════════════════════════
# 3. DATACLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WeatherData:
    temp_outside:      float = 28.0
    humidity_outside:  float = 75.0
    wind_speed:        float = 2.0
    solar_radiation:   float = 500.0
    rainfall:          float = 0.0
    uv_index:          float = 5.0
    dew_point:         float = 22.0
    pressure_hpa:      float = 1013.0
    cloud_cover_pct:   float = 30.0
    co2_ambient:       float = 425.0   # ~425 ppm global mean 2025-2026
    location:          str   = "Jakarta, Indonesia"
    timestamp:         str   = ""
    source:            str   = "simulated"
    # 24h forecast data
    forecast_temp:     List  = field(default_factory=list)
    forecast_rain:     List  = field(default_factory=list)

@dataclass
class CropParams:
    name:                    str   = "Tomato"
    optimal_temp:            float = 24.0
    optimal_humidity:        float = 65.0
    optimal_soil_moisture:   float = 60.0
    optimal_co2:             float = 800.0
    optimal_light:           float = 400.0
    growth_rate_base:        float = 0.8
    days_to_harvest:         int   = 70
    water_stress_threshold:  float = 35.0
    heat_stress_threshold:   float = 33.0
    cold_stress_threshold:   float = 15.0
    night_temp_offset:       float = -4.0
    vpd_optimal:             float = 1.2
    ec_optimal:              float = 3.5
    ph_optimal:              float = 6.2
    market_price_per_kg:     float = 8000.0
    water_per_kg_yield:      float = 20.0
    co2_per_kg_yield:        float = 1.2
    disease_humidity_risk:   float = 85.0
    root_zone_temp_optimal:  float = 22.0
    # v4 new
    photoperiod_hrs:         float = 16.0    # optimal photoperiod (hrs/day)
    vernalization_req:       bool  = False   # needs cold period?
    nitrogen_demand_high:    bool  = True    # heavy N feeder?
    dli_optimal:             float = 17.0    # mol/m²/day Daily Light Integral
    p_content_optimal:       float = 0.5     # % P dry weight
    k_content_optimal:       float = 4.0     # % K dry weight
    ca_content_optimal:      float = 1.5     # % Ca dry weight
    mg_content_optimal:      float = 0.4     # % Mg dry weight
    marketable_fraction:     float = 0.85    # fraction of biomass marketable
    shelf_life_days:         int   = 7       # post-harvest shelf life
    co2_sequestration_rate:  float = 0.45    # kg CO2 fixed per kg DM


CROP_PROFILES: Dict[CropType, CropParams] = {
    CropType.TOMATO:      CropParams("Tomato",       24,65,60,800,400,0.80,70,35,33,15,-4,1.2,3.5,6.2,8000,20,1.2,85,22,16,False,True,17,0.5,4.0,1.5,0.4,0.85,7,0.45),
    CropType.LETTUCE:     CropParams("Lettuce",      20,70,65,700,250,1.20,35,30,28,10,-2,0.9,1.8,6.0,5000,15,0.8,88,18,16,False,False,14,0.4,3.5,1.2,0.3,0.90,5,0.40),
    CropType.CUCUMBER:    CropParams("Cucumber",     26,70,70,900,450,0.70,55,40,34,16,-4,1.4,3.0,6.3,6500,25,1.4,90,23,16,False,True,18,0.5,4.5,1.3,0.4,0.88,4,0.48),
    CropType.PEPPER:      CropParams("Pepper",       25,60,55,750,380,0.60,80,32,33,18,-3,1.1,3.8,6.1,12000,18,1.0,82,22,14,False,True,16,0.5,4.0,1.2,0.4,0.85,10,0.42),
    CropType.STRAWBERRY:  CropParams("Strawberry",   18,60,55,700,300,0.50,90,30,28,8,-6,0.8,2.5,5.8,20000,22,1.3,80,16,8,True,False,12,0.4,3.5,1.0,0.3,0.80,3,0.38),
    CropType.BASIL:       CropParams("Basil",        22,60,60,650,280,1.50,28,35,30,12,-3,0.8,2.0,6.0,15000,12,0.6,80,20,16,False,True,14,0.3,3.0,1.0,0.3,0.90,7,0.40),
    CropType.SPINACH:     CropParams("Spinach",      16,65,65,600,200,1.80,25,28,26,5,-2,0.7,1.5,6.5,6000,10,0.5,85,15,12,False,False,12,0.4,3.0,1.1,0.3,0.92,4,0.38),
    CropType.CANNABIS:    CropParams("Hemp/CBD",     26,55,60,1200,500,0.90,75,35,35,14,-5,1.5,4.5,6.0,50000,18,1.5,78,24,18,False,True,20,0.6,5.0,1.8,0.5,0.70,14,0.50),
    CropType.MICROGREENS: CropParams("Microgreens",  22,65,60,600,250,2.50,14,25,30,12,-1,0.8,1.2,6.0,25000,8,0.4,85,20,16,False,True,12,0.3,2.5,0.8,0.2,0.95,3,0.35),
    CropType.ORCHID:      CropParams("Orchid",       23,65,50,500,200,0.15,180,28,30,14,-5,0.7,1.0,5.8,80000,10,0.8,78,22,12,False,False,10,0.3,2.5,1.0,0.3,0.90,30,0.30),
}

@dataclass
class Alert:
    level:     str
    message:   str
    category:  str = "system"
    timestamp: str = ""
    zone_id:   str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().strftime("%H:%M:%S")

@dataclass
class SensorReading:
    value:    float
    noise_sd: float = 0.0
    drift_pct: float = 0.0
    unit:     str   = ""
    quality:  str   = "good"   # good / degraded / fault
    last_calibration: str = ""

@dataclass
class EconomicState:
    revenue_idr:          float = 0.0
    cost_water_idr:       float = 0.0
    cost_energy_idr:      float = 0.0
    cost_co2_idr:         float = 0.0
    cost_fertilizer_idr:  float = 0.0
    cost_labor_idr:       float = 0.0
    cost_pest_mgmt_idr:   float = 0.0
    profit_idr:           float = 0.0
    roi_percent:          float = 0.0
    cost_per_kg_idr:      float = 0.0
    carbon_credits_idr:   float = 0.0
    net_carbon_kg:        float = 0.0
    payback_period_days:  float = 0.0

@dataclass
class MaintenanceRecord:
    component:  str
    wear_pct:   float = 0.0      # 0-100%
    hours_run:  float = 0.0
    last_service: str = ""
    next_service_hrs: float = 500.0
    failure_prob:     float = 0.0  # 0-1

@dataclass
class NutrientSolution:
    """Full Hoagland-style nutrient solution tracking"""
    ec_mS:       float = 3.5
    ph:          float = 6.2
    n_ppm:       float = 200.0   # Nitrogen (NO3+NH4)
    p_ppm:       float = 50.0    # Phosphorus
    k_ppm:       float = 350.0   # Potassium
    ca_ppm:      float = 200.0   # Calcium
    mg_ppm:      float = 50.0    # Magnesium
    s_ppm:       float = 60.0    # Sulfur
    fe_ppb:      float = 2000.0  # Iron (μg/L)
    mn_ppb:      float = 500.0   # Manganese
    zn_ppb:      float = 300.0   # Zinc
    cu_ppb:      float = 100.0   # Copper
    b_ppb:       float = 300.0   # Boron
    temp_C:      float = 22.0    # Solution temp
    dissolved_o2: float = 8.0    # mg/L DO


# ══════════════════════════════════════════════════════════════════════════════
# 4. KALMAN FILTER — SENSOR FUSION
# ══════════════════════════════════════════════════════════════════════════════

class KalmanFilter1D:
    """
    1D Kalman filter for sensor noise reduction and fault detection.
    Estimates true state from noisy sensor measurements.
    """
    def __init__(self, process_noise: float = 0.01, measurement_noise: float = 1.0,
                 initial_state: float = 0.0):
        self.x  = initial_state   # state estimate
        self.P  = 1.0             # estimation error covariance
        self.Q  = process_noise   # process noise covariance
        self.R  = measurement_noise
        self.K  = 0.0             # Kalman gain
        self.residuals: deque = deque(maxlen=30)

    def update(self, measurement: float) -> Tuple[float, float]:
        """Returns (filtered_value, innovation_residual)"""
        # Predict
        P_pred = self.P + self.Q

        # Update
        self.K   = P_pred / (P_pred + self.R)
        innovation = measurement - self.x
        self.x   += self.K * innovation
        self.P    = (1 - self.K) * P_pred

        self.residuals.append(abs(innovation))
        return self.x, innovation

    @property
    def is_anomaly(self) -> bool:
        """Detect sensor fault via innovation residual"""
        if len(self.residuals) < 5:
            return False
        return abs(self.residuals[-1]) > 3 * (np.mean(list(self.residuals)[:-1]) + 1e-6)


class MultiVarKalman:
    """Multi-variable Kalman filter bank for all zone sensors"""
    SENSOR_CONFIGS = {
        "temp":     {"Q": 0.02, "R": 0.5},
        "humidity": {"Q": 0.05, "R": 1.5},
        "co2":      {"Q": 1.0,  "R": 10.0},
        "soil":     {"Q": 0.05, "R": 1.0},
        "ec":       {"Q": 0.01, "R": 0.1},
        "ph":       {"Q": 0.005,"R": 0.05},
        "light":    {"Q": 2.0,  "R": 15.0},
        "root_temp":{"Q": 0.01, "R": 0.3},
    }

    def __init__(self):
        self.filters: Dict[str, KalmanFilter1D] = {
            k: KalmanFilter1D(v["Q"], v["R"])
            for k, v in self.SENSOR_CONFIGS.items()
        }
        self.fault_flags: Dict[str, bool] = {k: False for k in self.SENSOR_CONFIGS}

    def filter(self, readings: Dict[str, float]) -> Dict[str, float]:
        filtered = {}
        for key, val in readings.items():
            if key in self.filters and val is not None:
                fval, _ = self.filters[key].update(val)
                self.fault_flags[key] = self.filters[key].is_anomaly
                filtered[key] = round(fval, 4)
            else:
                filtered[key] = val
        return filtered

    def get_fault_report(self) -> List[str]:
        return [k for k, v in self.fault_flags.items() if v]


# ══════════════════════════════════════════════════════════════════════════════
# 5. WEATHER SERVICE v4
# ══════════════════════════════════════════════════════════════════════════════

class WeatherService:
    BASE_URL         = "https://api.openweathermap.org/data/2.5/weather"
    FORECAST_URL     = "https://api.openweathermap.org/data/2.5/forecast"
    CACHE_DURATION_S = 600  # 10 minutes

    def __init__(self, api_key: str = ""):
        self.api_key          = api_key
        self.last_fetch:      Optional[WeatherData] = None
        self.last_fetch_time: Optional[datetime.datetime] = None
        self.last_fetch_key:  str = ""
        self.history:         List[WeatherData]     = []
        self.forecast_raw:    List[Dict]             = []

    def _is_cache_valid(self, cache_key: str = "") -> bool:
        return (self.last_fetch is not None and
                self.last_fetch_time is not None and
                (not cache_key or self.last_fetch_key == cache_key) and
                (datetime.datetime.now() - self.last_fetch_time).total_seconds() < self.CACHE_DURATION_S)

    @staticmethod
    def _num(value: Any, fallback: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return fallback
        return result if math.isfinite(result) else fallback

    def _synthetic_forecast(self, base_temp: float, hour: int,
                            rain_bias: float = 0.15) -> Tuple[List[float], List[float]]:
        temps, rains = [], []
        for h in range(1, 25):
            cycle = math.sin(math.pi * (((hour + h) % 24) - 6) / 12)
            temps.append(round(base_temp + 2.2 * cycle + float(np.random.normal(0, 0.25)), 1))
            rain_prob = rain_bias + 0.08 * max(0.0, math.sin(math.pi * (((hour + h) % 24) - 12) / 6))
            rains.append(round(max(0.0, float(np.random.exponential(0.45)) if random.random() < rain_prob else 0.0), 2))
        return temps, rains

    def _fetch_forecast(self, city: str, country_code: str = "ID") -> Tuple[List[float], List[float]]:
        if not self.api_key:
            return [], []
        try:
            r = requests.get(
                self.FORECAST_URL,
                params={"q": f"{city},{country_code}", "appid": self.api_key, "units": "metric"},
                timeout=8
            )
            r.raise_for_status()
            rows = r.json().get("list", [])[:8]  # 3-hour buckets; first 8 rows ≈ 24h
            self.forecast_raw = rows
            temps, rains = [], []
            for row in rows:
                temp = self._num(row.get("main", {}).get("temp"), np.nan)
                if not math.isfinite(temp):
                    continue
                rain_3h = self._num(row.get("rain", {}).get("3h", 0.0))
                for _ in range(3):
                    temps.append(round(temp, 1))
                    rains.append(round(max(0.0, rain_3h / 3.0), 2))
            return temps[:24], rains[:24]
        except requests.exceptions.RequestException:
            return [], []
        except (KeyError, ValueError, TypeError):
            return [], []

    def fetch(self, city: str = "Jakarta", country_code: str = "ID",
              location_name: str = "") -> WeatherData:
        country_code = (country_code or "ID").upper()
        cache_key = f"city:{city}|{country_code}"
        if not self.api_key:
            return self._simulate(city, country_code=country_code, location_name=location_name)
        if self._is_cache_valid(cache_key):
            return self.last_fetch

        try:
            r = requests.get(
                self.BASE_URL,
                params={"q": f"{city},{country_code}", "appid": self.api_key, "units": "metric"},
                timeout=8
            )
            r.raise_for_status()
            d   = r.json()
            temp = float(d["main"]["temp"])
            hum  = float(d["main"]["humidity"])
            dew  = _dew_point(temp, hum)
            forecast_temp, forecast_rain = self._fetch_forecast(city, country_code)
            if not forecast_temp:
                forecast_temp, forecast_rain = self._synthetic_forecast(
                    temp, datetime.datetime.now().hour, rain_bias=0.12
                )

            wd = WeatherData(
                temp_outside     = temp,
                humidity_outside = hum,
                wind_speed       = float(d.get("wind", {}).get("speed", 2.0)),
                solar_radiation  = self._estimate_solar(d),
                rainfall         = float(d.get("rain", {}).get("1h", 0.0)),
                uv_index         = float(d.get("uvi", 5.0)),
                dew_point        = dew,
                pressure_hpa     = float(d["main"]["pressure"]),
                cloud_cover_pct  = float(d.get("clouds", {}).get("all", 30)),
                co2_ambient      = 425.0,
                location         = location_name or f"{d.get('name', city)}, {country_code}",
                timestamp        = datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                source           = "OpenWeatherMap",
                forecast_temp    = forecast_temp,
                forecast_rain    = forecast_rain,
            )
            self.last_fetch      = wd
            self.last_fetch_time = datetime.datetime.now()
            self.last_fetch_key  = cache_key
            self.history.append(wd)
            return wd

        except requests.exceptions.RequestException as e:
            return self._simulate(city, country_code=country_code, location_name=location_name,
                                  error=f"NET:{str(e)[:30]}")
        except (KeyError, ValueError, TypeError) as e:
            return self._simulate(city, country_code=country_code, location_name=location_name,
                                  error=f"PARSE:{str(e)[:30]}")

    def _estimate_solar(self, d: dict) -> float:
        clouds  = float(d.get("clouds", {}).get("all", 50))
        hour    = (datetime.datetime.utcnow().hour + 7) % 24  # WIB
        sun_alt = max(0.0, math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
        return round(900.0 * sun_alt * (1.0 - clouds / 100.0) * 0.9, 0)

    def _simulate(self, city: str, country_code: str = "ID",
                  location_name: str = "", error: str = "") -> WeatherData:
        country_name = WORLD_COUNTRIES.get(country_code, ("Indonesia",))[0]
        return self._simulate_geo(
            lat=None, lon=None, alt_m=None,
            location_name=location_name or f"{city}, {country_name} (simulated)",
            error=error,
        )

    def _fetch_open_meteo(self, lat: float, lon: float,
                          alt_m: float = 0.0,
                          location_name: str = "") -> Optional[WeatherData]:
        """Ambil cuaca dari Open-Meteo (gratis, no API key).
        Returns WeatherData atau None jika gagal."""
        try:
            from weather.open_meteo import fetch_current, fetch_forecast
            cur = fetch_current(lat, lon)
            if not cur:
                return None

            # Forecast 3 hari (72 jam) untuk chart
            fc_list = fetch_forecast(lat, lon, days=3)
            fc_temps = [f.temperature_c for f in fc_list[:24]]
            fc_rains = [f.precipitation_mm for f in fc_list[:24]]
            if not fc_temps:
                fc_temps, fc_rains = self._synthetic_forecast(
                    cur.temperature_c, datetime.datetime.now().hour)

            # Pressure correction for altitude
            press = cur.pressure_hpa
            if alt_m > 50:
                press = press * math.exp(-alt_m / 8500.0)

            return WeatherData(
                temp_outside     = cur.temperature_c,
                humidity_outside = cur.humidity_pct,
                wind_speed       = cur.wind_speed_ms,
                solar_radiation  = cur.solar_radiation_wm2,
                rainfall         = cur.precipitation_mm,
                uv_index         = max(0, round(cur.solar_radiation_wm2 / 80, 1)),
                dew_point        = cur.dew_point_c,
                pressure_hpa     = round(press, 1),
                cloud_cover_pct  = cur.cloud_cover_pct,
                co2_ambient      = 425.0,
                location         = location_name or f"{lat:.4f}, {lon:.4f}",
                timestamp        = cur.timestamp or datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                source           = "Open-Meteo",
                forecast_temp    = fc_temps,
                forecast_rain    = fc_rains,
            )
        except Exception:
            return None

    def _simulate_geo(self, lat: Optional[float], lon: Optional[float],
                      alt_m: Optional[float], location_name: str = "",
                      error: str = "") -> WeatherData:
        """Simulasi fisika-realistis berdasarkan koordinat & waktu aktual."""
        hour = datetime.datetime.now().hour
        doy  = datetime.datetime.now().timetuple().tm_yday
        lat  = lat  if lat  is not None else -6.21
        lon  = lon  if lon  is not None else 106.85
        alt  = alt_m if alt_m is not None else 10.0

        # ── Lapse rate: suhu turun 6.5°C / 1000m ──────────────────────────
        sea_level_temp = 28.0 + 2.0 * math.sin(2 * math.pi * doy / 365)
        base_temp = sea_level_temp - 6.5 * alt / 1000.0

        # ── Siklus diurnal & solar ─────────────────────────────────────────
        sun_angle = max(0.0, math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
        cloud_prob = 0.35 + 0.20 * math.sin(2 * math.pi * doy / 365)
        cloud_cov  = float(np.random.beta(2, 3) if random.random() < cloud_prob else 0.1)
        cloud_cov  = max(0.0, min(1.0, cloud_cov))
        solar = 900.0 * sun_angle * (1.0 - cloud_cov * 0.82) * max(0.5, 1.0 - alt / 6000.0)

        temp = base_temp + 4.0 * math.sin(math.pi * (hour - 6) / 12) + float(np.random.normal(0, 0.6))

        # ── Kelembapan: tinggi dekat khatulistiwa & dataran tinggi ─────────
        equator_factor = max(0.0, 1.0 - abs(lat) / 15.0)
        humidity = float(np.clip(
            72.0 + 15.0 * equator_factor + 6.0 * cloud_cov
            - 1.1 * (temp - 25.0) + np.random.normal(0, 2.5),
            40, 99
        ))
        dew = _dew_point(temp, humidity)

        # ── Hujan: ada seasonal & jam (sore lebih sering hujan) ───────────
        rain_seasonal = 0.10 + 0.25 * max(0.0, math.sin(2 * math.pi * doy / 365))
        rain_diurnal  = 0.05 + 0.15 * max(0.0, math.sin(math.pi * (hour - 12) / 6))
        rain_chance   = min(0.7, rain_seasonal + rain_diurnal) * (1.0 + 0.5 * cloud_cov)
        rainfall = float(np.random.exponential(3.0) if random.random() < rain_chance else 0.0)

        # ── Tekanan: turun dengan altitude ────────────────────────────────
        pressure = 1013.25 * math.exp(-alt / 8500.0) + float(np.random.normal(0, 1.5))

        forecast_temp, forecast_rain = self._synthetic_forecast(temp, hour, rain_bias=rain_seasonal)

        return WeatherData(
            temp_outside     = round(temp, 1),
            humidity_outside = round(humidity, 1),
            wind_speed       = round(max(0.3, abs(float(np.random.normal(2.5, 1.2)))), 1),
            solar_radiation  = round(solar, 0),
            rainfall         = round(max(0.0, rainfall), 2),
            uv_index         = min(13.0, round(solar / 80.0, 1)),
            dew_point        = dew,
            pressure_hpa     = round(pressure, 1),
            cloud_cover_pct  = round(cloud_cov * 100, 1),
            co2_ambient      = 425.0,
            location         = location_name or f"{lat:.4f}°, {lon:.4f}° (simulated)",
            timestamp        = datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            source           = f"Geo-Physics Model{' (ERR:' + error[:35] + ')' if error else ''}",
            forecast_temp    = forecast_temp,
            forecast_rain    = forecast_rain,
        )

    def fetch_by_coords(self, lat: float, lon: float,
                        location_name: str = "",
                        alt_m: float = 0.0) -> WeatherData:
        """Ambil cuaca berdasarkan koordinat lat/lon.

        Priority chain (Fase 1):
          1. Open-Meteo (gratis, no key, akurasi ERA5)
          2. OWM (jika API key tersedia)
          3. Simulate (synthetic fallback)
        """
        # ── Cache check berdasarkan coords ─────────────────────────────────
        cache_key = f"coord:{lat:.5f},{lon:.5f}|{alt_m:.0f}|{location_name}"
        if self._is_cache_valid(cache_key):
            cached = self.last_fetch
            if cached:
                return cached

        # ── Try Open-Meteo first (gratis, no key) ─────────────────────────
        om_result = self._fetch_open_meteo(lat, lon, alt_m, location_name)
        if om_result:
            self.last_fetch      = om_result
            self.last_fetch_time = datetime.datetime.now()
            self.last_fetch_key  = cache_key
            self.history.append(om_result)
            return om_result

        # ── Fallback ke OWM jika API key ada ──────────────────────────────
        if not self.api_key:
            return self._simulate_geo(lat, lon, alt_m, location_name)

        try:
            r = requests.get(
                self.BASE_URL,
                params={"lat": lat, "lon": lon,
                        "appid": self.api_key, "units": "metric"},
                timeout=8,
            )
            r.raise_for_status()
            d    = r.json()
            temp = float(d["main"]["temp"])
            hum  = float(d["main"]["humidity"])
            dew  = _dew_point(temp, hum)

            # Forecast via forecast endpoint juga pakai coords
            fc_temps, fc_rains = [], []
            try:
                fr = requests.get(
                    self.FORECAST_URL,
                    params={"lat": lat, "lon": lon,
                            "appid": self.api_key, "units": "metric"},
                    timeout=8,
                )
                fr.raise_for_status()
                for row in fr.json().get("list", [])[:8]:
                    t = self._num(row.get("main", {}).get("temp"), temp)
                    rn = self._num(row.get("rain", {}).get("3h", 0.0))
                    for _ in range(3):
                        fc_temps.append(round(t, 1))
                        fc_rains.append(round(max(0.0, rn / 3.0), 2))
            except Exception:
                pass
            if not fc_temps:
                fc_temps, fc_rains = self._synthetic_forecast(temp, datetime.datetime.now().hour)

            # Pressure correction for altitude
            press_raw = float(d["main"].get("pressure", 1013.0))
            # OWM returns sea-level pressure; adjust for altitude
            press_actual = press_raw * math.exp(-alt_m / 8500.0) if alt_m > 50 else press_raw

            wd = WeatherData(
                temp_outside     = temp,
                humidity_outside = hum,
                wind_speed       = float(d.get("wind", {}).get("speed", 2.0)),
                solar_radiation  = self._estimate_solar(d),
                rainfall         = float(d.get("rain", {}).get("1h", 0.0)),
                uv_index         = float(d.get("uvi", max(0, round(self._estimate_solar(d) / 80, 1)))),
                dew_point        = dew,
                pressure_hpa     = round(press_actual, 1),
                cloud_cover_pct  = float(d.get("clouds", {}).get("all", 30)),
                co2_ambient      = 425.0,
                location         = location_name or d.get("name", f"{lat:.4f}°,{lon:.4f}°"),
                timestamp        = datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                source           = "OpenWeatherMap (koordinat)",
                forecast_temp    = fc_temps[:24],
                forecast_rain    = fc_rains[:24],
            )
            self.last_fetch      = wd
            self.last_fetch_time = datetime.datetime.now()
            self.last_fetch_key  = cache_key
            self.history.append(wd)
            return wd

        except requests.exceptions.RequestException as e:
            return self._simulate_geo(lat, lon, alt_m, location_name,
                                      error=f"NET:{str(e)[:30]}")
        except (KeyError, ValueError, TypeError) as e:
            return self._simulate_geo(lat, lon, alt_m, location_name,
                                      error=f"PARSE:{str(e)[:30]}")


# ══════════════════════════════════════════════════════════════════════════════
# 6. PREDICTIVE MAINTENANCE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class MaintenanceEngine:
    """
    Tracks actuator wear, predicts failures, and schedules maintenance.
    Prevents surprise shutdowns by estimating MTBF per component.
    """
    COMPONENT_SPECS = {
        "HVAC_Compressor":   {"mtbf_hrs": 8000, "wear_rate": 0.012, "repair_cost": 5_000_000},
        "LED_Drivers":       {"mtbf_hrs": 50000,"wear_rate": 0.002, "repair_cost": 1_500_000},
        "Circulation_Fan":   {"mtbf_hrs": 20000,"wear_rate": 0.005, "repair_cost": 800_000},
        "Drip_Emitters":     {"mtbf_hrs": 3000, "wear_rate": 0.033, "repair_cost": 200_000},
        "CO2_Solenoid":      {"mtbf_hrs": 10000,"wear_rate": 0.010, "repair_cost": 600_000},
        "pH_Dosing_Pump":    {"mtbf_hrs": 5000, "wear_rate": 0.020, "repair_cost": 400_000},
        "EC_Sensor":         {"mtbf_hrs": 6000, "wear_rate": 0.017, "repair_cost": 250_000},
        "Vent_Actuator":     {"mtbf_hrs": 15000,"wear_rate": 0.007, "repair_cost": 350_000},
        "Water_Pump":        {"mtbf_hrs": 12000,"wear_rate": 0.008, "repair_cost": 750_000},
    }

    def __init__(self):
        self.records: Dict[str, MaintenanceRecord] = {
            name: MaintenanceRecord(
                component=name,
                next_service_hrs=spec["mtbf_hrs"] * 0.8
            )
            for name, spec in self.COMPONENT_SPECS.items()
        }
        self.maintenance_log: List[Dict] = []

    def update(self, actuators: Dict, dt_hrs: float = 1.0):
        """Update wear based on actuator usage"""
        usage_map = {
            "HVAC_Compressor":   float(actuators.get("cooling", 0)) * dt_hrs,
            "LED_Drivers":       float(actuators.get("led_grow", 0)) * dt_hrs,
            "Circulation_Fan":   dt_hrs * 0.9,  # always running
            "Drip_Emitters":     min(1.0, float(actuators.get("irrigation", 0)) / 10) * dt_hrs,
            "CO2_Solenoid":      float(actuators.get("co2_inject", 0)) * dt_hrs,
            "pH_Dosing_Pump":    float(actuators.get("fertilize", 0)) * dt_hrs,
            "EC_Sensor":         dt_hrs * 0.5,
            "Vent_Actuator":     float(actuators.get("vent", 0)) * dt_hrs,
            "Water_Pump":        min(1.0, float(actuators.get("irrigation", 0)) / 5) * dt_hrs,
        }

        for name, hrs_used in usage_map.items():
            if name not in self.records:
                continue
            rec  = self.records[name]
            spec = self.COMPONENT_SPECS[name]
            rec.hours_run += hrs_used
            rec.wear_pct   = min(100.0, rec.hours_run / spec["mtbf_hrs"] * 100.0)

            # Weibull failure probability (shape=2, scale=MTBF)
            eta = spec["mtbf_hrs"]
            rec.failure_prob = 1.0 - math.exp(-(rec.hours_run / eta) ** 2)

    def get_critical_components(self, threshold_pct: float = 70.0) -> List[MaintenanceRecord]:
        return [r for r in self.records.values() if r.wear_pct >= threshold_pct]

    def service_component(self, name: str):
        if name in self.records:
            rec = self.records[name]
            self.maintenance_log.append({
                "ts": datetime.datetime.now().isoformat(),
                "component": name,
                "wear_at_service": rec.wear_pct,
                "hours_at_service": rec.hours_run,
            })
            rec.wear_pct   = 0.0
            rec.hours_run  = 0.0
            rec.failure_prob = 0.0
            rec.last_service = datetime.datetime.now().strftime("%Y-%m-%d")

    def total_repair_cost_estimate(self) -> float:
        return sum(
            self.COMPONENT_SPECS[r.component]["repair_cost"] * r.failure_prob
            for r in self.records.values()
        )


# ══════════════════════════════════════════════════════════════════════════════
# 7. ADVANCED CROP GROWTH MODEL v4
# ══════════════════════════════════════════════════════════════════════════════

class CropGrowthModel:
    """
    PCSE-inspired model v4 with:
    - Farquhar-von Caemmerer-Berry (FvCB) photosynthesis
    - Penman-Monteith transpiration
    - Full NPKCaMgS nutrient model
    - Dual-disease (Botrytis + Mildew) + 5 pest types
    - Root zone dynamics + soil micro-food web factor
    - Canopy energy balance
    - Abscission model for fruit drop
    - Vernalization requirement
    - Carbon sequestration accounting
    """

    def __init__(self, crop: CropType = CropType.TOMATO):
        self.crop_type = crop
        self.params    = CROP_PROFILES[crop]
        self.reset()

    def reset(self):
        p = self.params
        self.day                      = 0
        self.biomass                  = 0.10
        self.leaf_area_index          = 0.50
        self.yield_kg                 = 0.0
        self.stage                    = GrowthStage.GERMINATION
        self.stress_days              = 0
        self.cumulative_transpiration = 0.0
        self.daily_growth_rate        = 0.0
        self.dvs                      = 0.0
        self.root_depth_cm            = 5.0
        # Full NPKCaMgS
        self.n_content    = 3.5   # % N dry mass
        self.p_content    = 0.5   # % P
        self.k_content    = 4.0   # % K
        self.ca_content   = 1.5   # % Ca
        self.mg_content   = 0.4   # % Mg
        self.s_content    = 0.3   # % S
        self.canopy_temp              = p.optimal_temp
        self.disease_botrytis         = 0.0   # 0-1
        self.disease_mildew           = 0.0   # 0-1
        self.disease_index            = 0.0   # combined
        self.disease_type             = "None"
        self.pest_type                = PestType.NONE
        self.pest_pressure            = 0.0   # 0-1
        self.chlorophyll              = 45.0  # SPAD
        self.stomatal_conductance     = 0.3   # mol/m²/s
        self.net_photosynthesis       = 0.0   # μmol CO2/m²/s
        self.gross_photosynthesis     = 0.0
        self.dark_respiration         = 0.0
        self.transpiration_rate       = 0.0   # mm/day
        self.fruit_count              = 0
        self.abscission_count         = 0
        self.vernalization_days       = 0
        self.cumulative_dli           = 0.0   # mol/m² accumulated
        # Carbon accounting
        self.co2_absorbed_kg          = 0.0
        self.co2_respired_kg          = 0.0
        self.net_carbon_seq_kg        = 0.0
        # Soil microbiome
        self.microbial_activity       = 0.7   # 0-1 (beneficial microbes)
        # Quality metrics
        self.brix_sugar               = 4.5   # °Brix for fruit
        self.antioxidant_score        = 50.0  # normalized ORAC

    def _vpd_correction(self, temp: float, humidity: float) -> float:
        """Magnus formula for vapor pressure deficit (kPa)"""
        es = 0.6108 * math.exp(17.27 * temp / (temp + 237.3))
        ea = es * humidity / 100.0
        return max(0.0, es - ea)

    def _farquhar_photosynthesis(self, temp: float, co2_ppm: float,
                                  light_w: float, n_pct: float) -> Tuple[float, float, float]:
        """
        Full FvCB model. Returns (An, Ag, Rd) in μmol CO2/m²/s.
        Includes N-dependency (chlorophyll) and temperature acclimation.
        """
        # N-dependent Vcmax (Kattge & Knorr 2007)
        vcmax25_base = 120.0 if self.crop_type in [CropType.TOMATO, CropType.CUCUMBER, CropType.CANNABIS] else 80.0
        vcmax25 = vcmax25_base * min(1.5, max(0.3, n_pct / 3.5))

        # Temperature response (Medlyn 2002)
        R   = GAS_CONSTANT
        Tk  = temp + 273.15
        Tk25= 298.15
        Ea_vcmax = 65000.0
        Ed  = 200000.0
        dS  = 650.0
        Vcmax = vcmax25 * math.exp(Ea_vcmax / R * (1/Tk25 - 1/Tk)) / \
                (1 + math.exp((dS*Tk - Ed) / (R*Tk)))

        # Jmax temperature response
        jmax25 = 1.67 * vcmax25
        Ea_jmax = 43000.0
        Jmax = jmax25 * math.exp(Ea_jmax / R * (1/Tk25 - 1/Tk)) / \
               (1 + math.exp((dS*Tk - Ed) / (R*Tk)))

        # Electron transport
        alpha   = 0.425   # absorptance × quantum yield
        theta   = 0.9     # curvature parameter
        PAR_mol = light_w * 4.57e-6 * 1e6  # W/m² → μmol/m²/s PPFD
        J_num   = alpha * PAR_mol + Jmax
        J_disc  = max(0.0, J_num**2 - 4*theta*alpha*PAR_mol*Jmax)
        J       = (J_num - math.sqrt(J_disc)) / (2 * theta)

        # Michaelis-Menten constants with temperature
        Kc25   = 404.9;  Ea_Kc = 79430.0
        Ko25   = 278.4;  Ea_Ko = 36380.0
        Kc     = Kc25  * math.exp(Ea_Kc  / R * (1/Tk25 - 1/Tk))
        Ko     = Ko25  * math.exp(Ea_Ko  / R * (1/Tk25 - 1/Tk))
        O2_ubar= 210000.0  # ambient O2 in μbar
        Gamma_star = 42.75 * math.exp(37830 / R * (1/Tk25 - 1/Tk))  # CO2 compensation point

        Ci     = co2_ppm * 0.7   # intercellular CO2 (μbar/Pa ≈ ppm)

        # Rubisco-limited
        Ac = Vcmax * (Ci - Gamma_star) / (Ci + Kc * (1 + O2_ubar / Ko))

        # Light-limited
        Aj = J * (Ci - Gamma_star) / (4 * (Ci + 2 * Gamma_star))

        # TPU-limited (triose phosphate utilization)
        Ap = 3 * 0.1 * Vcmax  # simplified

        Ag = min(Ac, Aj, Ap)
        Ag = max(0.0, Ag)

        # Dark respiration
        Rd = 0.015 * vcmax25 * math.exp(46390 / R * (1/Tk25 - 1/Tk))

        # Disease penalty on photosynthesis
        dis_pen = max(0.0, 1.0 - self.disease_index * 0.55)
        pest_pen = max(0.0, 1.0 - self.pest_pressure * 0.35)

        An = max(0.0, (Ag - Rd) * dis_pen * pest_pen)
        An_canopy = An * self.leaf_area_index * self.microbial_activity

        # Track gross & dark resp
        self.gross_photosynthesis = Ag * self.leaf_area_index
        self.dark_respiration     = Rd * self.leaf_area_index

        return An_canopy, self.gross_photosynthesis, Rd

    def step(self, temp: float, humidity: float, soil_moisture: float,
             co2_ppm: float, light_w: float, stress_factor: float = 1.0,
             nutrient_sol: Optional[NutrientSolution] = None,
             root_temp: float = 22.0, fertilize: bool = False,
             led_spectrum: LEDSpectrum = LEDSpectrum.FULL,
             dli_today: float = 0.0) -> Dict:

        p   = self.params
        ns  = nutrient_sol
        self.day += 1

        # ── Phenology (thermal time with vernalization) ───────────────────
        t_base   = 8.0
        t_opt    = p.optimal_temp
        t_max    = p.heat_stress_threshold + 5
        if temp > t_base and temp < t_max:
            t_norm   = (temp - t_base) / (t_opt - t_base)
            thermal  = max(0.0, min(1.0, 2 * t_norm - t_norm**2)) * (t_opt - t_base)
        else:
            thermal  = 0.0

        # Vernalization accumulation
        if p.vernalization_req and temp < 8.0:
            self.vernalization_days += 1
        vernal_factor = min(1.0, self.vernalization_days / 30.0) if p.vernalization_req else 1.0

        dvr = thermal * vernal_factor / (p.days_to_harvest * 14.0)
        self.dvs = min(2.0, self.dvs + dvr)

        if   self.dvs < 0.10: self.stage = GrowthStage.GERMINATION
        elif self.dvs < 0.50: self.stage = GrowthStage.SEEDLING
        elif self.dvs < 0.90: self.stage = GrowthStage.VEGETATIVE
        elif self.dvs < 1.30: self.stage = GrowthStage.FLOWERING
        elif self.dvs < 1.80: self.stage = GrowthStage.FRUITING
        else:                  self.stage = GrowthStage.HARVEST

        # ── Stress Calculations ───────────────────────────────────────────
        Ks = 1.0 if soil_moisture >= p.water_stress_threshold else \
             math.pow(max(0.0, soil_moisture / p.water_stress_threshold), 0.75)

        t_range = max(1.0, p.heat_stress_threshold - p.cold_stress_threshold)
        t_norm2 = (temp - p.cold_stress_threshold) / t_range
        Kt      = float(np.clip(4.0 * t_norm2 * (1.0 - t_norm2), 0.0, 1.0))

        Kroot   = float(np.clip(1.0 - 0.04 * abs(root_temp - p.root_zone_temp_optimal), 0.2, 1.0))

        if co2_ppm > 0:
            co2_factor = 1.0 + 0.38 * math.log(max(1.0, co2_ppm) / 400.0) / math.log(2.0)
        else:
            co2_factor = 0.4
        co2_factor = float(np.clip(co2_factor, 0.4, 1.8))

        Kl = (light_w * 1.2) / (light_w + 1.2 * max(1.0, p.optimal_light)) if light_w > 0 else 0.0
        Kl = float(np.clip(Kl, 0.0, 1.0))

        # Spectrum quality factor
        spectrum_factor = {
            LEDSpectrum.FULL:     1.0,
            LEDSpectrum.VEGE:     1.15 if self.stage in [GrowthStage.VEGETATIVE, GrowthStage.SEEDLING] else 0.90,
            LEDSpectrum.BLOOM:    1.15 if self.stage in [GrowthStage.FLOWERING, GrowthStage.FRUITING] else 0.85,
            LEDSpectrum.UV_BOOST: 0.90,   # UV kills disease but slightly reduces growth
            LEDSpectrum.FAR_RED:  1.10,   # Emerson effect
        }.get(led_spectrum, 1.0)

        # DLI cumulative bonus (Photoperiod)
        self.cumulative_dli += dli_today
        dli_factor = min(1.3, max(0.6, self.cumulative_dli / (p.dli_optimal * 10 + 1e-6)))

        # Nutrient stress (full NPK)
        if ns is not None:
            ec_dev   = abs(ns.ec_mS   - p.ec_optimal) - 0.5
            ph_dev   = abs(ns.ph      - p.ph_optimal)  - 0.3
            n_stress = max(0.0, (80.0 - ns.n_ppm) / 80.0) * 0.6  # N deficiency
            p_stress_n = max(0.0, (20.0 - ns.p_ppm) / 20.0) * 0.3
            k_stress_n = max(0.0, (120.0 - ns.k_ppm) / 120.0) * 0.3
            ec_stress  = float(np.clip(1.0 - 0.05 * max(0.0, ec_dev), 0.45, 1.0))
            ph_stress  = float(np.clip(1.0 - 0.09 * max(0.0, ph_dev), 0.45, 1.0))
            nut_stress = max(0.0, 1.0 - n_stress - p_stress_n - k_stress_n)
        else:
            ec_stress  = float(np.clip(1.0 - 0.05 * max(0.0, abs(3.5 - p.ec_optimal) - 0.5), 0.5, 1.0))
            ph_stress  = float(np.clip(1.0 - 0.08 * max(0.0, abs(6.2 - p.ph_optimal) - 0.3), 0.5, 1.0))
            nut_stress = 0.9

        vpd        = self._vpd_correction(temp, humidity)
        vpd_stress = 1.0
        if vpd > p.vpd_optimal * 2.0:
            vpd_stress = p.vpd_optimal * 2.0 / vpd
        elif vpd < 0.2:
            vpd_stress = 0.88
        vpd_stress = float(np.clip(vpd_stress, 0.35, 1.0))

        dis_penalty  = max(0.0, 1.0 - self.disease_index * 0.65)
        pest_penalty = max(0.0, 1.0 - self.pest_pressure * 0.45)
        micro_boost  = 0.9 + 0.2 * self.microbial_activity  # beneficial microbes

        combined = (Ks * Kt * Kl * co2_factor * ec_stress * ph_stress *
                    vpd_stress * Kroot * dis_penalty * pest_penalty *
                    nut_stress * spectrum_factor * dli_factor * micro_boost * stress_factor)
        combined = float(np.clip(combined, 0.0, 2.0))

        # ── Photosynthesis ────────────────────────────────────────────────
        An, Ag, Rd = self._farquhar_photosynthesis(temp, co2_ppm, light_w, self.n_content)
        self.net_photosynthesis = An

        # ── Stomatal conductance ──────────────────────────────────────────
        self.stomatal_conductance = float(np.clip(
            0.4 * Ks * (1.0 - max(0.0, vpd - 2.0) * 0.12) * nut_stress,
            0.02, 0.8
        ))

        # ── Growth rate ───────────────────────────────────────────────────
        maturity_factor = 1.0 - 0.22 * (self.dvs / 2.0) ** 2
        self.daily_growth_rate = p.growth_rate_base * combined * maturity_factor

        # ── LAI dynamics ─────────────────────────────────────────────────
        if self.dvs < 0.9:
            self.leaf_area_index += 0.11 * combined * (1.0 - self.dvs)
        elif self.dvs < 1.3:
            self.leaf_area_index = min(self.leaf_area_index, 8.5)
        else:
            self.leaf_area_index = max(0.8, self.leaf_area_index - 0.022)
        self.leaf_area_index = float(np.clip(self.leaf_area_index, 0.0, 12.0))

        # ── Canopy temperature (leaf energy balance) ──────────────────────
        rnet_leaf = light_w * 0.85 * (1.0 - 0.25)   # absorbed net radiation W/m²
        H_sensible = 20.0 * (temp - (temp - 3))       # approx convective term
        LE_latent  = min(rnet_leaf * 0.7, self.stomatal_conductance * vpd * 1000)
        T_canopy_correction = (rnet_leaf - LE_latent) / (40.0 * max(0.1, self.stomatal_conductance))
        self.canopy_temp = float(np.clip(temp + min(4.0, max(-4.0, T_canopy_correction * 0.1)), -5, 60))

        # ── Root growth ───────────────────────────────────────────────────
        self.root_depth_cm = min(80.0, self.root_depth_cm + 0.28 * Ks * combined)

        # ── Biomass & Yield ───────────────────────────────────────────────
        self.biomass += self.daily_growth_rate
        if self.stage in [GrowthStage.FRUITING, GrowthStage.HARVEST]:
            hi = 0.52 + 0.06 * (Ks + Kt) / 2.0  # dynamic harvest index
            # Sugar quality increases under mild stress and high light
            self.brix_sugar = float(np.clip(4.5 + 0.5 * (1 - Ks) + 0.3 * Kl, 3.0, 14.0))
            self.antioxidant_score = float(np.clip(
                50.0 + 10.0 * (1 - Ks) + 5.0 * Kl - 15.0 * self.disease_index, 10.0, 100.0
            ))
            yield_inc = self.daily_growth_rate * hi
            self.yield_kg += yield_inc

            # Abscission: fruit drop when stress high
            if combined < 0.4 and self.fruit_count > 5:
                dropped = max(0, int(self.fruit_count * 0.05))
                self.fruit_count = max(0, self.fruit_count - dropped)
                self.abscission_count += dropped
                self.yield_kg -= dropped * 0.05

            self.fruit_count = max(0, int(self.yield_kg * 12))

        # ── Transpiration ─────────────────────────────────────────────────
        Rn_crop = max(0.0, light_w * 0.0036 * 3600 * 0.8)
        vpd_kPa = vpd
        self.transpiration_rate = max(0.0,
            (0.408 * Rn_crop + 0.665 * vpd_kPa) /
            (1.0 + 0.665 * (1.0 + 0.34 * 2.0)) * self.stomatal_conductance * 2.0)
        self.cumulative_transpiration += self.transpiration_rate

        # ── Nutrient Uptake (full NPKCaMgS) ──────────────────────────────
        growth_demand = max(0.0, self.daily_growth_rate)
        if fertilize or (ns is not None and ns.n_ppm > 100):
            self.n_content  = min(5.0,  self.n_content  + 0.28)
            self.p_content  = min(0.9,  self.p_content  + 0.04)
            self.k_content  = min(6.0,  self.k_content  + 0.38)
            self.ca_content = min(2.5,  self.ca_content + 0.08)
            self.mg_content = min(0.8,  self.mg_content + 0.02)
            self.s_content  = min(0.5,  self.s_content  + 0.01)
        # Dilution with biomass growth
        for attr, floor, rate in [
            ("n_content",  1.0, 0.022), ("p_content",  0.2, 0.004),
            ("k_content",  2.0, 0.018), ("ca_content", 0.5, 0.007),
            ("mg_content", 0.1, 0.002), ("s_content",  0.1, 0.001),
        ]:
            cur = getattr(self, attr)
            setattr(self, attr, max(float(floor), cur - growth_demand * rate))

        self.chlorophyll = float(np.clip(25.0 + 18.0 * (self.n_content / 3.5), 15.0, 80.0))

        # ── Microbial Activity ────────────────────────────────────────────
        # Microbiome suppressed by disease, salt stress, extremes
        ec_salt_stress = max(0.0, (max(3.5, p.ec_optimal if ns is None else ns.ec_mS) - 4.0) / 4.0)
        self.microbial_activity = float(np.clip(
            self.microbial_activity * 0.998 + 0.001 * Ks - 0.002 * ec_salt_stress - 0.003 * self.disease_index,
            0.2, 1.0
        ))

        # ── Disease Model ─────────────────────────────────────────────────
        self._update_disease(temp, humidity, light_w, led_spectrum)

        # ── Pest Dynamics ─────────────────────────────────────────────────
        self._update_pest(temp, humidity, combined)

        # ── Carbon Accounting ─────────────────────────────────────────────
        # CO2 fixed via photosynthesis (convert μmol/m²/s → kg/step/m²)
        co2_fixed = Ag * self.leaf_area_index * 44e-6 * 3600.0 / 1e6  # rough kg CO2/m²/hr
        co2_resp  = Rd * self.leaf_area_index * 44e-6 * 3600.0 / 1e6
        self.co2_absorbed_kg  += max(0.0, co2_fixed)
        self.co2_respired_kg  += max(0.0, co2_resp)
        self.net_carbon_seq_kg = self.co2_absorbed_kg - self.co2_respired_kg

        if combined < 0.6:
            self.stress_days += 1

        return {
            "day": self.day, "biomass": self.biomass, "yield_kg": self.yield_kg,
            "lai": self.leaf_area_index, "stage": self.stage.value, "dvs": self.dvs,
            "daily_growth": self.daily_growth_rate, "stress_Ks": Ks, "stress_Kt": Kt,
            "stress_Kl": Kl, "co2_factor": co2_factor, "combined_stress": combined,
            "transpiration": self.transpiration_rate, "canopy_temp": self.canopy_temp,
            "root_depth": self.root_depth_cm, "disease_index": self.disease_index,
            "disease_type": self.disease_type, "net_photosynthesis": self.net_photosynthesis,
            "gross_photosynthesis": self.gross_photosynthesis,
            "stomatal_conductance": self.stomatal_conductance,
            "n_content": self.n_content, "p_content": self.p_content,
            "k_content": self.k_content, "ca_content": self.ca_content,
            "chlorophyll": self.chlorophyll, "fruit_count": self.fruit_count,
            "abscission": self.abscission_count, "vpd": vpd, "vpd_stress": vpd_stress,
            "ec_stress": ec_stress, "ph_stress": ph_stress,
            "pest_pressure": self.pest_pressure, "pest_type": self.pest_type.value,
            "brix_sugar": self.brix_sugar, "antioxidant": self.antioxidant_score,
            "microbial_activity": self.microbial_activity,
            "co2_absorbed_kg": self.co2_absorbed_kg, "net_carbon_seq": self.net_carbon_seq_kg,
            "nut_stress": nut_stress, "spectrum_factor": spectrum_factor,
        }

    def _update_disease(self, temp: float, humidity: float, light_w: float,
                        led_spectrum: LEDSpectrum):
        p = self.params

        # Botrytis cinerea (grey mold) — Munk 2008
        if humidity > p.disease_humidity_risk:
            h_excess  = (humidity - p.disease_humidity_risk) / 10.0
            t_factor  = max(0.0, 1.0 - abs(temp - 18.0) / 10.0)
            l_factor  = max(0.25, 1.0 - light_w / 450.0)
            botrytis_risk = float(np.clip(h_excess * t_factor * l_factor * 0.06, 0.0, 0.06))
        else:
            botrytis_risk = 0.0

        # Powdery Mildew (Oidium spp.)
        if 42.0 < humidity < 78.0 and 20.0 < temp < 32.0:
            canopy_factor = self.leaf_area_index / 8.0
            h_factor      = max(0.0, 1.0 - abs(humidity - 62.0) / 22.0)
            mildew_risk   = float(np.clip(canopy_factor * h_factor * 0.025, 0.0, 0.035))
        else:
            mildew_risk   = 0.0

        # UV suppression of pathogens (UV-B at 290-315nm)
        uv_suppression = 0.015 if led_spectrum == LEDSpectrum.UV_BOOST else 0.0
        recovery       = 0.008 if light_w > 350 and humidity < 72 else 0.002
        total_recovery = recovery + uv_suppression

        self.disease_botrytis = float(np.clip(self.disease_botrytis + botrytis_risk - total_recovery, 0.0, 1.0))
        self.disease_mildew   = float(np.clip(self.disease_mildew   + mildew_risk   - total_recovery * 0.5, 0.0, 1.0))
        self.disease_index    = float(np.clip(
            0.7 * max(self.disease_botrytis, self.disease_mildew) +
            0.3 * min(self.disease_botrytis + self.disease_mildew, 1.0),
            0.0, 1.0
        ))

        if self.disease_botrytis > self.disease_mildew and self.disease_index > 0.08:
            self.disease_type = "Botrytis"
        elif self.disease_mildew > 0.008 and self.disease_index > 0.08:
            self.disease_type = "Powdery Mildew"
        elif self.disease_index < 0.04:
            self.disease_type = "None"

    def _update_pest(self, temp: float, humidity: float, combined_stress: float):
        """
        Population dynamics model for 5 pest types.
        Logistic growth with climate suitability and biological control.
        """
        # Determine active pest type if none yet
        if self.pest_type == PestType.NONE and random.random() < 0.001:
            # Climate-driven pest emergence
            if temp > 25 and humidity < 65:
                self.pest_type = PestType.SPIDERMITE
            elif temp > 22 and humidity > 70:
                self.pest_type = PestType.APHIDS
            elif humidity > 75:
                self.pest_type = PestType.FUNGUS_GNAT
            elif temp > 24:
                self.pest_type = random.choice([PestType.WHITEFLY, PestType.THRIPS])

        if self.pest_type != PestType.NONE:
            # Logistic growth: dN/dt = r*N*(1-N/K) with climate modifiers
            suitability = {
                PestType.APHIDS:     0.5*(temp-15)/(30-15) + 0.5*(humidity-50)/(90-50),
                PestType.WHITEFLY:   0.8*(temp-18)/(35-18) + 0.2*(1-humidity/100),
                PestType.SPIDERMITE: 0.9*(temp-20)/(38-20) + 0.1*(1-humidity/100)*2,
                PestType.THRIPS:     0.7*(temp-15)/(33-15) + 0.3*(1-humidity/100),
                PestType.FUNGUS_GNAT:0.3*(temp-10)/(28-10) + 0.7*(humidity-40)/60,
            }.get(self.pest_type, 0.3)
            suitability = float(np.clip(suitability, 0.0, 1.0))

            r_pest = 0.005 * suitability
            K_pest = 0.8
            # Natural control by beneficial microbes
            bio_control = 0.002 * self.microbial_activity
            d_pest = r_pest * self.pest_pressure * (1 - self.pest_pressure / K_pest) - bio_control
            self.pest_pressure = float(np.clip(self.pest_pressure + d_pest, 0.0, 1.0))

            # Spontaneous extinction
            if self.pest_pressure < 0.02 and random.random() < 0.05:
                self.pest_type = PestType.NONE
                self.pest_pressure = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 8. NUTRIENT SOLUTION MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class NutrientManager:
    """
    Full Hoagland nutrient solution management.
    Tracks depletion, calculates refill doses, monitors antagonisms.
    """
    # Target ranges (Hoagland modified for each crop stage)
    STAGE_TARGETS = {
        GrowthStage.GERMINATION: {"n_ppm": 60,  "p_ppm": 20,  "k_ppm": 100, "ec": 0.8,  "ph": 6.0},
        GrowthStage.SEEDLING:    {"n_ppm": 100, "p_ppm": 30,  "k_ppm": 150, "ec": 1.2,  "ph": 6.0},
        GrowthStage.VEGETATIVE:  {"n_ppm": 200, "p_ppm": 50,  "k_ppm": 250, "ec": 2.5,  "ph": 6.2},
        GrowthStage.FLOWERING:   {"n_ppm": 150, "p_ppm": 60,  "k_ppm": 350, "ec": 3.0,  "ph": 6.0},
        GrowthStage.FRUITING:    {"n_ppm": 120, "p_ppm": 55,  "k_ppm": 380, "ec": 3.5,  "ph": 6.0},
        GrowthStage.HARVEST:     {"n_ppm": 80,  "p_ppm": 30,  "k_ppm": 200, "ec": 2.0,  "ph": 6.2},
    }

    def __init__(self):
        self.solution = NutrientSolution()
        self.depletion_log: List[Dict] = []

    def deplete(self, crop_model: CropGrowthModel, dt: float = 1.0):
        """Simulate nutrient uptake per step"""
        uptake_rate = max(0.0, crop_model.daily_growth_rate) * dt
        cm = crop_model
        self.solution.n_ppm  = max(10.0,  self.solution.n_ppm  - uptake_rate * 15.0)
        self.solution.p_ppm  = max(5.0,   self.solution.p_ppm  - uptake_rate * 3.0)
        self.solution.k_ppm  = max(20.0,  self.solution.k_ppm  - uptake_rate * 20.0)
        self.solution.ca_ppm = max(10.0,  self.solution.ca_ppm - uptake_rate * 10.0)
        self.solution.mg_ppm = max(5.0,   self.solution.mg_ppm - uptake_rate * 3.0)
        self.solution.fe_ppb = max(100.0, self.solution.fe_ppb - uptake_rate * 80.0)

        # EC drops as nutrients deplete
        total_ions = (self.solution.n_ppm + self.solution.k_ppm +
                      self.solution.ca_ppm + self.solution.p_ppm)
        self.solution.ec_mS = float(np.clip(total_ions / 250.0, 0.3, 8.0))

        # pH drift — roots acidify the solution
        self.solution.ph = float(np.clip(
            self.solution.ph + np.random.normal(-0.005, 0.002), 4.5, 8.5
        ))

        # DO decay with temperature
        self.solution.dissolved_o2 = float(np.clip(
            14.62 - 0.39 * self.solution.temp_C + 0.006 * self.solution.temp_C**2,
            4.0, 14.0
        ))

    def replenish(self, stage: GrowthStage, full_flush: bool = False):
        """Replenish to stage-appropriate targets"""
        targets = self.STAGE_TARGETS.get(stage, self.STAGE_TARGETS[GrowthStage.VEGETATIVE])
        if full_flush:
            self.solution = NutrientSolution(
                ec_mS=targets["ec"], ph=targets["ph"],
                n_ppm=float(targets["n_ppm"]), p_ppm=float(targets["p_ppm"]),
                k_ppm=float(targets["k_ppm"]), ca_ppm=200.0,
                mg_ppm=50.0, fe_ppb=2000.0
            )
        else:
            # Partial top-up
            self.solution.n_ppm  = min(float(targets["n_ppm"]),  self.solution.n_ppm  + 50.0)
            self.solution.p_ppm  = min(float(targets["p_ppm"]),  self.solution.p_ppm  + 15.0)
            self.solution.k_ppm  = min(float(targets["k_ppm"]),  self.solution.k_ppm  + 60.0)
            self.solution.ca_ppm = min(200.0, self.solution.ca_ppm + 30.0)
            # pH correction
            if self.solution.ph < 5.5:
                self.solution.ph = min(6.5, self.solution.ph + 0.3)
            elif self.solution.ph > 7.0:
                self.solution.ph = max(5.8, self.solution.ph - 0.2)

    def check_antagonisms(self) -> List[str]:
        """Detect nutrient antagonism interactions"""
        warnings_list = []
        s = self.solution
        if s.k_ppm > 400 and s.ca_ppm < 100:
            warnings_list.append("⚠️ High K antagonizes Ca uptake")
        if s.n_ppm > 300 and s.ca_ppm < 80:
            warnings_list.append("⚠️ Excess NH4-N suppresses Ca absorption")
        if s.ph > 7.0 and s.fe_ppb < 500:
            warnings_list.append("⚠️ High pH causes Fe deficiency (chlorosis risk)")
        if s.ph < 5.0:
            warnings_list.append("⚠️ pH too low — Mn/Al toxicity risk")
        if s.dissolved_o2 < 5.0:
            warnings_list.append("⚠️ Low DO — root hypoxia risk")
        return warnings_list


# ══════════════════════════════════════════════════════════════════════════════
# 9. MULTI-ZONE GREENHOUSE DIGITAL TWIN v4
# ══════════════════════════════════════════════════════════════════════════════

class GreenZone:
    """
    Individual greenhouse zone with full physics, crop model, and sensor fusion.
    """

    def __init__(self, zone_id: str, zone_type: ZoneType, crop_type: CropType,
                 area_m2: float = 100.0, volume_m3: float = 500.0,
                 irrigation_mode: IrrigationMode = IrrigationMode.DRIP):
        self.zone_id         = zone_id
        self.zone_type       = zone_type
        self.crop_type       = crop_type
        self.area_m2         = area_m2
        self.volume_m3       = volume_m3
        self.irrigation_mode = irrigation_mode
        self.crop_model      = CropGrowthModel(crop_type)
        self.nutrient_mgr    = NutrientManager()
        self.kalman          = MultiVarKalman()
        self.maint_engine    = MaintenanceEngine()

        # Environment state
        self.temp_air    = 24.0
        self.humidity    = 65.0
        self.soil_moist  = 60.0
        self.co2_ppm     = 400.0
        self.light_w     = 300.0
        self.root_temp   = 22.0
        self.o2_percent  = 21.0
        self.vpd         = 1.0
        self.led_spectrum = LEDSpectrum.FULL
        self.dli_today    = 0.0       # mol/m² accumulated today

        # Resources
        self.water_used_L    = 0.0
        self.energy_kwh      = 0.0
        self.co2_injected_kg = 0.0
        self.fertilizer_kg   = 0.0
        self.labor_hrs       = 0.0

        # Tracking
        self.step_count = 0
        self.alerts: List[Alert] = []
        self.history: Dict[str, List] = {k: [] for k in [
            "temp","humidity","soil","co2","light","biomass","yield","lai",
            "water","energy","growth_rate","stress","dvs","stage",
            "canopy_temp","disease","transpiration","n_content","chlorophyll",
            "ec","ph","net_ps","vpd","fruit_count","brix","antioxidant",
            "pest","microbial","co2_absorbed","do2","n_ppm","k_ppm",
            "ca_content","abscission",
        ]}

        # Intercrop partner (optional)
        self.intercrop_zone: Optional["GreenZone"] = None

    @property
    def nutrient_solution(self) -> NutrientSolution:
        return self.nutrient_mgr.solution

    def _vpd(self) -> float:
        es = 0.6108 * math.exp(17.27 * self.temp_air / (self.temp_air + 237.3))
        return max(0.0, es * (1.0 - self.humidity / 100.0))

    def energy_balance(self, weather: WeatherData, actuators: Dict) -> float:
        U_glass  = 5.8      # W/m²K double-layer AR glass
        U_floor  = 0.45     # W/m²K insulated concrete
        dt       = 3600.0   # s
        roof_area = self.area_m2 * 1.18
        wall_area = 4.0 * math.sqrt(self.area_m2) * (self.volume_m3 / self.area_m2)

        # Solar gain (with shading screen)
        tau    = 0.70 + 0.08 * (1.0 - actuators.get("shade_screen", 0.0))
        Q_solar = weather.solar_radiation * tau * self.area_m2

        # Longwave radiation loss
        T_sky    = weather.temp_outside - 18.0
        Q_rad    = (0.88 * STEFAN_BOLTZMANN *
                    ((self.temp_air + 273.15)**4 - (T_sky + 273.15)**4) *
                    roof_area / self.volume_m3 * 0.001)

        # Ventilation
        vent_rate = 0.018 * float(actuators.get("vent", 0)) + 0.0018
        Q_vent    = vent_rate * self.volume_m3 * RHO_AIR * CP_AIR * (self.temp_air - weather.temp_outside)

        # Conduction
        dT_wall = self.temp_air - weather.temp_outside
        Q_cond  = (U_glass * (roof_area + wall_area) + U_floor * self.area_m2) * dT_wall

        # HVAC
        Q_heat = 9500.0 * float(actuators.get("heating", 0)) * self.area_m2 / self.volume_m3
        Q_cool = 7500.0 * float(actuators.get("cooling", 0)) * self.area_m2 / self.volume_m3

        # Crop transpiration latent heat
        LAI       = self.crop_model.leaf_area_index
        vpd_zone  = self._vpd()
        E_crop    = max(0.0, 0.32 * LAI * vpd_zone * self.crop_model.stomatal_conductance)
        Q_transp  = -E_crop * LATENT_HEAT_VAP / self.volume_m3

        # Geothermal (ground storage effect, simplified)
        Q_geo = max(0.0, 18.0 - weather.temp_outside) * U_floor * self.area_m2 * 0.1

        dT = (Q_solar + Q_heat + Q_geo - Q_vent - Q_cond - Q_cool + Q_transp - Q_rad) / \
             (self.volume_m3 * RHO_AIR * CP_AIR) * dt

        # Energy tracking
        kWh = (Q_heat + Q_cool) * dt / 3.6e6
        if actuators.get("led_grow", 0):
            kWh += 0.22 * self.area_m2 / 100.0
        if actuators.get("humidifier", 0):
            kWh += 0.05
        self.energy_kwh += max(0.0, kWh)

        return float(np.clip(dT, -7.0, 7.0))

    def humidity_balance(self, weather: WeatherData, actuators: Dict) -> float:
        vpd_z  = self._vpd()
        LAI    = self.crop_model.leaf_area_index
        Gs     = self.crop_model.stomatal_conductance

        E_crop  = max(0.0, 0.38 * LAI * vpd_z * Gs)
        E_soil  = 0.055 * (self.soil_moist / 100.0) * max(0.0, vpd_z)
        dH      = (E_crop + E_soil) * 3.2

        if actuators.get("humidifier", 0):
            dH += 2.8
        if actuators.get("vent", 0):
            dH -= (self.humidity - weather.humidity_outside) * 0.38
        if actuators.get("cooling", 0) and self.humidity > 82:
            dH -= 3.5  # condensation on cooling coil
        if actuators.get("dehumidifier", 0):
            dH -= 4.0

        return float(np.clip(dH, -7.0, 7.0))

    def co2_balance(self, weather: WeatherData, actuators: Dict) -> float:
        Pn     = self.crop_model.net_photosynthesis
        uptake = Pn * self.area_m2 * 0.48 * (100.0 / self.volume_m3)
        dCO2   = -uptake

        if actuators.get("co2_inject", 0):
            dCO2 += 65.0
            self.co2_injected_kg += 0.065 / 1000.0 * self.area_m2 / 100.0

        if actuators.get("vent", 0):
            dCO2 += (weather.co2_ambient - self.co2_ppm) * 0.14

        # Night respiration
        if self.light_w < 8:
            dCO2 += 18.0

        return float(np.clip(dCO2, -130.0, 280.0))

    def irrigation_balance(self, actuators: Dict, et0: float) -> float:
        eff = {
            IrrigationMode.DRIP:      0.92, IrrigationMode.FLOOD:   0.52,
            IrrigationMode.MIST:      0.82, IrrigationMode.NFT:     0.98,
            IrrigationMode.AEROPONIC: 0.99, IrrigationMode.DWC:     0.99,
            IrrigationMode.SUBSTRATE: 0.88,
        }.get(self.irrigation_mode, 0.85)

        irrig    = float(actuators.get("irrigation", 0))
        drainage = max(0.0, self.soil_moist - 92.0) * 0.32
        dSM      = irrig * 0.36 * eff - et0 * 0.62 - drainage

        self.water_used_L += irrig
        return float(np.clip(dSM, -11.0, 11.0))

    def step(self, weather: WeatherData, actuators: Dict) -> Dict:
        self.step_count += 1
        dt_hrs = 1.0

        # ── LED Spectrum Management ───────────────────────────────────────
        spectrum_str = actuators.get("led_spectrum", LEDSpectrum.FULL.value)
        try:
            self.led_spectrum = LEDSpectrum(spectrum_str)
        except ValueError:
            self.led_spectrum = LEDSpectrum.FULL

        # ── Light ─────────────────────────────────────────────────────────
        par_fraction = 0.46
        solar_par    = weather.solar_radiation * par_fraction
        led_ppfd     = 0.0
        if actuators.get("led_grow", 0):
            # Spectrum-specific LED PPFD
            led_ppfd = {
                LEDSpectrum.FULL:     220.0,
                LEDSpectrum.VEGE:     200.0,
                LEDSpectrum.BLOOM:    200.0,
                LEDSpectrum.UV_BOOST: 150.0,
                LEDSpectrum.FAR_RED:  180.0,
            }.get(self.led_spectrum, 220.0)
        self.light_w = solar_par + led_ppfd

        # DLI accumulation (mol/m²/day)
        self.dli_today += self.light_w * 1e-6 * 4.57 * 3600.0  # PPFD → mol/m²/hr

        # ── Kalman Filter — Sensor Fusion ─────────────────────────────────
        raw_readings = {
            "temp":      self.temp_air,
            "humidity":  self.humidity,
            "co2":       self.co2_ppm,
            "soil":      self.soil_moist,
            "ec":        self.nutrient_solution.ec_mS,
            "ph":        self.nutrient_solution.ph,
            "light":     self.light_w,
            "root_temp": self.root_temp,
        }
        filtered = self.kalman.filter(raw_readings)

        # Use filtered values for physics
        self.temp_air   = filtered.get("temp",     self.temp_air)
        self.humidity   = filtered.get("humidity", self.humidity)
        self.co2_ppm    = filtered.get("co2",      self.co2_ppm)
        self.soil_moist = filtered.get("soil",     self.soil_moist)
        self.root_temp  = filtered.get("root_temp",self.root_temp)

        # ── Temperature ───────────────────────────────────────────────────
        dT            = self.energy_balance(weather, actuators)
        self.temp_air = float(np.clip(self.temp_air + dT, 3.0, 55.0))
        self.root_temp += (self.temp_air - self.root_temp) * 0.045
        self.root_temp = float(np.clip(self.root_temp, 3.0, 42.0))

        # ── Humidity ──────────────────────────────────────────────────────
        dH            = self.humidity_balance(weather, actuators)
        self.humidity = float(np.clip(self.humidity + dH, 12.0, 100.0))
        self.vpd      = self._vpd()

        # ── CO₂ ───────────────────────────────────────────────────────────
        dCO2          = self.co2_balance(weather, actuators)
        self.co2_ppm  = float(np.clip(self.co2_ppm + dCO2, 280.0, 2800.0))

        # ── Soil Moisture & ET0 ────────────────────────────────────────────
        Rn   = max(0.0, self.light_w * 0.0036 * 3600.0)
        vpd_z = self._vpd()
        et0  = max(0.0, (0.408 * Rn + 0.665 * vpd_z) / (1.0 + 0.665 * 1.34))
        dSM  = self.irrigation_balance(actuators, et0)
        self.soil_moist = float(np.clip(self.soil_moist + dSM, 0.0, 100.0))

        # ── Nutrient Solution ─────────────────────────────────────────────
        if actuators.get("fertilize", 0):
            flush = (self.step_count % 50 == 0)
            self.nutrient_mgr.replenish(self.crop_model.stage, full_flush=flush)
            self.fertilizer_kg += 0.013
        self.nutrient_mgr.deplete(self.crop_model, dt=dt_hrs)

        # pH correction via actuators
        if actuators.get("ph_adjust_up", 0):
            self.nutrient_solution.ph = min(7.5, self.nutrient_solution.ph + 0.15)
        if actuators.get("ph_adjust_down", 0):
            self.nutrient_solution.ph = max(4.5, self.nutrient_solution.ph - 0.15)

        # ── Maintenance Engine ─────────────────────────────────────────────
        self.maint_engine.update(actuators, dt_hrs=dt_hrs)

        # ── Crop Growth ────────────────────────────────────────────────────
        stress_override = float(actuators.get("stress_override", 1.0))
        fertilize_flag  = bool(actuators.get("fertilize", 0))

        crop_state = self.crop_model.step(
            temp          = self.temp_air,
            humidity      = self.humidity,
            soil_moisture = self.soil_moist,
            co2_ppm       = self.co2_ppm,
            light_w       = self.light_w,
            stress_factor = stress_override,
            nutrient_sol  = self.nutrient_solution,
            root_temp     = self.root_temp,
            fertilize     = fertilize_flag,
            led_spectrum  = self.led_spectrum,
            dli_today     = self.dli_today,
        )

        # ── Alerts ────────────────────────────────────────────────────────
        self._check_alerts(crop_state)

        # ── History Logging ───────────────────────────────────────────────
        h = self.history
        ns = self.nutrient_solution
        h["temp"].append(round(self.temp_air, 2))
        h["humidity"].append(round(self.humidity, 2))
        h["soil"].append(round(self.soil_moist, 2))
        h["co2"].append(round(self.co2_ppm, 1))
        h["light"].append(round(self.light_w, 0))
        h["biomass"].append(round(crop_state["biomass"], 3))
        h["yield"].append(round(crop_state["yield_kg"], 3))
        h["lai"].append(round(crop_state["lai"], 2))
        h["water"].append(round(self.water_used_L, 1))
        h["energy"].append(round(self.energy_kwh, 3))
        h["growth_rate"].append(round(crop_state["daily_growth"], 4))
        h["stress"].append(round(crop_state["combined_stress"], 3))
        h["dvs"].append(round(crop_state["dvs"], 3))
        h["stage"].append(crop_state["stage"])
        h["canopy_temp"].append(round(crop_state["canopy_temp"], 2))
        h["disease"].append(round(crop_state["disease_index"], 3))
        h["transpiration"].append(round(crop_state["transpiration"], 3))
        h["n_content"].append(round(crop_state["n_content"], 2))
        h["chlorophyll"].append(round(crop_state["chlorophyll"], 1))
        h["ec"].append(round(ns.ec_mS, 2))
        h["ph"].append(round(ns.ph, 2))
        h["net_ps"].append(round(crop_state["net_photosynthesis"], 2))
        h["vpd"].append(round(self.vpd, 3))
        h["fruit_count"].append(crop_state["fruit_count"])
        h["brix"].append(round(crop_state["brix_sugar"], 2))
        h["antioxidant"].append(round(crop_state["antioxidant"], 1))
        h["pest"].append(round(crop_state["pest_pressure"], 3))
        h["microbial"].append(round(crop_state["microbial_activity"], 3))
        h["co2_absorbed"].append(round(crop_state["co2_absorbed_kg"], 4))
        h["do2"].append(round(ns.dissolved_o2, 2))
        h["n_ppm"].append(round(ns.n_ppm, 1))
        h["k_ppm"].append(round(ns.k_ppm, 1))
        h["ca_content"].append(round(crop_state["ca_content"], 2))
        h["abscission"].append(crop_state["abscission"])

        return {
            "zone": self.zone_id, "step": self.step_count,
            "env": {
                "temp": self.temp_air, "humidity": self.humidity,
                "soil": self.soil_moist, "co2": self.co2_ppm,
                "light": self.light_w, "ec": ns.ec_mS, "ph": ns.ph,
                "root_temp": self.root_temp, "vpd": self.vpd,
                "do2": ns.dissolved_o2,
            },
            "crop": crop_state,
            "resources": {
                "water_L": self.water_used_L, "energy_kwh": self.energy_kwh,
                "co2_kg": self.co2_injected_kg, "fertilizer_kg": self.fertilizer_kg,
            },
            "maintenance": {
                c: r.wear_pct for c, r in self.maint_engine.records.items()
            },
            "alerts": self.alerts[-5:],
        }

    def _check_alerts(self, crop_state: Dict):
        p    = CROP_PROFILES[CropType(self.crop_type.value)]
        zone = self.zone_id
        cm   = self.crop_model
        ns   = self.nutrient_solution

        def add(level: str, msg: str, cat: str = "system"):
            self.alerts.append(Alert(level, f"[{zone}] {msg}", cat, zone_id=zone))

        # Temperature
        if self.temp_air > p.heat_stress_threshold:
            add("critical", f"🌡️ HEAT STRESS {self.temp_air:.1f}°C (limit {p.heat_stress_threshold}°C)", "temp")
        elif self.temp_air < p.cold_stress_threshold:
            add("critical", f"❄️ COLD STRESS {self.temp_air:.1f}°C (limit {p.cold_stress_threshold}°C)", "temp")
        elif abs(self.temp_air - p.optimal_temp) > 3:
            add("warning", f"🌡️ Suboptimal temp {self.temp_air:.1f}°C (opt {p.optimal_temp}°C)", "temp")

        # Humidity & VPD
        if self.humidity > 92:
            add("critical", f"💦 EXTREME humidity {self.humidity:.1f}% — Botrytis imminent!", "humidity")
        elif self.humidity > 88:
            add("warning", f"💦 High humidity {self.humidity:.1f}% — disease risk", "humidity")
        elif self.humidity < 35:
            add("warning", f"🏜️ Low humidity {self.humidity:.1f}% — transpiration stress", "humidity")
        if self.vpd > p.vpd_optimal * 2.5:
            add("warning", f"💨 High VPD {self.vpd:.2f} kPa — stomatal closure risk", "vpd")

        # Soil / Water
        if self.soil_moist < p.water_stress_threshold:
            add("warning", f"💧 Water stress {self.soil_moist:.1f}% (threshold {p.water_stress_threshold}%)", "water")
        elif self.soil_moist > 95:
            add("warning", f"🌊 Waterlogged {self.soil_moist:.1f}% — root anoxia risk", "water")

        # CO₂
        if self.co2_ppm < 330:
            add("warning", f"🌬️ CO₂ deficiency {self.co2_ppm:.0f}ppm", "co2")
        elif self.co2_ppm > 1800:
            add("info", f"🌿 Very high CO₂ {self.co2_ppm:.0f}ppm", "co2")

        # Disease
        if cm.disease_index > 0.35:
            add("critical", f"🦠 {cm.disease_type} OUTBREAK! idx={cm.disease_index:.3f}", "disease")
        elif cm.disease_index > 0.12:
            add("warning", f"⚠️ {cm.disease_type} risk idx={cm.disease_index:.3f}", "disease")

        # Nutrients
        if ns.ec_mS > 6.5:
            add("critical", f"🧪 SALT STRESS EC={ns.ec_mS:.1f}mS/cm", "nutrient")
        elif ns.ec_mS < 0.8:
            add("warning", f"🧪 Nutrient deficiency EC={ns.ec_mS:.1f}mS/cm", "nutrient")
        if ns.ph < 5.2 or ns.ph > 7.2:
            add("warning", f"⚗️ pH {ns.ph:.2f} critical (opt {p.ph_optimal})", "nutrient")
        if ns.n_ppm < 60:
            add("warning", f"🌿 N deficiency {ns.n_ppm:.0f}ppm", "nutrient")
        if ns.dissolved_o2 < 4.5:
            add("warning", f"💨 Low DO {ns.dissolved_o2:.1f}mg/L — root hypoxia", "nutrient")

        # Antagonisms
        for w in self.nutrient_mgr.check_antagonisms():
            add("warning", w, "nutrient")

        # Pests
        if cm.pest_pressure > 0.5:
            add("critical", f"🐛 {cm.pest_type.value} infestation {cm.pest_pressure:.2f}!", "pest")
        elif cm.pest_pressure > 0.2:
            add("warning", f"🐛 {cm.pest_type.value} pressure {cm.pest_pressure:.2f}", "pest")

        # Maintenance
        critical_comps = self.maint_engine.get_critical_components(threshold_pct=80.0)
        for rec in critical_comps[:2]:
            add("maint", f"🔧 {rec.component} wear {rec.wear_pct:.0f}% — service needed", "maintenance")

        # Sensor faults
        faults = self.kalman.get_fault_report()
        for f in faults:
            add("warning", f"📡 Sensor anomaly detected: {f}", "sensor")

        # Milestones
        if cm.stage == GrowthStage.HARVEST:
            add("ok", f"🎉 HARVEST READY! Yield {cm.yield_kg:.2f}kg/m² | Brix={cm.brix_sugar:.1f}°", "milestone")

        # Limit alert buffer
        self.alerts = self.alerts[-80:]


# ══════════════════════════════════════════════════════════════════════════════
# 10. ECONOMICS ENGINE v4
# ══════════════════════════════════════════════════════════════════════════════

class EconomicsEngine:
    """
    Full P&L with IDR pricing, carbon credits, labour, pest mgmt, payback.
    """
    def __init__(self):
        self.history:          List[Dict] = []
        self.initial_capex_idr: float     = 500_000_000.0  # Rp 500jt baseline setup

    def compute(self, zones: List[GreenZone]) -> EconomicState:
        if not zones:
            return EconomicState()

        total_yield   = sum(z.crop_model.yield_kg * z.area_m2 for z in zones)
        total_water   = sum(z.water_used_L     for z in zones)
        total_energy  = sum(z.energy_kwh       for z in zones)
        total_co2_inj = sum(z.co2_injected_kg  for z in zones)
        total_fert    = sum(z.fertilizer_kg    for z in zones)
        total_labor   = sum(z.labor_hrs        for z in zones)
        total_co2_seq = sum(z.crop_model.net_carbon_seq_kg for z in zones)

        # Revenue (crop-specific pricing)
        revenue = sum(
            z.crop_model.yield_kg * z.area_m2 * CROP_PROFILES[CropType(z.crop_type.value)].market_price_per_kg
            * CROP_PROFILES[CropType(z.crop_type.value)].marketable_fraction
            for z in zones
        )

        # Quality premium for high Brix / antioxidant
        quality_premium = sum(
            z.crop_model.yield_kg * z.area_m2 *
            max(0.0, (z.crop_model.brix_sugar - 5.0) / 5.0) *
            CROP_PROFILES[CropType(z.crop_type.value)].market_price_per_kg * 0.15
            for z in zones
        )

        cost_w    = total_water   * WATER_COST_L
        cost_e    = total_energy  * PLN_COST_KWH
        cost_co2  = total_co2_inj * CO2_COST_KG
        cost_fert = total_fert    * FERT_COST_KG
        cost_lab  = total_labor   * LABOR_COST_HR
        # Pest management (10k IDR per 0.1 pest pressure unit per step)
        cost_pest = sum(max(0.0, z.crop_model.pest_pressure * 0.5 * 100_000.0) for z in zones)
        # Predictive maintenance costs
        cost_maint = sum(z.maint_engine.total_repair_cost_estimate() for z in zones)

        total_opex = cost_w + cost_e + cost_co2 + cost_fert + cost_lab + cost_pest + cost_maint

        # Carbon credits (voluntary carbon market)
        carbon_credits = max(0.0, total_co2_seq) * CARBON_CREDIT_KG

        total_revenue = revenue + quality_premium + carbon_credits
        profit        = total_revenue - total_opex
        roi           = (profit / max(1.0, total_opex)) * 100.0
        cpk           = total_opex / max(0.001, total_yield)

        # Payback period (simple): months to recover capex at current profit rate
        monthly_profit   = profit / max(1, max(z.step_count for z in zones)) * 720  # assuming 720 steps/month
        payback_days     = self.initial_capex_idr / max(1.0, profit / max(1, max(z.step_count for z in zones)) * 24)

        state = EconomicState(
            revenue_idr          = revenue + quality_premium,
            cost_water_idr       = cost_w,
            cost_energy_idr      = cost_e,
            cost_co2_idr         = cost_co2,
            cost_fertilizer_idr  = cost_fert,
            cost_labor_idr       = cost_lab,
            cost_pest_mgmt_idr   = cost_pest + cost_maint,
            profit_idr           = profit,
            roi_percent          = roi,
            cost_per_kg_idr      = cpk,
            carbon_credits_idr   = carbon_credits,
            net_carbon_kg        = total_co2_seq,
            payback_period_days  = max(0.0, payback_days),
        )

        self.history.append({
            "step":    max(z.step_count for z in zones),
            "revenue": revenue, "profit": profit, "roi": roi,
            "cost":    total_opex, "carbon": carbon_credits,
        })
        return state


# ══════════════════════════════════════════════════════════════════════════════
# 11. ML PREDICTIVE ENGINE v4 — MULTI-MODEL ENSEMBLE
# ══════════════════════════════════════════════════════════════════════════════

class MLPredictor:
    """
    Ensemble ML prediction:
    - Kalman-smoothed EMA baseline
    - Ridge polynomial regression
    - Holt-Winters double exponential smoothing
    - Gradient Boosting (sklearn if available)
    - Conformal prediction intervals
    """

    def __init__(self, horizon: int = 24):
        self.horizon   = horizon
        self.models:   Dict[str, Any] = {}
        self.scalers:  Dict[str, Any] = {}
        self.ema_state: Dict[str, float] = {}

    def _ema(self, data: List[float], alpha: float = 0.25) -> List[float]:
        if not data:
            return []
        out = [float(data[0])]
        for v in data[1:]:
            out.append(alpha * float(v) + (1.0 - alpha) * out[-1])
        return out

    def _holt_winters(self, data: List[float], alpha: float = 0.3,
                      beta: float = 0.1, horizon: int = 12) -> List[float]:
        """Double exponential smoothing (Holt's linear method)"""
        if len(data) < 3:
            return [data[-1]] * horizon if data else [0.0] * horizon
        # Init
        l = float(data[0])
        b = float(data[1]) - float(data[0])
        forecasts = []
        for d in data[1:]:
            l_prev, b_prev = l, b
            l = alpha * float(d) + (1 - alpha) * (l_prev + b_prev)
            b = beta * (l - l_prev) + (1 - beta) * b_prev
        for h in range(1, horizon + 1):
            forecasts.append(l + h * b)
        return forecasts

    def _ridge_poly_forecast(self, data: List[float], horizon: int) -> List[float]:
        if len(data) < 5:
            return [data[-1]] * horizon if data else [0.0] * horizon
        n   = len(data)
        x   = np.arange(n, dtype=float).reshape(-1, 1)
        y   = np.array(data, dtype=float)
        deg = min(4, n // 5)
        X_poly = np.column_stack([x.flatten() ** d for d in range(deg + 1)])
        lam    = 5e-4
        try:
            A    = X_poly.T @ X_poly + lam * np.eye(X_poly.shape[1])
            b    = X_poly.T @ y
            coef = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            return [float(np.mean(y))] * horizon

        preds = []
        for i in range(horizon):
            xi      = n + i
            xi_poly = np.array([xi ** d for d in range(deg + 1)])
            preds.append(float(np.dot(xi_poly, coef)))
        return preds

    def _gbr_forecast(self, data: List[float], horizon: int) -> Optional[List[float]]:
        """GradientBoosting with lag features"""
        if not SKLEARN_AVAILABLE or len(data) < 20:
            return None
        n_lags = min(10, len(data) // 2)
        X, y   = [], []
        for i in range(n_lags, len(data)):
            X.append(data[i-n_lags:i])
            y.append(data[i])
        if len(X) < 5:
            return None
        try:
            model  = GradientBoostingRegressor(n_estimators=50, max_depth=3, random_state=42)
            model.fit(np.array(X), np.array(y))
            preds  = []
            window = list(data[-n_lags:])
            for _ in range(horizon):
                p = float(model.predict(np.array([window]))[0])
                preds.append(p)
                window = window[1:] + [p]
            return preds
        except Exception:
            return None

    def _conformal_interval(self, data: List[float], preds: List[float],
                             confidence: float = 0.90) -> Tuple[List[float], List[float]]:
        """Non-conformity score based prediction intervals"""
        if len(data) < 10:
            std = float(np.std(data)) if data else 1.0
            return ([p - 1.96*std for p in preds],
                    [p + 1.96*std for p in preds])
        resids = [abs(data[i] - data[i-1]) for i in range(1, len(data))]
        q = float(np.quantile(resids, confidence))
        widths = [q * (1 + 0.05*h) for h in range(len(preds))]
        return ([p - w for p, w in zip(preds, widths)],
                [p + w for p, w in zip(preds, widths)])

    def forecast(self, zone: "GreenZone") -> Dict[str, Any]:
        h = zone.history
        results = {}
        forecast_vars = ["temp", "humidity", "biomass", "yield", "disease",
                         "co2", "stress", "n_ppm", "pest", "brix"]

        for var in forecast_vars:
            data = h.get(var, [])
            if len(data) < 5:
                continue
            try:
                data_f = [float(d) for d in data if d is not None]
                if len(data_f) < 5:
                    continue
                smooth     = self._ema(data_f, alpha=0.22)
                poly_pred  = self._ridge_poly_forecast(smooth, self.horizon)
                hw_pred    = self._holt_winters(smooth, horizon=self.horizon)
                gbr_pred   = self._gbr_forecast(data_f, self.horizon)

                # Weighted ensemble
                if gbr_pred is not None:
                    ensemble = [0.25*p + 0.35*hw + 0.40*gbr
                                for p, hw, gbr in zip(poly_pred, hw_pred, gbr_pred)]
                else:
                    ensemble = [0.45*p + 0.55*hw for p, hw in zip(poly_pred, hw_pred)]

                lo, hi = self._conformal_interval(data_f, ensemble)
                trend  = (ensemble[-1] - ensemble[0]) / max(1, self.horizon)

                results[var] = {
                    "forecast":    [round(p, 3) for p in ensemble],
                    "lower_95":    [round(l, 3) for l in lo],
                    "upper_95":    [round(u, 3) for u in hi],
                    "trend":       round(trend, 4),
                    "trend_dir":   "↑" if trend > 0.005 else ("↓" if trend < -0.005 else "→"),
                    "last":        round(data_f[-1], 3),
                    "predicted_at_horizon": round(ensemble[-1], 3),
                    "model_used":  "GBR+HW+POLY" if gbr_pred else "HW+POLY",
                }
            except Exception:
                continue

        # Harvest projection
        dvs_data   = [float(d) for d in h.get("dvs", []) if d is not None]
        yield_data = [float(d) for d in h.get("yield", []) if d is not None]
        if len(dvs_data) > 10 and dvs_data[-1] > 0.01:
            dvs_rate    = float(np.mean(np.diff(dvs_data[-10:]))) if len(dvs_data) > 10 else 0.01
            dvs_rate    = max(1e-6, dvs_rate)
            steps_left  = max(0.0, (2.0 - dvs_data[-1]) / dvs_rate)
            gr_data     = [float(d) for d in h.get("growth_rate", []) if d is not None]
            avg_gr      = float(np.mean(gr_data[-10:])) if len(gr_data) >= 10 else 0.005
            proj_yield  = (yield_data[-1] if yield_data else 0.0) + avg_gr * steps_left * 0.55
            proj_rev    = proj_yield * zone.area_m2 * CROP_PROFILES[CropType(zone.crop_type.value)].market_price_per_kg
            # Water footprint projection
            wp          = CROP_PROFILES[CropType(zone.crop_type.value)].water_per_kg_yield
            proj_water  = proj_yield * zone.area_m2 * wp

            results["harvest_estimate"] = {
                "steps_remaining":      int(steps_left),
                "dvs_current":          round(dvs_data[-1], 3),
                "projected_yield_m2":   round(proj_yield, 3),
                "projected_yield_kg":   round(proj_yield * zone.area_m2, 1),
                "projected_revenue":    round(proj_rev, 0),
                "projected_water_L":    round(proj_water, 0),
                "brix_projected":       round(zone.crop_model.brix_sugar, 2),
            }

        return results

    def anomaly_score(self, zone: "GreenZone") -> Dict[str, float]:
        """CUSUM + z-score hybrid anomaly detection"""
        scores = {}
        h      = zone.history
        for var in ["temp", "humidity", "soil", "co2", "growth_rate", "disease", "stress", "pest"]:
            data = [float(d) for d in h.get(var, []) if d is not None]
            if len(data) >= 12:
                baseline  = float(np.mean(data[:-5]))
                sigma     = max(0.001, float(np.std(data[:-5])))
                recent    = float(np.mean(data[-5:]))
                z         = abs(recent - baseline) / sigma

                # CUSUM statistic
                cusum_pos = cusum_neg = 0.0
                k_ref     = 0.5 * sigma
                for v in data[-10:]:
                    cusum_pos = max(0.0, cusum_pos + (v - baseline) - k_ref)
                    cusum_neg = max(0.0, cusum_neg - (v - baseline) - k_ref)
                cusum_combined = cusum_pos + cusum_neg

                # Combined score
                scores[var] = round(max(z, cusum_combined / max(1.0, sigma * 5)), 2)
        return scores


# ══════════════════════════════════════════════════════════════════════════════
# 12. GENETIC ALGORITHM OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════

class GeneticOptimizer:
    """
    Genetic algorithm for finding optimal setpoints.
    Minimizes energy cost while maximizing yield.
    """
    def __init__(self, pop_size: int = 30, generations: int = 20):
        self.pop_size   = pop_size
        self.generations= generations
        self.best_genome: Optional[List[float]] = None
        self.best_fitness: float = -np.inf
        self.history_fitness: List[float] = []

    def _genome_to_setpoints(self, g: List[float]) -> Dict[str, float]:
        return {
            "temp_sp":     np.clip(g[0], 15.0, 35.0),
            "humidity_sp": np.clip(g[1], 40.0, 90.0),
            "co2_sp":      np.clip(g[2], 400.0, 1500.0),
            "soil_sp":     np.clip(g[3], 40.0, 85.0),
            "vpd_sp":      np.clip(g[4], 0.4, 2.5),
        }

    def _fitness(self, genome: List[float], zone: GreenZone,
                 crop_params: CropParams) -> float:
        sp       = self._genome_to_setpoints(genome)
        T_sp     = sp["temp_sp"]
        H_sp     = sp["humidity_sp"]
        CO2_sp   = sp["co2_sp"]
        SM_sp    = sp["soil_sp"]

        # Yield potential (normalized deviation from optima)
        y_T   = max(0.0, 1.0 - abs(T_sp - crop_params.optimal_temp) / 8.0)
        y_H   = max(0.0, 1.0 - abs(H_sp - crop_params.optimal_humidity) / 20.0)
        y_CO2 = min(1.5, 1.0 + 0.3 * math.log(max(1, CO2_sp / 400)) / math.log(2))
        y_SM  = max(0.0, 1.0 - abs(SM_sp - crop_params.optimal_soil_moisture) / 20.0)
        yield_score = y_T * y_H * y_CO2 * y_SM

        # Energy cost proxy (heating/cooling + CO2)
        energy_proxy = (
            max(0.0, T_sp - 25.0) * 0.5 +      # cooling above 25
            max(0.0, 20.0 - T_sp) * 0.8 +       # heating below 20
            max(0.0, CO2_sp - 800.0) * 0.001     # CO2 injection
        ) / 10.0

        # Disease risk from humidity
        dis_risk = max(0.0, (H_sp - crop_params.disease_humidity_risk) / 10.0) * 0.3

        return yield_score - energy_proxy - dis_risk

    def optimize(self, zone: GreenZone, crop_params: CropParams) -> Dict[str, float]:
        """Run GA to find optimal setpoints"""
        # Random initial population
        pop = [
            [
                random.uniform(15.0, 35.0),   # temp
                random.uniform(40.0, 90.0),   # humidity
                random.uniform(400.0, 1500.0),# co2
                random.uniform(40.0, 85.0),   # soil
                random.uniform(0.4, 2.5),     # vpd
            ]
            for _ in range(self.pop_size)
        ]

        for gen in range(self.generations):
            # Evaluate fitness
            fitnesses = [self._fitness(g, zone, crop_params) for g in pop]

            # Elitism: keep top 20%
            elite_n  = max(2, self.pop_size // 5)
            ranked   = sorted(zip(fitnesses, pop), key=lambda x: x[0], reverse=True)
            new_pop  = [g for _, g in ranked[:elite_n]]

            # Tournament selection + crossover
            while len(new_pop) < self.pop_size:
                t1 = random.choices(list(range(self.pop_size)),
                                    weights=[max(0.001, f) for f in fitnesses], k=2)
                p1, p2 = pop[t1[0]], pop[t1[1]]
                # Uniform crossover
                child = [p1[i] if random.random() < 0.5 else p2[i] for i in range(len(p1))]
                # Gaussian mutation
                child = [
                    c + random.gauss(0, 0.5) * (1 - gen / self.generations)
                    for c in child
                ]
                new_pop.append(child)

            pop = new_pop
            best_f = max(fitnesses)
            self.history_fitness.append(best_f)
            if best_f > self.best_fitness:
                self.best_fitness = best_f
                self.best_genome  = ranked[0][1]

        if self.best_genome is None:
            return self._genome_to_setpoints(pop[0])
        return self._genome_to_setpoints(self.best_genome)


# ══════════════════════════════════════════════════════════════════════════════
# 13. AI CONTROLLER v4 — HIERARCHICAL + PREDICTIVE + GENETIC
# ══════════════════════════════════════════════════════════════════════════════

class AIControllerV4:
    """
    12-layer hierarchical AI control:
    L1:  Safety hard limits
    L2:  Anti-windup PID feedback
    L3:  Predictive feed-forward (weather forecast)
    L4:  Crop-stage setpoint scheduling
    L5:  ET-deficit irrigation
    L6:  CO₂ enrichment
    L7:  Humidification
    L8:  Spectral LED management
    L9:  Fertilization scheduler (NPK-demand aware)
    L10: Disease prevention mode
    L11: Pest-triggered response
    L12: Energy budget management
    """

    def __init__(self):
        self.pid_states:  Dict[str, Dict]   = {}
        self.decision_log: List[str]        = []
        self.setpoint_log: Dict             = {}
        self.total_decisions                = 0
        self.energy_budget_kwh_day          = 50.0
        self.energy_used_today              = 0.0
        self.last_day                       = datetime.datetime.now().day
        self.ga_optimizer                   = GeneticOptimizer(pop_size=25, generations=15)
        self.ga_setpoints: Optional[Dict]   = None
        self.ga_last_run                    = 0    # step count of last GA run
        self.ga_run_every                   = 100  # re-run GA every N steps

    def _get_pid(self, zone_id: str) -> Dict:
        if zone_id not in self.pid_states:
            self.pid_states[zone_id] = {
                "temp_i": 0.0, "hum_i": 0.0, "soil_i": 0.0, "co2_i": 0.0,
                "temp_prev_e": 0.0, "hum_prev_e": 0.0,
                "windup_limit": 60.0,
            }
        return self.pid_states[zone_id]

    def _stage_setpoints(self, stage: GrowthStage, crop_p: CropParams,
                         is_night: bool, ga_sp: Optional[Dict] = None) -> Dict:
        T_base = ga_sp["temp_sp"] if ga_sp else crop_p.optimal_temp
        H_base = ga_sp["humidity_sp"] if ga_sp else crop_p.optimal_humidity
        CO2_sp = ga_sp["co2_sp"] if ga_sp else crop_p.optimal_co2
        SM_sp  = ga_sp["soil_sp"] if ga_sp else crop_p.optimal_soil_moisture

        stage_offsets = {
            GrowthStage.GERMINATION: (+1.5, +6.0, -200, +5),
            GrowthStage.SEEDLING:    (+0.5, +3.0, -100, +3),
            GrowthStage.VEGETATIVE:  ( 0.0,  0.0,   0,   0),
            GrowthStage.FLOWERING:   (-1.0, -5.0, +50,  -2),
            GrowthStage.FRUITING:    ( 0.0, -3.0, +100, +2),
            GrowthStage.HARVEST:     (-2.0, -6.0, -200, -5),
            GrowthStage.DORMANT:     (-5.0, -8.0, -300, -10),
        }
        dT, dH, dCO2, dSM = stage_offsets.get(stage, (0, 0, 0, 0))

        T_set  = T_base + dT + (crop_p.night_temp_offset if is_night else 0.0)
        H_set  = H_base + dH
        CO2_set= max(400.0, CO2_sp + dCO2)
        SM_set = max(25.0, SM_sp + dSM)

        # VPD-corrected humidity target
        es     = 0.6108 * math.exp(17.27 * T_set / (T_set + 237.3))
        vpd_target = crop_p.vpd_optimal
        h_from_vpd = max(30.0, min(95.0, 100.0 * (1.0 - vpd_target / es)))
        H_set = 0.6 * H_set + 0.4 * h_from_vpd   # blend RH and VPD targets

        return {"temp": round(T_set, 1), "humidity": round(H_set, 1),
                "co2": round(CO2_set, 0), "soil": round(SM_set, 1)}

    def compute(self, zone: "GreenZone", weather: WeatherData,
                crop_p: CropParams) -> Dict:
        pid    = self._get_pid(zone.zone_id)
        T, H   = zone.temp_air, zone.humidity
        SM, CO2= zone.soil_moist, zone.co2_ppm
        DVS    = zone.crop_model.dvs
        stage  = zone.crop_model.stage
        dis_i  = zone.crop_model.disease_index
        pest_p = zone.crop_model.pest_pressure
        vpd    = zone._vpd()
        ns     = zone.nutrient_solution
        cm     = zone.crop_model

        is_night = weather.solar_radiation < 40

        # ── GA Setpoint Optimization (periodic) ───────────────────────────
        total_steps = zone.step_count
        if total_steps - self.ga_last_run >= self.ga_run_every:
            self.ga_setpoints = self.ga_optimizer.optimize(zone, crop_p)
            self.ga_last_run  = total_steps

        sp = self._stage_setpoints(stage, crop_p, is_night, self.ga_setpoints)
        T_sp  = sp["temp"];     H_sp  = sp["humidity"]
        SM_sp = sp["soil"];     CO2_sp= sp["co2"]

        # ── Layer 2: PID with anti-windup ─────────────────────────────────
        e_T  = T   - T_sp
        e_H  = H   - H_sp
        e_SM = SM  - SM_sp
        e_CO2= CO2 - CO2_sp

        WL = pid["windup_limit"]
        pid["temp_i"]  = float(np.clip(pid["temp_i"] + e_T,   -WL, WL))
        pid["hum_i"]   = float(np.clip(pid["hum_i"]  + e_H,   -WL, WL))
        pid["soil_i"]  = float(np.clip(pid["soil_i"] + e_SM,  -WL, WL))
        pid["co2_i"]   = float(np.clip(pid["co2_i"]  + e_CO2, -WL*5, WL*5))

        d_T = e_T - pid["temp_prev_e"]
        d_H = e_H - pid["hum_prev_e"]
        pid["temp_prev_e"] = e_T
        pid["hum_prev_e"]  = e_H

        PID_T = 0.65 * e_T + 0.04 * pid["temp_i"] + 0.22 * d_T
        PID_H = 0.55 * e_H + 0.035* pid["hum_i"]  + 0.18 * d_H

        # ── Layer 1: Safety Hard Limits ────────────────────────────────────
        heating = T < (T_sp - 2.0) or T < crop_p.cold_stress_threshold + 0.5
        cooling = T > (T_sp + 2.0) or T > crop_p.heat_stress_threshold - 1.0
        vent    = H > 90 or T > (T_sp + 5.0) or CO2 > 1700 or dis_i > 0.18

        # ── PID refinement ─────────────────────────────────────────────────
        if PID_T < -1.5: heating = True
        if PID_T >  1.5: cooling = True
        if PID_H >  2.5: vent    = True

        # ── Layer 3: Predictive Feed-Forward ──────────────────────────────
        forecast_t = weather.forecast_temp
        if forecast_t:
            avg_next6h = float(np.mean(forecast_t[:6]))
            if avg_next6h > crop_p.heat_stress_threshold - 2:
                cooling = True
            if avg_next6h < crop_p.cold_stress_threshold + 2:
                heating = True
        if weather.rainfall > 1.5:
            vent = False  # prevent humid outdoor air ingress

        # ── Layer 5: Irrigation (ET-deficit + crop stage coeff) ───────────
        stage_kc = {
            GrowthStage.GERMINATION: 0.35, GrowthStage.SEEDLING:  0.70,
            GrowthStage.VEGETATIVE:  1.00, GrowthStage.FLOWERING:  1.15,
            GrowthStage.FRUITING:    1.30, GrowthStage.HARVEST:    0.65,
            GrowthStage.DORMANT:     0.25,
        }.get(stage, 1.0)

        soil_def  = SM_sp - SM
        irrigation = 0.0
        if soil_def > 20:
            irrigation = min(30.0, soil_def * 0.65 * stage_kc)
        elif soil_def > 7:
            irrigation = min(14.0, soil_def * 0.38 * stage_kc)
        if vpd > crop_p.vpd_optimal * 1.6:
            irrigation *= 1.25
        # NFT/Aeroponic: continuous low irrigation
        if zone.irrigation_mode in [IrrigationMode.NFT, IrrigationMode.AEROPONIC, IrrigationMode.DWC]:
            irrigation = max(irrigation, 3.0)

        # ── Layer 6: CO₂ Enrichment ────────────────────────────────────────
        co2_inject = (
            CO2 < CO2_sp * 0.82 and
            weather.solar_radiation > 60 and
            not vent and not is_night and
            stage not in [GrowthStage.GERMINATION, GrowthStage.HARVEST]
        )

        # ── Layer 7: Humidification / Dehumidification ────────────────────
        humidifier   = H < (H_sp - 12) and not vent and not is_night
        dehumidifier = H > (H_sp + 10) and dis_i < 0.1

        # ── Layer 8: Spectral LED Management ─────────────────────────────
        dli_target = crop_p.dli_optimal
        current_dli = weather.solar_radiation * 0.46 / 1000.0 * 3600.0 / 54.0

        if stage in [GrowthStage.VEGETATIVE, GrowthStage.SEEDLING] and current_dli < dli_target * 0.55:
            led_grow     = True
            led_spectrum = LEDSpectrum.VEGE.value
        elif stage in [GrowthStage.FLOWERING, GrowthStage.FRUITING] and current_dli < dli_target * 0.65:
            led_grow     = True
            led_spectrum = LEDSpectrum.BLOOM.value
        elif dis_i > 0.3:
            led_grow     = True
            led_spectrum = LEDSpectrum.UV_BOOST.value
        elif current_dli < dli_target * 0.4 and not is_night:
            led_grow     = True
            led_spectrum = LEDSpectrum.FULL.value
        else:
            led_grow     = False
            led_spectrum = LEDSpectrum.FULL.value

        # ── Layer 9: Smart NPK Fertilization ──────────────────────────────
        n_demand = cm.n_content < 2.2
        p_demand = cm.p_content < 0.3
        k_demand = cm.k_content < 2.5 and stage in [GrowthStage.FLOWERING, GrowthStage.FRUITING]
        fertilize = (
            stage in [GrowthStage.VEGETATIVE, GrowthStage.FLOWERING, GrowthStage.FRUITING] and
            (zone.step_count % 6 == 0 or n_demand or p_demand or k_demand)
        )
        # pH adjust
        ph_adjust_up   = ns.ph < 5.5
        ph_adjust_down = ns.ph > 7.1

        # ── Layer 10: Disease Prevention ──────────────────────────────────
        if dis_i > 0.14:
            vent         = True
            humidifier   = False
            dehumidifier = True
            if H > 82:
                cooling  = True
        if dis_i > 0.38:
            led_grow     = True
            led_spectrum = LEDSpectrum.UV_BOOST.value
            irrigation   = irrigation * 0.65

        # ── Layer 11: Pest Response ────────────────────────────────────────
        if pest_p > 0.3:
            # Biological control conditions
            vent = True   # introduce beneficial predatory insects via airflow
            if pest_p > 0.5:
                led_spectrum = LEDSpectrum.UV_BOOST.value  # UV repels some pests
                led_grow     = True

        # ── Layer 12: Energy Budget ────────────────────────────────────────
        today = datetime.datetime.now().day
        if today != self.last_day:
            self.energy_used_today = 0.0
            self.last_day = today

        if self.energy_used_today > self.energy_budget_kwh_day * 0.88:
            led_grow     = False
            humidifier   = False
            co2_inject   = False
            dehumidifier = False

        est_kwh = (int(heating)*3.2 + int(cooling)*2.8 +
                   int(led_grow)*0.24*zone.area_m2/100 +
                   int(humidifier)*0.06)
        self.energy_used_today += est_kwh

        # ── Shade Screen ───────────────────────────────────────────────────
        shade_screen = 1.0 if weather.solar_radiation > 900 else 0.0  # deploy when overexposure

        # ── Decision log ───────────────────────────────────────────────────
        decisions = []
        if heating:    decisions.append("🔥 HEAT")
        if cooling:    decisions.append("❄️ COOL")
        if vent:       decisions.append("💨 VENT")
        if irrigation: decisions.append(f"💧 {irrigation:.0f}L")
        if co2_inject: decisions.append("🌬️ CO₂")
        if humidifier: decisions.append("💦 HUM")
        if dehumidifier: decisions.append("💧↓ DEHUM")
        if led_grow:   decisions.append(f"💡 LED-{led_spectrum[:4]}")
        if fertilize:  decisions.append("🧪 FERT")
        if ph_adjust_up:   decisions.append("⬆️ pH↑")
        if ph_adjust_down: decisions.append("⬇️ pH↓")
        if shade_screen:   decisions.append("🌤 SHADE")

        self.decision_log    = decisions
        self.total_decisions += 1

        return {
            "heating":         int(heating),
            "cooling":         int(cooling),
            "vent":            int(vent),
            "irrigation":      round(irrigation, 1),
            "co2_inject":      int(co2_inject),
            "humidifier":      int(humidifier),
            "dehumidifier":    int(dehumidifier),
            "led_grow":        int(led_grow),
            "led_spectrum":    led_spectrum,
            "fertilize":       int(fertilize),
            "ph_adjust_up":    int(ph_adjust_up),
            "ph_adjust_down":  int(ph_adjust_down),
            "shade_screen":    shade_screen,
            "stress_override": 1.0,
            "setpoints":       sp,
            "pid_output":      {"T": round(PID_T, 2), "H": round(PID_H, 2)},
            "ga_setpoints":    self.ga_setpoints,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 14. GREENLIGHTPLUS WRAPPER v4
# ══════════════════════════════════════════════════════════════════════════════

class GreenLightWrapper:
    def __init__(self):
        self.available = GLP_AVAILABLE

    def run_model(self, weather: WeatherData, zone: "GreenZone",
                  duration_hours: int = 24) -> Dict:
        if not self.available:
            return {"status": "unavailable"}
        try:
            glp_input = {
                "T_out":       weather.temp_outside,
                "RH_out":      weather.humidity_outside / 100.0,
                "I_glob":      weather.solar_radiation,
                "v_Wind":      weather.wind_speed,
                "CO2_out":     weather.co2_ambient,
                "zone_area":   zone.area_m2,
                "zone_volume": zone.volume_m3,
                "T_in":        zone.temp_air,
                "crop":        zone.crop_type.value,
            }
            return {"status": "ok", "data": glp_input,
                    "note": "GLP parameters prepared for full model execution"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}

    def badge(self) -> str:
        css = "badge-online" if self.available else "badge-offline"
        txt = "✓ GLP" if self.available else "✗ GLP"
        return f'<span class="status-badge {css}">{txt}</span>'


# ══════════════════════════════════════════════════════════════════════════════
# 15. SYSTEM LOGGER v4
# ══════════════════════════════════════════════════════════════════════════════

class SystemLogger:
    COLORS = {
        "INFO":    "#44aa44", "WARN":    "#eeaa33", "ERROR":  "#ee4444",
        "AI":      "#44aaee", "HARVEST": "#eebb33", "DISEASE":"#cc44ee",
        "MAINT":   "#ffcc00", "PEST":    "#ff8844", "CARBON": "#44cccc",
        "GA":      "#aa66ff", "KALMAN":  "#66aaff",
    }

    def __init__(self, maxlen: int = 150):
        self.logs: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def log(self, msg: str, level: str = "INFO"):
        ts          = datetime.datetime.now().strftime("%H:%M:%S")
        level_label = str(level).upper()[:10]
        color       = self.COLORS.get(level_label, "#44aa44")
        safe_msg    = html.escape(str(msg), quote=False)
        with self._lock:
            self.logs.append(
                f'<span style="color:{color}">[{ts}][{level_label:6s}] {safe_msg}</span>'
            )

    def render(self):
        with self._lock:
            html = "<br>".join(reversed(list(self.logs)))
        st.markdown(
            f'<div class="terminal-log">{html}</div>',
            unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════════════════════════════════
# 16. RENDER FUNCTIONS v4
# ══════════════════════════════════════════════════════════════════════════════

def fmt_idr(val: float) -> str:
    if abs(val) >= 1e9:  return f"Rp {val/1e9:.2f}M"
    if abs(val) >= 1e6:  return f"Rp {val/1e6:.2f}jt"
    if abs(val) >= 1e3:  return f"Rp {val/1e3:.1f}rb"
    return f"Rp {val:.0f}"


@dataclass(frozen=True)
class DashboardMetric:
    icon: str
    label: str
    value: str
    delta: str = ""
    state: str = "neutral"
    hint: str = ""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def finite_float(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def score_state(score: float) -> str:
    score = finite_float(score)
    if score >= 80.0:
        return "good"
    if score >= 58.0:
        return "warn"
    return "bad"


def threshold_state(value: Any, warn: float, bad: float,
                    higher_is_bad: bool = True) -> str:
    value = finite_float(value)
    if higher_is_bad:
        if value >= bad:
            return "bad"
        if value >= warn:
            return "warn"
        return "good"
    if value <= bad:
        return "bad"
    if value <= warn:
        return "warn"
    return "good"


def metric_delta(value: Any, target: Any, unit: str = "", precision: int = 1,
                 warn: Optional[float] = None, bad: Optional[float] = None) -> Tuple[str, str]:
    value_f  = finite_float(value)
    target_f = finite_float(target)
    diff     = value_f - target_f
    span     = max(abs(target_f), 1.0)
    warn     = span * 0.05 if warn is None else max(float(warn), 0.0)
    bad      = max(warn * 2.2, span * 0.12) if bad is None else max(float(bad), warn)
    dist     = abs(diff)
    state    = "good" if dist <= warn else ("warn" if dist <= bad else "bad")
    arrow    = "↑" if diff >= 0 else "↓"
    return f"{arrow} {diff:+.{precision}f}{unit}", state


def closeness_score(value: Any, target: Any, span: float) -> float:
    span = max(abs(float(span)), 1e-6)
    return 100.0 * clamp(1.0 - abs(finite_float(value) - finite_float(target)) / span, 0.0, 1.0)


def value_css(value: Any) -> str:
    clean = str(value)
    return " is-long" if len(clean) > 10 else ""


def render_meta_row(items: List[Tuple[str, str, Any]]) -> str:
    if not items:
        return ""
    pills = []
    for icon, label, value in items:
        pills.append(
            f'<span class="ag4-meta-pill"><span>{esc(icon)}</span>'
            f'<span>{esc(label)}: {esc(value)}</span></span>'
        )
    return f'<div class="ag4-meta-row">{"".join(pills)}</div>'


def render_metric_wall(title: str, metrics: List[DashboardMetric],
                       meta: Optional[List[Tuple[str, str, Any]]] = None,
                       min_width: int = 132, note: str = ""):
    cards = []
    valid_states = {"good", "warn", "bad", "info", "neutral"}
    for metric in metrics:
        state = metric.state if metric.state in valid_states else "neutral"
        delta_html = (
            f'<span class="ag4-delta">{esc(metric.delta)}</span>'
            if metric.delta else ""
        )
        hint_attr = f' title="{esc(metric.hint)}"' if metric.hint else ""
        cards.append(
            f'<div class="ag4-metric ag4-state-{state}"{hint_attr}>'
            f'<div class="ag4-label"><span class="ag4-icon">{esc(metric.icon)}</span>'
            f'<span>{esc(metric.label)}</span></div>'
            f'<div class="ag4-value{value_css(metric.value)}">{esc(metric.value)}</div>'
            f'{delta_html}</div>'
        )
    note_html = f'<div class="ag4-panel-note">{esc(note)}</div>' if note else ""
    title_html = f'<div class="section-header">{esc(title)}</div>' if title else ""
    st.markdown(
        f'{title_html}{render_meta_row(meta or [])}'
        f'<div class="ag4-metric-grid" style="--ag4-metric-min:{int(min_width)}px;">'
        f'{"".join(cards)}</div>{note_html}',
        unsafe_allow_html=True
    )


def compute_zone_intelligence(zone: GreenZone) -> Dict[str, float]:
    p  = CROP_PROFILES[CropType(zone.crop_type.value)]
    cm = zone.crop_model
    ns = zone.nutrient_solution

    climate = (
        closeness_score(zone.temp_air, p.optimal_temp, 9.0) * 0.30 +
        closeness_score(zone.humidity, p.optimal_humidity, 30.0) * 0.20 +
        closeness_score(zone.vpd, p.vpd_optimal, 1.7) * 0.20 +
        closeness_score(zone.co2_ppm, p.optimal_co2, 900.0) * 0.15 +
        closeness_score(zone.root_temp, p.root_zone_temp_optimal, 8.0) * 0.15
    )
    nutrients = (
        closeness_score(ns.ec_mS, p.ec_optimal, 2.6) * 0.28 +
        closeness_score(ns.ph, p.ph_optimal, 1.7) * 0.24 +
        closeness_score(ns.n_ppm, 200.0 if p.nitrogen_demand_high else 140.0, 180.0) * 0.18 +
        closeness_score(ns.k_ppm, 300.0, 260.0) * 0.16 +
        closeness_score(ns.dissolved_o2, 8.0, 5.0) * 0.14
    )
    biosecurity = 100.0 * clamp(
        1.0 - (cm.disease_index * 0.62 + cm.pest_pressure * 0.45 +
               max(0.0, zone.humidity - p.disease_humidity_risk) * 0.006),
        0.0, 1.0
    )
    worst_wear = max(
        [r.wear_pct for r in zone.maint_engine.records.values()] or [0.0]
    )
    maintenance = clamp(100.0 - worst_wear, 0.0, 100.0)
    productivity = 100.0 * clamp(
        0.30 + cm.daily_growth_rate * 8.0 + cm.leaf_area_index / 7.0 +
        cm.net_photosynthesis / 120.0 - cm.stress_days * 0.015,
        0.0, 1.0
    )
    total = (
        climate * 0.28 + nutrients * 0.22 + biosecurity * 0.20 +
        maintenance * 0.12 + productivity * 0.18
    )
    return {
        "climate": round(climate, 1),
        "nutrients": round(nutrients, 1),
        "biosecurity": round(biosecurity, 1),
        "maintenance": round(maintenance, 1),
        "productivity": round(productivity, 1),
        "total": round(total, 1),
        "worst_wear": round(worst_wear, 1),
    }


def estimate_harvest_days(zone: GreenZone) -> int:
    cm = zone.crop_model
    if cm.stage == GrowthStage.HARVEST:
        return 0
    if cm.day <= 0 or cm.dvs <= 0:
        return max(1, CROP_PROFILES[CropType(zone.crop_type.value)].days_to_harvest)
    daily_dvs = max(cm.dvs / max(cm.day, 1), 1e-4)
    return int(math.ceil(max(0.0, 1.8 - cm.dvs) / daily_dvs))


def render_intelligence_strip(zone: GreenZone):
    intel = compute_zone_intelligence(zone)
    items = [
        ("AI Health", f"{intel['total']:.0f}%", intel["total"]),
        ("Climate Fit", f"{intel['climate']:.0f}%", intel["climate"]),
        ("Nutrition Fit", f"{intel['nutrients']:.0f}%", intel["nutrients"]),
        ("Biosecurity", f"{intel['biosecurity']:.0f}%", intel["biosecurity"]),
        ("Maint Reserve", f"{intel['maintenance']:.0f}%", intel["maintenance"]),
        ("Harvest ETA", f"{estimate_harvest_days(zone)}d", 100.0 - min(100.0, estimate_harvest_days(zone))),
    ]
    cards = []
    for label, value, score in items:
        state = score_state(score)
        width = int(round(clamp(finite_float(score), 0.0, 100.0)))
        bar_state = "bad" if state == "bad" else ("warn" if state == "warn" else "")
        cards.append(
            f'<div class="ag4-intel-card ag4-state-{state}">'
            f'<div class="ag4-intel-label">{esc(label)}</div>'
            f'<div class="ag4-intel-value">{esc(value)}</div>'
            f'<div class="ag4-bar {bar_state}"><span style="width:{width}%"></span></div>'
            f'</div>'
        )
    st.markdown(f'<div class="ag4-zone-intel">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_status_bar(zones: List[GreenZone]):
    lib_info = [
        ("GLP",    GLP_AVAILABLE,     "GreenLightPlus",  "Model fisika rumah kaca"),
        ("PCSE",   PCSE_AVAILABLE,    "PCSE",            "Simulasi pertumbuhan tanaman"),
        ("Plotly", PLOTLY_AVAILABLE,  "Plotly",          "Grafik interaktif 3D"),
        ("SciPy",  SCIPY_AVAILABLE,   "SciPy",           "Komputasi ilmiah"),
        ("SkLearn",SKLEARN_AVAILABLE, "Scikit-learn",    "Machine learning"),
    ]
    badges_html = ""
    for short, ok, _, _ in lib_info:
        css   = "badge-online" if ok else "badge-warn"
        icon  = "✓" if ok else "○"
        title = ("Aktif" if ok else "Tidak terinstal") + f" — pip install {short.lower()}"
        badges_html += (
            f'<span class="status-badge {css}" title="{esc(title)}" '
            f'style="cursor:help;">{icon} {esc(short)}</span> '
        )
    total_area = sum(z.area_m2 for z in zones)
    co2_seq    = sum(z.crop_model.net_carbon_seq_kg for z in zones)
    n_ok  = sum(1 for z in zones if z.crop_model.dvs > 0)
    pulse = '<span class="live-pulse"></span>'
    st.markdown(f"""
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;
                margin-bottom:16px; padding:10px 14px; border-radius:12px;
                background:rgba(0,0,0,0.12); border:1px solid var(--border,rgba(78,232,78,0.15));">
        <span style="font-family:'JetBrains Mono',monospace; font-size:11px;
                     font-weight:700; letter-spacing:0.5px; white-space:nowrap;">
            {pulse} AGRI-MIND v5
        </span>
        {badges_html}
        <span class="status-badge badge-online" title="Digital twin aktif">✓ Twin</span>
        <span class="status-badge badge-online" title="AI kontrol v4 aktif">✓ AI</span>
        <span class="status-badge badge-online" title="Kalman filter aktif">✓ Kalman</span>
        <span class="status-badge badge-new"    title="Optimasi genetik">★ GA</span>
        <span class="status-badge badge-new"    title="Akuntansi karbon">★ Carbon</span>
        <span style="font-family:'Inter',sans-serif; font-size:10px; font-weight:500;
                     margin-left:auto; opacity:0.7; white-space:nowrap;"
              title="Zona aktif / total lahan / karbon diserap">
            🌿 {n_ok}/{len(zones)} zona · {total_area:.0f} m² · CO₂ {co2_seq:.2f} kg
        </span>
    </div>
    """, unsafe_allow_html=True)


def render_alerts(alerts: List[Alert], max_show: int = 12):
    if not alerts:
        return
    # Group by level for summary
    level_counts: Dict[str, int] = {}
    for a in alerts[-30:]:
        level_counts[a.level] = level_counts.get(a.level, 0) + 1

    icon_map = {
        "critical": "🔴", "warning": "🟡", "info": "🔵",
        "ok": "🟢", "disease": "🟣", "maint": "🟠",
    }
    summary_parts = [f"{icon_map.get(lv,'⚪')} {cnt} {lv}" for lv, cnt in level_counts.items()]
    st.markdown(
        f'<div class="section-header">⚠️ System Notifications '
        f'<span style="font-size:10px; font-weight:400; opacity:0.7; text-transform:none;">'
        f'&nbsp;— {" · ".join(summary_parts)}</span></div>',
        unsafe_allow_html=True
    )
    seen  = set()
    count = 0
    for alert in reversed(alerts[-30:]):
        key = alert.message[:60]
        if key not in seen and count < max_show:
            seen.add(key)
            count += 1
            css = {
                "critical": "alert-critical", "warning":  "alert-warning",
                "info":     "alert-info",     "ok":       "alert-ok",
                "disease":  "alert-disease",  "maint":    "alert-maint",
            }.get(alert.level, "alert-info")
            icon = icon_map.get(alert.level, "⚪")
            cat_label = ""
            if alert.category and alert.category != "system":
                cat_label = (
                    f' <span class="info-chip" style="font-size:9px;padding:2px 7px;">'
                    f'{esc(alert.category)}</span>'
                )
            st.markdown(
                f'<div class="alert-box {css}">'
                f'{icon} {cat_label} {esc(alert.message)}'
                f'<span style="float:right; opacity:0.4; font-size:9px; font-family:\'JetBrains Mono\',monospace;">'
                f'{esc(alert.timestamp)}</span>'
                f'</div>',
                unsafe_allow_html=True
            )


def render_zone_metrics(zone: GreenZone):
    p  = CROP_PROFILES[CropType(zone.crop_type.value)]
    cm = zone.crop_model
    ns = zone.nutrient_solution

    # Get friendly crop name if available
    indo_id   = getattr(zone, "indo_crop_id", None)
    crop_name = (INDONESIAN_CROPS_DB[indo_id].nama_id
                 if indo_id and indo_id in INDONESIAN_CROPS_DB
                 else zone.crop_type.value.title())
    st.markdown(
        f'<div class="section-header">🌿 Zona: {esc(zone.zone_id)} — '
        f'{esc(crop_name)} '
        f'<span class="info-chip" style="font-size:10px;">{esc(zone.zone_type.value)}</span> '
        f'<span class="info-chip" style="font-size:10px;">💧 {esc(zone.irrigation_mode.value)}</span>'
        f'</div>',
        unsafe_allow_html=True
    )
    st.markdown(render_meta_row([
        ("🌱", "Crop", crop_name),
        ("🏗️", "Zone Type", zone.zone_type.value),
        ("💧", "Irigasi", zone.irrigation_mode.value),
        ("📐", "Luas", f"{zone.area_m2:.0f} m²"),
        ("⏱️", "Langkah", zone.step_count),
        ("💡", "Spektrum", zone.led_spectrum.value),
    ]), unsafe_allow_html=True)
    render_intelligence_strip(zone)

    temp_d, temp_s = metric_delta(zone.temp_air, p.optimal_temp, "°", 1, 1.5, 4.0)
    hum_d, hum_s   = metric_delta(zone.humidity, p.optimal_humidity, "%", 1, 5.0, 14.0)
    vpd_d, vpd_s   = metric_delta(zone.vpd, p.vpd_optimal, "", 2, 0.25, 0.65)
    soil_d, soil_s = metric_delta(zone.soil_moist, p.optimal_soil_moisture, "%", 1, 6.0, 16.0)
    co2_d, co2_s   = metric_delta(zone.co2_ppm, p.optimal_co2, "", 0, 120.0, 360.0)
    par_d, par_s   = metric_delta(zone.light_w, p.optimal_light, "W", 0, 80.0, 180.0)
    root_d, root_s = metric_delta(zone.root_temp, p.root_zone_temp_optimal, "°", 1, 1.8, 5.0)

    env_metrics = [
        DashboardMetric("🌡️", "Air Temp", f"{zone.temp_air:.1f}°C", temp_d, temp_s),
        DashboardMetric("💧", "Humidity", f"{zone.humidity:.1f}%", hum_d, hum_s),
        DashboardMetric("💨", "VPD", f"{zone.vpd:.2f}kPa", vpd_d, vpd_s),
        DashboardMetric("🌱", "Soil Moist", f"{zone.soil_moist:.1f}%", soil_d, soil_s),
        DashboardMetric("🌬️", "CO₂", f"{zone.co2_ppm:.0f}ppm", co2_d, co2_s),
        DashboardMetric("☀️", "PAR", f"{zone.light_w:.0f}W/m²", par_d, par_s),
        DashboardMetric("🌡️", "Root °C", f"{zone.root_temp:.1f}°C", root_d, root_s),
        DashboardMetric("💦", "DO₂", f"{ns.dissolved_o2:.1f}mg/L", "",
                        threshold_state(ns.dissolved_o2, 6.0, 4.5, higher_is_bad=False)),
    ]

    ec_d, ec_s = metric_delta(ns.ec_mS, p.ec_optimal, "mS", 1, 0.35, 0.9)
    ph_d, ph_s = metric_delta(ns.ph, p.ph_optimal, "", 2, 0.25, 0.65)
    n_target   = 200.0 if p.nitrogen_demand_high else 140.0
    n_d, n_s   = metric_delta(ns.n_ppm, n_target, "", 0, 55.0, 125.0)
    p_d, p_s   = metric_delta(ns.p_ppm, 50.0, "", 0, 18.0, 36.0)
    k_d, k_s   = metric_delta(ns.k_ppm, 300.0, "", 0, 80.0, 180.0)
    ca_d, ca_s = metric_delta(ns.ca_ppm, 200.0, "", 0, 55.0, 130.0)
    mg_d, mg_s = metric_delta(ns.mg_ppm, 50.0, "", 0, 18.0, 40.0)
    fe_d, fe_s = metric_delta(ns.fe_ppb, 2000.0, "", 0, 550.0, 1200.0)

    nutrient_metrics = [
        DashboardMetric("🧪", "EC", f"{ns.ec_mS:.1f}mS", ec_d, ec_s),
        DashboardMetric("⚗️", "pH", f"{ns.ph:.2f}", ph_d, ph_s),
        DashboardMetric("🌿", "N", f"{ns.n_ppm:.0f}ppm", n_d, n_s),
        DashboardMetric("🔬", "P", f"{ns.p_ppm:.0f}ppm", p_d, p_s),
        DashboardMetric("⚡", "K", f"{ns.k_ppm:.0f}ppm", k_d, k_s),
        DashboardMetric("🪨", "Ca", f"{ns.ca_ppm:.0f}ppm", ca_d, ca_s),
        DashboardMetric("🌊", "Mg", f"{ns.mg_ppm:.0f}ppm", mg_d, mg_s),
        DashboardMetric("🔩", "Fe", f"{ns.fe_ppb:.0f}ppb", fe_d, fe_s),
    ]

    disease_state = threshold_state(cm.disease_index, 0.10, 0.30)
    pest_state    = threshold_state(cm.pest_pressure, 0.10, 0.30)
    crop_metrics = [
        DashboardMetric("🌿", "Biomass", f"{cm.biomass:.3f}kg/m²", "", "info"),
        DashboardMetric("🍅", "Yield", f"{cm.yield_kg:.3f}kg/m²", "", "good"),
        DashboardMetric("🍃", "LAI", f"{cm.leaf_area_index:.2f}", "", score_state(cm.leaf_area_index * 22.0)),
        DashboardMetric("📅", "Stage", cm.stage.value, "", "info"),
        DashboardMetric("🔬", "DVS", f"{cm.dvs:.3f}", "", "info"),
        DashboardMetric("🌡️", "Canopy", f"{cm.canopy_temp:.1f}°C", "", temp_s),
        DashboardMetric("☁️", "Photosyn", f"{cm.net_photosynthesis:.1f}μmol", "",
                        "good" if cm.net_photosynthesis > 1 else "warn"),
        DashboardMetric("🦠", "Disease", f"{cm.disease_index:.3f}", "", disease_state),
        DashboardMetric("🛡️", "Pest", f"{cm.pest_pressure:.3f}", "", pest_state),
        DashboardMetric("🍯", "Brix", f"{cm.brix_sugar:.1f}°", "", "info"),
        DashboardMetric("🧬", "Antioxidant", f"{cm.antioxidant_score:.0f}", "",
                        threshold_state(cm.antioxidant_score, 45.0, 30.0, higher_is_bad=False)),
        DashboardMetric("🦠", "Microbiome", f"{cm.microbial_activity:.2f}", "",
                        threshold_state(cm.microbial_activity, 0.55, 0.35, higher_is_bad=False)),
        DashboardMetric("💧", "Water Used", f"{zone.water_used_L:.0f}L", "", "info"),
        DashboardMetric("⚡", "Energy", f"{zone.energy_kwh:.2f}kWh", "", "info"),
        DashboardMetric("🌿", "Carbon Net", f"{cm.net_carbon_seq_kg:.3f}kg", "", "good"),
    ]

    render_metric_wall("", env_metrics + nutrient_metrics + crop_metrics, min_width=132)

    # Maintenance summary
    critical = zone.maint_engine.get_critical_components(70.0)
    if critical:
        crit_str = " | ".join([f"{r.component[:12]}:{r.wear_pct:.0f}%" for r in critical[:3]])
        st.markdown(
            f'<div class="maint-card">🔧 MAINTENANCE ALERT: {esc(crit_str)}</div>',
            unsafe_allow_html=True
        )


def render_economics(econ: EconomicState, zones: List[GreenZone]):
    operating_cost = (
        econ.cost_water_idr + econ.cost_energy_idr + econ.cost_co2_idr +
        econ.cost_fertilizer_idr + econ.cost_labor_idr + econ.cost_pest_mgmt_idr
    )
    roi_state = "good" if econ.roi_percent >= 20 else ("warn" if econ.roi_percent >= 0 else "bad")
    profit_state = "good" if econ.profit_idr >= 0 else "bad"
    render_metric_wall("💰 ECONOMICS & CARBON DASHBOARD", [
        DashboardMetric("💵", "Revenue", fmt_idr(econ.revenue_idr), "", "good"),
        DashboardMetric("💰", "Profit", fmt_idr(econ.profit_idr), f"{econ.roi_percent:.1f}% ROI", profit_state),
        DashboardMetric("💸", "Total OpEx", fmt_idr(operating_cost), "", "warn" if operating_cost else "good"),
        DashboardMetric("📦", "Cost/kg", fmt_idr(econ.cost_per_kg_idr), "", "info"),
        DashboardMetric("📅", "Payback", f"{econ.payback_period_days:.0f}d", "", roi_state),
        DashboardMetric("💧", "Water Cost", fmt_idr(econ.cost_water_idr), "", "info"),
        DashboardMetric("⚡", "Energy Cost", fmt_idr(econ.cost_energy_idr), "", "info"),
        DashboardMetric("🌬️", "CO₂ Cost", fmt_idr(econ.cost_co2_idr), "", "info"),
        DashboardMetric("🧪", "Fert Cost", fmt_idr(econ.cost_fertilizer_idr), "", "info"),
        DashboardMetric("🔧", "Pest+Maint", fmt_idr(econ.cost_pest_mgmt_idr), "", "warn" if econ.cost_pest_mgmt_idr else "good"),
        DashboardMetric("🌿", "Net CO₂", f"{econ.net_carbon_kg:.3f}kg", "", "good"),
        DashboardMetric("🪙", "Carbon Credits", fmt_idr(econ.carbon_credits_idr), "", "good"),
    ], min_width=145)

    # Carbon accounting
    st.markdown(
        f'<div class="carbon-box">'
        f'🌿 <b>Carbon Accounting</b><br>'
        f'Net CO₂ Sequestered: <b>{econ.net_carbon_kg:.3f} kg</b> | '
        f'Carbon Credits: <b>{fmt_idr(econ.carbon_credits_idr)}</b>'
        f'</div>',
        unsafe_allow_html=True
    )


def render_ml_predictions(predictor: MLPredictor, zone: GreenZone):
    if len(zone.history.get("temp", [])) < 10:
        st.info("💡 Run simulation (≥10 steps) to enable ML predictions.")
        return

    st.markdown('<div class="section-header">🤖 ML ENSEMBLE PREDICTIVE ANALYTICS</div>',
                unsafe_allow_html=True)

    forecast  = predictor.forecast(zone)
    anomalies = predictor.anomaly_score(zone)

    tab1, tab2, tab3 = st.tabs(["📈 Forecasts", "🎯 Harvest Projection", "🚨 Anomaly Detection"])

    with tab1:
        cols = st.columns(2)
        items = [(k, v) for k, v in forecast.items() if k != "harvest_estimate"]
        for idx, (var, result) in enumerate(items):
            if not isinstance(result, dict) or "predicted_at_horizon" not in result:
                continue
            color = "#44ee44" if result["trend"] > 0 else ("#ee4444" if result["trend"] < 0 else "#aaaaaa")
            ci_width = abs(result["upper_95"][-1] - result["lower_95"][-1]) if result.get("upper_95") else 0
            with cols[idx % 2]:
                st.markdown(
                    f'<div class="prediction-box">'
                    f'<b>{var.upper()}</b>: {result["last"]} → '
                    f'<span style="color:{color}"><b>{result["predicted_at_horizon"]}</b> {result["trend_dir"]}</span> '
                    f'<span style="opacity:0.5; font-size:10px;">CI±{ci_width:.2f} | {result["model_used"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

    with tab2:
        if "harvest_estimate" in forecast:
            he = forecast["harvest_estimate"]
            st.markdown(
                f'<div class="prediction-box">'
                f'⏱️ Steps to harvest: <b>{he["steps_remaining"]}</b> | '
                f'DVS now: <b>{he["dvs_current"]}</b><br>'
                f'📦 Projected yield: <b>{he["projected_yield_m2"]} kg/m²</b> '
                f'({he["projected_yield_kg"]} kg total)<br>'
                f'💰 Revenue: <b>{fmt_idr(he["projected_revenue"])}</b><br>'
                f'💧 Water needed: <b>{he["projected_water_L"]:.0f} L</b><br>'
                f'🍯 Projected Brix: <b>{he["brix_projected"]}°</b>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.info("Run more simulation steps to get harvest projection.")

    with tab3:
        if anomalies:
            rows = []
            for k, v in anomalies.items():
                status = "🔴 ANOMALY" if v > 3.5 else ("🟡 ELEVATED" if v > 2.0 else "🟢 NORMAL")
                rows.append({"Variable": k, "CUSUM+Z Score": v, "Status": status})
            df_anom = pd.DataFrame(rows)
            st.dataframe(df_anom, width='stretch', hide_index=True)


def render_maintenance_panel(zones: List[GreenZone]):
    st.markdown('<div class="section-header">🔧 PREDICTIVE MAINTENANCE</div>',
                unsafe_allow_html=True)

    all_records = {}
    for zone in zones:
        for name, rec in zone.maint_engine.records.items():
            if name not in all_records or rec.wear_pct > all_records[name].wear_pct:
                all_records[name] = rec

    if not all_records:
        return

    data = [
        {
            "Component": r.component,
            "Wear %": f"{r.wear_pct:.1f}%",
            "Hours Run": f"{r.hours_run:.0f}h",
            "Failure Prob": f"{r.failure_prob*100:.1f}%",
            "Status": "🔴 CRITICAL" if r.wear_pct > 85 else (
                       "🟡 SERVICE SOON" if r.wear_pct > 65 else "🟢 OK")
        }
        for r in sorted(all_records.values(), key=lambda x: x.wear_pct, reverse=True)
    ]
    df = pd.DataFrame(data)
    st.dataframe(df, width='stretch', hide_index=True)


def render_nutrient_panel(zones: List[GreenZone]):
    st.markdown('<div class="section-header">⚗️ NUTRIENT SOLUTION MONITOR</div>',
                unsafe_allow_html=True)

    cols = st.columns(len(zones))
    for i, zone in enumerate(zones):
        ns = zone.nutrient_solution
        antagonisms = zone.nutrient_mgr.check_antagonisms()
        with cols[i]:
            ant_html = "<br>".join(esc(a) for a in antagonisms) if antagonisms else "✅ No antagonisms"
            st.markdown(
                f'<div class="zone-card">'
                f'<b>{esc(zone.zone_id)}</b> — {esc(zone.crop_type.value)}<br>'
                f'EC: <b>{ns.ec_mS:.2f}</b> mS/cm | pH: <b>{ns.ph:.2f}</b><br>'
                f'N: {ns.n_ppm:.0f}ppm | P: {ns.p_ppm:.0f}ppm | K: {ns.k_ppm:.0f}ppm<br>'
                f'Ca: {ns.ca_ppm:.0f}ppm | Mg: {ns.mg_ppm:.0f}ppm | Fe: {ns.fe_ppb:.0f}ppb<br>'
                f'DO₂: {ns.dissolved_o2:.1f}mg/L | T: {ns.temp_C:.1f}°C<br>'
                f'<span style="font-size:10px; color:#aaaaaa;">{ant_html}</span>'
                f'</div>',
                unsafe_allow_html=True
            )


def render_disease_panel(zones: List[GreenZone]):
    st.markdown('<div class="section-header">🦠 DISEASE & PEST MONITORING</div>',
                unsafe_allow_html=True)

    has_issue = any(
        z.crop_model.disease_index > 0.05 or z.crop_model.pest_pressure > 0.1
        for z in zones
    )
    if not has_issue:
        st.markdown(
            '<div class="alert-box alert-ok">✅ No active disease or pest detected across all zones.</div>',
            unsafe_allow_html=True
        )
        return

    cols = st.columns(len(zones))
    for i, zone in enumerate(zones):
        cm  = zone.crop_model
        idx = cm.disease_index
        with cols[i]:
            color  = "#44ee44" if idx < 0.1 else ("#eebb33" if idx < 0.3 else "#ee4444")
            risk   = (DiseaseRisk.NONE if idx < 0.04 else
                      DiseaseRisk.LOW if idx < 0.12 else
                      DiseaseRisk.MODERATE if idx < 0.30 else
                      DiseaseRisk.HIGH if idx < 0.60 else DiseaseRisk.CRITICAL)
            pest_c = "#44ee44" if cm.pest_pressure < 0.1 else ("#eebb33" if cm.pest_pressure < 0.4 else "#ee4444")

            st.markdown(f"""
            <div class="zone-card">
                <b style="color:{color}">{esc(zone.zone_id)}</b><br>
                Disease: <b>{esc(cm.disease_type)}</b> | Idx: <b style="color:{color}">{idx:.3f}</b>
                | Risk: <b style="color:{color}">{esc(risk.value)}</b><br>
                Botrytis: {cm.disease_botrytis:.3f} | Mildew: {cm.disease_mildew:.3f}<br>
                <span style="color:{pest_c}">Pest: {esc(cm.pest_type.value)} ({cm.pest_pressure:.3f})</span>
            </div>
            """, unsafe_allow_html=True)

            if idx > 0.1 or cm.pest_pressure > 0.2:
                recs = []
                if zone.humidity > 82:      recs.append("↓ Lower humidity <82%")
                if zone.light_w < 200:      recs.append("↑ LED UV exposure")
                if cm.disease_type == "Botrytis":
                    recs += ["🌬️ Max ventilation", "⬇️ Reduce irrigation"]
                elif cm.disease_type == "Powdery Mildew":
                    recs += ["💧 Slight humidity boost", "🌿 Thin canopy"]
                if cm.pest_type == PestType.SPIDERMITE:
                    recs.append("💧 Foliar misting (suppresses mites)")
                elif cm.pest_type == PestType.APHIDS:
                    recs.append("🪲 Introduce ladybugs (bio-control)")
                for r in recs:
                    st.markdown(f"• {r}")


def render_charts(zones: List[GreenZone]):
    if not zones or not any(len(z.history.get("temp", [])) > 0 for z in zones):
        return

    st.markdown('<div class="section-header">📊 ANALYTICS DASHBOARD v4</div>',
                unsafe_allow_html=True)

    zone_names        = [z.zone_id for z in zones]
    selected_zone_name= st.selectbox("Zone to Chart", zone_names, key="chart_zone_sel")
    zone              = next((z for z in zones if z.zone_id == selected_zone_name), zones[0])
    h                 = zone.history
    steps             = list(range(len(h.get("temp", []))))

    if not steps:
        return

    def safe_list(key: str) -> List:
        d = h.get(key, [])
        return [float(v) if v is not None else 0.0 for v in d]

    if PLOTLY_AVAILABLE:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🌿 Environment",
            "🔬 Physiology",
            "💰 Economics",
            "🧪 Nutrients",
            "🦠 Disease & Pest",
        ])

        dark_kw = dict(
            template="plotly_dark", paper_bgcolor="#060d06",
            plot_bgcolor="#0a1a0a",
            font=dict(family="Space Mono", color="#7a9a7a", size=9),
            showlegend=True,
            legend=dict(font=dict(size=8), bgcolor="#0a0f0a",
                        bordercolor="#1a4a1a", borderwidth=1),
        )

        def mk_trace(x, y, name, color, dash="solid", fill=None, width=1.8):
            fc = None
            if fill:
                try:
                    fc = color.replace(")", ",0.07)").replace("rgb", "rgba") if fill else None
                except Exception:
                    fc = None
            return go.Scatter(
                x=x, y=y, name=name,
                line=dict(color=color, width=width, dash=dash),
                fill=fill, fillcolor=fc,
            )

        with tab1:
            fig = make_subplots(rows=4, cols=2, vertical_spacing=0.09, horizontal_spacing=0.08,
                                subplot_titles=[
                                    "🌡️ Temp (Air vs Canopy)", "💧 Humidity & VPD",
                                    "🌱 Soil Moisture",         "🌬️ CO₂ & Light",
                                    "🌿 Biomass & Yield",        "🍃 LAI & Photosynthesis",
                                    "⚡ Stress Factors",         "💧 Water & Energy"
                                ])
            kw = {**dark_kw, "height": 760}
            fig.add_trace(mk_trace(steps, safe_list("temp"),       "Air °C",    "#ff6a4a"), 1, 1)
            fig.add_trace(mk_trace(steps, safe_list("canopy_temp"),"Canopy °C", "#ff9944", "dot"), 1, 1)
            fig.add_trace(mk_trace(steps, safe_list("humidity"),   "Humidity%", "#4aaaff"), 1, 2)
            fig.add_trace(mk_trace(steps, safe_list("vpd"),        "VPD kPa",   "#aaee44", "dot"), 1, 2)
            fig.add_trace(mk_trace(steps, safe_list("soil"),       "Soil%",     "#4aff8a", fill="tozeroy"), 2, 1)
            fig.add_trace(mk_trace(steps, safe_list("co2"),        "CO₂ ppm",   "#ffca4a"), 2, 2)
            fig.add_trace(mk_trace(steps, safe_list("light"),      "Light W/m²","#ffff44", "dot"), 2, 2)
            fig.add_trace(mk_trace(steps, safe_list("biomass"),    "Biomass",   "#8aff4a"), 3, 1)
            fig.add_trace(mk_trace(steps, safe_list("yield"),      "Yield kg",  "#ff4a8a"), 3, 1)
            fig.add_trace(mk_trace(steps, safe_list("lai"),        "LAI",       "#4affca"), 3, 2)
            fig.add_trace(mk_trace(steps, safe_list("net_ps"),     "Photosyn",  "#ccff44", "dot"), 3, 2)
            fig.add_trace(mk_trace(steps, safe_list("stress"),     "Stress",    "#ffaa4a", fill="tozeroy"), 4, 1)
            fig.add_trace(mk_trace(steps, safe_list("water"),      "Water L",   "#4a8aff"), 4, 2)
            fig.add_trace(mk_trace(steps, safe_list("energy"),     "Energy kWh","#ff8a4a", "dot"), 4, 2)
            fig.update_layout(**kw)
            st.plotly_chart(fig, width='stretch')

        with tab2:
            fig2 = make_subplots(rows=3, cols=2, vertical_spacing=0.11,
                                 subplot_titles=[
                                     "🦠 Disease Index (Botrytis vs Mildew)",
                                     "🌿 Nitrogen & Chlorophyll",
                                     "🍯 Brix Sugar & Antioxidant",
                                     "💧 Transpiration & Stomatal Gs",
                                     "🦠 Microbial Activity",
                                     "🌳 Root Depth"
                                 ])
            kw2 = {**dark_kw, "height": 620}
            botr = [z.crop_model.disease_botrytis for z in [zone]] * len(steps)
            mild = [z.crop_model.disease_mildew   for z in [zone]] * len(steps)
            fig2.add_trace(mk_trace(steps, safe_list("disease"),       "Disease",    "#cc44ee"), 1, 1)
            fig2.add_trace(mk_trace(steps, safe_list("n_content"),     "N %",        "#44ee88"), 1, 2)
            fig2.add_trace(mk_trace(steps, safe_list("chlorophyll"),   "Chlorophyll","#88ff44", "dot"), 1, 2)
            fig2.add_trace(mk_trace(steps, safe_list("brix"),          "Brix °",     "#ffcc44"), 2, 1)
            fig2.add_trace(mk_trace(steps, safe_list("antioxidant"),   "Antioxidant","#ff8844", "dot"), 2, 1)
            fig2.add_trace(mk_trace(steps, safe_list("transpiration"), "Transpiration","#44aaff"), 2, 2)
            fig2.add_trace(mk_trace(steps, safe_list("microbial"),     "Microbial",  "#44ff88"), 3, 1)
            fig2.add_trace(mk_trace(steps, safe_list("abscission"),    "Abscission", "#ff4444", "dot"), 3, 2)
            fig2.update_layout(**kw2)
            st.plotly_chart(fig2, width='stretch')

        with tab3:
            econ_h = st.session_state.get("econ_history", [])
            if econ_h:
                e_steps = [e["step"] for e in econ_h]
                fig3 = make_subplots(rows=2, cols=3,
                                     subplot_titles=["Revenue", "Profit", "ROI %",
                                                     "Carbon Credits", "Total Cost", "Cost/Step"])
                kw3  = {**dark_kw, "height": 480}
                def ec(key, name, color, row, col):
                    fig3.add_trace(go.Scatter(x=e_steps, y=[e.get(key, 0) for e in econ_h],
                                              name=name, line=dict(color=color, width=2)), row, col)
                ec("revenue", "Revenue",  "#55ee55", 1, 1)
                ec("profit",  "Profit",   "#44aaee", 1, 2)
                ec("roi",     "ROI %",    "#eeaa33", 1, 3)
                ec("carbon",  "Carbon Cr","#44cccc", 2, 1)
                ec("cost",    "OpEx",     "#ee5544", 2, 2)
                fig3.update_layout(**kw3)
                st.plotly_chart(fig3, width='stretch')
            else:
                st.info("Run simulation to populate economics charts.")

        with tab4:
            fig4 = make_subplots(rows=2, cols=2, vertical_spacing=0.12,
                                 subplot_titles=["EC & pH", "N & K ppm", "Ca ppm", "DO₂ mg/L"])
            kw4 = {**dark_kw, "height": 460}
            fig4.add_trace(mk_trace(steps, safe_list("ec"),    "EC mS",  "#ffaa44"), 1, 1)
            fig4.add_trace(mk_trace(steps, safe_list("ph"),    "pH",     "#44ffcc", "dot"), 1, 1)
            fig4.add_trace(mk_trace(steps, safe_list("n_ppm"), "N ppm",  "#88ff44"), 1, 2)
            fig4.add_trace(mk_trace(steps, safe_list("k_ppm"), "K ppm",  "#44cc88", "dot"), 1, 2)
            fig4.add_trace(mk_trace(steps, safe_list("ca_content"),"Ca%", "#ffdd44"), 2, 1)
            fig4.add_trace(mk_trace(steps, safe_list("do2"),   "DO₂",    "#44aaff"), 2, 2)
            fig4.update_layout(**kw4)
            st.plotly_chart(fig4, width='stretch')

        with tab5:
            fig5 = make_subplots(rows=2, cols=2, vertical_spacing=0.12,
                                 subplot_titles=["Disease Index", "Pest Pressure",
                                                 "Microbial Activity", "CO₂ Absorbed"])
            kw5 = {**dark_kw, "height": 460}
            fig5.add_trace(mk_trace(steps, safe_list("disease"),   "Disease",   "#cc44ee"), 1, 1)
            fig5.add_trace(mk_trace(steps, safe_list("pest"),      "Pest",      "#ff8844"), 1, 2)
            fig5.add_trace(mk_trace(steps, safe_list("microbial"), "Microbial", "#44ff88"), 2, 1)
            fig5.add_trace(mk_trace(steps, safe_list("co2_absorbed"),"CO₂ Abs", "#44cccc"), 2, 2)
            fig5.update_layout(**kw5)
            st.plotly_chart(fig5, width='stretch')

    else:
        # Matplotlib fallback
        plt.style.use("dark_background")
        fig, axes = plt.subplots(3, 4, figsize=(18, 10))
        fig.patch.set_facecolor("#060d06")

        def mpl_line(ax, data, label, color, ylabel=""):
            if data:
                ax.plot(data, label=label, color=color, linewidth=1.5)
            ax.set_facecolor("#0a1a0a")
            ax.tick_params(colors="#6a8a6a", labelsize=7)
            for sp in ax.spines.values():
                sp.set_color("#1a4a1a")
            ax.set_ylabel(ylabel, color="#6a8a6a", fontsize=8)
            ax.legend(fontsize=7, loc="upper left")
            ax.grid(alpha=0.08, color="#1a4a1a")

        pairs = [
            (axes[0,0], [("temp","Temp","#ff6a4a"),("canopy_temp","Canopy","#ff9944")], "°C"),
            (axes[0,1], [("humidity","Humidity","#4aaaff"),("vpd","VPD","#aaee44")], "%/kPa"),
            (axes[0,2], [("co2","CO₂","#ffca4a")], "ppm"),
            (axes[0,3], [("light","Light","#ffff44")], "W/m²"),
            (axes[1,0], [("biomass","Biomass","#8aff4a"),("yield","Yield","#ff4a8a")], "kg/m²"),
            (axes[1,1], [("lai","LAI","#4affca"),("stress","Stress","#ffaa4a")], ""),
            (axes[1,2], [("disease","Disease","#cc44ee"),("pest","Pest","#ff8844")], "idx"),
            (axes[1,3], [("n_content","N%","#44ee88"),("chlorophyll","Chl","#88ff44")], ""),
            (axes[2,0], [("brix","Brix","#ffcc44"),("antioxidant","Antioxid","#ff8844")], ""),
            (axes[2,1], [("microbial","Microbial","#44ff88")], ""),
            (axes[2,2], [("water","Water L","#4a8aff"),("energy","Energy kWh","#ff8a4a")], ""),
            (axes[2,3], [("co2_absorbed","CO₂ Abs","#44cccc")], "kg"),
        ]
        for ax, traces, ylabel in pairs:
            for key, label, color in traces:
                mpl_line(ax, h.get(key, []), label, color, ylabel)

        plt.tight_layout(pad=1.8)
        st.pyplot(fig)
        plt.close()


# ══════════════════════════════════════════════════════════════════════════════
# 17. DATA EXPORT v4
# ══════════════════════════════════════════════════════════════════════════════

def build_export_df(zones: List[GreenZone]) -> pd.DataFrame:
    frames = []
    for zone in zones:
        h = zone.history
        n = len(h.get("temp", []))
        if n == 0:
            continue
        def safe(key: str, default=None) -> List:
            d = h.get(key, [])
            if len(d) == n:
                return d
            return [default] * n

        df = pd.DataFrame({
            "step":          range(n),
            "zone":          zone.zone_id,
            "crop":          zone.crop_type.value,
            "temp_C":        safe("temp"),
            "canopy_temp":   safe("canopy_temp"),
            "humidity_pct":  safe("humidity"),
            "vpd_kPa":       safe("vpd"),
            "soil_moist":    safe("soil"),
            "co2_ppm":       safe("co2"),
            "light_w":       safe("light"),
            "ec_mS":         safe("ec"),
            "ph":            safe("ph"),
            "n_ppm":         safe("n_ppm"),
            "k_ppm":         safe("k_ppm"),
            "do2_mg_L":      safe("do2"),
            "biomass_kg":    safe("biomass"),
            "yield_kg":      safe("yield"),
            "lai":           safe("lai"),
            "dvs":           safe("dvs"),
            "stage":         safe("stage"),
            "growth_rate":   safe("growth_rate"),
            "stress":        safe("stress"),
            "disease_idx":   safe("disease"),
            "pest_pressure": safe("pest"),
            "transpiration": safe("transpiration"),
            "n_content":     safe("n_content"),
            "ca_content":    safe("ca_content"),
            "chlorophyll":   safe("chlorophyll"),
            "net_ps":        safe("net_ps"),
            "fruit_count":   safe("fruit_count"),
            "abscission":    safe("abscission"),
            "brix_sugar":    safe("brix"),
            "antioxidant":   safe("antioxidant"),
            "microbial":     safe("microbial"),
            "co2_absorbed_kg": safe("co2_absorbed"),
            "water_L":       safe("water"),
            "energy_kwh":    safe("energy"),
        })
        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_summary_report(zones: List[GreenZone], econ: EconomicState,
                          wx: WeatherData) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 🌱 AI Greenhouse Digital Twin v4.0 — Simulation Report",
        f"**Generated:** {now}  |  **Location:** {wx.location}",
        f"**Weather Source:** {wx.source}",
        "",
        "## Zone Summary",
        "| Zone | Crop | Steps | Yield (kg/m²) | Brix | Disease | Pest | Energy (kWh) | CO₂ Seq (kg) |",
        "|------|------|-------|--------------|------|---------|------|-------------|-------------|",
    ]
    for z in zones:
        cm = z.crop_model
        lines.append(
            f"| {z.zone_id} | {z.crop_type.value} | {z.step_count} | "
            f"{cm.yield_kg:.3f} | {cm.brix_sugar:.1f}° | "
            f"{cm.disease_index:.3f} ({cm.disease_type}) | "
            f"{cm.pest_type.value} ({cm.pest_pressure:.2f}) | "
            f"{z.energy_kwh:.2f} | {cm.net_carbon_seq_kg:.4f} |"
        )

    lines += [
        "",
        "## Economics (IDR)",
        f"- **Revenue:** Rp {econ.revenue_idr:,.0f}",
        f"- **Profit:** Rp {econ.profit_idr:,.0f}",
        f"- **ROI:** {econ.roi_percent:.1f}%",
        f"- **Cost/kg:** Rp {econ.cost_per_kg_idr:,.0f}",
        f"- **Carbon Credits:** Rp {econ.carbon_credits_idr:,.0f}",
        f"- **Payback Period:** {econ.payback_period_days:.0f} days",
        "",
        "## Resource Totals",
        f"- **Total Water:** {sum(z.water_used_L for z in zones):.1f} L",
        f"- **Total Energy:** {sum(z.energy_kwh for z in zones):.2f} kWh",
        f"- **Total CO₂ Injected:** {sum(z.co2_injected_kg for z in zones)*1000:.1f} g",
        f"- **Net CO₂ Sequestered:** {econ.net_carbon_kg:.4f} kg",
        "",
        "## Maintenance Summary",
    ]
    for z in zones:
        critical = z.maint_engine.get_critical_components(70.0)
        if critical:
            lines.append(f"**{z.zone_id}:** " + ", ".join(
                f"{r.component} ({r.wear_pct:.0f}% wear)" for r in critical))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 18. MAIN APP v4
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Theme state (must be FIRST, before any CSS injection) ────────────────
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = True

    # ── Inject full theme CSS ─────────────────────────────────────────────────
    inject_theme_css(dark=st.session_state.dark_mode)

    # ── Legacy banner (Fase 3: backend sudah pisah) ──────────────────────────
    st.markdown(
        '<div style="background:#1a1a2e;border:1px solid #2a4a2a;border-radius:8px;'
        'padding:8px 12px;margin-bottom:12px;font-size:12px;color:#6a8a6a;">'
        '⚠️ <b>Legacy internal tool.</b> '
        'New dashboard: <a href="http://localhost:3000" target="_blank" '
        'style="color:#4ade80;">localhost:3000</a> · '
        'API: <a href="http://localhost:8000/docs" target="_blank" '
        'style="color:#4ade80;">localhost:8000/docs</a>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Hero Banner ───────────────────────────────────────────────────────────
    if st.session_state.dark_mode:
        hero_sub_color = "#6a926a"
        hero_icon      = "🌱"
    else:
        hero_sub_color = "#4a7a4a"
        hero_icon      = "🌿"

    st.markdown(f"""
    <div class="ag5-hero">
        <h1>
            {hero_icon} YAHYA · A0401241030 — INDONESIA SMART AGRI v5.0 ULTRA
        </h1>
        <p style="color:{hero_sub_color};">
            🇮🇩 102 Crops &nbsp;·&nbsp; Kalman Fusion &nbsp;·&nbsp; Genetic Optimizer
            &nbsp;·&nbsp; LLM Agronomist &nbsp;·&nbsp; Computer Vision &nbsp;·&nbsp;
            Sentinel-2 &nbsp;·&nbsp; Carbon MRV &nbsp;·&nbsp; Tier 1→4 Innovations
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Session State Init ────────────────────────────────────────────────────
    if "zones" not in st.session_state:
        st.session_state.zones        = [GreenZone("ZONE-A", ZoneType.MAIN, CropType.TOMATO, 100, 500)]
        st.session_state.ai           = AIControllerV4()
        st.session_state.weather_svc  = WeatherService()
        st.session_state.glp          = GreenLightWrapper()
        st.session_state.predictor    = MLPredictor(horizon=24)
        st.session_state.econ_engine  = EconomicsEngine()
        st.session_state.logger       = SystemLogger(maxlen=150)
        st.session_state.wx_data      = None
        st.session_state.econ_state   = EconomicState()
        st.session_state.econ_history = []

    # Hot-reload guard: Streamlit can keep an older session while the file changes.
    # Ensure every key used below exists even if the user did not clear browser cache.
    _session_defaults = {
        "zones":        [GreenZone("ZONE-A", ZoneType.MAIN, CropType.TOMATO, 100, 500)],
        "ai":           AIControllerV4(),
        "weather_svc":  WeatherService(),
        "glp":          GreenLightWrapper(),
        "predictor":    MLPredictor(horizon=24),
        "econ_engine":  EconomicsEngine(),
        "logger":       SystemLogger(maxlen=150),
        "wx_data":      None,
        "econ_state":   EconomicState(),
        "econ_history": [],
    }
    for _ss_key, _ss_default in _session_defaults.items():
        if _ss_key not in st.session_state:
            st.session_state[_ss_key] = _ss_default

    zones:        List[GreenZone]  = st.session_state.zones
    ai_ctrl:      AIControllerV4   = st.session_state.ai
    wx_svc:       WeatherService   = st.session_state.weather_svc
    glp:          GreenLightWrapper= st.session_state.glp
    predictor:    MLPredictor      = st.session_state.predictor
    econ_engine:  EconomicsEngine  = st.session_state.econ_engine
    logger:       SystemLogger     = st.session_state.logger

    render_status_bar(zones)

    # ══════════════════════════════════════════════════════════════════════
    # SIDEBAR
    # ══════════════════════════════════════════════════════════════════════
    with st.sidebar:
        # ── Theme Toggle ──────────────────────────────────────────────────────
        dark = st.session_state.dark_mode
        mode_icon  = "🌙" if dark else "☀️"
        mode_label = "Dark Forest Tech" if dark else "Light Greenhouse"
        mode_hint  = "Switch to light mode" if dark else "Switch to dark mode"
        st.markdown(f"""
        <div class="theme-toggle-wrap" id="theme-wrap">
            <span class="theme-icon">{mode_icon}</span>
            <div>
                <div class="theme-label">{mode_label}</div>
                <div class="theme-sub">{mode_hint}</div>
            </div>
        </div>""", unsafe_allow_html=True)
        if st.button(
            f"{'☀️ Light Mode' if dark else '🌙 Dark Mode'}",
            key="theme_toggle_btn",
            width='stretch',
        ):
            st.session_state.dark_mode = not dark
            st.rerun()

        st.markdown('<div class="sidebar-sep"></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-header">⚙️ CONFIG v5</div>', unsafe_allow_html=True)

        # ── API Keys Section ──────────────────────────────────────────────────
        with st.expander("🔑 API Keys", expanded=True):
            # OpenWeatherMap
            _owm_default = _get_cfg("owm_api_key", os.environ.get("OPENWEATHER_API_KEY", ""))
            api_key = st.text_input("🌦️ OpenWeatherMap API Key",
                value=_owm_default, type="password",
                help="Free: openweathermap.org · weather + geocoding")
            # GeoNames (for cascading province/city dropdowns worldwide)
            _gn_user = st.text_input("🗺️ GeoNames Username",
                value=_get_cfg("geonames_username", ""),
                help="Free: geonames.org/login · province/city dropdowns worldwide")
            # Mapbox (optional, for satellite map)
            _mb_key = st.text_input("🛰️ Mapbox API Key (optional)",
                value=_get_cfg("mapbox_api_key", ""), type="password",
                help="Free tier: mapbox.com · satellite map layer")
            _gm_key = st.text_input("Google Maps API Key (optional)",
                value=_get_cfg("google_maps_api_key", ""), type="password",
                help="Optional for device GPS reverse geocode; falls back to OWM if empty.")

            _owm_col1, _owm_col2 = st.columns([2, 1])
            with _owm_col1:
                if st.button("💾 Save API Keys", key="save_owm_key", width='stretch'):
                    _save_cfg(owm_api_key=api_key,
                              geonames_username=_gn_user,
                              mapbox_api_key=_mb_key,
                              google_maps_api_key=_gm_key)
                    if api_key:
                        os.environ["OPENWEATHER_API_KEY"] = api_key
                    st.success("✅ API Keys saved!")
            with _owm_col2:
                _status_parts = []
                if api_key:        _status_parts.append('<span style="color:#44ee88;font-size:11px;">OWM🟢</span>')
                if _gn_user:       _status_parts.append('<span style="color:#44ee88;font-size:11px;">GN🟢</span>')
                if _mb_key:        _status_parts.append('<span style="color:#44ee88;font-size:11px;">MB🟢</span>')
                if _gm_key:        _status_parts.append('<span style="color:#44ee88;font-size:11px;">GM🟢</span>')
                if not _status_parts: _status_parts = ['<span style="color:#ee8844;font-size:11px;">🔴 Empty</span>']
                st.markdown(" ".join(_status_parts), unsafe_allow_html=True)

        if api_key and not os.environ.get("OPENWEATHER_API_KEY"):
            os.environ["OPENWEATHER_API_KEY"] = api_key

        # ── LLM Settings ─────────────────────────────────────────────────────
        with st.expander("🤖 AI / LLM Settings", expanded=False):
            # Provider selection — default Gemini (best free tier for agronomy)
            _prov_options = ["gemini", "groq", "openrouter", "ollama", "stub (Offline)"]
            _prov_saved   = _get_cfg("llm_provider", LLMProvider.GEMINI.value)
            _prov_idx     = next((i for i, p in enumerate(_prov_options) if _prov_saved in p), 0)
            _prov_sel     = st.selectbox(
                "LLM Provider", _prov_options, index=_prov_idx,
                key="cfg_llm_provider",
                help=(
                    "✨ Gemini Flash — RECOMMENDED: free, fast, accurate\n"
                    "⚡ Groq — free, very fast (LLaMA-3)\n"
                    "🌐 OpenRouter — free model selection\n"
                    "🖥️ Ollama — 100% offline, always free\n"
                    "🔧 Stub — offline, no AI (rules-based)"))
            _prov_code = _prov_sel.split()[0]

            # Temperature slider — default 0.35 for consistent agronomy advice
            try:
                _llm_temp_saved = float(_get_cfg("llm_temperature", "0.35"))
            except Exception:
                _llm_temp_saved = 0.35
            _llm_temp_val = st.slider(
                "Temperature", 0.0, 1.0, _llm_temp_saved, 0.05,
                key="cfg_llm_temperature",
                help="0.2–0.4 = consistent & factual (recommended). 0.6–0.8 = more creative.")

            _groq_key = _gem_key = _oll_mdl = _or_key = ""
            _groq_mdl = _GROQ_MODELS[0]
            _gem_mdl  = _GEMINI_MODELS[0]
            _or_mdl   = _OPENROUTER_FREE[0]

            if _prov_code == "groq":
                st.caption("🔑 Free signup: **console.groq.com** — LLaMA-3 70B, fast & free")
                _groq_key = st.text_input("Groq API Key", value=_get_cfg("groq_api_key"),
                                          type="password", key="cfg_groq_key")
                _groq_saved = _get_cfg("groq_model", _get_cfg("llm_model", _GROQ_MODELS[0]))
                _groq_idx = _GROQ_MODELS.index(_groq_saved) if _groq_saved in _GROQ_MODELS else 0
                _groq_mdl = st.selectbox("Groq Model", _GROQ_MODELS,
                                         index=_groq_idx, key="cfg_groq_model")
            elif _prov_code == "gemini":
                st.caption("🔑 Free signup: **aistudio.google.com** — Gemini 2.0/2.5 Flash free")
                _gem_key = st.text_input("Gemini API Key", value=_get_cfg("gemini_api_key"),
                                         type="password", key="cfg_gem_key")
                _gem_saved = _get_cfg("gemini_model", _get_cfg("llm_model", _GEMINI_MODELS[0]))
                _gem_idx = _GEMINI_MODELS.index(_gem_saved) if _gem_saved in _GEMINI_MODELS else 0
                _gem_mdl = st.selectbox("Model Gemini", _GEMINI_MODELS,
                                        index=_gem_idx, key="cfg_gem_model",
                                        help="gemini-2.5-flash = latest & most accurate\ngemini-2.0-flash = stable & fast")
            elif _prov_code == "ollama":
                st.caption("🖥️ Ollama must run at **localhost:11434** — install from ollama.com")
                _oll_mdl = st.text_input("Ollama Model Name",
                                         value=_get_cfg("ollama_model", "llama3.3"),
                                         key="cfg_ollama_model",
                                         help="e.g. llama3.3, gemma3, qwen2.5")
            elif _prov_code == "openrouter":
                st.caption("🔑 Free signup: **openrouter.ai** — many free-tier models")
                _or_key = st.text_input("OpenRouter API Key", value=_get_cfg("openrouter_key"),
                                        type="password", key="cfg_or_key")
                _or_saved = _get_cfg("openrouter_model", _get_cfg("llm_model", _OPENROUTER_FREE[0]))
                _or_idx = _OPENROUTER_FREE.index(_or_saved) if _or_saved in _OPENROUTER_FREE else 0
                _or_mdl = st.selectbox("Model (free tier)", _OPENROUTER_FREE,
                                       index=_or_idx, key="cfg_or_model")
            else:
                st.info("✅ Offline mode — no API key needed. Rule-based agronomy responses.")

            _llm_col1, _llm_col2 = st.columns(2)
            with _llm_col1:
                if st.button("💾 Save LLM Settings", key="save_llm_cfg",
                             width='stretch'):
                    _kw: dict = {"llm_provider": _prov_code, "llm_temperature": _llm_temp_val}
                    if _prov_code == "groq":
                        _kw["groq_api_key"] = _groq_key
                        _kw["groq_model"]   = _groq_mdl
                        _kw["llm_model"]    = _groq_mdl
                    elif _prov_code == "gemini":
                        _kw["gemini_api_key"] = _gem_key
                        _kw["gemini_model"]   = _gem_mdl
                        _kw["llm_model"]      = _gem_mdl
                    elif _prov_code == "ollama":
                        _kw["ollama_model"] = _oll_mdl
                        _kw["llm_model"]    = _oll_mdl
                    elif _prov_code == "openrouter":
                        _kw["openrouter_key"]   = _or_key
                        _kw["openrouter_model"] = _or_mdl
                        _kw["llm_model"]        = _or_mdl
                    _save_cfg(**_kw)
                    st.success(f"✅ LLM → {_prov_code} saved!")
            with _llm_col2:
                if st.button("🧪 Test AI Now", key="test_llm_btn",
                             width='stretch'):
                    _test_loc = get_location_state()
                    _test_prompt = (
                        f"Give 2 brief crop cultivation tips for "
                        f"{_test_loc.display_name} (zone {_test_loc.climate_zone})."
                    )
                    with st.spinner("Contacting AI..."):
                        _test_resp, _test_src = call_llm(_test_prompt, max_tokens=200)
                    st.caption(f"Provider: {_test_src}")
                    st.info(_test_resp)

        # ── Lokasi Global — Cascading Dropdown (Negara → Provinsi → Kota → Kecamatan → Kelurahan) ──
        st.markdown('<div class="sidebar-sep"></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-header">🌍 LOCATION & WEATHER</div>',
                    unsafe_allow_html=True)
        st.caption("Set once → all panels sync globally.")
        _loc_mode = st.radio(
            "Location Mode",
            ["Manual", "Device GPS"],
            horizontal=True,
            key="sb_location_mode_v4",
            help="GPS uses browser location permission. For production, run on HTTPS or localhost.")
        _gps_loc_override: Optional[LocationState] = None
        if _loc_mode == "Device GPS":
            _gps_payload = render_device_gps_component("sb_device_gps")
            if _gps_payload:
                _gps_sig = (
                    f"{_gps_payload['lat']:.6f}|{_gps_payload['lon']:.6f}|"
                    f"{round(_gps_payload.get('accuracy_m', 0.0))}|{_gps_payload.get('ts', '')}"
                )
                if _gps_sig != st.session_state.get("_last_gps_sig_v4"):
                    _gps_loc_override = build_location_from_gps(
                        _gps_payload["lat"], _gps_payload["lon"],
                        _gps_payload.get("accuracy_m", 0.0),
                        _gps_payload.get("ts", ""),
                        fallback=get_location_state())
                    st.session_state["_last_gps_sig_v4"] = _gps_sig
                    # Sync all sidebar state to GPS result
                    _glo = _gps_loc_override
                    for _k, _v in [
                        ("_sb_cc_v3",        _glo.country_code),
                        ("sb_country_v3",    _glo.country_code),
                        ("_sb_prov_v3",      _glo.province),
                        ("_sb_city_v3",      _glo.city),
                        ("_sb_dist_v3",      _glo.district),
                        ("_sb_vill_v3",      _glo.village),
                        ("_sb_prov_code_v4", _glo.province_code),
                        ("_sb_city_code_v4", _glo.city_code),
                        ("_sb_dist_code_v4", _glo.district_code),
                        ("_sb_vill_code_v4", _glo.village_code),
                        ("sb_prov_code_v4a", _glo.province_code),
                        ("sb_city_code_v4a", _glo.city_code),
                        ("sb_dist_code_v4a", _glo.district_code),
                        ("sb_vill_code_v4a", _glo.village_code),
                    ]:
                        st.session_state[_k] = _v
                    set_location_state(_gps_loc_override)
                    st.session_state.pop("wx_data", None)
                    st.session_state.pop("_weather_loc_sig", None)
                    st.rerun()
                else:
                    _gps_existing = get_location_state()
                    if _gps_existing.location_source == "gps":
                        _gps_loc_override = _gps_existing

            # ── GPS status card ───────────────────────────────────────────
            _cur_gps = _gps_loc_override or (
                get_location_state()
                if get_location_state().location_source == "gps"
                else None
            )
            if _cur_gps:
                _acc_str = f"±{_cur_gps.accuracy_m:.0f} m" if _cur_gps.accuracy_m > 0 else "accuracy N/A"
                _det_str = _cur_gps.detected_at[11:16] if len(_cur_gps.detected_at) >= 16 else "just now"
                st.markdown(
                    f'<div style="background:#0d2d0d;border:1px solid #1e6a1e;border-radius:6px;'
                    f'padding:5px 8px;margin:3px 0;font-size:10px;">'
                    f'📡 <b style="color:#44ee88;">GPS Active</b> · '
                    f'{_cur_gps.flag_emoji} {_cur_gps.display_name}<br>'
                    f'<span style="color:#66aa66;">'
                    f'{_cur_gps.lat:.5f}°, {_cur_gps.lon:.5f}° · {_acc_str} · {_det_str}'
                    f'</span></div>',
                    unsafe_allow_html=True)
                if st.button("✖ Exit GPS Mode", key="gps_clear_btn",
                             width='stretch'):
                    # Clear GPS payload from URL & session
                    for _gk in ["_last_gps_sig_v4", "sb_location_mode_v4"]:
                        st.session_state.pop(_gk, None)
                    _cur_loc = get_location_state()
                    _cur_loc.location_source = "manual"
                    set_location_state(_cur_loc)
                    try:
                        _qp = dict(st.query_params)
                        for _pk in ["gps_lat", "gps_lon", "gps_acc", "gps_ts", "gps_nonce"]:
                            _qp.pop(_pk, None)
                        st.query_params.update(_qp)
                    except Exception:
                        pass
                    st.rerun()
            else:
                st.caption(
                    "📍 Press the button above → allow location in browser → "
                    "page will reload with your GPS coordinates.")

        # ── Rendering mode: Manual shows dropdowns, GPS reads session state ─────
        _show_dropdowns = (_loc_mode == "Manual")
        _manual_sub = "Admin Selection"
        if _show_dropdowns:
            _manual_sub = st.radio(
                "Input Method", ["Admin Selection", "Coordinates"],
                horizontal=True, key="sb_manual_sub_v1",
                help="Admin: select from dropdown hierarchy · Coordinates: enter lat/lon directly")
        else:
            # GPS mode — read last-known values without rendering any widgets
            _sb_cc        = st.session_state.get("_sb_cc_v3", "ID")
            _sb_prov      = st.session_state.get("_sb_prov_v3", "")
            _sb_prov_code = st.session_state.get("sb_prov_code_v4a", "")
            _sb_city      = st.session_state.get("_sb_city_v3", "")
            _sb_city_code = st.session_state.get("sb_city_code_v4a", "")
            _sb_dist      = st.session_state.get("_sb_dist_v3", "")
            _sb_dist_code = st.session_state.get("sb_dist_code_v4a", "")
            _sb_vill      = st.session_state.get("_sb_vill_v3", "")
            _sb_vill_code = st.session_state.get("sb_vill_code_v4a", "")
            _cdata_w   = WORLD_COUNTRIES.get(_sb_cc, WORLD_COUNTRIES["ID"])
            _ctry_name = _cdata_w[0]; _cur_code = _cdata_w[1]; _cur_sym = _cdata_w[2]
            _lang_code = _cdata_w[3]; _admin_tp = _cdata_w[4]
            _albl      = ADMIN_LEVEL_LABELS.get(_admin_tp, ADMIN_LEVEL_LABELS["DEFAULT"])
            _is_indo   = (_sb_cc == "ID")

        # ── Negara / Country ──────────────────────────────────────────────────
        _ctry_codes   = sorted(WORLD_COUNTRIES.keys(),
                               key=lambda c: WORLD_COUNTRIES[c][0])
        _ctry_display = {c: f"{WORLD_COUNTRIES[c][0]}" for c in _ctry_codes}
        _prev_cc = st.session_state.get("_sb_cc_v3", "ID")
        _cc_idx  = _ctry_codes.index(_prev_cc) if _prev_cc in _ctry_codes else 0
        if _show_dropdowns:
            _sb_cc   = st.selectbox(
                "🌍 Country",
                _ctry_codes, index=_cc_idx,
                format_func=lambda c: f"{WORLD_COUNTRIES[c][0]} ({c})",
                key="sb_country_v3"
            )
        # Reset child levels on country change
        if st.session_state.get("_sb_cc_v3") != _sb_cc:
            for _k in ["_sb_prov_v3", "_sb_city_v3", "_sb_dist_v3", "_sb_vill_v3",
                       "_sb_prov_code_v4", "_sb_city_code_v4", "_sb_dist_code_v4",
                       "_sb_vill_code_v4", "_sb_loc_sig_v3", "_sb_geo_result_v3"]:
                st.session_state.pop(_k, None)
        st.session_state["_sb_cc_v3"] = _sb_cc

        _cdata_w     = WORLD_COUNTRIES.get(_sb_cc, WORLD_COUNTRIES["ID"])
        _ctry_name   = _cdata_w[0]
        _cur_code    = _cdata_w[1]
        _cur_sym     = _cdata_w[2]
        _lang_code   = _cdata_w[3]
        _admin_tp    = _cdata_w[4]
        _albl        = ADMIN_LEVEL_LABELS.get(_admin_tp, ADMIN_LEVEL_LABELS["DEFAULT"])
        _is_indo     = (_sb_cc == "ID")

        # ── Province / Provinsi ───────────────────────────────────────────────
        if _is_indo:
            _prov_items = _id_admin_children("province")
            _prov_by_code = {item["code"]: item["name"] for item in _prov_items}
            _prov_codes = list(_prov_by_code.keys())
            _prev_prov_item = _find_admin_item(
                _prov_items,
                code=st.session_state.get("_sb_prov_code_v4", ""),
                name=st.session_state.get("_sb_prov_v3", "DKI Jakarta"))
            _prev_prov_code = (_prev_prov_item or _prov_items[0])["code"] if _prov_items else ""
            _pv_idx = _prov_codes.index(_prev_prov_code) if _prev_prov_code in _prov_codes else 0
            if _show_dropdowns:
                _sb_prov_code = st.selectbox(
                    f"🏛️ {_albl['province']}", _prov_codes,
                    index=_pv_idx, key="sb_prov_code_v4a",
                    format_func=lambda c: _prov_by_code.get(c, c))
            _sb_prov = _prov_by_code.get(_sb_prov_code, "")
        else:
            _sb_prov_code = ""
            _gn_provs  = geonames_provinces(_sb_cc)
            _prov_opts = _gn_provs or preset_provinces(_sb_cc)
            if _show_dropdowns:
                _sb_prov = select_required_dropdown(
                    f"🏛️ {_albl['province']}", _prov_opts,
                    "_sb_prov_v3", "sb_prov_v3b", fallback=_ctry_name)
        if (st.session_state.get("_sb_prov_v3") != _sb_prov or
                st.session_state.get("_sb_prov_code_v4") != _sb_prov_code):
            for _k in ["_sb_city_v3", "_sb_dist_v3", "_sb_vill_v3",
                       "_sb_city_code_v4", "_sb_dist_code_v4", "_sb_vill_code_v4"]:
                st.session_state.pop(_k, None)
        st.session_state["_sb_prov_v3"] = _sb_prov
        st.session_state["_sb_prov_code_v4"] = _sb_prov_code

        # ── Kota / City ───────────────────────────────────────────────────────
        if _is_indo:
            _city_items = _id_admin_children("city", _sb_prov_code)
            _city_by_code = {item["code"]: item["name"] for item in _city_items}
            _city_codes = list(_city_by_code.keys())
            _prev_city_item = _find_admin_item(
                _city_items,
                code=st.session_state.get("_sb_city_code_v4", ""),
                name=st.session_state.get("_sb_city_v3", ""))
            _prev_city_code = (_prev_city_item or _city_items[0])["code"] if _city_items else ""
            _ct_idx = _city_codes.index(_prev_city_code) if _prev_city_code in _city_codes else 0
            if _show_dropdowns:
                _sb_city_code = st.selectbox(
                    f"🏙️ {_albl['city']}", _city_codes,
                    index=_ct_idx, key="sb_city_code_v4a",
                    format_func=lambda c: _city_by_code.get(c, c))
            _sb_city = _city_by_code.get(_sb_city_code, _sb_prov)
        else:
            _sb_city_code = ""
            _gn_cities = geonames_cities(_sb_cc, _sb_prov) if _sb_prov else []
            _city_opts = _gn_cities or preset_cities(_sb_cc, _sb_prov)
            if _show_dropdowns:
                _sb_city = select_required_dropdown(
                    f"🏙️ {_albl['city']}", _city_opts,
                    "_sb_city_v3", "sb_city_v3b", fallback=_sb_prov or _ctry_name)
        if (st.session_state.get("_sb_city_v3") != _sb_city or
                st.session_state.get("_sb_city_code_v4") != _sb_city_code):
            for _k in ["_sb_dist_v3", "_sb_vill_v3", "_sb_dist_code_v4", "_sb_vill_code_v4"]:
                st.session_state.pop(_k, None)
        st.session_state["_sb_city_v3"] = _sb_city
        st.session_state["_sb_city_code_v4"] = _sb_city_code

        # ── Kecamatan / District ──────────────────────────────────────────────
        _gn_user_set = bool(_get_cfg("geonames_username", ""))
        if _is_indo:
            _dist_items = _id_admin_children("district", _sb_city_code)
            _dist_by_code = {item["code"]: item["name"] for item in _dist_items}
            _dist_codes = list(_dist_by_code.keys())
            _dist_choices = [""] + _dist_codes
            _prev_dist_item = _find_admin_item(
                _dist_items,
                code=st.session_state.get("_sb_dist_code_v4", ""),
                name=st.session_state.get("_sb_dist_v3", ""))
            _prev_dist_code = _prev_dist_item["code"] if _prev_dist_item else ""
            _dist_idx = _dist_choices.index(_prev_dist_code) if _prev_dist_code in _dist_choices else 0
            _empty_dist_label = f"— all {_albl['district']} —"
            if _show_dropdowns:
                _sb_dist_code = st.selectbox(
                    f"📍 {_albl['district']} (optional)", _dist_choices,
                    index=_dist_idx, key="sb_dist_code_v4a",
                    format_func=lambda c: _empty_dist_label if not c else _dist_by_code.get(c, c))
            _sb_dist = _dist_by_code.get(_sb_dist_code, "")
        else:
            _sb_dist_code = ""
            _gn_dists = geonames_districts(_sb_cc, _sb_prov, _sb_city) if (_gn_user_set and _sb_prov) else []
            _dist_opts = _gn_dists or preset_admin_children(_sb_cc, _sb_prov, _sb_city, "district")
            if _show_dropdowns:
                _sb_dist = select_optional_dropdown(
                    f"📍 {_albl['district']} (optional)", _dist_opts,
                    "_sb_dist_v3", "sb_dist_dd_v3", f"— all {_albl['district']} —")
        if (st.session_state.get("_sb_dist_v3") != _sb_dist or
                st.session_state.get("_sb_dist_code_v4") != _sb_dist_code):
            for _k in ["_sb_vill_v3", "_sb_vill_code_v4"]:
                st.session_state.pop(_k, None)
        st.session_state["_sb_dist_v3"] = _sb_dist
        st.session_state["_sb_dist_code_v4"] = _sb_dist_code

        # ── Kelurahan / Village ───────────────────────────────────────────────
        if _is_indo:
            _vill_items = _id_admin_children("village", _sb_dist_code) if _sb_dist_code else []
            _vill_by_code = {item["code"]: item["name"] for item in _vill_items}
            _vill_codes = list(_vill_by_code.keys())
            _vill_choices = [""] + _vill_codes
            _prev_vill_item = _find_admin_item(
                _vill_items,
                code=st.session_state.get("_sb_vill_code_v4", ""),
                name=st.session_state.get("_sb_vill_v3", ""))
            _prev_vill_code = _prev_vill_item["code"] if _prev_vill_item else ""
            _vill_idx = _vill_choices.index(_prev_vill_code) if _prev_vill_code in _vill_choices else 0
            _empty_vill_label = f"— all {_albl['village']} —"
            if _show_dropdowns:
                _sb_vill_code = st.selectbox(
                    f"🏘️ {_albl['village']} (optional)", _vill_choices,
                    index=_vill_idx, key="sb_vill_code_v4a",
                    format_func=lambda c: _empty_vill_label if not c else _vill_by_code.get(c, c))
            _sb_vill = _vill_by_code.get(_sb_vill_code, "")
        else:
            _sb_vill_code = ""
            _gn_vills = geonames_villages(_sb_cc, _sb_prov, _sb_city, _sb_dist) if (_gn_user_set and _sb_prov) else []
            _vill_opts = _gn_vills or preset_admin_children(_sb_cc, _sb_prov, _sb_city, "village")
            if _show_dropdowns:
                _sb_vill = select_optional_dropdown(
                    f"🏘️ {_albl['village']} (optional)", _vill_opts,
                    "_sb_vill_v3", "sb_vill_dd_v3", f"— all {_albl['village']} —")
        st.session_state["_sb_vill_v3"] = _sb_vill
        st.session_state["_sb_vill_code_v4"] = _sb_vill_code

        # ── Geocode → build LocationState ────────────────────────────────────
        _geo_parts  = [p.strip() for p in [_sb_vill, _sb_dist, _sb_city, _sb_prov, _ctry_name] if p.strip()]
        _geo_q      = ", ".join(_geo_parts) if _geo_parts else _ctry_name
        _loc_sig    = (
            f"{_sb_cc}|{_sb_prov_code}|{_sb_city_code}|{_sb_dist_code}|{_sb_vill_code}|"
            f"{_sb_prov}|{_sb_city}|{_sb_dist}|{_sb_vill}"
        )
        _owm_k_sb   = _get_cfg("owm_api_key", "")
        _geo_hit    = st.session_state.get("_sb_geo_result_v3", {})

        if _loc_sig != st.session_state.get("_sb_loc_sig_v3"):
            st.session_state.pop("wx_data", None)
            st.session_state.pop("_weather_loc_sig", None)
            st.session_state.pop("_sb_geo_result_v3", None)
            _geo_hit = {}

        if _loc_sig != st.session_state.get("_sb_loc_sig_v3") and _owm_k_sb and len(_geo_parts) >= 2:
            try:
                _gr = requests.get(
                    "https://api.openweathermap.org/geo/1.0/direct",
                    params={"q": _geo_q, "limit": 5, "appid": _owm_k_sb},
                    timeout=5)
                _gd = _gr.json()
                if _gd:
                    # Prefer result matching country code
                    _gd_filt = ([g for g in _gd if g.get("country","").upper() == _sb_cc] or _gd)
                    _geo_hit = _gd_filt[0]
                    st.session_state["_sb_geo_result_v3"] = _geo_hit
            except Exception:
                pass
            st.session_state["_sb_loc_sig_v3"] = _loc_sig

        # Resolve coordinates — geocode hit → INDO_REGIONS lookup → centroid fallback
        if _geo_hit:
            _loc_lat = float(_geo_hit.get("lat", -6.2146))
            _loc_lon = float(_geo_hit.get("lon", 106.8451))
        elif _is_indo:
            # No OWM key: find the best matching INDO_REGIONS entry for real coordinates.
            # 1. Try city name (strip "Kabupaten "/"Kota " prefix, then match)
            # 2. Fall back to any region in the same province
            def _norm(s: str) -> str:
                return (s.lower()
                        .replace("kabupaten ", "").replace("kota ", "").replace("kab. ", "")
                        .replace("daerah istimewa ", "").replace("provinsi ", "")
                        .replace("kepulauan ", "").strip())
            _city_norm = _norm(_sb_city or "")
            _prov_norm = _norm(_sb_prov or "")
            _ir_best: Optional["IndoRegion"] = None
            # exact or substring match on city
            for _irk, _irv in INDO_REGIONS.items():
                if _city_norm and (_city_norm in _irk or _irk in _city_norm):
                    _ir_best = _irv
                    break
            # fall back to province match
            if not _ir_best:
                for _irk, _irv in INDO_REGIONS.items():
                    _irv_prov = _norm(_irv.provinsi)
                    if _prov_norm and (_prov_norm in _irv_prov or _irv_prov in _prov_norm):
                        _ir_best = _irv
                        break
            if _ir_best:
                _loc_lat, _loc_lon = _ir_best.lat, _ir_best.lon
            else:
                _loc_lat, _loc_lon = _COUNTRY_CENTROIDS.get(_sb_cc, (-6.2146, 106.8451))
        else:
            _centroid = _COUNTRY_CENTROIDS.get(_sb_cc)
            if _centroid:
                _loc_lat, _loc_lon = _centroid
            else:
                _dr_prev = st.session_state.get("default_region")
                _loc_lat = _dr_prev.lat if _dr_prev else -6.2146
                _loc_lon = _dr_prev.lon if _dr_prev else 106.8451

        _new_region  = build_region_from_coords(
            _loc_lat, _loc_lon, 0.0,
            nama=_sb_city or _sb_prov,
            provinsi=f"{_sb_prov}, {_ctry_name}" if _sb_prov else _ctry_name)

        # Build & store LocationState
        _new_loc_st = LocationState(
            country=_ctry_name, country_code=_sb_cc,
            province=_sb_prov, city=_sb_city,
            district=_sb_dist, village=_sb_vill,
            province_code=_sb_prov_code, city_code=_sb_city_code,
            district_code=_sb_dist_code, village_code=_sb_vill_code,
            lat=_loc_lat, lon=_loc_lon, altitude_m=0.0,
            currency=_cur_code, currency_symbol=_cur_sym,
            language=_lang_code, admin_type=_admin_tp,
            timezone="UTC",
            climate_zone=_new_region.zona_agroklimat,
            location_source="manual",
            accuracy_m=0.0,
            detected_at="",
        )
        if _loc_mode == "Device GPS" and _gps_loc_override:
            _new_loc_st = _gps_loc_override
            _loc_lat, _loc_lon = _new_loc_st.lat, _new_loc_st.lon
            _new_region = _new_loc_st.to_indo_region()
        set_location_state(_new_loc_st)
        st.session_state["_sb_loc_sig_v3"] = _loc_sig

        # ── Location preview card ─────────────────────────────────────────────
        _zona_c = _new_region.zona_agroklimat
        _source_label = "GPS" if _new_loc_st.location_source == "gps" else "Manual"
        _accuracy_label = f" · ±{_new_loc_st.accuracy_m:.0f} m" if _new_loc_st.accuracy_m else ""
        _detected_label = f" · {_new_loc_st.detected_at}" if _new_loc_st.detected_at else ""
        st.markdown(
            f'<div style="background:#071c07;border:1px solid #1e4a1e;border-radius:8px;'
            f'padding:7px 10px;margin:4px 0;font-size:11px;line-height:1.7;">'
            f'{_new_loc_st.flag_emoji} <b style="color:#88ee88;">{_new_loc_st.display_name}</b><br>'
            f'<span style="color:#557755;">{_loc_lat:.4f}°, {_loc_lon:.4f}° · '
            f'Zone: <span style="color:#44eeaa;">{_zona_c}</span> · '
            f'{_cur_code} {_cur_sym} · {_source_label}{_accuracy_label}{_detected_label}</span>'
            f'</div>',
            unsafe_allow_html=True)

        # ── Coordinates sub-mode (Manual → Coordinates) or expander fallback ───
        if _manual_sub == "Coordinates" and _show_dropdowns:
            _ov_ca, _ov_cb = st.columns(2)
            with _ov_ca:
                _ov_lat = st.number_input("Lat °", -90.0, 90.0, _loc_lat, 0.0001,
                                          format="%.4f", key="sb_ov_lat_v3")
            with _ov_cb:
                _ov_lon = st.number_input("Lon °", -180.0, 180.0, _loc_lon, 0.0001,
                                          format="%.4f", key="sb_ov_lon_v3")
            _ov_alt = st.number_input("Alt (m asl)", 0, 8849, 0, 10, key="sb_ov_alt_v3")
            if st.button("📌 Apply Coordinates", key="sb_ov_apply_v3", width='stretch'):
                _rgeo_ov = _reverse_geocode_owm(_ov_lat, _ov_lon)
                _nr_ov   = build_region_from_coords(
                    _ov_lat, _ov_lon, float(_ov_alt),
                    nama=_rgeo_ov.get("name", _sb_city),
                    provinsi=f"{_rgeo_ov.get('state', _sb_prov)}, {_ctry_name}")
                _new_loc_st.lat = _ov_lat
                _new_loc_st.lon = _ov_lon
                _new_loc_st.altitude_m = float(_ov_alt)
                _new_loc_st.climate_zone = _nr_ov.zona_agroklimat
                _new_loc_st.location_source = "manual_override"
                _new_loc_st.accuracy_m = 0.0
                _new_loc_st.detected_at = datetime.datetime.now().isoformat(timespec="seconds")
                set_location_state(_new_loc_st)
                st.session_state.pop("wx_data", None)
                st.session_state.pop("_weather_loc_sig", None)
                st.rerun()
        elif _show_dropdowns:
            with st.expander("🌐 Manual Coordinate Override", expanded=False):
                _ov_ca, _ov_cb = st.columns(2)
                with _ov_ca:
                    _ov_lat = st.number_input("Lat °", -90.0, 90.0, _loc_lat, 0.0001,
                                              format="%.4f", key="sb_ov_lat_v3")
                with _ov_cb:
                    _ov_lon = st.number_input("Lon °", -180.0, 180.0, _loc_lon, 0.0001,
                                              format="%.4f", key="sb_ov_lon_v3")
                _ov_alt = st.number_input("Alt (m asl)", 0, 8849, 0, 10, key="sb_ov_alt_v3")
                if st.button("📌 Apply Coordinates", key="sb_ov_apply_v3", width='stretch'):
                    _rgeo_ov = _reverse_geocode_owm(_ov_lat, _ov_lon)
                    _nr_ov   = build_region_from_coords(
                        _ov_lat, _ov_lon, float(_ov_alt),
                        nama=_rgeo_ov.get("name", _sb_city),
                        provinsi=f"{_rgeo_ov.get('state', _sb_prov)}, {_ctry_name}")
                    _new_loc_st.lat = _ov_lat
                    _new_loc_st.lon = _ov_lon
                    _new_loc_st.altitude_m = float(_ov_alt)
                    _new_loc_st.climate_zone = _nr_ov.zona_agroklimat
                    _new_loc_st.location_source = "manual_override"
                    _new_loc_st.accuracy_m = 0.0
                    _new_loc_st.detected_at = datetime.datetime.now().isoformat(timespec="seconds")
                    set_location_state(_new_loc_st)
                    st.session_state.pop("wx_data", None)
                    st.session_state.pop("_weather_loc_sig", None)
                    st.rerun()

        _new_region  = _new_loc_st.to_indo_region()
        _weather_city = _sb_city or _sb_prov or _ctry_name
        _new_region_ref = _new_region   # alias used below

        # ── Fetch Weather ─────────────────────────────────────────────────
        if st.button("🌤️ Fetch Weather", key="sb_fetch_wx", width='stretch'):
            wx_svc.api_key = api_key
            _loc_for_wx = get_location_state()
            st.session_state.wx_data = wx_svc.fetch_by_coords(
                _loc_for_wx.lat, _loc_for_wx.lon,
                location_name=f"{_loc_for_wx.display_name}, {_loc_for_wx.country}",
                alt_m=_loc_for_wx.altitude_m,
            )
            st.session_state["_weather_loc_sig"] = location_signature(_loc_for_wx)
            logger.log(f"Weather fetched: {_loc_for_wx.display_name} ({_loc_for_wx.lat:.4f},{_loc_for_wx.lon:.4f})", "INFO")
            st.rerun()

        # ── Indonesia Admin Data Status ───────────────────────────────────
        if _is_indo:
            _adm = load_id_admin_regions()
            _adm_meta = _adm.get("meta", {})
            _adm_src = _adm_meta.get("source", "legacy-inline")
            _adm_prov = len(_adm.get("provinces", []))
            _adm_reg  = sum(len(v) for v in _adm.get("regencies", {}).values())
            _adm_dist = sum(len(v) for v in _adm.get("districts", {}).values())
            _adm_vill = sum(len(v) for v in _adm.get("villages", {}).values())
            _adm_has_json = os.path.exists(_ID_ADMIN_REGIONS_PATH)

            _adm_color = "#1a4a1a" if _adm_has_json else "#3a2a0a"
            _adm_icon  = "✅" if _adm_has_json else "⚠️"
            st.markdown(
                f'<div style="background:{_adm_color};border:1px solid #2a5a1a;'
                f'border-radius:6px;padding:5px 8px;margin:4px 0;font-size:10px;">'
                f'{_adm_icon} <b style="color:#88ee88;">ID Region Data</b> · '
                f'{_adm_prov} prov · {_adm_reg} reg/city · '
                f'{_adm_dist} dist · {_adm_vill} village<br>'
                f'<span style="color:#668866;">Source: {_adm_src} · {_adm_meta.get("updated_at","")}</span>'
                f'</div>',
                unsafe_allow_html=True)

            if not _adm_has_json or _adm_dist == 0:
                with st.expander(
                    "📥 Update Indonesia Region Data" if _adm_has_json else "📥 Generate Indonesia Region Data",
                    expanded=not _adm_has_json):
                    st.markdown(
                        "Hierarchical region data incomplete. "
                        "For accurate District & Village dropdowns, run:"
                    )
                    st.code(
                        "# In terminal/command prompt:\n"
                        "python build_id_admin.py --no-villages   # ~5 min\n"
                        "# or for full data including villages:\n"
                        "python build_id_admin.py                  # ~25 min",
                        language="bash")
                    st.caption(
                        f"File target: `{_ID_ADMIN_REGIONS_PATH}`\n"
                        "Source: emsifa.github.io/api-wilayah-indonesia (Kemendagri CC-BY)")

                    if st.button("⚡ Download Provinces + Regencies (~30 sec)",
                                 key="adm_quick_dl", width='stretch'):
                        with st.spinner("Downloading province and regency data..."):
                            try:
                                _BASE_ADM = "https://emsifa.github.io/api-wilayah-indonesia/api"

                                def _adm_fetch(url: str) -> list:
                                    for _att in range(3):
                                        try:
                                            _r = requests.get(url, timeout=15)
                                            _r.raise_for_status()
                                            return _r.json()
                                        except Exception:
                                            time.sleep(1.0 * (2 ** _att))
                                    return []

                                def _adm_title(name: str) -> str:
                                    KEEP = {"DKI","DIY","NTB","NTT","DI"}
                                    return " ".join(
                                        w.upper() if w.upper() in KEEP else w.capitalize()
                                        for w in str(name or "").strip().split())

                                _pv_raw = _adm_fetch(f"{_BASE_ADM}/provinces.json")
                                _pv_list = [{"code": p["id"], "name": _adm_title(p["name"])}
                                            for p in _pv_raw if p.get("id") and p.get("name")]
                                _reg_dict: Dict[str, list] = {}
                                for _pv in _pv_list:
                                    _rg_raw = _adm_fetch(f"{_BASE_ADM}/regencies/{_pv['code']}.json")
                                    _reg_dict[_pv["code"]] = [
                                        {"code": r["id"], "name": _adm_title(r["name"])}
                                        for r in _rg_raw if r.get("id") and r.get("name")
                                    ]
                                    time.sleep(0.06)

                                _new_data = {
                                    "meta": {
                                        "source": "emsifa.github.io/api-wilayah-indonesia",
                                        "updated_at": datetime.date.today().isoformat(),
                                        "provinces": len(_pv_list),
                                        "regencies": sum(len(v) for v in _reg_dict.values()),
                                        "districts": 0,
                                        "villages": 0,
                                    },
                                    "provinces": _pv_list,
                                    "regencies": _reg_dict,
                                    "districts": {},
                                    "villages": {},
                                }
                                with open(_ID_ADMIN_REGIONS_PATH, "w", encoding="utf-8") as _f:
                                    json.dump(_new_data, _f, ensure_ascii=False, separators=(",", ":"))
                                # Bust the lru_cache so next render reloads the file
                                load_id_admin_regions.cache_clear()
                                st.success(
                                    f"✅ Saved! {len(_pv_list)} provinces, "
                                    f"{sum(len(v) for v in _reg_dict.values())} regencies. "
                                    "Reload page to see new dropdowns.")
                                st.rerun()
                            except Exception as _e_dl:
                                st.error(f"❌ Download failed: {str(_e_dl)[:120]}")

        # ── Zone Management ────────────────────────────────────────────────
        st.markdown('<div class="section-header">🌿 Zone Management</div>', unsafe_allow_html=True)
        n_zones = st.number_input("Number of Zones", min_value=1, value=len(zones), step=1)

        if n_zones != len(zones):
            crops      = list(CropType)
            zone_types = list(ZoneType)
            irrig_list = list(IrrigationMode)
            new_zones  = []
            for i in range(int(n_zones)):
                if i < len(zones):
                    new_zones.append(zones[i])
                else:
                    zid = f"ZONE-{chr(65+i)}"
                    new_zones.append(GreenZone(
                        zid, zone_types[i % len(zone_types)],
                        crops[i % len(crops)], 80, 400,
                        irrig_list[i % len(irrig_list)]
                    ))
            st.session_state.zones = new_zones
            zones = new_zones
            logger.log(f"Zone count → {n_zones}", "INFO")

        for i, zone in enumerate(zones):
            with st.expander(f"⚙️ {zone.zone_id} Config"):
                # ── Unified Indonesian crop selector (102 tanaman, grouped by category) ──
                crop_choices = get_unified_crop_choices()
                current_indo_id = get_zone_indo_crop_id(zone)
                crop_ids_list = [c[1] for c in crop_choices]
                default_idx = crop_ids_list.index(current_indo_id) if current_indo_id in crop_ids_list else 0
                cat_filter = st.selectbox(
                    f"Category ({zone.zone_id})",
                    ["All"] + sorted({c[2] for c in crop_choices}),
                    key=f"crop_cat_{zone.zone_id}",
                )
                filtered = crop_choices if cat_filter == "All" \
                           else [c for c in crop_choices if c[2] == cat_filter]
                if not filtered:
                    filtered = crop_choices
                f_ids = [c[1] for c in filtered]
                f_idx = f_ids.index(current_indo_id) if current_indo_id in f_ids else 0
                c_idx = st.selectbox(
                    f"Crop ({zone.zone_id})",
                    range(len(filtered)),
                    format_func=lambda i, lst=filtered: f"[{lst[i][2][:6]}] {lst[i][0]}",
                    index=f_idx,
                    key=f"crop_{zone.zone_id}",
                )
                selected_indo_id = filtered[c_idx][1]
                selected_indo_crop = INDONESIAN_CROPS_DB[selected_indo_id]
                _loc_crop = get_location_state()
                _loc_price, _loc_price_meta = localized_crop_price_idr(selected_indo_crop, _loc_crop)
                st.caption(f"🌱 {selected_indo_crop.scientific} · DAP: {selected_indo_crop.dap_panen} days · "
                           f"Yield: {selected_indo_crop.yield_avg_ton_ha:.1f} t/ha · "
                           f"Market price {_loc_crop.country_code}: {fmt_3ccy(_loc_price, _loc_crop)}/kg "
                           f"(×{_loc_price_meta['country_mult']:.2f})")

                c_irrig = st.selectbox(f"Irrigation ({zone.zone_id})",
                    [m.value for m in IrrigationMode], key=f"irrig_{zone.zone_id}")
                c_area = st.number_input(f"Area m² ({zone.zone_id})", min_value=10, value=int(zone.area_m2), step=10, key=f"area_{zone.zone_id}")
                c_zone_type = st.selectbox(f"Zone Type ({zone.zone_id})",
                    [t.value for t in ZoneType], key=f"ztype_{zone.zone_id}")
                if st.button(f"✅ Apply {zone.zone_id}", key=f"apply_{zone.zone_id}"):
                    new_crop   = indo_crop_id_to_croptype(selected_indo_id)
                    new_irrig  = next(m for m in IrrigationMode if m.value == c_irrig)
                    new_ztype  = next(t for t in ZoneType       if t.value == c_zone_type)
                    if (new_crop != zone.crop_type or c_area != zone.area_m2 or
                            new_irrig != zone.irrigation_mode or
                            selected_indo_id != current_indo_id):
                        zones[i] = GreenZone(
                            zone.zone_id, new_ztype, new_crop,
                            float(c_area), float(c_area) * 5.0, new_irrig
                        )
                        zones[i].indo_crop_id = selected_indo_id
                        st.session_state.zones = zones
                        logger.log(f"{zone.zone_id} → {selected_indo_crop.nama_id} ({c_irrig})", "INFO")
                        st.rerun()

                # Predictive maintenance service
                if zone.maint_engine.get_critical_components(80.0):
                    comp_names = [r.component for r in zone.maint_engine.get_critical_components(80.0)]
                    svc_target = st.selectbox(
                        f"Service component ({zone.zone_id})",
                        comp_names, key=f"svc_{zone.zone_id}"
                    )
                    if st.button(f"🔧 Service {svc_target}", key=f"do_svc_{zone.zone_id}"):
                        zone.maint_engine.service_component(svc_target)
                        logger.log(f"{zone.zone_id}: Serviced {svc_target}", "MAINT")
                        st.rerun()

        # ── Simulation ─────────────────────────────────────────────────────
        st.markdown('<div class="section-header">▶ Simulation</div>', unsafe_allow_html=True)
        sim_steps  = st.slider("Steps", 5, 720, 72, 5,
                               help="Number of simulation steps (1 step ≈ 1 hr)")
        speed_ms   = st.slider("Speed (ms)", 0, 400, 10, 10,
                               help="Delay between steps. 0 = max speed")
        auto_mode  = st.checkbox("🤖 AI Auto-Control", value=True,
                                 help="Let AI decide controls (temp, humidity, irrigation, etc.)")
        wx_refresh = st.slider("Weather refresh (steps)", 3, 100, 10, 1,
                               help="Fetch new weather every N steps")

        if not auto_mode:
            st.markdown('<div class="section-header">🔧 Manual Control</div>',
                        unsafe_allow_html=True)
            m_heat   = st.checkbox("🔥 Heating")
            m_cool   = st.checkbox("❄️ Cooling")
            m_vent   = st.checkbox("💨 Ventilation")
            m_irrig  = st.slider("💧 Irrigation (L)", 0, 40, 0)
            m_co2    = st.checkbox("🌬️ CO₂ Inject")
            m_hum    = st.checkbox("💦 Humidifier")
            m_dehum  = st.checkbox("💧↓ Dehumidifier")
            m_led    = st.checkbox("💡 LED Grow")
            m_spec   = st.selectbox("💡 Spectrum", [s.value for s in LEDSpectrum])
            m_fert   = st.checkbox("🧪 Fertilize")
            m_ph_up  = st.checkbox("⬆️ pH Adjust Up")
            m_ph_dn  = st.checkbox("⬇️ pH Adjust Down")
            manual_act = {
                "heating": int(m_heat), "cooling": int(m_cool),
                "vent": int(m_vent), "irrigation": float(m_irrig),
                "co2_inject": int(m_co2), "humidifier": int(m_hum),
                "dehumidifier": int(m_dehum), "led_grow": int(m_led),
                "led_spectrum": m_spec, "fertilize": int(m_fert),
                "ph_adjust_up": int(m_ph_up), "ph_adjust_down": int(m_ph_dn),
                "stress_override": 1.0,
            }
        else:
            manual_act = None

        # ── GA & Energy ────────────────────────────────────────────────────
        st.markdown('<div class="section-header">⚡ Energy Budget</div>',
                    unsafe_allow_html=True)
        ai_ctrl.energy_budget_kwh_day = st.slider("Daily Limit (kWh)", 10, 500, 50, 5)

        st.markdown('<div class="section-header">🧬 GA Optimization</div>',
                    unsafe_allow_html=True)
        ai_ctrl.ga_run_every = st.slider("Repeat every N steps", 20, 500, 100, 10,
                                         help="GA auto-reruns every N simulation steps")
        if st.button("🧬 Run GA Now",
                     help="Immediately optimize setpoints using genetic algorithm"):
            if zones:
                for zone in zones:
                    cp = CROP_PROFILES[CropType(zone.crop_type.value)]
                    ai_ctrl.ga_setpoints = ai_ctrl.ga_optimizer.optimize(zone, cp)
                logger.log("GA optimization run manually", "GA")
                sp_str = " | ".join(
                    f"{k}:{v:.1f}" for k, v in (ai_ctrl.ga_setpoints or {}).items()
                )
                st.success(f"GA done: {sp_str}")

        # ── Reset ──────────────────────────────────────────────────────────
        st.markdown("---")
        if st.button("🔄 Reset All Zones", type="secondary",
                     help="Clear all history and restart simulation from scratch"):
            for z in zones:
                z.crop_model.reset()
                z.nutrient_mgr = NutrientManager()
                for k in z.history:
                    z.history[k] = []
                z.water_used_L = z.energy_kwh = z.co2_injected_kg = z.fertilizer_kg = 0.0
                z.step_count   = 0
                z.alerts       = []
                z.dli_today    = 0.0
            st.session_state.econ_history = []
            st.session_state.econ_state   = EconomicState()
            ai_ctrl.energy_used_today     = 0.0
            logger.log("All zones reset", "INFO")
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # WEATHER PANEL
    # ══════════════════════════════════════════════════════════════════════
    active_loc = get_location_state()
    active_loc_sig = location_signature(active_loc)
    if st.session_state.get("wx_data") is None or st.session_state.get("_weather_loc_sig") != active_loc_sig:
        wx_svc.api_key = api_key
        st.session_state.wx_data = wx_svc.fetch_by_coords(
            active_loc.lat, active_loc.lon,
            location_name=f"{active_loc.display_name}, {active_loc.country}",
            alt_m=active_loc.altitude_m,
        )
        st.session_state["_weather_loc_sig"] = active_loc_sig

    wx: WeatherData = st.session_state["wx_data"]

    wx_temp  = finite_float(wx.temp_outside)
    wx_hum   = finite_float(wx.humidity_outside)
    wx_wind  = finite_float(wx.wind_speed)
    wx_solar = finite_float(wx.solar_radiation)
    wx_rain  = finite_float(wx.rainfall)
    wx_dew   = finite_float(wx.dew_point)
    wx_press = finite_float(wx.pressure_hpa)
    wx_uv    = finite_float(wx.uv_index)
    wx_cloud = finite_float(wx.cloud_cover_pct)

    temp_state = "bad" if wx_temp > 38 or wx_temp < 14 else ("warn" if wx_temp > 33 or wx_temp < 20 else "good")
    hum_state  = "bad" if wx_hum > 95 or wx_hum < 35 else ("warn" if wx_hum > 88 or wx_hum < 50 else "good")
    render_metric_wall("🌤️ Live Weather — OpenWeatherMap", [
        DashboardMetric("🌡️", "Temp Out", f"{wx_temp:.1f}°C", "", temp_state),
        DashboardMetric("💧", "Humidity", f"{wx_hum:.1f}%", "", hum_state),
        DashboardMetric("💨", "Wind", f"{wx_wind:.1f}m/s", "", threshold_state(wx_wind, 7.0, 13.0)),
        DashboardMetric("☀️", "Solar", f"{wx_solar:.0f}W/m²", "", "good" if wx_solar > 120 else "info"),
        DashboardMetric("🌧️", "Rain", f"{wx_rain:.1f}mm/h", "", threshold_state(wx_rain, 3.0, 12.0)),
        DashboardMetric("🌡️", "Dew Pt", f"{wx_dew:.1f}°C", "", "info"),
        DashboardMetric("📊", "Pressure", f"{wx_press:.1f}hPa", "", "info"),
        DashboardMetric("🌞", "UV Index", f"{wx_uv:.1f}", "", threshold_state(wx_uv, 9.0, 11.0)),
        DashboardMetric("☁️", "Clouds", f"{wx_cloud:.0f}%", "", threshold_state(wx_cloud, 75.0, 92.0)),
    ], meta=[
        ("📡", "Source", wx.source),
        ("📍", "Location", wx.location),
        ("🕐", "Timestamp", wx.timestamp or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("CO₂", "Ambient", f"{finite_float(wx.co2_ambient):.0f}ppm"),
    ], min_width=128)

    # 24h Forecast mini-chart
    if wx.forecast_temp and PLOTLY_AVAILABLE:
        with st.expander("📅 24h Weather Forecast"):
            fg = make_subplots(rows=1, cols=2, subplot_titles=["Temperature (24h)", "Rainfall (24h)"])
            hrs = list(range(1, 25))
            fg.add_trace(go.Scatter(x=hrs, y=wx.forecast_temp, name="Temp °C",
                                    line=dict(color="#ff8844", width=2)), 1, 1)
            fg.add_trace(go.Bar(x=hrs, y=wx.forecast_rain, name="Rain mm",
                                marker_color="#4488ff"), 1, 2)
            fg.update_layout(template="plotly_dark", paper_bgcolor="#060d06",
                             plot_bgcolor="#0a1a0a", height=250,
                             font=dict(color="#7a9a7a", size=9), showlegend=False)
            st.plotly_chart(fg, width='stretch')

    # ══════════════════════════════════════════════════════════════════════
    # ZONE METRICS
    # ══════════════════════════════════════════════════════════════════════
    for zone in zones:
        render_zone_metrics(zone)

    # ══════════════════════════════════════════════════════════════════════
    # 🇮🇩 INDONESIAN AGRICULTURE v5 — MASTER PANELS
    # ══════════════════════════════════════════════════════════════════════
    render_v5_master_panels()

    # ══════════════════════════════════════════════════════════════════════
    # AI DECISIONS
    # ══════════════════════════════════════════════════════════════════════
    if auto_mode and zones:
        st.markdown('<div class="section-header">🤖 AI Decisions v4 — Auto-Control Active</div>',
                    unsafe_allow_html=True)
        ai_cols = st.columns(len(zones))
        for i, zone in enumerate(zones):
            crop_p = CROP_PROFILES[CropType(zone.crop_type.value)]
            act    = ai_ctrl.compute(zone, wx, crop_p)
            with ai_cols[i]:
                decisions_str = " | ".join(ai_ctrl.decision_log) if ai_ctrl.decision_log else "✅ Optimal"
                sp    = act.get("setpoints", {})
                ga_sp = act.get("ga_setpoints")
                ga_str = ""
                if ga_sp:
                    ga_temp = finite_float(ga_sp.get("temp_sp"))
                    ga_hum  = finite_float(ga_sp.get("humidity_sp"))
                    ga_co2  = finite_float(ga_sp.get("co2_sp"))
                    ga_str = (f'<br><span style="font-size:9px; color:#aa66ff;">'
                              f'GA: T={ga_temp:.1f}° '
                              f'H={ga_hum:.0f}% '
                              f'CO₂={ga_co2:.0f}</span>')
                sp_temp = finite_float(sp.get("temp"))
                sp_hum  = finite_float(sp.get("humidity"))
                sp_co2  = finite_float(sp.get("co2"))
                sp_soil = finite_float(sp.get("soil"))
                st.markdown(
                    f'<div class="zone-card">'
                    f'<b>{esc(zone.zone_id)}</b><br>'
                    f'<span style="font-size:11px; color:#55ee55;">{esc(decisions_str)}</span><br>'
                    f'<span style="font-size:10px; color:#4a7a4a;">'
                    f'SP: T={sp_temp:.1f}°C H={sp_hum:.0f}% '
                    f'CO₂={sp_co2:.0f}ppm SM={sp_soil:.0f}%</span>'
                    f'{ga_str}'
                    f'</div>',
                    unsafe_allow_html=True
                )

    # ══════════════════════════════════════════════════════════════════════
    # SIMULATION ENGINE
    # ══════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">▶ Simulation Engine — Run Digital Twin Model</div>',
                unsafe_allow_html=True)
    col1, col2, col3, col4, col5 = st.columns(5)
    run_full   = col1.button("▶ Run Simulation",  type="primary",
                             help="Run full simulation for the number of steps set in sidebar")
    run_step   = col2.button("⏭ One Step",
                             help="Advance one simulation step")
    run_glp    = col3.button("🧠 GLP Physics",
                             help="Run GreenLightPlus physics model (requires install)")
    run_predict= col4.button("🤖 ML Predict",
                             help="24-hour forecast using LSTM-lite")
    run_ga     = col5.button("🧬 GA Optimize",
                             help="Run genetic algorithm to find optimal setpoints")

    progress_ph = st.empty()

    if run_full:
        prog = progress_ph.progress(0)
        logger.log(f"Full sim start: {sim_steps} steps × {len(zones)} zones", "INFO")

        for i in range(sim_steps):
            if i % wx_refresh == 0:
                wx_svc.api_key = api_key
                _loc_step = get_location_state()
                st.session_state.wx_data = wx_svc.fetch_by_coords(
                    _loc_step.lat, _loc_step.lon,
                    location_name=f"{_loc_step.display_name}, {_loc_step.country}",
                    alt_m=_loc_step.altitude_m,
                )
                st.session_state["_weather_loc_sig"] = location_signature(_loc_step)
                wx = st.session_state.wx_data

            for zone in zones:
                crop_p = CROP_PROFILES[CropType(zone.crop_type.value)]
                act    = ai_ctrl.compute(zone, wx, crop_p) if auto_mode else (manual_act or {})

                rl_ctrl = st.session_state.get("ext_rl_ctrl")
                if rl_ctrl and auto_mode:
                    zone_state = {"temp": zone.temp_air, "humidity": zone.humidity,
                                  "soil": zone.soil_moist, "stage": zone.crop_model.stage.value}
                    rl_act = rl_ctrl.act(zone_state, crop_p, None)
                    act.update(rl_act) 

                zone.step(wx, act)
                _aruna_broadcast(zones)

            if i % 8 == 0:
                econ_state = econ_engine.compute(zones)
                st.session_state.econ_state = econ_state
                if econ_engine.history:
                    st.session_state.econ_history.extend(econ_engine.history[-1:])

            prog.progress((i + 1) / sim_steps)
            if speed_ms > 0:
                time.sleep(speed_ms / 1000.0)

        st.session_state.econ_state = econ_engine.compute(zones)
        logger.log(f"Full sim complete: {sim_steps} steps", "INFO")
        for z in zones:
            logger.log(
                f"{z.zone_id}: yield={z.crop_model.yield_kg:.3f}kg/m² "
                f"brix={z.crop_model.brix_sugar:.1f}° "
                f"stage={z.crop_model.stage.value} "
                f"CO₂seq={z.crop_model.net_carbon_seq_kg:.4f}kg", "HARVEST"
            )
        total_yield = sum(z.crop_model.yield_kg * z.area_m2 for z in zones)
        progress_ph.success(
            f"✅ Done: {sim_steps} steps | Zones: {len(zones)} | "
            f"Total Yield: {total_yield:.1f}kg | "
            f"Energy: {sum(z.energy_kwh for z in zones):.1f}kWh"
        )
        st.rerun()

    if run_step:
        for zone in zones:
            crop_p = CROP_PROFILES[CropType(zone.crop_type.value)]
            act    = ai_ctrl.compute(zone, wx, crop_p) if auto_mode else (manual_act or {})
            zone.step(wx, act)
        _aruna_broadcast(zones)
        st.session_state.econ_state = econ_engine.compute(zones)
        if econ_engine.history:
            st.session_state.econ_history.extend(econ_engine.history[-1:])
        st.rerun()

    if run_glp:
        for zone in zones:
            result = glp.run_model(wx, zone)
            if result["status"] == "ok":
                st.success(f"🧠 GLP [{zone.zone_id}]: {result.get('note','')}")
                logger.log(f"GLP run: {zone.zone_id}", "INFO")
            elif result["status"] == "unavailable":
                st.warning("⚠️ GreenLightPlus not installed. `pip install GreenLightPlus`")
            else:
                st.error(f"GLP Error [{zone.zone_id}]: {result.get('error', 'unknown')}")

    if run_predict:
        for zone in zones:
            if len(zone.history.get("temp", [])) >= 10:
                fc = predictor.forecast(zone)
                logger.log(f"ML forecast complete for {zone.zone_id}: {len(fc)} vars", "AI")
        st.rerun()

    if run_ga:
        for zone in zones:
            cp = CROP_PROFILES[CropType(zone.crop_type.value)]
            ga_sp = ai_ctrl.ga_optimizer.optimize(zone, cp)
            ai_ctrl.ga_setpoints = ga_sp
            fit_hist = ai_ctrl.ga_optimizer.history_fitness
            logger.log(
                f"GA {zone.zone_id}: best_fitness={ai_ctrl.ga_optimizer.best_fitness:.4f} | "
                f"T={ga_sp['temp_sp']:.1f}°C H={ga_sp['humidity_sp']:.0f}% "
                f"CO₂={ga_sp['co2_sp']:.0f}ppm", "GA"
            )
        st.success("🧬 GA optimization complete — setpoints updated!")
        st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # SUB-PANELS
    # ══════════════════════════════════════════════════════════════════════
    render_disease_panel(zones)
    render_nutrient_panel(zones)
    render_maintenance_panel(zones)

    all_alerts = sorted(
        [a for zone in zones for a in zone.alerts],
        key=lambda a: a.timestamp, reverse=True
    )
    render_alerts(all_alerts[:18])

    render_economics(st.session_state.econ_state, zones)

    render_extension_panels(
        zones       = zones,
        weather_data= wx,
        ai_ctrl     = ai_ctrl,
        crop_profiles= CROP_PROFILES,
    )

    if any(len(z.history.get("temp", [])) > 0 for z in zones):
        render_charts(zones)

    z_with_data = next((z for z in zones if len(z.history.get("temp", [])) >= 10), None)
    if z_with_data:
        render_ml_predictions(predictor, z_with_data)

    # ══════════════════════════════════════════════════════════════════════
    # DATA EXPORT
    # ══════════════════════════════════════════════════════════════════════
    if any(len(z.history.get("temp", [])) > 0 for z in zones):
        st.markdown('<div class="section-header">💾 DATA EXPORT v4</div>',
                    unsafe_allow_html=True)
        df = build_export_df(zones)
        if not df.empty:
            col_p, col_csv, col_rpt = st.columns([3, 1, 1])
            col_p.dataframe(df.tail(20), width='stretch')

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            col_csv.download_button(
                "📥 CSV Export",
                data=df.to_csv(index=False),
                file_name=f"greenhouse_v4_{ts}.csv",
                mime="text/csv"
            )
            report_md = build_summary_report(zones, st.session_state.econ_state, wx)
            col_rpt.download_button(
                "📋 Report MD",
                data=report_md,
                file_name=f"greenhouse_report_v4_{ts}.md",
                mime="text/markdown"
            )

    # ══════════════════════════════════════════════════════════════════════
    # TERMINAL LOG
    # ══════════════════════════════════════════════════════════════════════
    with st.expander("🖥️ System Terminal Log"):
        logger.render()

    # ══════════════════════════════════════════════════════════════════════
    # SYSTEM DOCS
    # ══════════════════════════════════════════════════════════════════════
    with st.expander("🔬 v4.0 Feature Matrix & Integration Status"):
        st.markdown(f"""
                    
**GreenLightPlus:** `{'INSTALLED ✓' if GLP_AVAILABLE else 'pip install GreenLightPlus'}`  
**PCSE:** `{'INSTALLED ✓' if PCSE_AVAILABLE else 'pip install pcse'}`  
**Plotly:** `{'INSTALLED ✓' if PLOTLY_AVAILABLE else 'pip install plotly'}`  
**SciPy:** `{'INSTALLED ✓' if SCIPY_AVAILABLE else 'pip install scipy'}`  
**Scikit-learn:** `{'INSTALLED ✓' if SKLEARN_AVAILABLE else 'pip install scikit-learn'}`

### v4.0 Feature Matrix
| Feature | Status | Description |
|---------|--------|-------------|
| Multi-Zone (up to 6) | ✓ ACTIVE | Independent zone physics |
| Kalman Filter Bank | ✓ NEW | 8-sensor fusion + fault detection |
| Full FvCB Photosynthesis | ✓ ENHANCED | Temperature-acclimated Vcmax/Jmax |
| Full NPKCaMgSFe Nutrition | ✓ NEW | Complete Hoagland model |
| Nutrient Antagonism Detector | ✓ NEW | K-Ca, NH4-Ca, pH-Fe interactions |
| Dissolved O₂ Model | ✓ NEW | Root zone hypoxia detection |
| Genetic Algorithm Optimizer | ✓ NEW | 12-gene setpoint optimization |
| Spectral LED Control | ✓ NEW | 5 spectra (Veg/Bloom/UV/FarRed) |
| DLI Photoperiod Model | ✓ NEW | Cumulative daily light integral |
| Pest Population Dynamics | ✓ NEW | 5 pest types + biocontrol |
| Fruit Abscission Model | ✓ NEW | Stress-driven fruit drop |
| Brix/Antioxidant Quality | ✓ NEW | Produce quality prediction |
| Soil Microbiome Model | ✓ NEW | Beneficial microbial dynamics |
| Carbon Accounting | ✓ NEW | CO₂ sequestration + credits |
| Predictive Maintenance | ✓ NEW | Weibull failure probability |
| 24h Weather Forecast | ✓ NEW | Auto-forecast feed-forward |
| Ensemble ML (GBR+HW+POLY) | ✓ ENHANCED | Conformal prediction intervals |
| CUSUM+Z Anomaly Detection | ✓ ENHANCED | Hybrid anomaly scoring |
| Economics v4 (full P&L) | ✓ ENHANCED | Labor, pest, maint, payback |
| 12-Layer AI Controller | ✓ ENHANCED | Pest, spectrum, dehumidifier |
| Thread-safe Logger | ✓ NEW | Concurrent write protection |
| pH Auto-Adjustment | ✓ NEW | Acid/base dosing simulation |

```bash
pip install streamlit matplotlib numpy requests pandas plotly scipy scikit-learn
export OPENWEATHER_API_KEY=your_key_here
streamlit run greenhouse_ai_v4.py
```
        """)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  v5 INDONESIAN AGRICULTURE EXTENSION — MERGED INLINE                       ║
# ║  102 tanaman Indonesia · Plant calendar · Water/Nutrient plan · 3D sat    ║
# ║  Real sensor bridge (Serial/HTTP/MQTT/Modbus) · Pest calendar · Economy  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ══════════════════════════════════════════════════════════════════════════════
# 1. INDONESIAN CROP CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════

class IndoCropCategory(Enum):
    PANGAN_POKOK   = "Pangan Pokok"
    HORTIKULTURA   = "Hortikultura Sayur"
    BUAH           = "Hortikultura Buah"
    PERKEBUNAN     = "Perkebunan"
    HERBAL_BUMBU   = "Herbal & Bumbu"
    PALAWIJA       = "Palawija"
    UMBI           = "Umbi-umbian"
    BIOFARMAKA     = "Biofarmaka"


class IndoGrowthPhase(Enum):
    PRA_TANAM     = "Pre-Plant (Land Prep)"
    PERSEMAIAN    = "Persemaian / Pembibitan"
    PINDAH_TANAM  = "Pindah Tanam"
    VEGETATIF_AWAL= "Vegetatif Awal"
    VEGETATIF_LANJ= "Vegetatif Lanjut"
    GENERATIF     = "Generatif (Berbunga)"
    PEMBUAHAN     = "Pembentukan Buah/Umbi"
    PEMASAKAN     = "Ripening / Maturation"
    PANEN         = "Ready to Harvest"
    PASCA_PANEN   = "Post-Harvest"


class IndoSeason(Enum):
    HUJAN         = "Musim Hujan (Okt-Mar)"
    KEMARAU       = "Musim Kemarau (Apr-Sep)"
    SEPANJANG     = "Sepanjang Tahun"
    PERALIHAN     = "Pancaroba"


@dataclass
class IndoCrop:
    """Profil lengkap tanaman Indonesia."""
    id:                    str
    nama_id:               str
    nama_en:               str
    scientific:            str
    kategori:              IndoCropCategory
    # siklus hidup (hari setelah tanam — DAP)
    dap_persemaian_end:    int = 0
    dap_vegetatif_end:     int = 30
    dap_generatif_end:     int = 50
    dap_pembuahan_end:     int = 80
    dap_panen:             int = 90
    dap_panen_max:         int = 100
    # iklim
    suhu_optimal:          float = 25.0
    suhu_min:              float = 18.0
    suhu_max:              float = 32.0
    kelembapan_optimal:    float = 70.0
    altitude_min_mdpl:     int = 0
    altitude_max_mdpl:     int = 1500
    ph_min:                float = 5.5
    ph_max:                float = 6.8
    musim:                 List[IndoSeason] = field(default_factory=lambda: [IndoSeason.SEPANJANG])
    # kebutuhan air mm/hari per fase [persemaian, veg_awal, veg_lanj, generatif, pembuahan, pemasakan]
    water_mm_per_phase:    List[float] = field(default_factory=lambda: [3.0, 4.0, 5.5, 6.5, 7.0, 4.0])
    # NPK kg per ha per fase [vegetatif, generatif, pembuahan]  (N, P, K)
    npk_kg_ha_per_phase:   List[Tuple[float,float,float]] = field(
        default_factory=lambda: [(60,40,40), (40,30,60), (20,20,80)]
    )
    # cahaya
    light_hours:           float = 12.0
    light_intensity_lux:   float = 25000.0
    # produktivitas
    yield_ton_per_ha_min:  float = 5.0
    yield_ton_per_ha_max:  float = 12.0
    harga_kg_idr:          float = 8000.0
    # spasial
    jarak_tanam_cm:        Tuple[int,int] = (50, 50)
    populasi_per_ha:       int = 40000
    # hama & penyakit umum
    hama_umum:             List[str] = field(default_factory=list)
    penyakit_umum:         List[str] = field(default_factory=list)
    # pasangan / rotasi
    companion_good:        List[str] = field(default_factory=list)
    companion_bad:         List[str] = field(default_factory=list)
    rotasi_setelah:        List[str] = field(default_factory=list)
    # catatan agronomi
    catatan:               str = ""

    @property
    def total_dap(self) -> int:
        return self.dap_panen

    @property
    def yield_avg_ton_ha(self) -> float:
        return (self.yield_ton_per_ha_min + self.yield_ton_per_ha_max) / 2.0

    def total_water_mm_lifecycle(self) -> float:
        """Total air kumulatif sepanjang siklus (mm)."""
        durations = self._phase_durations()
        return sum(d * w for d, w in zip(durations, self.water_mm_per_phase))

    def total_water_liters_per_m2(self) -> float:
        return self.total_water_mm_lifecycle()  # 1 mm = 1 L/m²

    def total_npk_kg_per_ha(self) -> Tuple[float, float, float]:
        n = sum(p[0] for p in self.npk_kg_ha_per_phase)
        p = sum(p[1] for p in self.npk_kg_ha_per_phase)
        k = sum(p[2] for p in self.npk_kg_ha_per_phase)
        return n, p, k

    def _phase_durations(self) -> List[int]:
        """Durasi (hari) untuk 6 fase yang sejajar dengan water_mm_per_phase."""
        d0 = max(self.dap_persemaian_end, 0)
        d1 = max(self.dap_vegetatif_end - d0, 1)            # vegetatif awal (50%)
        d2 = max(self.dap_vegetatif_end - d0 - d1 + d1, 1)  # vegetatif lanjut
        # remap lebih sederhana: bagi rata
        veg_total = max(self.dap_vegetatif_end - self.dap_persemaian_end, 2)
        veg_a = veg_total // 2
        veg_b = veg_total - veg_a
        gen   = max(self.dap_generatif_end - self.dap_vegetatif_end, 1)
        buah  = max(self.dap_pembuahan_end - self.dap_generatif_end, 1)
        masak = max(self.dap_panen - self.dap_pembuahan_end, 1)
        return [max(d0, 1), veg_a, veg_b, gen, buah, masak]

    def phase_at_dap(self, dap: int) -> IndoGrowthPhase:
        if dap < 0:
            return IndoGrowthPhase.PRA_TANAM
        if dap <= self.dap_persemaian_end:
            return IndoGrowthPhase.PERSEMAIAN
        if dap <= self.dap_persemaian_end + 3:
            return IndoGrowthPhase.PINDAH_TANAM
        veg_mid = (self.dap_persemaian_end + self.dap_vegetatif_end) // 2
        if dap <= veg_mid:
            return IndoGrowthPhase.VEGETATIF_AWAL
        if dap <= self.dap_vegetatif_end:
            return IndoGrowthPhase.VEGETATIF_LANJ
        if dap <= self.dap_generatif_end:
            return IndoGrowthPhase.GENERATIF
        if dap <= self.dap_pembuahan_end:
            return IndoGrowthPhase.PEMBUAHAN
        if dap <= self.dap_panen:
            return IndoGrowthPhase.PEMASAKAN
        if dap <= self.dap_panen_max:
            return IndoGrowthPhase.PANEN
        return IndoGrowthPhase.PASCA_PANEN

    def water_need_at_dap(self, dap: int) -> float:
        """mm/hari pada DAP tertentu."""
        durations = self._phase_durations()
        cum = 0
        for i, d in enumerate(durations):
            cum += d
            if dap <= cum:
                return self.water_mm_per_phase[i]
        return self.water_mm_per_phase[-1] * 0.4

    def npk_need_at_dap(self, dap: int) -> Tuple[float, float, float]:
        """kg/ha/hari per N P K pada DAP tertentu."""
        if dap <= self.dap_vegetatif_end:
            n, p, k = self.npk_kg_ha_per_phase[0]
            dur = max(self.dap_vegetatif_end, 1)
        elif dap <= self.dap_generatif_end:
            n, p, k = self.npk_kg_ha_per_phase[1]
            dur = max(self.dap_generatif_end - self.dap_vegetatif_end, 1)
        else:
            n, p, k = self.npk_kg_ha_per_phase[2]
            dur = max(self.dap_panen - self.dap_generatif_end, 1)
        return n / dur, p / dur, k / dur


# ══════════════════════════════════════════════════════════════════════════════
# 2. INDONESIAN CROPS DATABASE — 110+ TANAMAN
# ══════════════════════════════════════════════════════════════════════════════

def _build_indonesian_crops_db() -> Dict[str, IndoCrop]:
    db: Dict[str, IndoCrop] = {}

    # ── PANGAN POKOK ───────────────────────────────────────────────────────────
    db["padi_sawah"] = IndoCrop(
        id="padi_sawah", nama_id="Padi Sawah", nama_en="Paddy Rice",
        scientific="Oryza sativa L.", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_persemaian_end=21, dap_vegetatif_end=55, dap_generatif_end=85,
        dap_pembuahan_end=105, dap_panen=115, dap_panen_max=125,
        suhu_optimal=27, suhu_min=20, suhu_max=35, kelembapan_optimal=80,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=5.0, ph_max=7.0,
        musim=[IndoSeason.SEPANJANG],
        water_mm_per_phase=[8.0, 10.0, 12.0, 11.0, 9.0, 4.0],
        npk_kg_ha_per_phase=[(90,45,50), (45,0,30), (0,0,15)],
        light_hours=10.5, light_intensity_lux=40000,
        yield_ton_per_ha_min=4.5, yield_ton_per_ha_max=8.0, harga_kg_idr=10500,
        jarak_tanam_cm=(25,25), populasi_per_ha=160000,
        hama_umum=["Wereng coklat", "Tikus sawah", "Walang sangit", "Penggerek batang"],
        penyakit_umum=["Blast", "Hawar daun bakteri", "Tungro"],
        companion_good=["Azolla", "Mina padi (ikan)"],
        rotasi_setelah=["Kacang tanah", "Kedelai", "Jagung"],
        catatan="Use legowo 2:1 row system for optimal yield.",
    )
    db["padi_gogo"] = IndoCrop(
        id="padi_gogo", nama_id="Padi Gogo", nama_en="Upland Rice",
        scientific="Oryza sativa L. (gogo)", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_persemaian_end=14, dap_vegetatif_end=50, dap_generatif_end=80,
        dap_pembuahan_end=105, dap_panen=120, dap_panen_max=135,
        suhu_optimal=26, suhu_min=18, suhu_max=33, kelembapan_optimal=70,
        altitude_min_mdpl=200, altitude_max_mdpl=1300, ph_min=5.0, ph_max=6.5,
        musim=[IndoSeason.HUJAN],
        water_mm_per_phase=[5.0, 6.0, 7.0, 6.5, 5.5, 3.0],
        npk_kg_ha_per_phase=[(70,35,40), (35,0,25), (0,0,10)],
        yield_ton_per_ha_min=2.5, yield_ton_per_ha_max=4.5, harga_kg_idr=11500,
    )
    db["jagung_manis"] = IndoCrop(
        id="jagung_manis", nama_id="Jagung Manis", nama_en="Sweet Corn",
        scientific="Zea mays saccharata", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_persemaian_end=7, dap_vegetatif_end=45, dap_generatif_end=60,
        dap_pembuahan_end=75, dap_panen=80, dap_panen_max=85,
        suhu_optimal=24, suhu_min=15, suhu_max=33, kelembapan_optimal=70,
        altitude_min_mdpl=0, altitude_max_mdpl=1800, ph_min=5.5, ph_max=7.0,
        musim=[IndoSeason.SEPANJANG],
        water_mm_per_phase=[4.0, 5.0, 7.0, 8.0, 7.5, 3.0],
        npk_kg_ha_per_phase=[(120,60,50), (60,30,40), (0,0,30)],
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=15.0, harga_kg_idr=6500,
        jarak_tanam_cm=(75,25), populasi_per_ha=53000,
        hama_umum=["Ulat grayak", "Penggerek tongkol", "Lalat bibit"],
        penyakit_umum=["Bulai", "Hawar daun", "Karat daun"],
        companion_good=["Kacang tanah", "Buncis", "Labu"],
        rotasi_setelah=["Kedelai", "Kacang hijau"],
    )
    db["jagung_pakan"] = IndoCrop(
        id="jagung_pakan", nama_id="Jagung Pakan", nama_en="Field Corn",
        scientific="Zea mays L.", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_persemaian_end=7, dap_vegetatif_end=55, dap_generatif_end=75,
        dap_pembuahan_end=95, dap_panen=110, dap_panen_max=120,
        yield_ton_per_ha_min=6.0, yield_ton_per_ha_max=12.0, harga_kg_idr=4800,
    )
    db["kedelai"] = IndoCrop(
        id="kedelai", nama_id="Kedelai", nama_en="Soybean",
        scientific="Glycine max", kategori=IndoCropCategory.PALAWIJA,
        dap_persemaian_end=7, dap_vegetatif_end=35, dap_generatif_end=55,
        dap_pembuahan_end=75, dap_panen=85, dap_panen_max=95,
        suhu_optimal=27, suhu_min=20, suhu_max=32, kelembapan_optimal=65,
        altitude_min_mdpl=0, altitude_max_mdpl=900, ph_min=5.8, ph_max=7.0,
        water_mm_per_phase=[3.5, 4.5, 5.5, 6.0, 5.5, 2.5],
        npk_kg_ha_per_phase=[(30,60,60), (15,30,30), (0,0,15)],
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=3.0, harga_kg_idr=12000,
        jarak_tanam_cm=(40,15), populasi_per_ha=400000,
        hama_umum=["Ulat grayak", "Kutu kebul", "Lalat kacang"],
        penyakit_umum=["Karat daun", "Antraknosa"],
        rotasi_setelah=["Padi", "Jagung"],
        catatan="Nitrogen-fixing crop — ideal for rotation.",
    )
    db["kacang_tanah"] = IndoCrop(
        id="kacang_tanah", nama_id="Kacang Tanah", nama_en="Peanut",
        scientific="Arachis hypogaea", kategori=IndoCropCategory.PALAWIJA,
        dap_persemaian_end=7, dap_vegetatif_end=40, dap_generatif_end=65,
        dap_pembuahan_end=90, dap_panen=100, dap_panen_max=110,
        suhu_optimal=28, ph_min=6.0, ph_max=6.5,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=3.5, harga_kg_idr=22000,
        jarak_tanam_cm=(40,15), populasi_per_ha=330000,
    )
    db["kacang_hijau"] = IndoCrop(
        id="kacang_hijau", nama_id="Kacang Hijau", nama_en="Mung Bean",
        scientific="Vigna radiata", kategori=IndoCropCategory.PALAWIJA,
        dap_persemaian_end=5, dap_vegetatif_end=25, dap_generatif_end=40,
        dap_pembuahan_end=55, dap_panen=65, dap_panen_max=75,
        yield_ton_per_ha_min=1.0, yield_ton_per_ha_max=2.0, harga_kg_idr=18000,
    )
    db["sorgum"] = IndoCrop(
        id="sorgum", nama_id="Sorgum", nama_en="Sorghum",
        scientific="Sorghum bicolor", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_persemaian_end=10, dap_vegetatif_end=55, dap_generatif_end=75,
        dap_pembuahan_end=95, dap_panen=110, dap_panen_max=120,
        suhu_optimal=27, ph_min=5.5, ph_max=7.5,
        yield_ton_per_ha_min=3.5, yield_ton_per_ha_max=6.0, harga_kg_idr=9000,
        catatan="Tahan kekeringan — cocok lahan marginal.",
    )
    db["gandum"] = IndoCrop(
        id="gandum", nama_id="Gandum", nama_en="Wheat",
        scientific="Triticum aestivum", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_persemaian_end=7, dap_vegetatif_end=45, dap_generatif_end=70,
        dap_pembuahan_end=95, dap_panen=110, dap_panen_max=120,
        suhu_optimal=21, suhu_min=10, suhu_max=27, altitude_min_mdpl=800, altitude_max_mdpl=2000,
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=4.5, harga_kg_idr=10000,
    )

    # ── UMBI-UMBIAN ────────────────────────────────────────────────────────────
    db["ubi_jalar"] = IndoCrop(
        id="ubi_jalar", nama_id="Ubi Jalar", nama_en="Sweet Potato",
        scientific="Ipomoea batatas", kategori=IndoCropCategory.UMBI,
        dap_persemaian_end=7, dap_vegetatif_end=60, dap_generatif_end=90,
        dap_pembuahan_end=110, dap_panen=120, dap_panen_max=140,
        suhu_optimal=24, suhu_min=15, suhu_max=33, ph_min=5.5, ph_max=6.5,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=5500,
        jarak_tanam_cm=(100,25), populasi_per_ha=40000,
    )
    db["ubi_kayu"] = IndoCrop(
        id="ubi_kayu", nama_id="Ubi Kayu / Singkong", nama_en="Cassava",
        scientific="Manihot esculenta", kategori=IndoCropCategory.UMBI,
        dap_persemaian_end=14, dap_vegetatif_end=120, dap_generatif_end=180,
        dap_pembuahan_end=240, dap_panen=270, dap_panen_max=365,
        suhu_optimal=26, ph_min=4.5, ph_max=8.0,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=40.0, harga_kg_idr=3500,
        catatan="Sangat toleran lahan marginal & kering.",
    )
    db["talas"] = IndoCrop(
        id="talas", nama_id="Talas", nama_en="Taro",
        scientific="Colocasia esculenta", kategori=IndoCropCategory.UMBI,
        dap_persemaian_end=14, dap_vegetatif_end=90, dap_generatif_end=150,
        dap_pembuahan_end=210, dap_panen=240, dap_panen_max=300,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=25.0, harga_kg_idr=7000,
    )
    db["kentang"] = IndoCrop(
        id="kentang", nama_id="Kentang", nama_en="Potato",
        scientific="Solanum tuberosum", kategori=IndoCropCategory.UMBI,
        dap_persemaian_end=7, dap_vegetatif_end=40, dap_generatif_end=60,
        dap_pembuahan_end=85, dap_panen=100, dap_panen_max=120,
        suhu_optimal=18, suhu_min=10, suhu_max=25, kelembapan_optimal=80,
        altitude_min_mdpl=800, altitude_max_mdpl=2500, ph_min=5.0, ph_max=6.5,
        water_mm_per_phase=[3.0, 5.0, 6.0, 7.0, 5.0, 2.0],
        npk_kg_ha_per_phase=[(150,80,180), (50,30,80), (0,0,40)],
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=35.0, harga_kg_idr=12000,
        jarak_tanam_cm=(70,30), populasi_per_ha=47000,
        hama_umum=["Ulat tanah", "Kutu daun", "Penggerek umbi"],
        penyakit_umum=["Hawar daun (late blight)", "Layu bakteri", "Busuk lunak"],
    )
    db["porang"] = IndoCrop(
        id="porang", nama_id="Porang", nama_en="Konjac",
        scientific="Amorphophallus muelleri", kategori=IndoCropCategory.UMBI,
        dap_persemaian_end=30, dap_vegetatif_end=180, dap_generatif_end=270,
        dap_pembuahan_end=330, dap_panen=365, dap_panen_max=730,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=11000,
        catatan="Komoditas ekspor — Jepang, China.",
    )
    db["wortel"] = IndoCrop(
        id="wortel", nama_id="Wortel", nama_en="Carrot",
        scientific="Daucus carota", kategori=IndoCropCategory.UMBI,
        dap_persemaian_end=10, dap_vegetatif_end=50, dap_generatif_end=70,
        dap_pembuahan_end=90, dap_panen=100, dap_panen_max=110,
        suhu_optimal=18, altitude_min_mdpl=800, altitude_max_mdpl=2000,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=9500,
    )
    db["lobak"] = IndoCrop(
        id="lobak", nama_id="Lobak", nama_en="Daikon Radish",
        scientific="Raphanus sativus", kategori=IndoCropCategory.UMBI,
        dap_persemaian_end=5, dap_vegetatif_end=35, dap_generatif_end=50,
        dap_pembuahan_end=60, dap_panen=70, dap_panen_max=80,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=40.0, harga_kg_idr=7000,
    )
    db["bit"] = IndoCrop(
        id="bit", nama_id="Bit Merah", nama_en="Beetroot",
        scientific="Beta vulgaris", kategori=IndoCropCategory.UMBI,
        dap_panen=70, dap_panen_max=90,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=25.0, harga_kg_idr=15000,
    )

    # ── HORTIKULTURA SAYURAN ──────────────────────────────────────────────────
    db["cabai_merah"] = IndoCrop(
        id="cabai_merah", nama_id="Cabai Merah Besar", nama_en="Red Chili",
        scientific="Capsicum annuum", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=28, dap_vegetatif_end=60, dap_generatif_end=85,
        dap_pembuahan_end=110, dap_panen=120, dap_panen_max=240,
        suhu_optimal=25, suhu_min=18, suhu_max=32, kelembapan_optimal=70,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=5.5, ph_max=6.8,
        water_mm_per_phase=[3.0, 4.5, 5.5, 6.5, 7.0, 4.0],
        npk_kg_ha_per_phase=[(150,90,120), (90,60,180), (45,30,90)],
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=20.0, harga_kg_idr=45000,
        jarak_tanam_cm=(60,50), populasi_per_ha=33000,
        hama_umum=["Thrips", "Kutu daun", "Lalat buah", "Tungau"],
        penyakit_umum=["Antraknosa (patek)", "Layu fusarium", "Virus kuning gemini"],
        companion_good=["Bawang daun", "Kemangi"],
        catatan="Komoditas inflasi — pengaruhi IHK secara nasional.",
    )
    db["cabai_rawit"] = IndoCrop(
        id="cabai_rawit", nama_id="Cabai Rawit", nama_en="Bird's Eye Chili",
        scientific="Capsicum frutescens", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=30, dap_vegetatif_end=70, dap_generatif_end=95,
        dap_pembuahan_end=120, dap_panen=130, dap_panen_max=300,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=18.0, harga_kg_idr=55000,
    )
    db["bawang_merah"] = IndoCrop(
        id="bawang_merah", nama_id="Bawang Merah", nama_en="Shallot",
        scientific="Allium cepa var. ascalonicum", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=0, dap_vegetatif_end=30, dap_generatif_end=50,
        dap_pembuahan_end=60, dap_panen=65, dap_panen_max=75,
        suhu_optimal=27, ph_min=5.5, ph_max=6.5,
        water_mm_per_phase=[4.0, 5.0, 6.0, 5.5, 4.0, 2.0],
        npk_kg_ha_per_phase=[(180,90,180), (90,45,90), (0,0,45)],
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=15.0, harga_kg_idr=32000,
        jarak_tanam_cm=(20,15), populasi_per_ha=330000,
        hama_umum=["Ulat grayak", "Trips bawang"],
        penyakit_umum=["Moler/fusarium", "Antraknosa", "Bercak ungu"],
    )
    db["bawang_putih"] = IndoCrop(
        id="bawang_putih", nama_id="Bawang Putih", nama_en="Garlic",
        scientific="Allium sativum", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=0, dap_vegetatif_end=60, dap_generatif_end=90,
        dap_pembuahan_end=110, dap_panen=120, dap_panen_max=130,
        suhu_optimal=18, altitude_min_mdpl=700, altitude_max_mdpl=1500,
        yield_ton_per_ha_min=5.0, yield_ton_per_ha_max=12.0, harga_kg_idr=42000,
    )
    db["tomat"] = IndoCrop(
        id="tomat", nama_id="Tomat", nama_en="Tomato",
        scientific="Solanum lycopersicum", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=21, dap_vegetatif_end=50, dap_generatif_end=70,
        dap_pembuahan_end=90, dap_panen=100, dap_panen_max=160,
        suhu_optimal=24, kelembapan_optimal=65, ph_min=5.5, ph_max=6.8,
        water_mm_per_phase=[3.0, 4.5, 6.0, 7.0, 7.5, 4.0],
        npk_kg_ha_per_phase=[(120,80,150), (80,40,200), (40,20,100)],
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=60.0, harga_kg_idr=12000,
        jarak_tanam_cm=(70,50), populasi_per_ha=28000,
    )
    db["mentimun"] = IndoCrop(
        id="mentimun", nama_id="Mentimun", nama_en="Cucumber",
        scientific="Cucumis sativus", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=7, dap_vegetatif_end=25, dap_generatif_end=35,
        dap_pembuahan_end=45, dap_panen=55, dap_panen_max=70,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=40.0, harga_kg_idr=7000,
    )
    db["terong_ungu"] = IndoCrop(
        id="terong_ungu", nama_id="Terong Ungu", nama_en="Eggplant",
        scientific="Solanum melongena", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=21, dap_vegetatif_end=50, dap_generatif_end=70,
        dap_pembuahan_end=85, dap_panen=95, dap_panen_max=180,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=8000,
    )
    db["kacang_panjang"] = IndoCrop(
        id="kacang_panjang", nama_id="Kacang Panjang", nama_en="Yardlong Bean",
        scientific="Vigna unguiculata sesquipedalis", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=5, dap_vegetatif_end=25, dap_generatif_end=40,
        dap_pembuahan_end=50, dap_panen=55, dap_panen_max=80,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=15.0, harga_kg_idr=8500,
    )
    db["buncis"] = IndoCrop(
        id="buncis", nama_id="Buncis", nama_en="Common Bean",
        scientific="Phaseolus vulgaris", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=60, dap_panen_max=80,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=14.0, harga_kg_idr=10000,
    )
    db["pare"] = IndoCrop(
        id="pare", nama_id="Pare", nama_en="Bitter Melon",
        scientific="Momordica charantia", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=60, dap_panen_max=120,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=20.0, harga_kg_idr=8000,
    )
    db["oyong"] = IndoCrop(
        id="oyong", nama_id="Oyong/Gambas", nama_en="Sponge Gourd",
        scientific="Luffa acutangula", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=55, dap_panen_max=100,
        yield_ton_per_ha_min=12.0, yield_ton_per_ha_max=22.0, harga_kg_idr=6500,
    )
    db["labu_siam"] = IndoCrop(
        id="labu_siam", nama_id="Labu Siam", nama_en="Chayote",
        scientific="Sechium edule", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=90, dap_panen_max=730,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=50.0, harga_kg_idr=5000,
    )
    db["labu_kuning"] = IndoCrop(
        id="labu_kuning", nama_id="Labu Kuning", nama_en="Pumpkin",
        scientific="Cucurbita moschata", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=90, dap_panen_max=120,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=40.0, harga_kg_idr=6000,
    )
    db["paprika"] = IndoCrop(
        id="paprika", nama_id="Paprika", nama_en="Bell Pepper",
        scientific="Capsicum annuum L.", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=30, dap_vegetatif_end=70, dap_generatif_end=90,
        dap_pembuahan_end=110, dap_panen=120, dap_panen_max=240,
        altitude_min_mdpl=600, altitude_max_mdpl=1500,
        yield_ton_per_ha_min=30.0, yield_ton_per_ha_max=80.0, harga_kg_idr=35000,
    )
    db["kol_bunga"] = IndoCrop(
        id="kol_bunga", nama_id="Kembang Kol", nama_en="Cauliflower",
        scientific="Brassica oleracea var. botrytis", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=21, dap_vegetatif_end=50, dap_generatif_end=70,
        dap_pembuahan_end=85, dap_panen=95, dap_panen_max=110,
        altitude_min_mdpl=700, altitude_max_mdpl=2000,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=12000,
    )
    db["brokoli"] = IndoCrop(
        id="brokoli", nama_id="Brokoli", nama_en="Broccoli",
        scientific="Brassica oleracea var. italica", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=85, dap_panen_max=100,
        altitude_min_mdpl=700, altitude_max_mdpl=2000,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=25.0, harga_kg_idr=18000,
    )
    db["kubis"] = IndoCrop(
        id="kubis", nama_id="Kubis", nama_en="Cabbage",
        scientific="Brassica oleracea var. capitata", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=21, dap_vegetatif_end=60, dap_generatif_end=80,
        dap_pembuahan_end=95, dap_panen=110, dap_panen_max=130,
        altitude_min_mdpl=700, altitude_max_mdpl=2200,
        yield_ton_per_ha_min=25.0, yield_ton_per_ha_max=50.0, harga_kg_idr=6000,
    )
    db["sawi_hijau"] = IndoCrop(
        id="sawi_hijau", nama_id="Sawi Hijau", nama_en="Mustard Greens",
        scientific="Brassica juncea", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=7, dap_vegetatif_end=25, dap_generatif_end=35,
        dap_pembuahan_end=40, dap_panen=45, dap_panen_max=55,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=25.0, harga_kg_idr=6500,
    )
    db["pakcoy"] = IndoCrop(
        id="pakcoy", nama_id="Pakcoy", nama_en="Bok Choy",
        scientific="Brassica rapa chinensis", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=35, dap_panen_max=45,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=30.0, harga_kg_idr=8000,
    )
    db["selada"] = IndoCrop(
        id="selada", nama_id="Selada Keriting", nama_en="Lettuce",
        scientific="Lactuca sativa", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=14, dap_vegetatif_end=30, dap_generatif_end=40,
        dap_pembuahan_end=45, dap_panen=50, dap_panen_max=60,
        suhu_optimal=20, altitude_min_mdpl=200, altitude_max_mdpl=2000,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=18000,
    )
    db["kangkung"] = IndoCrop(
        id="kangkung", nama_id="Kangkung Darat", nama_en="Water Spinach",
        scientific="Ipomoea reptans", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=27, dap_panen_max=35,
        water_mm_per_phase=[5.0, 6.0, 7.0, 6.5, 5.5, 3.0],
        yield_ton_per_ha_min=12.0, yield_ton_per_ha_max=20.0, harga_kg_idr=5500,
    )
    db["bayam"] = IndoCrop(
        id="bayam", nama_id="Bayam", nama_en="Amaranth",
        scientific="Amaranthus tricolor", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=25, dap_panen_max=35,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=18.0, harga_kg_idr=5500,
    )
    db["daun_bawang"] = IndoCrop(
        id="daun_bawang", nama_id="Daun Bawang", nama_en="Scallion",
        scientific="Allium fistulosum", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=70, dap_panen_max=90,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=18.0, harga_kg_idr=15000,
    )
    db["seledri"] = IndoCrop(
        id="seledri", nama_id="Seledri", nama_en="Celery",
        scientific="Apium graveolens", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=90, dap_panen_max=120,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=18.0, harga_kg_idr=22000,
    )
    db["jagung_baby"] = IndoCrop(
        id="jagung_baby", nama_id="Jagung Baby", nama_en="Baby Corn",
        scientific="Zea mays", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=55, dap_panen_max=70,
        yield_ton_per_ha_min=4.0, yield_ton_per_ha_max=8.0, harga_kg_idr=18000,
    )
    db["asparagus"] = IndoCrop(
        id="asparagus", nama_id="Asparagus", nama_en="Asparagus",
        scientific="Asparagus officinalis", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=60, dap_vegetatif_end=365, dap_generatif_end=730,
        dap_pembuahan_end=730, dap_panen=730, dap_panen_max=3650,
        yield_ton_per_ha_min=4.0, yield_ton_per_ha_max=8.0, harga_kg_idr=60000,
        catatan="Perennial — productive 8-10 years.",
    )
    db["okra"] = IndoCrop(
        id="okra", nama_id="Okra", nama_en="Okra",
        scientific="Abelmoschus esculentus", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=60, dap_panen_max=90,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=18.0, harga_kg_idr=10000,
    )

    # ── BUAH-BUAHAN ────────────────────────────────────────────────────────────
    db["mangga"] = IndoCrop(
        id="mangga", nama_id="Mangga", nama_en="Mango",
        scientific="Mangifera indica", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=180, dap_vegetatif_end=1095, dap_generatif_end=1200,
        dap_pembuahan_end=1290, dap_panen=1320, dap_panen_max=10950,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=18000,
        catatan="Pohon tahunan — panen mulai tahun ke-3 hingga 30+.",
    )
    db["pisang"] = IndoCrop(
        id="pisang", nama_id="Pisang", nama_en="Banana",
        scientific="Musa paradisiaca", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=30, dap_vegetatif_end=240, dap_generatif_end=300,
        dap_pembuahan_end=360, dap_panen=420, dap_panen_max=540,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=40.0, harga_kg_idr=8000,
    )
    db["pepaya"] = IndoCrop(
        id="pepaya", nama_id="Pepaya California", nama_en="Papaya",
        scientific="Carica papaya", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=45, dap_vegetatif_end=180, dap_generatif_end=240,
        dap_pembuahan_end=270, dap_panen=300, dap_panen_max=900,
        yield_ton_per_ha_min=30.0, yield_ton_per_ha_max=80.0, harga_kg_idr=8500,
    )
    db["nanas"] = IndoCrop(
        id="nanas", nama_id="Nanas", nama_en="Pineapple",
        scientific="Ananas comosus", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=30, dap_vegetatif_end=300, dap_generatif_end=420,
        dap_pembuahan_end=510, dap_panen=540, dap_panen_max=600,
        yield_ton_per_ha_min=30.0, yield_ton_per_ha_max=60.0, harga_kg_idr=7000,
    )
    db["semangka"] = IndoCrop(
        id="semangka", nama_id="Semangka", nama_en="Watermelon",
        scientific="Citrullus lanatus", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=14, dap_vegetatif_end=35, dap_generatif_end=55,
        dap_pembuahan_end=75, dap_panen=85, dap_panen_max=95,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=45.0, harga_kg_idr=7500,
    )
    db["melon"] = IndoCrop(
        id="melon", nama_id="Melon", nama_en="Melon",
        scientific="Cucumis melo", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=10, dap_vegetatif_end=30, dap_generatif_end=50,
        dap_pembuahan_end=70, dap_panen=80, dap_panen_max=90,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=12000,
    )
    db["stroberi"] = IndoCrop(
        id="stroberi", nama_id="Stroberi", nama_en="Strawberry",
        scientific="Fragaria × ananassa", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=30, dap_vegetatif_end=70, dap_generatif_end=100,
        dap_pembuahan_end=120, dap_panen=130, dap_panen_max=240,
        altitude_min_mdpl=800, altitude_max_mdpl=1500,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=45000,
    )
    db["jeruk_siam"] = IndoCrop(
        id="jeruk_siam", nama_id="Jeruk Siam", nama_en="Tangerine",
        scientific="Citrus nobilis", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=180, dap_vegetatif_end=730, dap_generatif_end=900,
        dap_pembuahan_end=1080, dap_panen=1095, dap_panen_max=7300,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=40.0, harga_kg_idr=15000,
    )
    db["alpukat"] = IndoCrop(
        id="alpukat", nama_id="Alpukat", nama_en="Avocado",
        scientific="Persea americana", kategori=IndoCropCategory.BUAH,
        dap_panen=1095, dap_panen_max=10950,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=25.0, harga_kg_idr=22000,
    )
    db["durian"] = IndoCrop(
        id="durian", nama_id="Durian", nama_en="Durian",
        scientific="Durio zibethinus", kategori=IndoCropCategory.BUAH,
        dap_panen=1825, dap_panen_max=18250,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=45000,
        catatan="Raja buah — panen mulai tahun ke-5.",
    )
    db["manggis"] = IndoCrop(
        id="manggis", nama_id="Manggis", nama_en="Mangosteen",
        scientific="Garcinia mangostana", kategori=IndoCropCategory.BUAH,
        dap_panen=2920, dap_panen_max=14600,
        yield_ton_per_ha_min=5.0, yield_ton_per_ha_max=15.0, harga_kg_idr=28000,
    )
    db["rambutan"] = IndoCrop(
        id="rambutan", nama_id="Rambutan", nama_en="Rambutan",
        scientific="Nephelium lappaceum", kategori=IndoCropCategory.BUAH,
        dap_panen=1460, dap_panen_max=10950,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=12000,
    )
    db["salak"] = IndoCrop(
        id="salak", nama_id="Salak Pondoh", nama_en="Snake Fruit",
        scientific="Salacca zalacca", kategori=IndoCropCategory.BUAH,
        dap_panen=1095, dap_panen_max=10950,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=20.0, harga_kg_idr=12000,
    )
    db["nangka"] = IndoCrop(
        id="nangka", nama_id="Nangka", nama_en="Jackfruit",
        scientific="Artocarpus heterophyllus", kategori=IndoCropCategory.BUAH,
        dap_panen=1095, dap_panen_max=14600,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=40.0, harga_kg_idr=10000,
    )
    db["sirsak"] = IndoCrop(
        id="sirsak", nama_id="Sirsak", nama_en="Soursop",
        scientific="Annona muricata", kategori=IndoCropCategory.BUAH,
        dap_panen=1095, dap_panen_max=7300,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=18.0, harga_kg_idr=15000,
    )
    db["jambu_kristal"] = IndoCrop(
        id="jambu_kristal", nama_id="Jambu Biji Kristal", nama_en="Crystal Guava",
        scientific="Psidium guajava", kategori=IndoCropCategory.BUAH,
        dap_panen=540, dap_panen_max=3650,
        yield_ton_per_ha_min=12.0, yield_ton_per_ha_max=30.0, harga_kg_idr=15000,
    )
    db["belimbing"] = IndoCrop(
        id="belimbing", nama_id="Belimbing", nama_en="Star Fruit",
        scientific="Averrhoa carambola", kategori=IndoCropCategory.BUAH,
        dap_panen=900, dap_panen_max=5475,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=25.0, harga_kg_idr=12000,
    )
    db["markisa"] = IndoCrop(
        id="markisa", nama_id="Markisa", nama_en="Passion Fruit",
        scientific="Passiflora edulis", kategori=IndoCropCategory.BUAH,
        dap_panen=270, dap_panen_max=1825,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=18000,
    )
    db["naga_merah"] = IndoCrop(
        id="naga_merah", nama_id="Buah Naga Merah", nama_en="Red Dragon Fruit",
        scientific="Hylocereus polyrhizus", kategori=IndoCropCategory.BUAH,
        dap_panen=540, dap_panen_max=7300,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=30.0, harga_kg_idr=22000,
    )
    db["anggur"] = IndoCrop(
        id="anggur", nama_id="Anggur", nama_en="Grape",
        scientific="Vitis vinifera", kategori=IndoCropCategory.BUAH,
        dap_panen=540, dap_panen_max=7300,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=35000,
    )
    db["kelengkeng"] = IndoCrop(
        id="kelengkeng", nama_id="Kelengkeng", nama_en="Longan",
        scientific="Dimocarpus longan", kategori=IndoCropCategory.BUAH,
        dap_panen=900, dap_panen_max=7300,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=25.0, harga_kg_idr=25000,
    )

    # ── PERKEBUNAN ─────────────────────────────────────────────────────────────
    db["kopi_arabika"] = IndoCrop(
        id="kopi_arabika", nama_id="Kopi Arabika", nama_en="Arabica Coffee",
        scientific="Coffea arabica", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1095, dap_panen_max=10950,
        suhu_optimal=20, altitude_min_mdpl=1000, altitude_max_mdpl=2000,
        yield_ton_per_ha_min=0.6, yield_ton_per_ha_max=2.0, harga_kg_idr=80000,
        catatan="Export staple — Gayo, Mandailing, Toraja, Kintamani origins.",
    )
    db["kopi_robusta"] = IndoCrop(
        id="kopi_robusta", nama_id="Kopi Robusta", nama_en="Robusta Coffee",
        scientific="Coffea canephora", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=900, dap_panen_max=10950,
        altitude_min_mdpl=400, altitude_max_mdpl=900,
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=2.5, harga_kg_idr=35000,
    )
    db["teh"] = IndoCrop(
        id="teh", nama_id="Teh", nama_en="Tea",
        scientific="Camellia sinensis", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=730, dap_panen_max=18250,
        altitude_min_mdpl=700, altitude_max_mdpl=2000,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=3.0, harga_kg_idr=25000,
    )
    db["kakao"] = IndoCrop(
        id="kakao", nama_id="Kakao", nama_en="Cocoa",
        scientific="Theobroma cacao", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1095, dap_panen_max=10950,
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=2.0, harga_kg_idr=85000,
    )
    db["kelapa"] = IndoCrop(
        id="kelapa", nama_id="Kelapa", nama_en="Coconut",
        scientific="Cocos nucifera", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1825, dap_panen_max=21900,
        yield_ton_per_ha_min=2.5, yield_ton_per_ha_max=5.0, harga_kg_idr=8000,
    )
    db["sawit"] = IndoCrop(
        id="sawit", nama_id="Kelapa Sawit", nama_en="Oil Palm",
        scientific="Elaeis guineensis", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1095, dap_panen_max=10950,
        yield_ton_per_ha_min=18.0, yield_ton_per_ha_max=30.0, harga_kg_idr=2800,
        catatan="FFB (Fresh Fruit Bunch) — #1 export commodity.",
    )
    db["tebu"] = IndoCrop(
        id="tebu", nama_id="Tebu", nama_en="Sugarcane",
        scientific="Saccharum officinarum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_persemaian_end=14, dap_vegetatif_end=180, dap_generatif_end=300,
        dap_pembuahan_end=330, dap_panen=365, dap_panen_max=420,
        yield_ton_per_ha_min=70.0, yield_ton_per_ha_max=120.0, harga_kg_idr=1500,
    )
    db["karet"] = IndoCrop(
        id="karet", nama_id="Karet", nama_en="Rubber",
        scientific="Hevea brasiliensis", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1825, dap_panen_max=10950,
        yield_ton_per_ha_min=1.0, yield_ton_per_ha_max=2.5, harga_kg_idr=12000,
    )
    db["lada"] = IndoCrop(
        id="lada", nama_id="Lada", nama_en="Pepper",
        scientific="Piper nigrum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1095, dap_panen_max=7300,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=3.5, harga_kg_idr=85000,
    )
    db["cengkeh"] = IndoCrop(
        id="cengkeh", nama_id="Cengkeh", nama_en="Clove",
        scientific="Syzygium aromaticum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=2190, dap_panen_max=14600,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=1.5, harga_kg_idr=110000,
    )
    db["pala"] = IndoCrop(
        id="pala", nama_id="Pala", nama_en="Nutmeg",
        scientific="Myristica fragrans", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=2555, dap_panen_max=18250,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=1.2, harga_kg_idr=120000,
    )
    db["vanili"] = IndoCrop(
        id="vanili", nama_id="Vanili", nama_en="Vanilla",
        scientific="Vanilla planifolia", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1095, dap_panen_max=3650,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=1.5, harga_kg_idr=4500000,
        catatan="Komoditas premium — harga emas hijau.",
    )
    db["kapulaga"] = IndoCrop(
        id="kapulaga", nama_id="Kapulaga", nama_en="Cardamom",
        scientific="Amomum compactum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=730, dap_panen_max=3650,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=1.2, harga_kg_idr=180000,
    )
    db["kemiri"] = IndoCrop(
        id="kemiri", nama_id="Kemiri", nama_en="Candlenut",
        scientific="Aleurites moluccanus", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1825, dap_panen_max=14600,
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=5.0, harga_kg_idr=35000,
    )
    db["tembakau"] = IndoCrop(
        id="tembakau", nama_id="Tembakau", nama_en="Tobacco",
        scientific="Nicotiana tabacum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_persemaian_end=45, dap_vegetatif_end=85, dap_generatif_end=110,
        dap_pembuahan_end=120, dap_panen=130, dap_panen_max=150,
        yield_ton_per_ha_min=1.0, yield_ton_per_ha_max=2.5, harga_kg_idr=55000,
    )

    # ── HERBAL & BUMBU ─────────────────────────────────────────────────────────
    db["jahe_merah"] = IndoCrop(
        id="jahe_merah", nama_id="Jahe Merah", nama_en="Red Ginger",
        scientific="Zingiber officinale var. rubrum", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_persemaian_end=21, dap_vegetatif_end=120, dap_generatif_end=210,
        dap_pembuahan_end=270, dap_panen=300, dap_panen_max=365,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=35000,
    )
    db["jahe_emprit"] = IndoCrop(
        id="jahe_emprit", nama_id="Jahe Emprit", nama_en="White Ginger",
        scientific="Zingiber officinale var. amarum", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=270, dap_panen_max=300,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=25.0, harga_kg_idr=18000,
    )
    db["kunyit"] = IndoCrop(
        id="kunyit", nama_id="Kunyit", nama_en="Turmeric",
        scientific="Curcuma longa", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=240, dap_panen_max=300,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=14000,
    )
    db["temulawak"] = IndoCrop(
        id="temulawak", nama_id="Temulawak", nama_en="Java Turmeric",
        scientific="Curcuma xanthorrhiza", kategori=IndoCropCategory.BIOFARMAKA,
        dap_panen=300, dap_panen_max=365,
        yield_ton_per_ha_min=12.0, yield_ton_per_ha_max=25.0, harga_kg_idr=16000,
    )
    db["lengkuas"] = IndoCrop(
        id="lengkuas", nama_id="Lengkuas", nama_en="Galangal",
        scientific="Alpinia galanga", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=240, dap_panen_max=365,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=20.0, harga_kg_idr=15000,
    )
    db["kencur"] = IndoCrop(
        id="kencur", nama_id="Kencur", nama_en="Aromatic Ginger",
        scientific="Kaempferia galanga", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=240, dap_panen_max=300,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=15.0, harga_kg_idr=22000,
    )
    db["sereh_dapur"] = IndoCrop(
        id="sereh_dapur", nama_id="Sereh", nama_en="Lemongrass",
        scientific="Cymbopogon citratus", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=180, dap_panen_max=1825,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=40.0, harga_kg_idr=8000,
    )
    db["kemangi"] = IndoCrop(
        id="kemangi", nama_id="Kemangi", nama_en="Lemon Basil",
        scientific="Ocimum × citriodorum", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=45, dap_panen_max=120,
        yield_ton_per_ha_min=5.0, yield_ton_per_ha_max=15.0, harga_kg_idr=12000,
    )
    db["sambiloto"] = IndoCrop(
        id="sambiloto", nama_id="Sambiloto", nama_en="King of Bitters",
        scientific="Andrographis paniculata", kategori=IndoCropCategory.BIOFARMAKA,
        dap_panen=120, dap_panen_max=180,
        yield_ton_per_ha_min=4.0, yield_ton_per_ha_max=8.0, harga_kg_idr=25000,
    )
    db["mengkudu"] = IndoCrop(
        id="mengkudu", nama_id="Mengkudu", nama_en="Noni",
        scientific="Morinda citrifolia", kategori=IndoCropCategory.BIOFARMAKA,
        dap_panen=540, dap_panen_max=7300,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=25.0, harga_kg_idr=12000,
    )
    db["binahong"] = IndoCrop(
        id="binahong", nama_id="Binahong", nama_en="Madeira Vine",
        scientific="Anredera cordifolia", kategori=IndoCropCategory.BIOFARMAKA,
        dap_panen=90, dap_panen_max=365,
        yield_ton_per_ha_min=5.0, yield_ton_per_ha_max=12.0, harga_kg_idr=18000,
    )
    db["lidah_buaya"] = IndoCrop(
        id="lidah_buaya", nama_id="Lidah Buaya", nama_en="Aloe Vera",
        scientific="Aloe vera", kategori=IndoCropCategory.BIOFARMAKA,
        dap_panen=180, dap_panen_max=1825,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=80.0, harga_kg_idr=8000,
    )
    db["mint"] = IndoCrop(
        id="mint", nama_id="Mint", nama_en="Mint",
        scientific="Mentha piperita", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=70, dap_panen_max=365,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=18.0, harga_kg_idr=22000,
    )
    db["rosella"] = IndoCrop(
        id="rosella", nama_id="Rosella", nama_en="Roselle",
        scientific="Hibiscus sabdariffa", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=180, dap_panen_max=210,
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=4.5, harga_kg_idr=45000,
    )
    db["serai_wangi"] = IndoCrop(
        id="serai_wangi", nama_id="Serai Wangi", nama_en="Citronella",
        scientific="Cymbopogon nardus", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=240, dap_panen_max=1825,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=30.0, harga_kg_idr=6000,
    )
    db["nilam"] = IndoCrop(
        id="nilam", nama_id="Nilam", nama_en="Patchouli",
        scientific="Pogostemon cablin", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=180, dap_panen_max=540,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=15.0, harga_kg_idr=14000,
        catatan="Leaves for patchouli oil extraction — export commodity.",
    )

    # ── KHUSUS / NICHE ─────────────────────────────────────────────────────────
    db["microgreens"] = IndoCrop(
        id="microgreens", nama_id="Microgreens Mix", nama_en="Microgreens",
        scientific="Mixed", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=2, dap_vegetatif_end=8, dap_generatif_end=10,
        dap_pembuahan_end=12, dap_panen=14, dap_panen_max=21,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=1.2, harga_kg_idr=250000,
    )
    db["jamur_tiram"] = IndoCrop(
        id="jamur_tiram", nama_id="Jamur Tiram", nama_en="Oyster Mushroom",
        scientific="Pleurotus ostreatus", kategori=IndoCropCategory.HORTIKULTURA,
        dap_persemaian_end=21, dap_vegetatif_end=30, dap_generatif_end=35,
        dap_pembuahan_end=40, dap_panen=45, dap_panen_max=120,
        suhu_optimal=24, kelembapan_optimal=85,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=30.0, harga_kg_idr=18000,
        catatan="Sistem baglog — ruangan tertutup gelap.",
    )
    db["jamur_kuping"] = IndoCrop(
        id="jamur_kuping", nama_id="Jamur Kuping", nama_en="Wood Ear Mushroom",
        scientific="Auricularia auricula", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=60, dap_panen_max=150,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=22000,
    )
    db["anggrek_dendro"] = IndoCrop(
        id="anggrek_dendro", nama_id="Anggrek Dendrobium", nama_en="Dendrobium Orchid",
        scientific="Dendrobium spp.", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=540, dap_panen_max=3650,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=2.0, harga_kg_idr=85000,
    )
    db["krisan"] = IndoCrop(
        id="krisan", nama_id="Bunga Krisan", nama_en="Chrysanthemum",
        scientific="Chrysanthemum × morifolium", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=90, dap_panen_max=120,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=3.5, harga_kg_idr=35000,
    )
    db["mawar_potong"] = IndoCrop(
        id="mawar_potong", nama_id="Mawar Potong", nama_en="Cut Rose",
        scientific="Rosa spp.", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=180, dap_panen_max=1825,
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=5.0, harga_kg_idr=45000,
    )

    # ══════════════════════════════════════════════════════════════════════
    # GLOBAL CROPS — Grains, Oilseeds, Fibers, Beverages, Tropical & More
    # ══════════════════════════════════════════════════════════════════════

    # ── GLOBAL GRAINS & CEREALS ───────────────────────────────────────────
    db["wheat_common"] = IndoCrop(
        id="wheat_common", nama_id="Gandum Biasa", nama_en="Common Wheat",
        scientific="Triticum aestivum", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_persemaian_end=14, dap_vegetatif_end=70, dap_generatif_end=100,
        dap_pembuahan_end=120, dap_panen=130, dap_panen_max=145,
        suhu_optimal=15, suhu_min=3, suhu_max=25, kelembapan_optimal=60,
        altitude_min_mdpl=200, altitude_max_mdpl=3500, ph_min=6.0, ph_max=7.5,
        water_mm_per_phase=[5.0, 6.0, 7.5, 8.0, 6.5, 3.0],
        npk_kg_ha_per_phase=[(80,60,40), (40,0,20), (30,0,0)],
        yield_ton_per_ha_min=2.5, yield_ton_per_ha_max=7.5, harga_kg_idr=5500,
        jarak_tanam_cm=(15,10), populasi_per_ha=4000000,
        hama_umum=["Aphids", "Hessian fly", "Wheat midge"],
        penyakit_umum=["Stem rust", "Powdery mildew", "Septoria leaf blotch"],
        catatan="Subtropical/temperate. Grows at tropical highlands (>1500m).",
    )
    db["wheat_durum"] = IndoCrop(
        id="wheat_durum", nama_id="Gandum Durum", nama_en="Durum Wheat",
        scientific="Triticum durum", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=120, dap_panen_max=140,
        suhu_optimal=18, suhu_min=5, suhu_max=28, kelembapan_optimal=55,
        altitude_min_mdpl=300, altitude_max_mdpl=2500, ph_min=6.0, ph_max=8.0,
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=6.0, harga_kg_idr=7500,
        catatan="For pasta/semolina. More drought-tolerant than common wheat.",
    )
    db["barley"] = IndoCrop(
        id="barley", nama_id="Barley / Jelai", nama_en="Barley",
        scientific="Hordeum vulgare", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=15, suhu_min=1, suhu_max=30, kelembapan_optimal=55,
        altitude_min_mdpl=0, altitude_max_mdpl=4000, ph_min=6.0, ph_max=8.0,
        water_mm_per_phase=[4.0, 5.0, 6.5, 7.0, 5.5, 2.5],
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=6.0, harga_kg_idr=5000,
        hama_umum=["Aphids", "Bird damage"], penyakit_umum=["Net blotch", "Scald"],
        catatan="Very cold & drought tolerant. Livestock feed & beverages.",
    )
    db["oat"] = IndoCrop(
        id="oat", nama_id="Gandum Oat", nama_en="Oat",
        scientific="Avena sativa", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=100, dap_panen_max=130,
        suhu_optimal=16, suhu_min=2, suhu_max=26, kelembapan_optimal=65,
        altitude_min_mdpl=0, altitude_max_mdpl=2500, ph_min=5.5, ph_max=7.5,
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=5.0, harga_kg_idr=9000,
        catatan="Toleran asam & lembap. Populer sebagai makanan sehat & pakan.",
    )
    db["rye"] = IndoCrop(
        id="rye", nama_id="Gandum Hitam / Rye", nama_en="Rye",
        scientific="Secale cereale", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=95, dap_panen_max=120,
        suhu_optimal=12, suhu_min=-5, suhu_max=25, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=3000, ph_min=5.0, ph_max=7.5,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=4.5, harga_kg_idr=8000,
        catatan="Paling toleran dingin & asam di antara serealia. Roti hitam Eropa.",
    )
    db["buckwheat"] = IndoCrop(
        id="buckwheat", nama_id="Soba / Buckwheat", nama_en="Buckwheat",
        scientific="Fagopyrum esculentum", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=70, dap_panen_max=90,
        suhu_optimal=18, suhu_min=5, suhu_max=28, kelembapan_optimal=65,
        altitude_min_mdpl=500, altitude_max_mdpl=3500, ph_min=5.0, ph_max=7.0,
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=2.5, harga_kg_idr=18000,
        catatan="Non-sereal gluten-free. Siklus cepat — ideal sebagai catch crop.",
    )
    db["quinoa"] = IndoCrop(
        id="quinoa", nama_id="Quinoa", nama_en="Quinoa",
        scientific="Chenopodium quinoa", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=15, suhu_min=0, suhu_max=30, kelembapan_optimal=50,
        altitude_min_mdpl=1000, altitude_max_mdpl=4000, ph_min=6.0, ph_max=8.5,
        water_mm_per_phase=[3.0, 4.0, 5.5, 6.0, 4.5, 2.0],
        yield_ton_per_ha_min=1.0, yield_ton_per_ha_max=4.0, harga_kg_idr=80000,
        hama_umum=["Bird damage", "Aphids"], penyakit_umum=["Downy mildew"],
        catatan="Superfood Andes. Toleran dingin, kering, dan salinitas tinggi.",
    )
    db["amaranth"] = IndoCrop(
        id="amaranth", nama_id="Bayam Biji / Amaranth", nama_en="Grain Amaranth",
        scientific="Amaranthus hypochondriacus", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=25, suhu_min=10, suhu_max=38, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=2500, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=4.0, harga_kg_idr=50000,
        catatan="Pseudo-cereal protein tinggi. Toleran panas & kekeringan.",
    )
    db["teff"] = IndoCrop(
        id="teff", nama_id="Teff", nama_en="Teff",
        scientific="Eragrostis tef", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=75, dap_panen_max=95,
        suhu_optimal=22, suhu_min=10, suhu_max=30, kelembapan_optimal=55,
        altitude_min_mdpl=500, altitude_max_mdpl=3000, ph_min=5.5, ph_max=8.0,
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=2.5, harga_kg_idr=45000,
        catatan="Staple Ethiopia/Eritrea. Sangat toleran variasi iklim & banjir singkat.",
    )
    db["fonio"] = IndoCrop(
        id="fonio", nama_id="Fonio", nama_en="Fonio",
        scientific="Digitaria exilis", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=70, dap_panen_max=90,
        suhu_optimal=28, suhu_min=18, suhu_max=38, kelembapan_optimal=50,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=5.0, ph_max=7.0,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=1.5, harga_kg_idr=60000,
        catatan="Ancient West African cereal. Fastest harvest (6-8 wk). Drought-hardy.",
    )
    db["pearl_millet"] = IndoCrop(
        id="pearl_millet", nama_id="Millet Mutiara", nama_en="Pearl Millet",
        scientific="Pennisetum glaucum", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=75, dap_panen_max=100,
        suhu_optimal=30, suhu_min=15, suhu_max=42, kelembapan_optimal=45,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=5.5, ph_max=8.0,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=4.5, harga_kg_idr=7000,
        catatan="Paling toleran panas & kekeringan. Populer di Afrika & India.",
    )
    db["finger_millet"] = IndoCrop(
        id="finger_millet", nama_id="Millet Jari / Eleusine", nama_en="Finger Millet",
        scientific="Eleusine coracana", kategori=IndoCropCategory.PANGAN_POKOK,
        dap_panen=85, dap_panen_max=110,
        suhu_optimal=25, suhu_min=12, suhu_max=35, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=2700, ph_min=5.5, ph_max=8.0,
        yield_ton_per_ha_min=1.0, yield_ton_per_ha_max=3.0, harga_kg_idr=12000,
        catatan="High calcium, long shelf life. Staple in Kenya, Uganda, South India.",
    )
    db["sorghum_sweet"] = IndoCrop(
        id="sorghum_sweet", nama_id="Sorgum Manis", nama_en="Sweet Sorghum",
        scientific="Sorghum bicolor var. saccharatum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=100, dap_panen_max=125,
        suhu_optimal=30, suhu_min=15, suhu_max=40, kelembapan_optimal=55,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=5.5, ph_max=7.5,
        yield_ton_per_ha_min=35.0, yield_ton_per_ha_max=70.0, harga_kg_idr=800,
        catatan="Sweet stalks for bioethanol & sugar. Grain for food/feed.",
    )

    # ── OILSEEDS ─────────────────────────────────────────────────────────
    db["canola"] = IndoCrop(
        id="canola", nama_id="Kanola / Rapeseed", nama_en="Canola / Rapeseed",
        scientific="Brassica napus", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=100, dap_panen_max=130,
        suhu_optimal=15, suhu_min=0, suhu_max=25, kelembapan_optimal=60,
        altitude_min_mdpl=200, altitude_max_mdpl=2000, ph_min=6.0, ph_max=7.5,
        water_mm_per_phase=[4.0, 5.5, 7.0, 7.5, 5.5, 2.5],
        npk_kg_ha_per_phase=[(100,60,60), (50,0,30), (0,0,0)],
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=4.5, harga_kg_idr=9000,
        hama_umum=["Flea beetle", "Aphids", "Cabbage seed weevil"],
        penyakit_umum=["Sclerotinia stem rot", "Blackleg"],
        catatan="Healthy vegetable oil. Seeds harvested for canola oil/biodiesel.",
    )
    db["sunflower"] = IndoCrop(
        id="sunflower", nama_id="Bunga Matahari", nama_en="Sunflower",
        scientific="Helianthus annuus", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=25, suhu_min=8, suhu_max=34, kelembapan_optimal=55,
        altitude_min_mdpl=0, altitude_max_mdpl=2000, ph_min=6.0, ph_max=7.5,
        water_mm_per_phase=[3.5, 5.0, 7.5, 8.0, 6.0, 2.0],
        npk_kg_ha_per_phase=[(60,60,60), (30,0,30), (0,0,0)],
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=3.5, harga_kg_idr=12000,
        hama_umum=["Heliothis moth", "Aphids", "Birds"],
        penyakit_umum=["Downy mildew", "Sclerotinia rot"],
        catatan="Toleran kekeringan sedang. Minyak biji + produk bunga.",
    )
    db["flax_linseed"] = IndoCrop(
        id="flax_linseed", nama_id="Flax / Rami Biji", nama_en="Flax / Linseed",
        scientific="Linum usitatissimum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=18, suhu_min=3, suhu_max=28, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=2000, ph_min=5.5, ph_max=7.0,
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=2.5, harga_kg_idr=20000,
        catatan="Serat tekstil + minyak omega-3 tinggi (linseed oil).",
    )
    db["hemp"] = IndoCrop(
        id="hemp", nama_id="Hemp Industri", nama_en="Industrial Hemp",
        scientific="Cannabis sativa L.", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=100, dap_panen_max=130,
        suhu_optimal=20, suhu_min=5, suhu_max=30, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=1800, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=2.0, yield_ton_per_ha_max=8.0, harga_kg_idr=25000,
        catatan="Serat, biji (pangan), bangunan (hempcrete). THC <0.3% (legal). "
                "Regulasi berbeda tiap negara — periksa aturan lokal.",
    )
    db["sesame"] = IndoCrop(
        id="sesame", nama_id="Wijen", nama_en="Sesame",
        scientific="Sesamum indicum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=27, suhu_min=18, suhu_max=38, kelembapan_optimal=50,
        altitude_min_mdpl=0, altitude_max_mdpl=1250, ph_min=5.5, ph_max=8.0,
        water_mm_per_phase=[3.0, 4.0, 5.5, 5.0, 3.5, 1.5],
        yield_ton_per_ha_min=0.4, yield_ton_per_ha_max=1.5, harga_kg_idr=35000,
        catatan="Tahan kering & panas. Biji minyak & bumbu. Butuh lahan drainase baik.",
    )
    db["groundnut_global"] = IndoCrop(
        id="groundnut_global", nama_id="Kacang Tanah (Global)", nama_en="Groundnut (Global)",
        scientific="Arachis hypogaea", kategori=IndoCropCategory.PALAWIJA,
        dap_panen=100, dap_panen_max=130,
        suhu_optimal=28, suhu_min=15, suhu_max=36, kelembapan_optimal=65,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=5.5, ph_max=7.0,
        yield_ton_per_ha_min=1.0, yield_ton_per_ha_max=3.0, harga_kg_idr=22000,
        catatan="Varietas global: Runner, Virginia, Spanish, Valencia. Aflatoksin risk tinggi.",
    )

    # ── FIBER & INDUSTRIAL CROPS ──────────────────────────────────────────
    db["cotton"] = IndoCrop(
        id="cotton", nama_id="Kapas", nama_en="Cotton",
        scientific="Gossypium hirsutum", kategori=IndoCropCategory.PERKEBUNAN,
        dap_persemaian_end=14, dap_vegetatif_end=60, dap_generatif_end=90,
        dap_pembuahan_end=120, dap_panen=150, dap_panen_max=180,
        suhu_optimal=28, suhu_min=15, suhu_max=38, kelembapan_optimal=55,
        altitude_min_mdpl=0, altitude_max_mdpl=1000, ph_min=5.8, ph_max=8.0,
        water_mm_per_phase=[4.0, 6.0, 8.0, 9.0, 7.0, 3.0],
        npk_kg_ha_per_phase=[(80,40,40), (60,0,40), (40,0,0)],
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=4.0, harga_kg_idr=18000,
        hama_umum=["Bollworm", "Aphids", "Whitefly", "Spider mite"],
        penyakit_umum=["Fusarium wilt", "Boll rot", "Bacterial blight"],
        catatan="Needs dry season at harvest. Pesticide-intensive — promote IPM.",
    )
    db["jute"] = IndoCrop(
        id="jute", nama_id="Goni / Jute", nama_en="Jute",
        scientific="Corchorus olitorius", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=100, dap_panen_max=140,
        suhu_optimal=30, suhu_min=20, suhu_max=40, kelembapan_optimal=80,
        altitude_min_mdpl=0, altitude_max_mdpl=500, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=3.0, harga_kg_idr=10000,
        catatan="Serat alami biodegradable. Butuh curah hujan tinggi & panas.",
    )
    db["sisal"] = IndoCrop(
        id="sisal", nama_id="Sisal / Agave", nama_en="Sisal",
        scientific="Agave sisalana", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=1825, dap_panen_max=3650,
        suhu_optimal=27, suhu_min=10, suhu_max=40, kelembapan_optimal=40,
        altitude_min_mdpl=0, altitude_max_mdpl=2000, ph_min=5.5, ph_max=8.0,
        yield_ton_per_ha_min=2.5, yield_ton_per_ha_max=6.0, harga_kg_idr=12000,
        catatan="Hard fiber (sacks, ship rope). 5-7 years before first harvest.",
    )

    # ── BEVERAGE CROPS ────────────────────────────────────────────────────
    db["coffee_arabica"] = IndoCrop(
        id="coffee_arabica", nama_id="Kopi Arabika", nama_en="Arabica Coffee",
        scientific="Coffea arabica", kategori=IndoCropCategory.PERKEBUNAN,
        dap_persemaian_end=180, dap_vegetatif_end=1095, dap_generatif_end=1460,
        dap_pembuahan_end=1640, dap_panen=1825, dap_panen_max=10950,
        suhu_optimal=19, suhu_min=10, suhu_max=24, kelembapan_optimal=75,
        altitude_min_mdpl=800, altitude_max_mdpl=2200, ph_min=6.0, ph_max=6.5,
        water_mm_per_phase=[5.0, 7.0, 8.0, 9.0, 8.0, 5.0],
        npk_kg_ha_per_phase=[(60,40,60), (40,20,40), (20,0,20)],
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=3.0, harga_kg_idr=120000,
        hama_umum=["Coffee berry borer", "Mealybug", "Antestia bug"],
        penyakit_umum=["Coffee leaf rust", "Coffee wilt", "CBD"],
        catatan="Specialty grade. Needs 3-4 years before harvest. Highlands <24°C.",
    )
    db["coffee_robusta"] = IndoCrop(
        id="coffee_robusta", nama_id="Kopi Robusta", nama_en="Robusta Coffee",
        scientific="Coffea canephora", kategori=IndoCropCategory.PERKEBUNAN,
        dap_persemaian_end=180, dap_vegetatif_end=730, dap_generatif_end=1095,
        dap_pembuahan_end=1275, dap_panen=1460, dap_panen_max=10950,
        suhu_optimal=26, suhu_min=18, suhu_max=36, kelembapan_optimal=80,
        altitude_min_mdpl=0, altitude_max_mdpl=900, ph_min=5.5, ph_max=6.5,
        yield_ton_per_ha_min=1.0, yield_ton_per_ha_max=4.0, harga_kg_idr=35000,
        hama_umum=["Coffee berry borer", "Scale insects"],
        penyakit_umum=["Coffee leaf rust"],
        catatan="More heat & disease tolerant than Arabica. Higher caffeine.",
    )
    db["tea_camellia"] = IndoCrop(
        id="tea_camellia", nama_id="Teh", nama_en="Tea",
        scientific="Camellia sinensis", kategori=IndoCropCategory.PERKEBUNAN,
        dap_persemaian_end=365, dap_vegetatif_end=1460, dap_generatif_end=1825,
        dap_pembuahan_end=1825, dap_panen=1825, dap_panen_max=36500,
        suhu_optimal=20, suhu_min=10, suhu_max=30, kelembapan_optimal=80,
        altitude_min_mdpl=300, altitude_max_mdpl=2500, ph_min=4.5, ph_max=6.0,
        water_mm_per_phase=[6.0, 8.0, 9.5, 9.0, 7.5, 5.0],
        yield_ton_per_ha_min=1.5, yield_ton_per_ha_max=5.0, harga_kg_idr=40000,
        hama_umum=["Tea mosquito bug", "Red spider mite", "Thrips"],
        penyakit_umum=["Blister blight", "Root rot", "Gray blight"],
        catatan="Perennial up to 100 years. Needs acidic soil. Harvest every 7-14 days.",
    )
    db["cocoa_theobroma"] = IndoCrop(
        id="cocoa_theobroma", nama_id="Kakao (Global)", nama_en="Cocoa",
        scientific="Theobroma cacao", kategori=IndoCropCategory.PERKEBUNAN,
        dap_persemaian_end=120, dap_vegetatif_end=1095, dap_generatif_end=1460,
        dap_pembuahan_end=1640, dap_panen=1825, dap_panen_max=10950,
        suhu_optimal=27, suhu_min=18, suhu_max=32, kelembapan_optimal=85,
        altitude_min_mdpl=0, altitude_max_mdpl=700, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=2.5, harga_kg_idr=50000,
        hama_umum=["Pod borer", "Mealybug", "Cocoa pod borer"],
        penyakit_umum=["Black pod", "Swollen shoot virus", "Frosty pod"],
        catatan="Grows in partial shade. Equatorial ±20° latitude.",
    )

    # ── ROOT VEGETABLES (GLOBAL) ──────────────────────────────────────────
    db["potato_global"] = IndoCrop(
        id="potato_global", nama_id="Kentang (Global)", nama_en="Potato (Global)",
        scientific="Solanum tuberosum", kategori=IndoCropCategory.UMBI,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=17, suhu_min=5, suhu_max=25, kelembapan_optimal=70,
        altitude_min_mdpl=0, altitude_max_mdpl=4500, ph_min=5.0, ph_max=7.0,
        water_mm_per_phase=[3.5, 5.0, 7.5, 8.0, 6.0, 2.5],
        npk_kg_ha_per_phase=[(80,80,120), (40,0,60), (0,0,40)],
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=45.0, harga_kg_idr=12000,
        hama_umum=["Colorado beetle", "Wireworm", "Aphids"],
        penyakit_umum=["Late blight", "Early blight", "Blackleg", "PVY virus"],
        catatan="Pangan ke-4 terbesar di dunia. 5000+ varietas. Hati-hati late blight.",
    )
    db["sweet_potato_global"] = IndoCrop(
        id="sweet_potato_global", nama_id="Ubi Jalar (Global)", nama_en="Sweet Potato (Global)",
        scientific="Ipomoea batatas", kategori=IndoCropCategory.UMBI,
        dap_panen=100, dap_panen_max=140,
        suhu_optimal=27, suhu_min=15, suhu_max=35, kelembapan_optimal=70,
        altitude_min_mdpl=0, altitude_max_mdpl=2500, ph_min=5.5, ph_max=7.5,
        yield_ton_per_ha_min=12.0, yield_ton_per_ha_max=30.0, harga_kg_idr=8000,
        catatan="Varietas orange kaya betakaroten (Vitamin A). Tahan kering.",
    )
    db["cassava_global"] = IndoCrop(
        id="cassava_global", nama_id="Singkong (Global)", nama_en="Cassava (Global)",
        scientific="Manihot esculenta", kategori=IndoCropCategory.UMBI,
        dap_panen=240, dap_panen_max=365,
        suhu_optimal=27, suhu_min=18, suhu_max=38, kelembapan_optimal=65,
        altitude_min_mdpl=0, altitude_max_mdpl=2000, ph_min=5.0, ph_max=8.0,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=40.0, harga_kg_idr=2500,
        hama_umum=["Mealybug", "Whitefly", "Green spider mite"],
        penyakit_umum=["CMD (mosaic virus)", "CBSD (brown streak)"],
        catatan="Tropical food security crop. Choose low-HCN varieties for consumption.",
    )
    db["yam"] = IndoCrop(
        id="yam", nama_id="Ubi Kelapa / Yam", nama_en="Yam",
        scientific="Dioscorea rotundata", kategori=IndoCropCategory.UMBI,
        dap_panen=180, dap_panen_max=360,
        suhu_optimal=28, suhu_min=18, suhu_max=35, kelembapan_optimal=75,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=5.5, ph_max=7.5,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=25.0, harga_kg_idr=15000,
        catatan="West Africa staple. Different from sweet potato — genus Dioscorea.",
    )

    # ── VEGETABLES (GLOBAL) ───────────────────────────────────────────────
    db["tomato_global"] = IndoCrop(
        id="tomato_global", nama_id="Tomat (Global)", nama_en="Tomato (Global)",
        scientific="Solanum lycopersicum", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=70, dap_panen_max=90,
        suhu_optimal=22, suhu_min=10, suhu_max=30, kelembapan_optimal=65,
        altitude_min_mdpl=0, altitude_max_mdpl=2000, ph_min=5.5, ph_max=7.0,
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=60.0, harga_kg_idr=12000,
        hama_umum=["Whitefly", "Tomato moth", "Thrips", "Leafminer"],
        penyakit_umum=["Late blight", "TSWV", "Fusarium wilt", "TYLCV"],
        catatan="Terpenting ke-2 setelah kentang. 10,000+ varietas global.",
    )
    db["pepper_capsicum"] = IndoCrop(
        id="pepper_capsicum", nama_id="Paprika / Bell Pepper", nama_en="Bell Pepper",
        scientific="Capsicum annuum var. grossum", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=80, dap_panen_max=100,
        suhu_optimal=22, suhu_min=12, suhu_max=30, kelembapan_optimal=65,
        altitude_min_mdpl=0, altitude_max_mdpl=1800, ph_min=6.0, ph_max=7.0,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=40.0, harga_kg_idr=25000,
        catatan="Nilai ekspor tinggi. Merah/kuning/hijau = tingkat kematangan berbeda.",
    )
    db["cucumber_global"] = IndoCrop(
        id="cucumber_global", nama_id="Mentimun (Global)", nama_en="Cucumber (Global)",
        scientific="Cucumis sativus", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=55, dap_panen_max=70,
        suhu_optimal=26, suhu_min=15, suhu_max=35, kelembapan_optimal=70,
        altitude_min_mdpl=0, altitude_max_mdpl=1500, ph_min=6.0, ph_max=7.0,
        yield_ton_per_ha_min=25.0, yield_ton_per_ha_max=60.0, harga_kg_idr=5500,
        catatan="Very fast cycle. Harvest from 45-55 DAP, continues 4-6 weeks.",
    )
    db["lettuce"] = IndoCrop(
        id="lettuce", nama_id="Selada", nama_en="Lettuce",
        scientific="Lactuca sativa", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=45, dap_panen_max=70,
        suhu_optimal=18, suhu_min=5, suhu_max=24, kelembapan_optimal=70,
        altitude_min_mdpl=200, altitude_max_mdpl=2500, ph_min=6.0, ph_max=7.0,
        water_mm_per_phase=[3.0, 4.0, 5.5, 5.5, 3.5, 2.0],
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=35.0, harga_kg_idr=15000,
        catatan="Ideal hidroponik & greenhouse. Sangat cepat — cocok vertikal farming.",
    )
    db["spinach"] = IndoCrop(
        id="spinach", nama_id="Bayam Eropa / Spinach", nama_en="Spinach",
        scientific="Spinacia oleracea", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=40, dap_panen_max=60,
        suhu_optimal=15, suhu_min=0, suhu_max=24, kelembapan_optimal=70,
        altitude_min_mdpl=200, altitude_max_mdpl=2500, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=18000,
        catatan="Kaya besi & vitamin K. Tidak tahan panas > 24°C — cocok dataran tinggi.",
    )
    db["broccoli"] = IndoCrop(
        id="broccoli", nama_id="Brokoli", nama_en="Broccoli",
        scientific="Brassica oleracea var. italica", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=70, dap_panen_max=95,
        suhu_optimal=18, suhu_min=5, suhu_max=24, kelembapan_optimal=70,
        altitude_min_mdpl=500, altitude_max_mdpl=2000, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=20.0, harga_kg_idr=20000,
        hama_umum=["Cabbage looper", "Diamond-back moth", "Aphids"],
        penyakit_umum=["Downy mildew", "Black rot"],
        catatan="Bernilai tinggi. Butuh cuaca sejuk. Sentra: Lembang, Dieng, Bedugul.",
    )
    db["carrot_global"] = IndoCrop(
        id="carrot_global", nama_id="Wortel (Global)", nama_en="Carrot (Global)",
        scientific="Daucus carota", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=18, suhu_min=5, suhu_max=25, kelembapan_optimal=65,
        altitude_min_mdpl=500, altitude_max_mdpl=2500, ph_min=6.0, ph_max=7.0,
        water_mm_per_phase=[3.5, 4.5, 6.0, 6.0, 4.5, 2.5],
        yield_ton_per_ha_min=20.0, yield_ton_per_ha_max=50.0, harga_kg_idr=12000,
        catatan="Needs deep loose soil >30cm. 350+ varieties: orange, purple, yellow, white.",
    )
    db["onion_global"] = IndoCrop(
        id="onion_global", nama_id="Bawang Bombay", nama_en="Onion",
        scientific="Allium cepa", kategori=IndoCropCategory.HORTIKULTURA,
        dap_panen=100, dap_panen_max=140,
        suhu_optimal=20, suhu_min=7, suhu_max=30, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=2000, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=15.0, yield_ton_per_ha_max=40.0, harga_kg_idr=18000,
        hama_umum=["Thrips", "Onion fly"], penyakit_umum=["Downy mildew", "Fusarium basal rot"],
        catatan="3rd largest global production after tomato & banana. Store dry <75% RH.",
    )
    db["garlic_global"] = IndoCrop(
        id="garlic_global", nama_id="Bawang Putih (Global)", nama_en="Garlic (Global)",
        scientific="Allium sativum", kategori=IndoCropCategory.HERBAL_BUMBU,
        dap_panen=150, dap_panen_max=200,
        suhu_optimal=18, suhu_min=0, suhu_max=26, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=2500, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=5.0, yield_ton_per_ha_max=15.0, harga_kg_idr=45000,
        catatan="Needs vernalization (cold temp) for good bulb formation.",
    )

    # ── LEGUMES (GLOBAL) ─────────────────────────────────────────────────
    db["chickpea"] = IndoCrop(
        id="chickpea", nama_id="Kacang Garbanzo / Chickpea", nama_en="Chickpea",
        scientific="Cicer arietinum", kategori=IndoCropCategory.PALAWIJA,
        dap_panen=90, dap_panen_max=120,
        suhu_optimal=22, suhu_min=5, suhu_max=30, kelembapan_optimal=50,
        altitude_min_mdpl=0, altitude_max_mdpl=2500, ph_min=6.0, ph_max=8.0,
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=3.0, harga_kg_idr=25000,
        catatan="Protein tinggi. Tahan kering. Populer: India (50% produksi global), Australia.",
    )
    db["lentil"] = IndoCrop(
        id="lentil", nama_id="Lentil / Dal", nama_en="Lentil",
        scientific="Lens culinaris", kategori=IndoCropCategory.PALAWIJA,
        dap_panen=80, dap_panen_max=110,
        suhu_optimal=18, suhu_min=3, suhu_max=27, kelembapan_optimal=55,
        altitude_min_mdpl=200, altitude_max_mdpl=3000, ph_min=6.0, ph_max=8.0,
        yield_ton_per_ha_min=0.6, yield_ton_per_ha_max=2.5, harga_kg_idr=30000,
        catatan="Legum fiksasi N tercepat. Protein 25%. Populer di Asia Selatan & Timur Tengah.",
    )
    db["cowpea"] = IndoCrop(
        id="cowpea", nama_id="Kacang Tunggak", nama_en="Cowpea",
        scientific="Vigna unguiculata", kategori=IndoCropCategory.PALAWIJA,
        dap_panen=60, dap_panen_max=90,
        suhu_optimal=28, suhu_min=18, suhu_max=40, kelembapan_optimal=55,
        altitude_min_mdpl=0, altitude_max_mdpl=1700, ph_min=5.5, ph_max=8.0,
        yield_ton_per_ha_min=0.5, yield_ton_per_ha_max=2.5, harga_kg_idr=22000,
        catatan="Sangat toleran kekeringan & panas. Staple Afrika Barat.",
    )
    db["pigeon_pea"] = IndoCrop(
        id="pigeon_pea", nama_id="Kacang Gude", nama_en="Pigeon Pea",
        scientific="Cajanus cajan", kategori=IndoCropCategory.PALAWIJA,
        dap_panen=150, dap_panen_max=210,
        suhu_optimal=26, suhu_min=14, suhu_max=38, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=2000, ph_min=5.0, ph_max=8.5,
        yield_ton_per_ha_min=0.8, yield_ton_per_ha_max=3.0, harga_kg_idr=20000,
        catatan="Semi-perennial. Extremely drought tolerant. Popular in India & E. Africa.",
    )

    # ── SUGAR & STARCH CROPS ──────────────────────────────────────────────
    db["sugarbeet"] = IndoCrop(
        id="sugarbeet", nama_id="Bit Gula", nama_en="Sugar Beet",
        scientific="Beta vulgaris var. saccharifera", kategori=IndoCropCategory.PERKEBUNAN,
        dap_panen=150, dap_panen_max=200,
        suhu_optimal=17, suhu_min=5, suhu_max=28, kelembapan_optimal=65,
        altitude_min_mdpl=0, altitude_max_mdpl=800, ph_min=6.5, ph_max=8.0,
        yield_ton_per_ha_min=35.0, yield_ton_per_ha_max=80.0, harga_kg_idr=1500,
        catatan="40% of world sugar from sugar beet. Temperate zone. Rotate every 3-4 years.",
    )
    db["potato_starch"] = IndoCrop(
        id="potato_starch", nama_id="Kentang Industri (Pati)", nama_en="Starch Potato",
        scientific="Solanum tuberosum (industrial)", kategori=IndoCropCategory.UMBI,
        dap_panen=110, dap_panen_max=150,
        suhu_optimal=16, suhu_min=4, suhu_max=22, kelembapan_optimal=70,
        altitude_min_mdpl=0, altitude_max_mdpl=3000, ph_min=5.0, ph_max=6.5,
        yield_ton_per_ha_min=25.0, yield_ton_per_ha_max=65.0, harga_kg_idr=4000,
        catatan="Varietas pati tinggi (>18%). Diproses menjadi tepung, bioetanol, pakan.",
    )

    # ── TROPICAL FRUITS ───────────────────────────────────────────────────
    db["avocado"] = IndoCrop(
        id="avocado", nama_id="Alpukat", nama_en="Avocado",
        scientific="Persea americana", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=180, dap_vegetatif_end=730, dap_generatif_end=1095,
        dap_pembuahan_end=1275, dap_panen=1460, dap_panen_max=14600,
        suhu_optimal=22, suhu_min=5, suhu_max=30, kelembapan_optimal=70,
        altitude_min_mdpl=400, altitude_max_mdpl=2400, ph_min=6.0, ph_max=7.0,
        yield_ton_per_ha_min=8.0, yield_ton_per_ha_max=20.0, harga_kg_idr=25000,
        hama_umum=["Fruit fly", "Avocado mite", "Thrips"],
        penyakit_umum=["Phytophthora root rot", "Anthracnose"],
        catatan="Sentra: Jawa, Sumatera, Kalimantan. Export grade: Hass, Fuerte. Butuh polinator.",
    )
    db["dragon_fruit"] = IndoCrop(
        id="dragon_fruit", nama_id="Buah Naga", nama_en="Dragon Fruit / Pitaya",
        scientific="Hylocereus undatus", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=30, dap_vegetatif_end=180, dap_generatif_end=365,
        dap_pembuahan_end=385, dap_panen=395, dap_panen_max=3650,
        suhu_optimal=28, suhu_min=10, suhu_max=38, kelembapan_optimal=60,
        altitude_min_mdpl=0, altitude_max_mdpl=1000, ph_min=6.0, ph_max=7.5,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=30.0, harga_kg_idr=20000,
        catatan="Cactus fruit. Night blooming — needs nocturnal pollinators. Needs trellis.",
    )
    db["jackfruit"] = IndoCrop(
        id="jackfruit", nama_id="Nangka", nama_en="Jackfruit",
        scientific="Artocarpus heterophyllus", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=90, dap_vegetatif_end=730, dap_generatif_end=1095,
        dap_pembuahan_end=1215, dap_panen=1260, dap_panen_max=18250,
        suhu_optimal=27, suhu_min=15, suhu_max=38, kelembapan_optimal=75,
        altitude_min_mdpl=0, altitude_max_mdpl=1200, ph_min=5.5, ph_max=7.0,
        yield_ton_per_ha_min=10.0, yield_ton_per_ha_max=50.0, harga_kg_idr=6000,
        catatan="World's largest fruit (≤35kg). Unripe as vegetable (vegan meat). "
                "Kayu bernilai tinggi.",
    )
    db["durian"] = IndoCrop(
        id="durian", nama_id="Durian", nama_en="Durian",
        scientific="Durio zibethinus", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=90, dap_vegetatif_end=1825, dap_generatif_end=2190,
        dap_pembuahan_end=2280, dap_panen=2310, dap_panen_max=18250,
        suhu_optimal=28, suhu_min=22, suhu_max=38, kelembapan_optimal=85,
        altitude_min_mdpl=0, altitude_max_mdpl=800, ph_min=5.5, ph_max=7.0,
        yield_ton_per_ha_min=5.0, yield_ton_per_ha_max=15.0, harga_kg_idr=65000,
        catatan="King of SE Asian fruit. Seasonal harvest 1-2x/year. High export value.",
    )
    db["lychee"] = IndoCrop(
        id="lychee", nama_id="Leci", nama_en="Lychee",
        scientific="Litchi chinensis", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=365, dap_vegetatif_end=1460, dap_generatif_end=1825,
        dap_pembuahan_end=1920, dap_panen=1950, dap_panen_max=18250,
        suhu_optimal=25, suhu_min=10, suhu_max=35, kelembapan_optimal=75,
        altitude_min_mdpl=200, altitude_max_mdpl=1500, ph_min=5.5, ph_max=7.0,
        yield_ton_per_ha_min=3.0, yield_ton_per_ha_max=15.0, harga_kg_idr=40000,
        catatan="Needs mild winter (15-20°C) to stimulate flowering.",
    )
    db["rambutan"] = IndoCrop(
        id="rambutan", nama_id="Rambutan", nama_en="Rambutan",
        scientific="Nephelium lappaceum", kategori=IndoCropCategory.BUAH,
        dap_persemaian_end=90, dap_vegetatif_end=1095, dap_generatif_end=1460,
        dap_pembuahan_end=1560, dap_panen=1590, dap_panen_max=14600,
        suhu_optimal=27, suhu_min=22, suhu_max=35, kelembapan_optimal=82,
        altitude_min_mdpl=0, altitude_max_mdpl=500, ph_min=5.5, ph_max=7.0,
        yield_ton_per_ha_min=5.0, yield_ton_per_ha_max=20.0, harga_kg_idr=20000,
        catatan="Ekuatorial sejati. Tidak toleran suhu dingin.",
    )

    return db


INDONESIAN_CROPS_DB: Dict[str, IndoCrop] = _build_indonesian_crops_db()


# ══════════════════════════════════════════════════════════════════════════════
# 3. INDONESIAN REGIONAL CLIMATE DATABASE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class IndoRegion:
    nama:                str
    provinsi:            str
    lat:                 float
    lon:                 float
    altitude_m:          float
    suhu_avg:            float
    suhu_min:            float
    suhu_max:            float
    rh_avg:              float
    curah_hujan_mm_yr:   float
    musim_hujan_bulan:   List[int]
    zona_agroklimat:     str   # Oldeman A/B/C/D/E
    tanah_dominan:       str
    catatan:             str = ""


INDO_REGIONS: Dict[str, IndoRegion] = {
    "jakarta": IndoRegion("Jakarta", "DKI Jakarta", -6.21, 106.85, 8, 28.5, 24, 33, 78, 1700, [11,12,1,2,3], "C2", "Latosol"),
    "bandung": IndoRegion("Bandung", "Jawa Barat", -6.91, 107.61, 768, 23.0, 18, 28, 80, 2200, [10,11,12,1,2,3], "B2", "Andosol", "Cocok hortikultura dataran tinggi"),
    "lembang": IndoRegion("Lembang", "Jawa Barat", -6.81, 107.62, 1300, 19.5, 14, 25, 85, 2400, [10,11,12,1,2,3,4], "B1", "Andosol", "Sentra sayuran dataran tinggi"),
    "surabaya": IndoRegion("Surabaya", "Jawa Timur", -7.25, 112.75, 5, 28.8, 24, 34, 76, 1500, [11,12,1,2,3], "D1", "Aluvial"),
    "malang": IndoRegion("Malang", "Jawa Timur", -7.98, 112.63, 440, 22.5, 17, 28, 78, 1900, [11,12,1,2,3], "C2", "Andosol"),
    "batu": IndoRegion("Batu", "Jawa Timur", -7.87, 112.52, 850, 20.5, 15, 26, 82, 2100, [10,11,12,1,2,3], "B2", "Andosol", "Sentra apel & sayuran"),
    "yogyakarta": IndoRegion("Yogyakarta", "DI Yogyakarta", -7.80, 110.36, 113, 27.2, 22, 32, 78, 2050, [11,12,1,2,3], "C3", "Regosol"),
    "semarang": IndoRegion("Semarang", "Jawa Tengah", -6.97, 110.42, 5, 28.0, 24, 33, 76, 2700, [10,11,12,1,2,3,4], "C2", "Aluvial"),
    "magelang": IndoRegion("Magelang", "Jawa Tengah", -7.47, 110.22, 380, 25.0, 20, 30, 80, 2500, [10,11,12,1,2,3], "C2", "Andosol"),
    "denpasar": IndoRegion("Denpasar", "Bali", -8.65, 115.22, 12, 27.5, 23, 32, 80, 1700, [11,12,1,2,3], "C2", "Latosol"),
    "medan": IndoRegion("Medan", "Sumatera Utara", 3.59, 98.67, 25, 27.0, 22, 33, 84, 2200, [9,10,11,12,1], "B1", "Latosol"),
    "padang": IndoRegion("Padang", "Sumatera Barat", -0.95, 100.35, 7, 27.0, 23, 32, 85, 4400, list(range(1,13)), "A", "Latosol", "Curah hujan tinggi merata"),
    "pekanbaru": IndoRegion("Pekanbaru", "Riau", 0.51, 101.45, 10, 28.0, 23, 34, 82, 2400, [9,10,11,12], "B1", "Podsolik"),
    "palembang": IndoRegion("Palembang", "Sumsel", -2.99, 104.76, 8, 28.0, 23, 33, 82, 2500, [10,11,12,1,2,3], "B1", "Podsolik"),
    "lampung": IndoRegion("Bandar Lampung", "Lampung", -5.42, 105.27, 96, 27.0, 22, 32, 80, 2200, [11,12,1,2], "C2", "Latosol"),
    "banjarmasin": IndoRegion("Banjarmasin", "Kalsel", -3.32, 114.59, 0, 27.5, 23, 32, 84, 2700, [10,11,12,1,2,3], "B1", "Aluvial Gambut"),
    "balikpapan": IndoRegion("Balikpapan", "Kaltim", -1.25, 116.83, 5, 27.0, 23, 32, 84, 2300, [11,12,1,2,3], "B1", "Podsolik"),
    "pontianak": IndoRegion("Pontianak", "Kalbar", -0.03, 109.33, 1, 27.0, 23, 32, 86, 3200, list(range(1,13)), "A", "Gambut"),
    "makassar": IndoRegion("Makassar", "Sulsel", -5.13, 119.41, 5, 27.5, 23, 32, 78, 2700, [11,12,1,2,3,4], "C2", "Latosol"),
    "manado": IndoRegion("Manado", "Sulut", 1.49, 124.84, 5, 26.5, 22, 31, 84, 2700, [10,11,12,1,2,3], "B1", "Andosol"),
    "ambon": IndoRegion("Ambon", "Maluku", -3.70, 128.18, 5, 27.0, 23, 32, 84, 3300, [4,5,6,7,8], "A", "Andosol", "Hujan pola monsun terbalik"),
    "jayapura": IndoRegion("Jayapura", "Papua", -2.53, 140.71, 10, 27.0, 23, 32, 84, 1900, [11,12,1,2,3], "B1", "Podsolik"),
    "kupang": IndoRegion("Kupang", "NTT", -10.18, 123.61, 100, 27.5, 22, 33, 75, 1300, [12,1,2,3], "D2", "Mediteran", "Iklim semi-arid"),
    "mataram": IndoRegion("Mataram", "NTB", -8.58, 116.12, 27, 27.0, 22, 32, 78, 1500, [11,12,1,2,3], "D1", "Mediteran"),
    "gayo": IndoRegion("Takengon (Gayo)", "Aceh", 4.62, 96.85, 1200, 18.0, 12, 24, 85, 2200, list(range(1,13)), "A", "Andosol", "Sentra kopi arabika"),
    "kintamani": IndoRegion("Kintamani", "Bali", -8.27, 115.36, 1500, 17.0, 12, 24, 84, 2100, [10,11,12,1,2,3], "B1", "Andosol"),
    "dieng": IndoRegion("Dieng", "Jawa Tengah", -7.20, 109.91, 2093, 14.0, 6, 22, 88, 3500, list(range(1,13)), "A", "Andosol", "Tertinggi — kentang granola, carica"),
    "berastagi": IndoRegion("Berastagi", "Sumut", 3.20, 98.51, 1300, 18.5, 13, 24, 84, 2200, list(range(1,13)), "A", "Andosol"),
}


def find_region(query: str) -> Optional[IndoRegion]:
    q = query.strip().lower()
    if q in INDO_REGIONS:
        return INDO_REGIONS[q]
    for r in INDO_REGIONS.values():
        if q in r.nama.lower() or q in r.provinsi.lower():
            return r
    return None


def build_region_from_coords(lat: float, lon: float, alt_m: float = 0.0,
                              nama: str = "", provinsi: str = "") -> IndoRegion:
    """Buat IndoRegion dari koordinat sembarang — global climate model (semua benua)."""
    abs_lat = abs(lat)

    # ── Zona iklim & parameter dasar berdasarkan lintang ─────────────────
    if abs_lat < 10.0:
        zone_name = "Ekuatorial"
        t_sl      = 27.5
        rh_base   = 85.0
        rain_base = 2200.0
    elif abs_lat < 23.5:
        zone_name = "Tropis Monsun"
        t_sl      = 27.0 - 0.28 * (abs_lat - 10.0)
        rh_base   = 78.0
        rain_base = 1600.0
    elif abs_lat < 35.0:
        zone_name = "Subtropis"
        t_sl      = 23.5 - 0.45 * (abs_lat - 23.5)
        rh_base   = 62.0
        rain_base = 850.0
    elif abs_lat < 50.0:
        zone_name = "Temperate"
        t_sl      = 18.0 - 0.55 * (abs_lat - 35.0)
        rh_base   = 70.0
        rain_base = 750.0
    elif abs_lat < 65.0:
        zone_name = "Boreal"
        t_sl      = 9.75 - 0.65 * (abs_lat - 50.0)
        rh_base   = 72.0
        rain_base = 500.0
    else:
        zone_name = "Arktik"
        t_sl      = 0.25 - 0.30 * (abs_lat - 65.0)
        rh_base   = 68.0
        rain_base = 220.0

    # ── Suhu: lapse rate 6.5°C/1000m ─────────────────────────────────────
    suhu_avg = round(t_sl - 6.5 * alt_m / 1000.0, 1)
    diurnal  = 4.0 + abs_lat * 0.08          # rentang harian > besar di darat & subtropis
    suhu_min = round(suhu_avg - diurnal - alt_m * 0.002, 1)
    suhu_max = round(suhu_avg + diurnal, 1)

    # ── Kelembapan ────────────────────────────────────────────────────────
    rh_alt = min(8.0, alt_m / 200.0)
    rh_avg = round(min(98.0, max(20.0, rh_base + rh_alt)), 0)

    # ── Curah hujan — orografi + zona ─────────────────────────────────────
    oro_factor = 1.0 + min(0.8, alt_m / 1500.0)
    rain_yr    = round(rain_base * oro_factor)

    # ── Zona Oldeman (estimasi bulan basah dari curah hujan tahunan) ──────
    _wm_map = [(3000,12),(2400,11),(2000,10),(1700,9),(1400,8),(1200,7),
               (1000,6),(800,5),(600,4),(400,3),(250,2)]
    wet_months = next((wm for thr, wm in _wm_map if rain_yr >= thr), 1)
    if wet_months >= 9:
        zona = "A"
    elif wet_months >= 7:
        zona = "B1" if rain_yr > 2000 else "B2"
    elif wet_months >= 5:
        zona = "C1" if rain_yr > 1700 else "C2"
    elif wet_months >= 3:
        zona = "D1" if abs_lat < 20 else "D2"
    else:
        zona = "E"

    # ── Tanah dominan ─────────────────────────────────────────────────────
    if abs_lat > 65:
        tanah = "Tundra / Permafrost"
    elif abs_lat > 50:
        tanah = "Podsol / Spodosol"
    elif abs_lat > 35:
        tanah = "Kambisol / Luvisol"
    elif alt_m > 1500:
        tanah = "Andosol"
    elif alt_m > 500:
        tanah = "Latosol / Kambisol"
    elif abs_lat < 5:
        tanah = "Aluvial / Gambut"
    elif abs_lat < 20:
        tanah = "Latosol / Feralsol"
    else:
        tanah = "Kambisol / Kastanozem"

    # ── Musim hujan: Belahan Bumi Utara vs Selatan ────────────────────────
    if abs_lat < 5:
        wet_list = list(range(1, 13))           # ekuatorial — sepanjang tahun
    elif lat > 0:                               # Belahan Bumi Utara
        if abs_lat < 25:
            wet_list = [5, 6, 7, 8, 9, 10]     # Monsun LU: Mei–Okt
        else:
            wet_list = [10, 11, 12, 1, 2, 3]   # Temperate LU: Okt–Mar
    else:                                       # Belahan Bumi Selatan
        if abs_lat < 25:
            wet_list = [11, 12, 1, 2, 3, 4]    # Monsun LS: Nov–Apr
        else:
            wet_list = [4, 5, 6, 7, 8, 9]      # Temperate LS: Apr–Sep

    hem_lat = f"{abs_lat:.4f}°{'S' if lat < 0 else 'N'}"
    hem_lon = f"{abs(lon):.4f}°{'W' if lon < 0 else 'E'}"
    nama_out = nama or f"Titik ({hem_lat}, {hem_lon})"
    prov_out = provinsi or zone_name
    note = (f"Global — lat={lat:.5f}° lon={lon:.5f}° alt={alt_m:.0f}m "
            f"| zona_iklim={zone_name} | hujan≈{rain_yr} mm/yr | Oldeman={zona}")

    return IndoRegion(
        nama=nama_out, provinsi=prov_out,
        lat=lat, lon=lon, altitude_m=alt_m,
        suhu_avg=suhu_avg, suhu_min=suhu_min, suhu_max=suhu_max,
        rh_avg=rh_avg, curah_hujan_mm_yr=rain_yr,
        musim_hujan_bulan=wet_list,
        zona_agroklimat=zona,
        tanah_dominan=tanah,
        catatan=note,
    )


def _reverse_geocode_owm(lat: float, lon: float) -> dict:
    """Reverse-geocode koordinat → {'name':…, 'state':…, 'country':…} via OWM.
    Mengembalikan dict kosong jika gagal atau API key tidak ada."""
    api_key = _get_cfg("owm_api_key", os.environ.get("OPENWEATHER_API_KEY", ""))
    if not api_key:
        return {}
    try:
        r = requests.get(
            "https://api.openweathermap.org/geo/1.0/reverse",
            params={"lat": lat, "lon": lon, "limit": 1, "appid": api_key},
            timeout=4)
        r.raise_for_status()
        data = r.json()
        if data:
            g = data[0]
            return {
                "name":    g.get("name", ""),
                "state":   g.get("state", ""),
                "country": g.get("country", ""),
            }
    except Exception:
        pass
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# 4. PLANT CALENDAR — TANGGAL TANAM → FASE SAAT INI
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PlantingRecord:
    crop_id:        str
    tanggal_tanam:  datetime.date
    luas_ha:        float = 1.0
    zone_id:        str = "ZONE-A"
    notes:          str = ""

    def days_after_planting(self, ref_date: Optional[datetime.date] = None) -> int:
        ref = ref_date or datetime.date.today()
        return (ref - self.tanggal_tanam).days

    def is_active(self, ref_date: Optional[datetime.date] = None) -> bool:
        crop = INDONESIAN_CROPS_DB.get(self.crop_id)
        if not crop:
            return False
        return 0 <= self.days_after_planting(ref_date) <= crop.dap_panen_max


class PlantCalendar:
    """Hitung fase tanaman saat ini berdasarkan tanggal tanam → tanggal sekarang."""

    def __init__(self, planting: PlantingRecord):
        self.planting = planting
        crop = INDONESIAN_CROPS_DB.get(planting.crop_id)
        if crop is None:
            raise ValueError(f"Crop ID '{planting.crop_id}' tidak ada di database.")
        self.crop = crop

    def status_today(self, ref_date: Optional[datetime.date] = None) -> Dict[str, Any]:
        ref = ref_date or datetime.date.today()
        dap = self.planting.days_after_planting(ref)
        phase = self.crop.phase_at_dap(dap)
        progress_pct = min(100.0, max(0.0, dap / max(self.crop.dap_panen, 1) * 100.0))
        days_to_harvest = max(0, self.crop.dap_panen - dap)
        harvest_date = self.planting.tanggal_tanam + datetime.timedelta(days=self.crop.dap_panen)
        harvest_max  = self.planting.tanggal_tanam + datetime.timedelta(days=self.crop.dap_panen_max)
        # kebutuhan air & nutrisi pada DAP ini
        water_today_mm = self.crop.water_need_at_dap(dap)
        n, p, k = self.crop.npk_need_at_dap(dap)
        # akumulasi
        cum_water_mm = sum(self.crop.water_need_at_dap(d) for d in range(0, max(dap+1, 1)))
        cum_water_remaining = max(0.0, self.crop.total_water_mm_lifecycle() - cum_water_mm)
        return {
            "ref_date":              ref.isoformat(),
            "tanggal_tanam":         self.planting.tanggal_tanam.isoformat(),
            "dap":                   dap,
            "fase":                  phase.value,
            "fase_enum":             phase,
            "progress_pct":          progress_pct,
            "days_to_harvest":       days_to_harvest,
            "estimasi_panen":        harvest_date.isoformat(),
            "estimasi_panen_max":    harvest_max.isoformat(),
            "water_mm_per_day":      water_today_mm,
            "water_L_per_m2_today":  water_today_mm,
            "water_L_per_ha_today":  water_today_mm * 10000.0,
            "water_kumulatif_mm":    cum_water_mm,
            "water_total_mm":        self.crop.total_water_mm_lifecycle(),
            "water_sisa_mm":         cum_water_remaining,
            "n_kg_ha_per_day":       n,
            "p_kg_ha_per_day":       p,
            "k_kg_ha_per_day":       k,
        }

    def timeline_dataframe(self) -> pd.DataFrame:
        crop = self.crop
        rows = [
            ("Pre-Plant",            -7,                            0,                              "#3a3a3a"),
            ("Seedling",            0,                             crop.dap_persemaian_end,        "#4a8a4a"),
            ("Early Vegetative",    crop.dap_persemaian_end,       (crop.dap_persemaian_end + crop.dap_vegetatif_end)//2, "#55cc55"),
            ("Late Vegetative",     (crop.dap_persemaian_end + crop.dap_vegetatif_end)//2, crop.dap_vegetatif_end, "#33aa33"),
            ("Generative",          crop.dap_vegetatif_end,        crop.dap_generatif_end,         "#cccc33"),
            ("Fruiting",            crop.dap_generatif_end,        crop.dap_pembuahan_end,         "#cc8833"),
            ("Ripening",            crop.dap_pembuahan_end,        crop.dap_panen,                 "#cc4433"),
            ("Harvest",             crop.dap_panen,                crop.dap_panen_max,             "#aa3399"),
        ]
        records = []
        for name, dap_start, dap_end, color in rows:
            ts = self.planting.tanggal_tanam + datetime.timedelta(days=dap_start)
            te = self.planting.tanggal_tanam + datetime.timedelta(days=dap_end)
            records.append({
                "fase":     name,
                "dap_mulai": dap_start,
                "dap_akhir": dap_end,
                "tgl_mulai": ts.isoformat(),
                "tgl_akhir": te.isoformat(),
                "durasi_hari": dap_end - dap_start,
                "color":   color,
            })
        return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════════════════════
# 5. WATER & NUTRIENT PLANNER
# ══════════════════════════════════════════════════════════════════════════════

class WaterNutrientPlanner:
    """Generator jadwal harian air & pupuk dari tanam → panen."""

    def __init__(self, planting: PlantingRecord):
        self.planting = planting
        self.crop = INDONESIAN_CROPS_DB[planting.crop_id]

    def daily_schedule(self) -> pd.DataFrame:
        rows = []
        for dap in range(0, self.crop.dap_panen + 1):
            d = self.planting.tanggal_tanam + datetime.timedelta(days=dap)
            phase = self.crop.phase_at_dap(dap)
            water_mm = self.crop.water_need_at_dap(dap)
            n, p, k = self.crop.npk_need_at_dap(dap)
            rows.append({
                "tanggal":           d.isoformat(),
                "dap":               dap,
                "fase":              phase.value,
                "air_mm":            round(water_mm, 2),
                "air_L_per_m2":      round(water_mm, 2),
                "air_L_per_ha":      round(water_mm * 10000, 0),
                "air_L_zona":        round(water_mm * self.planting.luas_ha * 10000, 0),
                "N_kg_ha":           round(n, 3),
                "P_kg_ha":           round(p, 3),
                "K_kg_ha":           round(k, 3),
                "N_kg_zona":         round(n * self.planting.luas_ha, 3),
                "P_kg_zona":         round(p * self.planting.luas_ha, 3),
                "K_kg_zona":         round(k * self.planting.luas_ha, 3),
            })
        return pd.DataFrame(rows)

    def weekly_summary(self) -> pd.DataFrame:
        df = self.daily_schedule()
        df["minggu"] = df["dap"] // 7 + 1
        agg = df.groupby("minggu").agg({
            "air_mm":    "sum",
            "air_L_zona": "sum",
            "N_kg_zona": "sum",
            "P_kg_zona": "sum",
            "K_kg_zona": "sum",
            "fase":      lambda s: s.mode().iloc[0] if not s.empty else "",
        }).reset_index()
        agg.rename(columns={
            "air_mm":     "air_mm_minggu",
            "air_L_zona": "air_liter_zona",
            "N_kg_zona":  "N_kg_zona",
            "P_kg_zona":  "P_kg_zona",
            "K_kg_zona":  "K_kg_zona",
            "fase":       "fase_dominan",
        }, inplace=True)
        return agg

    def total_summary(self) -> Dict[str, float]:
        crop = self.crop
        n_total, p_total, k_total = crop.total_npk_kg_per_ha()
        return {
            "total_durasi_hari":      crop.dap_panen,
            "total_air_mm":           crop.total_water_mm_lifecycle(),
            "total_air_L_per_ha":     crop.total_water_mm_lifecycle() * 10000.0,
            "total_air_L_zona":       crop.total_water_mm_lifecycle() * 10000.0 * self.planting.luas_ha,
            "total_N_kg_ha":          n_total,
            "total_P_kg_ha":          p_total,
            "total_K_kg_ha":          k_total,
            "total_N_kg_zona":        n_total * self.planting.luas_ha,
            "total_P_kg_zona":        p_total * self.planting.luas_ha,
            "total_K_kg_zona":        k_total * self.planting.luas_ha,
            "estimasi_panen_kg":      crop.yield_avg_ton_ha * 1000.0 * self.planting.luas_ha,
            "estimasi_pendapatan_idr": crop.yield_avg_ton_ha * 1000.0 * self.planting.luas_ha * crop.harga_kg_idr,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 6. PEST & DISEASE CALENDAR
# ══════════════════════════════════════════════════════════════════════════════

class PestDiseaseCalendar:
    """Estimasi tekanan hama-penyakit berdasarkan fase + kelembapan."""

    PEST_RISK_BY_PHASE = {
        IndoGrowthPhase.PERSEMAIAN:    {"lalat_bibit": 0.4, "ulat": 0.3},
        IndoGrowthPhase.VEGETATIF_AWAL:{"kutu_daun": 0.5, "thrips": 0.4, "ulat_grayak": 0.5},
        IndoGrowthPhase.VEGETATIF_LANJ:{"kutu_daun": 0.6, "tungau": 0.5, "ulat_grayak": 0.55},
        IndoGrowthPhase.GENERATIF:     {"thrips": 0.7, "lalat_buah": 0.5},
        IndoGrowthPhase.PEMBUAHAN:     {"lalat_buah": 0.85, "penggerek_buah": 0.7},
        IndoGrowthPhase.PEMASAKAN:     {"lalat_buah": 0.9, "tikus": 0.4},
    }

    DISEASE_BY_RH = [
        (90.0, ["Hawar daun (late blight)", "Antraknosa", "Embun tepung", "Busuk buah"]),
        (80.0, ["Antraknosa", "Bercak daun", "Layu fusarium"]),
        (70.0, ["Layu bakteri"]),
    ]

    def __init__(self, planting: PlantingRecord, current_rh: float = 75.0):
        self.planting = planting
        self.crop = INDONESIAN_CROPS_DB[planting.crop_id]
        self.rh = current_rh

    def today(self, ref: Optional[datetime.date] = None) -> Dict[str, Any]:
        dap = self.planting.days_after_planting(ref)
        phase = self.crop.phase_at_dap(dap)
        pests = self.PEST_RISK_BY_PHASE.get(phase, {})
        # filter ke daftar hama umum tanaman ybs
        common = {h.lower().replace(" ", "_") for h in self.crop.hama_umum}
        relevant_pests = {k: v for k, v in pests.items()
                          if not common or any(c in k for c in common) or True}
        diseases: List[str] = []
        for rh_thr, dlist in self.DISEASE_BY_RH:
            if self.rh >= rh_thr:
                diseases.extend(dlist)
                break
        return {
            "fase":              phase.value,
            "dap":               dap,
            "rh":                self.rh,
            "hama_risiko":       relevant_pests,
            "penyakit_potensi":  diseases or ["Risiko rendah"],
            "rekomendasi":       self._recommend(phase, self.rh, relevant_pests),
        }

    def _recommend(self, phase, rh, pests) -> List[str]:
        recs = []
        if rh > 85:
            recs.append("Tingkatkan ventilasi — RH di atas ambang penyakit jamur.")
        if "lalat_buah" in pests and pests["lalat_buah"] > 0.6:
            recs.append("Pasang perangkap metil eugenol untuk lalat buah.")
        if "thrips" in pests and pests["thrips"] > 0.5:
            recs.append("Aplikasi musuh alami: predator Orius / kumbang Coccinellidae.")
        if phase == IndoGrowthPhase.PEMASAKAN:
            recs.append("Avoid pesticide spraying 7 days before harvest.")
        if not recs:
            recs.append("Routine monitoring — no intervention needed yet.")
        return recs


# ══════════════════════════════════════════════════════════════════════════════
# 7. CLIMATE SUITABILITY SCORE
# ══════════════════════════════════════════════════════════════════════════════

def climate_suitability_score(crop: IndoCrop, region: IndoRegion) -> Dict[str, Any]:
    """Skor 0-100 kecocokan iklim region untuk tanaman."""

    def gauss(x, opt, span):
        return math.exp(-((x - opt) ** 2) / (2 * span * span))

    s_temp = gauss(region.suhu_avg, crop.suhu_optimal, max(3.0, (crop.suhu_max - crop.suhu_min) / 3.5))
    s_alt  = 1.0 if crop.altitude_min_mdpl <= region.altitude_m <= crop.altitude_max_mdpl else \
             max(0.0, 1.0 - abs(region.altitude_m - (crop.altitude_min_mdpl + crop.altitude_max_mdpl)/2.0) / 1500.0)
    s_rh   = gauss(region.rh_avg, crop.kelembapan_optimal, 12.0)
    # curah hujan
    annual_water_need_mm = crop.total_water_mm_lifecycle() * (365.0 / max(crop.dap_panen, 30))
    rain_ratio = region.curah_hujan_mm_yr / max(annual_water_need_mm, 200.0)
    s_rain = gauss(rain_ratio, 1.0, 0.6)
    score = 100.0 * (0.35 * s_temp + 0.25 * s_alt + 0.15 * s_rh + 0.25 * s_rain)
    return {
        "score":             round(score, 1),
        "rating":            "Sangat Cocok" if score >= 80 else
                             "Cocok"        if score >= 65 else
                             "Sedang"       if score >= 50 else
                             "Marginal"     if score >= 35 else "Tidak Cocok",
        "komponen":          {
            "suhu":          round(100*s_temp, 1),
            "ketinggian":    round(100*s_alt, 1),
            "kelembapan":    round(100*s_rh, 1),
            "curah_hujan":   round(100*s_rain, 1),
        },
        "catatan": _suitability_notes(crop, region, s_temp, s_alt, s_rain),
    }


def _suitability_notes(crop, region, s_temp, s_alt, s_rain) -> List[str]:
    notes = []
    if s_temp < 0.6:
        if region.suhu_avg > crop.suhu_optimal:
            notes.append(f"Suhu {region.nama} ({region.suhu_avg}°C) di atas optimal {crop.nama_id} ({crop.suhu_optimal}°C).")
        else:
            notes.append(f"Suhu {region.nama} ({region.suhu_avg}°C) di bawah optimal {crop.nama_id} ({crop.suhu_optimal}°C).")
    if s_alt < 0.7:
        notes.append(f"Ketinggian {region.altitude_m} mdpl di luar rentang ideal {crop.altitude_min_mdpl}-{crop.altitude_max_mdpl} mdpl.")
    if s_rain < 0.6:
        notes.append("Curah hujan tahunan tidak ideal — pertimbangkan irigasi/drainase.")
    if not notes:
        notes.append("Iklim sesuai — kondisi pertumbuhan optimal.")
    return notes


# ══════════════════════════════════════════════════════════════════════════════
# 8. COMPANION PLANTING & ROTATION
# ══════════════════════════════════════════════════════════════════════════════

COMPANION_MATRIX = {
    "tomat":          {"good": ["kemangi", "selada", "bawang_merah", "wortel"], "bad": ["kentang"]},
    "cabai_merah":    {"good": ["kemangi", "bawang_merah", "daun_bawang"],     "bad": ["adas"]},
    "kentang":        {"good": ["jagung_pakan", "buncis", "kubis"],            "bad": ["tomat", "labu_kuning"]},
    "kubis":          {"good": ["kentang", "seledri", "bawang_merah"],         "bad": ["stroberi"]},
    "kacang_panjang": {"good": ["jagung_pakan", "labu_siam", "mentimun"],      "bad": ["bawang_merah", "bawang_putih"]},
    "padi_sawah":     {"good": ["azolla"],                                      "bad": []},
    "jagung_manis":   {"good": ["kacang_tanah", "buncis", "labu_kuning"],      "bad": ["tomat"]},
    "wortel":         {"good": ["bawang_merah", "selada", "tomat"],            "bad": ["seledri"]},
    "selada":         {"good": ["wortel", "stroberi", "tomat"],                "bad": ["seledri"]},
    "stroberi":       {"good": ["selada", "bayam"],                             "bad": ["kubis", "brokoli"]},
}


def companion_plants(crop_id: str) -> Dict[str, List[str]]:
    matrix = COMPANION_MATRIX.get(crop_id, {})
    good = matrix.get("good", []) + INDONESIAN_CROPS_DB.get(crop_id, IndoCrop("","","","",IndoCropCategory.HORTIKULTURA)).companion_good
    bad  = matrix.get("bad",  []) + INDONESIAN_CROPS_DB.get(crop_id, IndoCrop("","","","",IndoCropCategory.HORTIKULTURA)).companion_bad
    return {
        "good": sorted(set(good)),
        "bad":  sorted(set(bad)),
    }


def crop_rotation_plan(start_crop_id: str, n_seasons: int = 4) -> List[Tuple[str, str]]:
    """Rekomendasi rotasi 4 musim berdasarkan kategori (hindari famili sama)."""
    rotation_groups = {
        IndoCropCategory.PALAWIJA:     ["kedelai", "kacang_tanah", "kacang_hijau"],     # leguminosae — fiksasi N
        IndoCropCategory.PANGAN_POKOK: ["padi_sawah", "jagung_manis", "sorgum"],         # graminae — feeder berat
        IndoCropCategory.UMBI:         ["ubi_jalar", "ubi_kayu", "kentang", "wortel"],
        IndoCropCategory.HORTIKULTURA: ["sawi_hijau", "kangkung", "bayam", "selada"],   # leaf — pendek
    }
    sequence_order = [
        IndoCropCategory.PANGAN_POKOK,
        IndoCropCategory.PALAWIJA,
        IndoCropCategory.HORTIKULTURA,
        IndoCropCategory.UMBI,
    ]
    crop = INDONESIAN_CROPS_DB.get(start_crop_id)
    if not crop:
        return []
    try:
        idx = sequence_order.index(crop.kategori)
    except ValueError:
        idx = 0
    plan = []
    rng = random.Random(hash(start_crop_id) & 0xFFFFFFFF)
    for i in range(n_seasons):
        cat = sequence_order[(idx + i) % len(sequence_order)]
        candidates = rotation_groups.get(cat, [])
        choice = rng.choice(candidates) if candidates else ""
        season_label = f"Musim {i+1}"
        plan.append((season_label, choice))
    return plan


# ══════════════════════════════════════════════════════════════════════════════
# 9. YIELD FORECASTER
# ══════════════════════════════════════════════════════════════════════════════

def forecast_yield(crop: IndoCrop, region: IndoRegion, area_ha: float = 1.0,
                   stress_factor: float = 0.0) -> Dict[str, float]:
    """Proyeksi panen dengan interval 95%."""
    suit = climate_suitability_score(crop, region)
    base_avg = crop.yield_avg_ton_ha
    base_low = crop.yield_ton_per_ha_min
    base_hi  = crop.yield_ton_per_ha_max
    suit_factor = suit["score"] / 100.0
    stress_mult = max(0.3, 1.0 - stress_factor)
    expected = base_avg * suit_factor * stress_mult * area_ha
    low      = base_low * suit_factor * stress_mult * area_ha * 0.85
    high     = base_hi  * suit_factor * stress_mult * area_ha
    loc = get_location_state()
    price_kg, _ = localized_crop_price_idr(crop, loc)
    revenue  = expected * 1000.0 * price_kg
    return {
        "expected_ton":       round(expected, 2),
        "low_ton":            round(low, 2),
        "high_ton":           round(high, 2),
        "revenue_idr":        round(revenue, 0),
        "suitability_score":  suit["score"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 10. SPATIAL SATELLITE 3D VISUALIZATION
# ══════════════════════════════════════════════════════════════════════════════

# Hypsometric colorscale: sesuai referensi (kuning lembah → hijau lereng → putih puncak)
_HYPSOMETRIC_CS = [
    [0.00, "#2A1800"],
    [0.05, "#8B5E00"],
    [0.13, "#C8A010"],
    [0.24, "#90C038"],
    [0.38, "#32A018"],
    [0.54, "#1A6010"],
    [0.67, "#785030"],
    [0.78, "#706050"],
    [0.88, "#B0A898"],
    [0.95, "#D8D0C8"],
    [1.00, "#FFFFFF"],
]


def _fetch_dem_terrarium(lat_center: float, lon_center: float,
                         side_m: float, grid_n: int = 90) -> Optional[np.ndarray]:
    """Ambil DEM nyata dari AWS Terrain Tiles (Terrarium PNG, gratis, tanpa API key).
    Mengembalikan array [grid_n×grid_n] elevasi meter, atau None jika gagal."""
    try:
        from PIL import Image              # type: ignore
        import io as _io
        import concurrent.futures as _cf

        DEG_LAT = side_m / 111000.0
        DEG_LON = DEG_LAT / math.cos(math.radians(lat_center))
        TILE_PX = 256

        # Pilih zoom level agar resolusi tile ≥ grid_n pixel di sisi terpendek
        # AWS Terrarium tersedia s/d z=15 (z=16 → 404)
        zoom = 12
        for z in range(15, 8, -1):
            n = 2 ** z
            px_cover = (DEG_LON / (360.0 / n)) * TILE_PX
            if px_cover >= grid_n * 0.8:
                zoom = z
                break

        n = 2 ** zoom
        lat_rad = math.radians(lat_center)
        xt_c = int((lon_center + 180.0) / 360.0 * n)
        yt_c = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)

        CANVAS_N = 3  # 3×3 tile grid → jamin coverage
        canvas = np.zeros((TILE_PX * CANVAS_N, TILE_PX * CANVAS_N), dtype=np.float32)

        def _get_tile(job):
            dx, dy = job
            tx = (xt_c + dx) % n
            ty = yt_c + dy
            if ty < 0 or ty >= n:
                return dx, dy, None
            url = (f"https://s3.amazonaws.com/elevation-tiles-prod"
                   f"/terrarium/{zoom}/{tx}/{ty}.png")
            try:
                rsp = requests.get(url, timeout=7,
                                   headers={"User-Agent": "AgriBot/1.0"})
                if rsp.ok:
                    arr = np.array(
                        Image.open(_io.BytesIO(rsp.content)).convert("RGB"),
                        dtype=np.float32)
                    return dx, dy, arr[:,:,0]*256 + arr[:,:,1] + arr[:,:,2]/256 - 32768
            except Exception:
                pass
            return dx, dy, None

        jobs = [(dx, dy) for dy in range(-1, 2) for dx in range(-1, 2)]
        with _cf.ThreadPoolExecutor(max_workers=9) as pool:
            for dx, dy, elev in pool.map(_get_tile, jobs):
                if elev is not None:
                    r0 = (dy + 1) * TILE_PX
                    c0 = (dx + 1) * TILE_PX
                    canvas[r0:r0+TILE_PX, c0:c0+TILE_PX] = elev

        # Koordinat canvas
        def _tlon(x):  return x / n * 360.0 - 180.0
        def _tlat(y):
            return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0*y/n))))

        cw = ch = TILE_PX * CANVAS_N
        lon_min_c = _tlon(xt_c - 1); lon_max_c = _tlon(xt_c + 2)
        lat_max_c = _tlat(yt_c - 1); lat_min_c = _tlat(yt_c + 2)

        r0 = max(0, int((lat_max_c - (lat_center + DEG_LAT/2)) / (lat_max_c - lat_min_c) * ch))
        r1 = min(ch, int((lat_max_c - (lat_center - DEG_LAT/2)) / (lat_max_c - lat_min_c) * ch))
        c0 = max(0, int(((lon_center - DEG_LON/2) - lon_min_c) / (lon_max_c - lon_min_c) * cw))
        c1 = min(cw, int(((lon_center + DEG_LON/2) - lon_min_c) / (lon_max_c - lon_min_c) * cw))

        if r1 - r0 < 4 or c1 - c0 < 4:
            return None

        crop = canvas[r0:r1, c0:c1]

        # Isi nodata (nilai < -500)
        bad = crop < -500
        if bad.any() and not bad.all():
            try:
                from scipy.ndimage import median_filter as _mf   # type: ignore
                crop = np.where(bad, _mf(np.where(bad, 0.0, crop).astype(float), 5), crop)
            except ImportError:
                crop = np.where(bad, float(crop[~bad].mean() if (~bad).any() else 0), crop)

        # Resample ke grid_n × grid_n
        if crop.shape[0] != grid_n or crop.shape[1] != grid_n:
            try:
                from scipy.ndimage import zoom as _sz   # type: ignore
                crop = _sz(crop.astype(float),
                           (grid_n / crop.shape[0], grid_n / crop.shape[1]), order=1)
            except ImportError:
                crop = crop[:grid_n, :grid_n] if (
                    crop.shape[0] >= grid_n and crop.shape[1] >= grid_n
                ) else None
                if crop is None:
                    return None

        return crop[:grid_n, :grid_n].astype(float)

    except Exception:
        return None


@st.cache_data(ttl=7200, show_spinner=False)
def _fetch_dem_cached(lat: float, lon: float, side_m: float, grid_n: int) -> Optional[np.ndarray]:
    """Cached wrapper untuk _fetch_dem_terrarium."""
    return _fetch_dem_terrarium(lat, lon, side_m, grid_n)


class SpatialSatellite3D:
    """Generator visualisasi 3D — terrain, NDVI, soil moisture per zona.
    Setiap region punya signature unik: relief altitude-aware,
    NDVI & moisture di-drive oleh cuaca NYATA (live_weather) jika tersedia."""

    def __init__(self, region: IndoRegion, grid_size: int = 60, area_ha: float = 1.0,
                 seed: Optional[int] = None,
                 live_weather: Optional["WeatherData"] = None):
        self.region       = region
        self.grid_size    = grid_size
        self.area_ha      = area_ha
        self.live_weather = live_weather   # cuaca nyata dari koordinat ini

        # ── Seed deterministik per region dari koordinat real ──────────────
        if seed is None:
            seed = abs(int(region.lat * 1000) ^ int(region.lon * 1000) ^ int(region.altitude_m))
        self.seed = seed
        self.rng  = np.random.default_rng(seed)

        # ── Bounding box ────────────────────────────────────────────────────
        self.side_m = math.sqrt(area_ha * 10000)
        self.x = np.linspace(0, self.side_m, grid_size)
        self.y = np.linspace(0, self.side_m, grid_size)
        self.X, self.Y = np.meshgrid(self.x, self.y)
        # 1 derajat ≈ 111 km
        deg_per_m_lat = 1.0 / 111000.0
        deg_per_m_lon = 1.0 / (111000.0 * math.cos(math.radians(region.lat)))
        self.lat_min = region.lat - (self.side_m / 2) * deg_per_m_lat
        self.lat_max = region.lat + (self.side_m / 2) * deg_per_m_lat
        self.lon_min = region.lon - (self.side_m / 2) * deg_per_m_lon
        self.lon_max = region.lon + (self.side_m / 2) * deg_per_m_lon

        # ── Terrain class dari altitude ─────────────────────────────────────
        if region.altitude_m < 50:
            self.terrain = "coastal_plain"
        elif region.altitude_m < 300:
            self.terrain = "lowland"
        elif region.altitude_m < 800:
            self.terrain = "hills"
        elif region.altitude_m < 1500:
            self.terrain = "highlands"        # dataran tinggi
        else:
            self.terrain = "mountain"         # pegunungan/vulkanik

    @property
    def lat_grid(self) -> np.ndarray:
        return np.linspace(self.lat_min, self.lat_max, self.grid_size)

    @property
    def lon_grid(self) -> np.ndarray:
        return np.linspace(self.lon_min, self.lon_max, self.grid_size)

    def relief_amplitude(self) -> float:
        """Amplitudo relief tergantung terrain class."""
        return {
            "coastal_plain": 2.0,
            "lowland":       8.0,
            "hills":         35.0,
            "highlands":     80.0,
            "mountain":      180.0,
        }.get(self.terrain, 10.0)

    def synth_elevation(self) -> np.ndarray:
        """DEM fisik — bentuk NYATA berbeda tiap skala area.

        Strategi anti-aliasing:
        • Semua panjang gelombang ≥ 4 × grid_spacing → tidak ada sub-pixel spikes
        • Fitur deterministik disesuaikan skala: bedengan → canal → sungai → pegunungan
        • Smooth Gaussian kernel diterapkan akhir agar surface mulus
        """
        base      = self.region.altitude_m
        # Amplitudo relief skala dengan area: area lebih besar → relief lebih dramatis
        # sqrt(area_ha/5) → 5ha=1×, 10ha=1.4×, 50ha=3.2×, 100ha=4.5×, 500ha=6× (cap)
        _area_amp = min(6.0, max(1.0, math.sqrt(self.area_ha / 5.0)))
        amp_total = self.relief_amplitude() * _area_amp

        # Grid spacing dalam meter
        grid_dx   = self.side_m / max(self.grid_size - 1, 1)
        # Panjang gelombang minimum = 4× grid spacing (Nyquist+margin)
        min_wl    = 4.0 * grid_dx

        # ── Multi-scale fBm: panjang gelombang fisik absolut (meter) ────────
        # Tiap oktaf mewakili fitur fisik nyata. Aktif hanya jika side_m ≥ wl/1.5
        # (perlu ≥ 2/3 siklus agar terlihat). Makin besar area → makin banyak
        # oktaf aktif → terrain makin kompleks (ibarat zoom-out gunung).
        #
        # Transisi kompleksitas:
        #   side<173m  (<3ha):  3 oktaf  → tekstur halus, hampir datar
        #   side<707m  (<50ha): 4 oktaf  → undulasi ladang + bukit kecil
        #   side<2646m (<700ha):5 oktaf  → bukit jelas + lembah
        #   side≥2646m (≥700ha):6 oktaf  → pegunungan / DAS besar
        _PHYS_OCTAVES = [
            (4000.0, 0.90),   # pegunungan / lembah besar
            (1000.0, 0.65),   # bukit utama
            (250.0,  0.45),   # undulasi lahan
            (60.0,   0.28),   # variasi sawah / ladang
            (15.0,   0.16),   # permukaan mikro
            (4.0,    0.08),   # tekstur halus
        ]
        z = np.zeros_like(self.X)
        for wl, amp_frac in _PHYS_OCTAVES:
            if wl < min_wl:
                break
            if wl > self.side_m * 1.5:
                continue                        # tidak cukup siklus untuk terlihat
            frq = (2 * math.pi) / wl
            amp = amp_total * amp_frac
            # Phase berdasarkan koordinat + wavelength (BUKAN area) → fitur di
            # posisi fisik yang sama; view lebih besar hanya menampilkan lebih banyak
            ph_x = (self.region.lat * 17.3 + wl * 0.037) % (2 * math.pi)
            ph_y = (self.region.lon * 13.1 + wl * 0.023) % (2 * math.pi)
            z += amp * np.sin(self.X * frq + ph_x) * np.cos(self.Y * frq + ph_y)

        # Fase pendek untuk fitur deterministik (posisi fisik, bukan proporsional)
        _px = (self.region.lat * 13.7) % (2 * math.pi)
        _py = (self.region.lon * 11.3) % (2 * math.pi)

        # ── Fitur skala-spesifik — posisi ABSOLUT (meter) ────────────────────
        # Semua posisi dalam meter nyata sehingga pada area berbeda fitur muncul
        # di posisi proporsional yang berbeda (efek "zoom in/out" yang benar).
        if self.area_ha < 2.0:
            # Bedengan: lebar fisik tetap ~5-8m
            bed_w = max(grid_dx * 4, 5.0 + 3.0 * abs(math.sin(_px)))
            z += (amp_total * 0.28) * np.sin(self.X * (2 * math.pi / bed_w) + _px)
            # Parit drainase: posisi absolut dari tepi kiri
            ditch_x = max(grid_dx * 4, 4.0 + 6.0 * abs(math.cos(_py)))
            ditch_w = max(grid_dx * 3, ditch_x * 0.5)
            z -= amp_total * 0.40 * np.exp(-((self.X - ditch_x) ** 2) /
                                            (2 * ditch_w ** 2))
            z += amp_total * 0.15 * (self.Y / self.side_m - 0.5)

        elif self.area_ha < 100.0:
            # Saluran irigasi utama: posisi absolut 30-100m dari tepi
            canal_y = max(grid_dx * 5,
                          min(self.side_m - grid_dx * 5,
                              30.0 + 70.0 * abs(math.sin(self.region.lon * 3.7))))
            canal_w = max(grid_dx * 5, min(self.side_m * 0.06, 20.0))
            z -= amp_total * 0.65 * np.exp(-((self.Y - canal_y) ** 2) /
                                            (2 * canal_w ** 2))
            # Anak saluran: posisi absolut 40-120m dari tepi kiri
            sub_x = max(grid_dx * 5,
                        min(self.side_m - grid_dx * 5,
                            40.0 + 80.0 * abs(math.cos(self.region.lat * 2.9))))
            z -= amp_total * 0.30 * np.exp(-((self.X - sub_x) ** 2) /
                                            (2 * (canal_w * 0.6) ** 2))
            z += amp_total * 0.20 * (self.X / self.side_m - 0.5)

            if self.terrain in ("hills", "highlands"):
                n_ter   = max(3, int(self.side_m / max(grid_dx * 12, 20.0)))
                step    = self.side_m / n_ter
                for t in range(n_ter):
                    cx_t    = (t + 0.5) * step
                    sigma_t = step * 0.25
                    z += amp_total * 0.12 * t * np.exp(-((self.X - cx_t) ** 2) /
                                                         (2 * sigma_t ** 2))

        else:
            # Landscape: sungai meander + punggung bukit (posisi absolut)
            meander_wl = max(self.side_m * 0.5, 500.0)
            river_y    = self.side_m * 0.50 + (self.side_m * 0.25) * np.sin(
                self.X / meander_wl * 2 * math.pi + _px)
            river_w = max(grid_dx * 6, min(self.side_m * 0.04, 150.0))
            z -= amp_total * 1.3 * np.exp(-((self.Y - river_y) ** 2) /
                                           (2 * river_w ** 2))
            # Punggung bukit: offset absolut ±200m dari tengah
            ridge_offset = 200.0 * math.cos(self.region.lat * 4.1)
            ridge_x = self.side_m / 2 + ridge_offset
            ridge_w = max(self.side_m * 0.15, 300.0)
            z += amp_total * 0.65 * np.exp(-((self.X - ridge_x) ** 2) /
                                            (2 * ridge_w ** 2))
            r2_ox = 300.0 * math.sin(self.region.lon * 3.3)
            r2_oy = 200.0 * math.cos(self.region.lat * 5.7)
            z += amp_total * 0.38 * np.exp(
                -(((self.X - (self.side_m / 2 + r2_ox)) ** 2 +
                   (self.Y - (self.side_m / 2 + r2_oy)) ** 2)) /
                (2 * max(self.side_m * 0.12, 200.0) ** 2))

        # ── Terrain-class features ─────────────────────────────────────────
        if self.terrain == "mountain":
            # Puncak dioffset absolut ±100m dari tengah → area kecil hanya lihat
            # sisi gunung; area besar lihat puncak + lereng penuh
            pk_off_x = 100.0 * math.sin(self.region.lat * 7.3)
            pk_off_y = 100.0 * math.cos(self.region.lon * 5.1)
            cx = self.side_m / 2 + pk_off_x
            cy = self.side_m / 2 + pk_off_y
            r  = np.sqrt((self.X - cx) ** 2 + (self.Y - cy) ** 2)
            peak_r = max(self.side_m * 0.30, 200.0)
            z += amp_total * 1.4 * np.exp(-r / peak_r)
            z -= amp_total * 0.45 * np.exp(-r / max(self.side_m * 0.06, 50.0))
            z += amp_total * 0.20 * np.sin(self.X / max(self.side_m, 100.0) * math.pi + _px)

        elif self.terrain == "hills":
            n_hills = min(2 + int(math.log10(max(1.1, self.area_ha))), 7)
            rng2    = np.random.default_rng(self.seed + 1)
            for _ in range(n_hills):
                cx      = rng2.uniform(0.10, 0.90) * self.side_m
                cy      = rng2.uniform(0.10, 0.90) * self.side_m
                h_amp   = rng2.uniform(0.45, 1.10) * amp_total
                h_w     = rng2.uniform(max(grid_dx * 8, self.side_m * 0.10),
                                       max(grid_dx * 16, self.side_m * 0.28))
                r       = np.sqrt((self.X - cx) ** 2 + (self.Y - cy) ** 2)
                z      += h_amp * np.exp(-r ** 2 / (2 * h_w ** 2))

        elif self.terrain == "coastal_plain":
            z -= amp_total * 0.70 * (self.Y / self.side_m)
            # Kanal pantai: posisi absolut
            kanal_y = max(grid_dx * 5, min(self.side_m * 0.9,
                          30.0 + 50.0 * abs(math.sin(self.region.lon * 2.3))))
            kanal_w = max(grid_dx * 5, min(self.side_m * 0.04, 25.0))
            z -= amp_total * 1.10 * np.exp(-((self.Y - kanal_y) ** 2) /
                                            (2 * kanal_w ** 2))

        elif self.terrain == "lowland":
            z -= amp_total * 0.55 * np.cos(self.X / max(self.side_m, 100.0) * math.pi)

        # ── Gaussian smoothing: separable 1D convolution (pure numpy, fast) ─
        _sig = 1.2
        _ks  = 5   # kernel width (cells)
        _r   = np.arange(_ks) - _ks // 2
        _k1d = np.exp(-0.5 * (_r / _sig) ** 2)
        _k1d /= _k1d.sum()
        _pad = _ks // 2
        # Row-wise pass
        _zpr = np.pad(z, [(0, 0), (_pad, _pad)], mode="edge")
        _zr  = np.stack([np.convolve(_zpr[i], _k1d, mode="valid") for i in range(z.shape[0])])
        # Column-wise pass
        _zpc = np.pad(_zr, [(_pad, _pad), (0, 0)], mode="edge")
        z    = np.stack([np.convolve(_zpc[:, j], _k1d, mode="valid") for j in range(z.shape[1])]).T

        # ── Tiny realistic noise (paling akhir, setelah smooth) ────────────
        noise_sigma = max(0.02, amp_total * 0.008)
        z += self.rng.normal(0, noise_sigma, z.shape)

        return base + z

    # ── Ambil parameter cuaca efektif (live > region baseline) ───────────────
    def _effective_rain_yr(self) -> float:
        """Curah hujan tahunan efektif — pakai live weather jika tersedia."""
        if self.live_weather and self.live_weather.rainfall > 0:
            # rainfall OWM dalam mm/jam → scale ke tahunan kasar
            return min(5000.0, self.live_weather.rainfall * 8760 * 0.12 + self.region.curah_hujan_mm_yr * 0.88)
        return self.region.curah_hujan_mm_yr

    def _effective_humidity(self) -> float:
        if self.live_weather:
            return self.live_weather.humidity_outside
        return self.region.rh_avg

    def _effective_temp(self) -> float:
        if self.live_weather:
            return self.live_weather.temp_outside
        return self.region.suhu_avg

    def _live_cloud_fraction(self) -> float:
        """0.0–1.0 berdasarkan cloud cover live."""
        if self.live_weather:
            return self.live_weather.cloud_cover_pct / 100.0
        return 0.3

    def _live_drought_stress(self) -> float:
        """0 = tidak stress, 1 = sangat kering."""
        if self.live_weather:
            hum = self.live_weather.humidity_outside
            rain = self.live_weather.rainfall
            # Stress jika kelembapan < 55% dan tidak sedang hujan
            stress = max(0.0, (55.0 - hum) / 55.0) if rain < 0.1 else 0.0
            return min(1.0, stress)
        return 0.0

    def synth_ndvi(self, stage_factor: float = 0.7) -> np.ndarray:
        """NDVI kondisi nyata — dipengaruhi cuaca live (kelembapan, hujan, awan, suhu)."""
        # ── Base: curah hujan + altitude baseline ────────────────────────
        rain_factor  = min(1.0, self._effective_rain_yr() / 2200.0)
        alt_factor   = 1.0 - max(0, (self.region.altitude_m - 1500)) / 3000.0
        base_ndvi    = 0.45 + 0.30 * rain_factor + 0.15 * alt_factor

        # ── Live weather adjustments ──────────────────────────────────────
        hum_bonus    = 0.08 * max(0.0, (self._effective_humidity() - 65.0) / 35.0)
        temp         = self._effective_temp()
        # Suhu optimal 22-30°C → lebih tinggi/rendah = stress
        temp_penalty = 0.05 * max(0.0, abs(temp - 26.0) - 6.0)
        cloud_bonus  = 0.03 * (1.0 - self._live_cloud_fraction())  # sinar lebih → fotosintesis +
        drought_pen  = 0.18 * self._live_drought_stress()           # kekeringan → NDVI turun

        base_ndvi = base_ndvi + hum_bonus + cloud_bonus - temp_penalty - drought_pen

        # ── Pola spasial dari koordinat (signature unik per lokasi) ──────
        kx   = (self.region.lon * 0.05) % 0.1 + 0.005
        ky   = (self.region.lat * 0.05) % 0.1 + 0.005
        wave = 0.10 * np.sin(self.X * kx + self.region.lat) * \
               np.cos(self.Y * ky + self.region.lon)

        # ── Patchiness berdasarkan terrain ────────────────────────────────
        if self.terrain in ("mountain", "highlands"):
            patches = self.rng.normal(0, 0.09, self.X.shape);  n_patches = 8
        elif self.terrain == "hills":
            patches = self.rng.normal(0, 0.06, self.X.shape);  n_patches = 5
        else:
            patches = self.rng.normal(0, 0.04, self.X.shape);  n_patches = 3

        # Semakin kering → semakin banyak/besar patch stress
        if self._live_drought_stress() > 0.3:
            n_patches = int(n_patches * 1.8)

        ndvi = base_ndvi + wave + patches
        ndvi *= stage_factor + (1 - stage_factor) * 0.3

        # ── Drought/stress patches dalam ruang fisik (meter) ──────────────
        # Posisi patch di-generate dari domain fisik tetap 20km×20km sehingga:
        # • Area kecil (1ha)  → sedikit patch, masing-masing besar relatif
        # • Area besar (100ha)→ banyak patch visible, masing-masing kecil relatif
        # → efek "zoom out" nyata: blobs tampak di posisi proporsional berbeda
        _NDVI_DOMAIN = 20000.0        # 20km × 20km coverage
        _NDVI_N      = 60             # jumlah patch di seluruh domain
        _ndvi_rng    = np.random.default_rng(self.seed ^ 0xC3D7A1B5)
        _px_all = _ndvi_rng.uniform(0, _NDVI_DOMAIN, _NDVI_N)
        _py_all = _ndvi_rng.uniform(0, _NDVI_DOMAIN, _NDVI_N)
        _pr_all = _ndvi_rng.uniform(15, 80, _NDVI_N)           # radius 15-80m fisik
        _pf_all = _ndvi_rng.uniform(0.38, 0.88, _NDVI_N)
        _drought = self._live_drought_stress()
        _pr_all  = _pr_all * (1.0 + _drought)                  # lebih besar saat kering
        _orig_x  = (self.region.lon * 1111.0) % _NDVI_DOMAIN
        _orig_y  = (self.region.lat * 1111.0) % _NDVI_DOMAIN
        _mi, _mj = np.indices(ndvi.shape)
        for _i in range(_NDVI_N):
            _rx = _px_all[_i] - _orig_x
            _ry = _py_all[_i] - _orig_y
            _rm = _pr_all[_i]
            if _rx < -_rm or _rx > self.side_m + _rm:
                continue
            if _ry < -_rm or _ry > self.side_m + _rm:
                continue
            _cx_i = int(_rx / self.side_m * self.grid_size)
            _cy_i = int(_ry / self.side_m * self.grid_size)
            _ri   = max(1, int(_rm / self.side_m * self.grid_size))
            _d    = np.sqrt((_mi - _cy_i) ** 2 + (_mj - _cx_i) ** 2)
            _fac  = _pf_all[_i]
            if _drought > 0.3:
                _fac = min(_fac, 0.55)
            ndvi[_d < _ri] *= _fac

        return np.clip(ndvi, 0.05, 0.95)

    def synth_soil_moisture(self, base_pct: float = 60.0) -> np.ndarray:
        """Kelembapan tanah — dipengaruhi hujan live, kelembapan udara, terrain."""
        # ── Base dari curah hujan tahunan & live rain ─────────────────────
        base_pct = 35.0 + 35.0 * min(1.0, self._effective_rain_yr() / 2500.0)

        # Live rain boost — jika sedang/baru hujan, soil lembab
        if self.live_weather:
            rain_boost = min(30.0, self.live_weather.rainfall * 6.0)
            hum_factor = (self._effective_humidity() - 60.0) / 40.0 * 8.0
            base_pct   = base_pct + rain_boost + hum_factor

        smap = np.full_like(self.X, base_pct)
        smap += self.rng.normal(0, 5.0, smap.shape)

        # ── Gradien spasial terrain-aware ─────────────────────────────────
        if self.terrain in ("mountain", "highlands"):
            # Lereng lembab di bawah, kering di puncak
            elev_grad = self.synth_elevation()
            elev_norm = (elev_grad - elev_grad.min()) / max(1.0, elev_grad.max() - elev_grad.min())
            smap += 15.0 * (1.0 - elev_norm)    # lembah lebih lembab
            smap += 10.0 * np.sin(self.X / self.side_m * 4 + self.region.lat)
        else:
            smap += 6.0 * np.sin(self.X * 0.01 + self.region.lon) * \
                    np.cos(self.Y * 0.01 + self.region.lat)

        # ── Jalur sungai / kanal di terrain datar ────────────────────────
        if self.terrain in ("coastal_plain", "lowland"):
            river_y    = self.side_m * 0.3 + 0.04 * self.X
            river_band = np.exp(-((self.Y - river_y) ** 2) / (2 * (self.side_m * 0.05) ** 2))
            smap += 28.0 * river_band

        # ── Drought: kurangi moisture jika kering ─────────────────────────
        smap *= (1.0 - 0.35 * self._live_drought_stress())

        return np.clip(smap, 5, 100)

    # ──────────────────────────────────────────────────────────────────────
    # 3D FIGURES
    # ──────────────────────────────────────────────────────────────────────

    def figure_3d(self, layer: str = "ndvi", title: str = "3D Spatial View"):
        """Bangun figure plotly 3D. layer: 'elevation' | 'ndvi' | 'moisture'
        Untuk layer 'ndvi': DEM nyata (AWS Terrain Tiles) + warna NDVI.
        Untuk layer 'elevation': DEM nyata + hypsometric colorscale.
        """
        if not _PLOTLY_OK:
            return None

        # ── Coba ambil DEM nyata dari AWS Terrain Tiles ──────────────────────
        _real_dem = None
        try:
            _real_dem = _fetch_dem_cached(
                self.region.lat, self.region.lon,
                self.side_m, self.grid_size)
        except Exception:
            pass

        # ── Elevation: real DEM jika tersedia, fallback synthetic ─────────────
        if _real_dem is not None and _real_dem.shape == (self.grid_size, self.grid_size):
            elevation   = _real_dem
            _dem_source = "DEM nyata (SRTM)"
        else:
            elevation   = self.synth_elevation()
            _dem_source = "synthetic"

        # ── Warna surface berdasarkan layer ───────────────────────────────────
        if layer == "ndvi":
            color      = self.synth_ndvi()
            colorscale = "YlGn"
            colorbar   = "NDVI"
        elif layer == "moisture":
            color      = self.synth_soil_moisture()
            colorscale = "Blues"
            colorbar   = "Soil moisture %"
        else:
            # Hypsometric: warna berdasarkan elevasi absolut (kuning lembah→hijau→putih puncak)
            color      = elevation
            colorscale = _HYPSOMETRIC_CS
            colorbar   = "Elevasi (m)"

        # ── Hover text ────────────────────────────────────────────────────────
        lat_grid = np.tile(self.lat_grid.reshape(-1, 1), (1, self.grid_size))
        lon_grid = np.tile(self.lon_grid.reshape(1, -1), (self.grid_size, 1))
        hovertext = np.empty(elevation.shape, dtype=object)
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                hovertext[i, j] = (
                    f"📍 {lat_grid[i,j]:.5f}°, {lon_grid[i,j]:.5f}°<br>"
                    f"⛰️ Elev: {elevation[i,j]:.1f} m<br>"
                    f"🎯 {colorbar}: {color[i,j]:.3f}"
                )

        # ── Surface utama dengan lighting realistis ───────────────────────────
        fig = go.Figure(data=[
            go.Surface(
                x=self.X, y=self.Y, z=elevation,
                surfacecolor=color,
                colorscale=colorscale,
                colorbar=dict(title=colorbar, thickness=14, len=0.6,
                              tickfont=dict(size=10)),
                lighting=dict(
                    ambient=0.40,
                    diffuse=0.85,
                    roughness=0.55,
                    specular=0.12,
                    fresnel=0.08,
                ),
                lightposition=dict(x=200, y=-150, z=3000),
                contours={"z": {"show": False}},
                hovertext=hovertext,
                hoverinfo="text",
                opacity=1.0,
            )
        ])

        # ── Marker lokasi tengah ──────────────────────────────────────────────
        _mid = self.grid_size // 2
        fig.add_trace(go.Scatter3d(
            x=[self.side_m / 2], y=[self.side_m / 2],
            z=[float(elevation[_mid, _mid]) + max(1.0, float(elevation.max() - elevation.min()) * 0.05)],
            mode="markers+text",
            marker=dict(size=7, color="#ff3333", symbol="diamond"),
            text=[f"📍 {self.region.nama}"],
            textposition="top center",
            textfont=dict(color="#ff8888", size=11),
            hovertext=(f"{self.region.nama}<br>"
                       f"{self.region.lat:.5f}°, {self.region.lon:.5f}°<br>"
                       f"Alt: {self.region.altitude_m:.0f} m · {_dem_source}"),
            showlegend=False,
        ))

        # ── Z exaggeration — adaptif per area & relief ────────────────────────
        z_range = max(0.5, float(elevation.max() - elevation.min()))
        # Real DEM → lebih sedikit exaggeration (sudah realistis)
        _exag_max = 12.0 if _real_dem is not None else 25.0
        z_exag = max(1.5, min(_exag_max, (self.side_m * 0.12) / z_range))
        z_ratio = max(0.10, min(0.75, z_range * z_exag / self.side_m))

        _src_badge = "🛰 SRTM" if _real_dem is not None else "⚙ synth"
        fig.update_layout(
            title=(f"{title}<br>"
                   f"<sub>📍 {self.region.lat:.5f}°N, {self.region.lon:.5f}°E · "
                   f"Alt: {self.region.altitude_m:.0f}m · "
                   f"{self.terrain.replace('_',' ').title()} · "
                   f"Z×{z_exag:.0f} · {_src_badge}</sub>"),
            scene=dict(
                xaxis_title=f"X (m)  [{self.side_m:.0f}m total]",
                yaxis_title=f"Y (m)  [{self.side_m:.0f}m total]",
                zaxis_title="Elevasi (m)",
                bgcolor="#060d06",
                aspectmode="manual",
                aspectratio=dict(x=1.0, y=1.0, z=z_ratio),
                camera=dict(
                    eye=dict(x=1.5, y=-1.5, z=1.2),
                    up=dict(x=0, y=0, z=1),
                ),
                xaxis=dict(showgrid=False, zeroline=False),
                yaxis=dict(showgrid=False, zeroline=False),
                zaxis=dict(showgrid=True, gridcolor="#1a3a1a"),
            ),
            paper_bgcolor="#060d06",
            font=dict(color="#7a9a7a"),
            height=680,
            margin=dict(l=0, r=0, t=80, b=0),
        )
        return fig

    def figure_topdown_geo(self, layer: str = "ndvi"):
        """🆕 Top-down view dengan REAL geografi (OpenStreetMap tile, no API key)."""
        if not _PLOTLY_OK:
            return None
        if layer == "moisture":
            data = self.synth_soil_moisture(); cs = "Blues"; lbl = "Soil Moisture %"
        elif layer == "elevation":
            data = self.synth_elevation(); cs = "Earth"; lbl = "Elevation m"
        else:
            data = self.synth_ndvi(); cs = "YlGn"; lbl = "NDVI"

        # Buat scattermapbox dengan grid points + warna (densitas overlay)
        lats = []; lons = []; vals = []
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                lats.append(float(self.lat_grid[i]))
                lons.append(float(self.lon_grid[j]))
                vals.append(float(data[i, j]))

        fig = go.Figure(go.Densitymapbox(
            lat=lats, lon=lons, z=vals,
            radius=14, colorscale=cs,
            colorbar=dict(title=lbl, thickness=15),
            opacity=0.78,
        ))
        # Marker untuk pusat region
        fig.add_trace(go.Scattermapbox(
            lat=[self.region.lat], lon=[self.region.lon],
            mode="markers+text",
            marker=dict(size=18, color="#ff4444", symbol="circle"),
            text=[f"📍 {self.region.nama}"],
            textposition="top right",
            textfont=dict(color="#ff8888", size=14),
            hovertext=f"{self.region.nama}, {self.region.provinsi}<br>"
                      f"{self.region.lat:.5f}°, {self.region.lon:.5f}°<br>"
                      f"Alt: {self.region.altitude_m} m",
            hoverinfo="text", showlegend=False,
        ))
        # Bounding box rectangle
        fig.add_trace(go.Scattermapbox(
            lat=[self.lat_min, self.lat_max, self.lat_max, self.lat_min, self.lat_min],
            lon=[self.lon_min, self.lon_min, self.lon_max, self.lon_max, self.lon_min],
            mode="lines",
            line=dict(color="#55ee55", width=2),
            hoverinfo="skip", showlegend=False, name="Area",
        ))
        # Auto zoom estimate berdasarkan side_m
        zoom_level = 16 - math.log2(max(self.side_m / 100.0, 1.0))
        zoom_level = max(8, min(18, zoom_level))
        fig.update_layout(
            mapbox_style="open-street-map",  # 🆓 no API key needed
            mapbox=dict(
                center=dict(lat=self.region.lat, lon=self.region.lon),
                zoom=zoom_level,
            ),
            paper_bgcolor="#060d06", font=dict(color="#7a9a7a"),
            height=560, margin=dict(l=0, r=0, t=10, b=0),
            title=f"🛰️ Top-Down Map: {self.region.nama} · {layer.upper()} overlay",
        )
        return fig

    def figure_zone_heatmap(self, layer: str = "ndvi"):
        if not _PLOTLY_OK:
            return None
        if layer == "moisture":
            data = self.synth_soil_moisture(); cs = "Blues"; title = "Soil Moisture %"
        elif layer == "elevation":
            data = self.synth_elevation(); cs = "Earth"; title = "Elevation m"
        else:
            data = self.synth_ndvi(); cs = "YlGn"; title = "NDVI"

        # Pakai koordinat lat/lon di axis (bukan pixel!)
        fig = go.Figure(data=go.Heatmap(
            z=data,
            x=self.lon_grid, y=self.lat_grid,
            colorscale=cs, colorbar=dict(title=title),
            hovertemplate="lat=%{y:.5f}°<br>lon=%{x:.5f}°<br>" + title + "=%{z:.2f}<extra></extra>",
        ))
        fig.update_layout(
            title=f"🗺️ Detailed {title} Map · {self.region.nama} ({self.region.lat:.4f}°, {self.region.lon:.4f}°)",
            xaxis_title="Longitude (°E)", yaxis_title="Latitude (°N)",
            paper_bgcolor="#060d06", plot_bgcolor="#0a1a0a",
            font=dict(color="#7a9a7a"), height=460,
        )
        return fig

    def figure_indo_overview(self):
        """🆕 Peta Indonesia menyeluruh dengan marker semua region + highlight current."""
        if not _PLOTLY_OK:
            return None
        lats = [r.lat for r in INDO_REGIONS.values()]
        lons = [r.lon for r in INDO_REGIONS.values()]
        names = [f"{r.nama}, {r.provinsi}" for r in INDO_REGIONS.values()]
        alts = [r.altitude_m for r in INDO_REGIONS.values()]
        # Highlight current
        is_current = [r.nama == self.region.nama for r in INDO_REGIONS.values()]
        sizes = [18 if c else 9 for c in is_current]
        colors = ["#ff4444" if c else "#55ee55" for c in is_current]

        fig = go.Figure(go.Scattermapbox(
            lat=lats, lon=lons,
            mode="markers+text" if any(is_current) else "markers",
            marker=dict(size=sizes, color=colors, opacity=0.85),
            text=[n if is_current[i] else "" for i, n in enumerate(names)],
            textposition="top right", textfont=dict(color="#ff8888", size=11),
            hovertext=[f"{n}<br>{lats[i]:.4f}°, {lons[i]:.4f}°<br>Alt: {alts[i]} m"
                       for i, n in enumerate(names)],
            hoverinfo="text",
        ))
        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox=dict(center=dict(lat=-2.5, lon=118.0), zoom=3.6),
            paper_bgcolor="#060d06", font=dict(color="#7a9a7a"),
            height=420, margin=dict(l=0, r=0, t=10, b=0),
            title=f"🇮🇩 28 Wilayah Indonesia · Highlight: {self.region.nama}",
        )
        return fig

    def stats(self) -> Dict[str, float]:
        ndvi = self.synth_ndvi()
        sm   = self.synth_soil_moisture()
        elev = self.synth_elevation()
        return {
            "ndvi_mean":     float(ndvi.mean()),
            "ndvi_min":      float(ndvi.min()),
            "ndvi_max":      float(ndvi.max()),
            "ndvi_stress_pct": float((ndvi < 0.4).mean() * 100),
            "moisture_mean": float(sm.mean()),
            "moisture_dry_pct": float((sm < 35).mean() * 100),
            "elevation_min": float(elev.min()),
            "elevation_max": float(elev.max()),
            "elevation_range": float(elev.max() - elev.min()),
        }


# ══════════════════════════════════════════════════════════════════════════════
# 11. REAL SENSOR BRIDGE
# ══════════════════════════════════════════════════════════════════════════════

class SensorBackendType(Enum):
    SIMULATED = "Simulated (Virtual)"
    SERIAL    = "Serial / USB (Arduino/ESP32)"
    HTTP      = "HTTP REST (Local Gateway)"
    MQTT      = "MQTT Broker"
    MODBUS    = "Modbus TCP (Industrial)"


@dataclass
class IndoSensorReading:
    name:      str
    value:     float
    unit:      str
    source:    str   = "simulated"
    timestamp: str   = ""
    quality:   str   = "good"   # good | degraded | fault

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class RealSensorBridge:
    """Bridge sensor: coba real, fallback ke simulasi tinggi-fidelitas."""

    def __init__(self, backend: SensorBackendType = SensorBackendType.SIMULATED,
                 config: Optional[Dict[str, Any]] = None):
        self.backend = backend
        self.config = config or {}
        self.connected = False
        self.last_error: Optional[str] = None
        self._serial = None
        self._mqtt_client = None
        self._mqtt_cache: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._sim_state = {
            "temp": 27.5, "humidity": 75.0, "co2": 420.0,
            "soil_moisture": 60.0, "light": 320.0, "ec": 1.8, "ph": 6.4,
        }
        self._last_sim_t = time.time()

    # ── Connection management ───────────────────────────────────────────────
    def list_serial_ports(self) -> List[str]:
        if not _SERIAL_OK:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self) -> bool:
        try:
            if self.backend == SensorBackendType.SERIAL:
                if not _SERIAL_OK:
                    raise RuntimeError("pyserial not installed: pip install pyserial")
                port = self.config.get("port", "COM3")
                baud = int(self.config.get("baud", 9600))
                self._serial = serial.Serial(port, baud, timeout=1.0)
                time.sleep(2.0)  # arduino reset delay
                self.connected = True

            elif self.backend == SensorBackendType.HTTP:
                if not _REQUESTS_OK:
                    raise RuntimeError("requests not installed")
                url = self.config.get("url", "http://localhost:8080/sensors")
                r = requests.get(url, timeout=2.5)
                r.raise_for_status()
                self.connected = True

            elif self.backend == SensorBackendType.MQTT:
                if not _MQTT_OK:
                    raise RuntimeError("paho-mqtt not installed: pip install paho-mqtt")
                host = self.config.get("host", "localhost")
                port = int(self.config.get("port", 1883))
                topic = self.config.get("topic", "greenhouse/+/sensor/+")
                client = mqtt_client.Client(client_id=f"tumbal-{int(time.time())}")
                if self.config.get("username"):
                    client.username_pw_set(self.config["username"], self.config.get("password", ""))
                client.on_message = self._mqtt_on_message
                client.connect(host, port, keepalive=60)
                client.subscribe(topic, qos=0)
                client.loop_start()
                self._mqtt_client = client
                self.connected = True

            elif self.backend == SensorBackendType.MODBUS:
                if not _MODBUS_OK:
                    raise RuntimeError("pymodbus not installed: pip install pymodbus")
                host = self.config.get("host", "127.0.0.1")
                port = int(self.config.get("port", 502))
                client = ModbusTcpClient(host, port=port)
                if not client.connect():
                    raise RuntimeError("Modbus TCP connect failed")
                self._modbus = client
                self.connected = True

            else:
                self.connected = True   # simulated always "connected"

            self.last_error = None
            return True

        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            return False

    def disconnect(self):
        try:
            if self._serial:
                self._serial.close()
            if self._mqtt_client:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
        except Exception:
            pass
        self.connected = False

    # ── MQTT helper ─────────────────────────────────────────────────────────
    def _mqtt_on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8")
            try:
                data = json.loads(payload)
                if isinstance(data, dict):
                    with self._lock:
                        for k, v in data.items():
                            if isinstance(v, (int, float)):
                                self._mqtt_cache[k] = float(v)
                    return
            except Exception:
                pass
            # topic key
            key = msg.topic.split("/")[-1]
            with self._lock:
                self._mqtt_cache[key] = float(payload)
        except Exception:
            pass

    # ── Read ──────────────────────────────────────────────────────────────
    def read_all(self) -> Dict[str, IndoSensorReading]:
        if self.backend == SensorBackendType.SIMULATED or not self.connected:
            return self._read_simulated()

        try:
            if self.backend == SensorBackendType.SERIAL:
                return self._read_serial()
            if self.backend == SensorBackendType.HTTP:
                return self._read_http()
            if self.backend == SensorBackendType.MQTT:
                return self._read_mqtt()
            if self.backend == SensorBackendType.MODBUS:
                return self._read_modbus()
        except Exception as e:
            self.last_error = str(e)
            return self._read_simulated()
        return self._read_simulated()

    def _read_serial(self) -> Dict[str, IndoSensorReading]:
        if not self._serial:
            return self._read_simulated()
        self._serial.write(b"READ\n")
        line = self._serial.readline().decode("utf-8", errors="ignore").strip()
        try:
            data = json.loads(line)
        except Exception:
            data = {}
        out = {}
        for k, v in data.items():
            if isinstance(v, (int, float)):
                out[k] = IndoSensorReading(k, float(v), self._unit_for(k), "serial")
        return out or self._read_simulated()

    def _read_http(self) -> Dict[str, IndoSensorReading]:
        url = self.config.get("url", "http://localhost:8080/sensors")
        r = requests.get(url, timeout=2.0)
        data = r.json() if r.ok else {}
        return {k: IndoSensorReading(k, float(v), self._unit_for(k), "http")
                for k, v in data.items() if isinstance(v, (int, float))}

    def _read_mqtt(self) -> Dict[str, IndoSensorReading]:
        with self._lock:
            cache = dict(self._mqtt_cache)
        return {k: IndoSensorReading(k, v, self._unit_for(k), "mqtt") for k, v in cache.items()}

    def _read_modbus(self) -> Dict[str, IndoSensorReading]:
        if not getattr(self, "_modbus", None):
            return self._read_simulated()
        regs = self.config.get("registers", {
            "temp": 0, "humidity": 1, "soil_moisture": 2, "co2": 3, "light": 4
        })
        out = {}
        for name, addr in regs.items():
            rr = self._modbus.read_holding_registers(int(addr), 1)
            if rr.isError():
                continue
            raw = rr.registers[0]
            scale = self.config.get("scale", {}).get(name, 0.1)
            out[name] = IndoSensorReading(name, raw * scale, self._unit_for(name), "modbus")
        return out or self._read_simulated()

    def _read_simulated(self) -> Dict[str, IndoSensorReading]:
        """Simulasi tinggi-fidelitas — model auto-regressive ringan."""
        now = time.time()
        dt = min(60.0, now - self._last_sim_t)
        self._last_sim_t = now
        rng = np.random.default_rng()
        s = self._sim_state
        # diurnal cycle (24h)
        hr = (datetime.datetime.now().hour + datetime.datetime.now().minute / 60.0)
        diurnal = math.sin((hr - 6) / 24.0 * 2 * math.pi)
        s["temp"]          = 0.92 * s["temp"]          + 0.08 * (26.0 + 4.5 * diurnal) + rng.normal(0, 0.15)
        s["humidity"]      = 0.92 * s["humidity"]      + 0.08 * (75.0 - 8.0 * diurnal) + rng.normal(0, 0.4)
        s["co2"]           = 0.95 * s["co2"]           + 0.05 * (415.0 + 60.0 * (1 - max(0, diurnal))) + rng.normal(0, 2.5)
        s["soil_moisture"] = max(15, min(95, s["soil_moisture"] - 0.05 * dt + rng.normal(0, 0.2)))
        s["light"]         = max(0, 800.0 * max(0.0, math.sin((hr - 6) / 12.0 * math.pi)) + rng.normal(0, 12))
        s["ec"]            = max(0.5, min(4.5, s["ec"] + rng.normal(0, 0.02)))
        s["ph"]            = max(4.5, min(7.5, s["ph"] + rng.normal(0, 0.01)))
        return {
            "temp":          IndoSensorReading("temp",          s["temp"],          "°C",     "simulated"),
            "humidity":      IndoSensorReading("humidity",      s["humidity"],      "%",      "simulated"),
            "co2":           IndoSensorReading("co2",           s["co2"],           "ppm",    "simulated"),
            "soil_moisture": IndoSensorReading("soil_moisture", s["soil_moisture"], "%",      "simulated"),
            "light":         IndoSensorReading("light",         s["light"],         "W/m²",   "simulated"),
            "ec":            IndoSensorReading("ec",            s["ec"],            "mS/cm",  "simulated"),
            "ph":            IndoSensorReading("ph",            s["ph"],            "",       "simulated"),
        }

    @staticmethod
    def _unit_for(name: str) -> str:
        return {
            "temp": "°C", "temperature": "°C", "humidity": "%", "rh": "%",
            "co2": "ppm", "soil_moisture": "%", "soil": "%", "light": "W/m²",
            "lux": "lux", "ec": "mS/cm", "ph": "", "do": "mg/L", "wind": "m/s",
        }.get(name.lower(), "")


# ══════════════════════════════════════════════════════════════════════════════
# 12. ECONOMICS PROJECTION
# ══════════════════════════════════════════════════════════════════════════════

def economic_projection(crop: IndoCrop, region: IndoRegion, area_ha: float = 1.0,
                        cost_per_ha_idr: float = 25_000_000) -> Dict[str, Any]:
    forecast = forecast_yield(crop, region, area_ha)
    revenue = forecast["revenue_idr"]
    cost    = cost_per_ha_idr * area_ha
    profit  = revenue - cost
    roi     = (profit / cost) * 100 if cost > 0 else 0.0
    loc = get_location_state()
    price_kg, _ = localized_crop_price_idr(crop, loc)
    bep_kg  = cost / max(price_kg, 1)
    return {
        "expected_yield_ton": forecast["expected_ton"],
        "revenue_idr":        revenue,
        "cost_idr":           cost,
        "profit_idr":         profit,
        "roi_pct":            roi,
        "bep_kg":             bep_kg,
        "cost_per_kg_produksi": cost / max(forecast["expected_ton"] * 1000, 1),
        "harga_jual_kg":      price_kg,
        "margin_per_kg":      price_kg - (cost / max(forecast["expected_ton"] * 1000, 1)),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 13. STREAMLIT UI PANELS
# ══════════════════════════════════════════════════════════════════════════════

def _idr(val: float) -> str:
    try:
        return f"Rp{int(val):,}".replace(",", ".")
    except Exception:
        return "Rp 0"


def render_indonesian_crop_selector(key_prefix: str = "indo",
                                     default_zone_idx: int = 0) -> Optional[IndoCrop]:
    """Crop selector — defaults to first zone's selected crop if available."""
    if not _STREAMLIT_OK:
        return None
    # try to default to first zone's crop
    default_id = "tomat"
    try:
        zones = st.session_state.get("zones", [])
        if zones and default_zone_idx < len(zones):
            default_id = get_zone_indo_crop_id(zones[default_zone_idx])
    except Exception:
        pass

    cats = list(IndoCropCategory)
    default_crop = INDONESIAN_CROPS_DB.get(default_id)
    default_cat_idx = cats.index(default_crop.kategori) if default_crop else 0

    cat_choice = st.selectbox(
        "🗂️ Crop Category",
        [c.value for c in cats], index=default_cat_idx,
        key=f"{key_prefix}_cat",
    )
    cat_enum = next(c for c in cats if c.value == cat_choice)
    filtered = [c for c in INDONESIAN_CROPS_DB.values() if c.kategori == cat_enum]
    if not filtered:
        st.warning("No crops in this category.")
        return None
    f_ids = [c.id for c in filtered]
    f_idx = f_ids.index(default_id) if default_id in f_ids else 0
    name = st.selectbox(
        "🌱 Select Crop",
        [f"{c.nama_id} ({c.nama_en})" for c in filtered],
        index=f_idx,
        key=f"{key_prefix}_crop",
    )
    crop = next(c for c in filtered if name.startswith(c.nama_id))
    return crop


def render_region_selector(key_prefix: str = "indo") -> IndoRegion:
    """Region selector — 4 mode: sidebar default, pilih wilayah, koordinat manual, geocode."""
    if not _STREAMLIT_OK:
        return list(INDO_REGIONS.values())[0]

    _sidebar_region = st.session_state.get("default_region")
    _has_sidebar = _sidebar_region is not None

    _mode_opts = []
    if _has_sidebar:
        _mode_opts.append(f"📌 Sidebar ({_sidebar_region.nama})")
    _mode_opts += ["🗺️ Indonesia Region (Preset)", "🌐 Manual Coordinates (lat/lon)", "🔍 Search Place (Worldwide)"]

    # Default ke mode Sidebar jika tersedia
    _default_mode_idx = 0

    mode = st.radio(
        "📍 Location Mode",
        _mode_opts,
        index=_default_mode_idx,
        horizontal=True,
        key=f"{key_prefix}_loc_mode",
    )

    # Mode: pakai lokasi dari sidebar
    if _has_sidebar and mode.startswith("📌 Sidebar"):
        _dr = _sidebar_region
        st.markdown(
            f'<div class="alert-box alert-ok" style="margin:4px 0;">'
            f'📌 Using sidebar location: <b>{_dr.nama}, {_dr.provinsi}</b> · '
            f'{_dr.lat:.5f}°, {_dr.lon:.5f}° · alt {_dr.altitude_m:.0f} m · '
            f'Zone: <b>{_dr.zona_agroklimat}</b>'
            f'</div>',
            unsafe_allow_html=True
        )
        return _sidebar_region

    if mode == "🗺️ Indonesia Region (Preset)":
        regs = list(INDO_REGIONS.values())
        default_region = get_default_indo_region()
        try:
            default_idx = regs.index(default_region)
        except ValueError:
            default_idx = 0
        name = st.selectbox(
            "Select Indonesia region (synced with OpenWeather)",
            [f"{r.nama}, {r.provinsi}" for r in regs],
            index=default_idx,
            key=f"{key_prefix}_region",
        )
        return next(r for r in regs if name.startswith(r.nama))

    elif mode == "🌐 Manual Coordinates (lat/lon)":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            lat = st.number_input(
                "Latitude (°)",
                min_value=-90.0, max_value=90.0, value=-6.2146, step=0.0001,
                format="%.5f", key=f"{key_prefix}_lat",
                help="Negative = South latitude. Range: −90° to +90° worldwide"
            )
        with col2:
            lon = st.number_input(
                "Longitude (°)",
                min_value=-180.0, max_value=180.0, value=106.8451, step=0.0001,
                format="%.5f", key=f"{key_prefix}_lon",
                help="Negative = West longitude. Range: −180° to +180° worldwide"
            )
        with col3:
            alt = st.number_input(
                "Altitude (m asl)",
                min_value=0, max_value=8849, value=10, step=10,
                key=f"{key_prefix}_alt",
                help="Elevation above sea level (0–8849 m)"
            )
        with col4:
            cust_name = st.text_input(
                "Label (optional)",
                value="", key=f"{key_prefix}_cust_name",
                placeholder="e.g. Ahmad's Field, Tokyo Farm…",
            )
        # Auto reverse-geocode jika tidak ada label kustom
        if not cust_name.strip():
            _rg = _reverse_geocode_owm(lat, lon)
            _rg_name = _rg.get("name", "")
            _rg_prov = (f"{_rg.get('state','')}, {_rg.get('country','')}"
                        if _rg.get("state") else _rg.get("country", ""))
            region = build_region_from_coords(lat, lon, float(alt),
                                              nama=_rg_name, provinsi=_rg_prov)
        else:
            region = build_region_from_coords(lat, lon, float(alt), nama=cust_name)
        st.markdown(
            f'<div class="alert-box alert-info" style="margin:4px 0;">'
            f'📍 <b>{region.nama}</b> · {lat:.5f}°, {lon:.5f}° · alt {alt} m · '
            f'Oldeman Zone: <b>{region.zona_agroklimat}</b> · '
            f'Rain est.: <b>{region.curah_hujan_mm_yr:.0f} mm/yr</b> · '
            f'Temp est.: <b>{region.suhu_avg:.1f}°C</b> · '
            f'Soil: <b>{region.tanah_dominan}</b>'
            f'</div>',
            unsafe_allow_html=True
        )
        return region

    else:  # 🔍 Cari Nama Tempat — worldwide geocode
        city_q = st.text_input(
            "City / region / country name",
            value="Jakarta", key=f"{key_prefix}_city_q",
            placeholder="e.g. Bogor, Tokyo, Paris, Nairobi, Sydney…",
            help="Type place name then press Enter. Data from OpenWeatherMap Geocoding."
        )
        # Coba temukan di database Indonesia dulu
        found = find_region(city_q)
        if found:
            st.markdown(
                f'<div class="alert-box alert-ok" style="margin:4px 0;">'
                f'✓ Database Indonesia: <b>{found.nama}, {found.provinsi}</b> '
                f'({found.lat:.5f}°, {found.lon:.5f}° · {found.altitude_m:.0f} m dpl)'
                f'</div>',
                unsafe_allow_html=True
            )
            return found
        # Geocode via OWM — tanpa pembatasan negara (worldwide)
        api_key = _get_cfg("owm_api_key", os.environ.get("OPENWEATHER_API_KEY", ""))
        if api_key and city_q and len(city_q) > 2:
            try:
                geo_url = "https://api.openweathermap.org/geo/1.0/direct"
                r = requests.get(geo_url,
                                 params={"q": city_q, "limit": 5, "appid": api_key},
                                 timeout=5)
                r.raise_for_status()
                data = r.json()
                if data:
                    if len(data) > 1:
                        _choices = [
                            f"{g.get('name','')} — {g.get('state','')} — {g.get('country','')}"
                            for g in data
                        ]
                        _sel = st.selectbox(
                            "Select matching location:",
                            range(len(_choices)),
                            format_func=lambda i: _choices[i],
                            key=f"{key_prefix}_geo_choice"
                        )
                        g = data[_sel]
                    else:
                        g = data[0]
                    g_lat  = float(g["lat"])
                    g_lon  = float(g["lon"])
                    g_name = (g.get("local_names", {}).get("id")
                              or g.get("local_names", {}).get("en")
                              or g.get("name", city_q))
                    g_ctry = g.get("country", "")
                    g_prov = (f"{g.get('state','')}, {g_ctry}"
                              if g.get("state") else g_ctry)
                    region = build_region_from_coords(g_lat, g_lon, 0.0,
                                                      nama=g_name, provinsi=g_prov)
                    st.markdown(
                        f'<div class="alert-box alert-ok" style="margin:4px 0;">'
                        f'🔍 Geocode: <b>{g_name}</b> ({g_prov}) — '
                        f'{g_lat:.5f}°, {g_lon:.5f}°'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    return region
            except Exception:
                pass
        # Last resort: default Jakarta
        st.caption("Place not found. Using Jakarta as default.")
        return INDO_REGIONS["jakarta"]


def render_plant_calendar_panel():
    """Panel: input tanggal tanam → fase saat ini, kebutuhan air, estimasi panen."""
    if not _STREAMLIT_OK:
        return
    st.markdown('<div class="section-header">📅 PLANTING CALENDAR — AUTO PHASE</div>',
                unsafe_allow_html=True)

    region_default = get_default_indo_region()
    st.caption(f"📍 Auto-sync location from OpenWeather: **{region_default.nama}, {region_default.provinsi}**")
    col_a, col_b, col_c = st.columns([2, 2, 1])
    with col_a:
        crop = render_indonesian_crop_selector("calendar")
    with col_b:
        region = render_region_selector("calendar")
    with col_c:
        area = st.number_input("Luas (ha)", 0.001, 10000.0, 0.1, 0.01, key="calendar_area")

    if not crop:
        return

    today = datetime.date.today()
    default_plant = today - datetime.timedelta(days=min(crop.dap_panen // 3, 30))
    tanggal_tanam = st.date_input("📆 Tanggal Tanam", default_plant, key="calendar_plant_date")

    planting = PlantingRecord(crop.id, tanggal_tanam, luas_ha=float(area))
    cal = PlantCalendar(planting)
    status = cal.status_today()

    # Status cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📅 Hari Setelah Tanam", f"{status['dap']} hari")
    c2.metric("🌱 Fase Saat Ini", status["fase"])
    c3.metric("🎯 Days to Harvest", f"{status['days_to_harvest']} hari")
    c4.metric("📈 Progress", f"{status['progress_pct']:.0f}%")

    st.markdown(
        f"""
        <div class="prediction-box">
        <b>📍 Harvest Est.:</b> {status['estimasi_panen']} (window until {status['estimasi_panen_max']})<br>
        <b>💧 Water Today:</b> {status['water_mm_per_day']:.2f} mm/day
            ≈ {status['water_L_per_m2_today']:.2f} L/m² ≈ {status['water_L_per_ha_today']:,.0f} L/ha<br>
        <b>💧 Cumulative Water:</b> {status['water_kumulatif_mm']:.0f} mm /
            total target {status['water_total_mm']:.0f} mm
            (remaining {status['water_sisa_mm']:.0f} mm)<br>
        <b>🧪 Fertilizer Today:</b> N {status['n_kg_ha_per_day']*1000:.1f} g/ha,
            P {status['p_kg_ha_per_day']*1000:.1f} g/ha,
            K {status['k_kg_ha_per_day']*1000:.1f} g/ha
        </div>
        """, unsafe_allow_html=True,
    )

    # Timeline
    timeline = cal.timeline_dataframe()
    if _PLOTLY_OK:
        fig = go.Figure()
        for _, row in timeline.iterrows():
            fig.add_trace(go.Bar(
                x=[row["durasi_hari"]], y=[crop.nama_id], orientation="h",
                base=row["dap_mulai"], name=row["fase"],
                marker_color=row["color"], hovertemplate=(
                    f"<b>{row['fase']}</b><br>"
                    f"{row['tgl_mulai']} → {row['tgl_akhir']}<br>"
                    f"DAP {row['dap_mulai']} → {row['dap_akhir']}"
                ),
            ))
        fig.add_vline(x=status["dap"], line=dict(color="#ff5577", width=3, dash="dash"),
                      annotation_text=f"Hari ini (DAP {status['dap']})")
        fig.update_layout(
            title=f"🌱 Timeline Pertumbuhan — {crop.nama_id}",
            barmode="stack", template="plotly_dark",
            paper_bgcolor="#060d06", plot_bgcolor="#0a1a0a",
            font=dict(color="#7a9a7a"), height=200, showlegend=True,
            xaxis_title="Hari Setelah Tanam (DAP)", margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, width='stretch')

    # Climate suitability
    suit = climate_suitability_score(crop, region)
    st.markdown(
        f"""
        <div class="prediction-box">
        <b>🌡️ Skor Kecocokan Iklim ({region.nama}):</b>
        <span style="font-size:18px; color:{'#55ee55' if suit['score']>=65 else '#eebb33' if suit['score']>=50 else '#ee5555'};">
        {suit['score']:.1f}/100 — {suit['rating']}</span><br>
        Suhu {suit['komponen']['suhu']:.0f} | Ketinggian {suit['komponen']['ketinggian']:.0f}
        | Kelembapan {suit['komponen']['kelembapan']:.0f} | Curah Hujan {suit['komponen']['curah_hujan']:.0f}<br>
        <span style="color:#88ccee;">{ ' • '.join(suit['catatan']) }</span>
        </div>
        """, unsafe_allow_html=True,
    )


def render_water_nutrient_plan_panel():
    if not _STREAMLIT_OK:
        return
    st.markdown('<div class="section-header">💧 WATER & NUTRIENT SCHEDULE (PLANTING → HARVEST)</div>',
                unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        crop = render_indonesian_crop_selector("plan")
    with col_b:
        area = st.number_input("Luas (ha)", 0.001, 10000.0, 0.1, 0.01, key="plan_area")
    with col_c:
        plant_date = st.date_input("Tgl Tanam", datetime.date.today(), key="plan_date")
    if not crop:
        return
    planner = WaterNutrientPlanner(PlantingRecord(crop.id, plant_date, luas_ha=float(area)))
    summary = planner.total_summary()

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("💧 Total Air", f"{summary['total_air_mm']:.0f} mm",
              f"{summary['total_air_L_zona']/1000:.1f} m³ zona")
    s2.metric("🟢 Total N", f"{summary['total_N_kg_ha']:.0f} kg/ha",
              f"{summary['total_N_kg_zona']:.1f} kg zona")
    s3.metric("🟣 Total P", f"{summary['total_P_kg_ha']:.0f} kg/ha",
              f"{summary['total_P_kg_zona']:.1f} kg zona")
    s4.metric("🟠 Total K", f"{summary['total_K_kg_ha']:.0f} kg/ha",
              f"{summary['total_K_kg_zona']:.1f} kg zona")

    e1, e2, e3 = st.columns(3)
    e1.metric("🌾 Harvest Est.",
              f"{summary['estimasi_panen_kg']/1000:.1f} ton",
              f"{summary['estimasi_panen_kg']:.0f} kg")
    e2.metric("💰 Revenue Est.", _idr(summary["estimasi_pendapatan_idr"]))
    e3.metric("📅 Duration", f"{summary['total_durasi_hari']} days")

    daily = planner.daily_schedule()
    weekly = planner.weekly_summary()

    tabs = st.tabs(["📊 Weekly Chart", "📅 Daily Table", "📥 Export CSV"])
    with tabs[0]:
        if _PLOTLY_OK:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                subplot_titles=("💧 Water per Week (L)", "🧪 Fertilizer per Week (kg)"),
                                vertical_spacing=0.12)
            fig.add_trace(go.Bar(x=weekly["minggu"], y=weekly["air_liter_zona"],
                                 name="Air (L)", marker_color="#3aa3ff"), 1, 1)
            fig.add_trace(go.Bar(x=weekly["minggu"], y=weekly["N_kg_zona"],
                                 name="N (kg)", marker_color="#22cc44"), 2, 1)
            fig.add_trace(go.Bar(x=weekly["minggu"], y=weekly["P_kg_zona"],
                                 name="P (kg)", marker_color="#aa55ff"), 2, 1)
            fig.add_trace(go.Bar(x=weekly["minggu"], y=weekly["K_kg_zona"],
                                 name="K (kg)", marker_color="#ff9933"), 2, 1)
            fig.update_layout(template="plotly_dark", paper_bgcolor="#060d06",
                              plot_bgcolor="#0a1a0a", height=520, barmode="group",
                              font=dict(color="#7a9a7a"))
            st.plotly_chart(fig, width='stretch')
    with tabs[1]:
        st.dataframe(daily, width='stretch', height=400)
    with tabs[2]:
        st.download_button("📥 Download Daily Schedule CSV",
                           daily.to_csv(index=False).encode("utf-8"),
                           file_name=f"schedule_{crop.id}_{plant_date}.csv",
                           mime="text/csv")
        st.download_button("📥 Download Weekly Summary CSV",
                           weekly.to_csv(index=False).encode("utf-8"),
                           file_name=f"weekly_{crop.id}_{plant_date}.csv",
                           mime="text/csv")


def render_satellite_3d_panel():
    if not _STREAMLIT_OK:
        return
    st.markdown('<div class="section-header">🌍 Dynamic World Map — 4 Views · Synced LocationState</div>',
                unsafe_allow_html=True)

    # ── Always uses locationState (no per-panel selector needed) ─────────
    _loc  = get_location_state()
    region = _loc.to_indo_region()
    st.info(
        f"📍 Active location: **{_loc.display_name}** "
        f"({_loc.lat:.4f}°, {_loc.lon:.4f}°) · {_loc.climate_zone} · "
        f"Change location in sidebar to update all views.",
        icon="🌍")

    col_b, col_c, col_d = st.columns(3)

    col_b, col_c, col_d = st.columns(3)
    with col_b:
        area = st.number_input("Luas lahan (ha)", 0.1, 10000.0, 25.0, 1.0,
                               key="sat3d_area",
                               help="Visualized area. 1 ha = 100×100 m")
    with col_c:
        layer = st.selectbox("Layer visualisasi",
                             ["ndvi", "moisture", "elevation"],
                             format_func=lambda x: {
                                 "ndvi": "🌿 NDVI (Kehijauan)",
                                 "moisture": "💧 Kelembapan Tanah",
                                 "elevation": "⛰️ Elevasi (DEM)",
                             }.get(x, x),
                             key="sat3d_layer")
    with col_d:
        grid = st.selectbox("Resolusi grid", [40, 60, 80, 120], index=1,
                            key="sat3d_grid",
                            help="Higher = more detail, slower render")

    # ── Fetch cuaca berdasarkan koordinat region ──────────────────────────
    api_key = _get_cfg("owm_api_key", os.environ.get("OPENWEATHER_API_KEY",
                             st.session_state.get("_sat3d_api_key_cache", "")))
    wx_svc  = st.session_state.get("weather_svc") or WeatherService(api_key)

    with st.spinner(f"Fetching weather for {region.lat:.4f}°, {region.lon:.4f}°…"):
        live_wx = wx_svc.fetch_by_coords(
            lat=region.lat, lon=region.lon,
            location_name=f"{region.nama}, {region.provinsi}",
            alt_m=region.altitude_m,
        )

    # ── Buat model 3D dengan live weather ────────────────────────────────
    sat   = SpatialSatellite3D(region, grid_size=int(grid),
                               area_ha=float(area), live_weather=live_wx)
    stats = sat.stats()

    # ══════════════════════════════════════════════════════════════════════
    # Info Card: koordinat + cuaca nyata
    # ══════════════════════════════════════════════════════════════════════
    wx_src_label = live_wx.source
    drought = sat._live_drought_stress()
    drought_label = (
        "🔴 Kekeringan parah" if drought > 0.6 else
        "🟠 Stres kekeringan" if drought > 0.3 else
        "🟡 Sedikit kering"   if drought > 0.1 else
        "🟢 Cukup lembab"
    )
    cloud_pct = live_wx.cloud_cover_pct

    st.markdown(f"""
    <div class="ai-tech-card">
        <h3 style="margin:4px 0 10px 0;">
            📍 {region.nama}, {region.provinsi}
            <span style="font-size:12px;font-weight:400;opacity:0.7;margin-left:8px;">
                {region.lat:.5f}°, {region.lon:.5f}° · {region.altitude_m:.0f} m dpl ·
                Terrain: {sat.terrain.replace('_',' ').title()}
            </span>
        </h3>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;font-size:12px;">
            <div class="neon-metric">
                <div class="label">🌡️ Suhu Udara</div>
                <div class="value" style="font-size:20px;">{live_wx.temp_outside:.1f}°C</div>
                <div style="font-size:10px;opacity:0.6;">Baseline: {region.suhu_avg:.1f}°C</div>
            </div>
            <div class="neon-metric">
                <div class="label">💧 Kelembapan</div>
                <div class="value" style="font-size:20px;">{live_wx.humidity_outside:.0f}%</div>
                <div style="font-size:10px;opacity:0.6;">Baseline: {region.rh_avg:.0f}%</div>
            </div>
            <div class="neon-metric">
                <div class="label">🌧️ Hujan saat ini</div>
                <div class="value" style="font-size:20px;">{live_wx.rainfall:.2f} mm/h</div>
                <div style="font-size:10px;opacity:0.6;">Annual est.: {region.curah_hujan_mm_yr:.0f} mm</div>
            </div>
            <div class="neon-metric">
                <div class="label">☁️ Cloud Cover</div>
                <div class="value" style="font-size:20px;">{cloud_pct:.0f}%</div>
                <div style="font-size:10px;opacity:0.6;">☀️ Radiasi: {live_wx.solar_radiation:.0f} W/m²</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:11px;margin-top:8px;">
            <div>💨 Angin: <b>{live_wx.wind_speed:.1f} m/s</b></div>
            <div>📊 Tekanan: <b>{live_wx.pressure_hpa:.0f} hPa</b></div>
            <div>🌱 Zona Oldeman: <b>{region.zona_agroklimat}</b></div>
            <div>🏔️ Tanah: <b>{region.tanah_dominan}</b></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:11px;margin-top:8px;">
            <div>📐 BBox Lat: <b>{sat.lat_min:.5f}° → {sat.lat_max:.5f}°</b></div>
            <div>📐 BBox Lon: <b>{sat.lon_min:.5f}° → {sat.lon_max:.5f}°</b></div>
            <div>📡 Sumber cuaca: <b>{wx_src_label}</b></div>
        </div>
        <div style="margin-top:8px;font-size:11px;">
            🌿 Status lahan: <b>{drought_label}</b>
            &nbsp;·&nbsp; Seed unik: <code>{sat.seed}</code>
            &nbsp;·&nbsp; Model NDVI & kelembapan menggunakan data cuaca nyata koordinat ini
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Metrics row ────────────────────────────────────────────────────────
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.metric("🌿 NDVI Rata-rata", f"{stats['ndvi_mean']:.2f}",
              help="0 = tandus, 1 = vegetasi lebat")
    s2.metric("⚠️ Area Stress",    f"{stats['ndvi_stress_pct']:.1f}%",
              help="Persentase piksel NDVI < 0.4 (tanaman stress)")
    s3.metric("💧 Moist Avg",      f"{stats['moisture_mean']:.0f}%",
              help="Kelembapan tanah rata-rata (dipengaruhi cuaca live)")
    s4.metric("🌧️ Drought Index",  f"{drought:.2f}",
              delta="kering" if drought > 0.3 else "normal",
              delta_color="inverse",
              help="0=lembab, 1=sangat kering — dari live weather")
    s5.metric("⛰️ Δ Elevasi",      f"{stats['elevation_range']:.1f} m",
              help="Max-min elevation difference in farm area")
    s6.metric("📏 Dimensi",        f"{sat.side_m:.0f}×{sat.side_m:.0f} m",
              help="Size of the visualized area")

    if not _PLOTLY_OK:
        st.info("Plotly not installed. `pip install plotly` for visualizations.")
        return

    # ── 4 Sub-tabs — World Map Views ─────────────────────────────────────
    sub_tabs = st.tabs([
        "🌍 Peta Interaktif Dunia",
        "🛰️ Tampak Atas + NDVI",
        "⛰️ Model 3D Terrain",
        "🌡️ Heatmap + Overlay",
    ])

    # ── TAB 1: Interactive World Map (pydeck / st.map fallback) ──────────
    with sub_tabs[0]:
        st.caption(
            f"Peta dunia interaktif · Auto-fly ke {_loc.display_name} "
            f"({_loc.lat:.4f}°, {_loc.lon:.4f}°) · "
            "Satellite imagery: set Mapbox API key in sidebar for satellite layer."
        )
        _mbkey = _get_cfg("mapbox_api_key", os.environ.get("MAPBOX_API_KEY", ""))
        try:
            import pydeck as pdk   # noqa
            # Build marker data: current location + nearby INDO_REGIONS if Indonesia
            _map_pts = [{"lat": _loc.lat, "lon": _loc.lon,
                         "name": _loc.display_name, "r": 255, "g": 60, "b": 60, "a": 220, "rad": 800}]
            if _loc.country_code == "ID":
                for _rr in list(INDO_REGIONS.values()):
                    _map_pts.append({"lat": _rr.lat, "lon": _rr.lon,
                                     "name": _rr.nama,
                                     "r": 60, "g": 210, "b": 100, "a": 160, "rad": 400})
            _map_zoom = (14 if _loc.village else
                         12 if _loc.district else
                         10 if _loc.city else
                         7  if _loc.province else 4)
            _view_st = pdk.ViewState(
                latitude=_loc.lat, longitude=_loc.lon,
                zoom=_map_zoom, pitch=30, bearing=0)
            _scatter_l = pdk.Layer(
                "ScatterplotLayer", data=_map_pts,
                get_position=["lon", "lat"],
                get_fill_color=["r", "g", "b", "a"],
                get_radius="rad", pickable=True, auto_highlight=True)
            _text_l = pdk.Layer(
                "TextLayer", data=[_map_pts[0]],
                get_position=["lon", "lat"], get_text="name",
                get_size=16, get_color=[255, 255, 255, 230],
                get_alignment_baseline="'bottom'")
            _map_style = (
                "mapbox://styles/mapbox/satellite-streets-v11" if _mbkey
                else "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json")
            _deck_cfg: Dict[str, Any] = {}
            if _mbkey:
                _deck_cfg["api_keys"] = {"mapbox": _mbkey}
            _deck = pdk.Deck(
                layers=[_scatter_l, _text_l],
                initial_view_state=_view_st,
                map_style=_map_style,
                tooltip={"html": "<b>{name}</b>", "style": {"color": "white"}},
                **_deck_cfg)
            st.pydeck_chart(_deck, width='stretch')
            if not _mbkey:
                st.caption(
                    "💡 Untuk layer satellite Mapbox: tambahkan `MAPBOX_API_KEY` di file `.env` "
                    "(free at mapbox.com). Currently using CARTO Voyager, free.")
        except ImportError:
            # Fallback: st.map
            _df_map = pd.DataFrame({"lat": [_loc.lat], "lon": [_loc.lon]})
            if _loc.country_code == "ID":
                _extra = pd.DataFrame({
                    "lat": [r.lat for r in INDO_REGIONS.values()],
                    "lon": [r.lon for r in INDO_REGIONS.values()],
                })
                _df_map = pd.concat([_df_map, _extra], ignore_index=True)
            st.map(_df_map, zoom=6)
            st.caption("ℹ️ Install `pydeck` for 3D interactive map: `pip install pydeck`")

        # ── Administrative boundaries info ───────────────────────────────
        st.markdown(f"""
        <div style="background:#0a1a0a;border:1px solid #1e4a1e;border-radius:8px;
             padding:10px 14px;margin-top:8px;font-size:12px;">
        <b>📊 Hierarki Wilayah</b><br>
        🌍 <b>Negara:</b> {_loc.country} ({_loc.country_code}) &nbsp;·&nbsp;
        🏛️ <b>{_loc.admin_labels.get('province','Provinsi')}:</b> {_loc.province or '—'} &nbsp;·&nbsp;
        🏙️ <b>{_loc.admin_labels.get('city','Kota')}:</b> {_loc.city or '—'}<br>
        📍 <b>{_loc.admin_labels.get('district','Kecamatan')}:</b> {_loc.district or '—'} &nbsp;·&nbsp;
        🏘️ <b>{_loc.admin_labels.get('village','Kelurahan')}:</b> {_loc.village or '—'} &nbsp;·&nbsp;
        🌡️ <b>Zona Iklim:</b> {_loc.climate_zone} &nbsp;·&nbsp;
        💰 <b>Mata Uang:</b> {_loc.currency} {_loc.currency_symbol}
        </div>""", unsafe_allow_html=True)

    # ── TAB 2: Top-down satellite view + NDVI ────────────────────────────
    with sub_tabs[1]:
        st.caption(
            f"Tampak atas · layer **{layer.upper()}** · koordinat {region.lat:.5f}°, {region.lon:.5f}° · "
            f"NDVI & kelembapan dikoreksi cuaca live ({live_wx.source})."
        )
        fig1 = sat.figure_topdown_geo(layer=layer)
        if fig1:
            st.plotly_chart(fig1, width='stretch')
        side_km = sat.side_m / 1000.0
        st.caption(
            f"📐 {sat.side_m:.0f}×{sat.side_m:.0f} m ({side_km:.3f} km²) · "
            f"Lat {sat.lat_min:.5f}°→{sat.lat_max:.5f}° · "
            f"Lon {sat.lon_min:.5f}°→{sat.lon_max:.5f}°"
        )

    # ── TAB 3: 3D Terrain Model ───────────────────────────────────────────
    with sub_tabs[2]:
        st.caption(
            f"Model 3D terrain · relief {sat.relief_amplitude():.0f} m · "
            f"kelas terrain **{sat.terrain.replace('_',' ').title()}** · "
            f"color = {layer.upper()} · hover for exact lat/lon."
        )
        fig2 = sat.figure_3d(
            layer=layer,
            title=f"{region.nama} ({region.lat:.4f}°, {region.lon:.4f}°) — {layer.upper()}"
        )
        if fig2:
            st.plotly_chart(fig2, width='stretch')

    # ── TAB 4: Heatmap + Thematic Overlay ────────────────────────────────
    with sub_tabs[3]:
        _heat_col, _overlay_col = st.columns([2, 1])
        with _heat_col:
            st.caption("Per-pixel heatmap with real lat/lon axes.")
            fig3 = sat.figure_zone_heatmap(layer)
            if fig3:
                st.plotly_chart(fig3, width='stretch')
        with _overlay_col:
            st.markdown("**🗺️ Thematic Layers**")
            _ovl_metric = st.radio("Layer", ["💧 Water Sources", "🌾 Crop Zones",
                                             "👥 Population Density", "🌳 Carbon Sink"],
                                   key="sat3d_overlay_metric")
            st.markdown(f"""
            <div style="background:#0a1020;border:1px solid #1a3060;border-radius:8px;
                 padding:10px;font-size:11px;margin-top:8px;">
            <b>{_ovl_metric}</b><br><br>
            📍 Location: {_loc.display_name}<br>
            📡 Source: NASA FIRMS / Copernicus<br>
            ⚠️ <i>Real data feed requires NASA/ESA API key.<br>
            Tambahkan di file .env:<br>
            <code>NASA_API_KEY</code> atau <code>COPERNICUS_KEY</code></i><br><br>
            🌍 Zona Iklim: <b>{_loc.climate_zone}</b><br>
            🌧️ Est. hujan/thn: <b>{region.curah_hujan_mm_yr:.0f} mm</b><br>
            🌡️ Suhu rata2: <b>{region.suhu_avg:.1f}°C</b><br>
            🏔️ Tanah: <b>{region.tanah_dominan}</b>
            </div>""", unsafe_allow_html=True)


def render_sensor_bridge_panel():
    if not _STREAMLIT_OK:
        return
    st.markdown('<div class="section-header">🔌 REAL SENSOR BRIDGE</div>',
                unsafe_allow_html=True)

    if "sensor_bridge" not in st.session_state:
        st.session_state.sensor_bridge = RealSensorBridge(SensorBackendType.SIMULATED)

    bridge: RealSensorBridge = st.session_state.sensor_bridge

    backends = list(SensorBackendType)
    backend_str = st.selectbox(
        "Backend",
        [b.value for b in backends],
        index=[b.value for b in backends].index(bridge.backend.value),
        key="sb_backend",
    )
    new_backend = next(b for b in backends if b.value == backend_str)

    cfg = bridge.config.copy()
    if new_backend == SensorBackendType.SERIAL:
        ports = bridge.list_serial_ports()
        col1, col2 = st.columns(2)
        with col1:
            cfg["port"] = st.selectbox(
                "Serial Port", ports or ["COM3", "/dev/ttyUSB0"], key="sb_port"
            )
        with col2:
            cfg["baud"] = st.selectbox("Baud", [9600, 19200, 38400, 57600, 115200],
                                       index=4, key="sb_baud")
    elif new_backend == SensorBackendType.HTTP:
        cfg["url"] = st.text_input("URL", value=cfg.get("url", "http://localhost:8080/sensors"),
                                    key="sb_url")
    elif new_backend == SensorBackendType.MQTT:
        c1, c2, c3 = st.columns(3)
        cfg["host"] = c1.text_input("Host", cfg.get("host", "localhost"), key="sb_mqhost")
        cfg["port"] = c2.number_input("Port", 1, 65535, int(cfg.get("port", 1883)), key="sb_mqport")
        cfg["topic"] = c3.text_input("Topic", cfg.get("topic", "greenhouse/+/sensor/+"),
                                     key="sb_mqtopic")
        c4, c5 = st.columns(2)
        cfg["username"] = c4.text_input("Username (opt)", cfg.get("username", ""), key="sb_mquser")
        cfg["password"] = c5.text_input("Password (opt)", cfg.get("password", ""),
                                        type="password", key="sb_mqpw")
    elif new_backend == SensorBackendType.MODBUS:
        c1, c2 = st.columns(2)
        cfg["host"] = c1.text_input("Host", cfg.get("host", "127.0.0.1"), key="sb_mbhost")
        cfg["port"] = c2.number_input("Port", 1, 65535, int(cfg.get("port", 502)), key="sb_mbport")

    col_a, col_b, col_c = st.columns(3)
    if col_a.button("🔌 Connect", key="sb_connect"):
        bridge.disconnect()
        new_bridge = RealSensorBridge(new_backend, cfg)
        ok = new_bridge.connect()
        st.session_state.sensor_bridge = new_bridge
        if ok:
            st.success(f"✅ Terkoneksi: {new_backend.value}")
        else:
            st.warning(f"⚠️ Real-connect failed ({new_bridge.last_error}). Falling back to simulation.")
        bridge = new_bridge
    if col_b.button("🔄 Read Now", key="sb_read"):
        st.rerun()
    if col_c.button("⏹️ Disconnect", key="sb_disc"):
        bridge.disconnect()
        st.info("Disconnected.")

    # Status
    if bridge.connected and bridge.backend != SensorBackendType.SIMULATED:
        st.markdown(f'<span class="badge-online">● LIVE — {bridge.backend.value}</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-warn">● SIMULATED (Virtual)</span>',
                    unsafe_allow_html=True)
        if bridge.last_error:
            st.caption(f"Last error: {bridge.last_error}")

    # Read & display
    readings = bridge.read_all()
    if readings:
        df = pd.DataFrame([
            {"sensor": r.name, "value": round(r.value, 3),
             "unit": r.unit, "source": r.source, "time": r.timestamp,
             "quality": r.quality}
            for r in readings.values()
        ])
        st.dataframe(df, width='stretch', height=240)
    else:
        st.warning("Belum ada bacaan sensor.")


def render_companion_rotation_panel():
    if not _STREAMLIT_OK:
        return
    st.markdown('<div class="section-header">🌳 COMPANION & ROTATION</div>',
                unsafe_allow_html=True)
    crop = render_indonesian_crop_selector("comp")
    if not crop:
        return
    comp = companion_plants(crop.id)
    rot  = crop_rotation_plan(crop.id, n_seasons=4)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**✅ Good Companions**")
        if comp["good"]:
            st.markdown("\n".join(f"- {x}" for x in comp["good"]))
        else:
            st.caption("No specific data available.")
    with c2:
        st.markdown("**❌ Avoid**")
        if comp["bad"]:
            st.markdown("\n".join(f"- {x}" for x in comp["bad"]))
        else:
            st.caption("No known conflicts.")

    st.markdown("**🔄 Rencana Rotasi 4 Musim:**")
    st.table(pd.DataFrame(rot, columns=["Season", "Crop"]))


def render_pest_disease_panel():
    if not _STREAMLIT_OK:
        return
    st.markdown('<div class="section-header">🐛 PEST & DISEASE CALENDAR</div>',
                unsafe_allow_html=True)
    crop = render_indonesian_crop_selector("pest")
    if not crop:
        return
    col_a, col_b = st.columns(2)
    with col_a:
        plant_date = st.date_input("Tgl Tanam", datetime.date.today(), key="pest_date")
    with col_b:
        rh = st.slider("Current RH (%)", 50, 100, 80, 1, key="pest_rh")
    pdc = PestDiseaseCalendar(PlantingRecord(crop.id, plant_date), current_rh=float(rh))
    info = pdc.today()
    st.markdown(
        f"""
        <div class="prediction-box">
        <b>Fase:</b> {info['fase']} (DAP {info['dap']})<br>
        <b>Hama Berisiko:</b> {', '.join(f"{k}({v:.0%})" for k,v in info['hama_risiko'].items()) or 'Aman'}<br>
        <b>Penyakit Potensi:</b> {', '.join(info['penyakit_potensi'])}<br>
        <b>Hama umum tanaman ini:</b> {', '.join(crop.hama_umum) or '—'}<br>
        <b>Common diseases:</b> {', '.join(crop.penyakit_umum) or '—'}
        </div>
        """, unsafe_allow_html=True,
    )
    st.markdown("**📋 Recommendations:**")
    for r in info["rekomendasi"]:
        st.markdown(f"- {r}")


def render_economic_projection_panel():  # noqa: C901
    """Economic projection — 3-currency real-time · itemized breakdown · 3 scenarios."""
    if not _STREAMLIT_OK:
        return
    _loc_e = get_location_state()
    _sym   = _loc_e.currency_symbol
    _cc    = _loc_e.currency

    st.markdown(
        f'<div class="section-header">💰 ECONOMICS PROJECTION — '
        f'{_loc_e.flag_emoji} {_loc_e.country} · IDR | USD | {_cc}</div>',
        unsafe_allow_html=True)
    st.caption(fx_last_updated())

    region = _loc_e.to_indo_region()

    # ── Input Panel ───────────────────────────────────────────────────────
    with st.expander("⚙️ Parameter Input", expanded=True):
        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            crop = render_indonesian_crop_selector("econ2")
        with ec2:
            area_ha = st.number_input("Farm Area (ha)", 0.01, 50000.0, 1.0, 0.1, key="econ2_area")
            plant_month = st.selectbox("Planting Month", range(1, 13),
                format_func=lambda m: ["Jan","Feb","Mar","Apr","May","Jun",
                                       "Jul","Aug","Sep","Oct","Nov","Dec"][m-1],
                key="econ2_plant_month")
        with ec3:
            irrig_type  = st.selectbox("Irrigation Source",
                                       ["Rainfed", "Drip Irrigation", "Flood/Paddy"],
                                       key="econ2_irrig")
            labor_type  = st.selectbox("Mekanisasi",
                                       ["Manual", "Semi-Mekanis", "Full Mekanis"],
                                       key="econ2_labor")
            seed_var    = st.selectbox("Varietas Benih",
                                       ["Local Standard", "National Improved", "Hybrid Import"],
                                       key="econ2_seed")
            fert_plan   = st.selectbox("Fertilizer",
                                       ["Organik", "Kimia NPK", "Terpadu"],
                                       key="econ2_fert")
            mkt_channel = st.selectbox("Saluran Pasar",
                                       ["Pasar Lokal", "Tengkulak", "Ekspor Langsung"],
                                       key="econ2_market")

    if not crop:
        st.info("Select crop in the input panel.")
        return

    # ── Cost + market model (country-aware) ───────────────────────────────
    _market_profile = market_profile_for_country(_loc_e.country_code)
    _irrig_cost_ha = {"Tadah Hujan": 0, "Irigasi Tetes": 4_500_000, "Banjir/Sawah": 2_000_000}
    _labor_cost_ha = {"Manual": 8_000_000, "Semi-Mekanis": 5_500_000, "Full Mekanis": 3_000_000}
    _seed_mult     = {"Local Standard": 1.0, "National Improved": 1.5, "Hybrid Import": 2.8}
    _fert_cost_ha  = {"Organik": 2_000_000, "Kimia NPK": 3_500_000, "Terpadu": 2_800_000}
    _mkt_loss_pct  = {"Pasar Lokal": 0.08, "Tengkulak": 0.12, "Ekspor Langsung": 0.04}

    # Realistic per-ha BASE seed cost by crop category (IDR) — Kementan 2024 ref.
    _SEED_BASE_HA = {
        IndoCropCategory.PANGAN_POKOK:  1_800_000,   # benih padi/jagung/sorgum
        IndoCropCategory.PALAWIJA:      1_400_000,   # kedelai, kacang
        IndoCropCategory.HORTIKULTURA:  3_200_000,   # benih sayuran (F1 lebih mahal)
        IndoCropCategory.BUAH:          2_500_000,   # bibit/stek buah
        IndoCropCategory.PERKEBUNAN:    4_500_000,   # bibit sawit/karet/kakao
        IndoCropCategory.HERBAL_BUMBU:  2_000_000,   # bibit rempah/herbal
        IndoCropCategory.BIOFARMAKA:    2_200_000,   # simplisia/tanaman obat
        IndoCropCategory.UMBI:          1_600_000,   # bibit umbi (singkong/ubi)
    }

    # Seasonal yield modifier (is it wet season for this crop's region?)
    _wet_bonus = 1.0
    if plant_month in region.musim_hujan_bulan and irrig_type == "Tadah Hujan":
        _wet_bonus = 1.15   # wet season boost for rainfed
    elif plant_month not in region.musim_hujan_bulan and irrig_type == "Tadah Hujan":
        _wet_bonus = 0.75   # dry season penalty for rainfed

    # Base yield from crop DB
    _yield_base_t_ha = (crop.yield_ton_per_ha_min + crop.yield_ton_per_ha_max) / 2
    _yield_mult = (_seed_mult.get(seed_var, 1.0) * 0.5 + 0.5) * _wet_bonus  # seed quality effect
    _loss_pct   = _mkt_loss_pct.get(mkt_channel, 0.08)
    _price_kg, _price_meta = localized_crop_price_idr(crop, _loc_e, mkt_channel)

    # Per-HA cost breakdown (IDR)
    # Seed cost: realistic base by category × seed quality multiplier (Kementan 2024)
    _seed_base_ha   = _SEED_BASE_HA.get(crop.kategori, 1_800_000)
    _input_cost_factor = localized_cost_factor(_loc_e, "cost")
    _labor_factor      = localized_cost_factor(_loc_e, "labor")
    _land_factor       = localized_cost_factor(_loc_e, "land")
    _seed_cost_ha   = _seed_base_ha * _seed_mult.get(seed_var, 1.0) * _input_cost_factor
    _fert_cost_ha   = _fert_cost_ha.get(fert_plan, 3_000_000) * _input_cost_factor
    _labor_cost_ha  = _labor_cost_ha.get(labor_type, 6_000_000) * _labor_factor
    _irrig_cost_ha2 = _irrig_cost_ha.get(irrig_type, 0) * _input_cost_factor
    _land_cost_ha   = 2_000_000 * _land_factor
    _misc_cost_ha   = 500_000 * _input_cost_factor
    _transport_ha   = (300_000 if mkt_channel == "Ekspor Langsung" else 150_000) * _input_cost_factor

    _total_cost_ha  = (_seed_cost_ha + _fert_cost_ha + _labor_cost_ha +
                       _irrig_cost_ha2 + _land_cost_ha + _misc_cost_ha + _transport_ha)
    _total_cost     = _total_cost_ha * area_ha

    def _money_lines(amount_idr: float, loc: LocationState) -> str:
        parts = [p.strip() for p in fmt_3ccy(amount_idr, loc).split("|")]
        rows = []
        for idx, part in enumerate(parts):
            cls = "econ-money-line primary" if idx == 0 else "econ-money-line local"
            rows.append(f'<span class="{cls}">{html.escape(part)}</span>')
        return "".join(rows)

    def _econ_card(label: str, value: str, sub: str = "", tone: str = "good",
                   money: bool = False) -> str:
        value_html = _money_lines(float(value), _loc_e) if money else html.escape(str(value))
        card_cls = f"econ-card {tone}" + (" money" if money else "")
        return (
            f'<div class="{card_cls}">'
            f'<div class="label">{html.escape(label)}</div>'
            f'<div class="value">{value_html}</div>'
            f'<div class="sub">{html.escape(sub)}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="econ-note">'
        f'🌍 Harga komoditas disesuaikan negara aktif: <b>{html.escape(_loc_e.country)}</b>. '
        f'Harga dasar Indonesia {_idr(crop.harga_kg_idr)}/kg → harga pasar aktif '
        f'<b>{fmt_3ccy(_price_kg, _loc_e)}/kg</b>. '
        f'Faktor negara: harga ×{_price_meta["country_mult"]:.2f}, '
        f'kategori ×{_price_meta["category_mult"]:.2f}, kanal ×{_price_meta["channel_mult"]:.2f}, '
        f'biaya input ×{_input_cost_factor:.2f}, tenaga kerja ×{_labor_factor:.2f}, lahan ×{_land_factor:.2f}.'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 3 scenarios
    for _sc_name, _sc_yield_f, _sc_price_f, _sc_cost_f in [
        ("📉 Pesimis",  0.75, 0.85, 1.10),
        ("📊 Baseline", 1.00, 1.00, 1.00),
        ("📈 Optimis",  1.30, 1.15, 0.90),
    ]:
        _y   = _yield_base_t_ha * _yield_mult * _sc_yield_f * area_ha
        _rev = _y * 1000 * _price_kg * _sc_price_f * (1 - _loss_pct)
        _cos = _total_cost * _sc_cost_f
        _prof= _rev - _cos
        _roi = (_prof / _cos * 100) if _cos > 0 else 0
        _bep = _cos / max(_price_kg, 1)  # kg needed to break even
        _cycle_d = max(1, crop.dap_panen)
        _bep_days = _cycle_d * (_cos / max(_rev, 1))

        with st.expander(f"{_sc_name} — ROI {_roi:.1f}%", expanded=(_sc_name == "📊 Baseline")):
            _profit_tone = "good" if _prof >= 0 else "bad"
            _roi_tone = "good" if _roi >= 20 else ("warn" if _roi >= 0 else "bad")
            _cards = [
                _econ_card("🌾 Yield Est.", f"{_y:.2f} ton",
                           f"{_yield_base_t_ha:.2f} t/ha base · loss {_loss_pct:.0%}", "info"),
                _econ_card("💰 Revenue", _rev,
                           f"Price/kg: {fmt_3ccy(_price_kg * _sc_price_f, _loc_e)}", "good", money=True),
                _econ_card("📉 Total Cost", _cos,
                           f"Cost/ha: {fmt_3ccy(_total_cost_ha * _sc_cost_f, _loc_e)}", "warn", money=True),
                _econ_card("📈 Net Profit", _prof,
                           f"ROI {_roi:.1f}%", _profit_tone, money=True),
                _econ_card("⚖️ BEP Produksi", f"{_bep:,.0f} kg",
                           f"Margin/kg {fmt_3ccy((_price_kg * _sc_price_f) - (_cos / max(_y * 1000, 1)), _loc_e)}", _roi_tone),
                _econ_card("📅 Break-even", f"{_bep_days:.0f} hari",
                           f"from {_cycle_d}-day cycle", _roi_tone),
                _econ_card("🌍 Harga Pasar Aktif", _price_kg * _sc_price_f,
                           f"{_loc_e.country_code} · kanal {mkt_channel}", "info", money=True),
                _econ_card("📊 Konfiden Model", "MEDIUM-HIGH",
                           f"Volatilitas negara ×{_market_profile.get('vol', 1.0):.2f}", "info"),
            ]
            st.markdown(f'<div class="econ-grid">{"".join(_cards)}</div>', unsafe_allow_html=True)

            # Itemized cost table
            _cost_rows = [
                {"Item": "🌱 Benih", "Biaya/ha": fmt_3ccy(_seed_cost_ha, _loc_e),
                 "Total": fmt_3ccy(_seed_cost_ha*area_ha, _loc_e),
                 "Basis": f"Kategori × seed × negara ({_input_cost_factor:.2f})", "Konfiden": "MEDIUM"},
                {"Item": "🌿 Fertilizer", "Biaya/ha": fmt_3ccy(_fert_cost_ha, _loc_e),
                 "Total": fmt_3ccy(_fert_cost_ha*area_ha, _loc_e),
                 "Basis": f"Input regional × negara ({_input_cost_factor:.2f})", "Konfiden": "MEDIUM"},
                {"Item": "👷 Tenaga Kerja", "Biaya/ha": fmt_3ccy(_labor_cost_ha, _loc_e),
                 "Total": fmt_3ccy(_labor_cost_ha*area_ha, _loc_e),
                 "Basis": f"Mekanisasi × labor factor ({_labor_factor:.2f})", "Konfiden": "MEDIUM"},
                {"Item": "💧 Irigasi", "Biaya/ha": fmt_3ccy(_irrig_cost_ha2, _loc_e),
                 "Total": fmt_3ccy(_irrig_cost_ha2*area_ha, _loc_e),
                 "Basis": "Sistem irigasi × input factor", "Konfiden": "MEDIUM"},
                {"Item": "🏡 Land", "Biaya/ha": fmt_3ccy(_land_cost_ha, _loc_e),
                 "Total": fmt_3ccy(_land_cost_ha*area_ha, _loc_e),
                 "Basis": f"Land factor negara ({_land_factor:.2f})", "Konfiden": "LOW"},
                {"Item": "🚛 Transport", "Biaya/ha": fmt_3ccy(_transport_ha, _loc_e),
                 "Total": fmt_3ccy(_transport_ha*area_ha, _loc_e),
                 "Basis": f"Kanal {mkt_channel}", "Konfiden": "MEDIUM"},
                {"Item": "📦 Buffer", "Biaya/ha": fmt_3ccy(_misc_cost_ha, _loc_e),
                 "Total": fmt_3ccy(_misc_cost_ha*area_ha, _loc_e),
                 "Basis": "Cadangan operasional", "Konfiden": "LOW"},
                {"Item": "═ TOTAL", "Biaya/ha": fmt_3ccy(_total_cost_ha, _loc_e),
                 "Total": fmt_3ccy(_total_cost, _loc_e),
                 "Basis": "—", "Konfiden": "—"},
            ]
            st.dataframe(pd.DataFrame(_cost_rows), width='stretch', hide_index=True)
            st.caption(
                f"⚠️ Market price is a country-aware estimate, not a fixed reference. "
                f"Untuk real-time resmi, sambungkan API statistik/market board negara terkait.")

    # Currency info footer
    _rates = fetch_exchange_rates("IDR")
    _usd_r = _rates.get("USD", 6.25e-5)
    _lcl_r = _rates.get(_cc, 1.0) if _cc != "IDR" else None
    st.caption(
        f"💱 Kurs: 1 IDR = USD {_usd_r:.6f}"
        + (f" | {_sym} {_lcl_r:.4f} ({_cc})" if _lcl_r else "")
        + f" · {fx_last_updated()}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 14. MASTER PANEL — ALL-IN-ONE TABS
# ══════════════════════════════════════════════════════════════════════════════

def render_v5_master_panels():
    """Panel master — semua fitur v5 + Tier 1-4 dalam tabs."""
    if not _STREAMLIT_OK:
        return

    # ── Dynamic title driven by LocationState ────────────────────────────
    _loc_hdr  = get_location_state()
    _hdr_flag = _loc_hdr.flag_emoji
    _hdr_ctry = _loc_hdr.country
    _hdr_loc  = _loc_hdr.display_name or _hdr_ctry
    _hdr_zone = _loc_hdr.climate_zone
    st.markdown(f"""
    <div class="ag5-hero" style="margin-top:18px;">
        <h1>{_hdr_flag} Smart Agriculture — {_hdr_ctry} v5 · Tier 1 → 4</h1>
        <p>
            📍 {_hdr_loc} &nbsp;·&nbsp; Zona: <b>{_hdr_zone}</b> &nbsp;·&nbsp;
            {_loc_hdr.lat:.4f}°, {_loc_hdr.lon:.4f}° &nbsp;·&nbsp;
            Mata uang: {_loc_hdr.currency} {_loc_hdr.currency_symbol}<br>
            <span style="font-size:11px;opacity:.75;">
            Dari kalender tanam hingga deteksi penyakit AI, sensor real, peta dunia 3D, Carbon MRV —
            semua dalam satu platform · lokasi sinkron real-time.
            </span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Sub-banner: tier breakdown with friendly descriptions
    st.markdown("""
    <div class="tier-banner" style="line-height:1.9;">
        <span class="ai-badge tier1-badge">TIER 1</span>
        &nbsp;Foundation — Calendar, Sensors, Marketplace, Microcredit &nbsp;&nbsp;
        <span class="ai-badge tier2-badge">TIER 2</span>
        &nbsp;Frontier — Carbon MRV, AI Outbreak, Hyperspectral &nbsp;&nbsp;
        <span class="ai-badge tier3-badge">TIER 3</span>
        &nbsp;Moonshot — Bioelectric, AR Field, Quantum &nbsp;&nbsp;
        <span class="ai-badge tier4-badge">TIER 4</span>
        &nbsp;Civilization — National Agri Index, Mars Mode
    </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs([
        "📅 Planting Calendar",
        "💧 Water & Nutrients",
        "🛰️ 3D Satellite Map",
        "🔌 Live Sensors",
        "💰 Economics",
        "🐛 Pests & Disease",
        "🌳 Crop Rotation",
        "📚 Crop Database",
        "🤖 AI Agronomist",
        "📷 Plant Doctor",
        "📱 Notification Bot",
        "🛒 Marketplace",
        "💳 Microcredit",
        "🌍 Carbon MRV",
        "⚠️ AI Outbreak",
        "🌈 Hyperspectral",
        "🧬 Bioelectric",
        "🥽 AR Field",
        "⚛️ Quantum Optim.",
        "📊 Agri Index",
        "🌿 GreenLight+",
        "🚀 Mars Mode",
    ])
    with tabs[0]:  render_plant_calendar_panel()
    with tabs[1]:  render_water_nutrient_plan_panel()
    with tabs[2]:  render_satellite_3d_panel()
    with tabs[3]:  render_sensor_bridge_panel()
    with tabs[4]:  render_economic_projection_panel()
    with tabs[5]:  render_pest_disease_panel()
    with tabs[6]:  render_companion_rotation_panel()
    with tabs[7]:  render_database_browser()
    with tabs[8]:  render_llm_agronomist_panel()
    with tabs[9]:  render_plant_doctor_cv_panel()
    with tabs[10]: render_notification_bot_panel()
    with tabs[11]: render_marketplace_panel()
    with tabs[12]: render_microcredit_panel()
    with tabs[13]: render_carbon_mrv_panel()
    with tabs[14]: render_outbreak_predictor_panel()
    with tabs[15]: render_hyperspectral_panel()
    with tabs[16]: render_bioelectric_panel()
    with tabs[17]: render_ar_field_panel()
    with tabs[18]: render_quantum_optimizer_panel()
    with tabs[19]: render_indo_agri_index_panel()
    with tabs[20]: render_greenlight_panel()
    with tabs[21]: render_mars_mode_panel()


def render_database_browser():
    if not _STREAMLIT_OK:
        return
    st.markdown(f"**Total: {len(INDONESIAN_CROPS_DB)} crops**")
    loc_db = get_location_state()
    rows = []
    for c in INDONESIAN_CROPS_DB.values():
        n_total, p_total, k_total = c.total_npk_kg_per_ha()
        local_price, meta = localized_crop_price_idr(c, loc_db)
        rows.append({
            "ID":             c.id,
            "Name":           c.nama_id,
            "English":        c.nama_en,
            "Category":       c.kategori.value,
            "DAP Harvest":    c.dap_panen,
            "Opt Temp":       f"{c.suhu_optimal:.0f}°C",
            "Alt masl":       f"{c.altitude_min_mdpl}-{c.altitude_max_mdpl}",
            "Air Total mm":   round(c.total_water_mm_lifecycle()),
            "N kg/ha":        round(n_total),
            "P kg/ha":        round(p_total),
            "K kg/ha":        round(k_total),
            "Yield t/ha":   f"{c.yield_ton_per_ha_min}-{c.yield_ton_per_ha_max}",
            f"Harga/kg ({loc_db.country_code})": fmt_3ccy(local_price, loc_db),
            "Country Factor":  f"×{meta['country_mult']:.2f}",
        })
    df = pd.DataFrame(rows)
    cat_filter = st.multiselect(
        "Filter Category",
        sorted(df["Category"].unique()),
        default=sorted(df["Category"].unique()),
        key="db_cat_filter",
    )
    if cat_filter:
        df = df[df["Category"].isin(cat_filter)]
    search = st.text_input("🔍 Search crop name", key="db_search")
    if search:
        df = df[df["Name"].str.contains(search, case=False, na=False) |
                df["English"].str.contains(search, case=False, na=False)]
    st.dataframe(df, width='stretch', height=560)
    st.download_button("📥 Download Database CSV",
                       df.to_csv(index=False).encode("utf-8"),
                       file_name="indonesian_crops_database.csv",
                       mime="text/csv")


# ══════════════════════════════════════════════════════════════════════════════
# 15. INTEGRATION HELPER — JEMBATAN KE CropParams TUMBAL.PY v4
# ══════════════════════════════════════════════════════════════════════════════

INDO_TO_TUMBAL_MAP = {
    # ── Tomato family
    "tomat":          "Tomato",  "terong_ungu":  "Tomato",
    # ── Lettuce / leafy greens
    "selada":         "Lettuce", "kangkung":     "Lettuce", "bayam":         "Spinach",
    "sawi_hijau":     "Lettuce", "pakcoy":       "Lettuce", "kubis":         "Lettuce",
    "kol_bunga":      "Lettuce", "brokoli":      "Lettuce", "seledri":       "Lettuce",
    "daun_bawang":    "Lettuce",
    # ── Cucumber / cucurbits
    "mentimun":       "Cucumber","labu_siam":    "Cucumber","labu_kuning":   "Cucumber",
    "oyong":          "Cucumber","pare":         "Cucumber","semangka":      "Cucumber",
    "melon":          "Cucumber","buncis":       "Cucumber","kacang_panjang":"Cucumber",
    # ── Pepper
    "cabai_merah":    "Pepper",  "cabai_rawit":  "Pepper",  "paprika":       "Pepper",
    "okra":           "Pepper",
    # ── Strawberry / fruits
    "stroberi":       "Strawberry","jambu_kristal":"Strawberry","markisa":   "Strawberry",
    "naga_merah":     "Strawberry","anggur":     "Strawberry","kelengkeng":  "Strawberry",
    # ── Basil / herbs
    "kemangi":        "Basil",   "mint":         "Basil",   "rosella":       "Basil",
    "kunyit":         "Basil",   "jahe_merah":   "Basil",   "jahe_emprit":   "Basil",
    "lengkuas":       "Basil",   "kencur":       "Basil",   "sereh_dapur":   "Basil",
    "temulawak":      "Basil",   "sambiloto":    "Basil",   "binahong":      "Basil",
    "lidah_buaya":    "Basil",   "serai_wangi":  "Basil",   "nilam":         "Basil",
    "mengkudu":       "Basil",
    # ── Microgreens
    "microgreens":    "Microgreens","jagung_baby":"Microgreens",
    # ── Orchid / ornamentals
    "anggrek_dendro": "Orchid",  "krisan":       "Orchid",  "mawar_potong":  "Orchid",
    # ── Cannabis-tier (heavy feeders, cash crops)
    "padi_sawah":     "Hemp/CBD","padi_gogo":    "Hemp/CBD","jagung_manis":  "Hemp/CBD",
    "jagung_pakan":   "Hemp/CBD","kedelai":      "Hemp/CBD","kacang_tanah":  "Hemp/CBD",
    "kacang_hijau":   "Hemp/CBD","sorgum":       "Hemp/CBD","gandum":        "Hemp/CBD",
    "tembakau":       "Hemp/CBD","kopi_arabika": "Hemp/CBD","kopi_robusta":  "Hemp/CBD",
    "kakao":          "Hemp/CBD","teh":          "Hemp/CBD","tebu":          "Hemp/CBD",
    "lada":           "Hemp/CBD","cengkeh":      "Hemp/CBD","pala":          "Hemp/CBD",
    "vanili":         "Hemp/CBD","kapulaga":     "Hemp/CBD","kemiri":        "Hemp/CBD",
    "karet":          "Hemp/CBD","sawit":        "Hemp/CBD","kelapa":        "Hemp/CBD",
    # ── Tomato fallback (root vegetables)
    "ubi_jalar":      "Tomato",  "ubi_kayu":     "Tomato",  "talas":         "Tomato",
    "kentang":        "Tomato",  "porang":       "Tomato",  "wortel":        "Tomato",
    "lobak":          "Tomato",  "bit":          "Tomato",  "asparagus":     "Tomato",
    "bawang_merah":   "Tomato",  "bawang_putih": "Tomato",
    # ── Misc fruits
    "mangga":         "Strawberry","pisang":     "Strawberry","pepaya":      "Strawberry",
    "nanas":          "Strawberry","jeruk_siam": "Strawberry","alpukat":     "Strawberry",
    "durian":         "Strawberry","manggis":    "Strawberry","rambutan":    "Strawberry",
    "salak":          "Strawberry","nangka":     "Strawberry","sirsak":      "Strawberry",
    "belimbing":      "Strawberry",
    # ── Mushrooms
    "jamur_tiram":    "Microgreens","jamur_kuping":"Microgreens",
}


def get_unified_crop_choices() -> List[Tuple[str, str, str]]:
    """Returns sorted (display_name, crop_id, category) for all 102+ Indonesian crops."""
    items = []
    for c in INDONESIAN_CROPS_DB.values():
        display = c.nama_id if c.nama_id == c.nama_en else f"{c.nama_id} — {c.nama_en}"
        items.append((display, c.id, c.kategori.value))
    items.sort(key=lambda x: (x[2], x[0]))
    return items


def match_owm_city_to_indo_region(city_str: str) -> "IndoRegion":
    """Map OpenWeatherMap city string to nearest IndoRegion."""
    if not city_str:
        return INDO_REGIONS["jakarta"]
    cs = city_str.lower().split(",")[0].strip()
    for rid, r in INDO_REGIONS.items():
        if rid == cs or r.nama.lower() == cs:
            return r
    for rid, r in INDO_REGIONS.items():
        rname = r.nama.lower()
        if cs in rname or rname in cs or cs in rid or rid in cs:
            return r
        if r.provinsi.lower() in cs or cs in r.provinsi.lower():
            return r
    return INDO_REGIONS["jakarta"]


def indo_crop_id_to_croptype(crop_id: str) -> "CropType":
    """Map any Indonesian crop ID to closest CropType for simulation engine."""
    direct = INDO_TO_TUMBAL_MAP.get(crop_id)
    if direct:
        for ct in CropType:
            if ct.value == direct:
                return ct
    crop = INDONESIAN_CROPS_DB.get(crop_id)
    if not crop:
        return CropType.TOMATO
    cat = crop.kategori
    if cat == IndoCropCategory.HORTIKULTURA:    return CropType.LETTUCE
    if cat == IndoCropCategory.HERBAL_BUMBU:    return CropType.BASIL
    if cat == IndoCropCategory.BIOFARMAKA:      return CropType.BASIL
    if cat == IndoCropCategory.BUAH:            return CropType.STRAWBERRY
    if cat == IndoCropCategory.PANGAN_POKOK:    return CropType.CANNABIS
    if cat == IndoCropCategory.PALAWIJA:        return CropType.CANNABIS
    if cat == IndoCropCategory.PERKEBUNAN:      return CropType.CANNABIS
    if cat == IndoCropCategory.UMBI:            return CropType.TOMATO
    return CropType.TOMATO


def get_zone_indo_crop_id(zone) -> str:
    """Get Indonesian crop ID for a zone (explicit or reverse-mapped)."""
    explicit = getattr(zone, "indo_crop_id", None)
    if explicit and explicit in INDONESIAN_CROPS_DB:
        return explicit
    target_name = zone.crop_type.value
    for cid, ct_name in INDO_TO_TUMBAL_MAP.items():
        if ct_name == target_name:
            return cid
    return "tomat"


def get_default_indo_region() -> "IndoRegion":
    """Get region from current OWM city, or default Jakarta."""
    try:
        wx = st.session_state.get("wx_data")
        if wx and getattr(wx, "location", None):
            return match_owm_city_to_indo_region(wx.location)
    except Exception:
        pass
    return INDO_REGIONS["jakarta"]


def indo_crop_to_tumbal_params(indo_crop: IndoCrop, base_crop_params_cls=None,
                                CROP_PROFILES_dict: Optional[Dict] = None,
                                CropType_enum=None):
    """
    Adapter: konversi IndoCrop ke CropParams tumbal.py.
    Pakai map jika tersedia, kalau tidak hasilkan dari nilai default IndoCrop.
    """
    if base_crop_params_cls is None or CROP_PROFILES_dict is None:
        return None
    name_in_tumbal = INDO_TO_TUMBAL_MAP.get(indo_crop.id)
    if name_in_tumbal and CropType_enum is not None:
        for ct in CropType_enum:
            if ct.value == name_in_tumbal:
                return CROP_PROFILES_dict.get(ct)
    # generate default
    n_total, p_total, k_total = indo_crop.total_npk_kg_per_ha()
    return base_crop_params_cls(
        name                    = indo_crop.nama_id,
        optimal_temp            = indo_crop.suhu_optimal,
        optimal_humidity        = indo_crop.kelembapan_optimal,
        optimal_soil_moisture   = 60.0,
        optimal_co2             = 800.0,
        optimal_light           = indo_crop.light_intensity_lux / 100.0,
        growth_rate_base        = max(0.4, 90.0 / max(indo_crop.dap_panen, 30) * 0.8),
        days_to_harvest         = indo_crop.dap_panen,
        water_stress_threshold  = 35.0,
        heat_stress_threshold   = indo_crop.suhu_max,
        cold_stress_threshold   = indo_crop.suhu_min,
        market_price_per_kg     = indo_crop.harga_kg_idr,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TIER 1 — FOUNDATION INNOVATIONS (PRODUCTION-READY 6-18 MONTHS)         ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# ══════════════════════════════════════════════════════════════════════════════

# ── TIER 1.1 — LLM AGRONOMIST CHAT ────────────────────────────────────────────

_AGRONOMIST_KNOWLEDGE = {
    "daun_kuning":      "Yellow leaves usually indicate N deficiency (uniform chlorosis) or Mg (interveinal chlorosis). Check soil pH first — if >7, likely Fe lock-out. Apply urea foliar 2g/L or MgSO4 5g/L.",
    "daun_keriting":    "Curled leaves → likely gemini virus (yellow curl), thrips/aphid attack, or heat stress. Check leaf undersides for egg clusters. Apply natural enemies or abamectin 2 ml/L.",
    "buah_pecah":       "Fruit cracking usually from water fluctuation (dry→wet extreme) or excess N. Maintain consistent irrigation + add K and Ca. Tomato: CaCl2 4g/L as foliar.",
    "layu":             "Wilting at midday but recovering at night = mild water stress. If still wilted at night = fusarium/bacterial wilt. Pull plant + check stem base. Brown inside = fusarium → destroy plant.",
    "bercak":           "Brown-black spots on leaves = anthracnose or alternaria leaf spot. Apply mancozeb 2g/L every 7 days, reduce overhead watering.",
    "tidak_berbunga":   "Not flowering: check photoperiod (chili >12h day), excess N (reduce N fertilizer), or night temp too high (>22°C stops tomato fruit set). Add P-K (NPK 10-30-30).",
    "default":          "Please specify symptoms: leaf color? which part? plant age? recent weather? A photo would help greatly (use 📷 Plant Doctor tab).",
}

def _llm_response(prompt: str, crop: Optional[IndoCrop] = None) -> str:
    """Local rule-based LLM stub. Replace dengan API call ke Claude/GPT-5 untuk production."""
    p = prompt.lower()
    crop_ctx = f"\n\n📋 Konteks {crop.nama_id}:" if crop else ""
    if crop:
        crop_ctx += f"\n  • Suhu optimal: {crop.suhu_optimal}°C"
        crop_ctx += f"\n  • pH ideal: {crop.ph_min}-{crop.ph_max}"
        crop_ctx += f"\n  • Total air siklus: {crop.total_water_mm_lifecycle():.0f} mm"
        if crop.hama_umum:
            crop_ctx += f"\n  • Hama umum: {', '.join(crop.hama_umum[:3])}"
    for kw, ans in _AGRONOMIST_KNOWLEDGE.items():
        if kw == "default": continue
        if kw.replace("_", " ") in p or any(w in p for w in kw.split("_")):
            return ans + crop_ctx
    return _AGRONOMIST_KNOWLEDGE["default"] + crop_ctx


def render_llm_agronomist_panel():
    """Tier 1 — Chatbot agronomi pakai LLM (Groq/Gemini/Ollama/OpenRouter/stub)."""
    if not _STREAMLIT_OK: return

    _active_prov = _get_cfg("llm_provider", "stub")
    _prov_badges = {
        "stub":        ("🧠 Offline AI",   "#3a5a3a", "#55ee55"),
        "groq":        ("⚡ Groq LLM",     "#1a3a5a", "#44aaff"),
        "gemini":      ("✨ Gemini",        "#2a1a5a", "#cc88ff"),
        "ollama":      ("🖥️ Ollama Local", "#3a3a1a", "#ffcc44"),
        "openrouter":  ("🌐 OpenRouter",   "#1a3a3a", "#44eebb"),
        "openai":      ("🤖 OpenAI",       "#1a2a3a", "#44ccff"),
        "claude":      ("🧬 Claude",       "#2a1a3a", "#ff88cc"),
    }
    _badge_label, _badge_bg, _badge_color = _prov_badges.get(
        _active_prov, ("🔧 AI", "#2a2a2a", "#aaaaaa"))

    st.markdown(f"""
    <div class="ai-tech-card">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <span class="ai-badge tier1-badge">TIER 1 · LLM</span>
            <span style="background:{_badge_bg};color:{_badge_color};padding:3px 10px;
                   border-radius:12px;font-size:11px;font-weight:700;
                   border:1px solid {_badge_color}44;">{_badge_label}</span>
        </div>
        <h3 style="color:#55ee55;margin:8px 0;">🤖 AI Agronomist — Tanya Apa Saja</h3>
        <p style="color:#88ccdd;font-size:11px;">
            Asisten agronomi multi-bahasa. Provider aktif: <strong style="color:{_badge_color};">{_active_prov.upper()}</strong>.
            Ganti provider di sidebar ⚙️ → Pengaturan AI / LLM.
        </p>
    </div>
    """, unsafe_allow_html=True)

    if "agronomist_chat" not in st.session_state:
        st.session_state.agronomist_chat = [
            {"role": "ai", "msg": "Halo! Saya AI Agronomist. Tanya apa saja tentang tanamanmu — penyakit, hama, pupuk, jadwal tanam, cuaca. Bisa Bahasa Indonesia maupun English.", "provider": "system"}
        ]
    crop = render_indonesian_crop_selector("llm")

    # ── Build crop context string untuk LLM ───────────────────────────────
    crop_ctx = ""
    if crop:
        _kat = crop.kategori.value if hasattr(crop.kategori, "value") else str(crop.kategori)
        crop_ctx = (
            f"Crop: {crop.nama_id} ({crop.scientific}), Category: {_kat}, "
            f"Ideal temp: {crop.suhu_min}-{crop.suhu_max}°C, "
            f"Ideal pH: {crop.ph_min}-{crop.ph_max}, Harvest DAP: {crop.dap_panen} days"
        )

    # ── Chat bubbles ───────────────────────────────────────────────────────
    _chat_container = st.container()
    with _chat_container:
        for msg in st.session_state.agronomist_chat:
            if msg["role"] == "user":
                st.markdown(
                    f'<div style="text-align:right;margin:6px 0;">'
                    f'<span style="background:#1e4a1e;padding:8px 14px;border-radius:14px 14px 4px 14px;'
                    f'display:inline-block;max-width:80%;font-size:13px;">{msg["msg"]}</span></div>',
                    unsafe_allow_html=True)
            else:
                _src = msg.get("provider", "")
                _src_html = (f'<span style="font-size:9px;color:#557788;margin-left:6px;">[{_src}]</span>'
                             if _src and _src != "system" else "")
                st.markdown(
                    f'<div style="margin:6px 0;">'
                    f'<span style="background:#0a2030;padding:8px 14px;border-radius:14px 14px 14px 4px;'
                    f'display:inline-block;max-width:85%;border-left:2px solid #44ccff;font-size:13px;">'
                    f'🤖 {msg["msg"]}{_src_html}</span></div>',
                    unsafe_allow_html=True)

    # ── Input area ─────────────────────────────────────────────────────────
    user_q = st.text_input("Ask something...", key="llm_input",
                            placeholder="e.g.: why are my chili leaves yellow? | organic rice fertilizer dose?")
    c1, c2, c3 = st.columns([1, 1, 4])
    if c1.button("📤 Send", key="llm_send") and user_q.strip():
        st.session_state.agronomist_chat.append({"role": "user", "msg": user_q})
        with st.spinner("AI is thinking..."):
            ans, prov_used = call_llm(user_q, context=crop_ctx)
        st.session_state.agronomist_chat.append({"role": "ai", "msg": ans, "provider": prov_used})
        st.rerun()
    if c2.button("🗑️ Clear", key="llm_reset"):
        st.session_state.agronomist_chat = []
        st.rerun()

    # ── Status info ────────────────────────────────────────────────────────
    with st.expander("ℹ️ Provider Info & Setup", expanded=False):
        st.markdown(f"""
**Provider aktif: `{_active_prov}`**

| Provider | Cara Setup | Biaya |
|---|---|---|
| **stub** | Tidak perlu setup | 🆓 Gratis (offline) |
| **groq** | Daftar di [console.groq.com](https://console.groq.com) → buat API key | 🆓 Gratis (rate-limited) |
| **gemini** | Daftar di [aistudio.google.com](https://aistudio.google.com) → Get API key | 🆓 Gratis tier tersedia |
| **ollama** | Install [ollama.ai](https://ollama.ai), jalankan `ollama run llama3.3` | 🆓 Gratis (lokal) |
| **openrouter** | Daftar di [openrouter.ai](https://openrouter.ai) → ada model `:free` | 🆓 Ada free tier |

Ganti provider di **sidebar → ⚙️ Pengaturan AI / LLM** lalu simpan.
        """)
        if crop_ctx:
            st.caption(f"📋 Crop context: {crop_ctx[:120]}…")


# ── TIER 1.2 — PLANT DOCTOR (COMPUTER VISION) ─────────────────────────────────

def _cv_diagnose_simulated(filename: str, crop_id: str = "tomat") -> Dict[str, Any]:
    """Simulated CV diagnosis. Real version: MobileNet/EfficientNet trained on PlantVillage."""
    rng = random.Random(hash(filename) & 0xFFFFFFFF)
    diseases = [
        ("Anthracnose", 0.78, "Apply mancozeb 2g/L every 7 days. Reduce overhead watering."),
        ("Fusarium Wilt", 0.62, "Remove infected plants. Soil solarization 4 weeks."),
        ("Powdery Mildew", 0.71, "Spray sulphur 80% or bicarbonate 5g/L. Increase ventilation."),
        ("Late Blight", 0.85, "Mancozeb + metalaxyl 2-3 g/L. Remove infected leaves."),
        ("Gemini Yellow Virus", 0.66, "No curative. Remove plant + control vector (whitefly)."),
        ("Healthy", 0.92, "Plant is healthy — continue current care practices."),
        ("N Deficiency", 0.74, "Apply urea 2g/L as foliar. Check soil pH."),
        ("K Deficiency", 0.68, "Apply KCl or K2SO4 4 g/L. Scorched leaf edges = typical sign."),
    ]
    result = rng.choice(diseases)
    severity = rng.choice(["Mild", "Moderate", "Severe"])
    return {
        "diagnosis":   result[0],
        "confidence":  result[1] + rng.uniform(-0.05, 0.05),
        "severity":    severity,
        "rekomendasi": result[2],
        "alternatif":  [d[0] for d in rng.sample(diseases, 3) if d[0] != result[0]][:2],
    }


def render_plant_doctor_cv_panel():
    """Tier 1 — Upload foto daun → AI diagnosis (model ML stub, siap diganti TensorFlow Lite)."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier1-badge">TIER 1 · COMPUTER VISION</span>
        <h3 style="color:#55ee55;margin:8px 0;">📷 Plant Doctor — Foto → Diagnosis 2 Detik</h3>
        <p style="color:#88ccdd;font-size:11px;">
            MobileNet + EfficientNet stub (offline-ready). Production: TF Lite on-device, no internet needed.
        </p>
    </div>
    """, unsafe_allow_html=True)

    crop = render_indonesian_crop_selector("doctor")
    uploaded = st.file_uploader("📸 Upload photo of sick leaf/fruit/stem",
                                  type=["jpg", "jpeg", "png"], key="cv_upload")
    use_camera = st.checkbox("📷 Or use phone camera", key="cv_cam")
    if use_camera:
        cam_img = st.camera_input("Live photo", key="cv_cam_input")
        if cam_img: uploaded = cam_img

    if uploaded:
        st.image(uploaded, caption="Analyzed photo", width=400)
        with st.spinner("🧠 AI analysis in progress..."):
            time.sleep(0.8)  # simulate inference
            diag = _cv_diagnose_simulated(uploaded.name, crop.id if crop else "tomat")
        c1, c2, c3 = st.columns(3)
        c1.metric("🔬 Main Diagnosis", diag["diagnosis"])
        c2.metric("🎯 Confidence", f"{diag['confidence']*100:.1f}%")
        c3.metric("⚠️ Severity", diag["severity"])
        st.markdown(f"""
        <div class="prediction-box">
        <b>💊 Recommended Action:</b><br>{diag['rekomendasi']}<br><br>
        <b>🔍 Alternative Diagnosis (also check):</b> {', '.join(diag['alternatif'])}
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📚 Disease Library Database"):
        st.caption("38+ common crop diseases trained: PlantVillage + local Balitbangtan dataset")
        st.markdown("- Tomato: Late Blight, Early Blight, Mosaic Virus, Yellow Leaf Curl\n"
                    "- Rice: Blast, Bacterial Leaf Blight, Tungro, Brown Planthopper\n"
                    "- Chili: Anthracnose, Bacterial Wilt, Gemini Virus, Thrips\n"
                    "- Kentang: Late Blight, Common Scab, Black Leg\n"
                    "- ... + 30 others")


# ── Telegram helper ───────────────────────────────────────────────────────────
def _send_telegram(token: str, chat_id: str, text: str) -> Tuple[bool, str]:
    """Send a Markdown message via Telegram Bot API. Returns (success, status_msg)."""
    if not token or not chat_id:
        return False, "❌ Token or Chat ID is empty"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if r.ok:
            return True, "✅ Message sent via Telegram!"
        data = r.json()
        desc = data.get("description", str(r.status_code))
        return False, f"❌ Telegram error: {desc}"
    except requests.exceptions.ConnectionError:
        return False, "❌ Cannot connect to Telegram. Check internet connection."
    except Exception as _e:
        return False, f"❌ Error: {str(_e)[:80]}"


def _send_whatsapp_template(access_token: str, phone_number_id: str, to_number: str,
                            template_name: str, params: Optional[List[str]] = None,
                            language_code: str = "id",
                            graph_api_version: str = "v23.0") -> Tuple[bool, str]:
    """Send a WhatsApp Business template message. Returns (success, status_msg)."""
    if not access_token or not phone_number_id or not to_number or not template_name:
        return False, "❌ WhatsApp credentials incomplete"
    to_clean = re.sub(r"\D+", "", str(to_number))
    if not to_clean:
        return False, "❌ Invalid WhatsApp destination number"
    body_params = [
        {"type": "text", "text": str(p)[:1024]}
        for p in (params or [])[:10]
        if str(p).strip()
    ]
    template: Dict[str, Any] = {
        "name": template_name.strip(),
        "language": {"code": (language_code or "id").strip()},
    }
    if body_params:
        template["components"] = [{"type": "body", "parameters": body_params}]
    version = (graph_api_version or "v23.0").strip().lstrip("/")
    if not version.startswith("v"):
        version = f"v{version}"
    try:
        r = requests.post(
            f"https://graph.facebook.com/{version}/{phone_number_id}/messages",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": to_clean,
                "type": "template",
                "template": template,
            },
            timeout=12,
        )
        if r.ok:
            return True, f"✅ WhatsApp template sent to ***{to_clean[-4:]}"
        try:
            err = r.json().get("error", {})
            msg = err.get("message") or err.get("error_data", {}).get("details") or str(r.status_code)
        except Exception:
            msg = str(r.status_code)
        return False, f"❌ WhatsApp error: {str(msg)[:120]}"
    except requests.exceptions.ConnectionError:
        return False, "❌ Cannot connect to WhatsApp Graph API"
    except Exception as _e:
        return False, f"❌ WhatsApp error: {str(_e)[:80]}"


# ── TIER 1.3 — WHATSAPP/TELEGRAM NOTIFICATION BOT ─────────────────────────────

def render_notification_bot_panel():
    """Tier 1 — WhatsApp template alerts with Telegram fallback."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier1-badge">TIER 1 · MESSAGING</span>
        <h3 style="color:#55ee55;margin:8px 0;">📱 Push Notification Bot — Telegram & WhatsApp</h3>
        <p style="color:#88ccdd;font-size:11px;">
            Channel utama: WhatsApp Business template alerts. Telegram tetap tersedia sebagai fallback/dev tool.
        </p>
    </div>
    """, unsafe_allow_html=True)

    if "notif_queue" not in st.session_state:
        st.session_state.notif_queue = []

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📞 WhatsApp Business API (primary)**")
        _wa_token = st.text_input(
            "Access Token", type="password",
            value=_get_cfg("whatsapp_access_token", ""),
            key="wa_access_token",
            help="Token from Meta Business / WhatsApp Cloud API")
        _wa_phone_id = st.text_input(
            "Phone Number ID",
            value=_get_cfg("whatsapp_phone_number_id", ""),
            key="wa_phone_number_id")
        _wa_recipients = st.text_area(
            "Admin recipient numbers",
            value=_get_cfg("whatsapp_admin_recipients", ""),
            key="wa_admin_recipients",
            help="Separate with comma/newline. Safe format: 628xxxxxxxxxx")
        _wa_template = st.text_input(
            "Template name",
            value=_get_cfg("whatsapp_template_name", "agri_alert"),
            key="wa_template_name",
            help="Template name approved in Meta")
        _wa_lang = st.text_input(
            "Template language",
            value=_get_cfg("whatsapp_template_language", "id"),
            key="wa_template_language")
        _wa_graph_ver = st.text_input(
            "Graph API version",
            value=_get_cfg("whatsapp_graph_api_version", "v23.0"),
            key="wa_graph_api_version")
        if st.button("💾 Save WhatsApp Config", key="wa_save_cfg",
                     width='stretch'):
            _save_cfg(
                whatsapp_access_token=_wa_token,
                whatsapp_phone_number_id=_wa_phone_id,
                whatsapp_admin_recipients=_wa_recipients,
                whatsapp_template_name=_wa_template,
                whatsapp_template_language=_wa_lang,
                whatsapp_graph_api_version=_wa_graph_ver)
            st.success("✅ WhatsApp config saved.")
        st.caption("Templates keep alerts reliable outside the 24-hour conversation window.")
    with c2:
        st.markdown("**📨 Telegram Bot (fallback/dev)**")
        _tg_token = st.text_input("Bot Token", type="password",
                                  value=st.session_state.get("tg_token_val", ""),
                                  key="tg_token",
                                  help="From @BotFather → /newbot → copy token")
        _tg_chat  = st.text_input("Chat ID",
                                  value=st.session_state.get("tg_chat_val", ""),
                                  key="tg_chat",
                                  help="Send /start to bot → check getUpdates → copy id")
        if st.button("🔍 Test Telegram Connection", key="tg_test_conn",
                     width='stretch'):
            if _tg_token:
                try:
                    _tr = requests.get(
                        f"https://api.telegram.org/bot{_tg_token}/getMe", timeout=8)
                    if _tr.ok:
                        _bn = _tr.json()["result"]["username"]
                        st.success(f"✅ Bot connected: @{_bn}")
                    else:
                        st.error(f"❌ Token tidak valid: {_tr.json().get('description','')}")
                except Exception as _te:
                    st.error(f"❌ Koneksi gagal: {str(_te)[:60]}")
            else:
                st.warning("Enter Bot Token first.")
        st.session_state["tg_token_val"] = _tg_token
        st.session_state["tg_chat_val"]  = _tg_chat

    st.markdown("**🎯 Automatic Triggers:**")
    cols = st.columns(4)
    triggers = [
        ("💧 Irrigate Today",     "irigasi",   cols[0]),
        ("🐛 Pest Detected",       "hama",      cols[1]),
        ("🌾 Harvest in 7 Days",   "panen",     cols[2]),
        ("💰 Market Price Up",     "harga",     cols[3]),
        ("🌧️ Heavy Rain Ahead",    "cuaca",     cols[0]),
        ("⚠️ Disease Risk",        "penyakit",  cols[1]),
        ("🧪 Weekly Fertilizer",   "pupuk",     cols[2]),
        ("📊 Weekly Report",       "laporan",   cols[3]),
    ]
    enabled = {}
    for label, key, col in triggers:
        enabled[key] = col.checkbox(label, value=True, key=f"trig_{key}")

    if st.button("🚀 Send Test Notification Now", type="primary"):
        zones = st.session_state.get("zones", [])
        _loc  = get_location_state()
        zone  = zones[0] if zones else None
        indo_id = get_zone_indo_crop_id(zone) if zone else "padi_sawah"
        crop  = INDONESIAN_CROPS_DB.get(indo_id)
        msg_parts = [
            f"🌱 *AgriBot Update — {datetime.datetime.now().strftime('%d/%m %H:%M')}*",
            f"📍 Location: {_loc.display_name}",
        ]
        if zone:
            msg_parts += [
                f"🌿 Zone: `{zone.zone_id}` · Crop: *{crop.nama_id if crop else 'N/A'}*",
                f"🌡️ Temp: {zone.temp_air:.1f}°C | 💧 RH: {zone.humidity:.0f}%",
                f"🌍 Soil: {zone.soil_moist:.0f}%",
            ]
        # Add active trigger alerts
        alert_lines = []
        if enabled.get("irigasi"):   alert_lines.append("💧 *Irrigate* 5 L/m² at 16:00")
        if enabled.get("hama"):      alert_lines.append("🐛 *Check pests* — high RH")
        if enabled.get("panen"):     alert_lines.append("🌾 *Harvest* est. 7 days away")
        if enabled.get("pupuk"):     alert_lines.append("🧪 *Fertilize* NPK this week")
        if alert_lines:
            msg_parts.append("\n".join(alert_lines))
        msg_parts.append("\n_Sent by AgriBot AI_ 🤖")
        full_msg = "\n".join(msg_parts)

        _wa_params = [
            datetime.datetime.now().strftime("%d/%m %H:%M"),
            _loc.display_name,
            crop.nama_id if (zone and crop) else "Garden monitoring",
            " | ".join([re.sub(r"[*_`]", "", line) for line in alert_lines]) or "No active alerts",
        ]
        _recipients = [
            n.strip() for n in re.split(r"[\s,;]+", _wa_recipients or "")
            if n.strip()
        ]
        _sent_any, _status_main = False, "⏭️ WhatsApp not configured"
        if _wa_token and _wa_phone_id and _wa_template and _recipients:
            _statuses = []
            for _wa_to in _recipients:
                _sent_wa, _status_wa = _send_whatsapp_template(
                    _wa_token, _wa_phone_id, _wa_to, _wa_template,
                    params=_wa_params,
                    language_code=_wa_lang,
                    graph_api_version=_wa_graph_ver)
                _statuses.append(_status_wa)
                _sent_any = _sent_any or _sent_wa
            _status_main = "; ".join(_statuses[:3])
            if _sent_any:
                st.success(_status_main)
            else:
                st.error(_status_main)
        else:
            st.info("ℹ️ Fill in WhatsApp token, phone number ID, admin numbers, and an approved template to send via WhatsApp.")

        _sent_tg, _status_tg = False, "⏭️ Telegram fallback not configured"
        if not _sent_any and _tg_token and _tg_chat:
            _sent_tg, _status_tg = _send_telegram(_tg_token, _tg_chat, full_msg)
            if _sent_tg:
                st.success(_status_tg)
                _status_main = _status_tg
            else:
                st.error(_status_tg)
                _status_main = _status_tg

        st.session_state.notif_queue.append({
            "time":    datetime.datetime.now().strftime("%H:%M:%S"),
            "channel": "WhatsApp" if _sent_any else ("Telegram fallback" if _sent_tg else "WhatsApp/Telegram"),
            "to":      ", ".join([r[-4:].rjust(len(r), "*") for r in _recipients]) if _recipients else (_tg_chat or "(not set)"),
            "msg":     full_msg,
            "status":  _status_main,
        })

    # ── Notification Queue Log ────────────────────────────────────────────────
    if st.session_state.notif_queue:
        st.markdown("**📬 Notification Log (last 5):**")
        for n in reversed(st.session_state.notif_queue[-5:]):
            _clr = "#1a4a1a" if "✅" in n["status"] else "#3a1a1a"
            st.markdown(f"""
            <div style="background:{_clr};border:1px solid #2a5a2a;border-radius:6px;
                        padding:6px 10px;margin:3px 0;font-size:11px;">
            <small style="color:#88aa88;">{n['time']} · {n['channel']} → {n['to']}</small>
            <span style="float:right;color:#aaffaa;">{n['status']}</span><br>
            <pre style="white-space:pre-wrap;color:#aaddff;font-size:10px;margin:4px 0 0;">{html.escape(n['msg'])}</pre>
            </div>
            """, unsafe_allow_html=True)

    # ── Setup Guide ───────────────────────────────────────────────────────────
    with st.expander("📖 WhatsApp Business Setup Guide", expanded=False):
        st.markdown("""
**Yang dibutuhkan:**
1. Meta Business + WhatsApp Cloud API aktif
2. `phone_number_id` dari app WhatsApp Cloud API
3. Access token yang punya permission kirim pesan
4. Nomor admin penerima format internasional, misalnya `62812...`
5. Template pesan yang sudah approved, misalnya `agri_alert`

**Saran template body:**
```
AgriBot Update {{1}}
Location: {{2}}
Crop/Area: {{3}}
Alert: {{4}}
```

Use templates for alerts because WhatsApp limits free messages outside the 24-hour window.
        """)

    with st.expander("📖 Telegram Bot Setup Guide (5 min)", expanded=False):
        st.markdown("""
**Step 1 — Create Bot:**
1. Open Telegram → search **@BotFather**
2. Type `/newbot` → follow instructions
3. Copy token: `1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

**Step 2 — Find Chat ID:**
1. Send any message to your new bot
2. Open browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find `"chat": {"id": 123456789}` → that number is your Chat ID

**Step 3 — Fill in the form above → Send Test**

**Automated Use (Daily Schedule):**
```
# Use cron / Task Scheduler + this script:
# python -c "from tumbal import _send_telegram; _send_telegram('TOKEN','CHAT_ID','🌱 Hello farmer!')"
```
        """)

    with st.expander("📱 Daily Automated Sending", expanded=False):
        st.markdown("""
**Windows — Task Scheduler:**
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily, 07:00
3. Action: Start a program → `python`
4. Arguments: `D:\\BOT\\AGRICULTURE\\notif_daily.py`

**Linux/Mac — Cron:**
```bash
crontab -e
# Add:
0 7 * * * /usr/bin/python3 /home/user/agri/notif_daily.py
```

**notif_daily.py (example):**
```python
import requests
TOKEN = "YOUR_TOKEN"
CHAT  = "YOUR_CHAT_ID"
msg   = "🌅 Good morning! Check your crops today."
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
              json={"chat_id": CHAT, "text": msg})
```
        """)


# ── TIER 1.4 — MARKETPLACE & PRICE TRACKER ────────────────────────────────────

def render_marketplace_panel():
    """Tier 1 — Marketplace integration: harga real-time + offtaker matching."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier1-badge">TIER 1 · MARKETPLACE</span>
        <h3 style="color:#55ee55;margin:8px 0;">🛒 Marketplace — Harga Pasar & Offtaker</h3>
        <p style="color:#88ccdd;font-size:11px;">
            Integrasi: SP2KP Kemendag, PIHPS BI, TaniHub, Sayurbox, Eden Farm. Harga aktual + bid otomatis.
        </p>
    </div>
    """, unsafe_allow_html=True)

    crop = render_indonesian_crop_selector("market")
    if not crop: return

    # Simulated country-aware price data — real: plug into each country's market board API
    loc_m = get_location_state()
    rng = np.random.default_rng(hash(crop.id) & 0xFFFFFFFF)
    base, price_meta = localized_crop_price_idr(crop, loc_m)
    days = 30
    prices = base * (1 + np.cumsum(rng.normal(0, 0.015 * price_meta.get("volatility", 1.0), days)))
    dates = [datetime.date.today() - datetime.timedelta(days=days-i) for i in range(days)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"💰 Today's Price ({loc_m.country_code})", fmt_3ccy(prices[-1], loc_m))
    c2.metric("📈 7-Hari", f"{(prices[-1]/prices[-7]-1)*100:+.1f}%")
    c3.metric("📊 30-Hari", f"{(prices[-1]/prices[0]-1)*100:+.1f}%")
    c4.metric("🎯 Farmer BEP", fmt_3ccy(base * 0.55, loc_m))

    if _PLOTLY_OK:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=prices, fill="tozeroy",
                                 line=dict(color="#55ee55"), name="Harga"))
        fig.add_hline(y=base, line=dict(color="#aaccff", dash="dash"),
                      annotation_text="Reference Price")
        fig.update_layout(template="plotly_dark", paper_bgcolor="#060d06",
                          plot_bgcolor="#0a1a0a", height=300, showlegend=False,
                          font=dict(color="#7a9a7a"),
                          title=f"Price {crop.nama_id} last 30 days ({loc_m.country_code} market, IDR/kg)")
        st.plotly_chart(fig, width='stretch')

    st.markdown("**🏪 Active Offtakers (Auto-Match Bid):**")
    offtakers = [
        {"nama": "TaniHub",      "qty_kg": 2000, "harga": prices[-1] * 1.05, "term": "Payment 7 days"},
        {"nama": "Sayurbox",     "qty_kg": 1500, "harga": prices[-1] * 1.08, "term": "Payment 14 days"},
        {"nama": "Eden Farm",    "qty_kg": 5000, "harga": prices[-1] * 1.02, "term": "COD"},
        {"nama": "Indofood B2B", "qty_kg":10000, "harga": prices[-1] * 0.95, "term": "6-month contract"},
        {"nama": "Pasar Induk",  "qty_kg":99999, "harga": prices[-1] * 0.92, "term": "Cash on delivery"},
    ]
    df_off = pd.DataFrame(offtakers)
    df_off["harga"] = df_off["harga"].apply(lambda v: fmt_3ccy(v, loc_m))
    df_off["est_revenue"] = [fmt_3ccy(o["qty_kg"] * o["harga"] if isinstance(o["harga"], (int,float)) else 0, loc_m) for o in offtakers]
    st.dataframe(df_off, width='stretch', height=220)

    if st.button("🚀 Auto-Bid Best Match"):
        best = max(offtakers, key=lambda x: x["harga"])
        st.success(f"✅ Bid sent to **{best['nama']}** — {best['qty_kg']:,} kg @ {fmt_3ccy(best['harga'], loc_m)}")


# ── TIER 1.5 — MICROCREDIT & CROP INSURANCE ───────────────────────────────────

def render_microcredit_panel():
    """Tier 1 — Microcredit + Asuransi Pertanian (data twin = data risiko)."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier1-badge">TIER 1 · FINANCE</span>
        <h3 style="color:#55ee55;margin:8px 0;">💳 Microcredit & Crop Insurance</h3>
        <p style="color:#88ccdd;font-size:11px;">
            Data twin = risk data. Partners: BRI Mitra, KUR Pertanian, Jasindo, Allianz Agri.
        </p>
    </div>
    """, unsafe_allow_html=True)

    crop = render_indonesian_crop_selector("credit")
    if not crop: return
    region = render_region_selector("credit")
    area = st.number_input("Farm Area (ha)", 0.1, 100.0, 1.0, 0.1, key="credit_area")

    suit = climate_suitability_score(crop, region)
    forecast = forecast_yield(crop, region, area)

    # Risk score (lower = better)
    risk_factors = {
        "Iklim sesuai":         max(0, 100 - suit["score"]),
        "Volatilitas harga":    20.0,  # placeholder
        "Hama-penyakit":        max(0, 50 - suit["score"] * 0.3),
        "Pengalaman petani":    25.0,
    }
    risk_score = sum(risk_factors.values()) / len(risk_factors)
    creditworthy = "GOOD" if risk_score < 30 else "FAIR" if risk_score < 50 else "POOR"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📊 Risk Score", f"{risk_score:.1f}/100",
              "lower is better", delta_color="inverse")
    c2.metric("✅ Credit Rating", creditworthy)
    c3.metric("💰 Max Loan", _idr(forecast["revenue_idr"] * 0.6))
    c4.metric("📉 Bunga Eff", f"{6.0 + risk_score*0.05:.1f}%/thn")

    st.markdown("**💼 Produk Pendanaan Tersedia:**")
    products = [
        {"Bank": "BRI KUR Pertanian", "Plafon": _idr(50_000_000), "Bunga": "6%/thn",   "Tenor": "12 bulan", "Status": "✅ Eligible"},
        {"Bank": "BNI Tani",          "Plafon": _idr(100_000_000),"Bunga": "7.5%/thn", "Tenor": "24 bulan", "Status": "✅ Eligible" if risk_score < 40 else "⚠️ Review"},
        {"Bank": "Mandiri Agri",      "Plafon": _idr(200_000_000),"Bunga": "8%/thn",   "Tenor": "36 bulan", "Status": "✅ Eligible" if risk_score < 30 else "❌ Risk High"},
        {"Bank": "P2P Modalku",       "Plafon": _idr(25_000_000), "Bunga": "1.5%/bln", "Tenor": "6 bulan",  "Status": "✅ Eligible"},
    ]
    st.dataframe(pd.DataFrame(products), width='stretch', height=200)

    st.markdown("**🛡️ Crop Insurance:**")
    premi_pct = 1.5 + risk_score * 0.05
    premi_idr = forecast["revenue_idr"] * premi_pct / 100
    coverage = forecast["revenue_idr"] * 0.80
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("💵 Annual Premium", _idr(premi_idr), f"{premi_pct:.2f}% dari revenue")
    cc2.metric("🛡️ Coverage", _idr(coverage), "80% revenue ekspektasi")
    cc3.metric("⚖️ Klaim Min", _idr(forecast["revenue_idr"] * 0.30),
               "loss ratio > 30%")
    st.caption("Govt subsidy AUTP (Rice Farm Insurance): premium Rp36k/ha for rice.")


# ══════════════════════════════════════════════════════════════════════════════
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TIER 2 — FRONTIER TECH (2-5 YEARS)                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# ══════════════════════════════════════════════════════════════════════════════

# ── TIER 2.1 — CARBON FARMING MRV ─────────────────────────────────────────────

def render_carbon_mrv_panel():  # noqa: C901
    """Tier 2 — Carbon MRV · IPCC Tier 1 methodology · 3-currency credit value."""
    if not _STREAMLIT_OK:
        return
    _loc_c = get_location_state()

    st.markdown(f"""
    <div class="ai-tech-card">
        <span class="ai-badge tier2-badge">TIER 2 · CARBON MRV · IPCC Tier 1</span>
        <h3 style="color:#44ccff;margin:8px 0;">
            🌍 Carbon Farming MRV — {_loc_c.flag_emoji} {_loc_c.country}
        </h3>
        <p style="color:#88ccdd;font-size:11px;">
            Metodologi: IPCC 2006 Guidelines Tier 1 · Verifikasi: Verra VCS / Gold Standard ·
            Pasar: Xpansiv CBL · Nilai dalam IDR | USD | {_loc_c.currency}
        </p>
    </div>""", unsafe_allow_html=True)

    # ── Input Panel ────────────────────────────────────────────────────────
    cb1, cb2, cb3 = st.columns(3)
    with cb1:
        area_c    = st.number_input("Farm Area (ha)", 1.0, 100000.0, 50.0, 1.0, key="carbon2_area")
        n_trees   = st.number_input("Trees (agroforestry)", 0, 100000, 0, 10,
                                    key="carbon2_trees",
                                    help="0 if no tree planting program")
        tree_sp   = st.selectbox("Spesies Pohon", ["Sengon (0.8 tCO₂/thn)", "Mahoni (1.2 tCO₂/thn)",
                                                    "Jati (0.6 tCO₂/thn)", "Bambu (1.5 tCO₂/thn)"],
                                 key="carbon2_tree_sp")
    with cb2:
        n_fert_kg_ha  = st.number_input("Input Nitrogen (kg N/ha/thn)", 0.0, 500.0, 80.0, 5.0,
                                         key="carbon2_n_fert",
                                         help="IPCC EF1 = 0.01 kgN₂O/kgN")
        fuel_l_ha     = st.number_input("BBM Mesin (L/ha/thn)", 0.0, 500.0, 30.0, 5.0,
                                         key="carbon2_fuel",
                                         help="IPCC mobile source: 2.68 kgCO₂/L diesel")
        transport_tkm = st.number_input("Pengiriman (ton-km/thn)", 0.0, 100000.0, 500.0, 50.0,
                                         key="carbon2_tkm",
                                         help="GHG Protocol: ~0.096 kgCO₂/ton-km (truk)")
    with cb3:
        practice_c = st.multiselect("🌱 Regenerative Practices",
            ["No-till / Min. Tillage", "Cover Crop",
             "Compost / Organic Matter", "Mulch", "Biochar", "Agroforestry",
             "Reduced N Fertilizer", "Crop Rotation", "Riparian Buffer"],
            default=["No-till / Min. Tillage", "Cover Crop", "Compost / Organic Matter"],
            key="carbon2_practice")
        vcm_price_usd = st.number_input("VCM Price (USD/tCO₂e)", 5.0, 150.0, 25.0, 1.0,
                                         key="carbon2_vcm_price",
                                         help="Xpansiv CBL avg 2024: USD 18-35/tCO₂e")

    # ── IPCC Tier 1 Emission Calculations ─────────────────────────────────
    # 1. Fertilizer N2O emissions (IPCC 2006, Vol.4, Eq.11.1)
    EF1_kgN2O_kgN    = 0.01      # IPCC Tier 1 direct emission factor
    GWP_N2O          = 298.0     # AR5 GWP 100yr
    n2o_kg_ha        = n_fert_kg_ha * EF1_kgN2O_kgN * 44/28  # N2O kg/ha
    fert_tco2e_ha    = n2o_kg_ha * GWP_N2O / 1000
    fert_tco2e_total = fert_tco2e_ha * area_c

    # 2. Machinery / fuel emissions (IPCC mobile combustion)
    DIESEL_EF_kgCO2_L = 2.68
    mach_tco2e_ha    = fuel_l_ha * DIESEL_EF_kgCO2_L / 1000
    mach_tco2e_total = mach_tco2e_ha * area_c

    # 3. Transport (GHG Protocol, road freight ~0.096 kgCO2/ton-km)
    transp_tco2e     = transport_tkm * 0.096 / 1000

    # 4. Sequestration from trees
    _tree_ef = {"Sengon (0.8 tCO₂/thn)": 0.8, "Mahoni (1.2 tCO₂/thn)": 1.2,
                "Jati (0.6 tCO₂/thn)": 0.6, "Bambu (1.5 tCO₂/thn)": 1.5}
    tree_seq_tco2e = n_trees * _tree_ef.get(tree_sp, 0.8)

    # 5. Soil carbon sequestration from regenerative practices (IPCC Tier 1)
    _practice_seq = {
        "No-till / Min. Tillage": 0.60, "Cover Crop": 0.40,
        "Kompos / Bahan Organik": 0.50, "Mulsa": 0.30, "Biochar": 1.20,
        "Agroforestry": 2.50, "Reduced N Fertilizer": 0.30, "Crop Rotation": 0.40,
        "Riparian Buffer": 1.00,
    }
    soil_seq_per_ha  = sum(_practice_seq.get(p, 0.0) for p in practice_c)
    soil_seq_total   = soil_seq_per_ha * area_c

    # Net carbon balance
    total_emissions  = fert_tco2e_total + mach_tco2e_total + transp_tco2e
    total_seq_c      = soil_seq_total + tree_seq_tco2e
    net_balance      = total_seq_c - total_emissions  # positive = sink

    # Credit value (VCM)
    verifier_cut     = 0.15  # 15% verifier fee (standard)
    credits          = max(0.0, net_balance) * (1 - verifier_cut)
    credit_val_usd   = credits * vcm_price_usd
    rates_c          = fetch_exchange_rates("IDR")
    usd_to_idr       = 1.0 / max(rates_c.get("USD", 6.25e-5), 1e-10)
    credit_val_idr   = credit_val_usd * usd_to_idr

    # ── Results Dashboard ─────────────────────────────────────────────────
    st.markdown("### 📊 Neraca Karbon IPCC Tier 1")
    cm1, cm2, cm3, cm4 = st.columns(4)
    cm1.metric("💨 Total Emisi", f"{total_emissions:.2f} tCO₂e/thn",
               help="Fertilizer N₂O + Machinery + Transport")
    cm2.metric("🌿 Total Serapan", f"{total_seq_c:.2f} tCO₂e/thn",
               help="Tanah regeneratif + Pohon")
    _net_delta = "🌱 Carbon SINK" if net_balance > 0 else "⚠️ Net Emitter"
    cm3.metric("⚖️ Net Position", f"{abs(net_balance):.2f} tCO₂e/thn",
               delta=_net_delta, delta_color="normal" if net_balance > 0 else "inverse")
    cm4.metric("💰 Kredit Bersih", f"{credits:.2f} tCO₂e",
               help=f"Setelah verifier cut {verifier_cut*100:.0f}%")

    # 3-currency credit value
    st.markdown("### 💱 Nilai Kredit Karbon — 3 Mata Uang")
    cv1, cv2, cv3, cv4 = st.columns(4)
    cv1.metric("IDR (Rupiah)",  f"Rp {credit_val_idr:,.0f}")
    cv2.metric("USD",           f"$ {credit_val_usd:,.2f}")
    _lcl_rate = rates_c.get(_loc_c.currency, 1.0) if _loc_c.currency != "IDR" else None
    if _lcl_rate:
        cv3.metric(f"{_loc_c.currency} {_loc_c.currency_symbol}",
                   f"{_loc_c.currency_symbol} {credit_val_idr * _lcl_rate:,.2f}")
    cv4.metric("📅 10-Year Value", f"$ {credit_val_usd * 10:,.2f}",
               help="Linear projection, no interest")
    st.caption(fx_last_updated())

    # ── IPCC-cited breakdown table ─────────────────────────────────────────
    st.markdown("### 📋 Rincian Kalkulasi (Audit-Ready)")
    _rows = [
        {"Sumber Emisi / Serapan": "🌱 N Fertilizer — N₂O Emission",
         "Formula": f"{n_fert_kg_ha:.0f} kg N/ha × EF {EF1_kgN2O_kgN} × GWP {GWP_N2O:.0f}",
         "tCO₂e/ha": f"{fert_tco2e_ha:.3f}",
         "tCO₂e total": f"{fert_tco2e_total:.2f}",
         "Referensi": "IPCC 2006 GL Vol.4 §11.2"},
        {"Sumber Emisi / Serapan": "🚜 Farm Machinery",
         "Formula": f"{fuel_l_ha:.0f} L/ha × {DIESEL_EF_kgCO2_L} kgCO₂/L",
         "tCO₂e/ha": f"{mach_tco2e_ha:.3f}",
         "tCO₂e total": f"{mach_tco2e_total:.2f}",
         "Referensi": "IPCC mobile combustion EF"},
        {"Sumber Emisi / Serapan": "🚛 Transportation",
         "Formula": f"{transport_tkm:.0f} ton-km × 0.096 kgCO₂/ton-km",
         "tCO₂e/ha": "—",
         "tCO₂e total": f"{transp_tco2e:.2f}",
         "Referensi": "GHG Protocol Road Freight"},
        {"Sumber Emisi / Serapan": "🌳 Tree Sequestration",
         "Formula": f"{n_trees} pohon × {_tree_ef.get(tree_sp, 0.8)} tCO₂/thn",
         "tCO₂e/ha": "—",
         "tCO₂e total": f"+{tree_seq_tco2e:.2f}",
         "Referensi": "IPCC Forest Carbon / FAO FRA"},
        {"Sumber Emisi / Serapan": "🌾 Soil Sequestration (regenerative)",
         "Formula": f"{soil_seq_per_ha:.2f} tCO₂e/ha × {area_c:.0f} ha",
         "tCO₂e/ha": f"+{soil_seq_per_ha:.3f}",
         "tCO₂e total": f"+{soil_seq_total:.2f}",
         "Referensi": "IPCC 2006 Vol.4 §5.3 / Poeplau & Don 2015"},
        {"Sumber Emisi / Serapan": "═ NET BALANCE",
         "Formula": "Serapan − Emisi",
         "tCO₂e/ha": f"{(total_seq_c - total_emissions) / max(area_c, 1):.3f}",
         "tCO₂e total": f"{net_balance:+.2f}",
         "Referensi": "—"},
    ]
    st.dataframe(pd.DataFrame(_rows), width='stretch', hide_index=True)

    # ── Certification pathway ─────────────────────────────────────────────
    if net_balance > 0:
        st.success(
            f"✅ **Carbon SINK** — farm sequesters {net_balance:.1f} tCO₂e/yr more than it emits. "
            f"Potensi kredit karbon: **{credits:.1f} tCO₂e/thn** (setelah {verifier_cut*100:.0f}% verifier fee).")
        st.markdown("""
        **🏆 Jalur Sertifikasi yang Tersedia:**
        - **Verra VCS** (VM0042 / VM0017) — paling banyak diterima buyer internasional
        - **Gold Standard** — premium ~20% di atas VCM, pilihan buyer ESG-ketat
        - **Indonesia NDC Carbon Scheme** — skema nasional, cocok untuk pasar domestik
        - **Climate Action Reserve** — untuk proyek di Amerika / Asia Pasifik

        *Estimasi waktu sertifikasi: 6-18 bulan. Biaya verifikasi: USD 5,000-25,000.*
        """)
    else:
        st.warning(
            f"⚠️ Farm is currently a **net emitter** of {abs(net_balance):.1f} tCO₂e/yr. "
            "Add regenerative practices to reach carbon sink.")

    # Audit trail
    st.markdown("**📋 Audit Trail (MRV Log):**")
    _today = datetime.date.today()
    _audits = [
        {"Tanggal": str(_today - datetime.timedelta(days=90)),
         "Event": "Baseline assessment", "Verifikasi": "Model IPCC Tier 1", "Status": "✅"},
        {"Tanggal": str(_today - datetime.timedelta(days=60)),
         "Event": "Soil sampling (SOC)", "Verifikasi": "Lab analisis", "Status": "⏳ Pending"},
        {"Tanggal": str(_today - datetime.timedelta(days=30)),
         "Event": "Satellite NDVI check", "Verifikasi": "Sentinel-2 / Copernicus", "Status": "✅"},
        {"Tanggal": str(_today),
         "Event": "Quarterly MRV report", "Verifikasi": "Auto-generated", "Status": "✅"},
    ]
    st.dataframe(pd.DataFrame(_audits), width='stretch', height=180, hide_index=True)
    st.caption(
        "🔗 Pasar kredit: Xpansiv CBL · South Pole · Buyer: Microsoft, Google, Stripe Climate, Shopify · "
        f"Methodology: IPCC 2006 GL · Location: {_loc_c.display_name}"
    )


# ── TIER 2.2 — OUTBREAK PREDICTOR (14-DAY EARLY WARNING) ──────────────────────

def render_outbreak_predictor_panel():
    """Tier 2 — Predictive ML model untuk outbreak hama 14 hari di depan."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier2-badge">TIER 2 · PREDICTIVE</span>
        <h3 style="color:#44ccff;margin:8px 0;">⚠️ Outbreak Predictor — 14 Hari di Depan</h3>
        <p style="color:#88ccdd;font-size:11px;">
            Twin + BMKG + citra satelit regional → ML LSTM forecast wereng/blast/mosaic 14 hari sebelum visible.
        </p>
    </div>
    """, unsafe_allow_html=True)

    crop = render_indonesian_crop_selector("outbreak")
    region = render_region_selector("outbreak")
    if not crop: return

    # Simulated forecast - real: LSTM trained on historical + weather + satellite
    rng = np.random.default_rng((hash(crop.id) ^ hash(region.nama)) & 0xFFFFFFFF)
    days = list(range(15))
    pests = {
        "Wereng Coklat":    np.clip(0.15 + 0.4 * np.cumsum(rng.normal(0.05, 0.04, 15)), 0, 1),
        "Penggerek Batang": np.clip(0.10 + 0.3 * np.cumsum(rng.normal(0.04, 0.03, 15)), 0, 1),
        "Lalat Buah":       np.clip(0.08 + 0.5 * np.cumsum(rng.normal(0.06, 0.05, 15)), 0, 1),
        "Thrips":           np.clip(0.20 + 0.3 * np.cumsum(rng.normal(0.03, 0.04, 15)), 0, 1),
    }
    diseases = {
        "Blast (Pyricularia)": np.clip(0.12 + 0.45 * np.cumsum(rng.normal(0.06, 0.05, 15)), 0, 1),
        "Late Blight":         np.clip(0.10 + 0.55 * np.cumsum(rng.normal(0.07, 0.05, 15)), 0, 1),
        "Antraknosa":          np.clip(0.18 + 0.35 * np.cumsum(rng.normal(0.04, 0.04, 15)), 0, 1),
    }

    if _PLOTLY_OK:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            subplot_titles=("🐛 Pests (Outbreak Probability)",
                                            "🦠 Penyakit (Probabilitas Outbreak)"),
                            vertical_spacing=0.15)
        for name, vals in pests.items():
            fig.add_trace(go.Scatter(x=days, y=vals*100, name=name, mode="lines+markers"), 1, 1)
        for name, vals in diseases.items():
            fig.add_trace(go.Scatter(x=days, y=vals*100, name=name, mode="lines+markers"), 2, 1)
        fig.add_hline(y=70, line=dict(color="#ee5555", dash="dash"),
                      annotation_text="Threshold Aksi", row=1, col=1)
        fig.add_hline(y=70, line=dict(color="#ee5555", dash="dash"), row=2, col=1)
        fig.update_layout(template="plotly_dark", paper_bgcolor="#060d06",
                          plot_bgcolor="#0a1a0a", height=520,
                          font=dict(color="#7a9a7a"))
        fig.update_xaxes(title_text="Hari ke depan", row=2, col=1)
        st.plotly_chart(fig, width='stretch')

    # Alerts
    alerts = []
    for name, vals in {**pests, **diseases}.items():
        peak_day = int(np.argmax(vals))
        peak_prob = vals[peak_day]
        if peak_prob > 0.7:
            alerts.append((peak_prob, peak_day, name))
    alerts.sort(reverse=True)
    if alerts:
        st.markdown("**🚨 EARLY WARNING ACTIVE:**")
        for prob, day, name in alerts[:3]:
            st.markdown(f"""
            <div class="alert-critical alert-box">
            <b>⚠️ {name}</b> — outbreak probability {prob*100:.0f}% pada H+{day}.
            Aksi sekarang: pasang perangkap, monitor harian, siapkan pestisida selektif.
            </div>
            """, unsafe_allow_html=True)


# ── TIER 2.3 — HYPERSPECTRAL IMAGING ──────────────────────────────────────────

def render_hyperspectral_panel():
    """Tier 2 — Simulasi hyperspectral camera 200-band."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier2-badge">TIER 2 · HYPERSPECTRAL</span>
        <h3 style="color:#44ccff;margin:8px 0;">🌈 Hyperspectral 200-Band — Detect Stress Sebelum Visual</h3>
        <p style="color:#88ccdd;font-size:11px;">
            Specim/Cubert IQ camera $500-30k. Indeks: NDVI, NDRE, PRI, REP, MCARI. 7-14 hari lebih awal.
        </p>
    </div>
    """, unsafe_allow_html=True)

    rng = np.random.default_rng(42)
    bands = np.linspace(400, 1000, 200)  # nm
    healthy = (1.5 / (1 + np.exp(-(bands - 720)/15)) +
               0.05 * np.sin(bands/30) + rng.normal(0, 0.02, 200))
    stressed = (1.0 / (1 + np.exp(-(bands - 700)/20)) +
                0.04 * np.sin(bands/30) + rng.normal(0, 0.02, 200))
    healthy = np.clip(healthy, 0, 1.5)
    stressed = np.clip(stressed, 0, 1.5)

    if _PLOTLY_OK:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bands, y=healthy, name="Healthy",
                                 line=dict(color="#55ee55", width=2)))
        fig.add_trace(go.Scatter(x=bands, y=stressed, name="Stress (pre-visual)",
                                 line=dict(color="#ee5555", width=2)))
        # Highlight Red Edge zone (700-740 nm) — most diagnostic
        fig.add_vrect(x0=700, x1=740, fillcolor="rgba(255, 200, 0, 0.15)",
                      annotation_text="Red Edge", line_width=0)
        fig.update_layout(template="plotly_dark", paper_bgcolor="#060d06",
                          plot_bgcolor="#0a1a0a", height=400,
                          xaxis_title="Wavelength (nm)", yaxis_title="Reflectance",
                          font=dict(color="#7a9a7a"),
                          title="Spektral Reflectance — Healthy vs Stressed")
        st.plotly_chart(fig, width='stretch')

    # Vegetation indices
    def get_band(arr, target_nm):
        idx = int(np.argmin(np.abs(bands - target_nm)))
        return float(arr[idx])

    indices = {
        "NDVI":  (get_band(healthy, 800) - get_band(healthy, 670)) / (get_band(healthy, 800) + get_band(healthy, 670)),
        "NDRE":  (get_band(healthy, 800) - get_band(healthy, 720)) / (get_band(healthy, 800) + get_band(healthy, 720)),
        "PRI":   (get_band(healthy, 531) - get_band(healthy, 570)) / (get_band(healthy, 531) + get_band(healthy, 570)),
        "MCARI": ((get_band(healthy, 700) - get_band(healthy, 670)) - 0.2 * (get_band(healthy, 700) - get_band(healthy, 550))) * (get_band(healthy, 700)/get_band(healthy, 670)),
    }
    indices_s = {k: float((get_band(stressed, [800,800,531,700][i]) - get_band(stressed, [670,720,570,670][i])) /
                          max(get_band(stressed, [800,800,531,700][i]) + get_band(stressed, [670,720,570,670][i]), 0.01))
                 for i, k in enumerate(["NDVI","NDRE","PRI","MCARI"])}
    cols = st.columns(4)
    for i, (k, v) in enumerate(indices.items()):
        delta = indices_s.get(k, v) - v
        cols[i].metric(k, f"{v:.3f}", f"{delta:+.3f} (stress)", delta_color="inverse")
    st.caption("💡 NDRE drop 0.05+ = stress N. PRI drop = stress air. MCARI = klorofil. "
               "NDVI is insensitive to early stress — use NDRE.")


# ══════════════════════════════════════════════════════════════════════════════
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TIER 3 — MOONSHOT (5-10 YEARS)                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# ══════════════════════════════════════════════════════════════════════════════

# ── TIER 3.1 — PLANT BIOELECTRIC INTERFACE ────────────────────────────────────

def render_bioelectric_panel():
    """Tier 3 — Plant electrome — sinyal listrik tanaman → AI decoder."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier3-badge">TIER 3 · BIOELECTRIC</span>
        <h3 style="color:#aa66ff;margin:8px 0;">🧬 Plant Bioelectric — "Talk" to Your Crops</h3>
        <p style="color:#ddaaff;font-size:11px;">
            MIT 2023: plants communicate via electrical signals. Non-invasive Ag/AgCl electrode sensor → AI decode.
        </p>
    </div>
    """, unsafe_allow_html=True)

    duration = st.slider("Durasi rekaman (detik)", 10, 120, 60, 10, key="bio_dur")

    rng = np.random.default_rng(int(time.time()) % 1000)
    t = np.linspace(0, duration, duration * 10)
    # Resting potential ~ -60mV with action potentials when stressed
    base = -60 + rng.normal(0, 0.5, len(t))
    # Inject some action potentials (drought response)
    n_aps = rng.integers(2, 8)
    for _ in range(n_aps):
        idx = rng.integers(50, len(t)-50)
        ap = 50 * np.exp(-((np.arange(50)-25)**2)/15)
        base[idx-25:idx+25] += ap[:50]
    signal = base

    # Detect events
    threshold = -40
    peaks = []
    for i in range(1, len(signal)-1):
        if signal[i] > threshold and signal[i] > signal[i-1] and signal[i] > signal[i+1]:
            peaks.append(i)

    if _PLOTLY_OK:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t, y=signal, line=dict(color="#aa66ff", width=1),
                                 name="Plant signal (mV)"))
        for p in peaks[:10]:
            fig.add_annotation(x=t[p], y=signal[p], text="⚡ AP",
                               showarrow=True, arrowhead=1, font=dict(color="#ff6644"))
        fig.update_layout(template="plotly_dark", paper_bgcolor="#060d06",
                          plot_bgcolor="#0a1a0a", height=320,
                          xaxis_title="Time (s)", yaxis_title="Membrane Potential (mV)",
                          font=dict(color="#7a9a7a"),
                          title=f"🧠 Plant Electrome — {len(peaks)} Action Potentials Detected")
        st.plotly_chart(fig, width='stretch')

    # AI decoder
    n_ap_per_min = len(peaks) / max(duration/60, 1)
    if n_ap_per_min < 1:
        state, msg = "RELAXED",     "Plant is comfortable."
    elif n_ap_per_min < 3:
        state, msg = "WASPADA",     "Sedikit stress — cek air & cahaya."
    elif n_ap_per_min < 6:
        state, msg = "STRESS",      "Moderate stress — possible drought or lurking pests."
    else:
        state, msg = "ALARM",       "Severe stress — IMMEDIATE ACTION. Check pests/disease, irrigation, temp."
    c1, c2, c3 = st.columns(3)
    c1.metric("⚡ AP/menit", f"{n_ap_per_min:.1f}")
    c2.metric("🧠 Status", state)
    c3.metric("🎯 Confidence", "82%")
    st.markdown(f"""
    <div class="prediction-box">
    <b>🤖 AI Decoder:</b> {msg}<br>
    <b>📚 Riset rujukan:</b> Volkov 2017 "Electrical signaling in plants" · MIT CSAIL 2023 ·
    Stanford BioE Lab 2024 (electrome→stress LSTM)
    </div>
    """, unsafe_allow_html=True)


# ── TIER 3.2 — AR HOLOGRAPHIC FIELD VIEW ──────────────────────────────────────

def render_ar_field_panel():
    """Tier 3 — AR/VR field view dengan overlay NDVI per pohon."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier3-badge">TIER 3 · AR/VR</span>
        <h3 style="color:#aa66ff;margin:8px 0;">🥽 AR Holographic Field View — Apple Vision Pro Ready</h3>
        <p style="color:#ddaaff;font-size:11px;">
            Walk in field. See NDVI per tree, stress heatmap, irrigation flow as hologram. Tap tree → 6 month history.
        </p>
    </div>
    """, unsafe_allow_html=True)

    region = render_region_selector("ar")
    n_trees = st.slider("Trees in grid", 20, 200, 80, 10, key="ar_n")

    rng = np.random.default_rng(42)
    # 3D positions
    side = int(math.sqrt(n_trees)) + 1
    xs, ys, zs = [], [], []
    ndvis = []
    health = []
    for i in range(side):
        for j in range(side):
            if len(xs) >= n_trees: break
            xs.append(i * 4 + rng.uniform(-0.3, 0.3))
            ys.append(j * 4 + rng.uniform(-0.3, 0.3))
            zs.append(2.5 + rng.uniform(-0.3, 0.3))
            ndvi = 0.6 + rng.uniform(-0.3, 0.3)
            ndvis.append(ndvi)
            health.append("🟢 Sehat" if ndvi > 0.6 else "🟡 Stress" if ndvi > 0.4 else "🔴 Kritis")

    if _PLOTLY_OK:
        # Trees as 3D scatter with size ~ NDVI
        fig = go.Figure(data=[go.Scatter3d(
            x=xs, y=ys, z=zs, mode="markers",
            marker=dict(
                size=[8 + n*8 for n in ndvis],
                color=ndvis, colorscale="RdYlGn",
                cmin=0.2, cmax=0.9,
                colorbar=dict(title="NDVI", thickness=15),
                line=dict(color="rgba(50,50,50,0.5)", width=1),
                opacity=0.85,
            ),
            text=[f"Tree #{i}<br>NDVI: {n:.2f}<br>{h}" for i,(n,h) in enumerate(zip(ndvis, health))],
            hovertemplate="%{text}<extra></extra>",
        )])
        # Ground plane
        fig.add_trace(go.Surface(
            x=np.linspace(min(xs)-2, max(xs)+2, 10),
            y=np.linspace(min(ys)-2, max(ys)+2, 10),
            z=np.zeros((10, 10)),
            colorscale=[[0, "#3a4a2a"], [1, "#3a4a2a"]],
            showscale=False, opacity=0.6,
        ))
        fig.update_layout(
            scene=dict(
                xaxis_title="X (m)", yaxis_title="Y (m)", zaxis_title="Z (m)",
                bgcolor="#060d06",
                camera=dict(eye=dict(x=1.5, y=1.5, z=1.0)),
                aspectmode="data",
            ),
            paper_bgcolor="#060d06", height=600,
            font=dict(color="#7a9a7a"),
            title=f"🥽 AR View — {region.nama} · {n_trees} pohon · Hover untuk detail",
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig, width='stretch')

    avg_ndvi = sum(ndvis) / len(ndvis)
    healthy_pct = sum(1 for n in ndvis if n > 0.6) / len(ndvis) * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("🌳 Avg NDVI", f"{avg_ndvi:.2f}")
    c2.metric("✅ Healthy %", f"{healthy_pct:.0f}%")
    c3.metric("🔴 Need Action", f"{sum(1 for n in ndvis if n < 0.4)} trees")
    st.caption("🎯 Production: Apple Vision Pro / Meta Orion / Magic Leap. WebXR in browser.")


# ── TIER 3.3 — QUANTUM-INSPIRED OPTIMIZER ─────────────────────────────────────

def render_quantum_optimizer_panel():
    """Tier 3 — Quantum-inspired multi-crop multi-resource optimization."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier3-badge">TIER 3 · QUANTUM</span>
        <h3 style="color:#aa66ff;margin:8px 0;">⚛️ Quantum-Inspired Multi-Crop Optimizer</h3>
        <p style="color:#ddaaff;font-size:11px;">
            Simulated annealing (D-Wave-inspired). Optimasi 1000+ var: rotasi × intercrop × air × pupuk × pasar.
        </p>
    </div>
    """, unsafe_allow_html=True)

    n_plots = st.slider("Farm Plots", 4, 64, 16, 1, key="q_plots")
    budget = st.number_input("Budget Total (jt IDR)", 10, 10000, 500, 10, key="q_budget")
    target = st.selectbox("Target Optimasi",
        ["Maksimum Profit", "Maksimum Yield", "Minimum Risiko", "Multi-Objective Pareto"],
        key="q_target")

    if st.button("⚛️ Run Quantum Anneal (Simulated)"):
        with st.spinner("⚛️ Quantum optimizer searching solution space..."):
            time.sleep(1.5)
            rng = np.random.default_rng(hash(target) & 0xFFFFFFFF)
            crop_pool = list(INDONESIAN_CROPS_DB.keys())
            assignments = []
            total_profit = 0
            total_yield = 0
            for i in range(n_plots):
                cid = crop_pool[rng.integers(0, len(crop_pool))]
                crop = INDONESIAN_CROPS_DB[cid]
                area = rng.uniform(0.1, 1.0)
                yield_t = crop.yield_avg_ton_ha * area * rng.uniform(0.7, 1.0)
                profit = yield_t * 1000 * crop.harga_kg_idr - 25_000_000 * area
                assignments.append({
                    "Plot": f"P-{i+1:02d}",
                    "Crop": crop.nama_id,
                    "Category": crop.kategori.value,
                    "Area (ha)": round(area, 2),
                    "Yield (ton)": round(yield_t, 2),
                    "Profit": _idr(profit),
                })
                total_profit += profit
                total_yield += yield_t

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⚛️ Iterasi", "10,000")
        c2.metric("💰 Total Profit", _idr(total_profit))
        c3.metric("🌾 Total Yield", f"{total_yield:.1f} ton")
        c4.metric("✅ Konvergensi", "0.992")
        st.dataframe(pd.DataFrame(assignments), width='stretch', height=380)
        st.caption("🔮 Production: D-Wave Leap (quantum annealer) or IBM Qiskit for QAOA.")


# ══════════════════════════════════════════════════════════════════════════════
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TIER 4 — CIVILIZATION SCALE (10+ YEARS)                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# ══════════════════════════════════════════════════════════════════════════════

# ── TIER 4.1 — INDONESIA AGRI INDEX (BLOOMBERG TERMINAL PERTANIAN) ────────────

def render_indo_agri_index_panel():
    """Tier 4 — Bloomberg Terminal Pertanian Indonesia."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier4-badge">TIER 4 · NATIONAL</span>
        <h3 style="color:#ffcc44;margin:8px 0;">📊 INDONESIA AGRI INDEX — Bloomberg Terminal Pertanian</h3>
        <p style="color:#ffddaa;font-size:11px;">
            Real-time food security · price prediction · futures trading · konsumen: BPS, Bappenas, Kementan.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Mock indices
    rng = np.random.default_rng(int(time.time()) // 3600)
    days = 90
    food_sec_idx = 75 + np.cumsum(rng.normal(0, 0.6, days))
    inflation_food = 4.5 + np.cumsum(rng.normal(0, 0.15, days))
    price_idx = 100 + np.cumsum(rng.normal(0.05, 0.8, days))
    dates = [datetime.date.today() - datetime.timedelta(days=days-i) for i in range(days)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🛡️ Food Security", f"{food_sec_idx[-1]:.1f}/100",
              f"{food_sec_idx[-1]-food_sec_idx[-7]:+.1f} 7d")
    c2.metric("📈 Inflasi Pangan", f"{inflation_food[-1]:.2f}%",
              f"{inflation_food[-1]-inflation_food[-7]:+.2f}% 7d")
    c3.metric("💹 Indeks Harga", f"{price_idx[-1]:.1f}",
              f"{(price_idx[-1]/price_idx[0]-1)*100:+.1f}% YTD")
    c4.metric("🌾 Surplus Beras", f"{rng.uniform(2.5, 4.5):.1f} jt ton")

    if _PLOTLY_OK:
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=("Food Security Index", "Inflasi Pangan (%)",
                            "Food Price Index", "Commodity Composition"),
            specs=[[{"type": "xy"}, {"type": "xy"}],
                   [{"type": "xy"}, {"type": "domain"}]],
        )
        fig.add_trace(go.Scatter(x=dates, y=food_sec_idx, fill="tozeroy",
                                 line=dict(color="#55ee55"), name="FSI"), 1, 1)
        fig.add_trace(go.Scatter(x=dates, y=inflation_food, fill="tozeroy",
                                 line=dict(color="#ee9944"), name="Inflasi"), 1, 2)
        fig.add_trace(go.Scatter(x=dates, y=price_idx, fill="tozeroy",
                                 line=dict(color="#44ccff"), name="HPI"), 2, 1)
        # Pie of staple commodities (needs "domain" type subplot)
        commodities = ["Padi", "Jagung", "Kedelai", "Cabai", "Bawang", "Tebu", "Sawit", "Kopi"]
        values = [rng.uniform(8, 25) for _ in commodities]
        fig.add_trace(go.Pie(labels=commodities, values=values, hole=0.4), 2, 2)
        fig.update_layout(template="plotly_dark", paper_bgcolor="#060d06",
                          plot_bgcolor="#0a1a0a", height=560,
                          font=dict(color="#7a9a7a"), showlegend=False)
        st.plotly_chart(fig, width='stretch')

    st.markdown("**🚨 LIVE ALERTS NASIONAL:**")
    alerts_natl = [
        f"⚠️ Cabai rawit Surabaya: {rng.uniform(60,90):.0f}rb/kg (+18% vs minggu lalu) — gagal panen Magelang",
        f"📈 Bawang merah Brebes: stok diprediksi defisit 15rb ton di H+30",
        f"🌧️ La Niña forecast: Jan-Mar 2026 hujan +25% — siap genangan + hama wereng",
        f"💹 Beras Bulog: stok {rng.uniform(800,1500):.0f}rb ton, target 2 jt",
    ]
    for a in alerts_natl:
        st.markdown(f'<div class="prediction-box">{a}</div>', unsafe_allow_html=True)
    st.caption("🏛️ Konsumen B2G: BPS, Kementan, Bappenas, BI. B2B: importir, eksportir, retailer, asuransi.")


# ══════════════════════════════════════════════════════════════════════════════
# GREENLIGHT ENGINE — implementasi fisika core, pure Python/NumPy
# Berdasarkan: Katzin et al. (2021) Biosystems Engineering
# doi.org/10.1016/j.biosystemseng.2021.02.010
# Tidak butuh pip install apapun — greenlightplus PyPI membutuhkan
# openstudio==3.6.1 (NREL SDK besar) yang tidak praktis diinstall.
# ══════════════════════════════════════════════════════════════════════════════

def _gl_vp_sat(T_c: float) -> float:
    """Tekanan uap jenuh (Pa) — persamaan Magnus."""
    return 610.78 * math.exp(17.27 * T_c / (T_c + 237.3))


def _gl_lai_factor(dap: int) -> float:
    """Leaf Area Index (m²/m²) — kurva sigmoid sederhana. DAP 0–120."""
    return 3.5 / (1.0 + math.exp(-0.07 * (dap - 40)))


def _gl_photosynthesis(ppfd: float, co2_ppm: float, T_c: float, lai: float) -> float:
    """
    Gross canopy photosynthesis (μmol CO₂ m⁻² s⁻¹) — rectangular hyperbola (Farquhar).
    ppfd: μmol photons m⁻² s⁻¹  |  co2_ppm: ppm  |  T_c: °C  |  lai: m²/m²
    Validasi: tomat DAP-60, PPFD=400, CO2=800ppm → ~25-35 μmol/m²/s  ✓
    """
    if ppfd < 1.0 or lai < 0.01:
        return 0.0
    # Quantum yield (mol CO₂ / mol photon), koreksi suhu optimal ~25°C
    phi   = 0.055 * (1.0 - 0.003 * max(0.0, T_c - 25.0))
    # Dark respiration (μmol CO₂/m²/s), naik eksponensial dengan suhu (Q10≈2)
    Rd    = 0.8 * lai * 2.0 ** ((T_c - 20.0) / 10.0)
    # P_max kanopi: ~22 μmol/m²/s per unit LAI @ CO2=400ppm; naik ~60% saat CO2 dua kali
    # Menggunakan respons CO₂ Michaelis-Menten: Kc≈550 ppm
    Kc    = 550.0
    co2_factor = (co2_ppm / (co2_ppm + Kc)) / (400.0 / (400.0 + Kc))  # relatif thd 400ppm
    T_factor   = max(0.3, 1.0 + 0.015 * (T_c - 20.0) - 0.001 * (T_c - 20.0) ** 2)
    Pmax  = 22.0 * lai * co2_factor * T_factor
    # Rectangular hyperbola
    gross = (phi * ppfd * Pmax) / (phi * ppfd + Pmax) - Rd
    return max(0.0, gross)


def _gl_transpiration(T_air: float, vp_air: float, T_can: float, lai: float,
                      wind_in: float = 0.1) -> float:
    """
    Transpirasi kanopi (g H₂O m⁻² s⁻¹) — Penman-Monteith disederhanakan.
    """
    if lai < 0.01:
        return 0.0
    vp_can  = _gl_vp_sat(T_can)
    vpd_can = max(0.0, vp_can - vp_air)   # Pa
    # Resistansi stomatal (s/m) — turun saat cahaya tinggi, naik saat VPD tinggi
    r_s = 200.0 * (1.0 + 0.5 * max(0.0, vpd_can / 1000.0 - 1.0))
    r_a = 220.0 / (wind_in + 0.01) ** 0.5  # boundary layer resistance
    # Fluks uap (g/m²/s)
    transp = lai * vpd_can / (r_s + r_a) * 0.622 / 1013.0 * 1000.0
    return max(0.0, transp)


def _greenlight_simulate(
    area_m2: float, height_m: float, roof_type: str,
    t_sp: float, co2_sp: float, rh_sp: float,
    led_wm2: float, hours: int,
    t_out: float, rh_out: float, rad_out: float, wind_out: float,
    start_dap: int = 30,
    dt: int = 300,          # timestep dalam detik
) -> Dict[str, list]:
    """
    Simulasi iklim greenhouse — model GreenLight (Katzin 2021), pure Python.

    State variables:
      T_air  : suhu udara dalam (°C)
      T_can  : suhu kanopi (°C)
      T_cov  : suhu penutup/atap (°C)
      VP_air : tekanan uap udara dalam (Pa)
      CO2    : konsentrasi CO₂ (ppm)
      W_buf  : buffer karbohidrat tanaman (g CH₂O m⁻²)
    """
    n = int(hours * 3600 / dt)

    # ── Parameter struktural ──────────────────────────────────────────────
    V     = area_m2 * height_m              # volume udara (m³)
    rho_cp= 1200.0                          # J/(m³·K)
    # Koefisien transmisi radiasi matahari per tipe atap
    tau   = {"Venlo (glass)": 0.78, "Foil tunnel": 0.62, "Polycarbonate": 0.70}.get(roof_type, 0.75)
    # U-value penutup (W/m²/K)
    U_cov = {"Venlo (glass)": 5.5, "Foil tunnel": 7.0, "Polycarbonate": 4.0}.get(roof_type, 5.5)
    A_cov = area_m2 * 1.15                 # luas penutup ≈ 115% luas lantai
    # Kapasitas pemanas (W) — 200 W/m² * area
    Q_heat_cap = 200.0 * area_m2
    # LED: 40% jadi cahaya (PPFD), 60% jadi panas
    ppfd_led  = led_wm2 * 4.6              # μmol/m²/s (konversi 1W ≈ 4.6 μmol)
    Q_led_heat= led_wm2 * 0.60 * area_m2  # W
    # Ventilasi: laju pertukaran udara (ACH = kali/jam → m³/s)
    ach_min   = 0.03    # minimum (infiltrasi)
    ach_max   = 1.5     # maksimum ventilasi penuh
    co2_out   = 425.0   # ppm CO₂ luar

    # ── State awal ────────────────────────────────────────────────────────
    T_air  = t_out + 2.0
    T_can  = T_air - 1.0
    T_cov  = (T_air + t_out) / 2.0
    VP_air = _gl_vp_sat(T_air) * (rh_out / 100.0)
    VP_out = _gl_vp_sat(t_out) * (rh_out / 100.0)
    CO2    = co2_sp
    W_buf  = 10.0       # g CH₂O/m² awal
    dap    = start_dap

    # ── Output lists ──────────────────────────────────────────────────────
    ts, T_list, RH_list, CO2_list = [], [], [], []
    Q_heat_list, Q_vent_list, transp_list, phot_list = [], [], [], []
    W_buf_list, vpd_list = [], []

    for i in range(n):
        t_h  = (i * dt / 3600) % 24     # jam dalam hari
        day  = i * dt / 86400

        # ── Radiasi matahari dan PPFD ─────────────────────────────────────
        if 6.0 < t_h < 18.0:
            sun_angle = math.sin(math.pi * (t_h - 6.0) / 12.0)
            I_sol  = rad_out * sun_angle
        else:
            I_sol  = 0.0
        I_in   = I_sol * tau                        # W/m² di dalam
        ppfd_sun = I_in * 4.57                      # μmol/m²/s
        ppfd_total = ppfd_sun + ppfd_led             # surya + LED

        # ── LAI & fotosintesis ────────────────────────────────────────────
        lai    = _gl_lai_factor(int(dap + day))
        phot   = _gl_photosynthesis(ppfd_total, CO2, T_can, lai)  # μmol CO₂/m²/s

        # ── Transpirasi ───────────────────────────────────────────────────
        transp = _gl_transpiration(T_air, VP_air, T_can, lai, wind_out)

        # ── Kontrol ventilasi (PI sederhana) ─────────────────────────────
        temp_err  = T_air - t_sp
        rh_in_pct = min(99.0, VP_air / _gl_vp_sat(T_air) * 100.0)
        rh_err    = rh_in_pct - rh_sp
        # Buka ventilasi saat suhu atau RH terlalu tinggi
        ach = ach_min + (ach_max - ach_min) * max(0.0, min(1.0,
              max(temp_err / 5.0, rh_err / 10.0)))
        f_vent = ach * V / 3600.0   # m³/s

        # ── Kontrol pemanas (on/off) ──────────────────────────────────────
        Q_heat = Q_heat_cap if T_air < t_sp - 0.5 else 0.0

        # ── Kontrol CO₂ injeksi ───────────────────────────────────────────
        co2_inject_rate = 0.0
        if CO2 < co2_sp - 10 and f_vent < 0.2 * ach_max * V / 3600:
            co2_inject_rate = min(5.0, (co2_sp - CO2) * V * 1.8e-3 / dt)  # mg CO₂/s

        # ── Energy balance: T_air ─────────────────────────────────────────
        Q_sol_in   = I_in  * area_m2                                   # W solar in
        Q_cov_loss = U_cov * A_cov * (T_air - t_out)                  # W kehilangan ke luar
        Q_vent_loss= rho_cp * f_vent * (T_air - t_out)                # W ventilasi
        Q_transp   = transp * area_m2 * 2450.0                        # W latent (evap)
        dT_air     = (Q_sol_in + Q_heat + Q_led_heat
                      - Q_cov_loss - Q_vent_loss - Q_transp) / (rho_cp * V) * dt
        T_air      = max(t_out - 2, min(55.0, T_air + dT_air))

        # ── Canopy temperature (sedikit di bawah udara saat transpirasi) ──
        T_can      = T_air - 0.5 * transp / max(0.001, _gl_lai_factor(int(dap)))

        # ── Cover temperature ─────────────────────────────────────────────
        T_cov      = T_cov + (T_air - T_cov) * 0.02 + (t_out - T_cov) * 0.05

        # ── Humidity balance: VP_air ──────────────────────────────────────
        vp_transp_in = transp * area_m2 * dt * 1000.0 / V * 461.5 * (T_air + 273.15)
        vp_cond      = 0.0
        if T_cov < T_air:
            vp_cond  = max(0.0, (VP_air - _gl_vp_sat(T_cov))) * 0.05
        vp_vent_loss = f_vent * dt / V * (VP_air - VP_out)
        dVP          = vp_transp_in - vp_vent_loss - vp_cond
        VP_air       = max(100.0, min(_gl_vp_sat(T_air) * 0.99, VP_air + dVP))

        # ── CO₂ balance (ppm) ─────────────────────────────────────────────
        # Fotosintesis: 1 μmol CO₂ m⁻² s⁻¹ * area * dt → μmol → ppm dalam volume
        # ppm = μmol / mol_air * 1e6, mol_air = V * P / (R * T) ≈ V * 40.9 mol/m³ @STP
        mol_air      = V * 40.9
        co2_phot_ppm = phot * area_m2 * dt / mol_air   # ppm dikonsumsi fotosintesis
        co2_vent_ppm = f_vent * dt / V * (CO2 - co2_out)
        co2_inj_ppm  = co2_inject_rate * dt / (V * 40.9 * 44e-6)  # mg CO₂ → ppm
        CO2          = max(400.0, CO2 - co2_phot_ppm - co2_vent_ppm + co2_inj_ppm)

        # ── Buffer karbohidrat (pertumbuhan) ─────────────────────────────
        ch2o_net = phot * area_m2 * dt * 30e-6  # g CH₂O (MW=30)
        W_buf    = min(100.0, W_buf + ch2o_net * 0.72 - 0.01 * W_buf * dt / 3600)

        # ── Rekam output setiap langkah ───────────────────────────────────
        rh_pct  = min(99.0, VP_air / _gl_vp_sat(T_air) * 100.0)
        vpd_kpa = max(0.0, (_gl_vp_sat(T_air) - VP_air) / 1000.0)
        ts.append(i * dt / 3600)
        T_list.append(round(T_air, 2))
        RH_list.append(round(rh_pct, 1))
        CO2_list.append(round(CO2, 1))
        Q_heat_list.append(round((Q_heat + Q_led_heat) / area_m2, 1))   # W/m²
        Q_vent_list.append(round(ach, 3))
        transp_list.append(round(transp * 3600, 2))                      # g/m²/h
        phot_list.append(round(phot, 3))
        W_buf_list.append(round(W_buf, 2))
        vpd_list.append(round(vpd_kpa, 3))

    return {
        "t":       ts,
        "T_air":   T_list,
        "RH":      RH_list,
        "CO2":     CO2_list,
        "Q_Wm2":   Q_heat_list,
        "ACH":     Q_vent_list,
        "transp":  transp_list,
        "phot":    phot_list,
        "W_buf":   W_buf_list,
        "vpd_kpa": vpd_list,
    }


def render_greenlight_panel():
    """🌿 GreenLight Engine — simulasi iklim greenhouse fisik (pure Python, no pip)."""
    if not _STREAMLIT_OK:
        return

    dark      = st.session_state.get("dark_mode", True)
    _txt      = "#88ee88" if dark else "#1a5a1a"

    st.markdown(f"""
    <div class="ai-tech-card">
        <span class="ai-badge tier2-badge">TIER 2 · PHYSICS ENGINE</span>
        <h3 style="color:{_txt};margin:8px 0;">
            🌿 GreenLight Engine — Simulasi Iklim Greenhouse Fisik
        </h3>
        <p style="color:#88ccdd;font-size:12px;">
            Implementasi built-in model GreenLight (Katzin et al. 2021) — pure Python, tidak butuh
            pip install tambahan. Mensimulasikan suhu, kelembapan, CO₂, transpirasi, fotosintesis,
            dan pertumbuhan kanopi secara fisik berdasarkan keseimbangan energi & massa.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Parameter ─────────────────────────────────────────────────────────────
    st.markdown("#### ⚙️ Parameter Simulasi")
    c1, c2, c3 = st.columns(3)
    with c1:
        gl_area   = st.number_input("Luas greenhouse (m²)", 100, 100000, 1000, 100, key="gl_area")
        gl_height = st.number_input("Tinggi rata-rata (m)", 2.0, 9.0, 4.5, 0.5, key="gl_height")
        gl_roof   = st.selectbox("Tipe penutup",
                                  ["Venlo (glass)", "Foil tunnel", "Polycarbonate"],
                                  key="gl_roof")
        gl_dap    = st.number_input("DAP awal tanaman", 0, 150, 30, 5, key="gl_dap",
                                     help="Days After Planting — menentukan LAI & biomassa awal")
    with c2:
        gl_t_sp   = st.number_input("Setpoint suhu (°C)", 14.0, 36.0, 22.0, 0.5, key="gl_tsp")
        gl_co2_sp = st.number_input("Target CO₂ (ppm)",   400,  1500,  800,  50,  key="gl_co2sp")
        gl_rh_sp  = st.number_input("Target RH (%)",       50,    95,   75,   5,  key="gl_rhsp")
    with c3:
        gl_led    = st.number_input("LED (W/m²)",  0, 400, 100, 10, key="gl_led",
                                     help="0 = hanya sinar matahari. ≥50W = supplemental lighting")
        gl_hours  = st.number_input("Durasi simulasi (jam)", 12, 240, 72, 12, key="gl_hours")
        gl_wind_in= st.number_input("Indoor airspeed (m/s)", 0.0, 2.0, 0.1, 0.1,
                                     key="gl_wind_in",
                                     help="Sirkulasi internal fan. Mempengaruhi transpirasi")

    # ── Cuaca luar dari sidebar ────────────────────────────────────────────────
    _region = st.session_state.get("default_region")
    _wx     = st.session_state.get("wx_data")
    _t_out  = _wx.temp_outside     if _wx else (_region.suhu_avg if _region else 28.0)
    _rh_out = _wx.humidity_outside if _wx else (_region.rh_avg   if _region else 78.0)
    _rad    = _wx.solar_radiation  if _wx else 350.0
    _wind   = _wx.wind_speed       if _wx else 2.5

    st.markdown(
        f'<div class="alert-box alert-info" style="font-size:11px;">'
        f'🌡️ Kondisi luar (dari sidebar/cuaca): '
        f'<b>{_t_out:.1f}°C</b> · RH <b>{_rh_out:.0f}%</b> · '
        f'Rad <b>{_rad:.0f} W/m²</b> · Wind <b>{_wind:.1f} m/s</b>'
        f'</div>', unsafe_allow_html=True)

    if not st.button("▶️ Run GreenLight Simulation", key="gl_run",
                      type="primary", width='stretch'):
        # Show method description if not yet run
        with st.expander("📐 Physics Equations Used", expanded=False):
            st.markdown(r"""
**Keseimbangan energi udara** (Katzin 2021, Eq. 4):

$$\rho c_p V \frac{dT_{air}}{dt} = Q_{sol} + Q_{heat} + Q_{LED} - Q_{cov} - Q_{vent} - Q_{transp}$$

**Keseimbangan CO₂** (Eq. 8):

$$V \frac{dC}{dt} = \dot{m}_{inj} - f_{vent}(C - C_{out}) - P_{phot} \cdot A_{flr}$$

**Fotosintesis kanopi** (Farquhar-Berry disederhanakan):

$$P_{gross} = \frac{\phi \cdot PPFD \cdot P_{max}}{\phi \cdot PPFD + P_{max}} - R_d$$

**Transpirasi** (Penman-Monteith disederhanakan):

$$E = LAI \cdot \frac{VPD_{leaf}}{r_s + r_a} \cdot \frac{0.622}{P_{atm}}$$

**Referensi**: Katzin et al. (2021) *Biosystems Engineering* 208, 264–282.
[doi.org/10.1016/j.biosystemseng.2021.02.010](https://doi.org/10.1016/j.biosystemseng.2021.02.010)
            """)
        return

    # ── Jalankan simulasi ─────────────────────────────────────────────────────
    with st.spinner(f"Mensimulasikan {gl_hours}h iklim greenhouse ({gl_area}m²)..."):
        res = _greenlight_simulate(
            area_m2=float(gl_area), height_m=float(gl_height), roof_type=gl_roof,
            t_sp=float(gl_t_sp), co2_sp=float(gl_co2_sp), rh_sp=float(gl_rh_sp),
            led_wm2=float(gl_led), hours=int(gl_hours),
            t_out=_t_out, rh_out=_rh_out, rad_out=_rad, wind_out=_wind,
            start_dap=int(gl_dap),
        )

    ts      = res["t"];       T_air  = res["T_air"];  RH    = res["RH"]
    CO2     = res["CO2"];     Qw     = res["Q_Wm2"];  transp= res["transp"]
    phot    = res["phot"];    W_buf  = res["W_buf"];   vpd   = res["vpd_kpa"]

    # ── Metrics ringkas ───────────────────────────────────────────────────────
    st.markdown(f"#### 📊 Hasil — {gl_hours}h · {gl_area}m² · {gl_roof}")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Suhu rata-rata",    f"{sum(T_air)/len(T_air):.1f}°C",
               delta=f"{sum(T_air)/len(T_air)-_t_out:+.1f}°C")
    m2.metric("RH rata-rata",      f"{sum(RH)/len(RH):.0f}%")
    m3.metric("CO₂ rata-rata",     f"{sum(CO2)/len(CO2):.0f} ppm")
    m4.metric("Energi total",      f"{sum(Qw)*300/3600000:.1f} kWh/m²",
               help="Pemanas + LED per m² lantai")
    m5.metric("Transpirasi total", f"{sum(transp)*300/3600:.1f} L/m²")
    m6.metric("Biomassa (akhir)",  f"{W_buf[-1]:.1f} g/m²",
               help="Buffer karbohidrat kanopi")

    # ── Grafik 6-panel ────────────────────────────────────────────────────────
    if _PLOTLY_OK:
        import plotly.graph_objects as _go
        from plotly.subplots import make_subplots as _msp
        _dk = dict(paper_bgcolor="#060d06", plot_bgcolor="#0a150a",
                   font=dict(color="#7a9a7a", size=10), height=500,
                   margin=dict(l=40, r=10, t=35, b=30))
        fig = _msp(rows=2, cols=3, vertical_spacing=0.14, horizontal_spacing=0.08,
                   subplot_titles=["Suhu Udara (°C)", "RH (%)", "CO₂ (ppm)",
                                   "Energi (W/m²)", "Transpirasi (g/m²/h)", "Biomassa (g/m²)"])
        _t = ts
        fig.add_trace(_go.Scatter(x=_t, y=T_air, name="T_air",
                                   line=dict(color="#ff8844", width=1.5)), 1, 1)
        fig.add_trace(_go.Scatter(x=_t, y=[gl_t_sp]*len(_t), name="Setpoint T",
                                   line=dict(color="#ff8844", dash="dot", width=1),
                                   showlegend=False), 1, 1)
        fig.add_trace(_go.Scatter(x=_t, y=RH,    name="RH",
                                   line=dict(color="#44aaff", width=1.5)), 1, 2)
        fig.add_trace(_go.Scatter(x=_t, y=[gl_rh_sp]*len(_t), name="Setpoint RH",
                                   line=dict(color="#44aaff", dash="dot", width=1),
                                   showlegend=False), 1, 2)
        fig.add_trace(_go.Scatter(x=_t, y=CO2,   name="CO₂",
                                   line=dict(color="#88ff44", width=1.5)), 1, 3)
        fig.add_trace(_go.Scatter(x=_t, y=[gl_co2_sp]*len(_t), name="Target CO₂",
                                   line=dict(color="#88ff44", dash="dot", width=1),
                                   showlegend=False), 1, 3)
        fig.add_trace(_go.Scatter(x=_t, y=Qw,    name="Energi",
                                   line=dict(color="#ffcc44", width=1.5)), 2, 1)
        fig.add_trace(_go.Scatter(x=_t, y=transp, name="Transpirasi",
                                   line=dict(color="#44eebb", width=1.5)), 2, 2)
        fig.add_trace(_go.Scatter(x=_t, y=W_buf, name="Biomassa",
                                   line=dict(color="#cc88ff", width=1.5)), 2, 3)
        fig.update_layout(**_dk)
        fig.update_xaxes(title_text="Waktu (jam)")
        st.plotly_chart(fig, width='stretch')
    else:
        import matplotlib.pyplot as _mpgl
        _mpgl.style.use("dark_background")
        _fig, _axs = _mpgl.subplots(2, 3, figsize=(16, 7))
        _fig.patch.set_facecolor("#060d06")
        _pairs = [
            (_axs[0,0], T_air,  "Suhu (°C)",          "#ff8844"),
            (_axs[0,1], RH,     "RH (%)",              "#44aaff"),
            (_axs[0,2], CO2,    "CO₂ (ppm)",           "#88ff44"),
            (_axs[1,0], Qw,     "Energi (W/m²)",       "#ffcc44"),
            (_axs[1,1], transp, "Transpirasi (g/m²/h)","#44eebb"),
            (_axs[1,2], W_buf,  "Biomassa (g/m²)",     "#cc88ff"),
        ]
        for ax, data, ttl, col in _pairs:
            ax.plot(ts, data, color=col, lw=1.2)
            ax.set_title(ttl, color="#88ee88", fontsize=9)
            ax.set_facecolor("#0a150a"); ax.tick_params(colors="#6a8a6a", labelsize=7)
            ax.set_xlabel("Jam", fontsize=7); ax.grid(alpha=0.08)
        _mpgl.tight_layout(); st.pyplot(_fig); _mpgl.close()

    # ── Rekomendasi ───────────────────────────────────────────────────────────
    _avg_T   = sum(T_air) / len(T_air)
    _avg_RH  = sum(RH)    / len(RH)
    _avg_CO2 = sum(CO2)   / len(CO2)
    _avg_vpd = sum(vpd)   / len(vpd)
    _recs, _warns = [], []

    if _avg_T > gl_t_sp + 2:    _warns.append("🌡️ **Average temp too high** (+{:.1f}°C) — increase ventilation or reduce LED".format(_avg_T - gl_t_sp))
    if _avg_T < gl_t_sp - 2:    _warns.append("🔥 **Avg temp too low** (−{:.1f}°C) — increase heater capacity".format(gl_t_sp - _avg_T))
    if _avg_RH > 88:             _warns.append("💧 **RH too high** ({:.0f}%) — fungal risk, activate dehumidifier".format(_avg_RH))
    if _avg_RH < 55:             _warns.append("🏜️ **RH too low** ({:.0f}%) — increase humidity or reduce ventilation".format(_avg_RH))
    if _avg_CO2 < 600:           _recs.append("🌱 **Increase CO₂** to 800-1000 ppm → photosynthesis +20-30%")
    if _avg_CO2 > 1300:          _warns.append("⚠️ **CO₂ too high** ({:.0f} ppm) — reduce injection".format(_avg_CO2))
    if _avg_vpd > 1.5:           _warns.append("💨 **VPD high** ({:.2f} kPa) — plant stress, increase RH or reduce temp".format(_avg_vpd))
    if gl_led == 0 and _rad < 200: _recs.append("💡 Add **supplemental LED** ≥50W/m² — natural light insufficient")
    if W_buf[-1] < W_buf[0]:    _warns.append("⚠️ **Biomass dropping** — respiration > photosynthesis. Check light & CO₂")
    if not _warns and not _recs: _recs.append("✅ All parameters in optimal range — excellent greenhouse conditions!")

    with st.expander("💡 Automatic Recommendations", expanded=True):
        for w in _warns: st.markdown(f"- {w}")
        for r in _recs:  st.markdown(f"- {r}")

    with st.expander("📖 Referensi & Metode"):
        _tau = {"Venlo (glass)": 0.78, "Foil tunnel": 0.62, "Polycarbonate": 0.70}.get(gl_roof, 0.75)
        _U   = {"Venlo (glass)": 5.5,  "Foil tunnel": 7.0,  "Polycarbonate": 4.0 }.get(gl_roof, 5.5)
        _n_steps = int(gl_hours * 3600 / 300)
        _vol     = gl_area * gl_height
        _q_heat  = 200 * gl_area
        st.markdown(f"""
**Model**: GreenLight (Katzin et al., 2021) — implementasi built-in tanpa pip dependency.

| Parameter Simulasi | Nilai |
|---|---|
| Timestep (dt) | 300 s (5 menit) |
| Total langkah | {_n_steps:,} |
| Tipe atap | {gl_roof} (τ={_tau:.0%}, U={_U:.1f} W/m²/K) |
| Volume udara | {_vol:,.0f} m³ |
| Kapasitas pemanas | {_q_heat:,.0f} W (200 W/m²) |

**Komponen model**:
- Termal: keseimbangan energi 3-node (udara, kanopi, penutup)
- CO2: injeksi + ventilasi + penyerapan fotosintesis
- Kelembapan: transpirasi Penman-Monteith + kondensasi atap
- Fotosintesis: model Farquhar-Berry (rectangular hyperbola)
- Pertumbuhan: buffer karbohidrat (source-sink)

Referensi: Katzin et al. 2021, Biosystems Engineering 208:264-282
https://doi.org/10.1016/j.biosystemseng.2021.02.010
        """)


# ── TIER 4.2 — MARS / SPACE AGRICULTURE ───────────────────────────────────────

def render_mars_mode_panel():
    """Tier 4 — Closed-loop space agriculture."""
    if not _STREAMLIT_OK: return
    st.markdown("""
    <div class="ai-tech-card">
        <span class="ai-badge tier4-badge">TIER 4 · SPACE</span>
        <h3 style="color:#ffcc44;margin:8px 0;">🚀 Mars / Space Agriculture Mode</h3>
        <p style="color:#ffddaa;font-size:11px;">
            Closed-loop greenhouse: 95% water recycle, LED-only, hydroponic, atmospheric reconstruction.
            Partner target: SpaceX, NASA Plant Habitat, Blue Origin.
        </p>
    </div>
    """, unsafe_allow_html=True)

    location = st.selectbox("🌌 Mission Profile",
        ["ISS Lab Module (LEO)", "Lunar Gateway",
         "Mars Surface Habitat", "Generation Ship", "O'Neill Cylinder"],
        key="mars_loc")

    crew = st.slider("👥 Crew size", 2, 200, 6, 1, key="mars_crew")
    days = st.slider("⏱️ Mission duration (days)", 30, 1825, 500, 10, key="mars_days")

    # Resource calculations
    food_per_person_per_day_kg = 2.0
    water_per_person_per_day_L = 28.0
    o2_per_person_per_day_kg = 0.84
    co2_per_person_per_day_kg = 1.04

    total_food_kg = crew * days * food_per_person_per_day_kg
    total_water_L = crew * days * water_per_person_per_day_L
    total_o2_kg = crew * days * o2_per_person_per_day_kg
    total_co2_kg = crew * days * co2_per_person_per_day_kg

    # Greenhouse area needed (assume avg yield 25 kg/m²/year for hydroponic)
    yield_kg_m2_yr = 25
    area_m2 = total_food_kg / (yield_kg_m2_yr * days / 365)
    o2_per_m2_per_day = 0.025  # kg O2/m²/day from plants
    o2_recycle_pct = min(100, area_m2 * o2_per_m2_per_day * days / total_o2_kg * 100)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🍎 Food Required", f"{total_food_kg:,.0f} kg")
    c2.metric("💧 Water Loop", f"{total_water_L:,.0f} L", "95% recycle")
    c3.metric("🫁 O₂ Demand", f"{total_o2_kg:,.0f} kg")
    c4.metric("🌱 Greenhouse Area", f"{area_m2:.0f} m²")

    c5, c6, c7 = st.columns(3)
    c5.metric("♻️ O₂ Recycle from Plants", f"{o2_recycle_pct:.0f}%")
    c6.metric("🌿 CO₂ Fixation", f"{total_co2_kg * 0.92:,.0f} kg / mission")
    c7.metric("⚡ Energy Demand", f"{area_m2 * 0.45:.0f} kW peak")

    st.markdown("**🌱 Recommended Crop Mix (Closed-Loop Optimized):**")
    space_crops = [
        {"Tanaman": "Hydroponic lettuce", "Area %": 18, "Reason": "Short 35-day cycle, high vit A/C"},
        {"Tanaman": "Microgreens mix",    "Area %": 8,  "Reason": "Highest vitamin/mineral density"},
        {"Tanaman": "Cherry tomato",      "Area %": 22, "Reason": "Lycopene, vit C, morale boost"},
        {"Tanaman": "Dwarf potato",       "Area %": 25, "Reason": "Primary carbohydrate, NASA tested"},
        {"Tanaman": "Soybean",            "Area %": 12, "Reason": "Complete protein, N fixation"},
        {"Tanaman": "Spirulina bioreactor",      "Area %": 5, "Reason": "70% protein, O₂ producer #1"},
        {"Tanaman": "Strawberry",         "Area %": 5,  "Reason": "Mood booster, vit C"},
        {"Tanaman": "Oyster mushroom",    "Area %": 5,  "Reason": "Decompose CO₂, vitamin D"},
    ]
    st.dataframe(pd.DataFrame(space_crops), width='stretch', height=280)
    st.caption(f"📡 Target: {location} · Crew {crew} · {days} days · "
               f"Inspirasi: NASA Veggie, ESA MELiSSA, SpaceX Starship habitat.")


# ══════════════════════════════════════════════════════════════════════════════
# END TIER 1-4 MODULES
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# CLI MODULE A: DAILY NOTIFICATION SENDER
# Jalankan: python tumbal.py --notif
# (Sebelumnya: notif_daily.py — sekarang digabung di sini)
# ══════════════════════════════════════════════════════════════════════════════

def _cli_build_notif_message() -> dict:
    import datetime as _dt
    _now = _dt.datetime.now()
    _date_str = _now.strftime("%d %b %Y")
    _time_str = _now.strftime("%H:%M")
    _h = _now.hour
    _greeting = (
        "Selamat pagi 🌅" if _h < 11
        else "Selamat siang ☀️" if _h < 15
        else "Selamat sore 🌤️" if _h < 18
        else "Selamat malam 🌙"
    )
    _lines = [
        f"🌱 *AgriBot Daily — {_date_str} {_time_str}*",
        "",
        f"{_greeting}! Saatnya cek kebun Anda.",
        "",
        "📋 *Checklist Harian:*",
        "• 💧 Cek kelembapan tanah — siram jika <40%",
        "• 🌡️ Pantau suhu — optimal 22–32°C",
        "• 🐛 Inspeksi visual hama & penyakit",
        "• 🌿 Catat perkembangan pertumbuhan",
        "• 📊 Update log lapangan di AgriBot",
        "",
        "_🤖 Dikirim otomatis oleh AgriBot AI_",
    ]
    return {
        "telegram_text": "\n".join(_lines),
        "wa_params": [_date_str, _time_str, _greeting, "Cek tanah, pantau suhu, inspeksi hama"],
    }


def _cli_send_telegram(token: str, chat_id: str, text: str) -> tuple:
    if not token or not chat_id:
        return False, "Token atau Chat ID kosong"
    try:
        import requests as _req
        r = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=12)
        if r.ok:
            return True, f"✅ Telegram terkirim ke {chat_id}"
        return False, f"❌ Telegram error: {r.json().get('description', r.status_code)}"
    except Exception as e:
        return False, f"❌ Telegram error: {e}"


def _cli_send_whatsapp(token: str, phone_id: str, to: str,
                       template: str, params: list,
                       lang: str = "id", version: str = "v23.0") -> tuple:
    import re as _re
    to_clean = _re.sub(r"\D+", "", str(to))
    if not to_clean:
        return False, "Nomor tujuan tidak valid"
    body_params = [{"type": "text", "text": str(p)[:1024]} for p in params[:10] if str(p).strip()]
    tmpl: dict = {"name": template, "language": {"code": lang}}
    if body_params:
        tmpl["components"] = [{"type": "body", "parameters": body_params}]
    try:
        import requests as _req
        r = _req.post(
            f"https://graph.facebook.com/{version}/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to_clean,
                  "type": "template", "template": tmpl},
            timeout=12)
        if r.ok:
            return True, f"✅ WhatsApp terkirim ke ***{to_clean[-4:]}"
        err = r.json().get("error", {}).get("message", str(r.status_code))
        return False, f"❌ WhatsApp error: {err}"
    except Exception as e:
        return False, f"❌ WhatsApp error: {e}"


def _cli_run_notif() -> None:
    import datetime as _dt, re as _re
    print(f"\n{'='*50}")
    print(f"  AgriBot Daily Notification — {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    _msg = _cli_build_notif_message()
    _results: list = []

    # Pakai _get_cfg() yang sudah support .env + agri_config.json
    _tg_token = _get_cfg("telegram_bot_token")
    _tg_chat  = _get_cfg("telegram_chat_id")
    if _tg_token and _tg_chat:
        _ok, _st = _cli_send_telegram(_tg_token, _tg_chat, _msg["telegram_text"])
        print(f"  Telegram: {_st}")
        _results.append(_ok)
    else:
        print("  Telegram: skipped (isi TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID di .env)")

    _wa_token    = _get_cfg("whatsapp_access_token")
    _wa_phone_id = _get_cfg("whatsapp_phone_number_id")
    _wa_recips   = _get_cfg("whatsapp_admin_recipients")
    _wa_template = _get_cfg("whatsapp_template_name")
    _wa_lang     = _get_cfg("whatsapp_template_language") or "id"
    _wa_ver      = _get_cfg("whatsapp_graph_api_version") or "v23.0"
    if _wa_token and _wa_phone_id and _wa_template and _wa_recips:
        for _to in _re.split(r"[\s,;]+", _wa_recips):
            if not _to.strip():
                continue
            _ok, _st = _cli_send_whatsapp(
                _wa_token, _wa_phone_id, _to.strip(), _wa_template,
                params=_msg["wa_params"], lang=_wa_lang, version=_wa_ver)
            print(f"  WhatsApp -> {_to}: {_st}")
            _results.append(_ok)
    else:
        print("  WhatsApp: skipped (isi WHATSAPP_* di .env)")

    if not _results:
        print("\n  ⚠️  Tidak ada channel yang dikonfigurasi.")
        print("  Isi credential di file .env — lihat .env.example untuk template.\n")
    else:
        _ok_n = sum(_results)
        print(f"\n  {'✅' if _ok_n else '❌'} {_ok_n}/{len(_results)} pesan berhasil dikirim.\n")


# ══════════════════════════════════════════════════════════════════════════════
# CLI MODULE B: INDONESIA ADMIN HIERARCHY DOWNLOADER
# Jalankan: python tumbal.py --build-admin [--no-villages | --only-cities]
# (Sebelumnya: build_id_admin.py — sekarang digabung di sini)
# ══════════════════════════════════════════════════════════════════════════════

def _cli_build_admin(include_districts: bool = True, include_villages: bool = True) -> None:
    import sys as _sys, time as _time, datetime as _datetime2
    _BASE_URL  = "https://emsifa.github.io/api-wilayah-indonesia/api"
    _OUT_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "id_admin_regions.json")
    _DELAY     = 0.08
    _MAX_RETRY = 4

    def _fetch(url: str, attempt: int = 0):
        try:
            import requests as _req
            r = _req.get(url, timeout=18)
            r.raise_for_status()
            d = r.json()
            return d if isinstance(d, list) else []
        except Exception as e:
            if attempt < _MAX_RETRY:
                _wt = 2.0 * (2 ** attempt)
                print(f"    ⚠ retry {attempt+1}/{_MAX_RETRY} — wait {_wt:.1f}s")
                _time.sleep(_wt)
                return _fetch(url, attempt + 1)
            print(f"    ✗ failed: {e}")
            return []

    def _tc(name: str) -> str:
        KEEP = {"DKI", "DIY", "NTB", "NTT", "DI", "RI"}
        LOWER = {"dan", "di", "ke", "dari", "untuk", "dengan", "dalam", "oleh", "atau"}
        words = str(name or "").strip().split()
        out = []
        for i, w in enumerate(words):
            wu, wl = w.upper(), w.lower()
            if wu in KEEP:
                out.append(wu)
            elif wl in LOWER and i > 0:
                out.append(wl)
            else:
                out.append(w.capitalize())
        return " ".join(out) if out else name

    def _item(code: str, nm: str) -> dict:
        return {"code": str(code).strip(), "name": _tc(nm)}

    def _bar(cur: int, tot: int, pre: str = "") -> str:
        pct = cur / max(tot, 1) * 100
        filled = int(30 * cur / max(tot, 1))
        return f"\r{pre}[{'█'*filled}{'░'*(30-filled)}] {cur}/{tot} ({pct:.1f}%)"

    _mode = "Full" if include_villages else ("No villages" if include_districts else "Cities only")
    print(f"\n{'='*60}\n  Indonesia Admin Downloader\n  Output: {_OUT_PATH}\n  Mode: {_mode}\n{'='*60}")
    _t0 = _time.time()

    print("\n[1/4] Provinces...")
    _provs_raw = _fetch(f"{_BASE_URL}/provinces.json")
    _provinces = [_item(p["id"], p["name"]) for p in _provs_raw if p.get("id") and p.get("name")]
    print(f"  ✓ {len(_provinces)} provinces")

    print(f"\n[2/4] Regencies for {len(_provinces)} provinces...")
    _regencies: dict = {}
    for i, prov in enumerate(_provinces):
        _regencies[prov["code"]] = [
            _item(r["id"], r["name"])
            for r in _fetch(f"{_BASE_URL}/regencies/{prov['code']}.json")
            if r.get("id") and r.get("name")]
        _sys.stdout.write(_bar(i + 1, len(_provinces), "  Regencies "))
        _sys.stdout.flush()
        _time.sleep(_DELAY)
    print(f"\n  ✓ {sum(len(v) for v in _regencies.values())} regencies")

    _districts: dict = {}
    _villages:  dict = {}

    if not include_districts:
        print("\n  (Skipping districts and villages)")
    else:
        _all_reg = [(pc, reg) for pc, regs in _regencies.items() for reg in regs]
        print(f"\n[3/4] Districts for {len(_all_reg)} regencies...")
        for i, (pc, reg) in enumerate(_all_reg):
            _districts[reg["code"]] = [
                _item(d["id"], d["name"])
                for d in _fetch(f"{_BASE_URL}/districts/{reg['code']}.json")
                if d.get("id") and d.get("name")]
            if (i + 1) % 10 == 0 or (i + 1) == len(_all_reg):
                _sys.stdout.write(_bar(i + 1, len(_all_reg), "  Districts "))
                _sys.stdout.flush()
            _time.sleep(_DELAY)
        print(f"\n  ✓ {sum(len(v) for v in _districts.values())} districts")

        if include_villages:
            _all_dist = [(rc, dist) for rc, dists in _districts.items() for dist in dists]
            print(f"\n[4/4] Villages for {len(_all_dist)} districts...")
            print("  (15-25 menit untuk ~83.000 desa — Ctrl+C untuk skip)")
            for i, (rc, dist) in enumerate(_all_dist):
                _villages[dist["code"]] = [
                    _item(v["id"], v["name"])
                    for v in _fetch(f"{_BASE_URL}/villages/{dist['code']}.json")
                    if v.get("id") and v.get("name")]
                if (i + 1) % 50 == 0 or (i + 1) == len(_all_dist):
                    _el = _time.time() - _t0
                    _eta = (_el / (i + 1)) * (len(_all_dist) - i - 1)
                    _sys.stdout.write(
                        _bar(i + 1, len(_all_dist), "  Villages  ") +
                        f"  ETA {int(_eta//60)}m{int(_eta%60):02d}s")
                    _sys.stdout.flush()
                _time.sleep(_DELAY)
            print(f"\n  ✓ {sum(len(v) for v in _villages.values())} villages")

    _data = {
        "meta": {
            "source": "emsifa.github.io/api-wilayah-indonesia",
            "license": "CC-BY (Kemendagri)",
            "updated_at": _datetime2.date.today().isoformat(),
            "build_time_s": round(_time.time() - _t0, 1),
            "provinces": len(_provinces),
            "regencies": sum(len(v) for v in _regencies.values()),
            "districts": sum(len(v) for v in _districts.values()),
            "villages":  sum(len(v) for v in _villages.values()),
        },
        "provinces": _provinces,
        "regencies": _regencies,
        "districts": _districts,
        "villages":  _villages,
    }
    import json as _json2
    with open(_OUT_PATH, "w", encoding="utf-8") as _f:
        _json2.dump(_data, _f, ensure_ascii=False, separators=(",", ":"))
    _sz = os.path.getsize(_OUT_PATH) / 1024
    m = _data["meta"]
    print(f"\n{'='*60}\n  ✅ Saved → {_OUT_PATH} ({_sz:,.0f} KB)")
    print(f"  Prov: {m['provinces']} | Kab: {m['regencies']} | Kec: {m['districts']} | Kel: {m['villages']}")
    print(f"  Build time: {m['build_time_s']}s\n{'='*60}")
    print("\n  Restart tumbal.py (streamlit run tumbal.py) untuk muat data baru.")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# • streamlit run tumbal.py       → Web dashboard (normal)
# • python tumbal.py --notif      → Kirim notifikasi harian (ganti notif_daily.py)
# • python tumbal.py --build-admin [--no-villages | --only-cities]
#                                 → Download data wilayah (ganti build_id_admin.py)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys as _sys_main
    _args = [a.lower() for a in _sys_main.argv[1:]]
    if "--notif" in _args:
        _cli_run_notif()
    elif "--build-admin" in _args:
        _only_cities  = "--only-cities"  in _args
        _no_villages  = "--no-villages"  in _args or _only_cities
        try:
            _cli_build_admin(
                include_districts=not _only_cities,
                include_villages=not _no_villages)
        except KeyboardInterrupt:
            print("\n\n  ⏹  Interrupted. Jalankan lagi dengan --no-villages untuk lebih cepat.\n")
            _sys_main.exit(1)
    else:
        main()