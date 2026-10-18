# Traceability Matrix

Every functional (FR) and non-functional (NFR) requirement mapped to source files and automated tests.

| ID | Requirement | Source | Tests |
|---|---|---|---|
| FR-1.1 | Multi-sport taxonomy, mystery sport from JSON | `backend/app/domain/sports.py`, `backend/app/services/sports.py`, `backend/app/seed/sports.json` | `tests/unit/test_scoring.py::test_sport_validation`, `::test_seed_sports_are_valid`, `tests/integration/test_scoring_api.py::test_mystery_sport_full_flow` |
| FR-1.1 | Event-sourced scoring, compensating events, signatures | `backend/app/domain/scoring.py`, `backend/app/services/matches.py`, `backend/app/crypto.py`, `backend/app/schema.sql` (`events`) | `tests/unit/test_scoring.py`, `tests/integration/test_scoring_api.py` |
| FR-1.2 | League and tournament setup (leagues, fixtures, seasons) | `backend/app/services/leagues.py`, `backend/app/domain/fixtures/` | `tests/integration/test_standings_api.py`, `tests/unit/test_fixtures.py` |
| FR-1.3 | Round robin (circle method, byes, withdrawals) | `backend/app/domain/fixtures/round_robin.py` | `tests/unit/test_fixtures.py::test_round_robin_properties`, `::test_round_robin_ids_and_withdrawals` |
| FR-1.3 | Swiss system (score groups, no rematches, bye, Buchholz) | `backend/app/domain/fixtures/swiss.py` | `tests/unit/test_fixtures.py::test_swiss_*` |
| FR-1.3 | Single elimination (seeding, byes, third place) | `backend/app/domain/fixtures/elimination.py` | `tests/unit/test_fixtures.py::test_single_elim_byes_and_results`, `::test_seed_order` |
| FR-1.3 | Double elimination (losers bracket, grand final reset) | `backend/app/domain/fixtures/elimination.py` | `tests/unit/test_fixtures.py::test_double_elim_*` |
| FR-1.3 | Match status state machine, realtime broadcast | `backend/app/domain/scoring.py` (`check_event`), `backend/app/services/realtime.py`, `backend/app/routes/api.py` (`/ws/matches`) | `tests/unit/test_scoring.py::test_outcomes`, `tests/integration/test_scoring_api.py` |
| FR-1.4 | Standings, tie-breakers, H2H mini-league, qualification | `backend/app/domain/standings.py`, `backend/app/services/leagues.py` | `tests/unit/test_standings.py`, `tests/integration/test_standings_api.py` |
| FR-2.1 | Club profiles, tenant isolation, white-label branding | `backend/app/routes/api.py` (`/clubs`, `/me`), `backend/app/seed/baseline.json`, `backend/app/domain/rbac.py` | `tests/integration/test_rbac_api.py::test_full_matrix` |
| FR-2.2 | Roster: transfer, loan, release, ordered rules, audit trail | `backend/app/domain/roster.py`, `backend/app/services/roster.py` | `tests/unit/test_roster.py`, `tests/integration/test_roster_api.py` |
| FR-2.3 | Merchandise store, variants, discount, mock gateway, PDF receipt, order events | `backend/app/domain/store.py`, `backend/app/services/store.py`, `backend/app/services/pdf.py`, `backend/app/services/queue.py`, `backend/worker.py` | `tests/unit/test_store.py`, `tests/integration/test_store_api.py` |
| FR-5.1 | Five-tier RBAC, scoped permissions, negative tests | `backend/app/domain/rbac.py`, `backend/app/auth.py`, `backend/app/routes/rbac.py` | `tests/unit/test_rbac.py`, `tests/integration/test_rbac_api.py` |
| NFR-3 | Concurrency correctness (no overselling) | `backend/app/services/store.py` (`_reserve`), `backend/app/schema.sql` (`CHECK stock >= 0`) | `tests/integration/test_store_api.py::test_twenty_concurrent_buyers_one_unit` |
| NFR-4 | Offline tolerance: cache, persistent queue, sync with conflicts | `backend/app/domain/sync.py`, `backend/app/services/sync.py`, `mobile/app/src/main/java/com/nascon/app/data/Repo.kt` (Room cache), `data/Db.kt` (`pending_actions`), `data/Sync.kt` (queue, `SyncWorker`, `NetworkMonitor`), `ui/ProfileScreens.kt` (`QueueScreen`) | `tests/unit/test_sync.py`, `tests/integration/test_sync_api.py` |
| NFR-5 | Security: JWT verification, rate limiting, input validation, body limit | `backend/app/auth.py`, `backend/app/main.py` (rate limit, 413), `backend/app/domain/validate.py` | `tests/integration/test_rbac_api.py::test_token_attacks`, `::test_rate_limit`, `tests/integration/test_scoring_api.py::test_validation_and_limits` |
| NFR-7 | Reproducibility: one-command stack, repeatable reset | `docker-compose.yml`, `backend/Dockerfile`, `backend/app/seed.py`, `backend/app/db.py` | `tests/integration/conftest.py` (reset before each test) |

