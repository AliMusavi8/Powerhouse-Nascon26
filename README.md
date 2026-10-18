# Powerhouse: NaSCon '26 League & Club Operations Platform.

Multi-tenant sports league and club-operations platform. It has two parts:
- a self-hosted backend: REST API, WebSocket live updates, an event-sourced scoring engine and a Redis Streams job queue;
- an Android app written in Kotlin with Jetpack Compose, with an offline cache and a sync queue.

## Run the backend:

Requirements: Docker Engine 24+ with Compose v2. Nothing else is needed on the host.

```bash
cp .env.example .env                       # set DAY1_SALT (never commit .env)
DAY1_SALT=<salt> docker compose up -d --build
curl http://localhost:8080/health          # {"status":"ok"}
```

| Service | Image | Purpose |
|---|---|---|
| `api` | built from `backend/` (Python 3.12, FastAPI, Uvicorn) | REST API + WebSocket on host port **8080** |
| `db` | `postgres:16-alpine` | All state; the event log is append-only |
| `redis` | `redis:7-alpine` | Domain-event queue (Redis Streams) |
| `worker` | built from `backend/` | Consumes domain events (order and match status changes) |

The API creates its schema and seeds the baseline data on first start. `POST /audit/v1/reset` wipes all state and
re-creates the same baseline every time.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `DAY1_SALT` | yes | Team salt used for HMAC-SHA256 signatures of events and receipts. Read only from the environment. |
| `JWT_SECRET` | no | JWT signing key. If empty it is derived from `DAY1_SALT`. |
| `DATABASE_URL` | set in compose | PostgreSQL connection string |
| `REDIS_URL` | set in compose | Redis connection string |
| `JWT_TTL_SECONDS` | no (7200) | Token lifetime |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | no (100 / 10) | `/api/v1/*` rate limit per client IP |

## Demo accounts (password `Nascon@26`)

| Role | Email | Scope |
|---|---|---|
| Platform Super-Admin | admin@nascon.test | Platform-wide |
| League Organizer | organizer@nascon.test | league-alpha-1 |
| Club Manager | manager@nascon.test | club-alpha-1 |
| Player | player@nascon.test | player-alpha-1 |
| General Viewer | viewer@nascon.test | tenant-alpha, read-only |

These accounts exist after every start and every reset.

## API overview

- **Autograder contract (`/audit/v1/*`, `/health`)**: reset, sports, fixtures, leagues, events, score, standings, roster
  setup/transfer/history, checkout, inventory, RBAC matrix and probes, offline sync. Not rate limited.
- **Mobile API (`/api/v1/*`)**: JWT bearer auth, RBAC on every route, rate limited to 100 requests per 10 s per IP.

| Method & path | Purpose |
|---|---|
| `POST /api/v1/auth/login` | Email + password, returns JWT and profile |
| `GET /api/v1/me` | Current user, tenant branding, permissions |
| `GET /api/v1/leagues` | Leagues of the user's tenant |
| `GET /api/v1/leagues/{id}/fixtures` | Fixtures with live status and score |
| `GET /api/v1/leagues/{id}/standings` | Points table with qualification status |
| `GET /api/v1/matches/{id}` | Score projection, timeline, pinned product |
| `POST /api/v1/matches/{id}/events` | Organizer: score / discipline / tie-break / compensation |
| `POST /api/v1/matches/{id}/pinned-product` | Pin a product to a match (pushed live) |
| `GET /api/v1/clubs`, `GET /api/v1/clubs/{id}` | Club profile, venue, staff, roster |
| `POST /api/v1/clubs/{id}/players` | Manager: add a player |
| `POST /api/v1/clubs/{id}/roster/transfer` | Manager: transfer / loan / release |
| `GET /api/v1/players/{id}/history` | Immutable roster audit trail |
| `GET /api/v1/products` | Catalogue with variants and stock |
| `POST /api/v1/checkout` | Purchase through the mock payment gateway |
| `GET /api/v1/orders`, `GET /api/v1/orders/{id}/receipt.pdf` | Order history, PDF receipt |
| `POST /api/v1/orders/{id}/status` | Order state machine (packed, shipped, ...) |
| `POST /api/v1/sync` | Replay the offline action queue (same engine as `/audit/v1/offline-sync`) |
| `GET /api/v1/ping` | Rate-limit probe |
| `WS /ws/matches/{id}?token=<jwt>` | Live score and pinned-product updates |

