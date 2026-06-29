"""
╔══════════════════════════════════════════════════════════════╗
║  🌿 AgriPulse Tech — Smart Greenhouse Dashboard             ║
║  PT AgriPulse Digital Nusantara                             ║
║  "Revolutionizing Agriculture with Precision Data"          ║
╚══════════════════════════════════════════════════════════════╝

Run:
  pip install streamlit pandas matplotlib numpy
  streamlit run agripulse.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import math, random, datetime, json
from typing import Dict, List, Optional, Tuple

# ══════════════════════════════════════════════════════
# PAGE CONFIG — must be first st call
# ══════════════════════════════════════════════════════

st.set_page_config(
    page_title="AgriPulse Tech",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;600;700&display=swap');
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# THEME — dark forest tech (adapted from tumbal.py)
# ══════════════════════════════════════════════════════

def inject_theme():
    G   = "#4ee84e"   # accent green
    GD  = "#28a428"   # green dim
    BL  = "#38d4ff"   # accent blue
    GLD = "#ffc844"   # gold / warn
    RD  = "#ff5757"   # red / crit
    BR  = "rgba(78,232,78,0.18)"   # border
    BRH = "rgba(78,232,78,0.42)"   # border hover
    GLW = "rgba(78,232,78,0.18)"   # glow

    st.markdown(f"""<style>
