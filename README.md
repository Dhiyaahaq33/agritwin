# AgriTwin

**AgriTwin** adalah *AI Greenhouse Digital Twin* — platform pemantauan dan pengelolaan rumah kaca (greenhouse) berbasis data real-time yang menggabungkan sensor IoT, machine learning, dan AI agronomist. "Digital twin" di sini berarti sistem membangun representasi digital dari kondisi greenhouse fisik (suhu, kelembapan, VOC, dsb.) secara real-time, sehingga petani/operator bisa memantau, mendapat peringatan dini, dan berkonsultasi dengan asisten AI tanpa harus berada di lokasi.

Proyek ini merupakan hasil migrasi dari aplikasi monolith Streamlit (`tumbal.py`, masih disertakan sebagai legacy tool) menjadi arsitektur backend/frontend terpisah.

## Fitur Utama

- **Dashboard realtime** — kartu sensor, cuaca, alert, dan chat AI (Next.js + WebSocket).
- **Ingest data sensor** dari ESP32/perangkat IoT via HTTP maupun MQTT, disimpan ke Supabase (dengan fallback data statis bila Supabase belum dikonfigurasi).
- **Live update via WebSocket** (`/ws/zones/{zone_id}/live`) — broadcast pembacaan sensor & alert terbaru ke klien yang terhubung.
- **Deteksi stres tanaman berbasis VOC (AgriVOC)** — klasifikasi sinyal sensor gas (MQ-135, MQ-9, MQ-2) menggunakan model **LightGBM**, dengan fallback rule-based jika model/library belum tersedia. Model bisa dilatih ulang dari data historis Supabase (ditambah dataset sintetis bila sampel kurang) lewat endpoint `/api/voc/train`.
- **Alert engine** — evaluasi ambang batas (threshold) sensor dengan sejumlah rule bawaan, mengirim notifikasi ke Telegram.
- **Data cuaca lokasi** via Open-Meteo (`/api/weather/{lat}/{lon}`).
- **Harga komoditas pertanian** (multi-crop) via `/api/market/prices`.
- **AI Agronomist** — endpoint tanya-jawab (`/api/ai/query`) yang menggunakan Google Gemini dan diperkaya konteks dari basis pengetahuan agronomi lokal (RAG sederhana berbasis keyword retrieval), dengan mode stub bila API key belum diisi.
- **Autentikasi multi-user** via Clerk, termasuk webhook sinkronisasi user (`/api/webhooks/clerk`).
- **Pembayaran/langganan** via Midtrans Snap (`/api/payments/create-transaction`, `/api/payments/webhook`) dengan validasi signature SHA-512.
- **Monitoring error** via Sentry dan **product analytics** via PostHog.
- **Rate limiting** pada endpoint sensitif (AI query, pembayaran) menggunakan SlowAPI.

## Arsitektur & Tech Stack

| Komponen | Teknologi | Peran |
|---|---|---|
| **Backend API** | FastAPI (Python) | Menyediakan REST API + WebSocket: zones, sensor, alert, cuaca, harga pasar, AI query, pembayaran, VOC/LightGBM. Entry point: `backend/main.py` |
| **Frontend** | Next.js 15 (App Router) + React 19 + Tailwind CSS 4 | Dashboard web: kartu sensor, grafik (Recharts), cuaca, alert, chat AI. Route API internal Next.js (`frontend/src/app/api/*`) sebagai proxy ke backend/Supabase |
| **Database** | Supabase (PostgreSQL) | Penyimpanan zona, histori sensor, alert, event pembayaran, user, histori VOC |
| **IoT/Messaging** | MQTT via HiveMQ Cloud (TLS, `paho-mqtt`) | Menghubungkan perangkat ESP32 ke cloud; ada mode simulator in-memory jika broker belum dikonfigurasi |
| **Machine Learning** | LightGBM | Klasifikasi stres tanaman dari pembacaan sensor VOC (gas), dilatih dari data Supabase + data sintetis pelengkap |
| **AI / LLM** | Google Gemini (`google-generativeai`) | Menjawab pertanyaan agronomi pengguna, dengan context injection dari knowledge base lokal (RAG) |
| **Autentikasi** | Clerk | Login/signup multi-user, webhook lifecycle user |
| **Pembayaran** | Midtrans Snap | Transaksi & langganan, webhook notifikasi status pembayaran |
| **Cuaca** | Open-Meteo API | Data cuaca dan forecast per lokasi (lat/lon) |
| **Monitoring** | Sentry, PostHog | Error tracking dan product analytics |
| **Legacy app** | Streamlit (`tumbal.py`) | Aplikasi monolith awal, masih dipertahankan sebagai internal tool |

