-- All state lives here. /audit/v1/reset truncates every table and reseeds.

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    branding  JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sports (
    sport_id   TEXT PRIMARY KEY,
    config     JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Leagues: seeded tenant leagues and leagues registered through /audit/v1/leagues.
CREATE TABLE IF NOT EXISTS leagues (
    league_id  TEXT PRIMARY KEY,
    tenant_id  TEXT,
    sport_id   TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    config     JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clubs (
    club_id   TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    league_id TEXT,
    name      TEXT NOT NULL,
    profile   JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    club_id   TEXT,
    name      TEXT NOT NULL,
    profile   JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL,
    tenant_id     TEXT,
    league_id     TEXT,
    club_id       TEXT,
    player_id     TEXT
);

-- Match streams (league fixtures or stand-alone match_init).
CREATE TABLE IF NOT EXISTS matches (
    match_id          TEXT PRIMARY KEY,
    sport_id          TEXT NOT NULL,
    league_id         TEXT,
    home_team_id      TEXT NOT NULL,
    away_team_id      TEXT NOT NULL,
    created_by_init   BOOLEAN NOT NULL DEFAULT FALSE,
    scheduled_at      TEXT,
    venue             TEXT,
    pinned_product_id TEXT,
    ord               BIGSERIAL
);

-- Append-only event log. Rows are never updated or deleted (except by /reset).
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    match_id   TEXT NOT NULL,
    sequence   INTEGER NOT NULL,
    event_id   TEXT NOT NULL UNIQUE,
    type       TEXT NOT NULL,
    payload    JSONB NOT NULL,
    body_hash  TEXT NOT NULL,
    signature  TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (match_id, sequence)
);

-- Roster scenarios (/audit/v1/roster/*).
CREATE TABLE IF NOT EXISTS roster_leagues (
    league_id TEXT PRIMARY KEY,
    config    JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS squads (
    league_id TEXT NOT NULL,
    squad_id  TEXT NOT NULL,
    club_id   TEXT,
    tenant_id TEXT,
    name      TEXT,
    PRIMARY KEY (league_id, squad_id)
);

CREATE TABLE IF NOT EXISTS registrations (
    league_id         TEXT NOT NULL,
    player_id         TEXT NOT NULL,
    name              TEXT,
    position          TEXT,
    squad_id          TEXT,
    parent_squad_id   TEXT,
    role              TEXT,
    registration_type TEXT,
    start_date        TEXT,
    loan_end_date     TEXT,
    ord               BIGSERIAL,
    PRIMARY KEY (league_id, player_id)
);

CREATE TABLE IF NOT EXISTS roster_live_matches (
    league_id     TEXT NOT NULL,
    match_id      TEXT NOT NULL,
    home_squad_id TEXT,
    away_squad_id TEXT
);

CREATE TABLE IF NOT EXISTS roster_audit (
    seq        BIGSERIAL PRIMARY KEY,
    audit_id   TEXT NOT NULL UNIQUE,
    league_id  TEXT NOT NULL,
    player_id  TEXT NOT NULL,
    entry      JSONB NOT NULL,
    return_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS roster_requests (
    request_id TEXT PRIMARY KEY,
    league_id  TEXT,
    body_hash  TEXT NOT NULL,
    response   JSONB NOT NULL
);

-- Store.
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    club_id    TEXT,
    data       JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS variants (
    variant_id  TEXT PRIMARY KEY,
    product_id  TEXT NOT NULL,
    price_minor BIGINT NOT NULL,
    currency    TEXT NOT NULL DEFAULT 'PKR',
    stock       INTEGER NOT NULL CHECK (stock >= 0),
    reserved    INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    attributes  JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS discount_codes (
    code    TEXT PRIMARY KEY,
    percent INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id    TEXT PRIMARY KEY,
    body_hash   TEXT NOT NULL,
    customer_id TEXT,
    status      TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    response    JSONB NOT NULL,
    pdf         BYTEA,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_events (
    id         BIGSERIAL PRIMARY KEY,
    order_id   TEXT NOT NULL,
    from_state TEXT,
    to_state   TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Offline sync results, keyed by (device_id, action_id).
CREATE TABLE IF NOT EXISTS sync_actions (
    device_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    result    JSONB NOT NULL,
    PRIMARY KEY (device_id, action_id)
);

-- ================================================================ Phase II

ALTER TABLE matches ADD COLUMN IF NOT EXISTS status_override TEXT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS live_stream_key TEXT;

-- Creator stream keys. At most one active key per player.
CREATE TABLE IF NOT EXISTS stream_keys (
    stream_key TEXT PRIMARY KEY,
    player_id  TEXT NOT NULL,
    label      TEXT NOT NULL,
    status     TEXT NOT NULL,
    seq        BIGSERIAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS stream_keys_one_active ON stream_keys (player_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS costream_sessions (
    session_id TEXT PRIMARY KEY,
    body_hash  TEXT NOT NULL,
    state      JSONB NOT NULL,
    response   JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dynamic QR: the short code never changes, the target route is computed at scan time.
CREATE TABLE IF NOT EXISTS qr_codes (
    entity_id   TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    short_code  TEXT NOT NULL UNIQUE,
    scan_count  BIGINT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Privacy-safe scan telemetry (NFR-9): no IP address, no user agent, no cookies.
CREATE TABLE IF NOT EXISTS qr_scan_stats (
    entity_id     TEXT NOT NULL,
    device_family TEXT NOT NULL,
    bucket        TEXT NOT NULL,
    count         BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (entity_id, device_family, bucket)
);

CREATE TABLE IF NOT EXISTS guest_tokens (
    guest_token     TEXT PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    cart            JSONB NOT NULL DEFAULT '[]',
    merged_user_id  TEXT,
    merged_hash     TEXT,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS carts (
    user_id    TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    ord        BIGSERIAL,
    PRIMARY KEY (user_id, variant_id)
);

CREATE TABLE IF NOT EXISTS chat_rooms (
    chat_room_id TEXT PRIMARY KEY,
    seq          BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_messages (
    chat_room_id TEXT NOT NULL,
    seq          BIGINT NOT NULL,
    message_id   TEXT NOT NULL,
    sender       TEXT NOT NULL,
    text         TEXT NOT NULL,
    flagged      BOOLEAN NOT NULL,
    reason       TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_room_id, seq)
);

CREATE TABLE IF NOT EXISTS moderation_state (
    chat_room_id TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    kind         TEXT NOT NULL,
    ord          BIGSERIAL,
    PRIMARY KEY (chat_room_id, user_id, kind)
);

-- Dead-letter queue for notifications that failed after the bounded retries.
CREATE TABLE IF NOT EXISTS dlq (
    id         BIGSERIAL PRIMARY KEY,
    event_id   TEXT NOT NULL UNIQUE,
    type       TEXT NOT NULL,
    target     TEXT,
    payload    JSONB NOT NULL DEFAULT '{}',
    attempts   INTEGER NOT NULL,
    last_error TEXT,
    failed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follows (
    follower_id TEXT NOT NULL,
    athlete_id  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (follower_id, athlete_id)
);

CREATE TABLE IF NOT EXISTS vods (
    vod_id     TEXT PRIMARY KEY,
    stream_key TEXT NOT NULL,
    player_id  TEXT,
    object_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
