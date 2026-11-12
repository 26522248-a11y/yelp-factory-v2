import * as React from "react";
import { Bell, BellRing, Check, CheckCheck, Inbox, ShieldAlert, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, EmptyState } from "@/components/shared/bits";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/form";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { JsonViewer } from "@/components/shared/bits";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { alerts } from "@/lib/mock";
import type { Alert } from "@/types";
import { cn, timeAgo } from "@/lib/utils";
import { notify } from "@/lib/bridge";

const sevVariant = { critical: "destructive", warning: "warning", info: "info" } as const;

export default function Alerts() {
  const [items, setItems] = React.useState(alerts);
  const [detail, setDetail] = React.useState<Alert | null>(null);
  const [filter, setFilter] = React.useState<"all" | "critical" | "warning" | "info">("all");

  const filtered = items.filter((a) => filter === "all" || a.severity === filter);
  const unread = items.filter((a) => a.status === "unread").length;

  const acknowledge = (id: string) => {
    setItems((prev) => prev.map((a) => (a.id === id ? { ...a, status: "acknowledged" } : a)));
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Monitor"
        title="Alerts"
        description="Everything that went wrong or needs a human. Alerts are written to disk by the engine and pushed to Telegram, Discord or a webhook."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => { setItems((p) => p.map((a) => ({ ...a, status: "acknowledged" }))); toast.success("All alerts acknowledged"); }}>
              <CheckCheck /> Acknowledge all
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Unread" value={unread} tone="danger" icon={<BellRing className="h-4 w-4" />} />
        <StatTile label="Critical" value={items.filter((a) => a.severity === "critical").length} tone="danger" icon={<ShieldAlert className="h-4 w-4" />} />
        <StatTile label="Warning" value={items.filter((a) => a.severity === "warning").length} tone="warning" />
        <StatTile label="Resolved" value={items.filter((a) => a.status === "resolved").length} tone="success" icon={<Check className="h-4 w-4" />} />
      </div>

      <Tabs defaultValue="feed">
        <TabsList>
          <TabsTrigger value="feed">Feed</TabsTrigger>
          <TabsTrigger value="settings">Notifications</TabsTrigger>
        </TabsList>

        <TabsContent value="feed">
          <div className="mb-2 flex items-center gap-1.5">
            {(["all", "critical", "warning", "info"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-md border px-2 py-0.5 text-[11px] capitalize",
                  filter === f ? "border-primary/40 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"
                )}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="space-y-1.5">
            {filtered.map((a) => (
              <div key={a.id} className={cn("panel flex flex-wrap items-center gap-2 px-3 py-2", a.status === "acknowledged" && "opacity-60")}>
                <span className={cn("h-1.5 w-1.5 rounded-full", a.severity === "critical" ? "bg-destructive" : a.severity === "warning" ? "bg-warning" : "bg-info")} />
                <Badge variant={sevVariant[a.severity]}>{a.severity}</Badge>
                <span className="text-[10px] text-muted-foreground">{a.type}</span>
                <span className="min-w-0 flex-1 truncate text-[11.5px]">{a.message}</span>
                <span className="text-[10px] text-muted-foreground">{timeAgo(a.ts)}</span>
                <Button size="sm" variant="ghost" onClick={() => setDetail(a)}>
                  Details
                </Button>
                {a.status === "unread" ? (
                  <Button size="sm" variant="outline" onClick={() => acknowledge(a.id)}>
                    Ack
                  </Button>
                ) : (
                  <Badge variant="muted">{a.status}</Badge>
                )}
              </div>
            ))}
            {filtered.length === 0 && <EmptyState icon={<Inbox className="h-6 w-6" />} title="Nothing here" description="No alerts match this filter." />}
          </div>
        </TabsContent>

        <TabsContent value="settings" className="max-w-2xl">
          <Card>
            <CardContent className="space-y-2 pt-3">
              {[
                ["Desktop notifications", "Native toast when the window is unfocused", true],
                ["Sound", "Play a chime on critical alerts", false],
                ["Telegram", "bot @yf_ops_bot → chat 441238", true],
                ["Discord webhook", "ops#alerts channel", true],
                ["Generic webhook", "https://ops.internal/hooks/yf", false],
              ].map(([title, desc, on]) => (
                <div key={title as string} className="flex items-center justify-between gap-4 rounded-md border border-border/60 p-2.5">
                  <div>
                    <div className="flex items-center gap-1.5 text-[12px]">
                      {title === "Sound" ? <Volume2 className="h-3 w-3" /> : title === "Desktop notifications" ? <Bell className="h-3 w-3" /> : null}
                      {title}
                    </div>
                    <div className="text-[10.5px] text-muted-foreground">{desc}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {title === "Desktop notifications" && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={async () => {
                          const ok = await notify("YFCP", "Desktop notifications are wired to the native shell.");
                          toast[ok ? "success" : "info"](ok ? "Native notification sent" : "Native notifications require the desktop build");
                        }}
                      >
                        Test
                      </Button>
                    )}
                    <Switch checked={on as boolean} onCheckedChange={() => toast.success("Notification preference saved")} />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{detail?.type}</DialogTitle>
            <DialogDescription>{detail ? new Date(detail.ts).toLocaleString() : ""}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <p className="text-[12px]">{detail?.message}</p>
            {detail?.accountEmail && (
              <div className="rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                linked account: <span className="font-mono">{detail.accountEmail}</span>
              </div>
            )}
            <JsonViewer data={detail?.evidence ?? {}} />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDetail(null)}>
              Close
            </Button>
            <Button size="sm" onClick={() => { toast.success("Marked resolved"); setDetail(null); }}>
              Resolve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
