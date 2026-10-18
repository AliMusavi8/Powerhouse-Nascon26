# Day 2 Phases: build → verify → move on

Each phase ends with a **verification gate**. Do not start the next phase until every gate box is ticked.
Details for each item are in `PLAN.md` (section numbers in brackets). Push targets: W2 < 12:45, W3 < 13:45, W4 < 14:05:00.

Legend: `[ ]` pending · `[x]` verified

---

## Phase 1: Foundation (config, crypto, schema, seed) [PLAN §3, §4.0]

Build:
- [x] `DAY2_SALT` read from env (`config.py`), forwarded in `docker-compose.yml`, `.env.example`
- [x] `crypto.sign_day2()`
- [x] Phase II tables in `schema.sql` + `db.TABLES`
- [x] Reset seeds `player-beta-2`, `match-m1` (in_progress 1-0), QR mappings `m1-live` / `p-alpha-1` / `c-alpha-1`, `guest_anon_tok_7721`, empty cart for `player-alpha-1`
- [x] Guest write guard middleware (403 `GUEST_WRITE_FORBIDDEN`)

Verification gate:
- [x] Unit test: Appendix A vector 1 (4-key) and vector 2 (legacy 2-key) with salt `T01D27ad7ffff12e`
- [x] `POST /audit/v1/reset` → 200, and `GET /audit/v1/score/match-m1` → in_progress, home 1, away 0
- [x] `Authorization: Bearer guest_anon_tok_7721` on `POST /audit/v1/events`, `/audit/v1/checkout`, `/api/v1/chat` → 403 `GUEST_WRITE_FORBIDDEN`
- [x] Day 1 unit + integration suites still green (`RUN_INTEGRATION=1 ./run_tests.sh`)

## Phase 2: Contract endpoints [PLAN §4.1-4.7]

Build:
- [x] `POST /audit/v1/stream/key` (generate / rotate / revoke)
- [x] `POST /audit/v1/costream/session` (validation order + handoff + idempotency)
- [x] `GET /audit/v1/qr/{id}`, `/export.{svg,png,pdf}`, `GET /q/{short_code}`, match status events (postponed etc.)
- [x] `POST /audit/v1/guest/cart-merge`
- [x] `POST /audit/v1/moderation/test` + DLQ
- [x] `GET /metrics`, `DELETE /audit/v1/privacy/user/{id}`

Verification gate (`tests/integration/test_day2_contract.py`):
- [x] Every example request in spec §5.4-5.9 returns the exact keys, status codes and a signature that matches `sign_day2` recomputed by the test
- [x] Hidden scenario 1: host drop → `active_host` = participants[1], count 3, same `chat_room_id`
- [x] Hidden scenario 2: `match_end` on match-m1 → same `short_url`, `target_route` `/vod`, new signature
- [x] Hidden scenario 3: 10 parallel moderation requests → all 200, `kicked_users == ["user-spammer"]`
- [x] Hidden scenario 4: cart-merge twice → 200 both, `total_items: 1`; different user → 409
- [x] Error codes: `PLAYER_NOT_FOUND`, `STREAM_NOT_FOUND`, `KEY_REVOKED`, `COSTREAM_SESSION_FULL`, `UNSUPPORTED_LAYOUT`, `QR_NOT_FOUND`, `VARIANT_NOT_FOUND`, `OUT_OF_STOCK`, `GUEST_TOKEN_ALREADY_MERGED`
- [x] `/metrics` content type `text/plain; version=0.0.4` with all 5 metric names
- [x] Unit tests for the 5 domain modules ≥85% (`COVERAGE_DAY2.json` generated)
- [x] Day 1 suites still green → **commit + push (W2)**

## Phase 3: Realtime + Guest Web Player [PLAN §4.6, §6]

Build:
- [x] Score payload in realtime messages; WS token optional; SSE `GET /api/v1/matches/{id}/stream`
- [x] Guest endpoints (`/api/v1/guest/session|matches|cart|chat`), member chat `POST /api/v1/chat`, `/api/v1/cart/merge`
- [x] `/web/*` pages with all 9 `data-testid`s, auth modal, WCAG basics

