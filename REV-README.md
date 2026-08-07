# TWIN TANI DIGITAL
### AgriTwin — Platform Simulasi & Monitoring Pertanian Cerdas (D:\BOT\AGRICULTURE)

---

## Apa Ini?

AgriTwin adalah "kembaran digital" (digital twin) untuk kebun/lahan pertanian. Bayangkan sebuah dashboard yang bisa menampilkan kondisi cuaca, harga komoditas, status sensor IoT (kelembaban tanah, suhu, dll), sampai kasih saran lewat AI chatbot — semuanya dalam satu aplikasi.

Proyek ini awalnya satu file raksasa bernama `tumbal.py` (aplikasi Streamlit), lalu berkembang jadi platform yang lebih rapi dengan backend API (FastAPI) dan folder-folder terpisah untuk tiap fitur (cuaca, database, harga pasar, IoT, alert, dan RAG/basis pengetahuan agronomi).

Cocok untuk: simulasi smart farming, riset/demo IoT pertanian, atau dashboard monitoring kebun yang terhubung ke data cuaca dan harga pasar asli.

## Fitur Utama

- Dashboard Streamlit (`tumbal.py`) — tampilan utama, masih aktif dipakai
- Backend API terpisah pakai FastAPI (folder `backend/`) dengan 9 endpoint + WebSocket real-time
- Data cuaca dari Open-Meteo (gratis, tanpa API key) di folder `weather/`
- Harga komoditas untuk 23 jenis tanaman (folder `market/`)
- Koneksi IoT lewat MQTT (HiveMQ Cloud), dengan mode simulasi otomatis kalau belum ada hardware
- Sistem alert/notifikasi otomatis ke Telegram kalau ada kondisi sensor di luar ambang batas
- RAG (Retrieval-Augmented Generation) — 10 dokumen pengetahuan agronomi buat dijadikan referensi jawaban AI
- Chatbot/asisten AI yang bisa pakai Gemini, Groq, OpenRouter, OpenAI, atau Anthropic (tinggal pilih provider)
- Database via Supabase (cloud) plus SQLite lokal (`agribot_historian.db`)
- Fitur opsional (aktif kalau library terkait di-install): Plant Doctor pakai kamera (OpenCV), sensor via serial/Modbus/OPC-UA, model simulasi tanaman WOFOST (pcse), simulasi rumah kaca (GreenLightPlus)
- Sudah siap deploy ke Railway / Render (`railway.toml`, `render.yaml`)

## Teknologi yang Dipakai

- Python 3.11 + Streamlit (dashboard utama)
- FastAPI (backend API terpisah)
- Supabase (database cloud) + SQLite (database lokal)
- Pandas, NumPy, SciPy, scikit-learn (olah data & analisis)
- Plotly, Matplotlib, PyDeck (grafik & peta)
- paho-mqtt (komunikasi IoT)
- Google Generative AI (Gemini), Groq, Anthropic (AI/LLM)
- Docker (lihat `backend/Dockerfile`)

## Cara Instalasi

1. Pastikan Python 3.11 sudah aktif (sudah terpasang di laptop ini di `C:\Users\izayy\AppData\Local\Programs\Python\Python311`).
2. Buka folder proyek:
   ```powershell
   cd "D:\BOT\AGRICULTURE"
   ```
3. (Opsional tapi disarankan) buat virtual environment dulu supaya rapi:
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```
4. Install semua dependency inti:
   ```powershell
   pip install -r requirements.txt
   ```
5. File `.env` sudah ada isinya (lihat catatan penting di bawah). Kalau mau setup ulang dari nol, copy dulu templatenya:
   ```powershell
   copy .env.example .env
   ```
   lalu isi API key kamu sendiri di file `.env` itu (jangan pernah upload/commit file ini ke GitHub).
6. Fitur tambahan (opsional, install manual kalau dibutuhkan): `pyserial`, `opencv-python`, `pymodbus`, `opcua`, `pcse`, `GreenLightPlus` — semua sudah dikomentari di `requirements.txt`, tinggal hapus tanda `#` untuk yang mau dipakai lalu `pip install` lagi.

## Cara Menjalankan

Menjalankan dashboard utama (Streamlit):
```powershell
streamlit run tumbal.py
```
Atau langsung pakai file batch yang sudah disediakan:
```powershell
start.bat
```

Menjalankan backend API (FastAPI) secara terpisah (kalau butuh):
```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## Catatan Penting

- **File `.env` di folder ini berisi API key ASLI yang sudah terisi** (OpenWeather, Gemini, GeoNames, dan token bot Telegram). Ini artinya kunci-kunci tersebut sudah aktif dan bisa dipakai orang lain kalau file ini bocor/ter-share. **Segera cek apakah key-key ini masih perlu dipakai, dan pertimbangkan untuk rotate (ganti) key kalau folder ini pernah di-share ke publik atau di-push ke repo GitHub yang tidak private.**
- Pastikan `.gitignore` benar-benar meng-exclude `.env`, `.env.local`, dan file database (`agribot_historian.db`) sebelum push ke GitHub — dari pengecekan, `.gitignore` sudah ada dan tampaknya sudah menangani ini, tapi tetap double-check sebelum commit.
- Folder `OTHER/` di dalam AGRICULTURE ini kemungkinan berisi file eksperimen/cadangan — cek isinya kalau bingung file mana yang aktif dipakai.
- File `id_admin_regions.json` berukuran besar (~4MB) — ini data referensi wilayah administratif Indonesia, bukan bug.

## Kebutuhan API LLM

- **Butuh API LLM?** Ya — proyek ini punya chatbot/asisten AI dan sistem RAG (10 dokumen pengetahuan agronomi) yang butuh model bahasa untuk menjawab pertanyaan petani/pengguna secara natural berdasarkan data sensor, cuaca, dan harga pasar.
- **Bisa pakai API Claude (Anthropic)?** Ya, bisa langsung — proyek ini SUDAH mendukung multi-provider LLM (Gemini, Groq, OpenRouter, OpenAI, Anthropic tinggal pilih), jadi API Claude tinggal dipasang sebagai salah satu provider tanpa perlu bikin integrasi baru. Untuk chatbot tanya-jawab harian pakai Claude Haiku 4.5 (cepat & murah), sedangkan untuk analisis RAG yang lebih dalam (menghubungkan data sensor + dokumen agronomi jadi rekomendasi) pakai Claude Sonnet 5.

## Instalasi & Eksekusi Offline

- **Bisa instalasi offline?** Tidak untuk instalasi pertama — `pip install -r requirements.txt` narik banyak package (Streamlit, FastAPI, Google Generative AI SDK, dll) dari PyPI, jadi wajib online. Setelah semua package pernah terpasang/ter-cache di pip cache lokal, install ulang di komputer yang sama bisa lebih cepat, tapi tetap disarankan online untuk memastikan versi lengkap.
- **Bisa dijalankan offline (setelah terinstall)?** Tidak sepenuhnya — dashboard Streamlit-nya bisa dibuka lokal, tapi fitur intinya (data cuaca dari Open-Meteo, harga komoditas, database Supabase cloud, IoT via HiveMQ MQTT, chatbot AI Gemini/Groq/Anthropic, alert Telegram) semuanya butuh koneksi internet ke layanan eksternal. Tanpa internet, dashboard jalan tapi banyak fitur akan gagal/timeout kecuali fallback ke mode simulasi (misalnya simulasi IoT kalau belum ada hardware).
