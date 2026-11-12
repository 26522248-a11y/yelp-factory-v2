import * as React from "react";
import { BarChart, DonutChart } from "@tremor/react";
import { BadgeCheck, CalendarClock, Filter, Image as ImageIcon, Send, Sparkles, Star } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel, EmptyState } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { assignments, clients, reviews, reviewVelocity } from "@/lib/mock";
import { cn, timeAgo } from "@/lib/utils";

const FILTERED = reviews.filter((r) => r.status === "filtered").length;
const filterRate = Math.round((FILTERED / Math.max(1, reviews.length)) * 100);

export default function Reviews() {
  const [postOpen, setPostOpen] = React.useState<string | null>(null);
  const [assignOpen, setAssignOpen] = React.useState(false);
  const [text, setText] = React.useState(
    "Stopped in on a Tuesday around 6pm and the place was busy but not packed. The brisket had a proper bark and the green chile stew was the sleeper hit. Only knock: the parking lot is tight, so come early."
  );

  const due = assignments.filter((a) => a.status === "assigned" || a.status === "pending");

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operate"
        title="Reviews"
        description="Assignments, posting and filter tracking. Text is generated from client facts, deduped by 5-gram, and always ships with a photo."
        actions={
          <Button size="sm" onClick={() => setAssignOpen(true)}>
            <CalendarClock /> Assign reviews
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Posted" value={reviews.length} hint="all time" tone="success" icon={<BadgeCheck className="h-4 w-4" />} />
        <StatTile label="Filtered" value={FILTERED} hint={`${filterRate}% filter rate`} tone="danger" icon={<Filter className="h-4 w-4" />} />
        <StatTile label="Due today" value={due.length} hint="assignments waiting" tone="warning" icon={<CalendarClock className="h-4 w-4" />} />
        <StatTile label="Avg rating" value="4.7" hint="70/30 five/four split" tone="info" icon={<Star className="h-4 w-4" />} />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Published vs. filtered</CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart data={reviewVelocity} index="day" categories={["posted", "filtered"]} colors={["emerald", "rose"]} className="h-48" yAxisWidth={28} showGridLines={false} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Rating mix</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-4">
            <DonutChart
              data={[
                { name: "5 stars", value: Math.round(reviews.length * 0.7) },
                { name: "4 stars", value: Math.round(reviews.length * 0.3) },
              ]}
              index="name"
              category="value"
              colors={["emerald", "sky"]}
              className="h-32 w-32"
              showLabel={false}
            />
            <div className="text-[11px] text-muted-foreground">
              Mild flaws are injected even on 5★ reviews — a perfect score with no criticism is a filter magnet.
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="due">
        <TabsList>
          <TabsTrigger value="due">Due ({due.length})</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="due">
          <Card>
            <CardContent className="space-y-1.5 pt-3">
              {due.map((a) => (
                <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5">
                  <span className="min-w-44 flex-1 truncate text-[11px]">{a.accountEmail}</span>
                  <Badge variant="outline">{a.clientName}</Badge>
                  <Badge variant={a.status === "assigned" ? "info" : "secondary"}>{a.status}</Badge>
                  <span className="text-[10px] text-muted-foreground">due {new Date(a.reviewDueAt).toLocaleString()}</span>
                  <Button size="sm" className="ml-auto" onClick={() => setPostOpen(a.id)}>
                    <Send /> Post
                  </Button>
                </div>
              ))}
              {due.length === 0 && <EmptyState title="Nothing due" description="All assignments are completed." />}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardContent className="space-y-2 pt-3">
              {reviews.slice(0, 12).map((r) => (
                <div key={r.id} className="rounded-md border border-border/60 p-2.5">
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="font-medium">{r.businessName}</span>
                    <span className="text-warning">{"★".repeat(r.rating)}</span>
                    <Badge variant={r.status === "posted" ? "success" : "destructive"}>{r.status}</Badge>
                    <span className="text-[10px] text-muted-foreground">{r.accountEmail}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">{timeAgo(r.postedAt)}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{r.text}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="settings" className="max-w-2xl">
          <Card>
            <CardContent className="space-y-3 pt-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Sessions per day">
                  <Input type="number" defaultValue={1} />
                </Field>
                <Field label="Max concurrent profiles">
                  <Input type="number" defaultValue={2} />
                </Field>
                <Field label="Review window start">
                  <Input type="time" defaultValue="08:00" />
                </Field>
                <Field label="Review window end">
                  <Input type="time" defaultValue="20:00" />
                </Field>
                <Field label="Penalty days on 429">
                  <Input type="number" defaultValue={3} />
                </Field>
                <Field label="Warranty max per client">
                  <Input type="number" defaultValue={2} />
                </Field>
              </div>
              <div>
                <div className="mb-1 flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Star distribution</span>
                  <span className="font-mono">70% · 30%</span>
                </div>
                <div className="flex h-2 overflow-hidden rounded-full">
                  <span className="w-[70%] bg-success" />
                  <span className="w-[30%] bg-info" />
                </div>
              </div>
              <Button size="sm" onClick={() => toast.success("Review settings saved")}>
                Save
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={!!postOpen} onOpenChange={(v) => !v && setPostOpen(null)}>
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>Post review</DialogTitle>
            <DialogDescription>Preview the generated text, swap the photo, then hand off to the browser flow.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4, 5].map((n) => (
                <Star key={n} className={cn("h-4 w-4", n <= 5 ? "fill-warning text-warning" : "text-muted-foreground")} />
              ))}
              <Badge variant="muted" className="ml-2">
                generated
              </Badge>
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setText((t) => t.split(".").reverse().join("."))}>
                <Sparkles /> Regenerate
              </Button>
            </div>
            <Textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} />
            <div>
              <SectionLabel>Photo (required)</SectionLabel>
              <div className="grid grid-cols-5 gap-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <button
                    key={i}
                    className={cn(
                      "flex aspect-square items-center justify-center rounded-md border",
                      i === 0 ? "border-primary/50 bg-primary/5" : "border-border hover:bg-accent/40"
                    )}
                  >
                    <ImageIcon className={cn("h-4 w-4", i === 0 ? "text-primary" : "text-muted-foreground/50")} />
                  </button>
                ))}
              </div>
            </div>
            <div className="rounded-md border border-border/60 bg-background/40 p-2 text-[10.5px] text-muted-foreground">
              Text checks: 4 sentences · 61 words · 5-gram dedupe passed · concrete details present · mild flaw present.
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setPostOpen(null)}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => { toast.success("Review posted — filter check in 72h"); setPostOpen(null); }}>
              <Send /> Submit review
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>Assign reviews</DialogTitle>
            <DialogDescription>Only accounts past the trust gate and outside their rest window are eligible.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Client">
                <Select>
                  {clients.map((c) => (
                    <option key={c.id}>{c.businessName}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Eligible accounts">
                <Select defaultValue="auto">
                  <option value="auto">Auto — 6 eligible</option>
                  <option value="manual">Pick manually…</option>
                </Select>
              </Field>
            </div>
            <SectionLabel>Eligibility preview</SectionLabel>
            <div className="space-y-1">
              {["marcus.reed41@outlook.com", "nina.patel88@hotmail.com", "sofia.novak9@outlook.com"].map((email, i) => (
                <div key={email} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                  <span>{email}</span>
                  <div className="flex items-center gap-2">
                    <Badge variant="success">trust {82 + i}</Badge>
                    <Badge variant="muted">no rest</Badge>
                  </div>
                </div>
              ))}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setAssignOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => { toast.success("3 assignments created"); setAssignOpen(false); }}>
              Create assignments
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