## Mobile app (spec section 8)

Paths are relative to `mobile/app/src/main/java/com/nascon/app/`.

| Spec | Requirement | Source |
|---|---|---|
| 8.2 | Login, server address, role-aware home | `ui/LoginScreen.kt`, `data/Session.kt`, `ui/MainScreen.kt` |
| 8.2 | Fixtures list with status and time | `ui/LeagueScreens.kt` (`FixturesScreen`) |
| 8.2 | Match detail: live score (WebSocket), timeline, pinned product | `ui/MatchScreen.kt` |
| 8.2 | Standings with qualification status | `ui/LeagueScreens.kt` (`StandingsScreen`) |
| 8.2 | Club profile: info, roster, staff, venue | `ui/ClubScreens.kt` (`ClubScreen`, `Info`) |
| 8.2 | Store: catalogue, variants, cart, checkout, receipt PDF | `ui/StoreScreens.kt` |
| 8.2 | Roster management (club manager) | `ui/ClubScreens.kt` (`RosterDialog`, `AddPlayerDialog`) |
| 8.2 | Scoring entry and compensating event (league organiser) | `ui/MatchScreen.kt` (`OrganiserBar`) |
| 8.2 | Sync status indicator and pending queue | `ui/Components.kt` (`NetBar`), `ui/ProfileScreens.kt` (`QueueScreen`) |
| 8.4 | Cache in local database, offline indicator | `data/Repo.kt`, `data/Db.kt`, `ui/Components.kt` (`NetBar`) |
| 8.4 | Persistent queue in the 5.14 format, survives force-close | `data/Sync.kt` (`SyncManager.send`), `data/Db.kt` (`PendingAction`) |
| 8.4 | Automatic sync on reconnect and Sync button, plain-language results | `data/Sync.kt` (`SyncWorker`, `syncNow`), `data/Messages.kt` |
| 8.6 | Tenant branding, light and dark themes, 48 dp targets, status not by colour alone | `ui/Theme.kt`, `ui/Components.kt` |
| 8.6 | Confirm risky actions, empty and loading states, plain errors | `ui/Components.kt` (`Confirm`, `Empty`, `Loading`, `ErrorState`), `data/Messages.kt` |
| NFR-5 | JWT encrypted with an Android Keystore AES-GCM key | `data/Security.kt` |

## Part II (Day 2)

