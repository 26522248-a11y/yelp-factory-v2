import * as React from "react";
import { cn } from "@/lib/utils";
import type { AccountState, AccountMode, Tier } from "@/types";
import { Badge } from "@/components/ui/badge";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 pb-4">
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-primary/80">{eyebrow}</div>
        ) : null}
        <h1 className="text-[19px] font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-0.5 max-w-3xl text-xs text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatTile({
  label,
  value,
  delta,
  hint,
  icon,
  tone = "default",
  className,
}: {
  label: string;
  value: React.ReactNode;
  delta?: string;
  hint?: string;
  icon?: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "info";
  className?: string;
}) {
  const toneClass = {
    default: "text-foreground",
    success: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
    info: "text-info",
  }[tone];

  return (
    <div className={cn("panel relative overflow-hidden px-3.5 py-3", className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</div>
        {icon ? <div className="text-muted-foreground/60">{icon}</div> : null}
      </div>
      <div className={cn("mt-1.5 text-[22px] font-semibold leading-none tabular-nums", toneClass)}>{value}</div>
      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
        {delta ? <span className="text-success">{delta}</span> : null}
        {hint ? <span>{hint}</span> : null}
      </div>
    </div>
  );
}

const STATE_TONE: Record<string, "success" | "warning" | "destructive" | "info" | "muted" | "default"> = {
  ACTIVE: "success",
  READY: "success",
  WARMING: "info",
  COOLDOWN: "warning",
  NEW: "muted",
  PROVISIONING: "info",
  PROXY_BOUND: "info",
  BROWSER_UP: "info",
  PREWARMED: "info",
  FORM_FILLED: "info",
  CAPTCHA_SOLVED: "info",
  SUBMITTED: "info",
  ONBOARDED: "info",
  EMAIL_PENDING: "warning",
  EMAIL_VERIFIED: "success",
  PHONE_PENDING: "warning",
  PHONE_VERIFIED: "success",
  RETIRED: "muted",
  NEEDS_MANUAL: "warning",
  BANNED: "destructive",
  RESTRICTED: "destructive",
  SUSPENDED: "destructive",
  QUARANTINED: "destructive",
  DEAD: "muted",
};

export function AccountStateBadge({ state, substate }: { state: AccountState | string; substate?: string }) {
  const tone = STATE_TONE[state] ?? "default";
  return (
    <Badge variant={tone}>
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          tone === "success" && "bg-success",
          tone === "info" && "bg-info",
          tone === "warning" && "bg-warning",
          tone === "destructive" && "bg-destructive",
          tone === "muted" && "bg-muted",
          tone === "default" && "bg-primary"
        )}
      />
      {substate ?? state}
    </Badge>
  );
}

export function ModeBadge({ mode }: { mode: AccountMode }) {
  const map = {
    post_review: { label: "Post-review", variant: "info" as const, icon: "🔥" },
    full_warm: { label: "Full warm", variant: "default" as const, icon: "🔥" },
    view_only: { label: "View only", variant: "muted" as const, icon: "👁" },
  };
  const m = map[mode];
  return (
    <Badge variant={m.variant}>
      <span>{m.icon}</span>
      {m.label}
    </Badge>
  );
}

export function TierBadge({ tier }: { tier: Tier }) {
  const map = {
    A: "success" as const,
    B: "info" as const,
    C: "warning" as const,
    Loai: "destructive" as const,
  };
  return <Badge variant={map[tier]}>{tier}</Badge>;
}

export function HealthDot({ ok, label }: { ok: boolean; label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <span className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-success animate-pulse-dot" : "bg-destructive")} />
      {label}
    </span>
  );
}

export function EmptyState({ icon, title, description, action }: { icon?: React.ReactNode; title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      {icon ? <div className="text-muted-foreground/50">{icon}</div> : null}
      <div className="text-sm font-medium">{title}</div>
      {description ? <div className="max-w-sm text-xs text-muted-foreground">{description}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function SectionLabel({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{children}</div>
      {right}
    </div>
  );
}

export function Avatar({ name, hue, size = 26 }: { name: string; hue: number; size?: number }) {
  const initials = name
    .split(/[\s.@]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: `linear-gradient(135deg, hsl(${hue} 65% 45%), hsl(${(hue + 40) % 360} 70% 35%))`,
      }}
    >
      {initials}
    </span>
  );
}

export function JsonViewer({ data, className }: { data: unknown; className?: string }) {
  return (
    <pre className={cn("overflow-auto rounded-md border border-border bg-background/70 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground scrollbar-thin", className)}>
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
