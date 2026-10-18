# NaSCon '26 Part II: Day 2 Implementation Plan

Live streaming, dynamic QR deep-linking, guest web player and automated grid QA
Day 2 sprint: Sun 18 Oct 2026, 10:15 to 14:00 PKT (hard lock 14:05:00). Weight: 80% backend + QA infra, 20% frontend.
Day 1 plan: see `PLAN.md` at commit `596c2bc` (the locked `DAY1_BASE_SHA`).

---

## 0. Ground rules (lose points if broken)

| Rule | Guard |
|---|---|
| Phase I ancestry: `git merge-base --is-ancestor 596c2bc HEAD` | Commit on `main` on top of history. Never force-push, rebase or re-init |
| One push in each window: W1 10:15-11:30, W2 11:30-12:45, W3 12:45-13:45, W4 13:45-14:05:00 | Push targets in Section 9. Grader takes the last commit at or before 14:05:00 |
| `DAY2_SALT` (and `DAY1_SALT`) only from env | `config.DAY2_SALT = os.environ[...]`. `grep` for the slip salt before every push. `.env` git-ignored |
| No client-only security | Guest write block is server-side middleware (403 `GUEST_WRITE_FORBIDDEN`). UI hiding is cosmetic |
| `docker compose up -d --build` healthy within 120 s, `GET /health` = 200 `{"status":"ok"}` | Pinned images, healthchecks, light API image, CI pre-pull |
| Exact ports | 8080 API+web, 4444 grid, 4723 appium, 1935 RTMP, 8888 HLS, 8889 WebRTC |
| Day 1 regression pass | Run `RUN_INTEGRATION=1 ./run_tests.sh` before every push. Do not change Day 1 response shapes |

---

## 1. What exists (Phase I) and what we reuse

- **Backend** `backend/app` (FastAPI, Python 3.12, 1 Uvicorn worker), PostgreSQL 16, Redis 7 (Streams), `worker` container.
  - `crypto.py`: `canonical()` + `sign(id, payload, salt)`. Add `sign_day2()` that uses `DAY2_SALT`.
  - `errors.py`: envelope, `validation()`, `not_found()`, `conflict()`. Reuse for every new error.
  - `http.py`: `read_object()` gives 400 on malformed JSON and 413 over 1 MB.
  - `db.tx()`, `db.lock(cur, key)` (advisory xact lock). Use for every new concurrency guard.
  - `services/matches.py`: event log with `match_start` / `score` / `match_end`. `Log.status` = upcoming / in_progress / completed.
  - `services/realtime.py`: in-process pub/sub. `publish_match()` currently sends only `{"type":"match_updated"}`.
  - `services/store.py`: variants, stock, prices (`var-jersey-001-M/L` @ 450000).
  - `routes/api.py`: `/api/v1/*` (JWT, rate limited), `WS /ws/matches/{id}?token=` (JWT required today).
  - `seed.py` + `seed/baseline.json`: Day 1 baseline. **`player-beta-2` is missing and must be added.**
- **Mobile** `mobile/` (Kotlin, Compose, Room, OkHttp, Navigation). `MainActivity` has a 1.6 s splash, then Login or Main. No deep links yet.
- **Tests**: `tests/unit` (pure domain), `tests/integration` (live HTTP), `tests/coverage_report.py` writes `COVERAGE.json`.
- **Local tools available**: docker + compose v5, k6, adb, ffmpeg, appium, node 24, Android SDK + emulator, 12 cores / 18 GB.

---

## 2. Target architecture

```
                      docker compose (single host, also the CI runner)
 Browser / phone ─► api :8080  FastAPI  /health /audit/v1/* /api/v1/* /web/* /q/* /metrics /ws/*
                     │   ├─► postgres:16   (all state incl. Phase II tables)
                     │   ├─► redis:7       (domain-events stream, DLQ stream, pub/sub, counters)
                     │   ├─► mediamtx API :9997 (kick publishers on revoke, read bitrate)
                     │   └─► minio :9000  (VOD objects)
                     worker  (domain events, notification retry ×3 → DLQ, VOD upload)
 OBS/FFmpeg/app ──► mediamtx  RTMP :1935  HLS :8888  WebRTC WHIP/WHEP :8889
                     │  auth → POST api:8080/internal/media/auth (stream key must be active)
                     │  costream/{id} → runOnDemand ffmpeg compositor (xstack) → HLS
                     └  record → /recordings → worker → MinIO + vods table
 selenium-hub :4444 + node-chrome-1, node-chrome-2, node-firefox (shm 1gb, no VNC)
 appium :4723 (laptop 2 + phone, not in compose)       k6 → tests/k6_load.js
```

Design rules:
1. **New logic goes in pure domain modules** (`domain/streaming.py`, `costream.py`, `qr.py`, `guest.py`, `moderation.py`, `dlq.py`, `metrics.py`) with unit tests. This keeps coverage at 85% or more with real numbers. Services do I/O and routes stay thin, same as Day 1.
2. **No new in-process state.** Everything lives in Postgres or Redis, so we can switch Uvicorn to 4 workers if k6 needs it (Section 7.3).
3. **Every signed response** builds `sig_payload` exactly as spec 5.3. Unit tests check the Appendix A vector with salt `T01D27ad7ffff12e`.
4. Validation order on every route: 400 schema → 404 entity → 403 permission → 409 business rule.

