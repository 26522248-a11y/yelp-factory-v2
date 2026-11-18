import * as React from "react";
import { MonitorCog, RefreshCcw, Server, Users, Wifi, WifiOff } from "lucide-react";
import { PageHeader, StatTile, EmptyState, SourceBadge } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useApiHealth, useEngineReport, useNodes } from "@/lib/hooks";
import { cn, timeAgo } from "@/lib/utils";

const ROLE_TONE = {
  console: "info",
  worker: "success",
  engine: "warning",
} as const;

export default function Nodes() {
  const health = useApiHealth();
  const report = useEngineReport("24h");
  const nodes = useNodes();

  const items = nodes.data?.items ?? [];
  const online = nodes.data?.online ?? 0;
  const total = nodes.data?.total ?? 0;
  const workers = items.filter((node) => node.role === "worker").length;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Machines"
        description="Every console and worker registered with this engine. Heartbeat every 30s; a machine is marked offline after 2 minutes without one."
        actions={
          <>
            <SourceBadge source={nodes.data ? "live" : "mock"} />
            <Button variant="outline" size="sm" onClick={() => void nodes.refetch()}>
              <RefreshCcw /> Refresh
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Machines online"
          value={`${online} / ${total}`}
          hint={total ? `${workers} worker${workers === 1 ? "" : "s"}` : "no heartbeats yet"}
          tone={online > 0 ? "success" : "warning"}
          icon={<Wifi className="h-4 w-4" />}
        />
        <StatTile
          label="Engine"
          value={health.data?.host ?? "—"}
          hint={health.data ? `v${health.data.version ?? "?"} · ${health.data.contract_version ? `contract v${health.data.contract_version}` : ""}` : "offline"}
          tone={health.data ? "info" : "danger"}
          icon={<Server className="h-4 w-4" />}
        />
        <StatTile
          label="Accounts"
          value={Object.values(report.data?.accounts ?? {}).reduce((sum, n) => sum + n, 0)}
          hint="shared across machines"
          icon={<Users className="h-4 w-4" />}
        />
        <StatTile
          label="Queue depth"
          value={report.data?.queue_depth ?? 0}
          hint="pending runs"
          tone={report.data?.queue_depth ? "warning" : "success"}
          icon={<MonitorCog className="h-4 w-4" />}
        />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Deployment</CardTitle>
            <p className="text-[11px] text-muted-foreground">
              Each console registers itself when it connects to this engine. Worker rows appear when a worker heartbeat is added.
            </p>
          </div>
          {nodes.error && <Badge variant="destructive">{nodes.error}</Badge>}
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <EmptyState
              icon={<WifiOff className="h-6 w-6" />}
              title="No machines registered"
              description={nodes.error ?? "Connect a console to the engine and it will appear here within 30 seconds."}
            />
          ) : (
            <div className="overflow-hidden rounded-md border border-border/60">
              <table className="w-full text-[11px]">
                <thead className="bg-muted/50 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Machine</th>
                    <th className="px-3 py-2 text-left font-medium">Role</th>
                    <th className="px-3 py-2 text-left font-medium">Version</th>
                    <th className="px-3 py-2 text-right font-medium">Slots</th>
                    <th className="px-3 py-2 text-right font-medium">Running</th>
                    <th className="px-3 py-2 text-right font-medium">Done 24h</th>
                    <th className="px-3 py-2 text-left font-medium">Status</th>
                    <th className="px-3 py-2 text-right font-medium">Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((node) => (
                    <tr key={node.id} className="border-t border-border/40 hover:bg-accent/20">
                      <td className="px-3 py-2">
                        <div className="font-medium">{node.name}</div>
                        <div className="font-mono text-[10px] text-muted-foreground">{node.hostname || node.id}</div>
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant={ROLE_TONE[node.role] ?? "muted"}>{node.role}</Badge>
                      </td>
                      <td className="px-3 py-2 font-mono text-[10.5px] text-muted-foreground">{node.version ?? "—"}</td>
                      <td className="px-3 py-2 text-right font-mono">{node.slots || "—"}</td>
                      <td className="px-3 py-2 text-right font-mono text-info">{node.progress.running || "—"}</td>
                      <td className="px-3 py-2 text-right font-mono text-success">{node.progress.done || "—"}</td>
                      <td className="px-3 py-2">
                        <span className={cn("inline-flex items-center gap-1.5", node.online ? "text-success" : "text-muted-foreground")}>
                          <span className={cn("h-1.5 w-1.5 rounded-full", node.online ? "bg-success animate-pulse-dot" : "bg-destructive")} />
                          {node.status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-[10.5px] text-muted-foreground">
                        {node.last_seen ? timeAgo(node.last_seen) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
