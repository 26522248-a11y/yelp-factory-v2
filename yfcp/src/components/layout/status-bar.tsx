import { Activity, Cpu, Database, HardDrive, MonitorSmartphone, Moon, Sun, Wifi } from "lucide-react";
import { useUi } from "@/stores/ui";
import { cn } from "@/lib/utils";
import { Tooltip } from "@/components/ui/primitives";
import { isTauri } from "@/lib/bridge";
import { useApiConfig, useApiHealth } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

function Item({
  ok,
  icon,
  label,
  detail,
}: {
  ok: boolean;
  icon: React.ReactNode;
  label: string;
  detail?: string;
}) {
  return (
    <Tooltip content={detail ?? label}>
      <div className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
        <span className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-success animate-pulse-dot" : "bg-destructive")} />
        <span className="text-muted-foreground/70">{icon}</span>
        <span className="hidden lg:inline">{label}</span>
      </div>
    </Tooltip>
  );
}

export function StatusBar() {
  const { theme, toggleTheme } = useUi();
  const health = useApiHealth();
  const config = useApiConfig();
  const apiOk = !!health.data && !health.isError;
  const dbOk = apiOk && (health.data?.db ?? false);

  return (
    <footer className="flex h-6 shrink-0 items-center gap-4 border-t border-border bg-sidebar px-3">
      <Item ok={dbOk} icon={<Database className="h-3 w-3" />} label="PG" detail={dbOk ? "PostgreSQL — 127.0.0.1:5433" : "PostgreSQL unreachable (detected via admin API)"} />
      <Item ok={apiOk} icon={<MonitorSmartphone className="h-3 w-3" />} label="GPM" detail={apiOk ? `GPM — ${health.data?.gpm_transport ?? "127.0.0.1:9495"}` : "GPM transport unknown — engine offline"} />
      <Item
        ok={apiOk}
        icon={<Wifi className="h-3 w-3" />}
        label="API"
        detail={
          apiOk
            ? `Admin API — ${config.data?.baseUrl ?? "127.0.0.1:8787"} · v${health.data?.version ?? "?"} · schema ${health.data?.schema_revision ?? "?"}`
            : "Admin API offline — showing sample data"
        }
      />
      <Item
        ok={apiOk}
        icon={<Activity className="h-3 w-3" />}
        label={`${health.data?.active_profiles ?? 0} active`}
        detail={`${health.data?.active_profiles ?? 0} browser profiles running`}
      />

      <div className="ml-auto flex items-center gap-4">
        {apiOk && (
          <span className="hidden font-mono text-[10px] text-muted-foreground/70 lg:inline">
            synced {health.dataUpdatedAt ? timeAgo(new Date(health.dataUpdatedAt)) : "now"}
          </span>
        )}
        <Item ok icon={<Cpu className="h-3 w-3" />} label="CPU 38%" detail="Intel Xeon Gold 6133 — 38% across 4 vCPU" />
        <Item ok icon={<HardDrive className="h-3 w-3" />} label="RAM 61%" detail="2.44 GB of 4.00 GB used — governor healthy" />
        <span className="font-mono text-[10px] text-muted-foreground/70">worker 3/5</span>
        <span className="hidden font-mono text-[10px] text-muted-foreground/70 lg:inline">
          {isTauri ? "desktop · v0.1.0" : "web preview"}
        </span>
        <button
          onClick={toggleTheme}
          className="grid h-4 w-4 place-items-center rounded text-muted-foreground hover:text-foreground"
          title="Toggle theme"
        >
          {theme === "dark" ? <Sun className="h-3 w-3" /> : <Moon className="h-3 w-3" />}
        </button>
      </div>
    </footer>
  );
}
