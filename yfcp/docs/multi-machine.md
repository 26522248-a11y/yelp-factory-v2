# Multi-machine deployment

Goal: several operator machines see the **same, continuously updated data**.
That is achieved by running **one engine + one Postgres** and pointing every
console at it (model "A+"). Workers can be added later without changing the
console contract.

```
        ┌──────────────────────────── server / VM ───────────────────────────┐
        │  Postgres 16 (private)  ──  yf serve (admin API, :8787)             │
        │                                 │                                   │
        └─────────────────────────────────┼───────────────────────────────────┘
                                          │ private LAN or WireGuard/Tailscale
                 ┌────────────────────────┼─────────────────────────┐
                 │                        │                         │
          Console (operator A)     Console (operator B)      Console (operator C)
          YFCP + token in          YFCP + token in          YFCP + token in
          Windows Credential Mgr   Windows Credential Mgr   Windows Credential Mgr
```

All screens poll the central engine (`/report`, `/events`, `/api/pool`,
`/api/accounts`) on a 15–30 s interval, so every machine converges on the same
state. The status bar shows the last successful sync.

## 1. Server

1. Install Postgres and create the database:
   `YF_DATABASE_URL=postgresql+psycopg://yf:PASS@127.0.0.1:5433/yelp_factory`
   (or a dedicated DB host; use TLS when it is not loopback).
2. Put the engine checkout on the server, create `.env`:
   ```
   YF_DATABASE_URL=...
   YF_MASTER_KEY=<same value on every worker that shares accounts>
   YF_ADMIN_TOKEN=<long random value>
   YF_ADMIN_HOST=0.0.0.0
   YF_ADMIN_PORT=8787
   ```
3. `yf migrate` then `yf serve` (as a Windows service / systemd unit).
4. Firewall: allow `8787` **only** from the VPN/LAN, never from the internet.
5. Back up Postgres daily and rehearse a restore (`docs/RUNBOOK.md`).

### Preferred network: VPN, no TLS

Tailscale/WireGuard gives an encrypted path. Private addresses
(`10/8`, `172.16/12`, `192.168/16`, `100.64/10`, IPv6 ULA/link-local) may use
plain HTTP; the console relay accepts them after the operator approves the
endpoint.

### Public network: HTTPS reverse proxy

If operators connect over the internet, terminate TLS with Caddy/nginx and
proxy to `127.0.0.1:8787`:

```
engine.example.com {
    reverse_proxy 127.0.0.1:8787
}
```

Public HTTP is rejected by the console relay. HTTPS works out of the box
(rustls). Keep the engine itself bound to loopback in this setup.

## 2. Each console machine

1. Install `YFCP_<version>_x64-setup.exe` (per-user).
2. Workspace settings → **Console connection**:
   - URL: `http://<vpn-ip>:8787` (private) or `https://engine.example.com`;
   - token: the server's `YF_ADMIN_TOKEN`.
3. **Save connection**. The first save approves the remote origin:
   - stored in `%APPDATA%\com.yfcp.console\remote-endpoint.txt`;
   - the token goes to Windows Credential Manager;
   - `settings.json` keeps only the URL.
4. Verify the line under the form: `engine v… · contract v… · schema … · host …`.
   A contract mismatch is shown as a global banner.

The relay refuses any other host, any redirect, and public plain HTTP. Requests
remain limited to `GET`/`POST` with size/time caps.

## 3. Shared data semantics

| Data | Shared? | Notes |
|---|---|---|
| Accounts | yes | `GET /api/accounts`, live rows |
| Report/aggregates, pool counters, events | yes | same central DB |
| Proxy imports | yes (engine pool) + local copy | console also keeps the rows for offline display |
| Account imports | **local only** | needs `POST /api/accounts` (planned) |
| Clients/reviews/warming/selectors/... | **pending engine endpoints** | labelled "endpoint not wired" |
| Artifacts/exports | local | move to SMB/MinIO before adding workers |

Multiple consoles can safely act at once — the engine enforces account locks,
browser slots and quotas in Postgres.

## 4. Adding worker machines (next phase)

- Keep the single Postgres; each worker machine runs its own GPM Login Global
  and browser slots, with a shared `YF_MASTER_KEY`.
- Node registry is **live**: every console heartbeats automatically and the
  **Nodes** screen shows online/offline machines, roles, versions, capacity,
  active browser slots and per-machine run progress (running / done 24h).
  `yf serve` registers as `engine`; `yf schedule` registers as `worker`
  (`YF_NODE_ID` / `YF_NODE_NAME` override the hostname). Runs and browser slots
  store `node_id`, so progress is attributed to the machine that executed it.
- Next: schedule jobs only to nodes with free slots (routing still uses global
  locks/slots today), move artifacts/exports to shared storage.
- Use NTP on every machine; account locks assume reasonably synced clocks.

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| “remote endpoint not configured” | URL not approved on this machine | Save connection again |
| “plain HTTP is only allowed for private/LAN addresses” | public http URL | use HTTPS or the VPN address |
| “Admin API rejected the token (401)” | token mismatch | copy `YF_ADMIN_TOKEN` from the server `.env` |
| Banner “Version mismatch” | console/engine contract differ | update both to the same release |
| Data feels stale | poll interval | press Retry in the banner / reopen the page; interval is 15–30 s |

## 6. Known limits

- One engine process (single writer). HA/multiple API replicas are not supported
  yet.
- One shared admin token; per-operator tokens/RBAC are planned.
- Console-side imports are per machine until the engine owns those writes.
- No auto-update; install new releases manually per machine.
