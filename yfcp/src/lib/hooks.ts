import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiErrorMessage,
  engine,
  getApiConfig,
  type EngineAccount,
  type EngineEvent,
  type EngineReport,
  type PoolStats,
} from "@/lib/bridge";
import * as mock from "@/lib/mock";
import { useImports, type ImportedAccount, type ImportedProxy } from "@/stores/imports";
import { nodeIdentity } from "@/lib/node-identity";
import type { Account, Alert, ProxyEntry } from "@/types";

/** Where the rows on screen came from. */
export type DataSource = "live" | "local" | "pending" | "mock";

export const qk = {
  health: ["engine", "health"] as const,
  config: ["engine", "config"] as const,
  report: (since: string) => ["engine", "report", since] as const,
  events: (limit: number) => ["engine", "events", limit] as const,
  pool: ["engine", "pool"] as const,
  accounts: ["engine", "accounts"] as const,
  nodes: ["engine", "nodes"] as const,
};

const HEALTH_POLL_MS = 15_000;
const DATA_POLL_MS = 30_000;

/**
 * `GET /health` is public (no token) so it doubles as the connection probe.
 * Every other hook stays disabled until this succeeds, which keeps the app
 * quiet when the engine is not running.
 */
export function useApiHealth() {
  return useQuery({
    queryKey: qk.health,
    queryFn: () => engine.health(),
    retry: false,
    refetchInterval: HEALTH_POLL_MS,
    refetchOnWindowFocus: true,
    staleTime: 5_000,
  });
}

export function useApiConfig() {
  return useQuery({ queryKey: qk.config, queryFn: getApiConfig, staleTime: 30_000 });
}

export function useEngineReport(since = "24h", options: { enabled?: boolean } = {}) {
  const health = useApiHealth();
  const query = useQuery({
    queryKey: qk.report(since),
    queryFn: () => engine.report(since),
    enabled: (options.enabled ?? true) && !!health.data,
    retry: false,
    refetchInterval: DATA_POLL_MS,
    staleTime: 10_000,
  });
  return {
    ...query,
    source: (query.data ? "live" : "mock") as DataSource,
    error: query.error ? apiErrorMessage(query.error) : null,
  };
}

export function useEngineEvents(limit = 200, options: { enabled?: boolean } = {}) {
  const health = useApiHealth();
  const query = useQuery({
    queryKey: qk.events(limit),
    queryFn: () => engine.events(limit),
    enabled: (options.enabled ?? true) && !!health.data,
    retry: false,
    refetchInterval: DATA_POLL_MS,
    staleTime: 10_000,
  });
  return {
    ...query,
    source: (query.data ? "live" : "mock") as DataSource,
    error: query.error ? apiErrorMessage(query.error) : null,
  };
}

/** `GET /api/accounts` — the real account inventory. */
export function useEngineAccounts(options: { enabled?: boolean } = {}) {
  const health = useApiHealth();
  const query = useQuery({
    queryKey: qk.accounts,
    queryFn: () => engine.accounts({ limit: 1000, sort: "-created_at" }),
    enabled: (options.enabled ?? true) && !!health.data,
    retry: false,
    refetchInterval: DATA_POLL_MS,
    staleTime: 10_000,
  });
  return {
    ...query,
    source: (query.data ? "live" : "mock") as DataSource,
    error: query.error ? apiErrorMessage(query.error) : null,
  };
}

/** `GET /api/nodes` — machines that have registered with this engine. */
export function useNodes(options: { enabled?: boolean } = {}) {
  const health = useApiHealth();
  const query = useQuery({
    queryKey: qk.nodes,
    queryFn: () => engine.nodes(),
    enabled: (options.enabled ?? true) && !!health.data,
    retry: false,
    refetchInterval: 15_000,
    staleTime: 5_000,
  });
  return {
    ...query,
    source: (query.data ? "live" : "mock") as DataSource,
    error: query.error ? apiErrorMessage(query.error) : null,
  };
}