Verification gate:
- [x] Browser: `http://localhost:8080/q/m1-live` → `/web/matches/match-m1/live`, score `1 - 0`, no modal
- [x] POST a goal → banner updates in under 500 ms with no reload
- [x] Guest chat send → no message appended, modal visible. Add to cart → count `1`
- [x] NFR-1 probe: 25 WS clients receive a score event, p95 < 500 ms

## Phase 4: Media server + full compose stack [PLAN §5, §7.1]

Build:
- [x] MediaMTX (1935 / 8888 / 8889), auth hook, revoke → kick, costream compositor, matchfeed slate
- [x] MinIO + VOD upload
- [x] Selenium hub + 3 nodes exactly per spec

Verification gate:
- [x] `docker compose down -v && DAY1_SALT=x DAY2_SALT=y docker compose up -d --build` → `/health` 200 in under 120 s
- [x] `curl localhost:4444/status` → `ready: true`, 3 nodes
- [x] `ffmpeg -re ... -f flv rtmp://localhost:1935/live/<active key>` publishes. `curl localhost:8888/live/<key>/index.m3u8` → 200
- [x] Revoke the key → publisher cut within 2 s. Republish with the revoked key → rejected
- [x] `curl localhost:8888/costream/cs-session-101/index.m3u8` → 200

## Phase 5: QA harness (Selenium, k6, CI) [PLAN §7.2-7.6]

Build:
- [x] `tests/selenium/test_guest_grid.py` (3 required tests + a11y checks)
- [x] `tests/k6_load.js` (verbatim spec script)
- [x] `.github/workflows/autograde.yml`

Verification gate:
- [x] `pytest -n 3 tests/selenium/ --junitxml=tests/reports/selenium-report.xml` → all pass on the Grid
- [x] `k6 run --summary-export=tests/reports/k6-summary.json tests/k6_load.js` → 0% failed, p95 < 800 ms
- [x] CI run on GitHub green (run on `3c02d2e`) → **commit + push (W3)**

## Phase 6: Mobile + Appium [PLAN §8, §7.4]

Build:
- [x] `nascon://` intent-filter, `singleTask`, deep-link router, splash skipped for deep links
- [x] Guest match live + co-stream screens (no login wall), test tags as resource ids
- [x] Video player (native HLS) and live chat on both screens
- [x] In-app QR scanner (ZXing) and broadcaster screen (stream key, RTMP/WHIP URLs, rotate/revoke, preview)
- [x] APK rebuilt: `mobile/release/scorix-day2.apk` (debug-signed; release keystore is not on this laptop)

Verification gate (on the Infinix phone):
- [x] `adb shell am start -W -a android.intent.action.VIEW -d "nascon://entity/match-m1"` → match screen in under 2 s, logged out too
- [x] Same for `nascon://stream/cs-session-101`
- [x] `curl localhost:4723/status` → ready. `pytest tests/appium --junitxml=tests/reports/appium-report.xml` passes
- [x] Cross-surface chat test passes (app + grid browser in under 3 s)

## Phase 7: Delivery [PLAN §12]

- [x] `COVERAGE_DAY2.json`, `TRACEABILITY.md` (Phase II IDs), README Day 2 section, ADRs
- [x] `tests/reports/selenium-report.xml`, `appium-report.xml`, `k6-summary.json` committed
- [x] Salt grep clean. `git merge-base --is-ancestor 596c2bc HEAD`
- [x] Cold boot test (`down -v` + `up --build`): health + 3 grid nodes in 15 s
- [ ] **Final push before 14:00 (grace 14:05:00)**

## Phase 8: Extended window additions (deadline moved to 14:20)

- [x] FR-3.1 athlete profile + concurrency-safe follow/unfollow (40-request toggle burst, no drift)
- [x] FR-3.2 member stream key route for the app
- [x] FR-3.3 host controls: signed invite token, mute, spotlight, kick
- [x] FR-5.2 notification bus: 3 attempts with exponential backoff, then DLQ (`simulate_dlq: true`)
- [x] App: Scan QR, Go live, athlete profile with Follow; Appium 3/3 on the new build
