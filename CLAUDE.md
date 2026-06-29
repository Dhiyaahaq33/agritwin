# AgriTwin — Project Context & Memory

**Codename evolution:** `tumbal.py` (monolith) -> `AgriTwin` (platform)
**Working dir:** `D:\BOT\AGRICULTURE\`

---

## Arsitektur Final (Post Fase 4)

```
D:\BOT\AGRICULTURE\
  tumbal.py                  — Legacy Streamlit app (internal tool, masih berjalan)
  .env                       — Semua secrets (git-ignored)
  .env.example               — Template env vars
  .gitignore                 — Exclude secrets, db, cache
  CLAUDE.md                  — Dokumen ini

  weather/
    open_meteo.py            — Open-Meteo API client (gratis, no key)

  db/
    supabase_client.py       — Supabase CRUD (sensor, alert, market, weather)
    setup_supabase.sql       — SQL schema untuk Supabase Dashboard

  market/
    price_feed.py            — Harga komoditas (23 crops, PIHPS/WB/fallback)

  iot/
    mqtt_broker.py           — HiveMQ Cloud MQTT (simulator fallback)

  alerts/
    alert_engine.py          — Threshold evaluation + Telegram notification

  rag/
    knowledge_base.py        — RAG: 10 dokumen agronomi, keyword retrieval

  backend/
    main.py                  — FastAPI app (9 endpoints + WebSocket)
    Dockerfile               — Multi-stage Alpine build
    requirements.txt         — Python dependencies

  frontend/
    package.json             — Next.js 15 + React 19 + Tailwind
    src/app/page.tsx         — Dashboard (sensor cards, weather, alerts, AI chat)
    src/lib/api.ts           — API client + WebSocket helper
    vercel.json              — Vercel deploy config

  docs/
    PRD_AgriTwin.md          — Product requirements
    TechStack_AgriTwin.md    — Tech stack decisions
    schema_agritwin.sql      — Full PostgreSQL schema (target)
    esp32_firmware_spec.md   — ESP32 MQTT payload spec + Arduino/MicroPython examples

  .github/workflows/
    deploy.yml               — CI/CD: test -> build -> deploy (Vercel + Railway)
```

---

## Cara Run (3 service simultan)

```bash
# 1. Backend (FastAPI) — port 8000
cd D:\BOT\AGRICULTURE
uvicorn backend.main:app --reload --port 8000

# 2. Frontend (Next.js) — port 3000
cd D:\BOT\AGRICULTURE\frontend
npm install && npm run dev

# 3. Legacy Streamlit — port 8501
cd D:\BOT\AGRICULTURE
streamlit run tumbal.py
```

API docs otomatis: http://localhost:8000/docs

---

## Cara Deploy

**Backend (Railway):**
```bash
railway login && railway up
# Atau: push ke GitHub → CI/CD otomatis via deploy.yml
```

**Frontend (Vercel):**
```bash
cd frontend && vercel --prod
# Set env: NEXT_PUBLIC_API_URL = https://your-backend.railway.app
```

**Environment variables di production:**
- Railway: semua dari `.env` (SUPABASE_*, GEMINI_*, TELEGRAM_*, dll.)
- Vercel: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`

---

## Roadmap Migrasi — Status

### Fase 0 — Security [DONE]
- [x] `.env` + python-dotenv (26 keys)
- [x] `.gitignore`
- [x] Sentry integration
- [x] `_get_cfg()` refactored

### Fase 1 — Data Layer [DONE]
- [x] `weather/open_meteo.py` — Open-Meteo primary, OWM fallback
- [x] `db/supabase_client.py` — 7 tabel di Supabase
- [x] SQLite data migrated (240 sensor + 39 flow rows)
- [x] `DataHistorian` dual-write (SQLite + Supabase)
- [x] `market/price_feed.py` — 23 crops + fallback

### Fase 2 — IoT Real [DONE]
- [x] `iot/mqtt_broker.py` — HiveMQ Cloud + simulator fallback
- [x] `alerts/alert_engine.py` — 9 default rules + Telegram
- [x] `docs/esp32_firmware_spec.md` — payload spec + code examples
- [x] Auto-ingest: MQTT message -> Supabase

### Fase 3 — Backend Split [DONE]
- [x] FastAPI backend (9 endpoints + WebSocket)
- [x] Next.js frontend (dashboard: sensors, weather, alerts, AI chat)
- [x] Streamlit legacy banner added
- [x] All three run simultaneously

### Fase 4 — Production [DONE]
- [x] Dockerfile (multi-stage)
- [x] `railway.toml` + `vercel.json`
- [x] `.github/workflows/deploy.yml` (CI/CD)
- [x] RAG knowledge base (10 dokumen agronomi Indonesia)
- [x] AI endpoint + RAG context injection
- [ ] **USER ACTION:** Setup Clerk auth (saat production)
- [ ] **USER ACTION:** Setup PostHog (saat production)
- [ ] **USER ACTION:** Install Node.js untuk run frontend

---

## Troubleshooting

| Problem | Solusi |
|---------|--------|
| `streamlit run` error import | `pip install streamlit matplotlib numpy requests pandas plotly scipy` |
| Backend port 8000 in use | `lsof -i :8000` atau ganti port: `uvicorn ... --port 8001` |
| Supabase "table not found" | Run `db/setup_supabase.sql` di Supabase SQL Editor |
| Open-Meteo timeout | Check internet, fallback otomatis ke OWM/simulate |
| MQTT "simulator mode" | Isi `HIVEMQ_*` di `.env`, atau tetap pakai simulator |
| Telegram alert gagal | Cek `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` di `.env` |
| Frontend `npm` not found | Install Node.js: https://nodejs.org/ |

---

## Konvensi Kode

- **Bahasa komentar:** Campuran Indonesia + English
- **Naming:** snake_case, prefix `_` untuk private
- **Config:** `.env` (secrets) + `agri_config.json` (fallback non-secret)
- **Testing:** `python -m py_compile` + `streamlit run` + `curl /api/health`
- **Commit:** NEVER commit `.env` atau API keys