/**
 * Register this console machine and keep its heartbeat fresh. Mounted once in the
 * shell; failures are ignored (offline/token-missing are shown elsewhere).
 */
export function useNodeHeartbeat() {
  const health = useApiHealth();
  React.useEffect(() => {
    if (!health.data || health.isError) return;
    let cancelled = false;
    const send = async () => {
      try {
        const identity = await nodeIdentity();
        if (!cancelled) await engine.heartbeat(identity);
      } catch {
        // no token / engine restarted — the next tick retries
      }
    };
    void send();
    const timer = window.setInterval(() => void send(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [health.data, health.isError]);
}

/** Mock pool counters, used when the admin API is unreachable. */export function mockPoolStats(): PoolStats {
  const count = (values: string[]) =>
    values.reduce<Record<string, number>>((acc, v) => {
      acc[v] = (acc[v] ?? 0) + 1;
      return acc;
    }, {});
  return {
    emails: count(mock.emails.map((e) => e.status)),
    proxies: count(mock.proxies.map((p) => p.status)),
    available_emails: mock.emails.filter((e) => e.status === "available").length,
    available_proxies: mock.proxies.filter((p) => p.status === "available").length,
  };
}

export function usePoolStats(options: { enabled?: boolean } = {}) {
  const health = useApiHealth();
  const query = useQuery({
    queryKey: qk.pool,
    queryFn: () => engine.pool(),
    enabled: (options.enabled ?? true) && !!health.data,
    retry: false,
    refetchInterval: DATA_POLL_MS,
    staleTime: 10_000,
  });
  return {
    ...query,
    stats: query.data ?? mockPoolStats(),
    source: (query.data ? "live" : "mock") as DataSource,
    error: query.error ? apiErrorMessage(query.error) : null,
  };
}

export function useImportPool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { kind: "emails" | "proxies"; text: string; dryRun?: boolean }) =>
      engine.importPool(vars.kind, vars.text, vars.dryRun ?? false),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.pool });
      qc.invalidateQueries({ queryKey: qk.report("24h") });
    },
  });
}

export function useSignupBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { count: number; city?: string; dryRun?: boolean }) => engine.signup(vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine"] });
    },
  });
}

/* ------------------------------------------------------------------ */
/* Local rows + mock fallback                                          */
/* ------------------------------------------------------------------ */

function titleCase(value: string) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

function importedToAccount(row: ImportedAccount): Account {
  const local = row.email.split("@")[0] ?? "imported";
  const [firstRaw, lastRaw] = local.split(/[._-]/);
  const createdAt = row.importedAt;
  return {
    id: row.id,
    email: row.email,
    firstName: titleCase(firstRaw || "Imported"),
    lastName: titleCase(lastRaw || "Account"),
    state: "NEW",
    substate: row.synced ? "SYNCED" : "IMPORTED",
    city: "—",
    state_code: "",
    zip: "",
    timezone: "America/Chicago",
    trustScore: 0,
    trust: { age: 0, profile: 0, consistency: 0, diversity: 0, warm: 0, content: 0, risk: 0 },
    reviewsDone: 0,
    phase: "P0",
    phaseDay: 0,
    tier: "Loai",
    blacklisted: false,
    gpmProfileId: "—",
    proxy: "—",
    proxyCity: "—",
    mode: "post_review",
    lastActiveAt: createdAt,
    createdAt,
    avatarHue: 205,
    profileComplete: 0,
    sessions7d: 0,
    photos: 0,
  };
}

function importedToProxy(row: ImportedProxy): ProxyEntry {
  return {
    id: row.id,
    raw: row.raw,
    host: row.host,
    port: row.port,
    kind: "residential",
    country: "US",
    city: "Imported",
    status: "available",
    health: 0,
    failStreak: 0,
    latencyMs: 0,
    asn: "—",
    accountsUsing: 0,
    importedAt: row.importedAt,
  };
}

