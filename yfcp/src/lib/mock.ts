import type {
  Account,
  AccountState,
  Alert,
  Assignment,
  AuditIssue,
  Batch,
  Client,
  EmailDomain,
  EmailEntry,
  ProxyEntry,
  Review,
  Run,
  SelectorRule,
  SmsNumber,
  SystemFlag,
  WarmingPlan,
  WarmingSession,
  WarmingTask,
} from "@/types";

/* ------------------------------------------------------------------ */
/* Deterministic PRNG so the demo data is stable between reloads      */
/* ------------------------------------------------------------------ */
let seed = 1337;
function rnd() {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
}
function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(rnd() * arr.length)];
}
function int(min: number, max: number) {
  return Math.floor(rnd() * (max - min + 1)) + min;
}
function hoursAgo(h: number) {
  return new Date(Date.now() - h * 3600_000).toISOString();
}
function daysAgo(d: number) {
  return new Date(Date.now() - d * 86_400_000).toISOString();
}

const CITIES = [
  ["Austin", "TX", "America/Chicago"],
  ["Dallas", "TX", "America/Chicago"],
  ["Houston", "TX", "America/Chicago"],
  ["Phoenix", "AZ", "America/Phoenix"],
  ["Denver", "CO", "America/Denver"],
  ["Seattle", "WA", "America/Los_Angeles"],
  ["Portland", "OR", "America/Los_Angeles"],
  ["San Diego", "CA", "America/Los_Angeles"],
  ["Atlanta", "GA", "America/New_York"],
  ["Miami", "FL", "America/New_York"],
  ["Charlotte", "NC", "America/New_York"],
  ["Nashville", "TN", "America/Chicago"],
] as const;

const FIRST = ["Amelia", "Noah", "Priya", "Marcus", "Sofia", "Ethan", "Layla", "Daniel", "Grace", "Owen", "Maya", "Lucas", "Chloe", "Ryan", "Nina", "Jonah"];
const LAST = ["Hart", "Kim", "Alvarez", "Brooks", "Nguyen", "Reed", "Patel", "Doyle", "Okafor", "Silva", "Moreau", "Bennett", "Rossi", "Chen", "Novak", "Fischer"];

const LIVE_STATES: AccountState[] = ["ACTIVE", "WARMING", "READY", "COOLDOWN"];
const BAD_STATES: AccountState[] = ["BANNED", "RESTRICTED", "SUSPENDED", "DEAD", "NEEDS_MANUAL", "QUARANTINED"];

function trustComponents(score: number) {
  const scale = score / 100;
  return {
    age: Math.round(15 * Math.min(1, scale * 1.15)),
    profile: Math.round(15 * Math.min(1, scale * 1.2)),
    consistency: Math.round(12 * Math.min(1, scale * 1.05)),
    diversity: Math.round(18 * Math.min(1, scale * 0.95)),
    warm: Math.round(30 * Math.min(1, scale * 1.1)),
    content: Math.round(20 * Math.min(1, scale * 1.05)),
    risk: -Math.round(6 * (1 - scale)),
  };
}

export const batches: Batch[] = [
  { id: "bat_001", name: "Spring Austin Ramp", status: "running", source: "signup", targetCount: 40, actualCount: 32, notes: "Q2 push — 2 weeks warm before first review.", createdAt: daysAgo(21), config: { phaseDays: [2, 3, 5, 10, 10], metro: "Austin, TX" } },
  { id: "bat_002", name: "Adopted Phoenix Set", status: "running", source: "adopt", targetCount: 24, actualCount: 24, notes: "Supplier batch — verify fingerprints before P1.", createdAt: daysAgo(14), config: { mode: "post_review", metro: "Phoenix, AZ" } },
  { id: "bat_003", name: "Dallas Seeding", status: "paused", source: "signup", targetCount: 30, actualCount: 18, notes: "Paused: email domain fail streak high.", createdAt: daysAgo(18), config: { phaseDays: [2, 3, 5, 10, 10], metro: "Dallas, TX" } },
  { id: "bat_004", name: "Denver Test Ring", status: "closed", source: "signup", targetCount: 12, actualCount: 11, notes: "Pilot. 9 survived, 2 banned post-review.", createdAt: daysAgo(60), config: { metro: "Denver, CO" } },
  { id: "bat_005", name: "Miami Replenish", status: "planned", source: "adopt", targetCount: 20, actualCount: 0, notes: "Awaiting proxy pool import.", createdAt: daysAgo(2), config: { mode: "post_review", metro: "Miami, FL" } },
  { id: "bat_006", name: "Seattle Organic", status: "running", source: "signup", targetCount: 16, actualCount: 14, notes: "Slower cadence, 1 session/day.", createdAt: daysAgo(9), config: { phaseDays: [3, 4, 6, 10, 10], metro: "Seattle, WA" } },
];

