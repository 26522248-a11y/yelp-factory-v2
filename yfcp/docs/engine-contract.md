# Engine ⇄ console contract

Status: **draft for the engine team**. Last updated: 2026-11-13.

The console (`yfcp/`) never touches the database. It reads and writes through the
engine admin API (`yf serve`, default `http://127.0.0.1:8787`). This file is the
single list of what the UI needs. Anything marked **blocked** currently renders
the deterministic sample dataset with an `endpoint not wired` badge.

Conventions used by every endpoint below (unless noted):

- `Authorization: Bearer <YF_ADMIN_TOKEN>` — `/health` is the only public route.
- `Content-Type: application/json`, UTF-8.
- Timestamps are ISO-8601 UTC strings (`2026-11-13T09:41:00Z`).
- Errors use FastAPI's `{"detail": "..."}` with 400/401/404/409/503.
- List endpoints accept `limit` (default 100, max 1000) and `offset`.
- IDs are engine UUIDs serialised as strings.

## Implemented (console is live against these)

| Endpoint | Method | Status | Shape |
|---|---|---|---|
| `/health` | GET | **live** | `{status, db, active_profiles, gpm_transport?, version, contract_version, schema_revision, host}` |
| `/report?since=24h` | GET | **live** | `{since, accounts: {STATE: n}, runs: {STATE: n}, signups_ok, signups_failed, quarantine: {code: n}, queue_depth}` |
| `/events?limit=100&code=` | GET | **live** | `[{id, ts, level, code, msg, account_id?}]` (`level`: INFO/WARN/ERROR/DEBUG) |
| `/api/pool` | GET | **live** | `{emails: {status: n}, proxies: {status: n}, available_emails, available_proxies}` |
| `/api/pool/import` | POST | **live** | req `{kind: "emails"\|"proxies", text, dry_run}` → `{kind, total, valid, duplicates, invalid, errors: [{line, reason, row}], dry_run}` |
| `/signup` | POST | **live** | req `{count, city?, dry_run?}` → `{accepted, city, dry_run}` |
| `/api/accounts` | GET | **live** | `{items: Account[], total, limit, offset}`; filters `state` (csv), `city`, `batch_id`, `q`, `blacklisted`, `mode`; `sort` (`created_at`, `email`, `state`, `trust_score`, `last_active_at`, prefix `-` = desc) |
| `/api/accounts/{id}` | GET | **live** | one `Account`, 404 when missing, 400 for a non-UUID |
| `/api/nodes` | GET | **live** | `{items, total, online, online_window_seconds}`; each item has `progress {running,pending,done,failed}` (24 h) and `slots`; offline after 120 s |
| `/api/nodes/heartbeat` | POST | **live** | req `{node_id, name, hostname?, role (console\|worker\|engine), version?, capacity?, meta?}` → the upserted node |

`runs.node_id` and `browser_slots.node_id` (migration `0015_run_nodes`) attribute
execution/progress to a machine. `yf serve` registers as `engine`, `yf schedule`
as `worker`; console heartbeats arrive through the API.

`Account` (snake_case, as shipped):

```
id, email, first_name, last_name, state, substate, city, state_code, zip,
timezone, trust_score, trust{age,profile,consistency,diversity,warm,content,risk},
reviews_done (0/1), reviews_posted, phase (P0..P4), phase_day, tier,
blacklisted, gpm_profile_id, proxy, proxy_city, batch_id, mode
(post_review|full_warm), adopted_at, city_changed_at, last_active_at,
created_at, profile_complete (0|100), sessions_7d, photos, use_count,
supplier, home_city
```

## Requested next (console hooks are ready, response models needed)

All of these are currently **blocked**; the UI shows sample rows with the
`endpoint not wired` badge. Field names mirror `yfcp/src/types/index.ts`.

### Accounts

| Endpoint | Status | Notes |
|---|---|---|
| `POST /api/accounts` | **planned** | Import rows `{email, password, yelp_url, access_email_url}` → created `NEW` accounts |
| `PATCH /api/accounts/{id}` | **planned** | `{mode?, state?, blacklisted?}` (writes stay gated by the state machine) |

