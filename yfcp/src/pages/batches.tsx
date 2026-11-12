import * as React from "react";
import { ArrowRight, Layers, Pause, Play, Plus, Square } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, SectionLabel, StatTile } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress, Field, Input, Select, Textarea } from "@/components/ui/form";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { batches, accounts } from "@/lib/mock";
import type { Batch } from "@/types";
import { timeAgo } from "@/lib/utils";

const statusVariant = {
  running: "success",
  paused: "warning",
  planned: "muted",
  closed: "secondary",
} as const;

export default function Batches() {
  const [open, setOpen] = React.useState<Batch | null>(null);
  const [create, setCreate] = React.useState(false);

  const totalTarget = batches.reduce((s, b) => s + b.targetCount, 0);
  const totalActual = batches.reduce((s, b) => s + b.actualCount, 0);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operate"
        title="Batches"
        description="Group accounts by intake wave. Batch state drives how much warming and review volume is released."
        actions={
          <Button size="sm" onClick={() => setCreate(true)}>
            <Plus /> New batch
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Batches" value={batches.length} hint="2 running" icon={<Layers className="h-4 w-4" />} />
        <StatTile label="Target accounts" value={totalTarget} hint="across all batches" />
        <StatTile label="Provisioned" value={totalActual} hint={`${totalTarget > 0 ? Math.round((totalActual / totalTarget) * 100) : 0}% of target`} tone="success" />
        <StatTile label="Paused" value={batches.filter((b) => b.status === "paused").length} hint="needs attention" tone="warning" />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {batches.map((b) => (
          <Card key={b.id} className="transition hover:border-primary/30">
            <CardHeader className="flex-row items-start justify-between">
              <div>
                <CardTitle>{b.name}</CardTitle>
                <div className="mt-0.5 text-[10.5px] text-muted-foreground">
                  {b.source} · created {timeAgo(b.createdAt)}
                </div>
              </div>
              <Badge variant={statusVariant[b.status]}>{b.status}</Badge>
            </CardHeader>
            <CardContent className="space-y-2.5">
              <div>
                <div className="mb-1 flex justify-between text-[11px] text-muted-foreground">
                  <span>Provisioned</span>
                  <span className="font-mono">
                    {b.actualCount}/{b.targetCount}
                  </span>
                </div>
                <Progress value={b.targetCount > 0 ? (b.actualCount / b.targetCount) * 100 : 0} />
              </div>
              <p className="line-clamp-2 text-[11px] text-muted-foreground">{b.notes}</p>
              <div className="flex items-center gap-1.5">
                {b.status === "running" ? (
                  <Button size="sm" variant="ghost" onClick={() => toast.warning(`${b.name} paused`)}>
                    <Pause /> Pause
                  </Button>
                ) : b.status === "paused" ? (
                  <Button size="sm" variant="ghost" onClick={() => toast.success(`${b.name} resumed`)}>
                    <Play /> Resume
                  </Button>
                ) : null}
                <Button size="sm" variant="ghost" onClick={() => toast.info(`${b.name} closed`)}>
                  <Square /> Close
                </Button>
                <Button size="sm" variant="outline" className="ml-auto" onClick={() => setOpen(b)}>
                  Detail <ArrowRight />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>{open?.name}</DialogTitle>
            <DialogDescription>
              {open?.source} intake · target {open?.targetCount} · {open?.notes}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              {[
                ["Provisioned", open?.actualCount ?? 0],
                ["Warming", accounts.filter((a) => a.batchId === open?.id && a.state === "WARMING").length],
                ["Ready", accounts.filter((a) => a.batchId === open?.id && a.state === "READY").length],
              ].map(([k, v]) => (
                <div key={k as string} className="rounded-md border border-border/60 p-2">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</div>
                  <div className="text-lg font-semibold">{v}</div>
                </div>
              ))}
            </div>
            <SectionLabel>Accounts in this batch</SectionLabel>
            <div className="panel overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Account</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Phase</TableHead>
                    <TableHead>Trust</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {accounts
                    .filter((a) => a.batchId === open?.id)
                    .slice(0, 10)
                    .map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="text-[11px]">{a.email}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{a.state}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-[11px]">{a.phase}</TableCell>
                        <TableCell className="font-mono text-[11px]">{a.trustScore}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(null)}>
              Close
            </Button>
            <Button size="sm" onClick={() => toast.success("Batch config saved")}>
              Save changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={create} onOpenChange={setCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create batch</DialogTitle>
            <DialogDescription>Batches group accounts for reporting and pause/resume control.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Field label="Name">
              <Input placeholder="Summer Austin ramp" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Target count">
                <Input type="number" defaultValue={20} />
              </Field>
              <Field label="Source">
                <Select defaultValue="signup">
                  <option value="signup">Signup</option>
                  <option value="adopt">Adopt</option>
                  <option value="import">Import</option>
                </Select>
              </Field>
            </div>
            <Field label="Notes">
              <Textarea placeholder="What is this wave for?" />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setCreate(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setCreate(false);
                toast.success("Batch created");
              }}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
