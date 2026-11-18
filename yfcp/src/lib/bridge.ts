/**
 * Runtime bridge between the console UI and the Tauri shell.
 *
 * Everything degrades to a browser-safe implementation so the same bundle can
 * run in `vite dev` during development and inside the desktop shell in
 * production. Nothing here mutates the engine directly — writes always go
 * through the local admin API (`yf serve`, 127.0.0.1:8787) and are gated by
 * the bearer token from `.env` (`YF_ADMIN_TOKEN`).
 *
 * In the desktop shell HTTP calls are relayed through the Rust command
 * `admin_request` because the engine does not send CORS headers and a
 * `tauri://localhost` origin cannot call 127.0.0.1 directly. In the browser we
 * fall back to plain `fetch` (works when the engine runs with CORS enabled or
 * when the page is served from the same origin).
 */

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export interface AppInfo {
  name: string;
  version: string;
  engine: string;
}

export async function appInfo(): Promise<AppInfo> {
  if (!isTauri) return { name: "YFCP", version: "0.1.0", engine: "yelp-factory-v2" };
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<AppInfo>("app_info");
}

export async function notify(title: string, body: string) {
  if (!isTauri) return false;
  const { isPermissionGranted, requestPermission, sendNotification } = await import("@tauri-apps/plugin-notification");
  let granted = await isPermissionGranted();
  if (!granted) {
    const permission = await requestPermission();
    granted = permission === "granted";
  }
  if (granted) {
    sendNotification({ title, body });
    return true;
  }
  return false;
}

export async function pickFile(filters?: { name: string; extensions: string[] }[]) {
  if (!isTauri) return null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({ multiple: false, directory: false, filters });
  return typeof selected === "string" ? selected : null;
}

export async function openExternal(url: string) {
  if (!isTauri) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

export async function windowAction(action: "minimize" | "maximize" | "close") {
  if (!isTauri) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const w = getCurrentWindow();
  if (action === "minimize") await w.minimize();
  if (action === "maximize") await w.toggleMaximize();
  if (action === "close") await w.close();
}

export async function readSettings<T>(key: string, fallback: T): Promise<T> {
  if (!isTauri) {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  }
  const { load } = await import("@tauri-apps/plugin-store");
  const store = await load("settings.json", { autoSave: false });
  return (await store.get<T>(key)) ?? fallback;
}

export async function writeSettings<T>(key: string, value: T) {
  if (!isTauri) {
    localStorage.setItem(key, JSON.stringify(value));
    return;
  }
  const { load } = await import("@tauri-apps/plugin-store");
  const store = await load("settings.json", { autoSave: true });
  await store.set(key, value);
  await store.save();
}

export async function removeSettings(key: string) {
  if (!isTauri) {
    localStorage.removeItem(key);
    return;
  }
  const { load } = await import("@tauri-apps/plugin-store");
  const store = await load("settings.json", { autoSave: true });
  await store.delete(key);
  await store.save();
}

/* ------------------------------------------------------------------ */
/* Engine admin API                                                    */
/* ------------------------------------------------------------------ */

export interface ApiConfig {
  /** Admin API base URL, no trailing slash. Defaults to 127.0.0.1:8787. */
  baseUrl: string;
  /** Bearer token from YF_ADMIN_TOKEN. Empty string = not configured. */
  token: string;
}

const API_KEY = "yfcp.api";

export function defaultApiConfig(): ApiConfig {
  const env = import.meta.env as Record<string, string | undefined>;
  return {
    baseUrl: env.VITE_YF_ADMIN_URL || "http://127.0.0.1:8787",
    token: env.VITE_YF_ADMIN_TOKEN || "",
  };
}

export function normalizeBaseUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return defaultApiConfig().baseUrl;
  return /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
}

let cachedApi: ApiConfig | null = null;

/** Desktop keeps the token in Windows Credential Manager; the browser dev build uses localStorage. */
async function keychainGet(): Promise<string | null> {
  if (!isTauri) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return (await invoke<string | null>("secret_get")) ?? null;
  } catch {
    return null;
  }
}

