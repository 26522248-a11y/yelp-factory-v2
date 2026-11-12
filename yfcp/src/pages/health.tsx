import * as React from "react";
import { AreaChart } from "@tremor/react";
import { Activity, Cpu, Database, HardDrive, MonitorSmartphone, RotateCcw, Server, ShieldCheck, Wifi } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel, HealthDot } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/form";
import { cn } from "@/lib/utils";

const history = Array.from({ length: 30 }).map((_, i) => ({
  t: `${i}m`,
  cpu: Math.round(30 + Math.sin(i / 3) * 12 + Math.random() * 6),
  ram: Math.round(50 + Math.cos(i / 4) * 10 + Math.random() * 4),
}));

const services = [
  { name: "PostgreSQL", detail: "127.0.0.1:5433 · pool 5/10", ok: true, latency: "4ms", icon: Database },
  { name: "GPM Login Global", detail: ":9495 · v3.4.1", ok: true, latency: "12ms", icon: MonitorSmartphone },
  { name: "Admin API", detail: "127.0.0.1:8787", ok: true, latency: "2ms", icon: Server },
  { name: "Playwright", detail: "chromium 131.0.6778", ok: true, icon: Activity },
  { name: "Internet", detail: "egress via proxy pool", ok: true, latency: "38ms", icon: Wifi },
  { name: "Captcha solver", detail: "capsolver primary · 2captcha backup", ok: true, latency: "1.2s", icon: ShieldCheck },
];

export default function Health() {
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Health"
        description="Host resources, service probes and the processes the console is supervising. This page is the first stop when something feels off."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => toast.success("Reaper ran")}>
              <RotateCcw /> Run reaper
            </Button>
            <Button variant="destructive" size="sm" onClick={() => toast.error("Emergency stop — all runs killed")}>
              Emergency stop
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="CPU" value="38%" hint="4 vCPU · Xeon Gold 6133" tone="success" icon={<Cpu className="h-4 w-4" />} />
        <StatTile label="RAM" value="61%" hint="2.44 / 4.00 GB" tone="success" />
        <StatTile label="Disk" value="50%" hint="18.5 GB free" tone="success" icon={<HardDrive className="h-4 w-4" />} />
        <StatTile label="Uptime" value="6d 4h" hint="console" tone="info" />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Resource pressure — 30 minutes</CardTitle>
          </CardHeader>
          <CardContent>
            <AreaChart data={history} index="t" categories={["cpu", "ram"]} colors={["emerald", "indigo"]} className="h-52" yAxisWidth={32} showGridLines={false} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Service probes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {services.map((s) => {
              const Icon = s.icon;
              return (
                <div key={s.name} className="flex items-center gap-2">
                  <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[11px]">{s.name}</div>
                    <div className="truncate text-[9.5px] text-muted-foreground">{s.detail}</div>
                  </div>
                  {s.latency && <span className="font-mono text-[10px] text-muted-foreground">{s.latency}</span>}
                  <HealthDot ok={s.ok} />
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Supervised processes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {[
              ["postgres", "PID 4812", "2.1% CPU", "18h"],
              ["yf-worker-1", "PID 9310", "6.2% CPU", "4h"],
              ["yf-worker-2", "PID 9311", "5.8% CPU", "4h"],
              ["yf-admin-api", "PID 1120", "0.4% CPU", "6d"],
              ["gpm-browser-1", "PID 2210", "12.4% CPU", "38m"],
              ["gpm-browser-2", "PID 2211", "11.9% CPU", "22m"],
            ].map(([name, pid, cpu, up]) => (
              <div key={name} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                <span className={cn("h-1.5 w-1.5 rounded-full", name.startsWith("gpm") ? "bg-info" : "bg-success")} />
                <span className="w-32 font-mono text-[10.5px]">{name}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{pid}</span>
                <span className="ml-auto font-mono text-[10px] text-muted-foreground">{cpu}</span>
                <span className="w-10 text-right font-mono text-[10px] text-muted-foreground">{up}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Browser slots</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-md border border-destructive/25 bg-destructive/5 p-2.5">
              <div className="flex items-center justify-between text-[11px]">
                <span>Saturation</span>
                <Badge variant="destructive">2 / 2</Badge>
              </div>
              <Progress value={100} barClassName="bg-destructive" className="mt-2" />
              <div className="mt-1 text-[10px] text-muted-foreground">No new profile can start until a slot frees.</div>
            </div>
            <div className="space-y-1.5">
              {["gpm-1311 · marcus.reed41", "gpm-1312 · nina.patel88"].map((s) => (
                <div key={s} className="flex items-center justify-between rounded-md border border-border/60 px-2 py-1 text-[10.5px]">
                  <span className="font-mono">{s}</span>
                  <Badge variant="info">running</Badge>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <Button size="sm" variant="outline" onClick={() => toast.success("Admin API restarted")}>
                Restart API
              </Button>
              <Button size="sm" variant="outline" onClick={() => toast.success("Workers restarted")}>
                Restart workers
              </Button>
              <Button size="sm" variant="outline" onClick={() => toast.warning("Browsers stopped")}>
                Stop browsers
              </Button>
              <Button size="sm" variant="outline" onClick={() => toast.success("Stale locks cleared")}>
                Clear locks
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
