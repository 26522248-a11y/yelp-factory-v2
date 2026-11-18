/**
 * Minimal fixture of the engine admin API for UI/integration tests.
 *
 * No dependencies — run with Node 20+:
 *   node tests/fixture-server.mjs
 *   PORT=8800 TOKEN=test node tests/fixture-server.mjs
 *
 * Modes (MODE env):
 *   ok      normal fixtures
 *   error   every protected endpoint returns 500 (UI should fall back)
 *   slow    protected endpoints hang for 15s (UI should time out at 10s)
 *   empty   empty datasets (UI should show empty states, not crash)
 *
 * This mirrors src/api/admin.py. Keep in sync with yfcp/docs/engine-contract.md.
 */
import http from "node:http";

const PORT = Number(process.env.PORT ?? 8799);
const TOKEN = process.env.TOKEN ?? "fixture-token";
const MODE = process.env.MODE ?? "ok";
const HOST = process.env.HOST ?? "127.0.0.1";

const now = () => new Date().toISOString();

const events = Array.from({ length: 24 }).map((_, i) => ({
  id: 1000 + i,
  ts: new Date(Date.now() - i * 90_000).toISOString(),
  level: ["INFO", "INFO", "WARN", "INFO", "ERROR", "DEBUG"][i % 6],
  code: ["warming.session", "review.posted", "selector.miss", "trust.recompute", "captcha.timeout", "proxy.probe"][i % 6],
  msg: [
    "warming session completed — 11 actions, trust +2",
    "review posted biz=copper-kettle-bbq rating=5 photo=1",
    "selector miss key=login.submit_button attempt=1",
    "trust recomputed 68 -> 72",
    "captcha timeout provider=capsolver after 120s",
    "proxy probe ok latency=118ms",
  ][i % 6],
  account_id: i % 4 === 0 ? null : `acc_fixture_${(i % 6) + 1}`,
}));

const report = {
  since: "24h",
  accounts: { ACTIVE: 12, WARMING: 7, READY: 5, COOLDOWN: 2, BANNED: 2, NEW: 3 },
  runs: { DONE: 9, FAILED: 1, RUNNING: 2 },
  signups_ok: 24,
  signups_failed: 3,
  quarantine: { captcha_timeout: 1, email_rejected: 2 },
  queue_depth: 2,
};

const pool = {
  emails: { available: 31, reserved: 4, suspended: 2 },
  proxies: { available: 43, used: 12, reserved: 3, dead: 2 },
  available_emails: 31,
  available_proxies: 43,
};

const nodes = new Map();

function nodePayload(row) {
  const last = new Date(row.last_seen).getTime();
  const age = Math.max(0, Math.round((Date.now() - last) / 1000));
  const online = age <= 120;
  return {
    id: row.id,
    name: row.name,
    hostname: row.hostname ?? "",
    role: row.role ?? "console",
    version: row.version ?? null,
    capacity: row.capacity ?? 0,
    status: online ? "online" : "offline",
    online,
    age_seconds: age,
    meta: row.meta ?? {},
    progress: row.progress ?? { running: 0, pending: 0, done: 0, failed: 0 },
    slots: row.slots ?? 0,
    first_seen: row.first_seen,
    last_seen: row.last_seen,
  };
}

const seedNow = new Date().toISOString();
nodes.set("fixture-worker", {
  id: "fixture-worker",
  name: "fixture-worker",
  hostname: "worker-01",
  role: "worker",
  version: "0.1.0",
  capacity: 8,
  meta: { service: "scheduler", gpm: "3.4.1" },
  first_seen: new Date(Date.now() - 6 * 3600_000).toISOString(),
  last_seen: seedNow,
  progress: { running: 2, pending: 1, done: 7, failed: 0 },
  slots: 2,
});