---

## 3. Data model additions (`schema.sql`, all truncated by `/reset`)

```sql
stream_keys      (stream_key PK, player_id, label, status active|revoked|rotated, created_at, revoked_at)
                 + UNIQUE INDEX one_active_key ON stream_keys(player_id) WHERE status='active'
costream_sessions(session_id PK, body_hash, host_player_id, participants JSONB, active_participants JSONB,
                  active_host, layout, status, handoff_occurred, chat_room_id, response JSONB, updated_at)
qr_codes         (entity_id PK, entity_type, short_code UNIQUE, scan_count BIGINT, created_at)
qr_scan_stats    (entity_id, device_family mobile|desktop, bucket TEXT 'YYYY-MM-DDTHH:00Z', count, PK(all 3))  -- no IP/UA/cookies
guest_tokens     (guest_token PK, created_at, expires_at, cart JSONB, merged_user_id, merged_hash, merged_response JSONB,
                  revoked BOOL)
carts            (user_id, variant_id, quantity, PK(user_id, variant_id))
chat_rooms       (chat_room_id PK, seq BIGINT)            -- monotonic sequence via UPDATE ... RETURNING
chat_messages    (chat_room_id, seq, message_id, sender, text, flagged, reason, created_at, PK(room, seq))
moderation_state (chat_room_id, user_id, kind kicked|muted, ord BIGSERIAL, PK(room, user, kind))  -- ON CONFLICT DO NOTHING
dlq              (id BIGSERIAL, event_id UNIQUE, type, target, payload JSONB, attempts, last_error, failed_at)
follows          (follower_id, athlete_id, created_at, PK(follower_id, athlete_id))
vods             (vod_id PK, stream_key, player_id, object_key, started_at, ended_at, duration_s)
matches          + status_override TEXT NULL (postponed|cancelled|abandoned), + live_stream_key TEXT NULL
```
Add all new tables to `db.TABLES`.

### 3.1 Reset seed extensions (`seed.reset`, spec 5.2)
- Add `player-beta-2` (tenant-beta, club-beta-1) to `baseline.json`.
- `match-m1`: football, league-alpha-1, home club-alpha-1, away club-alpha-2. Build it through `_append`: `match_start` + one `goal` for club-alpha-1 gives in_progress, 1-0.
  - Check: Day 1 standings for league-alpha-1 only count completed matches. Confirm demo standings are unchanged.
- QR: `match-m1 → m1-live`, `player-alpha-1 → p-alpha-1`, `club-alpha-1 → c-alpha-1`, all with `scan_count 0`.
- Guest token `guest_anon_tok_7721` (valid, not merged). Empty cart for `player-alpha-1`. DLQ empty. No stream keys, no costream sessions.
- Reset also clears Redis Phase II keys (DLQ stream, moderation windows, ws counters) and kicks MediaMTX publishers (best effort).

---

## 4. Backend: endpoint-by-endpoint (the 80%)

New files: `routes/day2.py` (audit), `routes/web.py` (`/web/*`, `/q/*`), `routes/media.py` (`/internal/media/*`), plus services and domain modules per area.

### 4.0 Platform
- `config.py`: `DAY2_SALT`, `MEDIAMTX_API=http://mediamtx:9997`, `MINIO_*`, `PUBLIC_BASE=http://localhost:8080`, `MEDIA_HLS_BASE=http://localhost:8888`, `MEDIA_RTMP_BASE=rtmp://localhost:1935`, `MEDIA_WEBRTC_BASE=http://localhost:8889`.
- `crypto.sign_day2(entity_id, payload)` uses `DAY2_SALT` (UTF-8, no trim or hex-decode).
- `/health`: DB + seeded flag + Redis ping are required. MediaMTX is checked with a 0.5 s timeout and logged only, so a slow media container cannot fail boot. Body stays exactly `{"status":"ok"}`.
- Convert the two `@app.middleware("http")` handlers to pure ASGI middleware (cheaper under k6). Rate-limit exemptions: `/api/v1/guest/*` and `/api/v1/matches/*/stream`.
- **Guest write guard (ASGI middleware, runs before validation):** any `POST/PUT/PATCH/DELETE` whose `Authorization: Bearer` starts with `guest_` returns 403. Allow-list: `POST /api/v1/guest/session`, `POST /api/v1/guest/cart` (local staging). Response:
  `{"error":{"code":"GUEST_WRITE_FORBIDDEN","message":"Anonymous guest tokens cannot perform write mutations.","details":{"guest_token":"<tok>"}}}`
  - This covers `POST /api/v1/chat`, `/audit/v1/checkout`, `/audit/v1/events` (spec 5.7 direct check) even with empty or invalid bodies.
  - `POST /api/v1/chat` with **no** token also returns 403 `GUEST_WRITE_FORBIDDEN` (unauthenticated guest session, FR-4.3).
  - `/audit/v1/*` without an Authorization header behaves as on Day 1.
  - Same check exposed as `guest.check_write(token) -> (status, code)` for the cart-merge simulation.

