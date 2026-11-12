import * as React from "react";
import { DonutChart } from "@tremor/react";
import { KeyRound, LockKeyhole, MailCheck, RefreshCcw, ShieldAlert, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, SectionLabel, StatTile, EmptyState } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { accounts } from "@/lib/mock";
import { timeAgo, cn } from "@/lib/utils";

const challenges = [
  { name: "Email link", value: 62 },
  { name: "Password", value: 21 },
  { name: "Captcha", value: 11 },
  { name: "Arkose", value: 6 },
];

const history = [
  { email: "marcus.reed41@outlook.com", outcome: "logged_in", challenge: "email link", ts: 1, dur: "48s" },
  { email: "nina.patel88@hotmail.com", outcome: "logged_in", challenge: "password", ts: 3, dur: "22s" },
  { email: "owen.doyle7@live.com", outcome: "bad_credentials", challenge: "password", ts: 5, dur: "61s" },
  { email: "sofia.novak9@outlook.com", outcome: "logged_in", challenge: "captcha", ts: 8, dur: "134s" },
  { email: "daniel.fischer22@outlook.com", outcome: "silent_fail", challenge: "email link", ts: 11, dur: "180s" },
  { email: "amelia.hart12@outlook.com", outcome: "logged_in", challenge: "email link", ts: 14, dur: "39s" },
];

export default function LoginReauth() {
  const [busy, setBusy] = React.useState<string | null>(null);
  const suspects = accounts.filter((a) => a.state === "COOLDOWN" || a.state === "NEEDS_MANUAL").slice(0, 6);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operate"
        title="Login & re-authentication"
        description="Session health across the farm. Trigger a manual login, bulk re-auth expired sessions, and track which challenge Yelp is serving."
        actions={
          <Button
            size="sm"
            onClick={() => {
              toast.success("Bulk re-auth queued for 6 accounts");
            }}
          >
            <RefreshCcw /> Re-auth suspects
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Sessions healthy" value={42} hint="66% of farm" tone="success" icon={<ShieldAlert className="h-4 w-4" />} />
        <StatTile label="Needs re-auth" value={suspects.length} hint="expired or challenged" tone="warning" icon={<KeyRound className="h-4 w-4" />} />
        <StatTile label="Email links" value="62%" hint="dominant challenge" tone="info" icon={<MailCheck className="h-4 w-4" />} />
        <StatTile label="Avg login" value="48s" hint="link → confirmed" />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Challenge mix — last 30 days</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-6">
            <DonutChart data={challenges} index="name" category="value" colors={["indigo", "sky", "amber", "rose"]} className="h-44 w-44" showLabel={false} />
            <div className="flex-1 space-y-2">
              {challenges.map((c, i) => (
                <div key={c.name} className="flex items-center gap-2 text-[11px]">
                  <span className={cn("h-1.5 w-1.5 rounded-full", ["bg-indigo-500", "bg-sky-500", "bg-amber-500", "bg-rose-500"][i])} />
                  <span className="flex-1 text-muted-foreground">{c.name}</span>
                  <span className="font-mono">{c.value}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Manual login</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2.5">
            <select className="h-8 w-full rounded-md border border-input bg-background/60 px-2 text-[12px]">
              {accounts.slice(0, 10).map((a) => (
                <option key={a.id}>{a.email}</option>
              ))}
            </select>
            <Button className="w-full" size="sm" loading={busy === "manual"} onClick={() => { setBusy("manual"); setTimeout(() => { setBusy(null); toast.success("Logged in — S7 owner verified"); }, 1600); }}>
              <LockKeyhole /> Run S1–S7
            </Button>
            <p className="text-[10.5px] text-muted-foreground">
              The flow pollutes nothing: it attaches over CDP, preserves cookies, and stops on a challenge instead of forcing it.
            </p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="suspects">
        <TabsList>
          <TabsTrigger value="suspects">Suspects</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="suspects">
          <Card>
            <CardContent className="space-y-1.5 pt-3">
              {suspects.map((a) => (
                <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5">
                  <span className="text-[11px]">{a.email}</span>
                  <Badge variant="warning">{a.state}</Badge>
                  <span className="text-[10px] text-muted-foreground">last activity {timeAgo(a.lastActiveAt)}</span>
                  <div className="ml-auto flex items-center gap-1.5">
                    <Button size="sm" variant="outline" loading={busy === a.id} onClick={() => { setBusy(a.id); setTimeout(() => { setBusy(null); toast.success(`Re-authenticated ${a.email}`); }, 1200); }}>
                      Re-auth
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => toast.info("Marked for manual review")}>
                      Flag
                    </Button>
                  </div>
                </div>
              ))}
              {suspects.length === 0 && <EmptyState title="No suspects" description="Every session looks fresh." />}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardContent className="pt-3">
              <SectionLabel>Login outcomes</SectionLabel>
              <div className="space-y-1">
                {history.map((h, i) => (
                  <div key={i} className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <span className="flex-1 truncate">{h.email}</span>
                    <Badge variant={h.outcome === "logged_in" ? "success" : h.outcome === "bad_credentials" ? "destructive" : "warning"}>{h.outcome}</Badge>
                    <span className="w-24 text-muted-foreground">{h.challenge}</span>
                    <span className="w-10 text-right font-mono text-muted-foreground">{h.dur}</span>
                    <span className="w-20 text-right text-muted-foreground">{h.ts}h ago</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="settings" className="max-w-2xl">
          <Card>
            <CardContent className="space-y-3 pt-3">
              {[
                ["Max password attempts", "3"],
                ["Bad credential retries", "2"],
                ["Email link timeout (s)", "180"],
                ["Auto re-auth on expiry", "enabled"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-2">
                  <span className="text-[12px]">{k}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{v}</span>
                </div>
              ))}
              <Button size="sm" onClick={() => toast.success("Login settings saved")}>
                Save
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