export const accounts: Account[] = Array.from({ length: 64 }).map((_, i) => {
  const [city, sc, tz] = CITIES[i % CITIES.length];
  const roll = rnd();
  const state: AccountState =
    roll > 0.86 ? pick(BAD_STATES) : roll > 0.55 ? pick(LIVE_STATES) : roll > 0.4 ? "READY" : "WARMING";
  const trust = state === "BANNED" ? int(10, 35) : int(28, 97);
  const first = FIRST[i % FIRST.length];
  const last = LAST[(i * 7) % LAST.length];
  const phaseDay = int(1, 10);
  const mode = i % 5 === 0 ? "full_warm" : i % 11 === 0 ? "view_only" : "post_review";
  const cityChanged = i % 17 === 0 ? hoursAgo(int(2, 30)) : undefined;
  return {
    id: `acc_${String(i + 1).padStart(4, "0")}`,
    email: `${first.toLowerCase()}.${last.toLowerCase()}${int(10, 99)}@outlook.com`,
    firstName: first,
    lastName: last,
    state,
    substate: roll <= 0.4 ? pick(["FORM_FILLED", "CAPTCHA_SOLVED", "EMAIL_PENDING"]) : undefined,
    city,
    state_code: sc,
    zip: String(int(10000, 99999)),
    timezone: tz,
    trustScore: trust,
    trust: trustComponents(trust),
    reviewsDone: state === "ACTIVE" || state === "READY" ? int(0, 9) : 0,
    phase: (["P0", "P1", "P2", "P3", "P4"] as const)[Math.min(4, Math.floor(phaseDay / 2))],
    phaseDay,
    tier: trust > 85 ? "A" : trust > 65 ? "B" : trust > 40 ? "C" : "Loai",
    blacklisted: i % 23 === 0,
    gpmProfileId: `gpm-${String(1000 + i)}`,
    proxy: `res.proxy-${int(10, 99)}.net:8${int(100, 999)}`,
    proxyCity: city,
    batchId: batches[i % batches.length].id,
    mode,
    adoptedAt: i % 3 === 0 ? daysAgo(int(3, 40)) : undefined,
    cityChangedAt: cityChanged,
    cityLockUntil: cityChanged ? new Date(new Date(cityChanged).getTime() + 48 * 3600_000).toISOString() : undefined,
    lastActiveAt: hoursAgo(int(0, 96)),
    createdAt: daysAgo(int(2, 70)),
    avatarHue: (i * 47) % 360,
    profileComplete: int(45, 100),
    sessions7d: int(0, 9),
    photos: int(0, 14),
  };
});

export const runs: Run[] = accounts
  .filter((a) => ["WARMING", "ACTIVE", "READY", "NEW", "FORM_FILLED"].includes(a.state))
  .slice(0, 4)
  .map((a, i) => ({
    id: `run_${9001 + i}`,
    accountId: a.id,
    accountEmail: a.email,
    kind: i === 0 ? "signup" : "post_review_warm",
    state: "RUNNING",
    currentStep: i === 0 ? "CAPTCHA_SOLVED" : ["search", "pageview", "scroll", "vote"][i % 4],
    stepIndex: int(3, 9),
    totalSteps: i === 0 ? 14 : 10,
    actionsDone: int(2, 26),
    startedAt: hoursAgo(int(0, 1)),
    workerId: `worker-${i + 1}`,
    traceId: `tr_${Math.random().toString(16).slice(2, 10)}`,
    screenshot: i % 2 === 0,
  }));

