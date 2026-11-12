import * as React from "react";
import { AreaChart, BarChart } from "@tremor/react";
import { RefreshCcw, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel, TierBadge } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Progress } from "@/components/ui/form";
import { accounts, trustHistory } from "@/lib/mock";
import { cn } from "@/lib/utils";

const buckets = [
  { range: "0–25", count: accounts.filter((a) => a.trustScore <= 25).length },
  { range: "26–50", count: accounts.filter((a) => a.trustScore > 25 && a.trustScore <= 50).length },
  { range: "51–75", count: accounts.filter((a) => a.trustScore > 50 && a.trustScore <= 75).length },
  { range: "76–100", count: accounts.filter((a) => a.trustScore > 75).length },
];

export default function Trust() {
  const sorted = [...accounts].sort((a, b) => b.trustScore - a.trustScore).slice(0, 10);
  const avg = Math.round(accounts.reduce((s, a) => s + a.trustScore, 0) / accounts.length);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Monitor"
        title="Trust"
        description="Trust is derived from real behaviour, never seeded. The review gate opens at 75 with 7+ days, 8+ photos and 6 sessions in the last week."
        actions={
          <Button size="sm" onClick={() => toast.success("Trust recompute queued for all accounts")}>
            <RefreshCcw /> Recompute all
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Average trust" value={avg} hint="farm-wide" icon={<ShieldCheck className="h-4 w-4" />} />
        <StatTile label="Above gate" value={accounts.filter((a) => a.trustScore >= 75).length} hint="review-eligible" tone="success" icon={<Sparkles className="h-4 w-4" />} />
        <StatTile label="Near gate" value={accounts.filter((a) => a.trustScore >= 65 && a.trustScore < 75).length} hint="65–74" tone="warning" />
        <StatTile label="Below 40" value={accounts.filter((a) => a.trustScore < 40).length} hint="quarantine candidates" tone="danger" />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Farm trust trajectory</CardTitle>
          </CardHeader>
          <CardContent>
            <AreaChart data={trustHistory} index="day" categories={["avg"]} colors={["indigo"]} className="h-52" yAxisWidth={32} showGridLines={false} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart data={buckets} index="range" categories={["count"]} colors={["sky"]} className="h-52" yAxisWidth={28} showGridLines={false} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Leaderboard</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {sorted.map((a, i) => (
              <div key={a.id} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                <span className="w-4 font-mono text-muted-foreground">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate">{a.email}</span>
                <TierBadge tier={a.tier} />
                <div className="w-24">
                  <Progress value={a.trustScore} barClassName={a.trustScore >= 75 ? "bg-success" : a.trustScore >= 50 ? "bg-warning" : "bg-destructive"} />
                </div>
                <span className="w-6 text-right font-mono">{a.trustScore}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Components</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              ["Age", 15, "Older accounts score higher"],
              ["Profile", 15, "Avatar, bio, birthday"],
              ["Consistency", 12, "Regular session cadence"],
              ["Diversity", 18, "Category / metro spread"],
              ["Warm", 30, "Real sessions with 3+ actions"],
              ["Content", 20, "Tips, photos, check-ins"],
              ["Risk", -20, "Challenge / ban signal"],
            ].map(([label, weight, desc]) => (
              <div key={label as string} className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-[11px]">{label}</div>
                  <div className="text-[9.5px] text-muted-foreground">{desc}</div>
                </div>
                <Badge variant={Number(weight) < 0 ? "destructive" : "muted"} className="font-mono">
                  {weight}
                </Badge>
              </div>
            ))}
            <div className="border-t border-border pt-2">
              <SectionLabel>Gate settings</SectionLabel>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Threshold">
                  <Input type="number" defaultValue={75} />
                </Field>
                <Field label="Min days">
                  <Input type="number" defaultValue={7} />
                </Field>
                <Field label="Min photos">
                  <Input type="number" defaultValue={8} />
                </Field>
                <Field label="Sessions / 7d">
                  <Input type="number" defaultValue={6} />
                </Field>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
