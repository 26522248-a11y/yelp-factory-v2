import * as React from "react";
import { AlertTriangle, ArrowRight, Download, Radar, Search, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel, EmptyState } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { auditIssues } from "@/lib/mock";
import type { AuditIssue } from "@/types";
import { cn } from "@/lib/utils";

const severityVariant = { high: "destructive", medium: "warning", low: "info" } as const;
const kindLabel = {
  proxy_asn_missing: "Proxy ASN missing",
  asn_shared_in_metro: "ASN shared in metro",
  trust_below_review: "Trust below review gate",
};

export default function Audit() {
  const [open, setOpen] = React.useState<AuditIssue | null>(null);
  const [running, setRunning] = React.useState(false);

  const totalAffected = auditIssues.reduce((s, i) => s + i.affected, 0);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Monitor"
        title="Pool & trust audit"
        description="Anti-detect hygiene. Finds accounts sharing an ASN inside a metro, proxies with no ASN data, and accounts marked review-ready below the gate."
        actions={
          <Button
            size="sm"
            loading={running}
            onClick={() => {
              setRunning(true);
              setTimeout(() => {
                setRunning(false);
                toast.success("Audit complete — 4 issues, 23 affected accounts");
              }, 1600);
            }}
          >
            <Radar /> Run audit
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Issues" value={auditIssues.length} hint="last scan 6m ago" icon={<Search className="h-4 w-4" />} />
        <StatTile label="Affected accounts" value={totalAffected} tone="warning" icon={<AlertTriangle className="h-4 w-4" />} />
        <StatTile label="High severity" value={auditIssues.filter((i) => i.severity === "high").length} tone="danger" />
        <StatTile label="Trust audit" value="passed" hint="no drift > 5" tone="success" icon={<ShieldCheck className="h-4 w-4" />} />
      </div>

      <Tabs defaultValue="issues">
        <TabsList>
          <TabsTrigger value="issues">Issues</TabsTrigger>
          <TabsTrigger value="trust">Trust audit</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="issues">
          <div className="space-y-2">
            {auditIssues.map((issue) => (
              <div key={issue.id} className="panel flex flex-wrap items-center gap-3 px-3 py-2.5">
                <span className={cn("grid h-7 w-7 place-items-center rounded-md", issue.severity === "high" ? "bg-destructive/10 text-destructive" : "bg-warning/10 text-warning")}>
                  <AlertTriangle className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium">{kindLabel[issue.kind]}</span>
                    <Badge variant={severityVariant[issue.severity]}>{issue.severity}</Badge>
                  </div>
                  <div className="text-[10.5px] text-muted-foreground">
                    {issue.metro} · {issue.asn} · {issue.affected} accounts affected
                  </div>
                </div>
                <Button size="sm" variant="outline" onClick={() => setOpen(issue)}>
                  Inspect <ArrowRight />
                </Button>
              </div>
            ))}
            {auditIssues.length === 0 && <EmptyState title="No issues" description="Pool integrity is clean." />}
          </div>
        </TabsContent>

        <TabsContent value="trust">
          <Card>
            <CardContent className="space-y-2 pt-3">
              <SectionLabel>Recompute flagged accounts</SectionLabel>
              {["marcus.reed41@outlook.com", "nina.patel88@hotmail.com", "owen.doyle7@live.com"].map((e) => (
                <div key={e} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                  <span>{e}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-muted-foreground">trust 61 → 68</span>
                    <Badge variant="success">+7</Badge>
                  </div>
                </div>
              ))}
              <Button size="sm" variant="outline" onClick={() => toast.success("Trust recomputed")}>
                Recompute flagged
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-1">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <span>{new Date(Date.now() - i * 86_400_000).toLocaleString()}</span>
                    <div className="flex items-center gap-2">
                      <Badge variant="muted">{3 + i} issues</Badge>
                      <Badge variant="success">clean run</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{open ? kindLabel[open.kind] : ""}</DialogTitle>
            <DialogDescription>
              {open?.metro} · {open?.asn}
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <SectionLabel>Affected accounts</SectionLabel>
            <div className="space-y-1">
              {open?.accounts.map((email) => (
                <div key={email} className="rounded-md border border-border/60 px-2.5 py-1.5 font-mono text-[10.5px]">
                  {email}
                </div>
              ))}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(null)}>
              Close
            </Button>
            <Button size="sm" onClick={() => toast.success("CSV exported")}>
              <Download /> Export
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
