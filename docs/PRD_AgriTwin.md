# Product Requirements Document (PRD)
## AgriTwin — AI Greenhouse Digital Twin Platform v6.0

**Document version:** 1.0
**Date:** 30 May 2026
**Author:** Johannes (Product Owner)
**Status:** Draft for review
**Codename evolution:** `tumbal.py` (monolith) → `AgriTwin` (platform)

---

## 1. Executive Summary

AgriTwin adalah platform digital twin untuk manajemen greenhouse berbasis AI yang mengubah prototipe monolitik `tumbal.py` (17.000+ baris Streamlit single-file) menjadi sistem production-grade yang dapat diskalakan, multi-user, dan terhubung dengan hardware IoT nyata.

Platform ini menggabungkan simulasi pertumbuhan tanaman (crop modeling), data cuaca real-time, sensor IoT, AI agronomist, dan analitik ekonomi pertanian dalam satu sistem terpadu yang menargetkan pasar Indonesia namun mendukung 40+ negara.

**Masalah inti yang dipecahkan:** Petani dan operator greenhouse di Indonesia tidak punya akses ke sistem pemantauan terpadu yang menggabungkan data sensor real-time, prediksi AI, dan rekomendasi agronomi dalam bahasa dan konteks lokal dengan harga terjangkau.

---

## 2. Problem Statement & Background

### 2.1 Kondisi Saat Ini (Prototipe `tumbal.py`)

Prototipe yang ada sudah membuktikan konsep dengan 22 modul fungsional, namun memiliki keterbatasan fundamental:

| Area | Masalah | Dampak |
|------|---------|--------|
| Arsitektur | Single-file Streamlit 17rb baris | Sulit di-maintain, tidak scalable |
| Penyimpanan data | SQLite lokal + file JSON | Data hilang saat restart/deploy, tidak multi-user |
| Data cuaca | Hardcoded seasonal bias | Bukan data BMKG real, akurasi rendah |
| IoT loop | MQTT simulator | Loop sensor-aktuator belum tertutup |
| Keamanan | API key di file config plaintext | Risiko kebocoran kredensial |
| Multi-user | Tidak ada autentikasi | Hanya bisa dipakai 1 orang lokal |
| Marketplace | Data harga `np.random` | Tidak ada nilai bisnis nyata |
| Deployment | Localhost only | Tidak bisa diakses tim/petani |

### 2.2 Peluang Pasar

Indonesia memiliki sektor hortikultura greenhouse yang berkembang pesat, namun adopsi teknologi pemantauan presisi masih rendah karena: biaya solusi impor yang tinggi, kurangnya lokalisasi (bahasa dan jenis tanaman), serta tidak adanya integrasi data cuaca lokal (BMKG) yang akurat.

---

## 3. Goals & Success Metrics

### 3.1 Tujuan Produk

**Tujuan Primer:**
1. Mengubah prototipe menjadi platform multi-user yang dapat diakses dari mana saja
2. Menutup loop IoT dengan integrasi hardware nyata (ESP32 → cloud → dashboard)
3. Mengganti seluruh data simulasi dengan sumber data real (cuaca, harga, sensor)
4. Mengamankan kredensial dan data pengguna

**Tujuan Sekunder:**
5. Menyediakan AI agronomist yang akurat dengan konteks lokal (RAG)
6. Membangun fondasi monetisasi (marketplace, microcredit, langganan)

### 3.2 Metrik Keberhasilan (KPI)

| Metrik | Baseline | Target (6 bulan) |
|--------|----------|------------------|
| Jumlah greenhouse aktif terdaftar | 1 (prototipe) | 50 |
| Sensor reading real per hari | 0 (semua sim) | 10.000+ |
| Uptime platform | N/A | 99.5% |
| Latensi data sensor (sensor→dashboard) | ~10 detik (file poll) | < 2 detik |
| Akurasi prediksi cuaca (vs aktual) | Tidak terukur | MAE < 1.5°C |
| Daily active users | 1 | 30 |
| AI query response time | 5-25 detik | < 8 detik |

---

## 4. User Personas

### Persona 1: Operator Greenhouse (Primary)
**Nama:** Budi, 34 tahun, pengelola greenhouse hidroponik 500 m² di Bandung
**Kebutuhan:** Pantau kondisi tanaman real-time, dapat alert dini saat parameter abnormal, rekomendasi tindakan
**Pain point:** Harus cek manual ke greenhouse berkali-kali sehari, sering telat menangani masalah
**Tingkat teknis:** Menengah — nyaman dengan aplikasi mobile, tidak bisa coding

