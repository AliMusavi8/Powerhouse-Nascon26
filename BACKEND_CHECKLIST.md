# Backend Checklist

Legend: `[x]` done · `[ ]` pending

## Phase 0: Platform skeleton
- [x] `git init`, `.gitignore`, `.env.example`
- [x] `docker-compose.yml` (api, db, redis, worker) with healthchecks, `DAY1_SALT: ${DAY1_SALT}`
- [x] `backend/Dockerfile`, `requirements.txt`
- [x] `config.py`: env-only settings
- [x] `db.py` connection pool + `schema.sql`
- [x] `errors.py`: error envelope + Appendix B codes
- [x] Middleware: 1 MB body limit (413), JSON validation errors (400), no 5xx leaks
- [x] `crypto.py`: canonical JSON, HMAC signature, lots key (Appendix A vectors)
- [x] `seed/sports.json` + `seed.py` baseline (tenants, leagues, clubs, players, store, users)
- [x] `GET /health`
- [x] `POST /audit/v1/reset` (seed + stock, repeatable)
- [x] Stack boots locally with `docker compose up -d --build`
- [x] First commit + push

## Phase 1: Fixtures (FR-1.3)
- [x] Round robin (circle method, byes, legs, withdrawals forfeit/void, summary)
- [x] Swiss (exact R1, standings + Buchholz, bye selection, min-diff rematch-free matching, NO_VALID_PAIRING)
- [x] Single elimination (seed order, byes, results propagation, third place)
- [x] Double elimination (WR/LR/GF routing, counts, GF2 conditional/required)
- [x] `POST /audit/v1/fixtures` validation + limits
- [x] Unit tests

## Phase 2: Sports & scoring (FR-1.1)
- [x] Sport config validation (event / innings / round) + `POST /audit/v1/sports`
- [x] Match streams + append-only event log (per-match lock, idempotency, signatures)
- [x] Event rules (state machine, limits, compensation, tie-break)
- [x] Score projection `GET /audit/v1/score/{match_id}`
- [x] Unit tests

## Phase 3: Standings (FR-1.4)
- [x] `POST /audit/v1/leagues`
- [x] Table, points, diffs (event/round/NRR)
- [x] `resolve(group)` with H2H mini-league + draw lots + `resolved_by`
- [x] Qualification status + H2H matrix
- [x] Unit tests

## Phase 4: Roster (FR-2.2)
- [x] `POST /audit/v1/roster/setup`
- [x] `POST /audit/v1/roster/transfer` (8 ordered checks, effects, deferred state, idempotency)
- [x] `GET /audit/v1/roster/history/{player_id}?as_of=` (loan auto-return once)
- [x] Unit tests

## Phase 5: Store (FR-2.3, NFR-3)
- [ ] Atomic stock reservation, mock gateway, discount
- [ ] Signed receipt + PDF (`PKR 4500.00`)
- [ ] Order idempotency + domain events to Redis Stream
- [ ] `GET /audit/v1/inventory/{variant_id}`
- [ ] 20-thread concurrency test

## Phase 6: RBAC & security (FR-5.1, NFR-5)
- [ ] JWT issue/verify (reject alg:none, tampered, expired)
- [ ] Policy matrix + 7 probe routes
- [ ] `POST /audit/v1/rbac-matrix`
- [ ] Rate limiter on `/api/v1/*` + `GET /api/v1/ping`
- [ ] Matrix tests

## Phase 7: Offline sync (NFR-4)
- [ ] `POST /audit/v1/offline-sync` (ordering, duplicates, versions, conflict resolution)
- [ ] Tests

## Phase 8: Production API for the app
- [ ] Auth login + `/me`
- [ ] Leagues, fixtures, standings, match detail, clubs, products, checkout, receipt PDF
- [ ] Scoring + roster + sync routes (RBAC enforced)
- [ ] WebSocket live score + pinned product
- [ ] Demo seed data (`demo-` fixtures)
- [ ] Worker consuming domain events

## Phase 9: Delivery
- [ ] `run_tests.sh` + real `COVERAGE.json`
- [ ] `README.md`, `TRACEABILITY.md`, `ADR.md` (8 ADRs)
- [ ] Clean-machine test (`down -v` + `up --build`, timed)
- [ ] Grader-style smoke script passes
- [ ] Final push
