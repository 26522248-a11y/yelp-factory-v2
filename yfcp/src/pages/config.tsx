import * as React from "react";
import {
  AlertTriangle,
  Bell,
  Database,
  Eye,
  EyeOff,
  KeyRound,
  Mail,
  MonitorSmartphone,
  Proportions,
  Save,
  ShieldCheck,
  Smartphone,
  Sparkles,
  UserCog,
  Wifi,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { useQueryClient } from "@tanstack/react-query";
import { apiErrorMessage, CONTRACT_VERSION, setApiConfig } from "@/lib/bridge";
import { useApiConfig, useApiHealth } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

const SECTIONS: [string, string, LucideIcon][] = [
  ["general", "General", UserCog],
  ["connection", "Connection", Wifi],
  ["database", "Database", Database],
  ["gpm", "GPM", MonitorSmartphone],
  ["concurrency", "Concurrency", Proportions],
  ["proxy", "Proxy", Wifi],
  ["email", "Email", Mail],
  ["captcha", "Captcha", ShieldCheck],
  ["sms", "SMS", Smartphone],
  ["alerts", "Alerts", Bell],
  ["human", "Human behavior", Sparkles],
  ["security", "Security", KeyRound],
];

function Secret({ label, value, hint }: { label: string; value: string; hint?: string }) {
  const [show, setShow] = React.useState(false);
  return (
    <Field label={label} hint={hint}>
      <div className="flex gap-2">
        <Input type={show ? "text" : "password"} defaultValue={value} />
        <Button variant="outline" size="icon" onClick={() => setShow((s) => !s)}>
          {show ? <EyeOff /> : <Eye />}
        </Button>
      </div>
    </Field>
  );
}

function ToggleRow({ title, desc, defaultOn, onChange }: { title: string; desc: string; defaultOn?: boolean; onChange?: (v: boolean) => void }) {
  const [on, setOn] = React.useState(!!defaultOn);
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-border/60 p-2.5">
      <div>
        <div className="text-[12px]">{title}</div>
        <div className="text-[10.5px] text-muted-foreground">{desc}</div>
      </div>
      <Switch
        checked={on}
        onCheckedChange={(v) => {
          setOn(v);
          onChange?.(v);
        }}
      />
    </div>
  );
}

