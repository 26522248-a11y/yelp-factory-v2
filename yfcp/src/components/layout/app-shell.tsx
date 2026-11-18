import * as React from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronLeft, Minus, RotateCcw, Search, Settings2, Square, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUi } from "@/stores/ui";
import { NAV, NAV_GROUPS } from "./nav";
import { Tooltip } from "@/components/ui/primitives";
import { Kbd } from "@/components/ui/form";
import { CommandPalette } from "./command-palette";
import { StatusBar } from "./status-bar";
import { apiErrorMessage, CONTRACT_VERSION } from "@/lib/bridge";
import { useApiConfig, useApiHealth, useEngineReport, useNodeHeartbeat } from "@/lib/hooks";

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const isMac = typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform);
const paletteShortcut = isMac ? "⌘K" : "Ctrl K";

function isActivePath(routePath: string, currentPath: string): boolean {
  if (routePath === "/") return currentPath === "/";
  // Exact match or starts with routePath + "/" (avoids /accounts matching /accounting)
  if (routePath.includes(":")) return currentPath.startsWith(routePath.split(":")[0]);
  return currentPath === routePath || currentPath.startsWith(routePath + "/");
}

/**
 * Global data-source banner. Two distinct failure modes:
 *  - engine unreachable  → sample data, start `yf serve`;
 *  - engine reachable but /report failed (bad/missing token) → auth/config hint.
 * Per-page "endpoint not wired" badges cover resources the engine does not serve.
 */
function ConnectionBanner() {
  const health = useApiHealth();
  const report = useEngineReport("24h");
  const config = useApiConfig();

  const offline = health.isError;
  const dataFailed = !offline && !!report.error;
  const mismatch =
    !offline &&
    !!health.data &&
    typeof health.data.contract_version === "number" &&
    health.data.contract_version !== CONTRACT_VERSION;
  if (!offline && !dataFailed && !mismatch) return null;

  const title = offline
    ? "Engine offline — showing sample data."
    : dataFailed
    ? "Engine reachable, data requests failed."
    : `Version mismatch: console contract v${CONTRACT_VERSION}, engine v${health.data?.contract_version}.`;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-[11px] text-warning">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
      <span className="font-medium">{title}</span>
      <span className="text-warning/80">
        {offline ? (
          <>
            Start the engine with <code className="rounded bg-warning/15 px-1">yf serve</code>, then retry.
          </>
        ) : dataFailed ? (
          apiErrorMessage(report.error)
        ) : (
          <>Update the console or engine so both speak the same contract.</>
        )}
      </span>
      <span className="font-mono text-[10px] text-warning/60">
        {config.data?.baseUrl}
        {health.data?.host ? ` · ${health.data.host}` : ""}
        {health.data?.version ? ` · v${health.data.version}` : ""}
      </span>
      <button
        onClick={() => {
          void health.refetch();
          void report.refetch();
        }}
        className="ml-auto inline-flex items-center gap-1 rounded border border-warning/40 px-2 py-0.5 hover:bg-warning/15"
      >
        <RotateCcw className="h-3 w-3" /> Retry
      </button>
      <Link to="/config" className="underline underline-offset-2 hover:text-warning/80">
        Connection settings
      </Link>
    </div>
  );
}

