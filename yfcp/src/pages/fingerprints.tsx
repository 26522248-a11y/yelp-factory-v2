import * as React from "react";
import { BarChart, DonutChart } from "@tremor/react";
import { Fingerprint, ScanLine, ShieldCheck, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Progress } from "@/components/ui/form";
import { accounts } from "@/lib/mock";
import { cn } from "@/lib/utils";

const windows = [
  { size: "1920×1080", count: 22 },
  { size: "1536×864", count: 17 },
  { size: "1440×900", count: 11 },
  { size: "1366×768", count: 8 },
  { size: "1280×720", count: 6 },
];

export default function Fingerprints() {
  const [lookup, setLookup] = React.useState(accounts[0].email);
  const found = accounts.find((a) => a.email === lookup) ?? accounts[0];

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Fingerprint matrix"
        description="Each account gets a deterministic browser fingerprint from its ID. The matrix exists to make the farm look like many people, not one."
        actions={
          <Button variant="outline" size="sm" onClick={() => toast.success("Fingerprint audit complete")}>
            <ScanLine /> Audit diversity
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Unique windows" value={windows.length} hint="across 64 accounts" tone="success" icon={<Fingerprint className="h-4 w-4" />} />
        <StatTile label="Chrome share" value="78%" hint="Firefox 22%" tone="info" />
        <StatTile label="Diversity score" value="0.82" hint="target > 0.7" tone="success" icon={<ShieldCheck className="h-4 w-4" />} />
        <StatTile label="Salt" value="v1" hint="yf-fingerprint-v1" />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Window size distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart data={windows} index="size" categories={["count"]} colors={["indigo"]} className="h-48" yAxisWidth={28} showGridLines={false} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Browser split</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-4">
            <DonutChart
              data={[
                { name: "Chrome", value: 78 },
                { name: "Firefox", value: 22 },
              ]}
              index="name"
              category="value"
              colors={["sky", "amber"]}
              className="h-32 w-32"
              showLabel={false}
            />
            <div className="text-[11px] text-muted-foreground">Deterministic from account ID via blake2b, salted once at the farm level.</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Per-account lookup</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="Account email">
              <Input value={lookup} onChange={(e) => setLookup(e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                ["OS", "Windows 11"],
                ["Browser", "Chrome 131"],
                ["Window", ["1920×1080", "1536×864", "1440×900"][found.avatarHue % 3]],
                ["Timezone", found.timezone],
                ["WebGL", "NVIDIA GeForce"],
                ["Canvas noise", "enabled"],
              ].map(([k, v]) => (
                <div key={k} className="rounded-md border border-border/60 p-2">
                  <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">{k}</div>
                  <div className="mt-0.5 truncate text-[11px]">{v}</div>
                </div>
              ))}
            </div>
            <div className="rounded-md border border-border/60 bg-background/40 p-2 text-[10.5px] text-muted-foreground">
              Matrix-calculated fingerprint vs. GPM persisted: <Badge variant="success">match</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Salt & versions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="Fingerprint salt" hint="Changing this reshuffles every fingerprint.">
              <Input defaultValue="yf-fingerprint-v1" />
            </Field>
            <div className="rounded-md border border-warning/25 bg-warning/10 p-2 text-[10.5px] text-warning">
              Rotating the salt is a farm-wide event. Existing sessions keep their current fingerprint until the profile is recreated.
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-muted-foreground">Chromium versions</span>
              <span className="font-mono">131.0.6778</span>
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-muted-foreground">Firefox versions</span>
              <span className="font-mono">133.0.3</span>
            </div>
            <Button size="sm" className="w-full" onClick={() => toast.success("Version pins applied")}>
              <Wand2 /> Apply version pins
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