### Persona 2: Agronomist / Konsultan (Secondary)
**Nama:** Sari, 41 tahun, konsultan pertanian yang mengelola beberapa klien
**Kebutuhan:** Pantau banyak greenhouse sekaligus, analisis tren, laporan untuk klien
**Pain point:** Tidak ada dashboard terpusat untuk multi-lokasi
**Tingkat teknis:** Tinggi — paham data, mau insight mendalam

### Persona 3: Pemilik / Investor (Tertiary)
**Nama:** Johannes, pemilik usaha agribisnis
**Kebutuhan:** Lihat ROI, proyeksi ekonomi, performa lintas fasilitas
**Pain point:** Sulit menilai profitabilitas tanpa data terstruktur
**Tingkat teknis:** Tinggi — fokus ke metrik bisnis

---

## 5. Feature Requirements

Fitur dikelompokkan dalam tiga prioritas: P0 (wajib MVP), P1 (penting, fase 2), P2 (nice-to-have, fase 3).

### 5.1 Modul Autentikasi & Multi-tenancy (P0)

- Registrasi dan login pengguna (email/password + Google OAuth)
- Manajemen organisasi: satu pemilik dapat mengelola banyak greenhouse
- Role-based access: Owner, Operator, Viewer
- Setiap pengguna hanya melihat data greenhouse miliknya

### 5.2 Modul Greenhouse & Zona (P0)

- CRUD greenhouse (nama, lokasi GPS, luas, jenis)
- CRUD zona dalam greenhouse (multi-zona per fasilitas)
- Penentuan tanaman per zona dari database 100+ tanaman Indonesia
- Pencatatan tanggal tanam dan fase pertumbuhan otomatis

### 5.3 Modul Sensor & IoT Real (P0)

- Integrasi MQTT broker nyata (HiveMQ Cloud)
- Endpoint ingest data sensor (suhu, kelembapan, CO2, soil moisture, pH, EC, cahaya)
- ESP32 push data → cloud → dashboard real-time (< 2 detik)
- Riwayat sensor tersimpan permanen di database cloud
- Deteksi anomali flow meter (clog, leak, dry-run)
- Visualisasi time-series real-time

### 5.4 Modul Cuaca Real (P0)

- Integrasi Open-Meteo API (gratis, no key, akurasi tinggi untuk Indonesia)
- Data historis + forecast 16 hari
- Weather ensemble dengan uncertainty quantification
- Auto-sync lokasi dari GPS greenhouse

### 5.5 Modul Kalender Tanam & Irigasi (P0)

- Hitung fase pertumbuhan, hari setelah tanam, estimasi panen
- Model evapotranspirasi FAO-56 Penman-Monteith
- Kebutuhan air dan nutrisi harian per zona
- Skor kecocokan iklim

### 5.6 Modul AI Agronomist (P1)

- Multi-LLM routing (Gemini, Claude, Groq) dengan fallback otomatis
- RAG: basis pengetahuan agronomi lokal Indonesia (vector database)
- Plant Doctor: deteksi penyakit dari foto (Gemini Vision / Groq Vision)
- Rekomendasi pemupukan dan penanganan hama

### 5.7 Modul Notifikasi (P1)

- Alert real-time via Telegram (gratis, reliable) dan WhatsApp Business
- Konfigurasi threshold per parameter
- Laporan harian otomatis terjadwal
- Log notifikasi

### 5.8 Modul Ekonomi & Marketplace (P1)

- Proyeksi biaya dan pendapatan multi-mata uang
- Integrasi harga pangan real (PIHPS Bank Indonesia, SP2KP Kemendag)
- Carbon MRV (Monitoring, Reporting, Verification)
- Offtaker matching

### 5.9 Modul Pembayaran (P2)

- Integrasi Midtrans (QRIS, transfer, e-wallet) untuk pasar Indonesia
- Integrasi Stripe untuk pembayaran internasional
- Sistem langganan tier (Free, Pro, Enterprise)

### 5.10 Modul Lanjutan (P2)

- Audit trail blockchain untuk sertifikasi organik
- Optimasi setpoint dengan genetic algorithm (NSGA-II)
- Simulasi GreenLight (model fisika iklim greenhouse)
- Visualisasi 3D greenhouse

