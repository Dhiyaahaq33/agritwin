-- ============================================================================
-- AgriTwin Database Schema (PostgreSQL / Supabase)
-- Version: 1.0  |  Date: 30 May 2026
-- Evolusi dari agribot_historian.db (SQLite) → PostgreSQL multi-tenant
-- ============================================================================

-- ─── EXTENSIONS ──────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS "vector";         -- pgvector for RAG embeddings
CREATE EXTENSION IF NOT EXISTS "timescaledb";    -- optional: time-series optimization

-- ============================================================================
-- DOMAIN 1: IDENTITY & MULTI-TENANCY
-- ============================================================================

-- Organizations (tenant root) ------------------------------------------------
CREATE TABLE organizations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    plan            TEXT NOT NULL DEFAULT 'free'      -- free | pro | enterprise
                    CHECK (plan IN ('free','pro','enterprise')),
    country_code    CHAR(2) NOT NULL DEFAULT 'ID',
    currency        CHAR(3) NOT NULL DEFAULT 'IDR',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users (links to Supabase auth.users) ---------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY,                 -- = auth.users.id
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email           TEXT NOT NULL UNIQUE,
    full_name       TEXT,
    role            TEXT NOT NULL DEFAULT 'operator'  -- owner | operator | viewer
                    CHECK (role IN ('owner','operator','viewer')),
    locale          TEXT NOT NULL DEFAULT 'id',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

-- ============================================================================
-- DOMAIN 2: PHYSICAL ASSETS (Greenhouse → Zone → Planting)
-- ============================================================================

-- Greenhouses ----------------------------------------------------------------
CREATE TABLE greenhouses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    facility_code   TEXT NOT NULL,                    -- e.g. "GH-INDO-01"
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    altitude_m      DOUBLE PRECISION DEFAULT 0,
    area_m2         DOUBLE PRECISION NOT NULL,
    structure_type  TEXT DEFAULT 'standard',          -- standard | hydroponic | aeroponic
    province        TEXT,
    city            TEXT,
    timezone        TEXT DEFAULT 'Asia/Jakarta',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, facility_code)
);

-- Crops master (reference data, 100+ Indonesian crops) -----------------------
CREATE TABLE crops (
    id              TEXT PRIMARY KEY,                 -- e.g. "tomat", "selada"
    name_id         TEXT NOT NULL,                    -- Bahasa Indonesia
    name_en         TEXT,
    category        TEXT NOT NULL,                    -- HORTIKULTURA, BUAH, etc.
    dap_harvest     INTEGER,                          -- days to harvest
    optimal_temp_c  DOUBLE PRECISION,
    optimal_humidity DOUBLE PRECISION,
    altitude_min_m  INTEGER,
    altitude_max_m  INTEGER,
    water_total_mm  DOUBLE PRECISION,                 -- lifecycle water need
    n_kg_ha         DOUBLE PRECISION,                 -- nitrogen requirement
    p_kg_ha         DOUBLE PRECISION,
    k_kg_ha         DOUBLE PRECISION,
    yield_ton_ha_min DOUBLE PRECISION,
    yield_ton_ha_max DOUBLE PRECISION,
    sim_crop_type   TEXT                              -- maps to simulation engine
);

-- Zones (subdivisions of a greenhouse) ---------------------------------------
CREATE TABLE zones (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    greenhouse_id   UUID NOT NULL REFERENCES greenhouses(id) ON DELETE CASCADE,
    zone_code       TEXT NOT NULL,                    -- e.g. "ZONE-A"
    area_m2         DOUBLE PRECISION NOT NULL,
    crop_id         TEXT REFERENCES crops(id),
    target_flow_lpm DOUBLE PRECISION DEFAULT 2.5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, zone_code)
);