## Tests

```bash
./run_tests.sh                       # unit tests + coverage -> COVERAGE.json
RUN_INTEGRATION=1 ./run_tests.sh     # also grader-style HTTP tests against the running stack
```

- Unit tests (`tests/unit`) cover the pure domain modules: fixtures, scoring, standings, store, roster, RBAC and sync.
- Integration tests (`tests/integration`) exercise the live API, including:
  - 20 concurrent checkouts for the last unit of stock;
  - the full RBAC matrix plus token attacks;
  - rate limiting;
  - offline-sync conflict resolution.

## Mobile app

The app is called **Scorix**. The source is in `mobile/` (Kotlin, Jetpack Compose, Room, WorkManager, OkHttp). The installable build is `mobile/release/app-release.apk` (minSdk 26, so Android 8.0+ including Android 10).

### Install and connect

1. Start the backend on the laptop.
2. Install the APK (`adb install mobile/release/app-release.apk`).
3. On the login screen tap **Server: ...** and set the address:
   - emulator: `http://10.0.2.2:8080` (default);
   - phone on the same network: `http://<laptop-LAN-IP>:8080`.
4. Sign in with a demo account (tap one in the list to fill it in).

### Build from source

```bash
cd mobile
./gradlew assembleDebug          # debug build
./gradlew assembleRelease        # signed release build
```

The release build reads its signing key from `mobile/local.properties` (`release.storeFile`, `release.storePassword`, `release.keyAlias`, `release.keyPassword`). The keystore and passwords are not committed.

### Screens

| Screen | Who | Notes |
|---|---|---|
| Login | everyone | Email + password, editable server address, offline sign-in for accounts used before on the device |
| Fixtures | everyone | Grouped by day, live matches first, status as text and marker |
| Match | everyone | Large score, live updates over WebSocket, timeline with corrections, pinned product |
| Scoring | league organiser | Start/end match, score events built from the sport config (`scoring_events`), discipline, tie-break winner, correction (compensating event) |
| Standings | everyone | Table with qualification status as icon + text + key, qualification cut line, tie-break notes |
| Club | everyone | Info, home venue, staff, socials, history, roster, recent moves |
| Roster management | club manager | Add player, transfer, loan, release, each confirmed in a dialog |
| Store | everyone | Catalogue, variant picker, cart, discount code, test card choice, receipt with view, download and share PDF, order history |
| Saved actions | everyone | Pending queue and per-action results in plain language |

The app is sport-agnostic: no sport or event names appear in the code. Event buttons and labels come from the server (`three_pointer` is shown as "Three pointer"), and innings fields (wickets, overs) are shown only when the server sends them.

### Offline behaviour

- Every screen is read network-first and saved to Room; in airplane mode the saved copy opens with an "Offline · showing data saved HH:MM" bar.
- Score and roster actions made offline are stored in the Room `pending_actions` table in the exact `/api/v1/sync` action format, survive a force-close, and show as "Pending" in the match timeline, the roster and the Saved actions screen.
- When the network returns, a WorkManager job (network-connected constraint) replays the queue; there is also a **Sync now** button. Each action is grouped by the account that created it and sent with that account's token.
- Results are shown per action in plain language (for example `SQUAD_FULL` becomes "The destination squad is full.") and the queue empties.

### Security

- The JWT is encrypted with an AES-256-GCM key held in the Android Keystore (`mobile/app/src/main/java/com/nascon/app/data/Security.kt`).
- Cleartext HTTP is allowed through `res/xml/network_security_config.xml` because the backend runs on plain HTTP on the LAN.

## Day 2 (Part II): streaming, dynamic QR, guest web player, grid QA

```bash
DAY1_SALT=<s1> DAY2_SALT=<s2> docker compose up -d --build
curl localhost:8080/health                  # {"status":"ok"}
curl localhost:4444/status                  # Selenium Grid: ready, 3 nodes
open http://localhost:8080/q/m1-live        # Guest Web Player for match-m1 (no app, no account)
```