export const clients: Client[] = [
  ["Bluebonnet Grill", "Austin, TX", "Restaurants", "bluebonnet-grill-austin"],
  ["Copper Kettle BBQ", "Austin, TX", "Restaurants", "copper-kettle-bbq"],
  ["Saguaro Auto Care", "Phoenix, AZ", "Automotive", "saguaro-auto-care"],
  ["Mile High Cuts", "Denver, CO", "Beauty & Spas", "mile-high-cuts"],
  ["Rain City Noodles", "Seattle, WA", "Restaurants", "rain-city-noodles"],
  ["Palm & Pine Spa", "Miami, FL", "Beauty & Spas", "palm-pine-spa"],
  ["Trinity Dental", "Dallas, TX", "Health & Medical", "trinity-dental"],
  ["Queen City Movers", "Charlotte, NC", "Home Services", "queen-city-movers"],
  ["Music Row Tacos", "Nashville, TN", "Restaurants", "music-row-tacos"],
  ["Pacific Smile Ortho", "San Diego, CA", "Health & Medical", "pacific-smile-ortho"],
  ["Peachtree Detailing", "Atlanta, GA", "Automotive", "peachtree-detailing"],
  ["Willamette Barkery", "Portland, OR", "Pets", "willamette-barkery"],
].map(([businessName, metro, category, yelpBizId], i) => ({
  id: `cli_${String(i + 1).padStart(3, "0")}`,
  businessName,
  metro,
  category,
  yelpBizId,
  address: `${int(100, 9999)} ${pick(["Main St", "Oak Ave", "5th Blvd", "Cedar Ln", "Market St"])}`,
  reviewsPosted: int(1, 24),
  avgRating: Number((3.9 + rnd() * 1.1).toFixed(1)),
  facts: {
    menuItems: ["brisket plate", "green chile stew", "house pickles"],
    staffNames: [pick(FIRST), pick(FIRST)],
    priceRange: pick(["$$", "$$$"]),
    specialty: pick(["wood-fired", "family-owned", "24/7 drop-off", "walk-ins welcome"]),
    notableFeatures: ["patio seating", "free parking", "late hours"],
  },
  createdAt: daysAgo(int(5, 80)),
}));

export const assignments: Assignment[] = Array.from({ length: 22 }).map((_, i) => {
  const client = clients[i % clients.length];
  const account = accounts[(i * 3) % accounts.length];
  const status = (["pending", "assigned", "posted", "filtered", "warranty"] as const)[i % 5];
  return {
    id: `asg_${String(i + 1).padStart(3, "0")}`,
    accountId: account.id,
    accountEmail: account.email,
    clientId: client.id,
    clientName: client.businessName,
    status,
    reviewDueAt: new Date(Date.now() + int(-20, 60) * 3600_000).toISOString(),
    publishedAt: status === "posted" || status === "filtered" ? daysAgo(int(1, 12)) : undefined,
    filteredAt: status === "filtered" ? daysAgo(int(0, 9)) : undefined,
    rating: status === "posted" || status === "filtered" ? (rnd() > 0.3 ? 5 : 4) : undefined,
    text:
      status !== "pending"
        ? "Stopped in on a Tuesday around 6pm and the place was busy but not packed. The brisket had a proper bark, and the green chile stew was the sleeper hit. Only knock: parking lot is tight."
        : undefined,
  };
});

export const reviews: Review[] = assignments
  .filter((a) => a.status === "posted" || a.status === "filtered")
  .map((a, i) => ({
    id: `rev_${String(i + 1).padStart(3, "0")}`,
    accountEmail: a.accountEmail,
    businessName: a.clientName,
    rating: a.rating ?? 5,
    status: a.status === "filtered" ? "filtered" : "posted",
    text: a.text ?? "",
    photo: true,
    postedAt: a.publishedAt ?? daysAgo(3),
    filteredAt: a.filteredAt,
  }));

export const proxies: ProxyEntry[] = Array.from({ length: 86 }).map((_, i) => {
  const [city, ,] = CITIES[i % CITIES.length];
  const status = (["available", "available", "available", "reserved", "failed", "exhausted"] as const)[Math.floor(rnd() * 6)];
  return {
    id: `prx_${String(i + 1).padStart(3, "0")}`,
    raw: `res.proxy-${int(10, 99)}.net:8${int(100, 999)}:u${int(1000, 9999)}:p${int(10000, 99999)}`,
    host: `res.proxy-${int(10, 99)}.net`,
    port: int(8000, 8999),
    kind: rnd() > 0.2 ? "residential" : rnd() > 0.5 ? "mobile" : "datacenter",
    country: "US",
    city,
    status,
    health: status === "failed" ? int(0, 30) : int(70, 100),
    failStreak: status === "failed" ? int(3, 9) : int(0, 2),
    latencyMs: int(48, 420),
    asn: `AS${int(20000, 65000)}`,
    accountsUsing: status === "reserved" ? 1 : 0,
    importedAt: daysAgo(int(1, 45)),
  };
});