function WindowControls() {  if (!isTauri) return null;
  const act = async (fn: "min" | "max" | "close") => {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const w = getCurrentWindow();
    if (fn === "min") await w.minimize();
    if (fn === "max") await w.toggleMaximize();
    if (fn === "close") await w.close();
  };
  return (
    <div className="no-drag flex items-center">
      <button onClick={() => act("min")} className="grid h-7 w-9 place-items-center text-muted-foreground hover:bg-accent hover:text-foreground">
        <Minus className="h-3.5 w-3.5" />
      </button>
      <button onClick={() => act("max")} className="grid h-7 w-9 place-items-center text-muted-foreground hover:bg-accent hover:text-foreground">
        <Square className="h-3 w-3" />
      </button>
      <button onClick={() => act("close")} className="grid h-7 w-9 place-items-center text-muted-foreground hover:bg-destructive hover:text-white">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { sidebarCollapsed, toggleSidebar, setCommandOpen } = useUi();
  const location = useLocation();
  const navigate = useNavigate();
  useNodeHeartbeat();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCommandOpen]);

  const current = NAV.find((n) => isActivePath(n.path, location.pathname));

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      {/* Native titlebar */}
      <div
        className="drag-region flex h-8 shrink-0 items-center justify-between border-b border-border/70 bg-sidebar pl-3"
      >
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <img src="/logo.svg" alt="" className="h-4 w-4 rounded-[5px]" />
          <span className="font-medium tracking-wide">YFCP</span>
          <span className="text-border">/</span>
          <span>{current?.label ?? "Workspace"}</span>
        </div>
        <WindowControls />
      </div>

      <div className="flex min-h-0 flex-1">
        {/* Sidebar */}
        <aside
          className={cn(
            "flex shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200",
            sidebarCollapsed ? "w-[52px]" : "w-[216px]"
          )}
        >
          <div className="flex h-11 items-center gap-2 px-3">
            {!sidebarCollapsed && (
              <Link to="/" className="min-w-0 flex-1">
                <div className="truncate text-[12px] font-semibold tracking-tight">
                  Yelp Factory <span className="text-primary">CP</span>
                </div>
                <div className="text-[10px] text-muted-foreground">operator console</div>
              </Link>
            )}
            <button
              onClick={toggleSidebar}
              className="ml-auto grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
            >
              <ChevronLeft className={cn("h-3.5 w-3.5 transition-transform", sidebarCollapsed && "rotate-180")} />
            </button>
          </div>

          <div className="px-2 pb-2">
            <button
              onClick={() => setCommandOpen(true)}
              className={cn(
                "group flex w-full items-center gap-2 rounded-md border border-sidebar-border bg-background/40 text-[11px] text-muted-foreground transition hover:border-primary/30 hover:text-foreground",
                sidebarCollapsed ? "h-7 justify-center" : "h-7 px-2"
              )}
            >
              <Search className="h-3 w-3" />
              {!sidebarCollapsed && (
                <>
                  <span className="flex-1 text-left">Jump to…</span>
                  <Kbd>{paletteShortcut}</Kbd>
                </>
              )}
            </button>
          </div>

          <nav className="flex-1 space-y-3 overflow-y-auto px-2 pb-3 scrollbar-thin">
            {NAV_GROUPS.map((group) => (
              <div key={group}>
                {!sidebarCollapsed && (
                  <div className="px-2 pb-1 text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/50">
                    {group}
                  </div>
                )}
                <div className="space-y-0.5">
                  {NAV.filter((n) => n.group === group).map((item) => {
                    const active = isActivePath(item.path, location.pathname);
                    const Icon = item.icon;
                    const link = (
                      <NavLink
                        key={item.path}
                        to={item.path}
                        className={cn(
                          "group relative flex h-7 items-center gap-2 rounded-md px-2 text-[12px] transition-colors",
                          active
                            ? "bg-sidebar-accent text-foreground"
                            : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                          sidebarCollapsed && "justify-center px-0"
                        )}
                      >
                        {active && <span className="absolute left-0 top-1/2 h-3.5 w-0.5 -translate-y-1/2 rounded-full bg-primary" />}
                        <Icon className={cn("h-3.5 w-3.5 shrink-0", active ? "text-primary" : "text-muted-foreground")} />
                        {!sidebarCollapsed && <span className="flex-1 truncate">{item.label}</span>}
                        {!sidebarCollapsed && item.badge && (
                          <span className="rounded bg-destructive/15 px-1 text-[10px] font-medium text-destructive">{item.badge}</span>
                        )}
                      </NavLink>
                    );
                    return sidebarCollapsed ? (
                      <Tooltip key={item.path} content={item.label} side="right">
                        {link}
                      </Tooltip>
                    ) : (
                      link
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {!sidebarCollapsed && (
            <div className="border-t border-sidebar-border p-2">
              <button
                onClick={() => navigate("/config")}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[11px] text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
              >
                <Settings2 className="h-3.5 w-3.5" />
                Workspace settings
              </button>
            </div>
          )}
        </aside>

        {/* Main */}
        <div className="flex min-w-0 flex-1 flex-col">
          <main className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <div className="mx-auto w-full max-w-[1500px] px-5 py-4">
              <ConnectionBanner />
              {children}
            </div>
          </main>
          <StatusBar />
        </div>
      </div>

      <CommandPalette />
    </div>
  );
}