-- Plantings (a crop cycle in a zone) -----------------------------------------
CREATE TABLE plantings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    zone_id         UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    crop_id         TEXT NOT NULL REFERENCES crops(id),
    planted_date    DATE NOT NULL,
    expected_harvest_date DATE,
    actual_harvest_date   DATE,
    area_ha         DOUBLE PRECISION NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'    -- active | harvested | failed
                    CHECK (status IN ('active','harvested','failed')),
    yield_kg        DOUBLE PRECISION,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- DOMAIN 3: TIME-SERIES TELEMETRY (the high-volume tables)
-- Migrated & expanded from SQLite: sensor_readings, flow_meter_log,
--                                   actuator_events, alerts, vernalization_log
-- ============================================================================

-- Sensor readings (hypertable candidate) -------------------------------------
CREATE TABLE sensor_readings (
    id              BIGSERIAL,
    zone_id         UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    param           TEXT NOT NULL,                    -- temperature|humidity|co2|soil_moisture|ph|ec|light|root_temp
    value           DOUBLE PRECISION NOT NULL,
    unit            TEXT,
    source          TEXT NOT NULL DEFAULT 'sensor'    -- sensor | sim | manual
                    CHECK (source IN ('sensor','sim','manual')),
    quality         TEXT DEFAULT 'good',              -- good | suspect | bad
    PRIMARY KEY (id, ts)
);
-- SELECT create_hypertable('sensor_readings', 'ts');  -- if TimescaleDB
CREATE INDEX idx_sensor_zone_param_ts ON sensor_readings (zone_id, param, ts DESC);

-- Flow meter log (drip irrigation) -------------------------------------------
CREATE TABLE flow_meter_log (
    id              BIGSERIAL,
    zone_id         UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    flow_lpm        DOUBLE PRECISION NOT NULL,        -- actual L/min
    target_lpm      DOUBLE PRECISION NOT NULL,
    pressure_bar    DOUBLE PRECISION,
    status          TEXT NOT NULL DEFAULT 'normal'    -- normal | clog | leak | dry_run
                    CHECK (status IN ('normal','clog','leak','dry_run')),
    PRIMARY KEY (id, ts)
);
CREATE INDEX idx_flow_zone_ts ON flow_meter_log (zone_id, ts DESC);

-- Actuator events (commands sent to hardware) --------------------------------
CREATE TABLE actuator_events (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    actuator        TEXT NOT NULL,                    -- valve|led|fan|pump|heater
    value           DOUBLE PRECISION NOT NULL,        -- pwm / on-off / setpoint
    triggered_by    TEXT NOT NULL DEFAULT 'auto'      -- auto | manual | ai | schedule
);

