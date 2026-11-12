import { Activity, Cpu, Database, HardDrive, MonitorSmartphone, Moon, Sun, Wifi } from "lucide-react";
import { useUi } from "@/stores/ui";
import { cn } from "@/lib/utils";
import { Tooltip } from "@/components/ui/primitives";
import { isTauri } from "@/lib/bridge";

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
  return (
    <footer className="flex h-6 shrink-0 items-center gap-4 border-t border-border bg-sidebar px-3">
      <Item ok icon={<Database className="h-3 w-3" />} label="PG" detail="PostgreSQL — 127.0.0.1:5433 (4ms)" />
      <Item ok icon={<MonitorSmartphone className="h-3 w-3" />} label="GPM" detail="GPM Login Global — :9495 (v3.4.1)" />
      <Item ok icon={<Wifi className="h-3 w-3" />} label="API" detail="Admin API — 127.0.0.1:8787" />
      <Item ok={false} icon={<Activity className="h-3 w-3" />} label="2/2 slots" detail="Browser slots saturated — 2 of 2 in use" />

      <div className="ml-auto flex items-center gap-4">
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
