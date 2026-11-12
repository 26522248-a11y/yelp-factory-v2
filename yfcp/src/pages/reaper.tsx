import * as React from "react";
import { AlertTriangle, CheckCircle2, Clock3, HardDrive, Play, ScanEye, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel, EmptyState } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Progress, Switch } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

const stuckRuns = [
  { id: "run_8821", account: "owen.doyle7@live.com", kind: "warm", started: "2h 41m ago", step: "scroll_two_way" },
  { id: "run_8814", account: "daniel.fischer22@outlook.com", kind: "review", started: "51m ago", step: "submit_poll" },
];

const orphans = [
  { id: "gpm-3301", name: "yf-orphan-3301", created: "9d ago" },
  { id: "gpm-3288", name: "yf-orphan-3288", created: "14d ago" },
];

export default function Reaper() {
  const [dryRunning, setDryRunning] = React.useState(false);
  const [autoPrune, setAutoPrune] = React.useState(true);
  const [days, setDays] = React.useState(7);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Reaper & cleanup"
        description="System hygiene: stale locks, stuck runs, orphan GPM profiles and old artifacts. Always dry-run first — deletion is permanent."
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              loading={dryRunning}
              onClick={() => {
                setDryRunning(true);
                setTimeout(() => {
                  setDryRunning(false);
                  toast.success("Dry run: 3 locks, 2 runs, 2 profiles, 412MB artifacts");
                }, 1200);
              }}
            >
              <ScanEye /> Dry run
            </Button>
            <Button size="sm" onClick={() => toast.success("Reaper ran — 412 MB freed")}>
              <Play /> Run reaper
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Stale locks" value={3} hint="TTL expired" tone="warning" icon={<Clock3 className="h-4 w-4" />} />
        <StatTile label="Stuck runs" value={stuckRuns.length} hint="> 30 minutes" tone="danger" icon={<AlertTriangle className="h-4 w-4" />} />
        <StatTile label="Orphan profiles" value={orphans.length} hint="unbound GPM" tone="warning" />
        <StatTile label="Artifact disk" value="1.9 GB" hint="412 MB prunable" tone="info" icon={<HardDrive className="h-4 w-4" />} />
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="stuck">Stuck runs</TabsTrigger>
          <TabsTrigger value="orphans">Orphans</TabsTrigger>
          <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[
            ["Last run", "18m ago", "3 locks · 1 run · 1 profile", "success"],
            ["Previous", "1h ago", "clean", "success"],
            ["Previous", "3h ago", "1 run killed", "warning"],
            ["Previous", "7h ago", "412 MB artifacts", "success"],
          ].map(([label, when, result, tone], i) => (
            <Card key={i}>
              <CardContent className="py-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
                  <Badge variant={tone as never}>{tone === "success" ? "ok" : "warn"}</Badge>
                </div>
                <div className="mt-1 text-[12px] font-medium">{when}</div>
                <div className="text-[10.5px] text-muted-foreground">{result}</div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="stuck">
          <Card>
            <CardContent className="space-y-1.5 pt-3">
              {stuckRuns.map((r) => (
                <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                  <span className="font-mono text-[10px] text-muted-foreground">{r.id}</span>
                  <span className="min-w-0 flex-1 truncate">{r.account}</span>
                  <Badge variant="muted">{r.kind}</Badge>
                  <span className="text-muted-foreground">{r.started}</span>
                  <span className="font-mono text-[10px] text-destructive">{r.step}</span>
                  <Button size="sm" variant="destructive" onClick={() => toast.error(`Killed ${r.id}`)}>
                    Force close
                  </Button>
                </div>
              ))}
              {stuckRuns.length === 0 && <EmptyState title="No stuck runs" />}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="orphans">
          <Card>
            <CardContent className="space-y-1.5 pt-3">
              {orphans.map((o) => (
                <div key={o.id} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                  <span className="font-mono text-[10.5px]">{o.id}</span>
                  <span className="flex-1 text-muted-foreground">{o.name}</span>
                  <span className="text-[10px] text-muted-foreground">{o.created}</span>
                  <Button size="sm" variant="ghost" className="text-destructive" onClick={() => toast.error(`Deleted ${o.id}`)}>
                    <Trash2 /> Delete
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="artifacts">
          <Card>
            <CardContent className="space-y-4 pt-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label={`Retention (days) — ${days}`}>
                  <input type="range" min={1} max={30} value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-full accent-[hsl(var(--primary))]" />
                </Field>
                <Field label="Minimum free disk (GB)">
                  <Input type="number" defaultValue={10} />
                </Field>
              </div>
              <div className="flex items-center justify-between rounded-md border border-border/60 p-2.5">
                <div>
                  <div className="text-[12px]">Auto-prune on disk pressure</div>
                  <div className="text-[10.5px] text-muted-foreground">Triggers when free disk drops below the floor.</div>
                </div>
                <Switch checked={autoPrune} onCheckedChange={setAutoPrune} />
              </div>
              <div>
                <div className="mb-1 flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Artifacts older than {days} days</span>
                  <span className="font-mono">412 MB</span>
                </div>
                <Progress value={64} />
              </div>
              <Button size="sm" onClick={() => toast.success(`Pruned artifacts older than ${days} days`)}>
                <Trash2 /> Prune now
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