function hueFromId(id: string) {
  let hue = 0;
  for (const char of id) hue = (hue * 31 + char.charCodeAt(0)) % 360;
  return hue;
}

function engineAccountToAccount(row: EngineAccount): Account {
  const trust = row.trust ?? {};
  const tier = ["A", "B", "C", "Loai"].includes(row.tier) ? (row.tier as Account["tier"]) : "Loai";
  const phase = /^P[0-4]$/.test(row.phase) ? (row.phase as Account["phase"]) : "P0";
  const cityChangedAt = row.city_changed_at ?? undefined;
  return {
    id: row.id,
    email: row.email,
    firstName: row.first_name,
    lastName: row.last_name,
    state: row.state as Account["state"],
    substate: row.substate ?? undefined,
    city: row.city,
    state_code: row.state_code,
    zip: row.zip,
    timezone: row.timezone,
    trustScore: row.trust_score,
    trust: {
      age: trust.age ?? 0,
      profile: trust.profile ?? 0,
      consistency: trust.consistency ?? 0,
      diversity: trust.diversity ?? 0,
      warm: trust.warm ?? 0,
      content: trust.content ?? 0,
      risk: trust.risk ?? 0,
    },
    reviewsDone: row.reviews_posted,
    phase,
    phaseDay: row.phase_day,
    tier,
    blacklisted: row.blacklisted,
    gpmProfileId: row.gpm_profile_id || "—",
    proxy: row.proxy || "—",
    proxyCity: row.proxy_city,
    batchId: row.batch_id ?? undefined,
    mode: row.mode === "post_review" ? "post_review" : "full_warm",
    adoptedAt: row.adopted_at ?? undefined,
    cityChangedAt,
    cityLockUntil: cityChangedAt
      ? new Date(new Date(cityChangedAt).getTime() + 48 * 3600_000).toISOString()
      : undefined,
    lastActiveAt: row.last_active_at ?? row.created_at ?? new Date().toISOString(),
    createdAt: row.created_at ?? new Date().toISOString(),
    avatarHue: hueFromId(row.id),
    profileComplete: row.profile_complete,
    sessions7d: row.sessions_7d,
    photos: row.photos,
  };
}

export function useAccountsData() {
  const imported = useImports((s) => s.accounts);
  const live = useEngineAccounts();
  const liveAccounts = React.useMemo(
    () => live.data?.items.map(engineAccountToAccount),
    [live.data]
  );
  const data = React.useMemo(
    () => [...imported.map(importedToAccount), ...(liveAccounts ?? mock.accounts)],
    [imported, liveAccounts]
  );
  const source: DataSource = liveAccounts ? "live" : imported.length ? "local" : "mock";
  return {
    data,
    imported,
    source,
    total: live.data?.total ?? data.length,
    error: live.error,
  };
}

export function useProxiesData() {
  const imported = useImports((s) => s.proxies);
  const data = React.useMemo(
    () => [...imported.map(importedToProxy), ...mock.proxies],
    [imported]
  );
  return {
    data,
    imported,
    source: (imported.length ? "local" : "mock") as DataSource,
  };
}

/** Account-state counts from the live report, or the deterministic mock. */
export function useAccountStateCounts() {
  const report = useEngineReport("24h");
  const counts = React.useMemo(() => {
    if (report.data) return report.data.accounts;
    return mock.accounts.reduce<Record<string, number>>((acc, a) => {
      acc[a.state] = (acc[a.state] ?? 0) + 1;
      return acc;
    }, {});
  }, [report.data]);

  const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
  return { counts, total, report: report.data as EngineReport | undefined, source: report.source, error: report.error };
}

/** Map engine events into the shape the logs page renders. */
export interface LogLine {
  id: string;
  ts: string;
  level: "INFO" | "WARN" | "ERROR" | "DEBUG";
  account: string;
  msg: string;
}

const LEVELS: LogLine["level"][] = ["INFO", "WARN", "ERROR", "DEBUG"];