export const emails: EmailEntry[] = Array.from({ length: 72 }).map((_, i) => {
  const status = (["available", "available", "reserved", "suspended"] as const)[Math.floor(rnd() * 4)];
  return {
    id: `eml_${String(i + 1).padStart(3, "0")}`,
    email: `${FIRST[i % FIRST.length].toLowerCase()}${int(100, 999)}@${pick(["outlook.com", "hotmail.com", "live.com"])}`,
    domain: pick(["outlook.com", "hotmail.com", "live.com"]),
    status,
    provider: rnd() > 0.3 ? "graph" : "fakemailo",
    reservedBy: status === "reserved" ? accounts[i % accounts.length].email : undefined,
    importedAt: daysAgo(int(1, 30)),
  };
});

export const smsNumbers: SmsNumber[] = Array.from({ length: 18 }).map((_, i) => ({
  id: `sms_${String(i + 1).padStart(3, "0")}`,
  e164: `+1${int(200, 989)}${int(1000, 9999)}`,
  areaCode: String(int(200, 989)),
  provider: i % 2 === 0 ? "smsactivate" : "hupsms",
  usedBy: i % 3 === 0 ? accounts[i].email : undefined,
  status: i % 3 === 0 ? "in_use" : i % 7 === 0 ? "expired" : "available",
}));

export const emailDomains: EmailDomain[] = [
  { domain: "outlook.com", enabled: true, failStreak: 0 },
  { domain: "hotmail.com", enabled: true, failStreak: 2 },
  { domain: "live.com", enabled: true, failStreak: 1 },
  { domain: "msn.com", enabled: false, failStreak: 6, disabledUntil: new Date(Date.now() + 36 * 3600_000).toISOString() },
];

export const alerts: Alert[] = Array.from({ length: 26 }).map((_, i) => {
  const severity = (["critical", "warning", "info"] as const)[i % 3 === 0 ? 0 : i % 3 === 1 ? 1 : 2];
  const type = pick([
    "account.banned",
    "review.filtered",
    "proxy.failed",
    "captcha.timeout",
    "ram.guard",
    "email.suspended",
    "selector.miss_rate",
  ]);
  return {
    id: `alr_${String(i + 1).padStart(3, "0")}`,
    ts: hoursAgo(int(0, 72)),
    severity,
    type,
    message:
      type === "account.banned"
        ? `Account ${accounts[i % accounts.length].email} hit a DataDome challenge and was flagged.`
        : type === "review.filtered"
        ? `Review for ${clients[i % clients.length].businessName} was filtered after 48h.`
        : type === "proxy.failed"
        ? `Proxy res.proxy-${int(10, 99)}.net failed 3 probes in a row; rotated out.`
        : type === "captcha.timeout"
        ? `Capsolver timed out after 120s on signup step CAPTCHA_SOLVED.`
        : type === "ram.guard"
        ? `RAM usage reached 87% — governor reduced workers from 4 to 2.`
        : type === "email.suspended"
        ? `Mailbox ${emails[i % emails.length].email} returned AADSTS50126; moved to suspended.`
        : `Selector 'login.submit_button' missed ${int(20, 60)} times in the last hour.`,
    accountEmail: accounts[i % accounts.length].email,
    status: (["unread", "unread", "acknowledged", "resolved"] as const)[i % 4],
    evidence: { trace: `tr_${Math.random().toString(16).slice(2, 10)}`, attempt: int(1, 3) },
  };
});

export const warmingPlans: WarmingPlan[] = accounts.slice(0, 28).map((a, i) => ({
  id: `pln_${String(i + 1).padStart(3, "0")}`,
  accountId: a.id,
  accountEmail: a.email,
  phase: a.phase,
  day: a.phaseDay,
  budget: { search: int(2, 5), pageview: int(3, 8), scroll: int(4, 10), save: int(0, 2), vote: int(0, 3), follow: int(0, 2), photo: int(0, 2) },
  status: (["pending", "active", "done", "skipped"] as const)[i % 4],
}));

export const warmingTasks: WarmingTask[] = Array.from({ length: 16 }).map((_, i) => ({
  id: `tsk_${String(i + 1).padStart(3, "0")}`,
  accountEmail: accounts[i % accounts.length].email,
  kind: pick(["search", "pageview", "scroll", "vote", "save", "follow", "photo"]),
  dueAt: new Date(Date.now() + int(-90, 360) * 60_000).toISOString(),
  status: (["queued", "queued", "running", "done", "failed"] as const)[i % 5],
}));

