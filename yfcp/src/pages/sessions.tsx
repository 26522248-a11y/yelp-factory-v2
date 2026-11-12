import * as React from "react";
import { Activity, CircleStop, Clock3, MonitorPlay, RefreshCcw, Square } from "lucide-react";
import { toast } from "sonner";
import { AreaChart } from "@tremor/react";
import { PageHeader, SectionLabel, StatTile, EmptyState } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/form";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { runs, warmingSessions } from "@/lib/mock";
import type { Run } from "@/types";
import { formatDuration, timeAgo } from "@/lib/utils";

export default function Sessions() {
  const [detail, setDetail] = React.useState<Run | null>(null);
  const tick = React.useState(0)[1];
  React.useEffect(() => {
    const t = setInterval(() => tick((v) => v + 1), 3000);
    return () => clearInterval(t);
  }, []);

  const history = warmingSessions.slice(0, 20);
  const durationSeries = warmingSessions.slice(0, 14).map((s, i) => ({
    run: `#${i + 1}`,
    minutes: s.durationMin,
    actions: s.actions,
  }));

  const steps = [
    ["S1", "attach_cdp", "DONE"],
    ["S2", "detect_session", "DONE"],
    ["S3", "search_entry", "DONE"],
    ["S4", "pageview", "RUNNING"],
    ["S5", "scroll_two_way", "PENDING"],
    ["S6", "vote_or_save", "PENDING"],
    ["S7", "close_profile", "PENDING"],
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Live"
        title="Sessions"
        description="Every browser run in flight and the trails left behind. Kill a run, resume from a checkpoint, or inspect its browser."
        actions={
          <Button variant="outline" size="sm" onClick={() => toast.success("Sessions refreshed")}>
            <RefreshCcw /> Refresh
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="In flight" value={runs.length} hint="max 2 browser slots" tone="info" icon={<Activity className="h-4 w-4" />} />
        <StatTile label="Browser slots" value="2 / 2" tone="danger" hint="saturated" />
        <StatTile label="Avg session" value="41m" hint="last 14 days" />
        <StatTile label="Killed today" value="1" tone="warning" hint="stuck > 30m" />
      </div>

      <Tabs defaultValue="live">
        <TabsList>
          <TabsTrigger value="live">Live</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="throughput">Throughput</TabsTrigger>
        </TabsList>

        <TabsContent value="live" className="space-y-2">
          {runs.map((run) => {
            const secs = Math.round((Date.now() - new Date(run.startedAt).getTime()) / 1000);
            return (
              <div key={run.id} className="panel flex flex-wrap items-center gap-3 px-3 py-2.5">
                <span className="grid h-8 w-8 place-items-center rounded-md bg-info/10 text-info">
                  <MonitorPlay className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[12px] font-medium">{run.accountEmail}</span>
                    <Badge variant="info">{run.kind}</Badge>
                    <Badge variant="muted">{run.id}</Badge>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <Progress value={(run.stepIndex / run.totalSteps) * 100} className="max-w-56" />
                    <span className="text-[10px] text-muted-foreground">
                      {run.currentStep} · step {run.stepIndex}/{run.totalSteps}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Clock3 className="h-3 w-3" /> {formatDuration(secs)}
                  </span>
                  <span>{run.actionsDone} actions</span>
                  <span className="font-mono">{run.workerId}</span>
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" variant="outline" onClick={() => setDetail(run)}>
                    Inspect
                  </Button>
                  <Button size="sm" variant="ghost" className="text-destructive" onClick={() => toast.warning(`Killed ${run.id}`)}>
                    <CircleStop /> Kill
                  </Button>
                </div>
              </div>
            );
          })}
          {runs.length === 0 && <EmptyState icon={<Activity className="h-6 w-6" />} title="No live sessions" description="Nothing is running right now." />}
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-1">
                {history.map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <div className="flex items-center gap-2">
                      <Badge variant={s.mode === "post_review" ? "info" : "default"}>{s.mode}</Badge>
                      <span>{s.accountEmail}</span>
                    </div>
                    <div className="flex items-center gap-4 text-muted-foreground">
                      <span>{timeAgo(s.startedAt)}</span>
                      <span>{s.durationMin}m</span>
                      <span>{s.actions} actions</span>
                      <span className="font-mono text-success">
                        +{s.trustAfter - s.trustBefore}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="throughput">
          <Card>
            <CardHeader>
              <CardTitle>Session length and action volume</CardTitle>
            </CardHeader>
            <CardContent>
              <AreaChart data={durationSeries} index="run" categories={["minutes", "actions"]} colors={["indigo", "emerald"]} className="h-64" yAxisWidth={32} showGridLines={false} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>{detail?.accountEmail}</DialogTitle>
            <DialogDescription>
              {detail?.kind} · {detail?.id} · worker {detail?.workerId}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-md border border-border/60 p-2">
                <div className="text-[10px] uppercase text-muted-foreground">Elapsed</div>
                <div className="font-mono text-sm">{detail ? formatDuration(Math.round((Date.now() - new Date(detail.startedAt).getTime()) / 1000)) : "—"}</div>
              </div>
              <div className="rounded-md border border-border/60 p-2">
                <div className="text-[10px] uppercase text-muted-foreground">Actions</div>
                <div className="font-mono text-sm">{detail?.actionsDone}</div>
              </div>
              <div className="rounded-md border border-border/60 p-2">
                <div className="text-[10px] uppercase text-muted-foreground">Trace</div>
                <div className="truncate font-mono text-[11px]">{detail?.traceId}</div>
              </div>
            </div>
            <div className="aspect-video rounded-md border border-border bg-gradient-to-br from-secondary to-background grid place-items-center">
              <div className="text-center">
                <MonitorPlay className="mx-auto h-6 w-6 text-muted-foreground/50" />
                <div className="mt-1 text-[11px] text-muted-foreground">Live browser preview (screenshot stream)</div>
              </div>
            </div>
            <SectionLabel>Checkpoints</SectionLabel>
            <div className="space-y-1">
              {steps.map(([seq, name, status]) => (
                <div key={seq} className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1 text-[11px]">
                  <span className="w-6 font-mono text-muted-foreground">{seq}</span>
                  <span className="flex-1 font-mono">{name}</span>
                  <Badge variant={status === "DONE" ? "success" : status === "RUNNING" ? "info" : "muted"}>{status}</Badge>
                </div>
              ))}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDetail(null)}>
              Close
            </Button>
            <Button size="sm" variant="secondary" onClick={() => toast.info("Resume requested from last checkpoint")}>
              Resume from #S4
            </Button>
            <Button size="sm" variant="destructive" onClick={() => { toast.error("Run killed"); setDetail(null); }}>
              <Square /> Force close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