Struktur direktori utama:

```
backend/    FastAPI app (main.py), Dockerfile
frontend/   Next.js dashboard
db/         Supabase client + skema SQL setup
iot/        MQTT broker client + VOC/LightGBM classifier
alerts/     Alert engine (threshold + notifikasi Telegram)
market/     Feed harga komoditas
payments/   Klien Midtrans
rag/        Knowledge base agronomi (retrieval untuk AI query)
weather/    Klien Open-Meteo
docs/       Dokumentasi produk, tech stack, skema database, spesifikasi firmware ESP32
tumbal.py   Legacy Streamlit app
```

## Instalasi & Menjalankan

Proyek terdiri dari tiga bagian yang bisa dijalankan bersamaan: backend, frontend, dan (opsional) legacy Streamlit app.

### 1. Backend (FastAPI)

```bash
# Dari root repo
pip install -r requirements.txt
# atau, dependensi backend saja:
pip install -r backend/requirements.txt

cp .env.example .env   # isi variabel sesuai kebutuhan (lihat bagian Konfigurasi)

uvicorn backend.main:app --reload --port 8000
```

Dokumentasi API otomatis (Swagger) tersedia di `http://localhost:8000/docs`.

### 2. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Frontend berjalan di `http://localhost:3000` dan berkomunikasi dengan backend via `NEXT_PUBLIC_API_URL`.

### 3. Legacy Streamlit app (opsional)

```bash
pip install -r requirements.txt
streamlit run tumbal.py
```

Berjalan di `http://localhost:8501`.

### Deployment

- **Backend** dapat dideploy ke Railway (`railway.toml`) — build otomatis via `backend/Dockerfile`.
- **Frontend** dapat dideploy ke Vercel (`frontend/vercel.json`).
- **CI/CD**: `.github/workflows/deploy.yml` menjalankan test → build → deploy.
- Alternatif deployment lain: `render.yaml` (Render).

## Konfigurasi Environment Variables

Salin `.env.example` menjadi `.env` di root repo dan isi sesuai kebutuhan (jangan pernah commit file `.env`). Variabel yang tersedia (lihat `.env.example` untuk keterangan lengkap masing-masing):

**Cuaca & Maps**
- `OPENWEATHER_API_KEY`
- `GEONAMES_USERNAME`, `MAPBOX_API_KEY`, `GOOGLE_MAPS_API_KEY`

**AI / LLM**
- `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- (opsional) `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TEMPERATURE`, `GEMINI_MODEL`, `GROQ_MODEL`, `OLLAMA_MODEL`, `OLLAMA_HOST`, `OPENROUTER_MODEL`

**Notifikasi**
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ADMIN_RECIPIENTS`, `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANGUAGE`, `WHATSAPP_GRAPH_API_VERSION`

**Monitoring**
- `SENTRY_DSN`, (opsional) `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`

**Database (Supabase)**
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

**MQTT (HiveMQ Cloud)**
- `HIVEMQ_HOST`, `HIVEMQ_PORT`, `HIVEMQ_USERNAME`, `HIVEMQ_PASSWORD`

**CORS**
- `CORS_ORIGINS`

**Autentikasi (Clerk)**
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`

**Analytics (PostHog)**
- `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST`

**Pembayaran (Midtrans)**
- `MIDTRANS_SERVER_KEY`, `MIDTRANS_CLIENT_KEY`, `MIDTRANS_PRODUCTION`, (opsional) `MIDTRANS_FINISH_URL`, `MIDTRANS_WEBHOOK_SECRET`

Contoh pengisian (gunakan nilai asli Anda sendiri):

```env
SUPABASE_URL=YOUR_SUPABASE_URL_HERE
SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY_HERE
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
```

## Lisensi

Lihat file [`LICENSE`](./LICENSE).
