# YFCP — Yelp Factory Control Panel

Desktop operator console for the **yelp-factory-v2** engine. Built with **Tauri 2 + React 18 + Vite**, styled with **Tailwind CSS** and shadcn-style primitives, tables by **TanStack Table**, charts by **Tremor**.

> The console is the operator surface. Business rules, locks and writes stay inside the engine — the UI never bypasses `src/core/*`.

## What's in the box

26 screens covering the full spec, plus the multi-machine **Nodes** registry:

| Group | Screens |
|-------|---------|
| **Operate** | Dashboard, Accounts, Account detail, Adopt, Batches, Sessions, Login / Reauth, Warming, Reviews, Clients, Pools |
| **Monitor** | Trust, Velocity, Audit, Volume, Reports, Alerts |
| **System** | Reaper, Lifecycle, Fingerprints, Governor, System flags, Selectors, Logs, Nodes, Health, Data, Config |

UX details:

- Custom frameless titlebar with native window controls (Tauri only)
- Command palette — `Ctrl/Cmd + K`
- Collapsible sidebar, dark/light theme, persisted workspace preferences
- Native file pickers, desktop notifications, tray icon and window-state restore
- Toasts, confirm dialogs, JSON editors with validation, live log stream

## Requirements

- Node.js 20+
- Rust **1.90.0** — pinned in [`rust-toolchain.toml`](rust-toolchain.toml); `rustup` installs it automatically. Run `rustup show` to confirm the active toolchain before building.
- Visual Studio Build Tools with the C++ workload
- WebView2 runtime (preinstalled on Windows 10/11; required on Server)

## Run

```bash
npm install
npm run dev          # browser preview at http://localhost:1420
npm run desktop:dev  # native window with HMR
```

## Build the installer

```bash
rustup show          # must report 1.90.0 (pinned by rust-toolchain.toml)
npm run desktop:build
```

The NSIS installer lands in `src-tauri/target/release/bundle/nsis/`.

> **Secrets:** the admin bearer token is stored in **Windows Credential Manager**
> (`com.yfcp.console` / `admin-api-token`, DPAPI-protected). `tauri-plugin-store`
> only keeps the base URL. An older build's plaintext token is migrated out of
> `settings.json` on first read. The browser dev build falls back to
> `localStorage` — use it only for development.

## Tests

```bash
npm run lint                 # oxlint
npx tsc -b                   # typecheck
npm run build                # production bundle
npm run fixture              # engine fixture on 127.0.0.1:8799
node tests/e2e-web.mjs       # browser mode (vite dev + fixture)
node tests/e2e-packaged.mjs setup   # packaged app over CDP (see file header)

cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --lib             # relay loopback/redirect/scheme/method tests
```

CI (`.github/workflows/yfcp-ci.yml`) runs the frontend + Rust jobs on every
change and builds the NSIS installer for `v*` tags.

The endpoint wishlist for the engine team lives in
[`docs/engine-contract.md`](docs/engine-contract.md). Multi-machine setup
(central engine + shared Postgres, several consoles) is documented in
[`docs/multi-machine.md`](docs/multi-machine.md).

## Project layout

```
src/
  components/
    layout/      shell, sidebar, status bar, command palette
    shared/      DataTable (TanStack), badges, stat tiles, JSON viewer
    ui/          primitives: button, card, dialog, tabs, form, table…
  pages/         one file per spec screen
  lib/
    bridge.ts    admin API client (Rust relay in Tauri), settings + plugin wrappers
    hooks.ts     React Query hooks; live engine data with mock fallback
    mock.ts      deterministic sample data (used while the engine is offline)
    utils.ts
  stores/        zustand stores (theme, sidebar, palette, saved imports)
  types/         domain types mirroring the engine schema
src-tauri/
  src/lib.rs     plugins, tray, window lifecycle, app_info + admin_request commands
  tauri.conf.json
  capabilities/default.json
```

## Wiring the engine

Start the engine with `yf serve` (binds `127.0.0.1:8787`, token from
`YF_ADMIN_TOKEN`). Then open **Workspace settings → Console connection** and set
the URL + token. The shell relays requests through the Rust `admin_request`
command because the engine does not send CORS headers.

No engine handy? A dependency-free fixture implements the same contract for UI
and integration tests:

```bash
npm run fixture                       # http://127.0.0.1:8799, token=fixture-token
MODE=error npm run fixture            # protected endpoints return 500
MODE=slow npm run fixture             # 15s delay, exercises the 10s relay timeout
MODE=empty npm run fixture            # empty datasets
```

Data flow:

- `useApiHealth` polls `GET /health` (public) every 15s and acts as the connection probe.
- `useEngineReport` → `GET /report`, `useEngineEvents` → `GET /events`,
  `usePoolStats` → `GET /api/pool`, `useImportPool` → `POST /api/pool/import`,
  `useEngineAccounts` → `GET /api/accounts`, `useSignupBatch` → `POST /signup`.
- Every screen consumes `src/lib/hooks.ts`; each hook returns
  `{ data, source }` and falls back to `mock.ts` when the API is offline, so the
  console never shows an empty/crashed page.
- Imported accounts/proxies are persisted with `tauri-plugin-store` (desktop) or
  `localStorage` (browser) in `src/stores/imports.ts`.

The engine exposes aggregates plus the account inventory (`GET /api/accounts`).
Screens without an endpoint yet (clients, reviews, selectors, flags, audit…)
return the sample dataset and are labelled **endpoint not wired**; wiring them
later only requires changing that hook's `queryFn`.

All writes must go through the engine so locks, quotas and the state machine stay authoritative.

## Safety rails encoded in the UI

- Destructive actions require explicit confirmation (delete, emergency stop, volume 0)
- Volume pin warns before silencing the pipeline
- Fingerprint salt rotation warns about farm-wide impact
- Reaper prefers a dry run and shows what would be deleted
