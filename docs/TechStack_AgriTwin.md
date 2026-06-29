# AgriTwin — Tech Stack & Architecture Decisions

**Version:** 1.0 | **Date:** 30 May 2026

Dokumen ini menjelaskan pilihan teknologi untuk evolusi `tumbal.py` → AgriTwin, beserta alasan, alternatif yang dipertimbangkan, dan tier gratis masing-masing.

---

## Ringkasan Stack

| Layer | Teknologi | Alasan | Free tier |
|-------|-----------|--------|-----------|
| Frontend (baru) | Next.js 15 (React) | SSR, routing, mobile-friendly, PWA | Vercel — no CC |
| Frontend (internal) | Streamlit (`tumbal.py`) | Sudah jalan, internal tool | HF Spaces — no CC |
| Backend | FastAPI (Python) | Async, WebSocket, reuse logika Python | Railway — no CC |
| Database | Supabase (PostgreSQL) | Realtime, auth, REST, pgvector | 500MB — no CC |
| Vector DB | pgvector → Qdrant | RAG; mulai pgvector, scale ke Qdrant | Gratis |
| Cache | Upstash (Redis) | Rate-limit API, cache harga/cuaca | 10K cmd/hari — no CC |
| IoT broker | HiveMQ Cloud (MQTT) | Loop ESP32 real, TLS | 100 koneksi — no CC |
| Auth | Supabase Auth / Clerk | Multi-user, OAuth | Gratis |
| Cuaca | Open-Meteo | Akurat Indonesia, no key | Gratis selamanya |
| Harga pangan | PIHPS BI, SP2KP | Data resmi pemerintah | Gratis |
| AI / LLM | Gemini, Claude, Groq | Multi-provider + fallback | Free tier masing-masing |
| AI Vision | Gemini Vision / Groq Vision | Plant Doctor deteksi penyakit | Gratis |
| Notifikasi | Telegram + WhatsApp | Alert reliable | Telegram gratis |
| Error monitor | Sentry | Crash alert real-time | 5K error/bln — no CC |
| Analytics | PostHog | Product analytics | 1jt event/bln — no CC |
| Payment | Midtrans + Stripe | Lokal + internasional | Sandbox gratis |
| Deploy FE | Vercel | Auto-deploy dari GitHub | No CC |
| Deploy BE | Railway | Python native | Starter no CC |

---

## Keputusan Kunci & Alasan

### Mengapa pisah Backend (FastAPI) dari Frontend (Next.js)?

Streamlit me-reload seluruh script setiap interaksi, tidak punya WebSocket proper, dan session multi-user terbatas. Dengan memisahkan:
- FastAPI menangani logika berat (simulasi crop, ingest sensor, alert engine) sebagai REST + WebSocket API
- Next.js memberi UI cepat, mobile-responsive, routing per halaman
- Streamlit tetap hidup sebagai internal tool/admin sambil migrasi bertahap

Logika Python yang sudah ada di `tumbal.py` (FAO-56 ET, genetic optimizer, weather ensemble) bisa di-port langsung ke FastAPI tanpa rewrite bahasa.

### Mengapa Supabase, bukan SQLite?

SQLite lokal hilang saat restart/deploy dan tidak multi-user. Supabase memberi PostgreSQL terkelola plus:
- Realtime subscription → sensor update langsung ke dashboard (ganti polling `aruna_state.json`)
- Auth bawaan + row-level security → isolasi data antar pengguna
- pgvector → RAG tanpa database terpisah
- REST auto-generated → ESP32 bisa push langsung

### Mengapa HiveMQ Cloud untuk MQTT?

Kode `MQTTBrokerClient` di `tumbal.py` sudah siap pakai paho-mqtt — tinggal sambung ke broker real. HiveMQ Cloud free tier (100 koneksi, TLS) menutup loop: ESP32 publish → HiveMQ → backend subscribe → simpan ke Supabase → push ke dashboard via WebSocket.

### Mengapa Open-Meteo, bukan OpenWeatherMap?

OWM butuh API key (yang sekarang bocor di config). Open-Meteo gratis tanpa key, akurasi setara ERA5 reanalysis untuk Indonesia, dan menyediakan historis + forecast 16 hari. Menggantikan `BMKG_SEASONAL_BIAS` yang hardcoded dengan data cuaca nyata.

### Mengapa multi-LLM dengan fallback?

`tumbal.py` sudah punya routing Gemini/Claude/Groq/OpenRouter/Ollama. Pertahankan dengan fallback chain: jika Gemini kena rate-limit (429), otomatis pindah ke Groq, lalu stub. Tambah RAG (pgvector) agar jawaban spesifik konteks Indonesia.

---

## Migrasi Bertahap (tanpa downtime prototipe)

1. **Fase 0** — Security: rotate keys, `.env`, Sentry
2. **Fase 1** — Data: Supabase + Open-Meteo (Streamlit tetap jalan)
3. **Fase 2** — IoT: HiveMQ + ESP32 firmware
4. **Fase 3** — Backend: ekstrak FastAPI, bangun Next.js
5. **Fase 4** — Production: deploy + auth + RAG

---

## Estimasi Biaya (skala awal)

Semua layer dipilih agar **gratis tanpa kartu kredit** pada skala 50 greenhouse. Upgrade berbayar hanya diperlukan jika:
- Sensor reading > batas Supabase 500MB (≈ beberapa juta baris) → upgrade Supabase Pro
- Koneksi MQTT > 100 simultan → upgrade HiveMQ
- LLM call sangat tinggi → bayar per token Gemini/Groq

Estimasi: **Rp 0/bulan** untuk MVP dan validasi awal.