| Service | Port(s) | Purpose |
|---|---|---|
| `api` | 8080 | REST + `/audit/v1/*` Part II contract, `/web/*` guest player, `/q/*` short links, `/metrics`, WebSocket/SSE |
| `mediamtx` | 1935 RTMP, 8888 HLS, 8889 WebRTC (WHIP/WHEP), 8189/udp | Self-hosted media server. Publishing is authorised by the API (active stream key only) |
| `minio` | internal 9000 | VOD recordings (bucket `vod`) |
| `selenium-hub` + `node-chrome-1/2` + `node-firefox` | 4444 | Selenium Grid 4.25, 1 GB shm, no VNC |

`DAY2_SALT` is read only from the environment and signs every Part II record (`crypto.sign_day2`).

### Part II contract (`/audit/v1/*`)

| Method & path | Notes |
|---|---|
| `POST /audit/v1/stream/key` | generate (201) / rotate / revoke. Revoking kicks the live publisher through the MediaMTX API (measured 0.23 s) |
| `POST /audit/v1/costream/session` | Validation in spec order, host handoff, idempotent replay (200), live re-post keeps `chat_room_id` |
| `GET /audit/v1/qr/{id}[?inspect=true]`, `/export.{svg,png,pdf}`, `GET /q/{code}` | Stable short URL, target route computed from live state, scan telemetry without IP/UA |
| `POST /audit/v1/guest/cart-merge` | 403 write-block check, atomic merge, network-replay safe |
| `POST /audit/v1/moderation/test` | Leetspeak masking, flood drop, deduplicated kick/mute under races, DLQ depth |
| `GET /metrics`, `DELETE /audit/v1/privacy/user/{id}` | Prometheus text 0.0.4; anonymisation + token wipe |

Match notice states for dynamic QR: append `match_postponed`, `match_cancelled`, `match_abandoned`, or
`match_status` with `{"status": "..."}` through `POST /audit/v1/events`.

### Guest access

- Any write with `Authorization: Bearer guest_*` returns 403 `GUEST_WRITE_FORBIDDEN` (middleware, before validation).
- Guest reads: `/api/v1/guest/{session,matches/{id},costream/{id},chat/{room}}`, live score `GET /api/v1/matches/{id}/stream` (SSE) or `WS /ws/matches/{id}` (token optional).

### QA harness

```bash
pytest -n 3 tests/selenium/ --junitxml=tests/reports/selenium-report.xml   # Grid (browsers reach the API via host.docker.internal)
pytest tests/appium --junitxml=tests/reports/appium-report.xml              # needs `appium` on :4723 + a device on adb
k6 run --summary-export=tests/reports/k6-summary.json tests/k6_load.js
./run_tests.sh                                                              # unit tests -> COVERAGE.json + COVERAGE_DAY2.json
```

`.github/workflows/autograde.yml` runs all of it on every push to `main`.

### Mobile deep links

`nascon://entity/{id}` and `nascon://stream/{cs-session-id}` open the Match Live / Co-Stream screen directly, signed in or not:

```bash
adb shell am start -W -a android.intent.action.VIEW -d "nascon://entity/match-m1"
```

## Repository map

| Path | Contents |
|---|---|
| `backend/app/domain/` | Pure domain logic (no I/O): fixtures, scoring, standings, roster, store, RBAC, sync |
| `backend/app/services/` | Persistence and orchestration (PostgreSQL, Redis, PDF, realtime) |
| `backend/app/routes/` | HTTP routes: `audit.py` (grader contract), `rbac.py` (probes), `api.py` (mobile API + WebSocket) |
| `backend/app/seed/` | Seed data: the four sports as JSON configuration, baseline tenants/clubs/users |
| `tests/` | Unit and integration tests, coverage report generator |
| `mobile/` | Android app (Kotlin, Compose, Room, WorkManager) |
| `TRACEABILITY.md` | Requirement → source → test mapping |
| `ADR.md` | Architecture decision records |