const accountsFixture = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    email: "fixture.one@example.com",
    first_name: "Amelia",
    last_name: "Hart",
    state: "WARMING",
    substate: null,
    city: "Austin",
    state_code: "TX",
    zip: "78701",
    timezone: "America/Chicago",
    trust_score: 64,
    trust: { age: 10, profile: 12, consistency: 8, diversity: 14, warm: 18, content: 2, risk: 0 },
    reviews_done: 0,
    reviews_posted: 0,
    phase: "P1",
    phase_day: 3,
    tier: "B",
    blacklisted: false,
    gpm_profile_id: "gpm-1001",
    proxy: "10.0.0.1:8001",
    proxy_city: "Austin, TX",
    batch_id: null,
    mode: "full_warm",
    adopted_at: null,
    city_changed_at: null,
    last_active_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    created_at: new Date(Date.now() - 12 * 86_400_000).toISOString(),
    profile_complete: 100,
    sessions_7d: 5,
    photos: 3,
    use_count: 1,
    supplier: "acme",
    home_city: "Austin",
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    email: "fixture.two@example.com",
    first_name: "Noah",
    last_name: "Kim",
    state: "ACTIVE",
    substate: null,
    city: "Dallas",
    state_code: "TX",
    zip: "75201",
    timezone: "America/Chicago",
    trust_score: 81,
    trust: { age: 14, profile: 13, consistency: 11, diversity: 16, warm: 24, content: 3, risk: 0 },
    reviews_done: 1,
    reviews_posted: 2,
    phase: "P3",
    phase_day: 8,
    tier: "A",
    blacklisted: false,
    gpm_profile_id: "gpm-1002",
    proxy: "10.0.0.2:8002",
    proxy_city: "Dallas, TX",
    batch_id: null,
    mode: "post_review",
    adopted_at: new Date(Date.now() - 30 * 86_400_000).toISOString(),
    city_changed_at: null,
    last_active_at: new Date(Date.now() - 90 * 60_000).toISOString(),
    created_at: new Date(Date.now() - 40 * 86_400_000).toISOString(),
    profile_complete: 100,
    sessions_7d: 7,
    photos: 9,
    use_count: 2,
    supplier: null,
    home_city: "Dallas",
  },
  {
    id: "33333333-3333-4333-8333-333333333333",
    email: "fixture.three@example.com",
    first_name: "Priya",
    last_name: "Patel",
    state: "BANNED",
    substate: null,
    city: "Houston",
    state_code: "TX",
    zip: "77002",
    timezone: "America/Chicago",
    trust_score: 21,
    trust: { age: 6, profile: 5, consistency: 4, diversity: 4, warm: 2, content: 0, risk: 0 },
    reviews_done: 0,
    reviews_posted: 0,
    phase: "P2",
    phase_day: 4,
    tier: "Loai",
    blacklisted: true,
    gpm_profile_id: "gpm-1003",
    proxy: "10.0.0.3:8003",
    proxy_city: "Houston, TX",
    batch_id: null,
    mode: "full_warm",
    adopted_at: null,
    city_changed_at: null,
    last_active_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
    created_at: new Date(Date.now() - 20 * 86_400_000).toISOString(),
    profile_complete: 60,
    sessions_7d: 0,
    photos: 1,
    use_count: 0,
    supplier: "acme",
    home_city: "Houston",
  },
];

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
    // Allows the browser dev build (vite) to call the fixture directly.
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "authorization,content-type",
    "access-control-allow-methods": "GET,POST,OPTIONS",
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > 2 * 1024 * 1024) {
        reject(new Error("body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function authorized(req) {
  const header = req.headers.authorization ?? "";
  return header === `Bearer ${TOKEN}`;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? `${HOST}:${PORT}`}`);
  console.log(`${req.method} ${url.pathname}${url.search}`);

  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "authorization,content-type",
      "access-control-allow-methods": "GET,POST,OPTIONS",
      "access-control-max-age": "600",
    });
    return res.end();
  }

  if (url.pathname === "/health") {
    if (MODE === "slow") {
      await new Promise((r) => setTimeout(r, 15_000));
    }
    return send(res, 200, {
      status: "ok",
      db: true,
      active_profiles: 2,
      gpm_transport: "fixture",
      version: "0.1.0",
      contract_version: 1,
      schema_revision: "0014",
      host: "fixture-engine",
    });
  }

  if (url.pathname === "/redirect") {
    res.writeHead(302, { location: "http://evil.example/steal" });
    return res.end();
  }

  if (MODE === "slow") {
    await new Promise((r) => setTimeout(r, 15_000));
  }

  if (!authorized(req)) {
    return send(res, 401, { detail: "unauthorized" });
  }
  if (MODE === "error") {
    return send(res, 500, { detail: "fixture failure" });
  }

  if (url.pathname === "/report" && req.method === "GET") {
    const since = url.searchParams.get("since") ?? "24h";
    if (MODE === "empty") {
      return send(res, 200, { since, accounts: {}, runs: {}, signups_ok: 0, signups_failed: 0, quarantine: {}, queue_depth: 0 });
    }
    return send(res, 200, { ...report, since });
  }

  if (url.pathname === "/events" && req.method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? 100);
    const code = url.searchParams.get("code");
    const rows = MODE === "empty" ? [] : events.filter((e) => !code || e.code === code).slice(0, limit);
    return send(res, 200, rows);
  }

  if (url.pathname === "/api/nodes" && req.method === "GET") {
    const items = [...nodes.values()].map(nodePayload).sort((a, b) => String(b.last_seen).localeCompare(String(a.last_seen)));
    return send(res, 200, {
      items,
      total: items.length,
      online: items.filter((node) => node.online).length,
      online_window_seconds: 120,
    });
  }

  if (url.pathname === "/api/nodes/heartbeat" && req.method === "POST") {
    const raw = await readBody(req).catch(() => "");
    let payload = {};
    try {
      payload = JSON.parse(raw);
    } catch {
      return send(res, 400, { detail: "invalid JSON" });
    }
    if (!payload.node_id || !payload.name) {
      return send(res, 422, { detail: "node_id and name are required" });
    }
    const now = new Date().toISOString();
    const existing = nodes.get(payload.node_id);
    const row = {
      id: payload.node_id,
      name: payload.name,
      hostname: payload.hostname ?? "",
      role: payload.role ?? "console",
      version: payload.version ?? null,
      capacity: payload.capacity ?? 0,
      meta: payload.meta ?? {},
      first_seen: existing?.first_seen ?? now,
      last_seen: now,
    };
    nodes.set(row.id, row);
    return send(res, 200, nodePayload(row));
  }

  if (url.pathname === "/api/accounts" && req.method === "GET") {
    const state = (url.searchParams.get("state") ?? "").toUpperCase();
    const city = (url.searchParams.get("city") ?? "").toLowerCase();
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const blacklisted = url.searchParams.get("blacklisted");
    const limit = Math.min(Number(url.searchParams.get("limit") ?? 100), 1000);
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const rows = (MODE === "empty" ? [] : accountsFixture).filter((row) => {
      if (state && !state.split(",").includes(row.state)) return false;
      if (city && !row.city.toLowerCase().includes(city)) return false;
      if (blacklisted !== null && String(row.blacklisted) !== blacklisted) return false;
      if (q && !`${row.email} ${row.first_name} ${row.last_name} ${row.city}`.toLowerCase().includes(q)) return false;
      return true;
    });
    return send(res, 200, { items: rows.slice(offset, offset + limit), total: rows.length, limit, offset });
  }

  if (url.pathname.startsWith("/api/accounts/") && req.method === "GET") {
    const id = url.pathname.split("/").pop();
    const row = accountsFixture.find((account) => account.id === id);
    if (!row) return send(res, 404, { detail: "account not found" });
    return send(res, 200, row);
  }

  if (url.pathname === "/api/pool" && req.method === "GET") {
    return send(res, 200, MODE === "empty" ? { emails: {}, proxies: {}, available_emails: 0, available_proxies: 0 } : pool);
  }

  if (url.pathname === "/api/pool/import" && req.method === "POST") {
    const raw = await readBody(req).catch(() => "");
    let payload = {};
    try {
      payload = JSON.parse(raw);
    } catch {
      return send(res, 400, { detail: "invalid JSON" });
    }
    const lines = String(payload.text ?? "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    return send(res, 200, {
      kind: payload.kind ?? "proxies",
      total: lines.length,
      valid: lines.length,
      duplicates: 0,
      invalid: 0,
      errors: [],
      dry_run: Boolean(payload.dry_run),
    });
  }

  if (url.pathname === "/signup" && req.method === "POST") {
    const raw = await readBody(req).catch(() => "");
    let payload = {};
    try {
      payload = JSON.parse(raw);
    } catch {
      return send(res, 400, { detail: "invalid JSON" });
    }
    return send(res, 200, { accepted: payload.count ?? 1, city: payload.city ?? null, dry_run: Boolean(payload.dry_run) });
  }

  if (url.pathname === "/metrics" && req.method === "GET") {
    res.writeHead(200, { "content-type": "text/plain" });
    return res.end("yf_fixture 1\n");
  }

  return send(res, 404, { detail: "not found" });
});

server.listen(PORT, HOST, () => {
  console.log(`[fixture] engine admin API on http://${HOST}:${PORT} mode=${MODE} token=${TOKEN}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
