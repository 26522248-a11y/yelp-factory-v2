import * as React from "react";
import { Archive, Database, Download, FileJson, FileSpreadsheet, FileUp, HardDriveDownload, Upload } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox, Field, Input, Select, Switch } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { ImportDialog } from "@/components/shared/import-dialog";
import type { LucideIcon } from "lucide-react";

const exportTargets = ["Accounts", "Reviews", "Batches", "Trust scores", "Audit results", "Pool health", "Velocity data"];

const IMPORT_TARGETS: [string, string, LucideIcon][] = [
  ["Clients", "CSV · business name, metro, category, facts", FileSpreadsheet],
  ["Proxies", "CSV/TXT · host:port:user:pass", FileUp],
  ["Emails", "CSV/TXT · mailbox, password, provider", FileUp],
  ["SMS numbers", "CSV · e164, provider", FileUp],
  ["Accounts (adopt)", "CSV · gpm_profile_id, email, proxy", FileJson],
  ["Flags bundle", "JSON · key/value pairs", FileJson],
];

export default function Data() {
  const [selected, setSelected] = React.useState<string[]>(["Accounts", "Reviews"]);
  const [scheduled, setScheduled] = React.useState(true);
  const [importOpen, setImportOpen] = React.useState(false);
  const [importTarget, setImportTarget] = React.useState<"accounts" | "proxies">("accounts");
  const [lastImport, setLastImport] = React.useState<{ name: string; count: number } | null>(null);

  const handleImportClick = (name: string) => {
    if (name === "Proxies") setImportTarget("proxies");
    else if (name === "Accounts (adopt)") setImportTarget("accounts");
    else {
      toast.info(`${name} — use the Accounts or Proxies importer for TXT files`);
      return;
    }
    setImportOpen(true);
  };

  const handleImport = (result: unknown[]) => {
    setLastImport({ name: importTarget === "proxies" ? "Proxies" : "Accounts", count: result.length });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Data management"
        description="One place for every export, import and backup. Files land in the workspace export folder and keep a full operation log."
        actions={
          <Button variant="outline" size="sm" onClick={() => toast.success("Full database backup started")}>
            <Archive /> Back up now
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Exports this week" value={14} tone="info" icon={<Download className="h-4 w-4" />} />
        <StatTile label="Imports this week" value={6} icon={<Upload className="h-4 w-4" />} />
        <StatTile label="DB size" value="412 MB" hint="postgres 16" icon={<Database className="h-4 w-4" />} />
        <StatTile label="Last backup" value="3h ago" hint="scheduled daily" tone="success" icon={<HardDriveDownload className="h-4 w-4" />} />
      </div>

      <Tabs defaultValue="export">
        <TabsList>
          <TabsTrigger value="export">Export</TabsTrigger>
          <TabsTrigger value="import">Import</TabsTrigger>
          <TabsTrigger value="backup">Backup</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="export" className="grid gap-3 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Build an export</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <SectionLabel>Datasets</SectionLabel>
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {exportTargets.map((t) => (
                  <label key={t} className="flex cursor-pointer items-center gap-2 rounded-md border border-border/60 px-2 py-1.5 text-[11px] hover:bg-accent/30">
                    <Checkbox checked={selected.includes(t)} onCheckedChange={(v) => setSelected((p) => (v ? [...p, t] : p.filter((x) => x !== t)))} />
                    {t}
                  </label>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Field label="Format">
                  <Select defaultValue="csv">
                    <option value="csv">CSV</option>
                    <option value="json">JSON</option>
                    <option value="pdf">PDF</option>
                  </Select>
                </Field>
                <Field label="From">
                  <Input type="date" />
                </Field>
                <Field label="To">
                  <Input type="date" />
                </Field>
              </div>
              <Button size="sm" onClick={() => toast.success(`Export queued — ${selected.length} datasets`)}>
                <Download /> Export {selected.length} datasets
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Scheduled exports</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5">
              <div className="flex items-center justify-between rounded-md border border-border/60 p-2">
                <div>
                  <div className="text-[11px]">Weekly digest</div>
                  <div className="text-[10px] text-muted-foreground">Mondays 08:00 → Telegram</div>
                </div>
                <Switch checked={scheduled} onCheckedChange={setScheduled} />
              </div>
              <div className="flex items-center justify-between rounded-md border border-border/60 p-2">
                <div>
                  <div className="text-[11px]">Monthly board pack</div>
                  <div className="text-[10px] text-muted-foreground">1st 09:00 → PDF email</div>
                </div>
                <Switch checked onCheckedChange={() => toast.success("Preference saved")} />
              </div>
              <div className="rounded-md border border-border/60 p-2 text-[10.5px] text-muted-foreground">
                Exports are written to <span className="font-mono text-foreground">data/exports/</span> and never leave the machine unless you configure a webhook.
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="import" className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {IMPORT_TARGETS.map(([name, hint, Icon]) => (
            <Card key={name} className="transition hover:border-primary/30">
              <CardContent className="flex items-start gap-3 py-3">
                <span className="grid h-8 w-8 place-items-center rounded-md bg-primary/10 text-primary">
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-medium">{name}</div>
                  <div className="text-[10.5px] text-muted-foreground">{hint}</div>
                  <Button size="sm" variant="outline" className="mt-2" onClick={() => handleImportClick(name)}>
                    Choose file
                  </Button>
                  {lastImport?.name === name && (
                    <Badge variant="success" className="mt-1.5 text-[9px]">
                      {lastImport.count} loaded
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
          <ImportDialog open={importOpen} onOpenChange={setImportOpen} type={importTarget} onImport={handleImport} />
        </TabsContent>

        <TabsContent value="backup">
          <Card>
            <CardContent className="space-y-3 pt-3">
              <div className="flex items-center justify-between rounded-md border border-border/60 p-2.5">
                <div>
                  <div className="text-[12px]">Daily automatic backup</div>
                  <div className="text-[10.5px] text-muted-foreground">02:00 local · keep 14 days</div>
                </div>
                <Switch checked onCheckedChange={() => toast.success("Backup schedule updated")} />
              </div>
              <SectionLabel>Recent backups</SectionLabel>
              {[
                ["yf_2026-11-11_0200.dump", "412 MB", "9h ago"],
                ["yf_2026-11-10_0200.dump", "408 MB", "1d ago"],
                ["yf_2026-11-09_0200.dump", "401 MB", "2d ago"],
              ].map(([file, size, when]) => (
                <div key={file} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                  <span className="min-w-0 flex-1 truncate font-mono text-[10.5px]">{file}</span>
                  <span className="text-muted-foreground">{size}</span>
                  <span className="w-16 text-right text-[10px] text-muted-foreground">{when}</span>
                  <Button size="sm" variant="ghost" onClick={() => toast.warning("Restore requires typed confirmation")}>
                    Restore
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-1">
                {[
                  ["Accounts export", "CSV", "64 rows", "18m ago", "success"],
                  ["Adopt import", "CSV", "5 rows · 2 failed", "1h ago", "warning"],
                  ["Backup", "dump", "412 MB", "9h ago", "success"],
                  ["Proxy import", "TXT", "24 rows", "1d ago", "success"],
                ].map(([op, fmt, rows, when, status]) => (
                  <div key={op as string} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <span className="min-w-0 flex-1 truncate">{op}</span>
                    <Badge variant="muted">{fmt}</Badge>
                    <span className="text-muted-foreground">{rows}</span>
                    <span className="w-16 text-right text-[10px] text-muted-foreground">{when}</span>
                    <Badge variant={status === "success" ? "success" : "warning"}>{status}</Badge>
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