export function eventToLine(event: EngineEvent): LogLine {
  const level = LEVELS.includes(event.level as LogLine["level"])
    ? (event.level as LogLine["level"])
    : "INFO";
  return {
    id: String(event.id),
    ts: event.ts ?? new Date().toISOString(),
    level,
    account: event.account_id ?? event.code ?? "engine",
    msg: event.msg,
  };
}

/* ------------------------------------------------------------------ */
/* Domain hooks for resources the engine does not expose yet           */
/*                                                                     */
/* The admin API currently only serves accounts-in-aggregate, runs in  */
/* aggregate, events, pool counters and signup. These hooks give the   */
/* remaining screens one seam to grow into: today they return the      */
/* deterministic sample dataset, tomorrow only the queryFn changes.    */
/* ------------------------------------------------------------------ */

const SAMPLE: DataSource = "mock";

/**
 * Sample rows for a resource the engine does not expose yet. When the engine
 * is reachable we label them `pending` ("endpoint not wired") instead of
 * pretending they are live or that the engine is down.
 */
export function useSampleSource(): DataSource {
  const health = useApiHealth();
  return health.data && !health.isError ? "pending" : SAMPLE;
}

export function useClientsData() {
  const source = useSampleSource();
  return { data: mock.clients, source };
}

export function useAssignmentsData() {
  const source = useSampleSource();
  return { data: mock.assignments, source };
}

export function useReviewsData() {
  const source = useSampleSource();
  return { data: mock.reviews, source };
}

export function useBatchesData() {
  const source = useSampleSource();
  return { data: mock.batches, source };
}

export function useRunsData() {
  const source = useSampleSource();
  return { data: mock.runs, source };
}

export function useWarmingPlansData() {
  const source = useSampleSource();
  return { data: mock.warmingPlans, source };
}

export function useWarmingTasksData() {
  const source = useSampleSource();
  return { data: mock.warmingTasks, source };
}

export function useWarmingSessionsData() {
  const source = useSampleSource();
  return { data: mock.warmingSessions, source };
}

export function useAuditIssuesData() {
  const source = useSampleSource();
  return { data: mock.auditIssues, source };
}

export function useSelectorsData() {
  const source = useSampleSource();
  return { data: mock.selectors, source };
}

export function useSystemFlagsData() {
  const source = useSampleSource();
  return { data: mock.systemFlags, source };
}

export function useSmsNumbersData() {
  const source = useSampleSource();
  return { data: mock.smsNumbers, source };
}

export function useEmailsData() {
  const source = useSampleSource();
  return { data: mock.emails, source };
}

export function useEmailDomainsData() {
  const source = useSampleSource();
  return { data: mock.emailDomains, source };
}

export function useReviewVelocityData() {
  const source = useSampleSource();
  return { data: mock.reviewVelocity, source };
}

export function useTrustHistoryData() {
  const source = useSampleSource();
  return { data: mock.trustHistory, source };
}

export function useActivity7dData() {
  const source = useSampleSource();
  return { data: mock.activity7d, source };
}

/** Turn engine events into alerts so the Alerts page works against the API. */
export function useAlertsData() {
  const events = useEngineEvents(200);
  const derived = React.useMemo<Alert[] | null>(() => {
    if (!events.data || events.data.length === 0) return null;
    return events.data
      .filter((event) => event.level === "WARN" || event.level === "ERROR" || event.level === "CRITICAL")
      .map((event) => ({
        id: `ev_${event.id}`,
        ts: event.ts ?? new Date().toISOString(),
        severity: event.level === "ERROR" || event.level === "CRITICAL" ? "critical" : "warning",
        type: event.code,
        message: event.msg,
        accountEmail: event.account_id ?? undefined,
        status: "unread" as const,
        evidence: { source: "engine event" },
      }));
  }, [events.data]);

  return {
    data: derived ?? mock.alerts,
    source: (derived ? "live" : "mock") as DataSource,
    error: events.error,
  };
}
