-- ============================================================================
-- AgriTwin — Supabase Table Setup (Fase 1)
-- ============================================================================
-- CARA PAKAI:
--   1. Buka https://supabase.com/dashboard → pilih project
--   2. Klik "SQL Editor" di sidebar kiri
--   3. Paste SEMUA isi file ini → klik "Run"
--   4. Selesai! Tabel otomatis muncul di Table Editor.
-- ============================================================================

-- sensor_readings — data sensor IoT (suhu, kelembapan, CO2, dll.)
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

-- flow_meter_log — data flow meter irigasi
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

-- actuator_events — perintah ke hardware (valve, LED, fan, pump)
CREATE TABLE IF NOT EXISTS actuator_events (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    actuator        TEXT NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    triggered_by    TEXT NOT NULL DEFAULT 'auto'
);

-- alerts — peringatan saat parameter di luar threshold
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

-- vernalization_log — akumulasi cold hours untuk tanaman tertentu
CREATE TABLE IF NOT EXISTS vernalization_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    crop_id         TEXT NOT NULL,
    temp_c          DOUBLE PRECISION,
    cold_hours      DOUBLE PRECISION,
    target_hours    DOUBLE PRECISION
);

-- weather_snapshots — cache cuaca dari Open-Meteo
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

-- market_prices — harga komoditas dari PIHPS/World Bank
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

-- knowledge_documents — dokumen agronomi untuk RAG
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    source          TEXT,
    content         TEXT NOT NULL,
    language        TEXT DEFAULT 'id',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- knowledge_chunks — potongan teks untuk vector search
-- Catatan: kolom embedding memerlukan pgvector (lihat bagian pgvector di bawah)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     BIGINT REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id
    ON knowledge_chunks (document_id, chunk_index);

-- users — user dari Clerk Auth, disinkronisasi via Clerk webhook
-- clerk_id UNIQUE: satu akun Clerk = satu baris, tidak pernah dihapus (soft delete)
CREATE TABLE IF NOT EXISTS users (
    id                   BIGSERIAL PRIMARY KEY,
    clerk_id             TEXT NOT NULL,
    email                TEXT NOT NULL,
    name                 TEXT DEFAULT '',
    subscription_active  BOOLEAN NOT NULL DEFAULT false,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at           TIMESTAMPTZ                           -- NULL = aktif, diisi = soft delete
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_id ON users (clerk_id);
CREATE INDEX IF NOT EXISTS idx_users_email           ON users (email);

-- payment_events — audit trail semua event pembayaran dari Midtrans webhook
-- Setiap notifikasi webhook menghasilkan satu baris, termasuk transaksi gagal
CREATE TABLE IF NOT EXISTS payment_events (
    id                   BIGSERIAL PRIMARY KEY,
    order_id             TEXT NOT NULL,
    transaction_id       TEXT DEFAULT '',
    transaction_status   TEXT NOT NULL,
    payment_type         TEXT DEFAULT '',
    gross_amount         TEXT DEFAULT '',
    user_id              TEXT DEFAULT '',    -- clerk_id dari tabel users
    raw_payload          JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_events_order_id ON payment_events (order_id);
CREATE INDEX IF NOT EXISTS idx_payment_events_user_id  ON payment_events (user_id);

-- voc_readings — pembacaan sensor VOC array (MQ-135, MQ-9, MQ-2) + hasil klasifikasi stres
-- id menggunakan UUID agar mudah di-shard dan tidak sequential-guessable
CREATE TABLE IF NOT EXISTS voc_readings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id             TEXT NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),   -- waktu pembacaan sensor
    mq135_value         DOUBLE PRECISION NOT NULL DEFAULT 0,  -- CO2, NH3, alkohol (0-1000 ADC)
    mq9_value           DOUBLE PRECISION NOT NULL DEFAULT 0,  -- CO, gas mudah terbakar
    mq2_value           DOUBLE PRECISION NOT NULL DEFAULT 0,  -- LPG, hidrogen, asap
    stress_type         TEXT NOT NULL DEFAULT 'unknown',      -- hasil klasifikasi AI
    confidence_score    DOUBLE PRECISION NOT NULL DEFAULT 0,  -- probabilitas 0.0-1.0
    recommended_action  TEXT NOT NULL DEFAULT '',             -- rekomendasi tindakan
    raw_payload         JSONB,                                -- payload MQTT asli dari ESP32
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_voc_zone_ts
    ON voc_readings (zone_id, timestamp DESC);

-- ============================================================================
-- Enable Realtime untuk sensor_readings (sensor update → dashboard live)
-- ============================================================================
ALTER PUBLICATION supabase_realtime ADD TABLE sensor_readings;
ALTER PUBLICATION supabase_realtime ADD TABLE alerts;
ALTER PUBLICATION supabase_realtime ADD TABLE voc_readings;

-- ============================================================================
-- PGVECTOR SETUP (opsional — untuk semantic vector search di RAG)
-- ============================================================================
-- Jalankan bagian ini TERPISAH setelah tabel di atas sudah dibuat.
-- Memerlukan hak superuser di Supabase (tersedia di semua tier gratis).
--
-- Langkah:
--   1. Jalankan dulu semua CREATE TABLE di atas
--   2. Paste dan jalankan SQL di bawah ini secara terpisah di SQL Editor
-- ============================================================================

-- Aktifkan ekstensi pgvector
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Tambah kolom embedding ke knowledge_chunks (768 dimensi = Gemini text-embedding-004)
-- ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Index IVFFlat untuk approximate nearest neighbor search (cosine distance)
-- Jalankan setelah ada minimal 1 baris data di tabel
-- CREATE INDEX IF NOT EXISTS idx_chunks_embedding
--     ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 50);

-- Fungsi RPC untuk similarity search (dipakai oleh supabase-py)
-- CREATE OR REPLACE FUNCTION match_knowledge_chunks(
--     query_embedding vector(768),
--     match_count     int DEFAULT 5
-- )
-- RETURNS TABLE (id bigint, content text, similarity float)
-- LANGUAGE sql STABLE AS $$
--     SELECT id, content,
--            1 - (embedding <=> query_embedding) AS similarity
--     FROM knowledge_chunks
--     WHERE embedding IS NOT NULL
--     ORDER BY embedding <=> query_embedding
--     LIMIT match_count;
-- $$;