### 4.1 `POST /audit/v1/stream/key` (spec 5.4), module **streaming**
- Validate: `action ∈ {generate, rotate, revoke}`, `player_id` string, `label` optional 1-64 (default `"default"`), `stream_key_override` optional non-empty string.
  - Generated keys: `"sk_live_" + secrets.token_hex(8)` (matches `^sk_live_[a-f0-9]{16}$`).
- 404 `PLAYER_NOT_FOUND`. Under `db.lock("streamkey:"+player_id)`:
  - `generate` → 201. Invalidates any active key first.
  - `rotate` → 200. Old key becomes `rotated`, new key is `active`.
  - `revoke`: no key ever → 404 `STREAM_NOT_FOUND`. Latest key already revoked/rotated and no active key → 409 `KEY_REVOKED`. Otherwise mark revoked → 200 with `status:"revoked"`, `ingest_endpoints:null`, `playback_url:null`.
- Response: `player_id, label, stream_key, status, ingest_endpoints{rtmp: rtmp://localhost:1935/live/<k>, webrtc: http://localhost:8889/live/<k>/whip}, playback_url: http://localhost:8888/live/<k>/index.m3u8, signature`.
- Signature: `sign_day2(stream_key, {"action","player_id","status","stream_key"})`.
- **Revocation severs ingest within 2 s:** after commit, call MediaMTX API `GET /v3/rtmpconns/list`, `/v3/webrtcsessions/list`, `/v3/rtspsessions/list`, filter `path == live/<key>`, then `POST .../kick/{id}`. The worker also runs a 1 s sweeper as backup (publishers on non-active keys get kicked).
- `POST /internal/media/auth` (MediaMTX `authMethod: http`): `publish` on `live/<k>` is allowed only if the key is active, else 401 (logged as `KEY_REVOKED`). `costream/*` and `matchfeed/*` publish only from the internal network. `read` is always allowed.
- `GET /api/v1/streams/key/{key}` returns 409 `KEY_REVOKED` for a revoked key (API-level evidence for desk audit).

### 4.2 `POST /audit/v1/costream/session` (spec 5.5), module **costream**
- Pure `domain/costream.evaluate(body, existing_player_ids) -> state | raises`, checked in this exact order:
  1. Schema: `session_id` str, `host_player_id` str, `participants` non-empty list of unique str, `simulate_host_drop` bool (default false), `layout ∈ {solo, grid_2, grid_4, spotlight}` (default `grid_4`) → 400 `VALIDATION_ERROR` with `details.fields`.
  2. Every participant and the host exist → 404 `PLAYER_NOT_FOUND`. Host not in participants → 400 `VALIDATION_ERROR`.
  3. `len(participants) > 4` → 409 `COSTREAM_SESSION_FULL`.
  4. Effective count = `len-1` if drop and len≥2, `0` if drop and len==1, else `len`. `solo` and eff>1, or `grid_2` and eff>2 → 400 `UNSUPPORTED_LAYOUT`.
  5. Handoff: no drop → host stays, `handoff_occurred:false`. Drop and len≥2 → `active_host = remaining[0]`, true, count len-1, active. Drop and len==1 → `active_host:null`, false, 0, `terminated`, `active_participants:[]`.
- Persistence under `db.lock("costream:"+session_id)`:
  - New → 201.
  - Identical body (body hash) → 200 with stored response.
  - Same session, different body → apply as state transition (e.g. host drop on a live session) → 200. `chat_room_id` and `composite_playback_url` stay the same (hidden scenario 1).
