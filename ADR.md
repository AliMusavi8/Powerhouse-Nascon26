# Architecture Decision Records

## ADR-001: Python FastAPI backend with a pure domain layer
**Status:** Accepted
**Context:** The contract is graded literally by Python scripts, and every algorithm (fixtures, standings, roster rules) must be unit-tested to at least 85% coverage.
**Decision:**
- Use FastAPI on Python 3.12.
- All domain logic lives in `backend/app/domain/` as pure functions with no I/O.
- Services load state, call the domain and persist the result.
- Routes are thin wrappers.
**Consequences:**
- Fast, deterministic unit tests.
- The canonical JSON and HMAC follow Appendix A byte for byte (`json.dumps(sort_keys, separators, ensure_ascii=False)`).
- `/audit/v1/*` and `/api/v1/*` share one implementation.

## ADR-002: PostgreSQL as the single source of truth
**Status:** Accepted
**Context:** We need transactional guarantees for concurrent checkouts, ordered event appends and roster changes, and a one-command reproducible stack.
**Decision:**
- Use PostgreSQL 16, with JSONB columns for configuration-shaped data (sport configs, league configs, stored responses).
- The schema is created on boot.
- `/reset` truncates and reseeds everything inside one transaction.
**Consequences:**
- Reset is atomic and repeatable.
- There are no migrations to run manually.

## ADR-003: Event sourcing for match scoring
**Status:** Accepted
**Context:** Scores must be rebuilt from an append-only log, and corrections must never mutate history.
**Decision:**
- The `events` table is insert-only (unique `event_id` and `(match_id, sequence)`).
- Corrections are `compensation` events.
- Projections (`scoring.project`) are recomputed on every read; there are no counters.
- Appends to the same match are serialised with a transaction-scoped advisory lock.
**Consequences:**
- Full audit history.
- Standings always reflect compensations.
- Reads cost O(events), which is small per match.

## ADR-004: Sports are data, not code
**Status:** Accepted
**Context:** Mystery sports are created during grading, and any branch on a sport or event name is penalised.
**Decision:**
- A sport is a JSON config with three generic scoring models (event, innings, round).
- The seed sports live in `seed/sports.json`.
- Rules (points, runs, legal balls, wickets, best-of, draw policy) are read from the config.
**Consequences:** A new sport works immediately through `POST /audit/v1/sports`, with no restart.

## ADR-005: Atomic conditional updates for inventory
**Status:** Accepted
**Context:** Twenty simultaneous buyers for the last unit must yield exactly one order and never negative stock.
**Decision:**
- Reservation is a single `UPDATE variants SET stock = stock - q, reserved = reserved + q WHERE stock >= q` per item, inside one transaction (all items or nothing), with a `CHECK (stock >= 0)` constraint.
- Payment runs outside the reservation transaction.
- On failure the reservation is released; on success it is committed (`reserved -= q`).
**Consequences:**
- Row locks serialise the contenders and losers get `OUT_OF_STOCK` immediately.
- Released stock is purchasable again.

## ADR-006: Custom HS256 JWT with a database-backed policy matrix
**Status:** Accepted
**Context:** Five roles, strict tenant isolation, and negative authorization tests for every boundary.
**Decision:**
- Tokens are HS256 JWTs, verified with `algorithms=["HS256"]` (which rejects `alg:none`) and a required `exp`.
- Authorization is the policy matrix `POLICY[action][role] = scope` in `domain/rbac.py`.
- Tenant isolation is checked first, so cross-tenant access is always 403.
**Consequences:**
- One place defines every permission.
- The probe routes and the mobile API use the same `require()`.

## ADR-007: Redis Streams as the internal job queue
**Status:** Accepted
**Context:** Order state transitions must emit structured domain events to an internal queue.
**Decision:**
- Services `XADD` to the `domain-events` stream.
- A separate `worker` container consumes it with a consumer group.
- A queue outage never fails a request.
**Consequences:** Order processing is decoupled from side effects such as notifications and fulfilment.

## ADR-008: Offline-first mobile client with a server-arbitrated sync queue
**Status:** Accepted
**Context:** The app must work in airplane mode, queue scoring and roster actions persistently, and reconcile them on reconnect.
**Decision:**
- The Android app (Kotlin, Compose) caches fixtures, standings and clubs in Room.
- Offline actions are stored in a Room table in the exact `/offline-sync` action format, with a `base_version`.
- WorkManager replays the queue when connectivity returns.
- The server orders actions by `queued_at` and resolves each one as `appended`, `rebased_append`, `skipped_duplicate` or `server_wins`.
**Consequences:**
- The server stays authoritative.
- The app shows a result for every action in plain language and clears the queue.

## ADR-009: MediaMTX as the media server, with the API as the publish authority
**Status:** Accepted
**Decision:** One MediaMTX container serves RTMP, HLS and WebRTC (WHIP/WHEP). Its `authMethod: http` hook asks the API
whether a stream key is active; revoking a key also kicks live sessions through the MediaMTX control API.
**Consequences:** Revocation cuts ingest in well under 2 s. No key logic lives in the media server.

## ADR-010: On-demand compositor owned by the media server
**Status:** Accepted
**Decision:** `costream/<id>` and `matchfeed/<id>` are `runOnDemand` paths. The ffmpeg compositor reads the layout
from the API; host handoff kicks the path so MediaMTX restarts it with the new layout, and stops it when no one watches.
**Consequences:** The composite URL never changes across handoffs and no orphaned ffmpeg process can exist.

## ADR-011: Guest boundary as middleware
**Status:** Accepted
**Decision:** A pure ASGI middleware rejects every write carrying a `guest_*` bearer before routing (403
`GUEST_WRITE_FORBIDDEN`). The cart-merge probe calls the same rule.
**Consequences:** New write routes are protected by default; UI hiding is never the control.

## ADR-012: Generation-checked caches for the load-tested reads
**Status:** Accepted
**Decision:** QR `inspect` views and the DLQ status are cached in process. Every write that can change them bumps a
generation counter; a reader only stores its result if no write happened during the read.
**Consequences:** k6 (500 + 50 VUs) runs at p95 117 ms with 0% errors while dynamic QR routes still change instantly.