export const warmingSessions: WarmingSession[] = Array.from({ length: 30 }).map((_, i) => ({
  id: `wss_${String(i + 1).padStart(3, "0")}`,
  accountEmail: accounts[i % accounts.length].email,
  mode: i % 4 === 0 ? "post_review" : "warm",
  startedAt: daysAgo(int(0, 14)),
  durationMin: int(4, 88),
  actions: int(6, 34),
  trustBefore: int(10, 70),
  trustAfter: int(20, 95),
}));

export const auditIssues: AuditIssue[] = [
  { id: "aud_1", kind: "asn_shared_in_metro", metro: "Austin, TX", asn: "AS22773", affected: 7, severity: "high", accounts: accounts.slice(0, 7).map((a) => a.email) },
  { id: "aud_2", kind: "proxy_asn_missing", metro: "Miami, FL", asn: "—", affected: 4, severity: "medium", accounts: accounts.slice(4, 8).map((a) => a.email) },
  { id: "aud_3", kind: "trust_below_review", metro: "Dallas, TX", asn: "AS7018", affected: 9, severity: "medium", accounts: accounts.slice(8, 17).map((a) => a.email) },
  { id: "aud_4", kind: "asn_shared_in_metro", metro: "Phoenix, AZ", asn: "AS20057", affected: 3, severity: "low", accounts: accounts.slice(17, 20).map((a) => a.email) },
];

export const selectors: SelectorRule[] = [
  { key: "signup.email_input", strategies: ["css#email", "label:Email", "placeholder"], priority: 1, pageTag: "signup", hits: 941, misses: 2, active: true },
  { key: "signup.submit", strategies: ["cssbutton[type=submit]", "text:Sign up"], priority: 1, pageTag: "signup", hits: 908, misses: 5, active: true },
  { key: "login.password_input", strategies: ["css#password", "label:Password"], priority: 1, pageTag: "login", hits: 1874, misses: 1, active: true },
  { key: "login.submit_button", strategies: ["cssbutton[type=submit]", "text:Log In"], priority: 1, pageTag: "login", hits: 1790, misses: 44, active: true },
  { key: "warm.search_box", strategies: ["css#search_description", "placeholder:Search"], priority: 2, pageTag: "warm", hits: 2210, misses: 12, active: true },
  { key: "review.star_5", strategies: ["aria-label:5 star rating"], priority: 1, pageTag: "review", hits: 143, misses: 0, active: true },
  { key: "review.text_area", strategies: ["css#textarea", "role:textbox"], priority: 1, pageTag: "review", hits: 140, misses: 3, active: true },
  { key: "captcha.frame", strategies: ["cssiframe[src*=recaptcha]"], priority: 3, pageTag: "captcha", hits: 88, misses: 21, active: true },
  { key: "onboarding.avatar_upload", strategies: ["cssinput[type=file]"], priority: 2, pageTag: "onboarding", hits: 61, misses: 9, active: true },
  { key: "cookie.accept", strategies: ["text:Accept", "css#onetrust-accept-btn-handler"], priority: 1, pageTag: "global", hits: 3120, misses: 7, active: true },
];

export const systemFlags: SystemFlag[] = [
  { key: "volume", value: { multiplier: 0.8, paused: false }, updatedAt: hoursAgo(5) },
  { key: "trust_recompute", value: { requested: false, last_run: hoursAgo(26) }, updatedAt: hoursAgo(26) },
  { key: "filter_alert", value: { threshold: 0.35, window_days: 7 }, updatedAt: daysAgo(3) },
  { key: "proxy_fail_count", value: { austin_residential: 3 }, updatedAt: hoursAgo(9) },
];

export const reviewVelocity = Array.from({ length: 14 }).map((_, i) => ({
  day: new Date(Date.now() - (13 - i) * 86_400_000).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  posted: int(0, 9),
  filtered: int(0, 3),
}));

export const trustHistory = Array.from({ length: 21 }).map((_, i) => ({
  day: new Date(Date.now() - (20 - i) * 86_400_000).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  avg: Math.round(38 + i * 2.2 + Math.sin(i) * 4),
}));

export const activity7d = Array.from({ length: 7 }).map((_, i) => ({
  day: new Date(Date.now() - (6 - i) * 86_400_000).toLocaleDateString("en-US", { weekday: "short" }),
  signups: int(0, 6),
  sessions: int(8, 26),
  reviews: int(0, 8),
}));
