import {
  Activity,
  BadgeCheck,
  ChartNoAxesCombined,
  Database,
  Download,
  Fingerprint,
  Flag,
  Gauge,
  Inbox,
  KeyRound,
  Layers,
  LifeBuoy,
  MonitorCog,
  Radar,
  RefreshCcw,
  ScrollText,
  Settings2,
  ShieldCheck,
  Store,
  Table2,
  Target,
  Trash2,
  UserPlus,
  Users,
  Waypoints,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
  badge?: string;
  group: "Operate" | "Monitor" | "System";
  hint?: string;
}

export const NAV: NavItem[] = [
  { label: "Dashboard", path: "/", icon: Gauge, group: "Operate", hint: "Live overview" },
  { label: "Accounts", path: "/accounts", icon: Users, group: "Operate", hint: "All managed identities" },
  { label: "Adopt", path: "/adopt", icon: UserPlus, group: "Operate", hint: "Bring an existing account in" },
  { label: "Batches", path: "/batches", icon: Layers, group: "Operate" },
  { label: "Sessions", path: "/sessions", icon: Activity, group: "Operate", hint: "Live & past runs" },
  { label: "Login / Reauth", path: "/login", icon: KeyRound, group: "Operate" },
  { label: "Warming", path: "/warming", icon: RefreshCcw, group: "Operate" },
  { label: "Reviews", path: "/reviews", icon: BadgeCheck, group: "Operate" },
  { label: "Clients", path: "/clients", icon: Store, group: "Operate" },
  { label: "Pools", path: "/pools", icon: Database, group: "Operate" },

  { label: "Trust", path: "/trust", icon: ShieldCheck, group: "Monitor" },
  { label: "Velocity", path: "/velocity", icon: Zap, group: "Monitor" },
  { label: "Audit", path: "/audit", icon: Radar, group: "Monitor" },
  { label: "Volume", path: "/volume", icon: ChartNoAxesCombined, group: "Monitor" },
  { label: "Reports", path: "/reports", icon: Table2, group: "Monitor" },
  { label: "Alerts", path: "/alerts", icon: Inbox, group: "Monitor", badge: "12" },

  { label: "Reaper", path: "/reaper", icon: Trash2, group: "System" },
  { label: "Lifecycle", path: "/lifecycle", icon: Waypoints, group: "System" },
  { label: "Fingerprints", path: "/fingerprints", icon: Fingerprint, group: "System" },
  { label: "Governor", path: "/governor", icon: MonitorCog, group: "System" },
  { label: "System flags", path: "/flags", icon: Flag, group: "System" },
  { label: "Selectors", path: "/selectors", icon: Target, group: "System" },
  { label: "Logs", path: "/logs", icon: ScrollText, group: "System" },
  { label: "Health", path: "/health", icon: LifeBuoy, group: "System" },
  { label: "Data", path: "/data", icon: Download, group: "System" },
  { label: "Config", path: "/config", icon: Settings2, group: "System" },
];

export const NAV_GROUPS = ["Operate", "Monitor", "System"] as const;
