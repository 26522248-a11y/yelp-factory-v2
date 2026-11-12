import * as React from "react";
import { Ban, Clock3, Layers, ShieldOff, Unlock, Waypoints } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel, TierBadge } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { accounts } from "@/lib/mock";
import { cn } from "@/lib/utils";

export default function Lifecycle() {
  const locked = accounts.filter((a) => a.cityLockUntil && new Date(a.cityLockUntil) > new Date());
  const blacklisted = accounts.filter((a) => a.blacklisted);
  const tiers = ["A", "B", "C", "Loai"] as const;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Lifecycle"
        description="Rules that gate an account outside of trust: metro-change locks, tier definitions and the blacklist."
        actions={
          <Button size="sm" onClick={() => toast.success("Lifecycle rules saved")}>
            Save rules
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="City-locked" value={locked.length} hint="48h after a metro move" tone="warning" icon={<Clock3 className="h-4 w-4" />} />
        <StatTile label="Blacklisted" value={blacklisted.length} hint="blocked from reviews" tone="danger" icon={<ShieldOff className="h-4 w-4" />} />
        <StatTile label="Tier A" value={accounts.filter((a) => a.tier === "A").length} tone="success" icon={<Waypoints className="h-4 w-4" />} />
        <StatTile label="Tier Loai" value={accounts.filter((a) => a.tier === "Loai").length} tone="danger" icon={<Ban className="h-4 w-4" />} />
      </div>

      <Tabs defaultValue="locks">
        <TabsList>
          <TabsTrigger value="locks">City locks</TabsTrigger>
          <TabsTrigger value="tiers">Tiers</TabsTrigger>
          <TabsTrigger value="blacklist">Blacklist</TabsTrigger>
          <TabsTrigger value="rules">Rules</TabsTrigger>
        </TabsList>

        <TabsContent value="locks">
          <Card>
            <CardContent className="space-y-1.5 pt-3">
              {locked.map((a) => {
                const remaining = Math.max(0, Math.round((new Date(a.cityLockUntil!).getTime() - Date.now()) / 3600_000));
                return (
                  <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <span className="min-w-0 flex-1 truncate">{a.email}</span>
                    <Badge variant="warning">{a.city}</Badge>
                    <span className="text-muted-foreground">{remaining}h remaining</span>
                    <span className="font-mono text-[10px] text-muted-foreground">until {new Date(a.cityLockUntil!).toLocaleString()}</span>
                    <Button size="sm" variant="ghost" onClick={() => toast.success(`Cleared city lock for ${a.email}`)}>
                      <Unlock /> Clear
                    </Button>
                  </div>
                );
              })}
              {locked.length === 0 && <div className="py-6 text-center text-xs text-muted-foreground">No city locks active.</div>}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tiers">
          <Card>
            <CardContent className="space-y-3 pt-3">
              <div className="grid grid-cols-4 gap-2">
                {tiers.map((t) => (
                  <div key={t} className="rounded-md border border-border/60 p-2.5 text-center">
                    <TierBadge tier={t} />
                    <div className="mt-1.5 text-lg font-semibold">{accounts.filter((a) => a.tier === t).length}</div>
                    <div className="text-[10px] text-muted-foreground">accounts</div>
                  </div>
                ))}
              </div>
              <SectionLabel>Bulk change</SectionLabel>
              <div className="flex flex-wrap items-end gap-2">
                <Field label="Target tier" className="w-40">
                  <Select defaultValue="B">
                    <option>A</option>
                    <option>B</option>
                    <option>C</option>
                    <option>Loai</option>
                  </Select>
                </Field>
                <Button size="sm" onClick={() => toast.success("Tier change queued")}>
                  Apply to selected
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="blacklist">
          <Card>
            <CardContent className="space-y-1.5 pt-3">
              {blacklisted.map((a) => (
                <div key={a.id} className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/5 px-2.5 py-1.5 text-[11px]">
                  <span className="min-w-0 flex-1 truncate">{a.email}</span>
                  <Badge variant="destructive">blacklisted</Badge>
                  <span className="text-[10px] text-muted-foreground">manual hold</span>
                  <Button size="sm" variant="ghost" onClick={() => toast.success(`Removed ${a.email} from blacklist`)}>
                    Unblacklist
                  </Button>
                </div>
              ))}
              {blacklisted.length === 0 && <div className="py-6 text-center text-xs text-muted-foreground">Blacklist is empty.</div>}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="rules" className="max-w-2xl">
          <Card>
            <CardContent className="space-y-3 pt-3">
              <Field label="City change lock (hours)">
                <Input type="number" defaultValue={48} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Tier A — min trust">
                  <Input type="number" defaultValue={85} />
                </Field>
                <Field label="Tier A — min reviews">
                  <Input type="number" defaultValue={4} />
                </Field>
                <Field label="Tier B — min trust">
                  <Input type="number" defaultValue={65} />
                </Field>
                <Field label="Tier C — min trust">
                  <Input type="number" defaultValue={40} />
                </Field>
              </div>
              <div className="rounded-md border border-border/60 bg-background/40 p-2.5 text-[10.5px] text-muted-foreground">
                Below Tier C the account is auto-marked <span className="font-mono text-foreground">Loai</span> and cannot receive assignments.
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
