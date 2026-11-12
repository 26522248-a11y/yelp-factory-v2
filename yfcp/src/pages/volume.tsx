import * as React from "react";
import { AreaChart } from "@tremor/react";
import { Pause, Play, RotateCcw, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress, Switch } from "@/components/ui/form";
import { reviewVelocity } from "@/lib/mock";
import { cn } from "@/lib/utils";

const filterSeries = reviewVelocity.map((d) => ({
  day: d.day,
  rate: Math.round((d.filtered / Math.max(1, d.posted)) * 100),
}));

export default function Volume() {
  const [pin, setPin] = React.useState(100);
  const [paused, setPaused] = React.useState(false);
  const [overrideLazy, setOverrideLazy] = React.useState(false);

  const lazy = overrideLazy ? 1 : 0.6;
  const filter = 0.8;
  const manual = paused ? 0 : pin / 100;
  const effective = lazy * filter * manual;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Monitor"
        title="Volume governor"
        description="Output is throttled three ways: lazy weeks, filter-rate response and a manual pin. Whatever you set, the effective multiplier is the product."
        actions={
          <>
            {paused ? (
              <Button size="sm" variant="success" onClick={() => { setPaused(false); toast.success("Volume resumed"); }}>
                <Play /> Resume
              </Button>
            ) : (
              <Button size="sm" variant="destructive" onClick={() => { setPaused(true); toast.error("Volume paused"); }}>
                <Pause /> Pause all
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => { setPin(100); setPaused(false); setOverrideLazy(false); toast.success("Volume reset to 1.0×"); }}>
              <RotateCcw /> Reset
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Effective multiplier" value={`${effective.toFixed(2)}×`} hint="lazy × filter × pin" tone={effective < 0.5 ? "warning" : "success"} icon={<SlidersHorizontal className="h-4 w-4" />} />
        <StatTile label="Lazy week" value={overrideLazy ? "overridden" : "active"} hint="week 46 of 52" tone="info" />
        <StatTile label="7-day filter rate" value="18%" hint="threshold 35%" tone="success" />
        <StatTile label="Actions released today" value={Math.round(64 * effective)} hint="of 64 budgeted" />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Filter-rate response</CardTitle>
          </CardHeader>
          <CardContent>
            <AreaChart data={filterSeries} index="day" categories={["rate"]} colors={["rose"]} className="h-52" yAxisWidth={32} showGridLines={false} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Manual pin</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex justify-between text-[11px]">
                <span className="text-muted-foreground">Multiplier</span>
                <span className="font-mono">{(pin / 100).toFixed(2)}×</span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={pin}
                onChange={(e) => setPin(Number(e.target.value))}
                className="mt-2 w-full accent-[hsl(var(--primary))]"
              />
              <div className="flex justify-between text-[9.5px] text-muted-foreground">
                <span>0×</span>
                <span>0.5×</span>
                <span>1×</span>
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between rounded-md border border-border/60 p-2">
                <div>
                  <div className="text-[11px]">Override lazy week</div>
                  <div className="text-[10px] text-muted-foreground">Force full volume this week</div>
                </div>
                <Switch checked={overrideLazy} onCheckedChange={setOverrideLazy} />
              </div>
              <div className="rounded-md border border-border/60 p-2 text-[10.5px] text-muted-foreground">
                Effective: <span className="font-mono text-foreground">{lazy.toFixed(2)}</span> ×{" "}
                <span className="font-mono text-foreground">{filter.toFixed(2)}</span> ×{" "}
                <span className="font-mono text-foreground">{manual.toFixed(2)}</span> ={" "}
                <span className="font-mono text-primary">{effective.toFixed(2)}×</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Lazy weeks</CardTitle>
            <Badge variant="warning">2 of 4 weeks</Badge>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-2">
              {[1, 2, 3, 4].map((w) => (
                <div key={w} className={cn("rounded-md border p-2 text-center", [2, 4].includes(w) ? "border-warning/40 bg-warning/10" : "border-border")}>
                  <div className="text-[10px] text-muted-foreground">week {w}</div>
                  <div className="text-[12px] font-medium">{[2, 4].includes(w) ? "60%" : "100%"}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Time-of-day pacing</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              ["Morning (06–12)", 30],
              ["Afternoon (12–18)", 40],
              ["Evening (18–23)", 30],
            ].map(([label, pct]) => (
              <div key={label as string}>
                <div className="mb-1 flex justify-between text-[11px]">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="font-mono">{pct}%</span>
                </div>
                <Progress value={Number(pct)} />
              </div>
            ))}
            <div className="rounded-md border border-border/60 bg-background/40 px-2 py-1.5 text-[10.5px] text-muted-foreground">
              Current slot: <span className="text-foreground">afternoon</span> · next release in 14m
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