-- Vernalization log (cold-hour accumulation) ---------------------------------
CREATE TABLE vernalization_log (
    id              BIGSERIAL PRIMARY KEY,
    planting_id     UUID REFERENCES plantings(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    temp_c          DOUBLE PRECISION,
    cold_hours      DOUBLE PRECISION,
    target_hours    DOUBLE PRECISION
);

-- ============================================================================
-- DOMAIN 4: ALERTS & NOTIFICATIONS
-- ============================================================================

-- Alert rules (user-configured thresholds) -----------------------------------
CREATE TABLE alert_rules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    zone_id         UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    param           TEXT NOT NULL,
    min_value       DOUBLE PRECISION,
    max_value       DOUBLE PRECISION,
    severity        TEXT NOT NULL DEFAULT 'warning'   -- info | warning | critical
                    CHECK (severity IN ('info','warning','critical')),
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Alerts (fired events) ------------------------------------------------------
CREATE TABLE alerts (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    rule_id         UUID REFERENCES alert_rules(id) ON DELETE SET NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    param           TEXT,
    value           DOUBLE PRECISION,
    acknowledged    BOOLEAN NOT NULL DEFAULT false,
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ
);
CREATE INDEX idx_alerts_zone_ack ON alerts (zone_id, acknowledged, ts DESC);

-- Notification channels (per org config) -------------------------------------
CREATE TABLE notification_channels (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    channel_type    TEXT NOT NULL                     -- telegram | whatsapp | email
                    CHECK (channel_type IN ('telegram','whatsapp','email')),
    config          JSONB NOT NULL,                   -- {chat_id, token_ref, ...} (no secrets!)
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Notification log -----------------------------------------------------------
CREATE TABLE notification_log (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      UUID REFERENCES notification_channels(id) ON DELETE SET NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    recipient       TEXT,
    message         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'sent'      -- sent | failed | queued
);

-- ============================================================================
-- DOMAIN 5: WEATHER (Open-Meteo cache)
-- ============================================================================

CREATE TABLE weather_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    greenhouse_id   UUID NOT NULL REFERENCES greenhouses(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    forecast_for    TIMESTAMPTZ NOT NULL,             -- the time this forecast targets
    temp_c          DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    wind_ms         DOUBLE PRECISION,
    solar_wm2       DOUBLE PRECISION,
    source          TEXT DEFAULT 'open-meteo',
    is_forecast     BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX idx_weather_gh_ts ON weather_snapshots (greenhouse_id, forecast_for DESC);

-- ============================================================================
-- DOMAIN 6: AI & KNOWLEDGE (RAG with pgvector)
-- ============================================================================

-- Knowledge base documents (agronomy corpus) ---------------------------------
CREATE TABLE knowledge_documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    source          TEXT,                             -- BPPT, BMKG, literature, etc.
    content         TEXT NOT NULL,
    language        TEXT DEFAULT 'id',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Document chunks with embeddings --------------------------------------------
CREATE TABLE knowledge_chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_text      TEXT NOT NULL,
    embedding       VECTOR(768),                      -- Gemini text-embedding dim
    chunk_index     INTEGER
);
CREATE INDEX idx_chunks_embedding ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- AI conversation log --------------------------------------------------------
CREATE TABLE ai_queries (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    zone_id         UUID REFERENCES zones(id) ON DELETE SET NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    query_type      TEXT,                             -- agronomist | plant_doctor | general
    prompt          TEXT NOT NULL,
    response        TEXT,
    llm_provider    TEXT,                             -- gemini | claude | groq
    latency_ms      INTEGER,
    image_url       TEXT                              -- for plant doctor
);

-- ============================================================================
-- DOMAIN 7: ECONOMICS & MARKETPLACE
-- ============================================================================

-- Market prices (cached from PIHPS BI / SP2KP) -------------------------------
CREATE TABLE market_prices (
    id              BIGSERIAL PRIMARY KEY,
    crop_id         TEXT REFERENCES crops(id),
    region          TEXT,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    price_per_kg    DOUBLE PRECISION NOT NULL,
    currency        CHAR(3) DEFAULT 'IDR',
    source          TEXT                              -- pihps_bi | sp2kp | world_bank
);

-- Carbon MRV records ---------------------------------------------------------
CREATE TABLE carbon_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    greenhouse_id   UUID NOT NULL REFERENCES greenhouses(id) ON DELETE CASCADE,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    energy_kwh      DOUBLE PRECISION,
    water_l         DOUBLE PRECISION,
    co2_kg          DOUBLE PRECISION,
    sequestered_kg  DOUBLE PRECISION,
    net_carbon_kg   DOUBLE PRECISION,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- DOMAIN 8: AUDIT TRAIL (blockchain-style, from GreenChain)
-- ============================================================================

CREATE TABLE audit_blocks (
    id              BIGSERIAL PRIMARY KEY,
    block_index     INTEGER NOT NULL,
    greenhouse_id   UUID REFERENCES greenhouses(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type      TEXT NOT NULL,                    -- sensor|actuator|milestone|alert|chemical
    data            JSONB NOT NULL,
    prev_hash       TEXT NOT NULL,
    hash            TEXT NOT NULL,
    nonce           INTEGER DEFAULT 0
);
CREATE INDEX idx_audit_gh_index ON audit_blocks (greenhouse_id, block_index);

-- ============================================================================
-- ROW-LEVEL SECURITY (multi-tenant isolation)
-- ============================================================================

ALTER TABLE greenhouses ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON greenhouses
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- (repeat similar policies for zones, plantings, sensor_readings, etc.)

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
