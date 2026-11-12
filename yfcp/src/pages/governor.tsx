import * as React from "react";
import { AreaChart } from "@tremor/react";
import { Cpu, Gauge, HardDrive, MemoryStick, MonitorCheck, RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress, Switch } from "@/components/ui/form";
import { cn } from "@/lib/utils";

const ramHistory = Array.from({ length: 24 }).map((_, i) => ({
  t: `${String(i).padStart(2, "0")}:00`,
  ram: Math.round(38 + Math.sin(i / 3) * 14 + (i > 16 ? 12 : 0)),
  cpu: Math.round(22 + Math.cos(i / 2.4) * 12),
}));

export default function Governor() {
  const [autoReduce, setAutoReduce] = React.useState(true);
  const [workers, setWorkers] = React.useState(3);
  const [maxProfiles, setMaxProfiles] = React.useState(2);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Governor"
        description="RAM and CPU guardrails. When memory climbs past the guard threshold the governor reduces concurrency before the OS starts swapping."
        actions={
          <Button variant="outline" size="sm" onClick={() => toast.success("Governor state refreshed")}>
            <RefreshCcw /> Refresh
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="RAM used" value="61%" hint="2.44 / 4.00 GB" tone="success" icon={<MemoryStick className="h-4 w-4" />} />
        <StatTile label="CPU" value="38%" hint="4 vCPU" tone="success" icon={<Cpu className="h-4 w-4" />} />
        <StatTile label="Profile cap" value="2" hint="RAM_GB / 2" tone="info" icon={<Gauge className="h-4 w-4" />} />
        <StatTile label="Disk free" value="18.5 GB" hint="min 10 GB" tone="success" icon={<HardDrive className="h-4 w-4" />} />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Resource pressure — 24h</CardTitle>
            <Badge variant="success">governor healthy</Badge>
          </CardHeader>
          <CardContent>
            <AreaChart data={ramHistory} index="t" categories={["ram", "cpu"]} colors={["indigo", "emerald"]} className="h-56" yAxisWidth={32} showGridLines={false} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Concurrency decision</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-md border border-border/60 bg-background/40 p-2.5">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Configured</div>
              <div className="text-lg font-semibold">{workers} workers · {maxProfiles} profiles</div>
              <div className="mt-1 text-[10.5px] text-muted-foreground">Hard cap from RAM: 4 GB / 2 = 2 profiles</div>
            </div>
            <div className="rounded-md border border-border/60 p-2.5">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Governor would allow</div>
              <div className="text-lg font-semibold text-success">{workers} workers</div>
              <div className="text-[10.5px] text-muted-foreground">No reduction needed at 61% RAM</div>
            </div>
            <div className="flex items-center justify-between rounded-md border border-border/60 p-2.5">
              <div>
                <div className="text-[11px]">Auto-reduce on pressure</div>
                <div className="text-[10px] text-muted-foreground">Page out workers past the guard</div>
              </div>
              <Switch checked={autoReduce} onCheckedChange={setAutoReduce} />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Auto-reduction events</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {[
              ["87%", "workers 4 → 2", "12m ago", "warning"],
              ["84%", "workers 3 → 2", "3h ago", "warning"],
              ["86%", "workers 4 → 3", "1d ago", "warning"],
              ["81%", "no change", "2d ago", "success"],
            ].map(([peak, action, when, tone]) => (
              <div key={when as string} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                <span className={cn("h-1.5 w-1.5 rounded-full", tone === "warning" ? "bg-warning" : "bg-success")} />
                <span className="w-12 font-mono">{peak}</span>
                <span className="flex-1">{action}</span>
                <span className="text-[10px] text-muted-foreground">{when}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Limits</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <div className="mb-1 flex justify-between text-[11px]">
                <span className="text-muted-foreground">RAM guard</span>
                <span className="font-mono">85%</span>
              </div>
              <Progress value={85} barClassName="bg-warning" />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[11px]">
                <span className="text-muted-foreground">Current RAM</span>
                <span className="font-mono">61%</span>
              </div>
              <Progress value={61} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button size="sm" variant="outline" onClick={() => { setWorkers((w) => Math.max(1, w - 1)); toast.success("Worker count reduced"); }}>
                −1 worker
              </Button>
              <Button size="sm" variant="outline" onClick={() => { setWorkers((w) => w + 1); toast.success("Worker count increased"); }}>
                +1 worker
              </Button>
            </div>
            <Button size="sm" className="w-full" onClick={() => toast.success("Governor settings saved")}>
              <MonitorCheck /> Save
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
