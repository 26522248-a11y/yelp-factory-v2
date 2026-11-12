import * as React from "react";
import { AlertTriangle, Code2, Save, Search, Target } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Progress, Textarea } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { selectors } from "@/lib/mock";
import { cn } from "@/lib/utils";

export default function Selectors() {
  const [selected, setSelected] = React.useState(selectors[0]);
  const [testHtml, setTestHtml] = React.useState('<button id="onetrust-accept-btn-handler">Accept all</button>');
  const [testResult, setTestResult] = React.useState<string | null>(null);

  const worst = [...selectors].sort((a, b) => b.misses - a.misses);
  const totalHits = selectors.reduce((s, x) => s + x.hits, 0);
  const totalMisses = selectors.reduce((s, x) => s + x.misses, 0);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Selector registry"
        description="Yelp ships DOM changes. Every interaction is a priority list of CSS, label, placeholder and text strategies — this is where you fix them."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => toast.success("registry.yaml reloaded")}>
              Reload
            </Button>
            <Button size="sm" onClick={() => toast.success("registry.yaml saved")}>
              <Save /> Save registry
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Selectors" value={selectors.length} hint="active rules" icon={<Target className="h-4 w-4" />} />
        <StatTile label="Hit rate" value={`${Math.round((totalHits / (totalHits + totalMisses)) * 100)}%`} tone="success" />
        <StatTile label="Misses 24h" value={totalMisses} tone="warning" icon={<AlertTriangle className="h-4 w-4" />} />
        <StatTile label="Failing" value={selectors.filter((s) => s.misses > 20).length} hint="> 20 misses" tone="danger" />
      </div>

      <div className="grid gap-3 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Rules by miss rate</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {worst.map((s) => (
              <button
                key={s.key}
                onClick={() => setSelected(s)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left transition",
                  selected.key === s.key ? "border-primary/40 bg-primary/5" : "border-border/60 hover:bg-accent/40"
                )}
              >
                <span className="min-w-0 flex-1 truncate font-mono text-[10.5px]">{s.key}</span>
                <div className="w-14">
                  <Progress value={(s.misses / (s.hits + s.misses)) * 100} barClassName={s.misses > 20 ? "bg-destructive" : "bg-warning"} />
                </div>
                <span className={cn("w-6 text-right font-mono text-[10px]", s.misses > 20 ? "text-destructive" : "text-muted-foreground")}>{s.misses}</span>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="xl:col-span-3">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="font-mono text-[12px]">{selected.key}</CardTitle>
            <Badge variant={selected.active ? "success" : "muted"}>{selected.active ? "active" : "inactive"}</Badge>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="strategies">
              <TabsList>
                <TabsTrigger value="strategies">Strategies</TabsTrigger>
                <TabsTrigger value="yaml">Raw YAML</TabsTrigger>
                <TabsTrigger value="test">Test</TabsTrigger>
              </TabsList>

              <TabsContent value="strategies" className="space-y-1.5">
                {selected.strategies.map((strat, i) => (
                  <div key={i} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5">
                    <span className="w-5 font-mono text-[10px] text-muted-foreground">#{i + 1}</span>
                    <span className="flex-1 font-mono text-[11px]">{strat}</span>
                    <Badge variant="muted">priority {selected.priority + i}</Badge>
                    <Badge variant="success">visible</Badge>
                  </div>
                ))}
                <div className="grid grid-cols-3 gap-2 pt-2">
                  <Field label="Hits">
                    <Input value={selected.hits} readOnly />
                  </Field>
                  <Field label="Misses">
                    <Input value={selected.misses} readOnly />
                  </Field>
                  <Field label="Page tag">
                    <Input value={selected.pageTag} readOnly />
                  </Field>
                </div>
              </TabsContent>

              <TabsContent value="yaml">
                <Textarea
                  rows={10}
                  className="font-mono text-[11px]"
                  defaultValue={`${selected.key}:
  page: ${selected.pageTag}
  priority: ${selected.priority}
  strategies:
${selected.strategies.map((s) => `    - ${s}`).join("\n")}
  active: ${selected.active}`}
                />
                <Button size="sm" className="mt-2" onClick={() => toast.success("Rule saved")}>
                  <Save /> Save rule
                </Button>
              </TabsContent>

              <TabsContent value="test" className="space-y-2">
                <Field label="Paste HTML">
                  <Textarea rows={5} className="font-mono text-[11px]" value={testHtml} onChange={(e) => setTestHtml(e.target.value)} />
                </Field>
                <Button size="sm" variant="outline" onClick={() => setTestResult("Matched via strategy #1 · element visible · bounding box 212×38")}>
                  <Search /> Run selector
                </Button>
                {testResult && <div className="rounded-md border border-success/25 bg-success/10 p-2 text-[11px] text-success">{testResult}</div>}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Miss-rate monitor</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-3">
            {selectors
              .filter((s) => s.misses > 10)
              .map((s) => (
                <div key={s.key} className="rounded-md border border-warning/25 bg-warning/5 p-2">
                  <div className="flex items-center gap-1.5">
                    <Code2 className="h-3 w-3 text-warning" />
                    <span className="truncate font-mono text-[10.5px]">{s.key}</span>
                  </div>
                  <div className="mt-1 text-[10px] text-muted-foreground">{s.misses} misses · {s.pageTag}</div>
                </div>
              ))}
          </div>
          <p className="mt-2 text-[10.5px] text-muted-foreground">
            Threshold: alert when a key exceeds 20 misses per hour. Adjust in workspace settings.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