`GET /api/accounts` and the detail route are **live** (see the table above); the
console (`useEngineAccounts`) maps them onto `Account` in `src/types/index.ts`.
Remaining gaps on that screen: `sessions_7d` and `photos` are still returned as
0 until the engine exposes per-account counters.

`Account` fields: `id, email, first_name, last_name, state, substate?, city,
state_code, zip, timezone, trust_score, trust{age,profile,consistency,diversity,
warm,content,risk}, reviews_done, phase, phase_day, tier, blacklisted,
gpm_profile_id, proxy, proxy_city, batch_id?, mode, adopted_at?, city_changed_at?,
city_lock_until?, last_active_at, created_at, profile_complete, sessions_7d, photos`.

### Runs / sessions

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/runs?state=RUNNING` | **blocked** | `[{id, account_id, account_email, kind, state, current_step, step_index, total_steps, actions_done, started_at, worker_id, trace_id, screenshot?}]` |
| `GET /api/runs/{id}/steps` | **planned** | checkpoint list for the session drawer |

### Clients / reviews / assignments

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/clients` | **blocked** | `[{id, business_name, metro, category, yelp_biz_id, address, reviews_posted, avg_rating, facts{}, created_at}]` |
| `GET /api/assignments?status=` | **blocked** | `[{id, account_id, account_email, client_id, client_name, status, review_due_at, published_at?, filtered_at?, rating?, text?}]` |
| `GET /api/reviews?status=` | **blocked** | `[{id, account_email, business_name, rating, status, text, photo, posted_at, filtered_at?}]` |

### Batches / warming

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/batches` | **blocked** | `[{id, name, status, source, target_count, actual_count, notes, created_at, config{}}]` |
| `GET /api/warming/plans?date=` | **blocked** | `[{id, account_id, account_email, phase, day, budget{search,pageview,scroll,save,vote,follow,photo}, status}]` |
| `GET /api/warming/tasks?status=` | **blocked** | `[{id, account_email, kind, due_at, status}]` |
| `GET /api/warming/sessions?from=&to=` | **blocked** | `[{id, account_email, mode, started_at, duration_min, actions, trust_before, trust_after}]` |

### Trust / audit / velocity

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/trust/history?days=21` | **blocked** | `[{day, avg}]` (day already formatted for the chart) |
| `GET /api/audit/issues` | **blocked** | `[{id, kind, metro, asn, affected, severity, accounts[]}]` |
| `GET /api/velocity?days=14` | **blocked** | `[{day, posted, filtered}]` |
| `GET /api/activity?days=7` | **blocked** | `[{day, signups, sessions, reviews}]` |

### System management

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/selectors` | **blocked** | `[{key, strategies[], priority, page_tag, hits, misses, active}]` |
| `GET /api/flags` | **blocked** | `[{key, value, updated_at}]`; `POST /api/flags` `{key, value}` |
| `GET /api/config` | **planned** | redacted config for the Config screen (secrets masked) |
| `POST /api/config` | **planned** | validate + persist `config.yaml`/`.env` fields the UI edits |
| `GET /api/alerts?status=` | **planned** | `[{id, ts, severity, type, message, account_email?, status, evidence{}}]`; acknowledge/resolve endpoints |
| `POST /api/reaper/run` | **planned** | `{dry_run, targets[]}` |

## Not requests, on purpose

- No delete-account endpoint until the UI has typed confirmation end-to-end.
- No raw SQL endpoints.
- No CORS headers: the Tauri shell relays loopback HTTP through Rust
  (`admin_request`). Browser-only development must use the fixture server.

## Verification

- `yfcp/tests/fixture-server.mjs` implements every **live** endpoint above. It is
  the reference for the error/timeout states (`MODE=error|slow|empty`).
- `yfcp/tests/e2e-packaged.mjs` verifies the packaged desktop app against it:
  relay, auth, import persistence, bad URL and engine-down states.