---

## 6. Non-Functional Requirements

### 6.1 Performa
- Latensi sensor end-to-end < 2 detik
- Dashboard load < 3 detik
- Mendukung 100 koneksi MQTT simultan (free tier HiveMQ)

### 6.2 Keamanan
- Semua kredensial di environment variables / secrets manager
- Enkripsi HTTPS untuk semua endpoint
- Row-level security di database (pengguna hanya akses data sendiri)
- API key tidak pernah di-commit ke repository

### 6.3 Skalabilitas
- Arsitektur stateless backend untuk horizontal scaling
- Database mendukung partisi time-series

### 6.4 Reliabilitas
- Error monitoring real-time (Sentry)
- Graceful degradation (jika API cuaca down, pakai cache terakhir)
- Auto-fallback LLM provider

### 6.5 Usability
- Mobile-responsive (operator akses dari HP)
- Bahasa Indonesia sebagai default, dukungan multi-bahasa
- Antarmuka intuitif untuk pengguna non-teknis

---

## 7. Out of Scope (Fase Ini)

- Aplikasi mobile native (iOS/Android) — gunakan PWA dulu
- Marketplace transaksi penuh end-to-end dengan escrow
- Integrasi drone / citra satelit berbayar
- Model machine learning training pipeline sendiri (pakai API dulu)
- Hardware manufacturing — fokus software, ESP32 pakai yang ada

---

## 8. Migration Strategy (Prototipe → Platform)

Pendekatan bertahap agar prototipe tetap berfungsi selama transisi:

**Fase 0 — Stabilisasi (Minggu 1)**
- Rotate semua API key yang bocor
- Pindahkan kredensial ke `.env`
- Tambahkan Sentry

**Fase 1 — Data Layer (Minggu 2-3)**
- Setup Supabase (PostgreSQL)
- Migrasi skema SQLite → PostgreSQL
- Integrasi Open-Meteo menggantikan weather simulator

**Fase 2 — IoT Real (Minggu 4-5)**
- Aktivasi MQTT broker HiveMQ
- Update firmware ESP32
- Realtime subscription

**Fase 3 — Backend Split (Bulan 2)**
- Ekstrak logika ke FastAPI backend
- Streamlit tetap jalan sebagai internal tool
- Bangun frontend Next.js baru

**Fase 4 — Production (Bulan 3)**
- Deploy frontend (Vercel) + backend (Railway)
- Autentikasi (Clerk/Supabase Auth)
- RAG system

---

## 9. Risks & Mitigations

| Risiko | Probabilitas | Dampak | Mitigasi |
|--------|--------------|--------|----------|
| Free tier limit terlampaui | Sedang | Sedang | Monitor usage, siapkan upgrade path |
| API cuaca/harga down | Rendah | Sedang | Cache + multi-source fallback |
| Refactor memakan waktu lebih lama | Tinggi | Sedang | Pendekatan bertahap, prototipe tetap jalan |
| ESP32 firmware kompleks | Sedang | Tinggi | Mulai dengan 1 zona pilot |
| Adopsi pengguna lambat | Sedang | Tinggi | Onboarding mudah, free tier menarik |

---

## 10. Open Questions

1. Apakah perlu mendukung offline mode untuk area dengan koneksi internet buruk?
2. Model monetisasi: langganan bulanan vs per-greenhouse vs freemium?
3. Apakah data sensor agregat boleh digunakan untuk riset/benchmark anonim?
4. Sejauh mana integrasi dengan sistem pemerintah (e-RDKK, Kartu Tani)?

---

## 11. Appendix — Glossary

- **Digital Twin**: Representasi digital real-time dari objek fisik (greenhouse)
- **FAO-56 Penman-Monteith**: Standar internasional perhitungan evapotranspirasi
- **MQTT**: Protokol messaging ringan untuk IoT
- **RAG**: Retrieval Augmented Generation — AI dengan basis pengetahuan terkurasi
- **Carbon MRV**: Sistem pelaporan jejak karbon untuk sertifikasi
- **DAP**: Days After Planting (hari setelah tanam)
- **EC**: Electrical Conductivity (ukuran konsentrasi nutrisi)
- **PPFD**: Photosynthetic Photon Flux Density (intensitas cahaya untuk fotosintesis)
