export type AccountState =
  | "NEW"
  | "PROVISIONING"
  | "PROXY_BOUND"
  | "BROWSER_UP"
  | "PREWARMED"
  | "FORM_FILLED"
  | "CAPTCHA_SOLVED"
  | "SUBMITTED"
  | "ONBOARDED"
  | "EMAIL_PENDING"
  | "EMAIL_VERIFIED"
  | "PHONE_PENDING"
  | "PHONE_VERIFIED"
  | "ACTIVE"
  | "WARMING"
  | "READY"
  | "COOLDOWN"
  | "RETIRED"
  | "NEEDS_MANUAL"
  | "BANNED"
  | "RESTRICTED"
  | "SUSPENDED"
  | "QUARANTINED"
  | "DEAD";

export type AccountMode = "post_review" | "full_warm" | "view_only";
export type Tier = "A" | "B" | "C" | "Loai";

export interface TrustComponents {
  age: number;
  profile: number;
  consistency: number;
  diversity: number;
  warm: number;
  content: number;
  risk: number;
}

export interface Account {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  state: AccountState;
  substate?: string;
  city: string;
  state_code: string;
  zip: string;
  timezone: string;
  trustScore: number;
  trust: TrustComponents;
  reviewsDone: number;
  phase: "P0" | "P1" | "P2" | "P3" | "P4";
  phaseDay: number;
  tier: Tier;
  blacklisted: boolean;
  gpmProfileId: string;
  proxy: string;
  proxyCity: string;
  batchId?: string;
  mode: AccountMode;
  adoptedAt?: string;
  cityChangedAt?: string;
  cityLockUntil?: string;
  lastActiveAt: string;
  createdAt: string;
  avatarHue: number;
  profileComplete: number;
  sessions7d: number;
  photos: number;
}

export type RunKind = "signup" | "warm" | "post_review_warm" | "review" | "login" | "reauth";
export type RunStatus = "RUNNING" | "DONE" | "FAILED" | "STUCK" | "KILLED";

export interface Run {
  id: string;
  accountId: string;
  accountEmail: string;
  kind: RunKind;
  state: RunStatus;
  currentStep: string;
  stepIndex: number;
  totalSteps: number;
  actionsDone: number;
  startedAt: string;
  workerId: string;
  traceId: string;
  screenshot?: boolean;
}

export interface StepCheckpoint {
  seq: number;
  name: string;
  status: "RUNNING" | "DONE" | "SKIPPED" | "FAILED";
  startedAt?: string;
  endedAt?: string;
  meta?: Record<string, unknown>;
}

export interface Batch {
  id: string;
  name: string;
  status: "planned" | "running" | "paused" | "closed";
  source: "signup" | "adopt" | "import";
  targetCount: number;
  actualCount: number;
  notes: string;
  createdAt: string;
  config: Record<string, unknown>;
}

export interface Client {
  id: string;
  businessName: string;
  metro: string;
  category: string;
  yelpBizId: string;
  address: string;
  reviewsPosted: number;
  avgRating: number;
  facts: {
    menuItems?: string[];
    staffNames?: string[];
    priceRange?: string;
    specialty?: string;
    notableFeatures?: string[];
  };
  createdAt: string;
}

export type AssignmentStatus = "pending" | "assigned" | "posted" | "filtered" | "warranty";

export interface Assignment {
  id: string;
  accountId: string;
  accountEmail: string;
  clientId: string;
  clientName: string;
  status: AssignmentStatus;
  reviewDueAt: string;
  publishedAt?: string;
  filteredAt?: string;
  rating?: number;
  text?: string;
}

export interface Review {
  id: string;
  accountEmail: string;
  businessName: string;
  rating: number;
  status: "posted" | "filtered" | "pending";
  text: string;
  photo: boolean;
  postedAt: string;
  filteredAt?: string;
}

export interface ProxyEntry {
  id: string;
  raw: string;
  host: string;
  port: number;
  kind: "residential" | "datacenter" | "mobile";
  country: string;
  city: string;
  status: "available" | "reserved" | "failed" | "exhausted";
  health: number;
  failStreak: number;
  latencyMs: number;
  asn: string;
  accountsUsing: number;
  importedAt: string;
}

export interface EmailEntry {
  id: string;
  email: string;
  domain: string;
  status: "available" | "reserved" | "suspended";
  provider: "graph" | "fakemailo" | "imap";
  reservedBy?: string;
  importedAt: string;
}

export interface SmsNumber {
  id: string;
  e164: string;
  areaCode: string;
  provider: "hupsms" | "smsactivate";
  usedBy?: string;
  status: "available" | "in_use" | "expired";
}

export interface EmailDomain {
  domain: string;
  enabled: boolean;
  failStreak: number;
  disabledUntil?: string;
}

export type AlertSeverity = "critical" | "warning" | "info";

export interface Alert {
  id: string;
  ts: string;
  severity: AlertSeverity;
  type: string;
  message: string;
  accountEmail?: string;
  status: "unread" | "acknowledged" | "resolved";
  evidence?: Record<string, unknown>;
}

export interface WarmingPlan {
  id: string;
  accountId: string;
  accountEmail: string;
  phase: "P0" | "P1" | "P2" | "P3" | "P4";
  day: number;
  budget: { search: number; pageview: number; scroll: number; save: number; vote: number; follow: number; photo: number };
  status: "pending" | "active" | "done" | "skipped";
}

export interface WarmingTask {
  id: string;
  accountEmail: string;
  kind: string;
  dueAt: string;
  status: "queued" | "running" | "done" | "failed";
}

export interface WarmingSession {
  id: string;
  accountEmail: string;
  mode: "warm" | "post_review";
  startedAt: string;
  durationMin: number;
  actions: number;
  trustBefore: number;
  trustAfter: number;
}

export interface AuditIssue {
  id: string;
  kind: "proxy_asn_missing" | "asn_shared_in_metro" | "trust_below_review";
  metro: string;
  asn: string;
  affected: number;
  severity: "high" | "medium" | "low";
  accounts: string[];
}

export interface SelectorRule {
  key: string;
  strategies: string[];
  priority: number;
  pageTag: string;
  hits: number;
  misses: number;
  active: boolean;
}

export interface SystemFlag {
  key: string;
  value: unknown;
  updatedAt: string;
}

export interface MetricPoint {
  t: string;
  v: number;
}

export interface ServiceStatus {
  name: string;
  ok: boolean;
  detail: string;
  latencyMs?: number;
}

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  kind: "success" | "error" | "warning" | "info";
}