- Response: `session_id, status, active_host, handoff_occurred, participant_count, active_participants, layout, composite_playback_url: http://localhost:8888/costream/<id>/index.m3u8, chat_room_id: "chat-<id>", signature`.
- Signature: `sign_day2(session_id, {"active_host","handoff_occurred","layout","participant_count","session_id","status"})`.
- Creates `chat_rooms` row `chat-<id>` and a QR mapping for `cs-session-*` ids. Publishes `costream_updated` on `costream:<id>`.
- **Real composition:** MediaMTX path `~^costream/(.+)$` with `runOnDemand: /scripts/composite.sh $G1`. The script reads `GET http://api:8080/internal/costream/<id>/layout` (active participants' active keys + layout) and runs ffmpeg `xstack` (`grid_2` hstack, `grid_4` 2x2, `spotlight` big + 3 thumbnails, `solo`). Missing feeds become `color` + `drawtext` slates. Output goes to `rtsp://localhost:8554/costream/<id>`.
  - Handoff or layout change: backend kicks the path publisher → MediaMTX restarts the process with the new layout.
  - MediaMTX owns the process lifecycle (`runOnDemandCloseAfter: 10s`, SIGINT on close), so no zombie ffmpeg.
  - Terminated session: layout endpoint returns 404 → script exits.
- WebSocket host disconnect: `WS /ws/costream/{id}?player_id=` tracks hosts. When the host socket drops, after 1.5 s grace run the same handoff transition (FR-3.3).

### 4.3 QR (spec 5.6), module **qr_guest**
- `GET /audit/v1/qr/{entity_id}[?inspect=true]`:
  - Mapping: look up `qr_codes`. If missing and the entity exists (match / club / player / costream), lazily create it with `short_code = base32(HMAC(DAY2_SALT, entity_id))[:8]`. Unknown → 404 `QR_NOT_FOUND`.
  - Without `inspect`: `UPDATE qr_codes SET scan_count = scan_count+1 RETURNING scan_count` (atomic), and return the **post-increment** value (example shows 1).
  - `entity_status`: match = `status_override` or the status derived from the log (store a cached `matches.status` column updated in `_append` so the k6 path is one PK query). Player/club = `active`. Costream = session status.
  - `target_route` (pure `qr.target_route(type, id, status)`): upcoming `/preview`, in_progress `/live`, completed `/vod`, postponed/cancelled/abandoned `/notice?state=<s>`, player `/web/players/<id>`, club `/web/clubs/<id>`, costream `/web/costream/<id>`.
  - Response: `entity_id, entity_type, entity_status, short_url, target_route, deep_link_uri: nascon://entity/<id>, scan_count, export_formats{svg,png,pdf}, signature`.
  - Signature: `sign_day2(entity_id, {"entity_id","short_url","target_route"})`. It is recomputed on every call, so it changes when the status changes (hidden scenario 2).
- `GET /audit/v1/qr/{id}/export.{svg|png|pdf}` using the `segno` library (pure Python):
  - svg `image/svg+xml` (body starts `<?xml`/`<svg`)
  - png `image/png` (8-byte magic)
  - pdf via fpdf2 poster: QR image + `entity_id` + short URL, `application/pdf`, starts `%PDF-`
  - Other fmt → 404 `QR_NOT_FOUND`.
- `GET /q/{short_code}`: 302 with a **relative** `Location: <target_route>` (works for localhost, `host.docker.internal` and LAN IP). Increments scan count and `qr_scan_stats` (device family from UA, then the UA is discarded). `?format=json` returns the JSON resolution. Unknown → 404 `QR_NOT_FOUND`.
- **Match status changes (hidden scenario 2):** `match_end` already gives completed. For postponed / cancelled / abandoned, accept new event types `match_postponed`, `match_cancelled`, `match_abandoned` and a generic `match_status` with `payload.status`, all on `/audit/v1/events`. They set `status_override`, are allowed from upcoming or in_progress, and are signed like other events. **Ask the organisers how the grader postpones a match.**

### 4.4 Guest access and `POST /audit/v1/guest/cart-merge` (spec 5.7), module **qr_guest**
- `POST /api/v1/guest/session` → `{guest_token:"guest_anon_tok_<12hex>", role:"guest", scopes:["playback","scores","cart_stage"], expires_at}` (2 h TTL).
- `GET /api/v1/guest/matches/{id}`, `GET /api/v1/guest/products/{id}`, `GET /api/v1/guest/chat/{room}` are read-only, take no auth or a guest token, and are not rate limited.
- `POST /api/v1/guest/cart` stages items on the guest token (allowed write, cart only).
- cart-merge rules, in order:
  1. Schema: `guest_token` starts with `guest_`, `registered_user_id` str, `guest_cart` 1-10 items `{variant_id str, quantity int≥1}`, `test_write_block` bool (default true) → 400.
  2. `registered_user_id` must exist in `players` or `users`, else 404 `PLAYER_NOT_FOUND`. Every variant must exist, else 404 `VARIANT_NOT_FOUND`.
  3. Under `db.lock("guestmerge:"+token)`: already merged → identical `(user, canonical cart)` returns 200 with the merged cart state, no re-add (hidden scenario 4). Different → 409 `GUEST_TOKEN_ALREADY_MERGED`.
  4. Stock: `existing_cart_qty + guest_qty > variants.stock` → 409 `OUT_OF_STOCK` `details.variant_id`. No reservation, so inventory is never double-reserved.
  5. `test_write_block`: run `guest.check_write(token)` → `write_block_verified:true, write_rejection_code:403`. If false: `write_block_verified:false`, code still 403 (deterministic, typed int). **Confirm with organisers.**
  6. Upsert into `carts` (sum quantities), mark token merged (`merged_user_id`, hash, response), same tx.
- Response 200: `guest_token, write_block_verified, write_rejection_code, cart_merged:true, active_cart{user_id, currency:"PKR", total_items, subtotal_minor, items[{variant_id, quantity, unit_price_minor}]}, signature`.
- Signature: `sign_day2(guest_token, {"cart_merged","guest_token","registered_user_id","total_items","write_rejection_code"})`.
- Member route `POST /api/v1/cart/merge` (JWT + `guest_token` in body) uses the same service. The web modal calls it after login.

### 4.5 Chat, moderation and DLQ (spec 5.8), module **moderation_dlq**
- Pure `domain/moderation.moderate(messages) -> filtered, kicked, muted`:
  - Normalise per whitespace token: lowercase, map `@→a 0→o 1→i !→i 3→e $→s`, strip `_ . - / * ` and zero-width chars. Characters with two readings (`! 1 |`) are tried as mapped and as stripped (so `s!c@m` → `scam`, `sh1t` → `shit`).
  - Dictionary: `badword, porn, scam, fuck, shit, bitch, asshole, idiotspam`. A normalised token containing a dictionary word becomes `***`; trailing punctuation is kept (`now!` stays).
  - Profanity → kept, `flagged:true, reason:"profanity_leetspeak"`, sender appended to `kicked_users` (dedup, order of violation).
  - Flood: `(.)\1{3,}` case-insensitive **or** `[!?]{3,}` → dropped from `filtered_messages`, sender to `muted_users`. Flood is checked first (dropped wins).
  - Clean → unchanged, `flagged:false, reason:null`.
  - Rate limit (>3 messages per sender in 2 s) is applied on the live `/api/v1/chat` path with Redis windows. In the probe it applies only within one batch, so vectors stay deterministic.
- `POST /audit/v1/moderation/test`:
  - Validate `chat_room_id` str and `incoming_messages` list of `{message_id, sender, text}` str, `check_dlq` bool, `simulate_failed_notifications` int ≥0.
  - Unknown rooms are **not** 404 (k6 posts to `chat-cs-session-101` without creating it).
  - Persist kicked/muted with `INSERT ... ON CONFLICT DO NOTHING` (no deadlocks, no duplicates under the 10-thread race, hidden scenario 3). The response lists are per request, deduplicated.
  - DLQ: N > 0 → insert N failed notification rows (`attempts:3`, `last_error`, simulated backoff 0.1/0.2/0.4 s recorded, not slept) in one tx. Then read `queue_depth = COUNT(*)` and `undelivered_events` (latest 50: `event_id, type, target, attempts, last_error, failed_at`).
  - Response: `chat_room_id, filtered_messages, kicked_users, muted_users, dlq_status{queue_depth, undelivered_events}, signature`.
  - Signature: `sign_day2(chat_room_id, {"chat_room_id","flagged_count","kicked_users","queue_depth"})`, where `flagged_count` = number of flagged messages in `filtered_messages`.
  - Fast path for k6: clean batches do no writes beyond the DLQ count read.
- Live chat: `POST /api/v1/chat {chat_room_id, text}` (JWT member) → moderate → `seq` from `UPDATE chat_rooms SET seq=seq+1 RETURNING seq` → store → publish `chat:<room>`.
  - `GET /api/v1/guest/chat/{room}` returns history. `WS /ws/chat/{room}` and the SSE stream carry `{type:"chat", seq, ...}`.
- Notification bus (FR-5.2): score updates, co-stream invites and order status changes go to Redis Stream `notifications`. The worker delivers (webhook/push stub). On failure it retries 3× with exponential backoff, then writes to `dlq` (also `simulate_dlq:true` on a notification forces failure). Order status events already exist on `domain-events`.

### 4.6 Realtime (NFR-1)
- `realtime.publish_match` sends the full score: `{type:"score", match_id, status, home{team_id,score}, away{team_id,score}, version}`, so the browser updates without a refetch (<500 ms).
- `WS /ws/matches/{id}`: token becomes **optional** (JWT, guest token or none) because subscribing is read-only and the NFR-1 25-client probe may not send one. Reject only a malformed JWT.
- New `GET /api/v1/matches/{id}/stream` (SSE, `text/event-stream`, 15 s keep-alive comments) carries the same messages. It also carries chat for `chat-<match_id>`.
- Connection gauge: increment and decrement around WS/SSE handlers (Redis `INCR` so it works with multiple workers).

### 4.7 `GET /metrics` and privacy (spec 5.9), module **observability**
- `domain/metrics.render(samples)` produces Prometheus text with `# HELP` / `# TYPE`:
  - `nascon_active_ws_connections` gauge
  - `nascon_active_streams_total` gauge (MediaMTX `/v3/paths/list` ready paths, fallback: active keys)
  - `nascon_stream_bitrate_kbps{stream=...}` gauge (bytesReceived delta from MediaMTX). Always emit an unlabeled `0` line when no streams.
  - `nascon_dlq_depth` gauge
  - `nascon_qr_scans_total` counter (sum of `scan_count`)
- Header set raw to exactly `Content-Type: text/plain; version=0.0.4`. Starlette would append `; charset=utf-8`, so build the `Response` and override the header.
- `DELETE /audit/v1/privacy/user/{user_id}` (accepts player or user id, unknown → 404 `PLAYER_NOT_FOUND`):
  - In one tx: scrub `players.name/profile` and `users.email/name` (→ `anon-<sha8>`), delete follows, revoke stream keys, delete or unlink guest tokens merged into this user and their cart, null chat `sender` → `anon-<sha8>`.
  - Returns 200 `{"user_id","status":"anonymized","pii_retained":false,"tokens_wiped":true}`. Idempotent.
- NFR-9: `qr_scan_stats` has no IP, UA or cookie columns, and the access log is disabled for `/q/*`.

### 4.8 FR-3.1 athlete profile and follow (not in the audit contract; do it after 4.1-4.7)
- `GET /api/v1/players/{id}/profile`: career records from the event log (matches played by the player's club, goals), clubs, upcoming fixtures, VOD list, `follower_count`.
- `POST|DELETE /api/v1/players/{id}/follow`: `INSERT ... ON CONFLICT DO NOTHING` / `DELETE`. Idempotent per pair, the count is `COUNT(*)` (no counter drift). Guest returns 403 via middleware.

---

## 5. Media server (MediaMTX) and storage

- Image `bluenviron/mediamtx:1.9.3-ffmpeg` (pin; has ffmpeg + busybox for the healthcheck). Config `media/mediamtx.yml`, scripts `media/composite.sh`, `media/slate.sh`. Ports `1935, 8888, 8889, 8189/udp`. API `9997` internal only.
- Key settings:
  - `authMethod: http`, `authHTTPAddress: http://api:8080/internal/media/auth`, `authHTTPExclude: [api, metrics]`
  - `hlsVariant: mpegts`, `hlsSegmentDuration: 1s`, `hlsAlwaysRemux: yes`
  - `webrtcAdditionalHosts: [127.0.0.1]` (plus LAN IP via env for phones)
  - `record: yes` on `live/*` → `/recordings/%path/%Y-%m-%d_%H-%M-%S` (fmp4)
- Paths:
  - `live/~^.+$` publishers (OBS, ffmpeg, phone)
  - `costream/~^.+$` runOnDemand compositor
  - `matchfeed/~^.+$` runOnDemand: if `matches.live_stream_key` is set, relay that key, else a test-pattern slate with the score text. This gives the guest player a playable stream for `match-m1` with no broadcaster.
- Low latency (<3 s glass-to-glass): the web player tries **WHEP** (`:8889/<path>/whep`) first and falls back to hls.js. The mobile app uses ExoPlayer LL-HLS.
- VOD: `runOnRecordSegmentComplete` + `runOnNotReady` call `POST api:8080/internal/media/recorded`. The worker uploads segments to MinIO bucket `vod`, inserts `vods`, and the match `/vod` page lists them.
- MinIO: `minio/minio:RELEASE.2024-10-13T13-34-11Z` + one-shot `minio/mc` init that creates the `vod` bucket (anonymous download). Volumes `minio-data`, `recordings`.

---

## 6. Guest Web Player (`/web/*`, part of the 20%)

- Served by FastAPI from `backend/app/web/` (static HTML/CSS/JS, no build step). **hls.js is vendored locally** (no CDN at grading). One HTML shell per page type, and JS reads the id from `location.pathname`.
  - `/web/matches/{id}/live|preview|vod|notice`, `/web/players/{id}`, `/web/clubs/{id}`, `/web/costream/{id}`
- On load: get or create the guest token (`localStorage`, else `POST /api/v1/guest/session`). No login wall, no install prompt.
  - `progressive-auth-modal` is in the DOM but `hidden` until a protected action.
- The 9 mandatory `data-testid`s are in the static markup (present before JS runs):
  - `guest-video-player` (`<video>` + container, WHEP then HLS of `matchfeed/<id>` or `costream/<id>`)
  - `live-score-banner` (text `"1 - 0"`, updated from SSE `score` messages)
  - `pinned-merch-card` (prod-jersey-001 / var-jersey-001-L)
  - `add-to-guest-cart-btn` (stages var-jersey-001-L ×1 → `POST /api/v1/guest/cart`, local count +1)
  - `guest-cart-count` (`"0"` → `"1"`)
  - `chat-message-list` (`role="log" aria-live="polite"`, masked text as `***`)
  - `chat-input-field`
  - `chat-send-btn` (sends with guest token → server 403 → message **not** appended → show modal)
  - `progressive-auth-modal` (`role="dialog" aria-modal="true"`, login form + register link)
- After login: `POST /api/v1/cart/merge` with the guest token, then return to the same page with `?t=<video.currentTime>` and seek.
- WCAG 2.1 AA (NFR-8):
  - contrast ≥4.5:1 (dark text on light, checked)
  - every control is a real `<button>`/`<input>` with `aria-label`, focus-visible outlines, Tab order, Enter/Escape in the modal, focus trap
  - all targets `min-width/min-height: 48px`
  - `lang`, `<title>`, landmarks

---

## 7. QA harness (part of the 80%)

### 7.1 `docker-compose.yml`
Add `mediamtx`, `minio`, `minio-init`, `selenium-hub`, `node-chrome-1`, `node-chrome-2`, `node-firefox` exactly as spec 6.2.1 (`selenium/*:4.25.0`, `shm_size: "1gb"`, `SE_START_VNC=false`, `SE_NODE_MAX_SESSIONS=2`), plus `extra_hosts: ["host.docker.internal:host-gateway"]` on the nodes.
- API env adds `DAY2_SALT: ${DAY2_SALT}`. API `depends_on` mediamtx (started).
- Hub healthcheck: `curl -sf localhost:4444/status`.
- In the browser, the guest web is reached as `http://api:8080` or `http://host.docker.internal:8080`. Relative redirects make both work.

### 7.2 `tests/selenium/test_guest_grid.py` (pytest + selenium + pytest-xdist)
- `conftest.py`: `GRID_URL=http://localhost:4444`, `WEB_BASE=http://host.docker.internal:8080` (browser side), `API_BASE=http://localhost:8080` (runner side). Browsers parametrised chrome / chrome / firefox. Headless. No reset inside tests (xdist-safe; CI resets once before).
- Test 1: open `/q/m1-live` → URL path ends `/web/matches/match-m1/live`, video + banner visible in ≤3 s, modal not displayed.
- Test 2: type into chat, click send → message not in list, modal displayed.
- Test 3: add to cart → count `"1"`. POST a `goal` to `/audit/v1/events` (unique `event_id`) → banner changes within 500 ms (`WebDriverWait(0.5)` after the POST).
- Extra: WCAG checks (48×48 rects, aria-labels, Tab reaches send button).
- Run: `pytest -n 3 tests/selenium/ --junitxml=tests/reports/selenium-report.xml`.

### 7.3 `tests/k6_load.js` and performance (NFR-2)
- Commit the spec script **verbatim**. Run: `k6 run --summary-export=tests/reports/k6-summary.json tests/k6_load.js`.
- Hot paths: `GET /audit/v1/qr/match-m1?inspect=true` (1 indexed query, async, no threadpool if possible) and `POST /audit/v1/moderation/test` (clean batch: pure CPU + 1 count read).
- Plan: measure on 1 worker by 12:30. If p95 ≥ 800 ms or any 5xx, switch the Dockerfile to `--workers 4`. That requires moving `realtime` fan-out to Redis pub/sub and the Day 1 rate limiter to Redis (sliding window in a sorted set); both are prepared as small modules.
- Also add `orjson` responses, bump the DB pool (`max_size` 30 → 50/worker cap) and keep `--limit-concurrency` high.
- NFR-1 probe script `tests/integration/test_ws_latency.py`: 25 WS clients, POST score, assert p95 < 500 ms.

### 7.4 `tests/appium/test_mobile_deeplink.py` (Appium-Python-Client, uiautomator2)
- Appium 2 on laptop 2 at `:4723` (`appium driver install uiautomator2`). Phone or emulator over adb.
- Test: `adb shell am start -W -a android.intent.action.VIEW -d nascon://entity/match-m1` (through `mobile: shell` or `mobile: deepLink`) → element `resource-id=match-live-screen` visible within 2 s. Same for `nascon://stream/cs-session-101` → `costream-screen`.
- Cross-surface test: create `cs-session-101` via API, open it in the app (Appium) **and** `/web/costream/cs-session-101` in a Grid browser. A member posts chat via `/api/v1/chat`, and both surfaces must show the text within 3.0 s.
- `--junitxml=tests/reports/appium-report.xml`.

### 7.5 `.github/workflows/autograde.yml`
- On push to `main`, ubuntu-latest:
  - checkout, `docker compose pull` (pre-pull images in parallel)
  - `DAY1_SALT/DAY2_SALT` from repo secrets with test fallbacks, `docker compose up -d --build`
  - wait `/health` (≤120 s) and grid `value.ready && nodes ≥3`
  - Day 1 unit + integration, Day 2 contract tests (`tests/integration/test_day2_*.py`), Selenium suite, `grafana/setup-k6-action` + k6 smoke (10 s)
  - upload `tests/reports/` as artifact
- Pushing this file needs a token with `workflow` scope.

### 7.6 Coverage `COVERAGE_DAY2.json`
- Extend `tests/coverage_report.py` with `AREAS_DAY2`, writing `COVERAGE_DAY2.json`:
  - `streaming`: domain/streaming.py
  - `costream`: domain/costream.py
  - `qr_guest`: domain/qr.py, domain/guest.py, services/qrexport.py
  - `moderation_dlq`: domain/moderation.py, domain/dlq.py
  - `observability`: domain/metrics.py, domain/privacy.py
- Target ≥85% each, numbers generated (never hand-written).
- Unit tests: `tests/unit/test_day2_*.py`, including the Appendix A vectors (4-key and legacy 2-key), every validation branch, handoff table, leetspeak table, target_route table, metrics format.

---

## 8. Mobile app updates (part of the 20%)

Priority order:
1. **Deep links (Appium-graded):**
   - `AndroidManifest.xml`: add the spec `intent-filter` (VIEW, DEFAULT, BROWSABLE, `scheme="nascon"`) and `android:launchMode="singleTask"`.
   - `MainActivity` parses `intent.data` in `onCreate` and `onNewIntent`: `nascon://entity/{id}` and `nascon://stream/{cs-session-id}`.
   - If a deep link is present, **skip the 1.6 s splash**.
   - No session → `GuestMatchLiveScreen` / `GuestCoStreamScreen` (guest token, `/api/v1/guest/*`), never the login screen. With a session → navigate into the `MainScreen` NavHost (`match/{id}`, `costream/{id}`, `clubs/{id}`, `player/{id}`).
   - Set `Modifier.semantics { testTagsAsResourceId = true }` at the root and `testTag("match-live-screen")` / `testTag("costream-screen")`.
2. **Match Live screen:** Media3 ExoPlayer (HLS `matchfeed/<id>`), score overlay, club badges and pinned merch from the WS metadata (no stream restart).
3. **Co-stream screen:** composite URL player (or up to 4 tiles), unified chat (WS `chat-<id>`, ordered by `seq`), host controls (invite token, mute, spotlight, kick) for the host.
4. **QR scanner:** `com.journeyapps:zxing-android-embedded`. Scans `/q/...` or `nascon://...` → resolve via `?format=json` → navigate.
5. **Broadcaster screen** (player role): get a key (`/api/v1/streams/key`), show RTMP/WHIP URLs + QR for OBS, rotate/revoke. Stretch: in-app RTMP go-live with RootEncoder.
6. **Notifications:** WS events → in-app snackbar + `NotificationCompat` for co-stream invites and score.
7. Rebuild the signed `mobile/release/app-release.apk` and update `MOBILE_CHECKLIST.md`.

---

## 9. Timeline (now → 14:05). Push every window.

| Time (PKT) | Work | Push |
|---|---|---|
| 10:15 - 11:30 | Read spec + repo, `.env.example` DAY2_SALT | W1: commit `5bda661` (push only if done by 11:30) |
| 11:40 - 12:35 | **Backend contract core:** config/crypto/schema/seed (§3), guest guard, stream key, costream, QR + exports + `/q`, cart-merge, moderation + DLQ, metrics, privacy, unit tests + Appendix A vectors, Day 2 integration tests | **W2 before 12:45** (target 12:35) |
| 12:35 - 13:35 | Compose: mediamtx + minio + selenium grid. Media auth + revoke kick + compositor. Realtime score payload + SSE + optional WS token. Guest web player. Selenium suite. k6 run + perf fix. Mobile deep links + guest screens + APK. Appium test. CI workflow | **W3 before 13:45** (target 13:35) |
| 13:35 - 13:55 | Clean `down -v && up -d --build` timing, full grader-style run, generate reports (`selenium-report.xml`, `appium-report.xml`, `k6-summary.json`), `COVERAGE_DAY2.json`, `TRACEABILITY.md` (Phase II IDs), README + ADR-009..012, salt grep | **W4 final before 14:00** (target 13:55, grace 14:05:00) |

Push in the middle of each phase too. Small safe commits beat one big late one.

Parallel split if the team uses 3 laptops (spec 6.5):
- **A (laptop 1):** backend contract §4.
- **B (laptop 3):** compose + MediaMTX + Selenium + k6 + CI §5, §7.
- **C (laptop 2):** web player §6, then mobile + Appium §8.

---

## 10. Open questions for the organisers (ask at the desk early)

1. How does the grader move `match-m1` to **postponed** (event type name / endpoint)? We accept `match_postponed` and `match_status{status}`.
2. `write_rejection_code` when `test_write_block:false`: is it `403` or `null`? We send 403 with `write_block_verified:false`.
3. Are `kicked_users` / `muted_users` in `/moderation/test` per request or cumulative per room? We return per request (deduplicated) and persist per room.
4. Should `stream_key_override` be regex-validated? We accept any non-empty string.
5. Is the NFR-1 WebSocket probe sent with a JWT? We accept with or without one.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| k6 p95 > 800 ms on one Python worker | ASGI middleware, 1-query hot path, orjson. Fallback: 4 workers with Redis-backed realtime and rate limit (§7.3) |
| Compose takes over 120 s on the CI runner (big Selenium images) | Pre-pull step in CI. Light API image. Healthchecks with short intervals |
| WebRTC inside Docker (ICE) | Expose 8189/udp, `webrtcAdditionalHosts`. HLS fallback always works |
| Browser nodes cannot reach the API via `localhost` | `extra_hosts host-gateway` + relative redirects + `WEB_BASE` env |
| Day 1 regressions (new seed rows, WS auth change, middleware) | Run the Day 1 integration suite before each push |
| Salt leak | Env only. `grep -r "<slip salt>"` before each push |
| Ancestry broken | Never `git push -f`. Always `git pull --ff-only` before work on another laptop |
| Coverage under 85% | Logic in pure domain modules. Table-driven unit tests written alongside the code |

---

## 12. Pre-submission checklist (spec Appendix C)

- [ ] `DAY1_SALT=… DAY2_SALT=… docker compose up -d --build` → `/health` 200 within 120 s
- [ ] `git merge-base --is-ancestor 596c2bc HEAD`
- [ ] `/audit/v1/reset` seeds `match-m1`, `player-beta-2`, `guest_anon_tok_7721`, 3 QR mappings
- [ ] Every `/audit/v1/*` Phase II route: exact keys, statuses, error codes, `DAY2_SALT` signatures (Appendix A vector passes)
- [ ] Guest bearer on `POST /api/v1/chat`, `/audit/v1/checkout`, `/audit/v1/events` → 403 `GUEST_WRITE_FORBIDDEN`
- [ ] 4 hidden scenarios pass (host drop, QR mutation, 10-thread moderation race, cart-merge replay)
- [ ] `localhost:4444/status` ready with ≥3 nodes
- [ ] `/web/matches/match-m1/live` has all 9 `data-testid`s
- [ ] `localhost:4723/status` ready. `adb … nascon://entity/match-m1` opens the match screen in ≤2 s
- [ ] k6: 500 + 50 VUs for 15 s, 0% failed, p95 < 800 ms
- [ ] `tests/reports/*`, `COVERAGE_DAY2.json`, `TRACEABILITY.md` committed. Last push before 14:05:00
