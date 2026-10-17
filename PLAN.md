# NaSCon '26 Part I: Project Plan

Multi-Sport League & Club Operations Platform
Day 1 sprint: Sat 17 Oct 2026, 10:45 to 15:00 PKT (final push 15:05:00)

---

## 1. End Products

| # | Product | Who uses it | Graded by | Points |
|---|---------|-------------|-----------|--------|
| 1 | **Backend server**: headless JSON API in Docker (no web UI) | Grader scripts (`/audit/v1/*`) and the Android app (`/api/v1/*`) | Python grading scripts | 36 + offline-sync script share |
| 2 | **Android app** (Kotlin, Jetpack Compose) | Players, managers, organizers, viewers | Judges at the desk (15:15+) | 10 UI/HCI + offline desk-check share |
| 3 | **Repo documents**: README, TRACEABILITY, ADR, tests, coverage | Graders and judges | Checked for presence and accuracy | Coverage bonus (10% per backend area) |

### 1.1 Backend server: how it works

- Started with one command: `DAY1_SALT=<salt> docker compose up -d --build`
- Containers:
  - `api`: FastAPI (Python 3.12) on host port **8080**
  - `db`: PostgreSQL 16 (all state)
  - `redis`: Redis 7 (domain-event queue through Redis Streams, plus rate-limit counters)
  - `worker`: consumes domain events from the stream (order/match status changes)
- Receives HTTP requests with JSON bodies and returns JSON. No HTML pages.
- Two route families share **the same domain services**:
  - `/audit/v1/*`: the binding autograder contract (Section 5 of the spec). No auth except the RBAC probes, and no rate limit.
  - `/api/v1/*`: the production API used by the mobile app. JWT auth, RBAC and rate limiting (100 requests per 10 s per IP).
- WebSocket `/ws/matches/{match_id}` pushes live score and pinned-product updates to the app.

### 1.2 Android app: how it works

