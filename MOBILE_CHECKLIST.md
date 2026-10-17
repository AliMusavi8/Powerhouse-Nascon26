# Mobile Checklist (Android, Kotlin + Compose)

Spec references: 8.2 (screens), 8.3 (accounts), 8.4 (offline desk check), 8.6 (UI/HCI), 5.14 (sync format), NFR-4.

## Setup and security
- [ ] Project in `mobile/`, package `com.nascon.app`, minSdk 26, builds offline
- [ ] Network security config allows cleartext HTTP (LAN backend)
- [ ] Server URL setting on login (default `http://10.0.2.2:8080`), persisted
- [ ] JWT stored encrypted (AES-GCM key in Android Keystore)
- [ ] API client maps `{"error":{code,message}}` to plain-language messages (never raw codes)
- [ ] Logout clears token and cached user data

## Screens (8.2)
- [ ] Login: email + password, loading state, plain error, demo account hints
- [ ] Home: role-aware, bottom navigation (Fixtures, Standings, Store, Club, Profile)
- [ ] Fixtures: list with status (Live / Upcoming / Full time) as text + icon, and time; tap opens match
- [ ] Match detail: large live score, WebSocket updates, event timeline (corrections shown), pinned product card
- [ ] Standings: points table, qualification status as icon + text + key, tie-break note
- [ ] Club profile: info, home venue, socials, staff, history, roster
- [ ] Store: catalogue, variant picker, cart, discount code, checkout with mock token choice
- [ ] Receipt: view, download PDF, open/share PDF; order list
- [ ] Roster management (Club Manager only): add, transfer, loan, release, each with confirm dialog
- [ ] Scoring entry (League Organizer only): event types from server `scoring_events`, discipline, start/end, compensating event
- [ ] Sync status: always-visible Online / Offline / Syncing bar, pending queue screen
- [ ] Profile: user, role, tenant, server, logout

## Sport-agnostic rules
- [ ] No sport or event names in code; event buttons built from `scoring_events`
- [ ] Event labels derived from ids (`three_pointer` -> "Three pointer")
- [ ] Innings fields (wickets/overs) shown only when present

## Offline (8.4)
- [ ] Fixtures, standings, club profiles and match detail cached in Room
- [ ] Cached screens open in airplane mode with "Offline" indicator and "saved at" time
- [ ] Offline score and roster actions stored in Room queue in the exact 5.14 action format
- [ ] Pending actions shown as "pending" and survive force-close
- [ ] Auto sync on reconnect (WorkManager, CONNECTED constraint) + "Sync now" button
- [ ] Per-action result (applied / rejected / duplicate) in plain language, then queue cleared
- [ ] Error-code to sentence map (e.g. `SQUAD_FULL` -> "The destination squad is full")

## UI / HCI (8.6)
- [ ] Tenant colours (`#1E4FD8`, `#F5B700`) and logo text from `/me` branding
- [ ] Light and dark themes, dynamic colour off
- [ ] 48 dp tap targets; content descriptions on icons
- [ ] Loading, success (snackbar) and error feedback on every action
- [ ] Empty states ("No matches yet", "Your cart is empty", "No pending actions")
- [ ] Confirm before risky actions (release, transfer, loan, checkout, compensation, logout)
- [ ] Status never by colour alone
- [ ] Works at 360x640 dp and after rotation (state kept)
- [ ] Back always works, no dead ends
- [ ] Each role sees only its own actions (`can_score`, `can_manage`, permissions)

## Delivery
- [ ] Signed release APK at `mobile/release/app-release.apk` (installs on Android 10+)
- [ ] Keystore and passwords not committed
- [ ] README mobile section (build, install, server URL, demo accounts)
- [ ] TRACEABILITY mobile paths
