import * as React from "react";
import { Flag, Plus, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, SectionLabel, StatTile } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Textarea } from "@/components/ui/form";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { JsonViewer } from "@/components/shared/bits";
import { systemFlags } from "@/lib/mock";
import type { SystemFlag } from "@/types";
import { timeAgo } from "@/lib/utils";

export default function Flags() {
  const [flags, setFlags] = React.useState<SystemFlag[]>(systemFlags);
  const [editing, setEditing] = React.useState<SystemFlag | null>(null);
  const [draft, setDraft] = React.useState("{}");

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="System flags"
        description="Operational switches stored in the database so every worker sees them instantly. Volume pin, pause, filter alert thresholds and recompute markers."
        actions={
          <Button size="sm" onClick={() => { setEditing({ key: "", value: {}, updatedAt: new Date().toISOString() }); setDraft("{}"); }}>
            <Plus /> New flag
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Flags" value={flags.length} icon={<Flag className="h-4 w-4" />} />
        <StatTile label="Volume pin" value="0.8×" hint="manual multiplier" tone="info" />
        <StatTile label="Paused" value="no" hint="pipeline running" tone="success" />
        <StatTile label="Recompute" value="idle" hint="last 26h ago" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Flag registry</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {flags.map((f) => (
            <div key={f.key} className="rounded-md border border-border/60 p-2.5">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] font-medium">{f.key}</span>
                <Badge variant="muted">json</Badge>
                <span className="ml-auto text-[10px] text-muted-foreground">{timeAgo(f.updatedAt)}</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setEditing(f);
                    setDraft(JSON.stringify(f.value, null, 2));
                  }}
                >
                  Edit
                </Button>
                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { setFlags((p) => p.filter((x) => x.key !== f.key)); toast.error(`Deleted ${f.key}`); }}>
                  <Trash2 />
                </Button>
              </div>
              <JsonViewer data={f.value} className="mt-2 max-h-32" />
            </div>
          ))}
        </CardContent>
      </Card>

      <Dialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing?.key ? `Edit ${editing.key}` : "New system flag"}</DialogTitle>
            <DialogDescription>Values are JSON. Workers read them on every task tick.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Field label="Key">
              <Input
                value={editing?.key ?? ""}
                onChange={(e) => editing && setEditing({ ...editing, key: e.target.value })}
                placeholder="volume"
                disabled={!!editing?.key && flags.some((f) => f.key === editing.key)}
              />
            </Field>
            <Field label="Value (JSON)" hint="Must parse as JSON — objects, arrays or scalars.">
              <Textarea rows={7} className="font-mono text-[11px]" value={draft} onChange={(e) => setDraft(e.target.value)} />
            </Field>
            {editing?.key === "volume" && (
              <div className="rounded-md border border-warning/25 bg-warning/10 p-2 text-[10.5px] text-warning">
                Setting volume to 0 or paused stops all output. Confirm before saving.
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                try {
                  const parsed = JSON.parse(draft);
                  if (editing?.key) {
                    setFlags((p) => p.map((x) => (x.key === editing.key ? { ...x, value: parsed, updatedAt: new Date().toISOString() } : x)));
                  } else {
                    setFlags((p) => [...p, { key: "new_flag", value: parsed, updatedAt: new Date().toISOString() }]);
                  }
                  toast.success("Flag saved");
                  setEditing(null);
                } catch {
                  toast.error("Value is not valid JSON");
                }
              }}
            >
              <Save /> Save flag
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