/* ── Base ── */
html,body,[class*="css"] {{ font-family:'Inter',sans-serif; color:#bdd9bd; }}
.stApp {{ background:radial-gradient(ellipse at top left,#0a1a0a 0%,#071307 55%,#040a04 100%); }}
.block-container {{ padding-top:1rem; max-width:1540px; }}
div[data-testid="stHorizontalBlock"] {{ gap:0.7rem; }}

/* ── Scrollbar ── */
::-webkit-scrollbar {{width:6px;height:6px;}}
::-webkit-scrollbar-track {{background:#0a180a;border-radius:6px;}}
::-webkit-scrollbar-thumb {{background:#1e4a1e;border-radius:6px;}}
::-webkit-scrollbar-thumb:hover {{background:{G};}}

/* ── Keyframes ── */
@keyframes fadeInUp {{from{{opacity:0;transform:translateY(12px)}} to{{opacity:1;transform:translateY(0)}}}}
@keyframes gradientShift {{0%{{background-position:0% 50%}} 50%{{background-position:100% 50%}} 100%{{background-position:0% 50%}}}}
@keyframes pulseGlow {{0%,100%{{opacity:1;transform:scale(1)}} 50%{{opacity:.7;transform:scale(1.2)}}}}
@keyframes ripple {{0%{{transform:scale(.8);opacity:1}} 100%{{transform:scale(2.2);opacity:0}}}}
@keyframes breathe {{0%,100%{{box-shadow:0 0 0 0 {GLW}}} 50%{{box-shadow:0 0 18px 4px {GLW}}}}}

/* ── Hero ── */
.ap-hero {{
    position:relative;padding:20px 26px;margin-bottom:16px;border-radius:16px;
    background:linear-gradient(135deg,rgba(9,26,9,.97) 0%,rgba(8,18,30,.97) 60%,rgba(18,9,30,.97) 100%);
    border:1px solid {BRH};overflow:hidden;
    animation:fadeInUp .5s ease both;box-shadow:0 4px 24px rgba(0,0,0,.55);
}}
.ap-hero::before {{
    content:'';position:absolute;top:0;left:0;right:0;height:3px;
    background:linear-gradient(90deg,{G} 0%,{BL} 50%,#c084ff 100%);
    background-size:200% 100%;animation:gradientShift 5s ease infinite;
}}
.ap-hero h1 {{
    font-family:'JetBrains Mono',monospace;font-weight:700;font-size:21px;margin:0;
    background:linear-gradient(90deg,{G},{BL});background-size:200% auto;
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
    animation:gradientShift 6s ease infinite;letter-spacing:.5px;
}}
.ap-hero p {{color:#6a926a;font-size:11px;margin:6px 0 0;letter-spacing:.8px;}}

/* ── Section header ── */
.sec-hdr {{
    display:flex;align-items:center;gap:8px;font-family:'Inter',sans-serif;
    font-weight:700;color:{G};font-size:13px;letter-spacing:1.2px;
    text-transform:uppercase;border-bottom:1px solid {BR};
    padding-bottom:8px;margin:20px 0 12px;animation:fadeInUp .4s ease both;
}}

/* ── Neon metric card ── */
.nm {{
    background:rgba(11,24,11,.94);border:1px solid {BR};border-radius:12px;
    padding:14px 18px;transition:all .28s ease;animation:fadeInUp .4s ease both;
    box-shadow:0 4px 16px rgba(0,0,0,.4);
}}
.nm:hover {{transform:translateY(-3px);border-color:{BRH};box-shadow:0 8px 40px {GLW};}}
.nm .lbl {{font-size:10px;color:#6a926a;text-transform:uppercase;letter-spacing:1.5px;font-weight:600;}}
.nm .val {{
    font-size:28px;font-weight:700;font-family:'JetBrains Mono',monospace;line-height:1.2;margin:4px 0;
    background:linear-gradient(135deg,{G},{BL});
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}}
.nm .val.warn {{background:linear-gradient(135deg,{GLD},#ff9944);-webkit-background-clip:text;background-clip:text;}}
.nm .val.crit {{background:linear-gradient(135deg,{RD},#ff9900);-webkit-background-clip:text;background-clip:text;}}
.nm .unt {{font-size:12px;color:#4a7a4a;font-family:'JetBrains Mono',monospace;}}
.nm .rng {{font-size:10px;color:#3d5e3d;margin-top:6px;}}
.nm-bar {{height:3px;border-radius:2px;background:rgba(78,232,78,.10);margin-top:8px;}}
.nm-fill {{height:100%;border-radius:2px;transition:width .5s ease;}}

/* ── Alert boxes ── */
.ab {{
    padding:11px 15px;border-radius:10px;margin:4px 0;
    font-family:'Inter',sans-serif;font-size:12px;font-weight:500;
    animation:fadeInUp .3s ease both;
}}
.ab.crit {{background:#2e0808;border-left:4px solid {RD};color:#ffaaaa;}}
.ab.warn {{background:#2e2008;border-left:4px solid {GLD};color:#ffdaaa;}}
.ab.info {{background:#08202e;border-left:4px solid {BL};color:#aaddff;}}
.ab.ok   {{background:#08280a;border-left:4px solid {G};color:#aaff99;}}

/* ── Status badges ── */
.sbadge {{
    display:inline-block;padding:3px 10px;border-radius:20px;
    font-size:10px;font-family:'Inter',sans-serif;font-weight:700;
    text-transform:uppercase;letter-spacing:.8px;
}}
.sb-ok   {{background:#142814;color:{G};border:1px solid {GD};}}
.sb-warn {{background:#3a2e08;color:{GLD};border:1px solid #886622;}}
.sb-crit {{background:#3a1010;color:{RD};border:1px solid #882222;}}

/* ── Live pulse ── */
.pulse {{
    display:inline-block;width:9px;height:9px;border-radius:50%;
    background:{G};animation:pulseGlow 1.8s ease-in-out infinite;
    margin-right:6px;vertical-align:middle;position:relative;
}}
.pulse::after {{
    content:'';position:absolute;top:-3px;left:-3px;
    width:15px;height:15px;border-radius:50%;
    border:2px solid {G};animation:ripple 1.8s ease-out infinite;
}}

/* ── Status bar ── */
.statusbar {{
    display:flex;gap:8px;align-items:center;flex-wrap:wrap;
    margin-bottom:16px;padding:10px 14px;border-radius:12px;
    background:rgba(0,0,0,.22);border:1px solid rgba(78,232,78,.14);
}}

/* ── GH card ── */
.gh-card {{
    background:rgba(11,24,11,.94);border:1px solid {BR};
    border-radius:14px;padding:16px 20px;margin:5px 0;
    transition:all .28s ease;animation:fadeInUp .45s ease both;
    box-shadow:0 4px 20px rgba(0,0,0,.4);
}}
.gh-card:hover {{border-color:{BRH};box-shadow:0 8px 40px {GLW};}}

/* ── Streamlit overrides ── */
div[data-testid="stMetricValue"] {{
    font-family:'JetBrains Mono',monospace;color:{G};font-size:24px;font-weight:700;
}}
div[data-testid="stMetricLabel"] {{
    color:#6a926a;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;
}}
.stButton>button {{
    background:linear-gradient(90deg,#143a14,#1e6a1e);color:#bdd9bd;
    border:1px solid {BR};border-radius:10px;font-weight:600;font-size:12px;
    transition:all .22s ease;
}}
.stButton>button:hover {{
    background:linear-gradient(90deg,#1e6a1e,#28aa28);border-color:{BRH};transform:translateY(-2px);
}}
.stButton>button[kind="primary"] {{background:linear-gradient(90deg,{GD},{G});color:#071307;font-weight:700;}}
.stTabs [data-baseweb="tab-list"] {{
    gap:5px;background:rgba(10,22,10,.5);padding:5px;border-radius:12px;border:1px solid {BR};
}}
.stTabs [data-baseweb="tab"] {{
    background:transparent;border-radius:9px;padding:8px 16px;border:1px solid transparent;
    font-family:'Inter',sans-serif;font-size:12px;font-weight:600;color:#6a926a;transition:all .22s ease;
}}
.stTabs [data-baseweb="tab"]:hover {{background:rgba(40,70,40,.45);border-color:{BR};color:#bdd9bd;}}
.stTabs [aria-selected="true"] {{
    background:linear-gradient(135deg,rgba(30,65,30,.75),rgba(18,44,70,.75))!important;
    border-color:{BRH}!important;color:{G}!important;box-shadow:0 2px 12px {GLW};
}}
[data-testid="stSidebar"] {{background:#060f06!important;border-right:1px solid {BR}!important;}}
.stSelectbox label,.stSlider label,.stNumberInput label,.stTextInput label,.stToggle label {{
    color:#6a926a;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;
}}
.stTextInput>div>div>input,.stSelectbox>div>div>div,.stNumberInput>div>div>input {{
    background:rgba(9,20,9,.85)!important;color:#bdd9bd!important;
    border:1px solid {BR}!important;border-radius:8px!important;
}}
.stExpanderHeader {{background:rgba(11,24,11,.94)!important;border:1px solid {BR}!important;border-radius:10px!important;}}
.stDataFrame {{border:1px solid {BR};border-radius:10px;overflow:hidden;}}
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# DOMAIN CONSTANTS
# ══════════════════════════════════════════════════════

KOMODITAS: Dict[str, dict] = {
    "selada": {
        "nama":"Selada (Butterhead & Romaine)","emoji":"🥬","sistem":"NFT",
        "suhu":      {"min":18,  "max":25,   "unit":"°C"},
        "kelembaban":{"min":60,  "max":80,   "unit":"%"},
        "co2":       {"min":400, "max":800,  "unit":"ppm"},
        "ec":        {"min":1.2, "max":2.0,  "unit":"mS/cm"},
        "ph":        {"min":5.5, "max":6.5,  "unit":""},
    },
    "tomat": {
        "nama":"Tomat (Beef & Cherry)","emoji":"🍅","sistem":"Drip System",
        "suhu":      {"min":20,  "max":28,   "unit":"°C"},
        "kelembaban":{"min":65,  "max":80,   "unit":"%"},
        "co2":       {"min":600, "max":1000, "unit":"ppm"},
        "ec":        {"min":2.0, "max":3.5,  "unit":"mS/cm"},
        "ph":        {"min":5.8, "max":6.8,  "unit":""},
    },
    "melon": {
        "nama":"Melon Premium","emoji":"🍈","sistem":"Drip System",
        "suhu":      {"min":25,  "max":32,   "unit":"°C"},
        "kelembaban":{"min":60,  "max":75,   "unit":"%"},
        "co2":       {"min":600, "max":1000, "unit":"ppm"},
        "ec":        {"min":2.0, "max":3.5,  "unit":"mS/cm"},
        "ph":        {"min":6.0, "max":6.8,  "unit":""},
    },
    "paprika": {
        "nama":"Paprika","emoji":"🫑","sistem":"Drip System",
        "suhu":      {"min":20,  "max":28,   "unit":"°C"},
        "kelembaban":{"min":65,  "max":75,   "unit":"%"},
        "co2":       {"min":600, "max":1000, "unit":"ppm"},
        "ec":        {"min":2.5, "max":4.0,  "unit":"mS/cm"},
        "ph":        {"min":5.8, "max":6.5,  "unit":""},
    },
}

CASHFLOW = [
    {"bulan":1,  "unit":0,  "total_in":0,           "opex":129_260_000},
    {"bulan":2,  "unit":0,  "total_in":0,           "opex":129_260_000},
    {"bulan":3,  "unit":5,  "total_in":39_000_000,  "opex":129_260_000},
    {"bulan":4,  "unit":5,  "total_in":43_000_000,  "opex":129_260_000},
    {"bulan":5,  "unit":15, "total_in":117_500_000, "opex":129_260_000},
    {"bulan":6,  "unit":15, "total_in":121_500_000, "opex":129_260_000},
    {"bulan":7,  "unit":15, "total_in":125_500_000, "opex":129_260_000},
    {"bulan":8,  "unit":15, "total_in":129_500_000, "opex":129_260_000},
    {"bulan":9,  "unit":25, "total_in":206_000_000, "opex":150_260_000},
    {"bulan":10, "unit":25, "total_in":212_000_000, "opex":150_260_000},
    {"bulan":11, "unit":25, "total_in":218_000_000, "opex":150_260_000},
    {"bulan":12, "unit":25, "total_in":224_000_000, "opex":150_260_000},
]
_kum = 0
for _cf in CASHFLOW:
    _cf["net"] = _cf["total_in"] - _cf["opex"]
    _kum += _cf["net"]
    _cf["kumulatif"] = _kum


# ══════════════════════════════════════════════════════
# DOMAIN HELPERS
# ══════════════════════════════════════════════════════

def hitung_vpd(suhu: float, rh: float) -> float:
    svp = 0.6108 * math.exp(17.27 * suhu / (suhu + 237.3))
    return round(svp * (1 - rh / 100), 2)


def vpd_label_status(vpd: float) -> Tuple[str, str]:
    if vpd < 0.4:   return "Terlalu Lembab",         "warn"
    if vpd <= 0.8:  return "Optimal — Vegetatif",    "ok"
    if vpd <= 1.2:  return "Optimal — Generatif",    "ok"
    if vpd <= 1.6:  return "Tinggi — Waspada",       "warn"
    return "Sangat Tinggi — Kritis",                  "crit"


def sensor_state(val: float, key: str, thr: dict) -> str:
    mn, mx = thr[key]["min"], thr[key]["max"]
    if mn <= val <= mx:                              return "ok"
    if val < mn * 0.92 or val > mx * 1.08:          return "crit"
    return "warn"


def sim_sensor(komoditas_key: str) -> dict:
    k = KOMODITAS[komoditas_key]

    def near(mn, mx, spread=0.28):
        c = (mn + mx) / 2
        s = (mx - mn) * (1 + spread)
        return round(random.uniform(c - s/2, c + s/2), 2)

    return {
        "suhu":       near(k["suhu"]["min"],       k["suhu"]["max"]),
        "kelembaban": near(k["kelembaban"]["min"], k["kelembaban"]["max"]),
        "co2":        int(near(k["co2"]["min"],    k["co2"]["max"], 0.45)),
        "ec":         near(k["ec"]["min"],         k["ec"]["max"]),
        "ph":         near(k["ph"]["min"],         k["ph"]["max"]),
        "ts": datetime.datetime.now().strftime("%H:%M:%S"),
    }


def get_thr(komoditas_key: str) -> dict:
    return {k: v for k, v in KOMODITAS[komoditas_key].items()
            if k not in ("nama", "emoji", "sistem")}


def aktuator_action(sensor: dict, thr: dict) -> Tuple[List[str], List[str]]:
    ok_acts, alerts = [], []
    if sensor["suhu"] > thr["suhu"]["max"]:
        ok_acts += ["💨 Exhaust Fan AKTIF — buang udara panas",
                    "🌫️ Mist Fogger AKTIF — turunkan suhu ruangan"]
    elif sensor["suhu"] < thr["suhu"]["min"]:
        alerts.append("🌡️ Suhu terlalu rendah — aktifkan pemanas / heater")
    if sensor["kelembaban"] > thr["kelembaban"]["max"]:
        ok_acts.append("💨 Fan sirkulasi AKTIF — kurangi kelembaban berlebih")
    elif sensor["kelembaban"] < thr["kelembaban"]["min"]:
        ok_acts.append("🌫️ Mist Fogger AKTIF — naikkan kelembaban udara")
    if sensor["co2"] < thr["co2"]["min"]:
        ok_acts.append("🔄 Sirkulasi AKTIF — tambah kadar CO₂")
    elif sensor["co2"] > thr["co2"]["max"]:
        ok_acts.append("💨 Fan AKTIF — kurangi CO₂ berlebih")
    if sensor["ec"] < thr["ec"]["min"]:
        ok_acts.append("💧 Pompa Nutrisi AKTIF — naikkan EC larutan")
    elif sensor["ec"] > thr["ec"]["max"]:
        alerts.append("⚠️ EC terlalu tinggi — encerkan konsentrasi nutrisi")
    if sensor["ph"] < thr["ph"]["min"]:
        alerts.append("🔴 pH terlalu asam — tambahkan larutan pH Up")
    elif sensor["ph"] > thr["ph"]["max"]:
        alerts.append("🔴 pH terlalu basa — tambahkan larutan pH Down")
    if not ok_acts and not alerts:
        ok_acts.append("✅ Semua parameter dalam rentang optimal — sistem standby")
    return ok_acts, alerts


def health_score(sensor: dict, thr: dict) -> float:
    keys = list(thr.keys())
    score = 0.0
    for k in keys:
        mn, mx = thr[k]["min"], thr[k]["max"]
        v = sensor[k]
        if mn <= v <= mx:
            score += 1.0
        else:
            span = max(0.01, (mx - mn) / 2)
            score += max(0.0, 1.0 - min(abs(v - mn), abs(v - mx)) / span)
    return round(score / len(keys) * 100, 1)


# ══════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════

def init_state():
    if "greenhouses" not in st.session_state:
        st.session_state.greenhouses = [
            {"id":1,"nama":"GH Selada A1","komoditas":"selada","lokasi":"Berastagi","luas":500},
            {"id":2,"nama":"GH Tomat B1", "komoditas":"tomat", "lokasi":"Karo",     "luas":800},
        ]
        st.session_state.next_id = 3
    if "histories"  not in st.session_state: st.session_state.histories  = {}
    if "alert_log"  not in st.session_state: st.session_state.alert_log  = []
    if "sel_gh"     not in st.session_state: st.session_state.sel_gh     = 1


def get_gh(gh_id: int) -> Optional[dict]:
    return next((g for g in st.session_state.greenhouses if g["id"] == gh_id), None)


def history_of(gh_id: int) -> List[dict]:
    return st.session_state.histories.get(gh_id, [])


def push_reading(gh_id: int, sensor: dict):
    h = st.session_state.histories.get(gh_id, [])
    h.append(sensor)
    if len(h) > 80:
        h = h[-80:]
    st.session_state.histories[gh_id] = h


def push_alerts(gh_id: int, gh_nama: str, msgs: List[str]):
    for msg in msgs:
        st.session_state.alert_log.append({
            "id": len(st.session_state.alert_log) + 1,
            "gh_id": gh_id, "gh_nama": gh_nama,
            "pesan": msg, "resolved": False,
            "ts": datetime.datetime.now().strftime("%d/%m %H:%M:%S"),
        })
    if len(st.session_state.alert_log) > 300:
        st.session_state.alert_log = st.session_state.alert_log[-300:]


# ══════════════════════════════════════════════════════
# UI COMPONENTS
# ══════════════════════════════════════════════════════

def hero():
    now = datetime.datetime.now().strftime("%A, %d %B %Y — %H:%M")
    st.markdown(f"""
    <div class="ap-hero">
      <h1>🌿 AgriPulse Tech — Smart Greenhouse Dashboard</h1>
      <p>PT AgriPulse Digital Nusantara &nbsp;·&nbsp;
         "Revolutionizing Agriculture with Precision Data" &nbsp;·&nbsp; {now}</p>
    </div>
    """, unsafe_allow_html=True)


def statusbar():
    ghs  = st.session_state.greenhouses
    area = sum(g["luas"] for g in ghs)
    badges = " ".join(
        f'<span class="sbadge sb-ok">{KOMODITAS[g["komoditas"]]["emoji"]} {g["nama"]}</span>'
        for g in ghs
    )
    st.markdown(f"""
    <div class="statusbar">
      <span style="font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:700;white-space:nowrap;">
        <span class="pulse"></span>AGRIPULSE LIVE
      </span>
      {badges}
      <span style="font-size:10px;opacity:.55;margin-left:auto;white-space:nowrap;">
        🌿 {len(ghs)} greenhouse &nbsp;·&nbsp; {area:,.0f} m² total lahan
      </span>
    </div>
    """, unsafe_allow_html=True)


def sec(title: str):
    st.markdown(f'<div class="sec-hdr">{title}</div>', unsafe_allow_html=True)


def sensor_card(label: str, value, unit: str, state: str, mn: float, mx: float):
    css   = {"ok": "", "warn": " warn", "crit": " crit"}.get(state, "")
    pct   = int(max(0, min(100, (value - mn) / max(0.001, mx - mn) * 100)))
    color = {"ok": "#4ee84e", "warn": "#ffc844", "crit": "#ff5757"}.get(state, "#4ee84e")
    badge_css = {"ok": "sb-ok", "warn": "sb-warn", "crit": "sb-crit"}.get(state, "sb-ok")
    badge_txt = {"ok": "✓ OPTIMAL", "warn": "⚠ WASPADA", "crit": "🔴 KRITIS"}.get(state, "")
    st.markdown(f"""
    <div class="nm">
      <div class="lbl">{label}</div>
      <div class="val{css}">{value}</div>
      <div class="unt">{unit}&nbsp;
        <span class="sbadge {badge_css}">{badge_txt}</span>
      </div>
      <div class="rng">Target: {mn} – {mx} {unit}</div>
      <div class="nm-bar"><div class="nm-fill" style="width:{pct}%;background:{color};"></div></div>
    </div>
    """, unsafe_allow_html=True)


def vpd_card(vpd: float):
    label, state = vpd_label_status(vpd)
    color = {"ok": "#4ee84e", "warn": "#ffc844", "crit": "#ff5757"}[state]
    pct   = int(min(100, vpd / 2.0 * 100))
    st.markdown(f"""
    <div class="nm">
      <div class="lbl">VPD — Vapor Pressure Deficit</div>
      <div class="val" style="-webkit-text-fill-color:{color};">{vpd}</div>
      <div class="unt">kPa &nbsp;·&nbsp; <span style="color:{color};font-family:'Inter';">{label}</span></div>
      <div class="rng">Optimal: 0.4 – 1.2 kPa &nbsp;·&nbsp; Tekanan evaporasi tanaman</div>
      <div class="nm-bar"><div class="nm-fill" style="width:{pct}%;background:{color};"></div></div>
    </div>
    """, unsafe_allow_html=True)


def health_card(score: float):
    color = "#4ee84e" if score >= 80 else "#ffc844" if score >= 60 else "#ff5757"
    label = "EXCELLENT" if score >= 90 else "GOOD" if score >= 80 else "WARNING" if score >= 60 else "CRITICAL"
    st.markdown(f"""
    <div class="nm" style="text-align:center;">
      <div class="lbl">Health Score</div>
      <div style="font-size:44px;font-weight:700;font-family:'JetBrains Mono',monospace;
                  color:{color};line-height:1.1;margin:4px 0;">{score:.0f}</div>
      <div class="unt">/ 100 &nbsp;
        <span class="sbadge" style="background:rgba(0,0,0,.3);color:{color};border:1px solid {color};">{label}</span>
      </div>
      <div class="nm-bar" style="height:5px;margin-top:10px;">
        <div class="nm-fill" style="width:{score:.0f}%;background:{color};height:100%;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def action_panel(aksi: List[str], alerts: List[str]):
    sec("⚙️ Automated Action — Closed-Loop Control")
    for a in aksi:
        st.markdown(f'<div class="ab ok">{a}</div>', unsafe_allow_html=True)
    for a in alerts:
        st.markdown(f'<div class="ab warn">{a}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════

def sidebar() -> dict:
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:12px 0 8px;">
          <div style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;
                      background:linear-gradient(90deg,#4ee84e,#38d4ff);
                      -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
            🌿 AgriPulse Tech
          </div>
          <div style="font-size:9px;color:#6a926a;margin-top:3px;letter-spacing:1.2px;">
            SMART GREENHOUSE SYSTEM
          </div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        ghs = st.session_state.greenhouses
        if not ghs:
            st.warning("Belum ada greenhouse. Tambahkan di tab Greenhouse.")
            return {}

        opts = {g["id"]: f"{KOMODITAS[g['komoditas']]['emoji']} {g['nama']}" for g in ghs}
        sel  = st.selectbox("Pilih Greenhouse Aktif",
                            options=list(opts.keys()),
                            format_func=lambda x: opts[x])
        st.session_state.sel_gh = sel
        gh = get_gh(sel)

        st.divider()
        if gh:
            k = KOMODITAS[gh["komoditas"]]
            st.markdown(f"""
            <div style="background:rgba(11,24,11,.8);border:1px solid rgba(78,232,78,.15);
                        border-radius:10px;padding:12px;font-size:11px;color:#6a926a;line-height:1.9;">
              <b style="color:#bdd9bd;">{gh['nama']}</b><br>
              {k['emoji']} {k['nama']}<br>
              🌱 {k['sistem']}<br>
              📍 {gh.get('lokasi','-')}<br>
              📐 {gh.get('luas',0):,} m²
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        if st.button("🔄 Ambil Data Sensor", use_container_width=True, type="primary"):
            if gh:
                s   = sim_sensor(gh["komoditas"])
                thr = get_thr(gh["komoditas"])
                push_reading(gh["id"], s)
                _, alrt = aktuator_action(s, thr)
                if alrt:
                    push_alerts(gh["id"], gh["nama"], alrt)
                st.rerun()

        auto = st.toggle("Auto Refresh (30 dtk)", value=False)
        if auto:
            import time; time.sleep(30); st.rerun()

        st.divider()
        st.markdown("""
        <div style="font-size:9px;color:#3d5e3d;text-align:center;line-height:1.9;">
          PT AgriPulse Digital Nusantara<br>
          "Revolutionizing Agriculture<br>with Precision Data"<br>
          Kelompok 2 · 2025
        </div>""", unsafe_allow_html=True)

    return get_gh(st.session_state.sel_gh) or {}


# ══════════════════════════════════════════════════════
# TAB 1 — LIVE DASHBOARD
# ══════════════════════════════════════════════════════

def tab_live(gh: dict):
    komod = gh["komoditas"]
    k     = KOMODITAS[komod]
    thr   = get_thr(komod)

    hist  = history_of(gh["id"])
    if not hist:
        for _ in range(12):
            push_reading(gh["id"], sim_sensor(komod))
        hist = history_of(gh["id"])

    s    = hist[-1]
    vpd  = hitung_vpd(s["suhu"], s["kelembaban"])
    aksi, alrts = aktuator_action(s, thr)
    hs   = health_score(s, thr)

    # Header strip
    st.markdown(f"""
    <div class="sec-hdr" style="margin-top:4px;">
      📡 {k['emoji']} {gh['nama']} &nbsp;·&nbsp; {k['nama']} ({k['sistem']})
      &nbsp;·&nbsp; 📍 {gh.get('lokasi','-')} &nbsp;·&nbsp; 📐 {gh.get('luas',0):,} m²
      <span style="font-size:10px;opacity:.6;margin-left:auto;">Update: {s['ts']}</span>
    </div>
    """, unsafe_allow_html=True)

    # VPD + Health
    c1, c2 = st.columns([1.2, 1])
    with c1: vpd_card(vpd)
    with c2: health_card(hs)

    st.markdown("<br>", unsafe_allow_html=True)

    # 5 sensor cards
    cols = st.columns(5)
    CARDS = [
        ("🌡️ Suhu Udara",  "suhu",       "°C"),
        ("💧 Kelembaban",   "kelembaban", "%"),
        ("🌫️ CO₂",         "co2",        "ppm"),
        ("⚗️ EC Nutrisi",  "ec",         "mS/cm"),
        ("🔬 pH Larutan",  "ph",         ""),
    ]
    for col, (label, key, unit) in zip(cols, CARDS):
        with col:
            sensor_card(label, s[key], unit,
                        sensor_state(s[key], key, thr),
                        thr[key]["min"], thr[key]["max"])

    # Automated actions
    action_panel(aksi, alrts)


# ══════════════════════════════════════════════════════
# TAB 2 — ANALYTICS
# ══════════════════════════════════════════════════════

def tab_analytics(gh: dict):
    hist = history_of(gh["id"])
    if len(hist) < 3:
        st.markdown('<div class="ab info">Minimal 3 pembacaan diperlukan. Klik "Ambil Data Sensor" beberapa kali.</div>', unsafe_allow_html=True)
        return

    df  = pd.DataFrame(hist)
    thr = get_thr(gh["komoditas"])

    sec("📈 Trend Sensor Historis")

    fig, axes = plt.subplots(2, 3, figsize=(14, 6))
    fig.patch.set_facecolor("#071307")
    PARAMS = [
        ("suhu",       "Suhu (°C)",     "#ff5757", axes[0,0]),
        ("kelembaban", "Kelembaban (%)", "#38d4ff", axes[0,1]),
        ("co2",        "CO₂ (ppm)",     "#c084ff", axes[0,2]),
        ("ec",         "EC (mS/cm)",    "#4ee84e", axes[1,0]),
        ("ph",         "pH Larutan",    "#ffc844", axes[1,1]),
    ]
    xs = list(range(len(df)))
    for key, title, color, ax in PARAMS:
        ax.set_facecolor("#0d200d")
        ax.tick_params(colors="#6a926a", labelsize=8)
        for sp in ax.spines.values(): sp.set_color((0.306, 0.910, 0.306, 0.15))
        vals = df[key].tolist()
        ax.plot(xs, vals, color=color, lw=1.8, marker="o", markersize=3)
        ax.fill_between(xs, vals, alpha=0.07, color=color)
        ax.axhline(thr[key]["min"], color=color, lw=0.8, ls="--", alpha=0.35)
        ax.axhline(thr[key]["max"], color=color, lw=0.8, ls="--", alpha=0.35)
        ax.set_title(title, color="#bdd9bd", fontsize=9, fontfamily="monospace")
        ax.grid(color=(0.306, 0.910, 0.306, 0.05), lw=0.5)

    axes[1, 2].set_facecolor("#0d200d")
    axes[1, 2].set_visible(False)
    fig.tight_layout(pad=1.5)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    sec("📊 Statistik Ringkas")
    rows = []
    for key, title, _, _ in PARAMS:
        vals  = df[key].tolist()
        mn_t  = thr[key]["min"]
        mx_t  = thr[key]["max"]
        pct_ok = sum(1 for v in vals if mn_t <= v <= mx_t) / len(vals) * 100
        rows.append({
            "Parameter": title,
            "Min Aktual": round(min(vals), 2),
            "Max Aktual": round(max(vals), 2),
            "Rata-Rata":  round(sum(vals) / len(vals), 2),
            "Target Min": mn_t,
            "Target Max": mx_t,
            "% Optimal":  f"{pct_ok:.0f}%",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Export CSV Sensor History",
        csv_bytes,
        file_name=f"agripulse_{gh['nama'].replace(' ','_')}_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


# ══════════════════════════════════════════════════════
# TAB 3 — ALERTS
# ══════════════════════════════════════════════════════

def tab_alerts():
    logs     = st.session_state.alert_log
    active   = [a for a in logs if not a["resolved"]]
    resolved = [a for a in logs if a["resolved"]]

    c1, c2 = st.columns(2)
    c1.metric("Alert Belum Diselesaikan", len(active))
    c2.metric("Total Alert (semua)", len(logs))

    sec("🔴 Alert Aktif")
    if not active:
        st.markdown('<div class="ab ok">✅ Tidak ada alert aktif — semua greenhouse dalam kondisi optimal!</div>', unsafe_allow_html=True)
    else:
        for a in reversed(active[-25:]):
            st.markdown(f"""
            <div class="ab warn">
              <strong>{a['gh_nama']}</strong> &nbsp;·&nbsp; {a['pesan']}
              <span style="float:right;opacity:.45;font-size:9px;font-family:'JetBrains Mono';">{a['ts']}</span>
            </div>
            """, unsafe_allow_html=True)
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("✓ Resolve Semua", type="primary"):
                for a in st.session_state.alert_log:
                    a["resolved"] = True
                st.rerun()

    if resolved:
        sec("✅ Riwayat Resolved")
        with st.expander(f"{len(resolved)} alert sudah diselesaikan"):
            for a in reversed(resolved[-30:]):
                st.markdown(f"""
                <div class="ab ok" style="opacity:.55;">
                  <strong>{a['gh_nama']}</strong> &nbsp;·&nbsp; {a['pesan']}
                  <span style="float:right;opacity:.35;font-size:9px;">{a['ts']}</span>
                </div>
                """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# TAB 4 — GREENHOUSE MANAGER
# ══════════════════════════════════════════════════════

def tab_greenhouse():
    sec("➕ Tambah Greenhouse Baru")
    with st.expander("Buka Form Tambah", expanded=len(st.session_state.greenhouses) == 0):
        c1, c2, c3, c4 = st.columns(4)
        with c1: nama  = st.text_input("Nama",    placeholder="GH Selada A1", key="add_nama")
        with c2:
            kom = st.selectbox("Komoditas", list(KOMODITAS.keys()),
                               format_func=lambda x: f"{KOMODITAS[x]['emoji']} {KOMODITAS[x]['nama']}",
                               key="add_kom")
        with c3: lok   = st.text_input("Lokasi",  placeholder="Berastagi, Karo", key="add_lok")
        with c4: luas  = st.number_input("Luas (m²)", 10.0, 50000.0, 500.0, 10.0, key="add_luas")

        if st.button("➕ Tambah Greenhouse", type="primary"):
            if nama.strip():
                st.session_state.greenhouses.append({
                    "id": st.session_state.next_id,
                    "nama": nama.strip(), "komoditas": kom,
                    "lokasi": lok, "luas": luas,
                })
                st.session_state.next_id += 1
                st.success(f"Greenhouse '{nama}' berhasil ditambahkan!")
                st.rerun()
            else:
                st.error("Nama greenhouse wajib diisi.")

    sec("📋 Daftar Greenhouse")
    if not st.session_state.greenhouses:
        st.markdown('<div class="ab info">Belum ada greenhouse. Tambahkan menggunakan form di atas.</div>', unsafe_allow_html=True)
        return

    for gh in st.session_state.greenhouses:
        k    = KOMODITAS[gh["komoditas"]]
        hist = history_of(gh["id"])
        last = hist[-1]["ts"] if hist else "Belum ada data"
        n_ok = len(hist)

        col_card, col_del = st.columns([5, 1])
        with col_card:
            st.markdown(f"""
            <div class="gh-card">
              <div style="display:flex;align-items:center;gap:12px;">
                <span style="font-size:28px;">{k['emoji']}</span>
                <div style="flex:1;">
                  <div style="font-family:'JetBrains Mono',monospace;font-weight:700;color:#e4f5e4;font-size:14px;">
                    {gh['nama']}
                  </div>
                  <div style="font-size:11px;color:#6a926a;margin-top:2px;">
                    {k['nama']} ({k['sistem']}) &nbsp;·&nbsp; 📍 {gh.get('lokasi','-')} &nbsp;·&nbsp; 📐 {gh.get('luas',0):,} m²
                  </div>
                </div>
                <span class="sbadge {'sb-ok' if hist else 'sb-warn'}">
                  {'✓ ' + str(n_ok) + ' readings' if hist else '○ NO DATA'}
                </span>
              </div>
              <div style="font-size:10px;color:#3d5e3d;margin-top:8px;">
                🕐 Update terakhir: {last}
              </div>
            </div>
            """, unsafe_allow_html=True)
        with col_del:
            st.markdown("<br><br>", unsafe_allow_html=True)
            if st.button("🗑️", key=f"del_{gh['id']}", help=f"Hapus {gh['nama']}"):
                st.session_state.greenhouses = [
                    g for g in st.session_state.greenhouses if g["id"] != gh["id"]
                ]
                st.session_state.histories.pop(gh["id"], None)
                if st.session_state.sel_gh == gh["id"]:
                    st.session_state.sel_gh = (
                        st.session_state.greenhouses[0]["id"]
                        if st.session_state.greenhouses else 1
                    )
                st.rerun()


# ══════════════════════════════════════════════════════
# TAB 5 — FINANSIAL & ROI
# ══════════════════════════════════════════════════════

def tab_finansial():
    sec("🧮 ROI Calculator — Simulasi Keuntungan Klien")

    with st.expander("Input Parameter", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            n_kit  = st.number_input("Jumlah Smart-Kit",      1, 200, 5)
            p_kit  = st.number_input("Harga per unit (Rp)",   value=6_800_000, step=100_000)
        with c2:
            tk_now = st.number_input("Biaya TK/bulan saat ini (Rp)", value=8_000_000, step=500_000)
            eff    = st.slider("Efisiensi TK dengan IoT (%)", 20, 70, 50)
        with c3:
            p_saas = st.number_input("Biaya SaaS/tahun/unit (Rp)", value=2_000_000, step=100_000)
            n_panen = st.number_input("Siklus panen per tahun",    1, 8, 4)

    invest    = n_kit * p_kit
    saas_1y   = n_kit * p_saas
    hemat_mo  = tk_now * eff / 100
    hemat_yr  = hemat_mo * 12
    net_y1    = hemat_yr - saas_1y
    payback   = invest / max(1, hemat_mo)
    roi_y1    = net_y1 / max(1, invest) * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Investasi",     f"Rp {invest:,.0f}".replace(",","."),
              delta=None)
    c2.metric("Hemat TK / tahun",    f"Rp {hemat_yr:,.0f}".replace(",","."),
              delta=f"+Rp {hemat_mo:,.0f}/bln".replace(",","."))
    c3.metric("Payback Period",      f"{payback:.1f} bulan")
    c4.metric("ROI Tahun 1",         f"{roi_y1:.1f}%",
              delta="positif" if roi_y1 > 0 else "belum BEP")

    sec("📈 Proyeksi Cash Flow Tahun 1 (Business Plan AgriPulse)")

    bulan  = [cf["bulan"]    for cf in CASHFLOW]
    income = [cf["total_in"] / 1e6 for cf in CASHFLOW]
    opex_v = [cf["opex"]     / 1e6 for cf in CASHFLOW]
    kum_v  = [cf["kumulatif"]/ 1e6 for cf in CASHFLOW]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.patch.set_facecolor("#071307")
    xs = np.arange(len(bulan))

    for ax in (ax1, ax2):
        ax.set_facecolor("#0d200d")
        ax.tick_params(colors="#6a926a", labelsize=8)
        for sp in ax.spines.values(): sp.set_color((0.306, 0.910, 0.306, 0.15))
        ax.grid(color=(0.306, 0.910, 0.306, 0.05), lw=0.5)
        ax.set_xticks(xs)
        ax.set_xticklabels([f"B{b}" for b in bulan], fontsize=8, color="#6a926a")

    ax1.bar(xs - 0.2, income, 0.38, label="Income", color="#4ee84e", alpha=0.85)
    ax1.bar(xs + 0.2, opex_v, 0.38, label="OPEX",   color="#ff5757", alpha=0.85)
    ax1.set_title("Income vs OPEX (Juta Rp)", color="#bdd9bd", fontsize=9, fontfamily="monospace")
    ax1.legend(fontsize=8, labelcolor="#bdd9bd", facecolor="#0d200d", edgecolor="#1e4a1e")

    bar_colors = ["#4ee84e" if v >= 0 else "#ff5757" for v in kum_v]
    ax2.bar(xs, kum_v, color=bar_colors, alpha=0.85)
    ax2.axhline(0, color="#ffc844", lw=1.2, ls="--", alpha=0.8)
    ax2.set_title("Kumulatif Net Cash Flow (Juta Rp)", color="#bdd9bd", fontsize=9, fontfamily="monospace")

    fig.tight_layout(pad=1.5)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    sec("📋 Tabel Cash Flow Detail")
    df = pd.DataFrame(CASHFLOW)[["bulan","unit","total_in","opex","net","kumulatif"]]
    df.columns = ["Bulan","Unit Terjual","Total Income (Rp)","OPEX (Rp)","Net CF (Rp)","Kumulatif (Rp)"]
    st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

def main():
    inject_theme()
    init_state()

    gh = sidebar()
    if not gh:
        hero()
        st.info("Belum ada greenhouse. Buka tab **Greenhouse** untuk menambahkan.")
        return

    hero()
    statusbar()

    t1, t2, t3, t4, t5 = st.tabs([
        "📊 Live Dashboard",
        "📈 Analytics",
        "🔔 Alerts",
        "🌱 Greenhouse",
        "💰 Finansial",
    ])

    with t1: tab_live(gh)
    with t2: tab_analytics(gh)
    with t3: tab_alerts()
    with t4: tab_greenhouse()
    with t5: tab_finansial()


if __name__ == "__main__":
    main()