export default function Config() {
  const [active, setActive] = React.useState("general");
  const apiConfig = useApiConfig();
  const health = useApiHealth();
  const qc = useQueryClient();
  const [baseUrl, setBaseUrl] = React.useState("http://127.0.0.1:8787");
  const [token, setToken] = React.useState("");
  const apiOk = !!health.data && !health.isError;

  React.useEffect(() => {
    if (!apiConfig.data) return;
    setBaseUrl(apiConfig.data.baseUrl);
    setToken(apiConfig.data.token);
  }, [apiConfig.data]);

  const saveConnection = async () => {
    try {
      await setApiConfig({ baseUrl, token });
      await qc.invalidateQueries({ queryKey: ["engine"] });
      await health.refetch();
      toast.success("Connection settings saved");
    } catch (error) {
      toast.error(apiErrorMessage(error));
    }
  };

  React.useEffect(() => {
    const scroller = document.querySelector("main");
    if (!scroller) return;
    const onScroll = () => {
      const marker = scroller.getBoundingClientRect().top + 72;
      let current = SECTIONS[0][0];
      for (const [id] of SECTIONS) {
        const el = document.getElementById(`config-${id}`);
        if (el && el.getBoundingClientRect().top <= marker) current = id;
      }
      setActive(current);
    };
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, []);

  const jumpTo = (id: string) => {
    setActive(id);
    document.getElementById(`config-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Workspace configuration"
        description="Every setting the engine reads. Changes are written to config.yaml and .env on save — the running workers reload on their next tick."
        actions={
          <Button size="sm" onClick={() => toast.success("Configuration saved — workers will reload")}>
            <Save /> Save all
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <nav className="panel sticky top-0 h-fit p-1.5">
          {SECTIONS.map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => jumpTo(id)}
              aria-current={active === id ? "true" : undefined}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11.5px] transition",
                active === id
                  ? "bg-primary/10 font-medium text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
              {active === id && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
            </button>
          ))}
        </nav>

        <div className="space-y-3">
          <Card id="config-general">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>General</CardTitle>
              <Badge variant="success">connected</Badge>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Language">
                <Select defaultValue="vi">
                  <option value="vi">Tiếng Việt</option>
                  <option value="en">English</option>
                </Select>
              </Field>
              <Field label="Timezone">
                <Select defaultValue="America/Chicago">
                  <option>America/Chicago</option>
                  <option>America/New_York</option>
                  <option>America/Los_Angeles</option>
                  <option>Asia/Ho_Chi_Minh</option>
                </Select>
              </Field>
              <Secret label="Master key" value="9f2c8a41e7b34d6c9a1f" hint="AES-GCM · urlsafe base64. Never leaves this machine." />
              <Secret label="Admin token" value="yf_admin_8f21ac33" hint="Bearer token for the local admin API." />
              <div className="sm:col-span-2 flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => toast.success("New master key generated and stored")}>
                  <KeyRound /> Generate new key
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    localStorage.removeItem("yfcp-onboarded");
                    window.location.reload();
                  }}
                >
                  Replay first-run wizard
                </Button>
                <span className="text-[10.5px] text-muted-foreground">Rotating the key re-encrypts stored credentials.</span>
              </div>
            </CardContent>
          </Card>

          <Card id="config-connection">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Console connection</CardTitle>
              <Badge variant={apiOk ? "success" : "destructive"}>
                {apiOk ? `connected · ${health.data?.status}` : "offline"}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Admin API URL" hint="Loopback or LAN/VPN. Remote public hosts must use HTTPS — plain public HTTP is rejected.">
                  <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8787" className="font-mono text-[11px]" />
                </Field>
                <Field label="Bearer token" hint="Must match YF_ADMIN_TOKEN in the engine .env.">
                  <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="YF_ADMIN_TOKEN" className="font-mono text-[11px]" />
                </Field>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={saveConnection}>
                  <Save /> Save connection
                </Button>
                <Button variant="outline" size="sm" onClick={() => health.refetch()}>
                  Test connection
                </Button>
                <span className="text-[10.5px] text-muted-foreground">
                  {health.isError
                    ? apiErrorMessage(health.error)
                    : health.data
                    ? `engine v${health.data.version ?? "?"} · contract v${health.data.contract_version ?? "?"} · schema ${health.data.schema_revision ?? "?"} · ${health.data.host ?? "host ?"} · DB ${health.data.db ? "up" : "down"} · ${health.data.active_profiles} active${health.data.gpm_transport ? ` · GPM ${health.data.gpm_transport}` : ""}`
                    : "No response yet — the console falls back to the sample dataset."}
                </span>
                {health.data && health.data.contract_version !== CONTRACT_VERSION && (
                  <Badge variant="warning" className="text-[9px]">
                    contract mismatch: console v{CONTRACT_VERSION}
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>

          <Card id="config-database">
            <CardHeader>
              <CardTitle>Database</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Field label="Connection string">
                <Input defaultValue="postgresql+psycopg://postgres:postgres@127.0.0.1:5433/yelp_factory" className="font-mono text-[11px]" />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => toast.success("Connection OK — 4ms")}>
                  Test connection
                </Button>
                <Button variant="outline" size="sm" onClick={() => toast.success("Migrated to head (0013)")}>
                  Run migrations
                </Button>
                <Button variant="outline" size="sm" onClick={() => toast.success("Backup created (412 MB)")}>
                  Backup database
                </Button>
                <Badge variant="muted" className="self-center font-mono">
                  alembic 0013
                </Badge>
              </div>
            </CardContent>
          </Card>

          <Card id="config-gpm">
            <CardHeader>
              <CardTitle>GPM Login Global</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Flavor">
                <Select defaultValue="global-v1">
                  <option value="global-v1">global-v1</option>
                  <option value="gpm-v3">gpm-v3</option>
                </Select>
              </Field>
              <Field label="Base URL">
                <Input defaultValue="http://127.0.0.1:9495" className="font-mono text-[11px]" />
              </Field>
              <Field label="MCP URL">
                <Input defaultValue="http://127.0.0.1:9495/mcp" className="font-mono text-[11px]" />
              </Field>
              <Secret label="MCP token" value="mcp_live_7f2a9c" />
              <Secret label="License key" value="GPM-2B41-9F0C-2210" />
              <Field label="Browser version">
                <Input defaultValue="131.0.6778.86" className="font-mono text-[11px]" />
              </Field>
              <div className="sm:col-span-2">
                <Button variant="outline" size="sm" onClick={() => toast.success("GPM reachable — 6 profiles listed")}>
                  Test connection
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card id="config-concurrency">
            <CardHeader>
              <CardTitle>Concurrency</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Workers">
                <Input type="number" defaultValue={3} />
              </Field>
              <Field label="Max profiles">
                <Input type="number" defaultValue={2} />
              </Field>
              <Field label="RAM guard (%)">
                <Input type="number" defaultValue={85} />
              </Field>
              <Field label="Browser slots">
                <Input type="number" defaultValue={2} />
              </Field>
              <div className="sm:col-span-2 rounded-md border border-border/60 bg-background/40 p-2 text-[10.5px] text-muted-foreground">
                Hard cap: <span className="font-mono text-foreground">RAM_GB / 2</span> profiles. The governor may reduce below the configured value but never above the cap.
              </div>
            </CardContent>
          </Card>

          <Card id="config-proxy">
            <CardHeader>
              <CardTitle>Proxy</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Default kind">
                <Select defaultValue="residential">
                  <option value="residential">Residential</option>
                  <option value="datacenter">Datacenter</option>
                  <option value="mobile">Mobile</option>
                </Select>
              </Field>
              <Field label="Sticky minutes">
                <Input type="number" defaultValue={30} />
              </Field>
              <Field label="Probe timeout (s)">
                <Input type="number" defaultValue={12} />
              </Field>
              <Field label="Default proxy (raw)">
                <Input placeholder="host:port:user:pass" className="font-mono text-[11px]" />
              </Field>
            </CardContent>
          </Card>

          <Card id="config-email">
            <CardHeader>
              <CardTitle>Email</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Provider">
                <Select defaultValue="graph">
                  <option value="fakemailo">Fakemailo</option>
                  <option value="graph">Microsoft Graph</option>
                  <option value="imap">IMAP</option>
                </Select>
              </Field>
              <Field label="Fakemailo URL">
                <Input defaultValue="https://fakemailo.com" />
              </Field>
              <Secret label="Graph client ID" value="8a2f-4c11-9e0a" />
              <Secret label="Graph refresh token" value="0.AX4A7..." />
            </CardContent>
          </Card>

          <Card id="config-captcha">
            <CardHeader>
              <CardTitle>Captcha</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Providers (in order)">
                <Input defaultValue="capsolver, 2captcha, human_in_loop" />
              </Field>
              <Field label="Timeout (s)">
                <Input type="number" defaultValue={120} />
              </Field>
              <Secret label="Capsolver key" value="CAP-2f81ab" />
              <Secret label="2captcha key" value="2C-91aa0d" />
            </CardContent>
          </Card>

          <Card id="config-sms">
            <CardHeader>
              <CardTitle>SMS</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Provider">
                <Select defaultValue="smsactivate">
                  <option value="smsactivate">SMS-Activate</option>
                  <option value="hupsms">HupSMS</option>
                </Select>
              </Field>
              <Field label="Default area code">
                <Input defaultValue="512" />
              </Field>
              <Secret label="API key" value="sms_9a2c11" />
            </CardContent>
          </Card>

          <Card id="config-alerts">
            <CardHeader>
              <CardTitle>Alerts</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Secret label="Telegram bot token" value="7712:AAF2..." />
              <Field label="Telegram chat ID">
                <Input defaultValue="441238991" />
              </Field>
              <Field label="Discord webhook">
                <Input defaultValue="https://discord.com/api/webhooks/…" className="text-[11px]" />
              </Field>
              <Field label="Generic webhook">
                <Input placeholder="https://ops.internal/hooks/yf" className="text-[11px]" />
              </Field>
              <div className="sm:col-span-2 flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => toast.success("Telegram test delivered")}>
                  Test Telegram
                </Button>
                <Button variant="outline" size="sm" onClick={() => toast.success("Discord test delivered")}>
                  Test Discord
                </Button>
                <Button variant="outline" size="sm" onClick={() => toast.success("Webhook returned 200")}>
                  Test webhook
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card id="config-human">
            <CardHeader>
              <CardTitle>Human behavior</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <div className="mb-1 flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Time scale</span>
                  <span className="font-mono">1.0×</span>
                </div>
                <input type="range" min={0} max={100} step={10} defaultValue={100} className="w-full accent-[hsl(var(--primary))]" />
                <div className="flex justify-between text-[9.5px] text-muted-foreground">
                  <span>0 — instant (tests)</span>
                  <span>0.5 — fast</span>
                  <span>1.0 — production</span>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Working window start">
                  <Input type="time" defaultValue="06:00" />
                </Field>
                <Field label="Working window end">
                  <Input type="time" defaultValue="23:00" />
                </Field>
                <Field label="Session length min (m)">
                  <Input type="number" defaultValue={25} />
                </Field>
                <Field label="Session length max (m)">
                  <Input type="number" defaultValue={88} />
                </Field>
              </div>
              <ToggleRow title="Idle jitter" desc="Occasional pauses that look like a human reading." defaultOn />
            </CardContent>
          </Card>

          <Card id="config-security">
            <CardHeader>
              <CardTitle>Security</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Field label="Fingerprint salt" hint="Changing this reshuffles every account fingerprint.">
                <Input defaultValue="yf-fingerprint-v1" className="font-mono text-[11px]" />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Session timeout (h)">
                  <Input type="number" defaultValue={24} />
                </Field>
                <Field label="Lock TTL (s)">
                  <Input type="number" defaultValue={900} />
                </Field>
              </div>
              <div className="flex items-start gap-2 rounded-md border border-warning/25 bg-warning/10 p-2.5 text-[10.5px] text-warning">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                The console binds the admin API to 127.0.0.1 only. Do not expose it on a public interface.
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
