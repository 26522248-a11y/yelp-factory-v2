import * as React from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  BadgeCheck,
  Clock3,
  Flame,
  Gauge,
  Play,
  ShieldCheck,
  Users,
} from "lucide-react";
import { AreaChart, BarChart, DonutChart } from "@tremor/react";
import { PageHeader, StatTile, HealthDot } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/form";
import { activity7d, alerts, accounts, reviewVelocity, runs, trustHistory } from "@/lib/mock";
import { formatDuration, timeAgo } from "@/lib/utils";

const stateCounts = accounts.reduce<Record<string, number>>((acc, a) => {
  const key = ["ACTIVE", "READY"].includes(a.state)
    ? "Healthy"
    : ["WARMING", "NEW", "PROVISIONING", "FORM_FILLED", "SUBMITTED", "ONBOARDED"].includes(a.state)
    ? "Warming"
    : ["COOLDOWN", "NEEDS_MANUAL", "EMAIL_PENDING", "PHONE_PENDING"].includes(a.state)
    ? "Attention"
    : "Dead / banned";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const donut = Object.entries(stateCounts).map(([name, value]) => ({ name, value }));

export default function Dashboard() {
  const [, setLive] = React.useState(0);
  React.useEffect(() => {
    const t = setInterval(() => setLive((v) => v + 1), 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operations"
        title="Control room"
        description="Everything the factory is doing right now — signups, warming cadence, review throughput and the guardrails around them."
        actions={
          <>
            <Button variant="outline" size="sm">
              <Clock3 /> Schedule review
            </Button>
            <Button size="sm">
              <Play /> Run daily cycle
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile label="Total accounts" value={accounts.length} hint="64 managed" icon={<Users className="h-4 w-4" />} />
        <StatTile label="Active today" value={stateCounts["Healthy"] ?? 0} delta="+4" hint="vs. yesterday" tone="success" icon={<Activity className="h-4 w-4" />} />
        <StatTile label="Reviews this week" value={reviewVelocity.reduce((s, d) => s + d.posted, 0)} hint="7-day posted" tone="info" icon={<BadgeCheck className="h-4 w-4" />} />
        <StatTile label="Avg trust" value={72} hint="gate at 75" tone="warning" icon={<ShieldCheck className="h-4 w-4" />} />
        <StatTile label="Filter rate" value="18%" delta="-3.1%" hint="7-day rolling" tone="success" icon={<Gauge className="h-4 w-4" />} />
        <StatTile label="Browser slots" value="2 / 2" hint="saturated" tone="danger" icon={<Flame className="h-4 w-4" />} />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Factory output — last 7 days</CardTitle>
              <p className="text-[11px] text-muted-foreground">Signups completed, warming sessions, reviews published</p>
            </div>
            <Badge variant="success">live</Badge>
          </CardHeader>
          <CardContent>
            <BarChart
              data={activity7d}
              index="day"
              categories={["signups", "sessions", "reviews"]}
              colors={["indigo", "sky", "emerald"]}
              yAxisWidth={28}
              showLegend
              showGridLines={false}
              className="h-56"
            />
          </CardContent>
        </Card>

        <div className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle>Account health</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center gap-4">
              <DonutChart
                data={donut}
                category="value"
                index="name"
                colors={["emerald", "sky", "amber", "rose"]}
                className="h-36 w-36"
                showLabel={false}
              />
              <div className="flex-1 space-y-2">
                {donut.map((d, i) => (
                  <div key={d.name} className="flex items-center gap-2 text-[11px]">
                    <span className={`h-1.5 w-1.5 rounded-full ${["bg-emerald-500", "bg-sky-500", "bg-amber-500", "bg-rose-500"][i]}`} />
                    <span className="flex-1 text-muted-foreground">{d.name}</span>
                    <span className="font-medium tabular-nums">{d.value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>System status</CardTitle>
              <Link to="/health" className="text-[11px] text-primary hover:underline">
                Health →
              </Link>
            </CardHeader>
            <CardContent className="space-y-2">
              {[
                ["PostgreSQL", "127.0.0.1:5433", true],
                ["GPM Login Global", ":9495 · v3.4.1", true],
                ["Admin API", ":8787", true],
                ["Playwright", "chromium 131", true],
                ["Internet", "egress OK", true],
              ].map(([label, detail, ok]) => (
                <div key={label as string} className="flex items-center justify-between">
                  <div className="text-[11px]">
                    <span className="text-foreground">{label}</span>
                    <span className="ml-2 text-muted-foreground">{detail}</span>
                  </div>
                  <HealthDot ok={ok as boolean} />
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Active runs</CardTitle>
            <Link to="/sessions" className="text-[11px] text-primary hover:underline">
              Sessions →
            </Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {runs.map((run) => (
              <div key={run.id} className="flex items-center gap-3 rounded-md border border-border/60 bg-background/40 px-2.5 py-2">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-info animate-pulse-dot" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px]">{run.accountEmail}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {run.kind} · step {run.stepIndex}/{run.totalSteps} · {run.currentStep}
                  </div>
                </div>
                <div className="hidden w-28 sm:block">
                  <Progress value={(run.stepIndex / run.totalSteps) * 100} />
                </div>
                <Badge variant="info">{formatDuration(Math.round((Date.now() - new Date(run.startedAt).getTime()) / 1000))}</Badge>
              </div>
            ))}
            {runs.length === 0 && <div className="py-6 text-center text-xs text-muted-foreground">No runs in flight.</div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Volume governor</CardTitle>
            <Badge variant="warning">lazy week</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <div className="flex justify-between text-[11px]">
                <span className="text-muted-foreground">Effective multiplier</span>
                <span className="font-mono">0.48×</span>
              </div>
              <Progress value={48} />
              <div className="grid grid-cols-3 gap-2 pt-1 text-[10px] text-muted-foreground">
                <div>
                  lazy <div className="font-mono text-foreground">0.60</div>
                </div>
                <div>
                  filter <div className="font-mono text-foreground">0.80</div>
                </div>
                <div>
                  pin <div className="font-mono text-foreground">1.00</div>
                </div>
              </div>
            </div>
            <div className="rounded-md border border-border/60 bg-background/40 p-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-muted-foreground">Time-of-day</span>
                <span className="font-mono">afternoon</span>
              </div>
              <div className="mt-1.5 flex h-1.5 overflow-hidden rounded-full">
                <span className="w-[30%] bg-info/50" />
                <span className="w-[40%] bg-info" />
                <span className="w-[30%] bg-info/30" />
              </div>
            </div>
            <Link to="/volume" className="flex items-center gap-1 text-[11px] text-primary hover:underline">
              Open controls <ArrowUpRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Trust trajectory</CardTitle>
          </CardHeader>
          <CardContent>
            <AreaChart
              data={trustHistory}
              index="day"
              categories={["avg"]}
              colors={["indigo"]}
              yAxisWidth={32}
              showGridLines={false}
              showLegend={false}
              className="h-44"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent alerts</CardTitle>
            <Link to="/alerts" className="text-[11px] text-primary hover:underline">
              All →
            </Link>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {alerts.slice(0, 5).map((a) => (
              <div key={a.id} className="flex items-start gap-2 rounded-md px-1.5 py-1 hover:bg-accent/40">
                <span
                  className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                    a.severity === "critical" ? "bg-destructive" : a.severity === "warning" ? "bg-warning" : "bg-info"
                  }`}
                />
                <div className="min-w-0">
                  <div className="truncate text-[11px]">{a.message}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {a.type} · {timeAgo(a.ts)}
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
