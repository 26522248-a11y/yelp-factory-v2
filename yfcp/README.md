# YFCP — Yelp Factory Control Panel

Desktop operator console for the **yelp-factory-v2** engine. Built with **Tauri 2 + React 18 + Vite**, styled with **Tailwind CSS** and shadcn-style primitives, tables by **TanStack Table**, charts by **Tremor**.

> The console is the operator surface. Business rules, locks and writes stay inside the engine — the UI never bypasses `src/core/*`.

## What's in the box

26 screens covering the full spec:

| Group | Screens |
|-------|---------|
| **Operate** | Dashboard, Accounts, Account detail, Adopt, Batches, Sessions, Login / Reauth, Warming, Reviews, Clients, Pools |
| **Monitor** | Trust, Velocity, Audit, Volume, Reports, Alerts |
| **System** | Reaper, Lifecycle, Fingerprints, Governor, System flags, Selectors, Logs, Health, Data, Config |

UX details:

- Custom frameless titlebar with native window controls (Tauri only)
- Command palette — `Ctrl/Cmd + K`
- Collapsible sidebar, dark/light theme, persisted workspace preferences
- Native file pickers, desktop notifications, tray icon and window-state restore
- Toasts, confirm dialogs, JSON editors with validation, live log stream

## Requirements

- Node.js 20+
- Rust 1.77+ (`rustup`, MSVC toolchain)
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
npm run desktop:build
```

The NSIS installer lands in `src-tauri/target/release/bundle/nsis/`.

## Project layout

```
src/
  components/
    layout/      shell, sidebar, status bar, command palette
    shared/      DataTable (TanStack), badges, stat tiles, JSON viewer
    ui/          primitives: button, card, dialog, tabs, form, table…
  pages/         one file per spec screen
  lib/
    bridge.ts    Tauri invoke / plugin wrappers with browser fallbacks
    mock.ts      deterministic demo data (swap for the admin API)
    utils.ts
  stores/        zustand stores (theme, sidebar, palette)
  types/         domain types mirroring the engine schema
src-tauri/
  src/lib.rs     plugins, tray, window lifecycle, app_info command
  tauri.conf.json
  capabilities/default.json
```

## Wiring the engine

`src/lib/mock.ts` is the only source of demo data. Replace the reads in pages with calls to:

- `GET  http://127.0.0.1:8787/report` — dashboard aggregates
- `GET  http://127.0.0.1:8787/events` — timeline and logs
- `POST http://127.0.0.1:8787/signup` — account creation
- `yf` CLI via `tauri-plugin-shell` — long-running operations

All writes must go through the engine so locks, quotas and the state machine stay authoritative.

## Safety rails encoded in the UI

- Destructive actions require explicit confirmation (delete, emergency stop, volume 0)
- Volume pin warns before silencing the pipeline
- Fingerprint salt rotation warns about farm-wide impact
- Reaper prefers a dry run and shows what would be deleted