async function keychainSet(token: string): Promise<void> {
  if (!isTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  if (token) await invoke("secret_set", { value: token });
  else await invoke("secret_delete");
}

/**
 * Remote engines must be explicitly approved on this machine. Loopback and
 * private/LAN HTTP is allowed; public hosts must use HTTPS. The Rust relay
 * persists the origin and refuses any other host.
 */
async function approveRemoteEndpoint(baseUrl: string): Promise<void> {
  if (!isTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke<string>("remote_endpoint_set", { url: baseUrl });
}

export async function getApiConfig(): Promise<ApiConfig> {
  if (cachedApi) return cachedApi;
  const saved = await readSettings<Partial<ApiConfig>>(API_KEY, {});
  const baseUrl = normalizeBaseUrl(saved.baseUrl || defaultApiConfig().baseUrl);

  if (isTauri) {
    let token = (await keychainGet()) ?? "";
    // Migrate a token written by an older build (plaintext in settings.json).
    if (!token && saved.token) {
      token = saved.token;
      try {
        await keychainSet(token);
        await writeSettings(API_KEY, { baseUrl });
      } catch {
        // Keep the old value so the operator is not locked out; the next save retries.
      }
    }
    // Best effort: approve the saved origin so a restored settings file keeps
    // working on a new machine. Invalid public HTTP stays blocked by the relay.
    void approveRemoteEndpoint(baseUrl).catch(() => undefined);
    cachedApi = { baseUrl, token };
    return cachedApi;
  }

  cachedApi = { baseUrl, token: saved.token ?? defaultApiConfig().token };
  return cachedApi;
}

export async function setApiConfig(config: ApiConfig): Promise<ApiConfig> {
  const next: ApiConfig = { baseUrl: normalizeBaseUrl(config.baseUrl), token: config.token.trim() };
  if (isTauri) {
    // Validate/approve the origin first: this is what unlocks a remote host in
    // the Rust relay. Throws with a clear message for public HTTP.
    await approveRemoteEndpoint(next.baseUrl);
    // URL only in settings.json; token in the OS keychain.
    await writeSettings(API_KEY, { baseUrl: next.baseUrl });
    await keychainSet(next.token);
  } else {
    await writeSettings(API_KEY, next);
  }
  cachedApi = next;
  return next;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Admin API rejected the token (401). Check YF_ADMIN_TOKEN in Workspace settings.";
    if (error.status === 503) return "Admin API is running but no admin token is configured on the engine.";
    if (error.status === 0) {
      // Distinguish a transport failure from an intentional relay refusal
      // (e.g. "host must be loopback") — both arrive with status 0.
      if (/cannot reach|connection failed/i.test(error.message)) {
        return "Engine unreachable — start it with `yf serve` (127.0.0.1:8787).";
      }
      return error.message;
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}

interface RawResponse {
  status: number;
  text: string;
}

const REQUEST_TIMEOUT_MS = 8000;

async function rawRequest(
  config: ApiConfig,
  path: string,
  init: { method?: string; body?: unknown } = {}
): Promise<RawResponse> {
  const url = `${config.baseUrl}${path}`;
  const method = init.method ?? "GET";

  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    try {
      const res = await invoke<{ status: number; body: unknown }>("admin_request", {
        url,
        method,
        token: config.token || null,
        body: init.body ?? null,
      });
      return { status: res.status, text: typeof res.body === "string" ? res.body : JSON.stringify(res.body) };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      // Rust/reqwest transport failures are noisy; normalise them. Validation
      // refusals (loopback/scheme/method) are intentional and passed through.
      if (/error sending request|connection refused|forcibly closed|tcp connect|dns error|os error 100\d\d|timed out/i.test(message)) {
        throw new ApiError(`Cannot reach ${url} (connection failed)`, 0);
      }
      throw new ApiError(message, 0);
    }
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const headers: Record<string, string> = { accept: "application/json" };
    if (config.token) headers.authorization = `Bearer ${config.token}`;
    if (init.body !== undefined) headers["content-type"] = "application/json";
    const res = await fetch(url, {
      method,
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
    });
    return { status: res.status, text: await res.text() };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new ApiError(`Cannot reach ${url} — ${message}`, 0);
  } finally {
    clearTimeout(timer);
  }
}

async function request<T>(config: ApiConfig, path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await rawRequest(config, path, init);
  let parsed: unknown = null;
  if (res.text) {
    try {
      parsed = JSON.parse(res.text);
    } catch {
      parsed = res.text;
    }
  }
  if (res.status < 200 || res.status >= 300) {
    const detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : typeof parsed === "string"
        ? parsed
        : `HTTP ${res.status}`;
    throw new ApiError(detail, res.status);
  }
  return parsed as T;
}

/* ---------------------------------------------------------------- types */

export interface EngineHealth {
  status: string;
  db: boolean;
  active_profiles: number;
  gpm_transport?: string | null;
  version?: string;
  contract_version?: number;
  schema_revision?: string | null;
  host?: string | null;
}

/** Bump together with `CONTRACT_VERSION` in `src/api/admin.py`. */
export const CONTRACT_VERSION = 1;

export interface EngineReport {
  since: string;
  accounts: Record<string, number>;
  runs: Record<string, number>;
  signups_ok: number;
  signups_failed: number;
  quarantine: Record<string, number>;
  queue_depth: number;
}

export interface EngineEvent {
  id: string | number;
  ts: string | null;
  level: string;
  code: string;
  msg: string;
  account_id: string | null;
}

export interface PoolStats {
  emails: Record<string, number>;
  proxies: Record<string, number>;
  available_emails: number;
  available_proxies: number;
}

export interface PoolImportError {
  line: number;
  reason: string;
  row: string;
}

export interface PoolImportResult {
  kind: "emails" | "proxies";
  total: number;
  valid: number;
  duplicates: number;
  invalid: number;
  errors: PoolImportError[];
  dry_run: boolean;
}

export interface SignupRequest {
  count: number;
  city?: string | null;
  dry_run?: boolean;
}

export interface SignupResult {
  accepted: number;
  city: string | null;
  dry_run: boolean;
}

export interface EngineAccount {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  state: string;
  substate: string | null;
  city: string;
  state_code: string;
  zip: string;
  timezone: string;
  trust_score: number;
  trust: Record<string, number>;
  reviews_done: number;
  reviews_posted: number;
  phase: string;
  phase_day: number;
  tier: string;
  blacklisted: boolean;
  gpm_profile_id: string;
  proxy: string;
  proxy_city: string;
  batch_id: string | null;
  mode: string;
  adopted_at: string | null;
  city_changed_at: string | null;
  last_active_at: string | null;
  created_at: string | null;
  profile_complete: number;
  sessions_7d: number;
  photos: number;
  use_count: number;
  supplier: string | null;
  home_city: string | null;
}

export interface EngineAccountsPage {
  items: EngineAccount[];
  total: number;
  limit: number;
  offset: number;
}

export interface AccountQuery {
  state?: string;
  city?: string;
  batchId?: string;
  q?: string;
  blacklisted?: boolean;
  mode?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

export interface EngineNode {
  id: string;
  name: string;
  hostname: string;
  role: "console" | "worker" | "engine";
  version: string | null;
  capacity: number;
  status: string;
  online: boolean;
  age_seconds: number | null;
  meta: Record<string, unknown>;
  progress: { running: number; pending: number; done: number; failed: number };
  slots: number;
  first_seen: string | null;
  last_seen: string | null;
}

export interface EngineNodesPage {
  items: EngineNode[];
  total: number;
  online: number;
  online_window_seconds: number;
}

export interface NodeHeartbeat {
  node_id: string;
  name: string;
  hostname?: string;
  role?: "console" | "worker" | "engine";
  version?: string | null;
  capacity?: number;
  meta?: Record<string, unknown>;
}

/* ------------------------------------------------------------- endpoints */

async function withConfig<T>(fn: (config: ApiConfig) => Promise<T>, requireToken = true): Promise<T> {
  const config = await getApiConfig();
  if (requireToken && !config.token) {
    throw new ApiError("Admin token not configured", 401);
  }
  return fn(config);
}

export const engine = {
  /** `GET /health` — public, no bearer token required. */
  health: (): Promise<EngineHealth> => withConfig((c) => request<EngineHealth>(c, "/health"), false),

  /** `GET /report?since=24h` — account/run/quarantine aggregates. */
  report: (since = "24h"): Promise<EngineReport> =>
    withConfig((c) => request<EngineReport>(c, `/report?since=${encodeURIComponent(since)}`)),

  /** `GET /events?limit=` — structured engine events (logs page). */
  events: (limit = 100, code?: string): Promise<EngineEvent[]> =>
    withConfig((c) =>
      request<EngineEvent[]>(c, `/events?limit=${limit}${code ? `&code=${encodeURIComponent(code)}` : ""}`)
    ),

  /** `GET /api/pool` — pool status counters. */
  pool: (): Promise<PoolStats> => withConfig((c) => request<PoolStats>(c, "/api/pool")),

  /** `POST /api/pool/import` — parse + persist proxy/email pools. */
  importPool: (kind: "emails" | "proxies", text: string, dryRun = false): Promise<PoolImportResult> =>
    withConfig((c) =>
      request<PoolImportResult>(c, "/api/pool/import", {
        method: "POST",
        body: { kind, text, dry_run: dryRun },
      })
    ),

  /** `POST /signup` — records a batch signup intent (workers execute it). */
  signup: (payload: SignupRequest): Promise<SignupResult> =>
    withConfig((c) => request<SignupResult>(c, "/signup", { method: "POST", body: payload })),

  /** `GET /api/accounts` — read-only account listing for the console. */
  accounts: (query: AccountQuery = {}): Promise<EngineAccountsPage> =>
    withConfig((c) => {
      const params = new URLSearchParams();
      if (query.state) params.set("state", query.state);
      if (query.city) params.set("city", query.city);
      if (query.batchId) params.set("batch_id", query.batchId);
      if (query.q) params.set("q", query.q);
      if (query.blacklisted !== undefined) params.set("blacklisted", String(query.blacklisted));
      if (query.mode) params.set("mode", query.mode);
      if (query.sort) params.set("sort", query.sort);
      params.set("limit", String(query.limit ?? 500));
      if (query.offset) params.set("offset", String(query.offset));
      return request<EngineAccountsPage>(c, `/api/accounts?${params.toString()}`);
    }),

  /** `GET /api/accounts/{id}` — one account, same shape as the list rows. */
  account: (id: string): Promise<EngineAccount> =>
    withConfig((c) => request<EngineAccount>(c, `/api/accounts/${encodeURIComponent(id)}`)),

  /** `GET /api/nodes` — machines participating in this deployment. */
  nodes: (): Promise<EngineNodesPage> => withConfig((c) => request<EngineNodesPage>(c, "/api/nodes")),

  /** `POST /api/nodes/heartbeat` — register/update this machine. */
  heartbeat: (payload: NodeHeartbeat): Promise<EngineNode> =>
    withConfig((c) => request<EngineNode>(c, "/api/nodes/heartbeat", { method: "POST", body: payload })),
};