- Connects to the backend on the team laptop. The server URL can be changed in Settings (emulator `10.0.2.2:8080`, phone uses the laptop's LAN IP).
- After login, the JWT is encrypted with an AES-GCM key held in the **Android Keystore**.
- Every list (fixtures, standings, club, products) is shown from the local **Room** cache first, then refreshed from the network.
- Offline scoring and roster actions are stored in a persistent Room queue using the exact `/offline-sync` action format, and synced automatically when the network returns.

---

## 2. Architecture

```
                ┌──────────────── docker compose (host :8080) ────────────────┐
Android app ──► │  api (FastAPI)  ──►  postgres:16   (all state, JSONB)        │
(Kotlin/Room)   │     │  /api/v1/*  /audit/v1/*  /ws/*                         │
   ▲  WS        │     └──►  redis:7  (Redis Streams queue, rate limit)         │
   └────────────│  worker (same image): consumes domain events               │
                └──────────────────────────────────────────────────────────────┘
Grader (Python) ──► /audit/v1/*  (thin wrappers over the same domain services)
```

**Design rule:** every algorithm is a **pure function** in `app/domain/` with no database access:
fixtures, score projection, standings, roster rules, sync decisions and RBAC policy. Routes load
data, call the domain function and persist the result.

This gives:
- fast unit tests and easy coverage above 85%;
- identical behaviour for the grader and the app;
- **no sport or event names in code**. The seed sports live in `seed/sports.json` as data, which avoids the -8 penalty.

---

## 3. Repository Layout

```
Powerhouse/                      (git root, public GitHub repo)
├── docker-compose.yml
├── .env.example                 (variable names only, never the real salt)
├── .gitignore                   (.env, build outputs, keystores except release signing config)
├── README.md                    (run instructions + 5 demo accounts)
├── TRACEABILITY.md              (FR/NFR id → source files → tests)
├── ADR.md                       (8 architecture decision records)
├── COVERAGE.json                (generated from the real pytest --cov run)
├── run_tests.sh
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── worker.py
│   └── app/
│       ├── main.py              app factory, middleware (413, error envelope, rate limit)
│       ├── config.py            env-only settings (DAY1_SALT, DATABASE_URL, JWT_SECRET, REDIS_URL)
│       ├── db.py, schema.sql, seed.py
│       ├── seed/sports.json, seed/baseline.json
│       ├── errors.py            ApiError + Appendix B catalogue
│       ├── crypto.py            canonical_json, sign, lots_key
│       ├── domain/
│       │   ├── fixtures/        round_robin.py, swiss.py, single_elim.py, double_elim.py
│       │   ├── sports.py        sport config validation (event / innings / round)
│       │   ├── scoring.py       event rules + projection from the log
│       │   ├── standings.py     table, resolve(group), H2H, NRR, qualification
│       │   ├── roster.py        8 ordered checks, loans, auto-return
│       │   ├── store.py         pricing, discount, mock payment gateway
│       │   ├── rbac.py          policy matrix
│       │   └── sync.py          offline replay + conflict resolution
│       ├── routes/              audit.py, api.py, auth.py, ws.py
│       └── services/            pdf.py (fpdf2), queue.py (Redis Streams), realtime.py
├── tests/
│   ├── unit/                    pure domain tests (no DB)
│   └── integration/             grader-style HTTP tests against the running stack
└── mobile/
    ├── (Android Gradle project, Kotlin)
    └── release/app-release.apk
```

---

## 4. Backend: Global Conventions

- Base URL `http://localhost:8080`, JSON UTF-8.
- Error body on every non-2xx response: `{"error":{"code","message","details":{}}}`. `VALIDATION_ERROR` puts the offending fields in `details.fields`.
- Validation order: **400 → 404 → 409** (402 for payment). The first failure wins.
- Unknown fields are ignored. Ids are 1 to 64 chars from `A-Za-z0-9_.:-`, stored verbatim.
- Money is integer paisa, currency `PKR`. Timestamps use `YYYY-MM-DDTHH:MM:SSZ`, dates use `YYYY-MM-DD`.
- Idempotency: the same client id with the same body returns 200 with the stored response. The same id with a different body returns 409 `DUPLICATE_*`.
- Bodies over 1 MB return 413 `PAYLOAD_TOO_LARGE`.
- `/audit/v1/*` and `/health` are never rate limited.
- Signature: `HMAC_SHA256(DAY1_SALT utf-8, id + "|" + canonical_json(payload))` as lowercase hex.
  Canonical JSON = sorted keys, separators `,` and `:`, no ASCII escaping.
  Must reproduce Appendix A vector 1: `972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501`.
- `DAY1_SALT` is read only from the environment and is never committed.

---

## 5. Backend: Area-by-Area Plan

### 5.0 Platform (NFR-7)
- Compose healthchecks; `api` depends on a healthy `db` and `redis`.
- On boot: create the schema, then seed. `/health` returns 200 `{"status":"ok"}` only when the DB is reachable and the seed is present.
- `POST /audit/v1/reset` truncates all tables and reseeds in **one transaction**. It accepts `seed` (default 42) and `stock` (defaults M=1, L=5), must be repeatable, and finishes in under 10 s.
- Baseline data:
  - tenants `tenant-alpha` and `tenant-beta`;
  - leagues `league-alpha-1`, `league-alpha-2` and `league-beta-1`;
  - clubs `club-alpha-1`, `club-alpha-2` and `club-beta-1`;
  - players `player-alpha-1`, `player-alpha-2` and `player-beta-1`;
  - product `prod-jersey-001` with variants `-M` and `-L` at 450000 paisa;
  - discount code `WELCOME10`;
  - the 4 sports;
  - the 5 demo users.
- Demo content for the app (fixtures with ids prefixed `demo-` so they never collide with grader ids): completed, live and upcoming matches in `league-alpha-1`.

### 5.1 Fixtures: `POST /audit/v1/fixtures` (FR-1.3), computation only
- **Round robin**
  - Circle method; odd n adds a phantom team that produces the bye.
  - Home/away alternates so that `|home-away| ≤ 1` per leg; leg 2 mirrors leg 1.
  - Global round numbers; ids `RR-L{leg}-R{round}-M{i}`.
  - Withdrawals: `forfeit_remaining` (round > after_round becomes forfeit, awarded to the opponent) or `void_all`. Both teams withdrawn means voided. Summary counts.
- **Swiss**
  - Standings from history: win 1, draw 0.5, bye 1; Buchholz.
  - Sort by score desc, Buchholz desc, then seed.
  - Round 1 is exact: seed i plays seed i+m, and the last seed gets the bye when n is odd.
  - Later rounds: try bye candidates from lowest score with no previous bye (largest index first). For each candidate, run a branch-and-bound search for the rematch-free perfect matching with the minimum sum of |score diff|.
  - If no candidate works: 409 `NO_VALID_PAIRING` with `details.round`.
- **Single elim**
  - B = next power of two; recursive seed order; byes propagated immediately.
  - `winner_to` / `loser_to` routing; `params.results` applied in order.
  - Optional third-place match `TP`.
- **Double elim**
  - WR is identical to single elim.
  - LR has 2(k-1) rounds (B-2 matches); WR1 losers go to LR1, WRr losers go to LR(2r-2).
  - `GF1` and `GF2` (`conditional:true`, `required` null, then true or false).
- Limits: RR 2-40, swiss 2-64, single 2-128, double 3-128, otherwise 400.

### 5.2 Sports & Scoring: `/sports`, `/events`, `/score/{id}` (FR-1.1)
- `sports` table: `sport_id` plus JSONB config, validated per model (event / innings / round). Duplicate gives 409 `SPORT_EXISTS`.
- `matches` table: id, sport, league, home and away teams.
- `events` table is **append-only**: `(match_id, sequence, event_id UNIQUE, type, payload, body_hash, signature)`.
- Appends are serialised per match with `SELECT ... FOR UPDATE` on the match row.
- Event types:
  - `match_init`, `match_start`, `score`, `discipline`;
  - `tiebreak_winner`, `match_end`, `compensation`.
- Rules come from config only: innings ball/wicket limits (`INNINGS_COMPLETE`) and round best-of limits (`SERIES_ALREADY_DECIDED`). Compensated events don't count toward limits.
- Projection is rebuilt from the log on every read:
  - status and outcome;
  - per-team score, wickets, balls, overs (`"b div bpo . b mod bpo"`), fair_play;
  - the event list with `compensated` / `compensated_by`.

### 5.3 Standings: `/leagues`, `/standings/{id}` (FR-1.4)
- `/leagues` registers teams and fixtures; each fixture becomes an `upcoming` match stream.
- Standings are recomputed from scratch on every call; only completed matches count.
- Points come from configurable win/draw/loss values; a tiebreak winner counts as a win.
- `resolve(group)`: walk `tie_break_order`. When a criterion splits the group, recurse on each sub-group from the first criterion. `draw_lots` always comes last.
  - `h2h_points` / `h2h_diff`: only matches among the current group (3-way mini-league).
  - `overall_diff`, `scored`, `fair_play`: all league matches.
  - Diff by model: event = score diff; round = maps won minus lost; innings = **net run rate**, rounded to 3 decimals, where an all-out innings counts as full overs.
  - `draw_lots`: ascending `sha256(f"{seed}|{league_id}|{team_id}")`.
- `resolved_by` is the criterion that placed the team above the next tied team.
- Qualification (points only), with `max(T) = points + W × remaining`:
  - **clinched** if fewer than k other teams have max ≥ points(T);
  - **eliminated** if at least k teams have points > max(T);
  - **still_possible** otherwise.
- `h2h` matrix for every ordered pair, with zeros when the teams never met.

### 5.4 Roster: `/roster/setup`, `/roster/transfer`, `/roster/history/{id}` (FR-2.2)
- Checks run in **exact order**:
  1. validation;
  2. 404s;
  3. `CROSS_TENANT_TRANSFER`;
  4. `NOT_IN_SQUAD`;
  5. `TRANSFER_WINDOW_CLOSED`;
  6. `PLAYER_ON_LOAN`;
  7. `SQUAD_FULL`;
  8. `MIN_POSITION_VIOLATION`.
- Effects:
  - **transfer**: the role becomes substitute;
  - **loan**: `parent_squad_id` is set and the end date is inclusive;
  - **release**: the player has no squad.
- In-progress match: the request is accepted with `state:"deferred_until_match_end"` and `blocking_match_id`.
- Audit trail is append-only. `history?as_of=` writes the `loan_return` entry **once** (enforced by a unique constraint), with who = `system`.
- Idempotent by `request_id`. Rejected requests write nothing.

### 5.5 Store: `/checkout`, `/inventory/{id}` (FR-2.3, NFR-3)
- Order: validate → variants exist (404) → discount (400) → reserve atomically.
- Reservation: `UPDATE variants SET stock = stock - q, reserved = reserved + q WHERE id = ? AND stock >= q`. All items go in one transaction; if any item fails, roll back and return 409 `OUT_OF_STOCK`.
- Mock gateway:
  - `tok_success`: authorize and capture;
  - `tok_declined`: 402 `PAYMENT_DECLINED`;
  - `tok_capture_fail`: void, then 402 `PAYMENT_CAPTURE_FAILED`.
  - Failures release the stock.
- On success: `reserved -= q`, status `paid`, signed receipt, PDF through fpdf2 (contains the order id and `PKR 4500.00`).
- `WELCOME10`: `discount = floor(subtotal * 10 / 100)`.
- Order state machine: Pending, Paid, Packed, Shipped, Delivered, Cancelled, Refunded. Each transition is published to Redis Stream `domain-events`.
- Idempotent by `order_id` plus a body hash.

### 5.6 RBAC & Security: `/rbac-matrix`, P1-P7, `/api/v1/ping` (FR-5.1, NFR-5)
- JWT HS256 with the secret from env and expiry of at least 1 h. Reject `alg:none`, tampered or expired tokens with 401 `UNAUTHENTICATED`.
- Policy matrix (role × action → scope):
  - `platform`;
  - `own_league`;
  - `own_club`;
  - `self_or_own_club_player`;
  - `tenant_read`.
- Authorization happens before anything else. Cross-tenant access returns **403**, not 404.
- Sliding-window rate limiter on `/api/v1/*`: 100 requests per 10 s per IP, with 429 `RATE_LIMITED` and a `Retry-After` header.
- Parameterised SQL everywhere; input strings are stored as plain data; never return a 5xx.

### 5.7 Offline Sync: `POST /audit/v1/offline-sync` (NFR-4)
- Stable sort by `queued_at`; results are returned in request order with `processed_order`.
- Per action:
  1. **duplicate**: (device_id, action_id) already seen, or the same event_id with an identical payload;
  2. **unknown id**: `*_NOT_FOUND`;
  3. **base_version > current**: `INVALID_BASE_VERSION`;
  4. a domain rule fails: `server_wins` with that rule's code;
  5. otherwise applied: `appended` when the versions are equal, `rebased_append` when the device is stale.
- Versions: for a match, the number of events; for a player, the number of audit entries.
- Results are stored, so resending the same request returns every action as a duplicate.

### 5.8 Production API for the app (`/api/v1`)

| Method & path | Purpose |
|---|---|
| `POST /api/v1/auth/login` | Email + password, returns a JWT and the profile |
| `GET /api/v1/me` | Current user, role, tenant (logo, colors) |
| `GET /api/v1/leagues` | Leagues in the tenant |
| `GET /api/v1/leagues/{id}/fixtures` | Fixtures with status and time |
| `GET /api/v1/leagues/{id}/standings` | Table + qualification |
| `GET /api/v1/matches/{id}` | Score projection + timeline + pinned product |
| `POST /api/v1/matches/{id}/events` | Organizer: score or compensation |
| `POST /api/v1/matches/{id}/pinned-product` | Pin a product (realtime broadcast) |
| `GET /api/v1/clubs/{id}` | Club info, venue, staff, roster |
| `POST /api/v1/clubs/{id}/roster/transfer` | Manager: transfer / loan / release |
| `GET /api/v1/products` | Catalogue with variants and stock |
| `POST /api/v1/checkout` | Purchase through the mock gateway |
| `GET /api/v1/orders/{id}/receipt.pdf` | PDF receipt download |
| `POST /api/v1/sync` | Offline queue replay (same code as `/audit/v1/offline-sync`) |
| `GET /api/v1/ping` | Rate-limit probe |
| `WS /ws/matches/{id}` | Live score + pinned product push |

---

## 6. Android App (Kotlin)

### 6.1 Stack
Kotlin, Jetpack Compose with Material 3, Hilt, Room, WorkManager, DataStore, OkHttp (REST and WebSocket) and
kotlinx.serialization. All of these are already resolved in the offline Gradle cache from `android-starter`.
`minSdk` is 26 and runs on Android 10+ (API 29).

### 6.2 Layers

| Layer | Contents |
|---|---|
| `data/remote` | `ApiClient` (OkHttp; base URL from DataStore; adds Bearer token), DTOs, `LiveScoreSocket` |
| `data/local` | Room DB: `fixtures`, `standings`, `clubs`, `players`, `products`, `pending_actions`, `sync_results` |
| `data/secure` | `TokenStore`: an AES-GCM key in the Android Keystore encrypts the JWT, and the ciphertext lives in DataStore |
| `data/repo` | Repositories show the cache first and refresh from the network; writes go to the queue while offline |
| `sync` | `ConnectivityObserver` (NetworkCallback) and `SyncWorker` (WorkManager, runs when the network is connected) |
| `ui` | Compose screens, ViewModels, a shared component kit and the tenant theme |

### 6.3 Screens

| Screen | Content | Roles |
|---|---|---|
| Login | Email + password, server URL setting, demo-account hint | All |
| Home | Role-aware dashboard and bottom navigation: Fixtures, Standings, Store, Club, Profile | All |
| Fixtures | Matches with status chip + time; tap to open; empty state | All |
| Match detail | Large live score (WebSocket), event timeline, pinned product card | All |
| Scoring entry | Add a score event / discipline / compensate an event (with confirmation) | League Organizer |
| Standings | Points table with a qualification chip (text + icon, not color alone) | All |
| Club profile | Info, home venue, social handles, staff, roster | All |
| Roster management | Add / transfer / loan / release with a confirmation dialog | Club Manager |
| Store | Catalogue → variant picker → cart → checkout → receipt view / share PDF | All signed-in users |
| Sync queue | Pending actions and per-action results in plain language | All |
| Settings / Profile | Server URL, logout | All |

An **always-visible status bar** shows Online, Offline or Syncing, with a pending-action count.

### 6.4 Offline flow (desk check 8.4)
1. When online, fixtures, standings and club data are written to Room.
2. In airplane mode, screens render from Room and the banner shows **Offline**.
3. Scoring and roster actions are inserted into `pending_actions` using the 5.14 format:
   `{action_id, type: score_event|roster_transfer, queued_at, base_version, payload}`. The UI marks them **Pending**.
4. The queue survives a force-close because it is persisted in Room.
5. When the network returns, `SyncWorker` posts the queue to `/api/v1/sync` and shows **Applied ✓** or
   **Rejected: <plain-language reason>** for each action, then clears the queue. A manual **Sync now** button is also available.

### 6.5 UI/HCI checklist (judged areas 8.6)
- **Navigation**: bottom nav for the 5 main sections, a working back button everywhere, no dead ends, and common tasks in 3 taps or fewer.
- **Consistency**: one theme with the tenant's logo and colors; the score and the Buy button are visually dominant.
- **Feedback**: loading indicators, success snackbars, plain-language errors (error codes mapped to sentences, never "Error 500"), confirmation before risky actions.
- **Accessibility**: tap targets of at least 48 dp, readable text sizes, good contrast, content descriptions on icons, meaning never carried by color alone.
- **Role fit**: each role only sees its own actions; empty states such as "No matches yet"; works at 360×640 dp and when rotated.

### 6.6 Release
- Release keystore generated locally, `assembleRelease`, output copied to `mobile/release/app-release.apk`.
- Install test on an emulator or phone (API 29+).

---

## 7. Testing & Coverage

- `tests/unit/`: pure domain tests per area: fixtures, scoring, standings, store, roster, rbac.
  - Property tests for round robin (n = 2 to 40): pairs meet `legs` times, one bye per leg, balance ≤ 1.
  - Brute-force optimality check for Swiss pairings at small n.
  - Bracket counts (losers matches = B-2) and GF2 `required` logic.
  - Signature vector 1 and draw-lots vector 2 from Appendix A.
- `tests/integration/`: grader-style HTTP tests:
  - 20 concurrent checkouts with a barrier: one 201, nineteen 409, stock 0, reserved 0;
  - the full RBAC matrix plus forged, `alg:none` and expired tokens;
  - the rate limit (150 pings);
  - reset twice gives identical state;
  - offline-sync replay gives all duplicates.
- `run_tests.sh` runs pytest with `--cov` per area and writes `COVERAGE.json` from **real** numbers. The declared figure must not be more than 2 points above the real one.

---

## 8. Timeline & Push Checkpoints

A push is required in every window; each missed window costs -2.

| Time (PKT) | Work | Push |
|---|---|---|
| 11:00 - 11:35 | git init, compose, Dockerfile, schema, seed, `/health`, `/reset`, crypto, error envelope, 413, `.gitignore`, `.env.example`, README stub | **#1 before 11:45** |
| 11:35 - 12:40 | Fixtures (4 formats), sports, events/score, standings + unit tests | **#2 before 12:45** |
| 12:40 - 13:40 | Store + PDF + queue, roster, RBAC + JWT + rate limit, offline-sync, `/api/v1` + WebSocket, demo seed | **#3 before 13:45** |
| 13:40 - 14:40 | Android app: screens, Room cache, offline queue, Keystore, sync, APK build | **#4 before 14:45** |
| 14:40 - 15:00 | Grader-style smoke run, clean `docker compose down -v && up --build`, COVERAGE.json, TRACEABILITY.md, ADR.md, README | **Final before 15:05:00** (target 14:58) |

Written contract questions must be submitted **before 13:00**.

---

## 9. Penalties to Avoid

| Penalty | Points | Guard |
|---|---|---|
| Non-reproducible stack | -10 | Pinned images, healthchecks, no host deps, final clean-machine test |
| Hard-coded sport logic | -8 | Sport and event names only in `seed/sports.json`; grep the code before each push |
| Managed BaaS | -10 | Self-hosted Postgres, Redis and JWT only |
| Missed push window | -2 each | Push at every checkpoint in Section 8 |

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| App runs out of time | Shared component kit; offline queue and sync before polish |
| Swiss / double-elim edge cases | Brute-force cross-check tests at small n |
| Concurrency bug in checkout | Single conditional `UPDATE` per variant inside a transaction; 20-thread barrier test |
| Salt leaked into the repo | `.env` git-ignored; grep for the salt before every push |
| Coverage claim too high | COVERAGE.json generated by `run_tests.sh` |
| Spec ambiguity | Written question to the organizers before 13:00 |

---

## 11. Pre-Submission Checklist

- [ ] `DAY1_SALT=<salt> docker compose up -d --build` works from a clean clone; `/health` is 200 in under 2 min
- [ ] `/reset` twice leaves identical data; the 5 demo accounts and all seed ids exist
- [ ] Response fields match Section 5 of the spec character by character
- [ ] Appendix A vector 1 signature reproduced
- [ ] 20 parallel checkouts give one 201, nineteen 409, stock 0, reserved 0
- [ ] `/audit/v1/*` is not rate limited; `/api/v1/ping` is
- [ ] COVERAGE.json, TRACEABILITY.md, ADR.md, README.md, .env.example and `mobile/release/app-release.apk` are committed
- [ ] No salt and no hard-coded sport names in the code
- [ ] Last commit pushed before 15:05:00 PKT

---

## 12. Demo Accounts (password `Nascon@26`)

| Role | Email | Scope |
|---|---|---|
| Platform Super-Admin | admin@nascon.test | Platform-wide |
| League Organizer | organizer@nascon.test | league-alpha-1 |
| Club Manager | manager@nascon.test | club-alpha-1 |
| Player | player@nascon.test | player-alpha-1 |
| General Viewer | viewer@nascon.test | tenant-alpha read-only |
