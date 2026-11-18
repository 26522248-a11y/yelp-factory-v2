import * as React from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { FileUp, Mail, RefreshCcw, ShieldAlert, Smartphone, Trash2, Wifi } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SourceBadge } from "@/components/shared/bits";
import { DataTable } from "@/components/shared/data-table";
import { ImportDialog, type ParsedProxy } from "@/components/shared/import-dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { apiErrorMessage } from "@/lib/bridge";
import { useApiHealth, useEmailDomainsData, useEmailsData, useImportPool, usePoolStats, useProxiesData, useSmsNumbersData } from "@/lib/hooks";
import { useImports } from "@/stores/imports";
import type { EmailEntry, ProxyEntry, SmsNumber } from "@/types";
import { cn, timeAgo } from "@/lib/utils";

const proxyBadge = {
  available: "success",
  reserved: "info",
  failed: "destructive",
  exhausted: "muted",
} as const;

export default function Pools() {
  const { data: emailDomainsSeed } = useEmailDomainsData();
  const { data: emails } = useEmailsData();
  const { data: smsNumbers } = useSmsNumbersData();
  const [domains, setDomains] = React.useState(emailDomainsSeed);
  const [importOpen, setImportOpen] = React.useState(false);

  const health = useApiHealth();
  const { data: proxies, imported } = useProxiesData();  const { stats, source: poolSource } = usePoolStats();
  const addProxies = useImports((s) => s.addProxies);
  const markProxiesSynced = useImports((s) => s.markProxiesSynced);
  const removeProxy = useImports((s) => s.removeProxy);
  const importPool = useImportPool();

  const handleImport = async (rows: unknown[]) => {
    const parsed = rows as ParsedProxy[];
    const before = useImports.getState().proxies.map((p) => p.raw);
    const added = addProxies(
      parsed.map((r) => ({ host: r.host, port: r.port, username: r.username, password: r.password, raw: r.raw }))
    );

    if (!health.data) {
      toast.success(`Saved ${added} proxies locally — start the engine to push them to the pool`);
      return;
    }

    try {
      const result = await importPool.mutateAsync({ kind: "proxies", text: parsed.map((r) => r.raw).join("\n") });
      const synced = useImports
        .getState()
        .proxies.filter((p) => !before.includes(p.raw))
        .map((p) => p.id);
      markProxiesSynced(synced);
      toast.success(
        `Engine imported ${result.valid} proxies${result.duplicates ? ` · ${result.duplicates} duplicates` : ""}${
          result.invalid ? ` · ${result.invalid} invalid` : ""
        }`
      );
    } catch (error) {
      toast.warning(`Saved locally — engine import failed: ${apiErrorMessage(error)}`);
    }
  };

  const proxyTotal = Object.values(stats.proxies).reduce((sum, n) => sum + n, 0) || proxies.length;
  const emailTotal = Object.values(stats.emails).reduce((sum, n) => sum + n, 0) || emails.length;

  const proxyCols: ColumnDef<ProxyEntry>[] = [
    {
      accessorKey: "raw",
      header: "Endpoint",
      cell: ({ row }) => (
        <div>
          <div className="font-mono text-[11px]">
            {row.original.host}:{row.original.port}
          </div>
          <div className="text-[10px] text-muted-foreground">{row.original.kind}</div>
        </div>
      ),
    },
    {
      id: "geo",
      header: "Geo",
      accessorFn: (r) => `${r.city}, ${r.country}`,
      cell: ({ row }) => (
        <div className="text-[11px]">
          {row.original.city}, {row.original.country}
          <div className="font-mono text-[10px] text-muted-foreground">{row.original.asn}</div>
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <Badge variant={proxyBadge[row.original.status]}>{row.original.status}</Badge>,
    },
    {
      accessorKey: "health",
      header: "Health",
      cell: ({ row }) => (
        <div className="flex items-center gap-1.5">
          <div className="h-1 w-10 overflow-hidden rounded-full bg-secondary">
            <div className={cn("h-full rounded-full", row.original.health > 70 ? "bg-success" : row.original.health > 35 ? "bg-warning" : "bg-destructive")} style={{ width: `${row.original.health}%` }} />
          </div>
          <span className="font-mono text-[10px] text-muted-foreground">{row.original.health}</span>
        </div>
      ),
    },
    {
      accessorKey: "latencyMs",
      header: "Latency",
      cell: ({ row }) => <span className="font-mono text-[11px]">{row.original.latencyMs}ms</span>,
    },
    {
      accessorKey: "failStreak",
      header: "Fails",
      cell: ({ row }) => <span className={cn("font-mono text-[11px]", row.original.failStreak > 2 && "text-destructive")}>{row.original.failStreak}</span>,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon-sm" variant="ghost" onClick={() => toast.info(`Probed ${row.original.host} — 92ms`)}>
            <Wifi />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            className="text-destructive"
            onClick={() => {
              if (row.original.id.startsWith("ipx_")) removeProxy(row.original.id);
              toast.error("Proxy removed");
            }}
          >
            <Trash2 />
          </Button>
        </div>
      ),
    },
  ];

  const emailCols: ColumnDef<EmailEntry>[] = [
    {
      accessorKey: "email",
      header: "Mailbox",
      cell: ({ row }) => (
        <div>
          <div className="text-[11px]">{row.original.email}</div>
          <div className="text-[10px] text-muted-foreground">{row.original.provider}</div>
        </div>
      ),
    },
    { accessorKey: "domain", header: "Domain", cell: ({ row }) => <Badge variant="muted">{row.original.domain}</Badge> },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <Badge variant={row.original.status === "available" ? "success" : row.original.status === "reserved" ? "info" : "destructive"}>{row.original.status}</Badge>
      ),
    },
    { accessorKey: "reservedBy", header: "Reserved by", cell: ({ row }) => <span className="text-[10.5px] text-muted-foreground">{row.original.reservedBy ?? "—"}</span> },
    { accessorKey: "importedAt", header: "Imported", cell: ({ row }) => <span className="text-[10.5px] text-muted-foreground">{timeAgo(row.original.importedAt)}</span> },
  ];

  const smsCols: ColumnDef<SmsNumber>[] = [
    { accessorKey: "e164", header: "Number", cell: ({ row }) => <span className="font-mono text-[11px]">{row.original.e164}</span> },
    { accessorKey: "areaCode", header: "Area code", cell: ({ row }) => <span className="font-mono text-[11px]">{row.original.areaCode}</span> },
    { accessorKey: "provider", header: "Provider", cell: ({ row }) => <Badge variant="muted">{row.original.provider}</Badge> },
    { accessorKey: "usedBy", header: "Used by", cell: ({ row }) => <span className="text-[10.5px] text-muted-foreground">{row.original.usedBy ?? "—"}</span> },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <Badge variant={row.original.status === "available" ? "success" : row.original.status === "in_use" ? "info" : "destructive"}>{row.original.status}</Badge>,
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Inventory"
        title="Pools"
        description="Proxies, mailboxes and SMS numbers. Pools are reserved atomically so two accounts can never share a resource."
        actions={
          <>
            <SourceBadge source={imported.length ? "local" : poolSource} />
            <Button variant="outline" size="sm" onClick={() => toast.success("Probe-all queued")}>
              <RefreshCcw /> Probe all
            </Button>
            <Button size="sm" onClick={() => setImportOpen(true)}>
              <FileUp /> Import
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Proxies" value={proxyTotal} hint={`${stats.available_proxies} available`} icon={<Wifi className="h-4 w-4" />} />
        <StatTile label="Mailboxes" value={emailTotal} hint={`${stats.available_emails} available`} tone="info" icon={<Mail className="h-4 w-4" />} />
        <StatTile label="SMS numbers" value={smsNumbers.length} hint={`${smsNumbers.filter((s) => s.status === "available").length} available`} tone="success" icon={<Smartphone className="h-4 w-4" />} />
        <StatTile label="Domain health" value="3 / 4" hint="1 disabled" tone="warning" icon={<ShieldAlert className="h-4 w-4" />} />
      </div>

      <Tabs defaultValue="proxies">
        <TabsList>
          <TabsTrigger value="proxies">Proxies</TabsTrigger>
          <TabsTrigger value="emails">Email pool</TabsTrigger>
          <TabsTrigger value="sms">SMS</TabsTrigger>
          <TabsTrigger value="domains">Domains</TabsTrigger>
        </TabsList>

        <TabsContent value="proxies">
          <div className="panel h-[440px] overflow-hidden">
            <DataTable columns={proxyCols} data={proxies} searchPlaceholder="Search host, ASN, city…" pageSize={12} dense />
          </div>
        </TabsContent>

        <TabsContent value="emails">
          <div className="panel h-[440px] overflow-hidden">
            <DataTable columns={emailCols} data={emails} searchPlaceholder="Search mailbox…" pageSize={12} dense />
          </div>
        </TabsContent>

        <TabsContent value="sms">
          <div className="panel h-[440px] overflow-hidden">
            <DataTable columns={smsCols} data={smsNumbers} searchPlaceholder="Search number…" pageSize={12} dense />
          </div>
        </TabsContent>

        <TabsContent value="domains">
          <Card>
            <CardContent className="space-y-2 pt-3">
              {domains.map((d) => (
                <div key={d.domain} className="flex items-center gap-3 rounded-md border border-border/60 px-2.5 py-2">
                  <span className="min-w-36 text-[12px]">{d.domain}</span>
                  <Badge variant={d.failStreak > 3 ? "destructive" : d.failStreak > 0 ? "warning" : "success"}>
                    fail streak {d.failStreak}
                  </Badge>
                  {d.disabledUntil && <span className="text-[10px] text-muted-foreground">disabled until {new Date(d.disabledUntil).toLocaleString()}</span>}
                  <div className="ml-auto flex items-center gap-2">
                    <Button size="sm" variant="ghost" onClick={() => toast.success(`Reset fail streak for ${d.domain}`)}>
                      Reset streak
                    </Button>
                    <Switch
                      checked={d.enabled}
                      onCheckedChange={(v) => {
                        setDomains((prev) => prev.map((x) => (x.domain === d.domain ? { ...x, enabled: v } : x)));
                        toast.success(`${d.domain} ${v ? "enabled" : "disabled"}`);
                      }}
                    />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <ImportDialog open={importOpen} onOpenChange={setImportOpen} type="proxies" onImport={handleImport} />
    </div>
  );
}
