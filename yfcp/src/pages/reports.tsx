import * as React from "react";
import { BarChart, DonutChart } from "@tremor/react";
import { CalendarRange, Download, FileText, Printer, Table2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { activity7d, reviewVelocity, trustHistory } from "@/lib/mock";

const reports = [
  ["Signup report", "Accounts created per day, success rate, average duration and the top failure reasons."],
  ["Warming report", "Sessions per day, action distribution, phase progression and trust growth."],
  ["Review report", "Posted per week, filter rate, rating distribution and warranty replacements."],
  ["Pool health", "Proxy health ratio, mailbox domain status and captcha success rate."],
  ["Batch report", "Per-batch target vs. actual, survival rate and current status."],
  ["Volume report", "Lazy weeks, throttle events and time-of-day pacing."],
  ["Alert summary", "Alerts per day by type and resolution rate."],
];

export default function Reports() {
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Monitor"
        title="Reports"
        description="Board-ready summaries. Every chart exports to PNG, every dataset to CSV, and the whole page to PDF."
        actions={
          <>
            <Select className="h-8 w-40 text-xs" defaultValue="30">
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </Select>
            <Button variant="outline" size="sm" onClick={() => toast.success("PDF generated")}>
              <Printer /> Export PDF
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Signups (30d)" value={48} delta="+12%" tone="success" />
        <StatTile label="Warming sessions" value={312} delta="+8%" />
        <StatTile label="Reviews published" value={86} delta="+4%" tone="info" />
        <StatTile label="Filter rate" value="18%" delta="-3%" tone="success" />
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="library">Library</TabsTrigger>
          <TabsTrigger value="scheduled">Scheduled</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="grid gap-3 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Activity</CardTitle>
            </CardHeader>
            <CardContent>
              <BarChart data={activity7d} index="day" categories={["signups", "sessions", "reviews"]} colors={["indigo", "sky", "emerald"]} className="h-56" yAxisWidth={28} showGridLines={false} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Review outcomes</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center gap-4">
              <DonutChart
                data={[
                  { name: "Published", value: 86 },
                  { name: "Filtered", value: 19 },
                ]}
                index="name"
                category="value"
                colors={["emerald", "rose"]}
                className="h-32 w-32"
                showLabel={false}
              />
              <div className="text-[11px] text-muted-foreground">
                18% of published reviews were filtered within 72h. Target ceiling is 35%.
              </div>
            </CardContent>
          </Card>
          <Card className="xl:col-span-3">
            <CardHeader>
              <CardTitle>Trust growth</CardTitle>
            </CardHeader>
            <CardContent>
              <BarChart data={trustHistory.slice(-14)} index="day" categories={["avg"]} colors={["indigo"]} className="h-44" yAxisWidth={32} showGridLines={false} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="library">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {reports.map(([name, desc]) => (
              <Card key={name} className="transition hover:border-primary/30">
                <CardHeader className="flex-row items-start justify-between">
                  <CardTitle>{name}</CardTitle>
                  <Table2 className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <p className="text-[11px] text-muted-foreground">{desc}</p>
                  <div className="mt-3 flex gap-1.5">
                    <Button size="sm" variant="outline" onClick={() => toast.success(`${name} — CSV exported`)}>
                      <Download /> CSV
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => toast.success(`${name} — PDF generated`)}>
                      <FileText /> PDF
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="scheduled">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-1">
                {[
                  ["Weekly operator digest", "Mondays 08:00", "Telegram + email", true],
                  ["Monthly board pack", "1st of month 09:00", "PDF to email", true],
                  ["Filter-rate watchdog", "Every 6 hours", "Discord if > 35%", true],
                  ["Pool health", "Daily 07:00", "Telegram", false],
                ].map(([name, cadence, channel, on]) => (
                  <div key={name as string} className="flex items-center gap-3 rounded-md border border-border/60 px-2.5 py-2 text-[11px]">
                    <CalendarRange className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate">{name}</span>
                    <span className="text-muted-foreground">{cadence}</span>
                    <span className="text-muted-foreground">{channel}</span>
                    <Badge variant={on ? "success" : "muted"}>{on ? "on" : "off"}</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
