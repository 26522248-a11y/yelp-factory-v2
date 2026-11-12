import * as React from "react";
import { AreaChart, BarChart } from "@tremor/react";
import { AlertTriangle, TrendingUp, Zap } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/form";
import { assignments, clients, reviewVelocity } from "@/lib/mock";
import { cn } from "@/lib/utils";

const metroActivity = [
  { metro: "Austin", accounts: 18, reviews: 14 },
  { metro: "Phoenix", accounts: 12, reviews: 9 },
  { metro: "Denver", accounts: 9, reviews: 6 },
  { metro: "Seattle", accounts: 7, reviews: 5 },
  { metro: "Dallas", accounts: 6, reviews: 3 },
  { metro: "Miami", accounts: 5, reviews: 2 },
];

export default function Velocity() {
  const stalledClients = clients.filter((c) => c.reviewsPosted < 4);
  const posted = reviewVelocity.reduce((s, d) => s + d.posted, 0);
  const filtered = reviewVelocity.reduce((s, d) => s + d.filtered, 0);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Monitor"
        title="Velocity"
        description="How fast reviews are going out, per account, per client and per metro. Runaway velocity is a filter risk."
        actions={
          <Button variant="outline" size="sm" onClick={() => toast.success("Velocity thresholds saved")}>
            Tune thresholds
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Posted 14d" value={posted} tone="success" icon={<TrendingUp className="h-4 w-4" />} />
        <StatTile label="Filtered 14d" value={filtered} hint={`${Math.round((filtered / Math.max(1, posted)) * 100)}% rate`} tone="danger" />
        <StatTile label="Avg / account" value="1.4" hint="per week" tone="info" icon={<Zap className="h-4 w-4" />} />
        <StatTile label="Stalled clients" value={stalledClients.length} hint="no publish in 14d" tone="warning" icon={<AlertTriangle className="h-4 w-4" />} />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Daily review velocity</CardTitle>
          </CardHeader>
          <CardContent>
            <AreaChart
              data={reviewVelocity.map((d) => ({ ...d, rate: Math.round((d.filtered / Math.max(1, d.posted)) * 100) }))}
              index="day"
              categories={["posted", "rate"]}
              colors={["emerald", "rose"]}
              className="h-56"
              yAxisWidth={32}
              showGridLines={false}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Metro activity</CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart data={metroActivity} index="metro" categories={["reviews", "accounts"]} colors={["indigo", "sky"]} className="h-56" yAxisWidth={28} showGridLines={false} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Per-client velocity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {clients.slice(0, 8).map((c) => {
              const assigned = assignments.filter((a) => a.clientId === c.id).length;
              return (
                <div key={c.id} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                  <span className="min-w-0 flex-1 truncate">{c.businessName}</span>
                  <Badge variant="muted">{c.metro.split(",")[0]}</Badge>
                  <div className="w-20">
                    <Progress value={(c.reviewsPosted / Math.max(1, assigned + c.reviewsPosted)) * 100} />
                  </div>
                  <span className="w-16 text-right font-mono text-[10px] text-muted-foreground">
                    {c.reviewsPosted}/{assigned + c.reviewsPosted}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Velocity alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              ["marcus.reed41@outlook.com", "3 reviews in 6 days — above the 2/week soft cap", "warning"],
              ["Bluebonnet Grill", "No publish in 21 days — assignment stalled", "warning"],
              ["nina.patel88@hotmail.com", "4 reviews in the same category this week", "critical"],
            ].map(([who, msg, tone]) => (
              <div key={who as string} className="flex gap-2 rounded-md border border-border/60 p-2">
                <span className={cn("mt-1 h-1.5 w-1.5 shrink-0 rounded-full", tone === "critical" ? "bg-destructive" : "bg-warning")} />
                <div>
                  <div className="text-[11px] font-medium">{who}</div>
                  <div className="text-[10.5px] text-muted-foreground">{msg}</div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
