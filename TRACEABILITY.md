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