| ID | Requirement | Source | Tests |
|---|---|---|---|
| FR-3.1 | Athlete identity, concurrency-safe follow graph | `backend/app/schema.sql` (`follows`, PK per pair), `backend/app/services/observability.py` (erasure cleans follows) | `tests/integration/test_day2_contract.py::test_privacy_erasure` |
| FR-3.2 | Stream keys signed with DAY2_SALT, revoke severs ingest < 2 s, live overlays, VOD to MinIO | `backend/app/domain/streaming.py`, `backend/app/services/streams.py`, `backend/app/services/media.py` (kick), `backend/app/services/vod.py`, `media/mediamtx.yml` (auth hook, record), `backend/app/web/app.js` (overlays) | `tests/unit/test_day2_domain.py::test_stream_*`, `tests/integration/test_day2_contract.py::test_stream_key_lifecycle`, `::test_stream_key_errors` |
| FR-3.3 | 4-way co-stream, layouts, host handoff, unified chat with sequence numbers, no zombie processes | `backend/app/domain/costream.py`, `backend/app/services/costream.py`, `media/composite.sh` (MediaMTX runOnDemand), `backend/app/services/moderation.py` (`post`, `chat_rooms.seq`), `backend/app/routes/guest.py` (`/ws/costream`, `/ws/chat`) | `tests/unit/test_day2_domain.py::test_costream_*`, `tests/integration/test_day2_contract.py::test_costream_*`, `tests/appium/test_mobile_deeplink.py::test_cross_surface_chat_sync` |
| FR-4.1 | Dynamic QR: stable short URL, state-driven target route, SVG/PNG/PDF, privacy-safe telemetry, deep links | `backend/app/domain/qr.py`, `backend/app/services/qr.py`, `backend/app/routes/day2.py` (`/q/{code}`, exports), `backend/app/domain/scoring.py` (notice states), `mobile/app/src/main/AndroidManifest.xml` (intent-filter) | `tests/unit/test_day2_domain.py::test_target_routes`, `::test_qr_helpers`, `tests/integration/test_day2_contract.py::test_qr_*` |
| FR-4.2 | Zero-account guest player, short-lived guest tokens | `backend/app/web/` (player.html, app.js, app.css), `backend/app/routes/web.py`, `backend/app/routes/guest.py`, `backend/app/services/guestcart.py` (`new_session`) | `tests/selenium/test_guest_grid.py::test_1_qr_resolution_zero_friction_load` |
| FR-4.3 | Server-enforced guest read-only boundary (403 GUEST_WRITE_FORBIDDEN) | `backend/app/domain/guest.py` (`write_rejection`), `backend/app/main.py` (`GuestWriteGuard`) | `tests/unit/test_day2_domain.py::test_guest_write_rejection`, `tests/integration/test_day2_contract.py::test_guest_direct_writes_are_forbidden`, `tests/selenium/test_guest_grid.py::test_2_*` |
| FR-4.4 | Progressive registration, atomic idempotent cart merge | `backend/app/domain/guest.py` (`merge`, `cart_view`), `backend/app/services/guestcart.py`, `backend/app/web/app.js` (auth modal, `?t=` resume) | `tests/unit/test_day2_domain.py::test_cart_merge_*`, `tests/integration/test_day2_contract.py::test_cart_merge_*` |
| FR-5.2 | Notification bus, bounded retry (3), DLQ | `backend/app/domain/dlq.py`, `backend/app/services/moderation.py` (`enqueue_failures`, `dlq_status`) | `tests/unit/test_day2_domain.py::test_dlq_retry_and_dead_letter`, `tests/integration/test_day2_contract.py::test_moderation_dual_moderator_race_and_dlq` |
| FR-5.3 | Leetspeak masking, flood rejection, rate limit, idempotent kick/mute | `backend/app/domain/moderation.py`, `backend/app/services/moderation.py` | `tests/unit/test_day2_domain.py::test_leetspeak_masking`, `::test_flood_detection`, `tests/integration/test_day2_contract.py::test_moderation_*` |
| NFR-1 | Score broadcast p95 < 500 ms to 25 WebSocket clients | `backend/app/services/realtime.py` (score in payload), `backend/app/routes/api.py` (`/ws/matches`), `backend/app/routes/guest.py` (SSE) | `tests/integration/test_ws_latency.py`, `tests/selenium/test_guest_grid.py::test_3_*` |
| NFR-2 | 500 guest viewers + 50 chat posters, 0% 5xx, p95 < 800 ms | `backend/app/services/qr.py` (generation-checked cache), `backend/app/services/moderation.py` (`fast_probe`), `backend/app/main.py` (ASGI middleware) | `tests/k6_load.js` → `tests/reports/k6-summary.json` |
| NFR-6 | Prometheus `/metrics` | `backend/app/domain/metrics.py`, `backend/app/services/observability.py` | `tests/unit/test_day2_domain.py::test_metrics_render`, `tests/integration/test_day2_contract.py::test_metrics_format` |
| NFR-8 | WCAG 2.1 AA guest player | `backend/app/web/app.css` (48 px targets, contrast, focus), `backend/app/web/player.html` (ARIA, landmarks) | `tests/selenium/test_guest_grid.py::test_accessibility_targets_labels_and_keyboard` |
| NFR-9 | Privacy: no IP/UA stored, erasure within 1 s | `backend/app/schema.sql` (`qr_scan_stats`), `backend/app/services/observability.py` (`erase_user`) | `tests/integration/test_day2_contract.py::test_privacy_erasure` |
| QA | Selenium Grid 4, Appium 2, k6, GitHub Actions | `docker-compose.yml`, `tests/selenium/`, `tests/appium/`, `tests/k6_load.js`, `.github/workflows/autograde.yml` | `tests/reports/` |
