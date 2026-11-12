import * as React from "react";
import { BarChart } from "@tremor/react";
import { CalendarDays, Flame, Play, RefreshCcw, SkipForward, Timer } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, SectionLabel, StatTile } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Progress, Select, Switch } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { accounts, warmingPlans, warmingSessions, warmingTasks } from "@/lib/mock";
import { cn, timeAgo } from "@/lib/utils";

const phaseDays = [
  { phase: "P0", days: 2, accounts: 8 },
  { phase: "P1", days: 3, accounts: 12 },
  { phase: "P2", days: 5, accounts: 15 },
  { phase: "P3", days: 10, accounts: 18 },
  { phase: "P4", days: 10, accounts: 11 },
];

export default function Warming() {
  const [enabled, setEnabled] = React.useState(true);
  const [minGap, setMinGap] = React.useState(90);

  const actions = warmingSessions.slice(0, 14).map((s, i) => ({
    session: `S${i + 1}`,
    search: 2 + (i % 3),
    pageviews: 3 + (i % 5),
    scrolls: 4 + (i % 4),
    votes: i % 3,
  }));

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operate"
        title="Warming"
        description="The cadence that makes accounts look alive. Plans are generated per account, released inside the metro working window, and gated by trust."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => toast.success("Plans regenerated for 12 accounts")}>
              <RefreshCcw /> Regenerate
            </Button>
            <Button size="sm" onClick={() => toast.success("Manual warming session started")}>
              <Play /> Start session
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Plans today" value={warmingPlans.length} hint="across 28 accounts" icon={<CalendarDays className="h-4 w-4" />} />
        <StatTile label="Sessions today" value={9} delta="+2" hint="vs. yesterday" tone="success" icon={<Flame className="h-4 w-4" />} />
        <StatTile label="Queued tasks" value={warmingTasks.filter((t) => t.status === "queued").length} hint="next in 12m" tone="info" icon={<Timer className="h-4 w-4" />} />
        <StatTile label="Min gap" value={`${minGap}m`} hint="between sessions" tone="warning" />
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        {phaseDays.map((p) => (
          <Card key={p.phase}>
            <CardContent className="py-2.5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[12px] font-semibold">{p.phase}</span>
                <Badge variant="muted">{p.days}d</Badge>
              </div>
              <div className="mt-1 text-lg font-semibold">{p.accounts}</div>
              <div className="text-[10px] text-muted-foreground">accounts in this phase</div>
              <Progress className="mt-2" value={(p.accounts / 22) * 100} />
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="today">
        <TabsList>
          <TabsTrigger value="today">Today's plan</TabsTrigger>
          <TabsTrigger value="plans">Plans</TabsTrigger>
          <TabsTrigger value="actions">Action mix</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="today" className="grid gap-3 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Queued tasks</CardTitle>
              <span className="text-[10px] text-muted-foreground">metro-local 06:00–23:00</span>
            </CardHeader>
            <CardContent className="space-y-1">
              {warmingTasks.slice(0, 12).map((t) => (
                <div key={t.id} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                  <span className="flex-1 truncate">{t.accountEmail}</span>
                  <Badge variant="muted">{t.kind}</Badge>
                  <span className="w-28 text-right text-muted-foreground">{new Date(t.dueAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  <Badge
                    variant={
                      t.status === "done" ? "success" : t.status === "running" ? "info" : t.status === "failed" ? "destructive" : "secondary"
                    }
                  >
                    {t.status}
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Working hours</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-md border border-border/60 p-2.5">
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Austin, TX</span>
                  <span className="font-mono">14:32 CT</span>
                </div>
                <div className="mt-1 text-[10px] text-success">inside working window</div>
              </div>
              <div className="rounded-md border border-border/60 p-2.5">
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Seattle, WA</span>
                  <span className="font-mono">12:32 PT</span>
                </div>
                <div className="mt-1 text-[10px] text-success">inside working window</div>
              </div>
              <div className="rounded-md border border-border/60 p-2.5">
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Phoenix, AZ</span>
                  <span className="font-mono">12:32 MST</span>
                </div>
                <div className="mt-1 text-[10px] text-success">inside working window</div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="plans">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-1">
                {warmingPlans.map((p) => (
                  <div key={p.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <span className="min-w-48 flex-1 truncate">{p.accountEmail}</span>
                    <Badge variant="muted">{p.phase}</Badge>
                    <span className="text-muted-foreground">day {p.day}</span>
                    <span className="hidden gap-2 text-[10px] text-muted-foreground md:flex">
                      <span>s{p.budget.search}</span>
                      <span>p{p.budget.pageview}</span>
                      <span>sc{p.budget.scroll}</span>
                      <span>v{p.budget.vote}</span>
                    </span>
                    <Badge variant={p.status === "done" ? "success" : p.status === "active" ? "info" : p.status === "skipped" ? "warning" : "secondary"}>{p.status}</Badge>
                    <Button size="sm" variant="ghost" onClick={() => toast.info(`Regenerated plan for ${p.accountEmail}`)}>
                      <RefreshCcw />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => toast.warning(`Forced ${p.accountEmail} to next phase`)}>
                      <SkipForward />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="actions">
          <Card>
            <CardHeader>
              <CardTitle>Action distribution per session</CardTitle>
            </CardHeader>
            <CardContent>
              <BarChart data={actions} index="session" categories={["search", "pageviews", "scrolls", "votes"]} colors={["indigo", "sky", "emerald", "amber"]} stack className="h-64" yAxisWidth={28} showGridLines={false} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="settings" className="max-w-2xl">
          <Card>
            <CardContent className="space-y-4 pt-3">
              <div className="flex items-center justify-between rounded-md border border-border/60 p-2.5">
                <div>
                  <div className="text-[12px]">Warming enabled</div>
                  <div className="text-[10.5px] text-muted-foreground">Master switch for all scheduled sessions.</div>
                </div>
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Max sessions / day">
                  <Input type="number" defaultValue={3} />
                </Field>
                <Field label="Minimum gap (minutes)">
                  <Input type="number" value={minGap} onChange={(e) => setMinGap(Number(e.target.value))} />
                </Field>
                <Field label="Working window start">
                  <Input type="time" defaultValue="06:00" />
                </Field>
                <Field label="Working window end">
                  <Input type="time" defaultValue="23:00" />
                </Field>
              </div>
              <div className="grid grid-cols-5 gap-2">
                {phaseDays.map((p) => (
                  <Field key={p.phase} label={`${p.phase} days`}>
                    <Input type="number" defaultValue={p.days} />
                  </Field>
                ))}
              </div>
              <Button size="sm" onClick={() => toast.success("Warming settings saved")}>
                Save
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
