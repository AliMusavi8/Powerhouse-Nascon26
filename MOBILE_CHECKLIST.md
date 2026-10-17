# Mobile Checklist (Android, Kotlin + Compose)

Spec references: 8.2 (screens), 8.3 (accounts), 8.4 (offline desk check), 8.6 (UI/HCI), 5.14 (sync format), NFR-4.

## Setup and security
- [x] Project in `mobile/`, package `com.nascon.app`, minSdk 26, builds offline
- [x] Network security config allows cleartext HTTP (LAN backend)
- [x] Server URL setting on login (default `http://10.0.2.2:8080`), persisted
- [x] JWT stored encrypted (AES-GCM key in Android Keystore)
- [x] API client maps `{"error":{code,message}}` to plain-language messages (never raw codes)
- [x] Logout clears token and cached user data

## Screens (8.2)
- [x] Login: email + password, loading state, plain error, demo account hints
- [x] Home: role-aware, bottom navigation (Fixtures, Standings, Store, Club, Profile)
- [x] Fixtures: list with status (Live / Upcoming / Full time) as text + icon, and time; tap opens match
- [x] Match detail: large live score, WebSocket updates, event timeline (corrections shown), pinned product card
- [x] Standings: points table, qualification status as icon + text + key, tie-break note
- [x] Club profile: info, home venue, socials, staff, history, roster
- [x] Store: catalogue, variant picker, cart, discount code, checkout with mock token choice
- [x] Receipt: view, download PDF, open/share PDF; order list
- [x] Roster management (Club Manager only): add, transfer, loan, release, each with confirm dialog
- [x] Scoring entry (League Organizer only): event types from server `scoring_events`, discipline, start/end, compensating event
- [x] Sync status: always-visible Online / Offline / Syncing bar, pending queue screen
- [x] Profile: user, role, tenant, server, logout

## Sport-agnostic rules
- [x] No sport or event names in code; event buttons built from `scoring_events`
- [x] Event labels derived from ids (`three_pointer` -> "Three pointer")
- [x] Innings fields (wickets/overs) shown only when present

## Offline (8.4)
- [x] Fixtures, standings, club profiles and match detail cached in Room
- [x] Cached screens open in airplane mode with "Offline" indicator and "saved at" time
- [x] Offline score and roster actions stored in Room queue in the exact 5.14 action format
- [x] Pending actions shown as "pending" and survive force-close
- [x] Auto sync on reconnect (WorkManager, CONNECTED constraint) + "Sync now" button
- [x] Per-action result (applied / rejected / duplicate) in plain language, then queue cleared
- [x] Error-code to sentence map (e.g. `SQUAD_FULL` -> "The destination squad is full")

## UI / HCI (8.6)
- [x] Tenant colours (`#1E4FD8`, `#F5B700`) and logo text from `/me` branding
- [x] Light and dark themes, dynamic colour off
- [x] 48 dp tap targets; content descriptions on icons
- [x] Loading, success (snackbar) and error feedback on every action
- [x] Empty states ("No matches yet", "Your cart is empty", "No pending actions")
- [x] Confirm before risky actions (release, transfer, loan, checkout, compensation, logout)
- [x] Status never by colour alone
- [x] Works at 360x640 dp and after rotation (state kept)
- [x] Back always works, no dead ends
- [x] Each role sees only its own actions (`can_score`, `can_manage`, permissions)

## Delivery
- [x] Signed release APK at `mobile/release/app-release.apk` (installs on Android 10+)
- [x] Keystore and passwords not committed
- [x] README mobile section (build, install, server URL, demo accounts)
- [x] TRACEABILITY mobile paths
