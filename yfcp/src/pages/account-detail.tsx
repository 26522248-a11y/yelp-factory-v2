import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Ban,
  Camera,
  Check,
  CircleDashed,
  Clock3,
  Fingerprint,
  Play,
  RefreshCcw,
  ShieldCheck,
  UserCog,
} from "lucide-react";
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from "recharts";
import { toast } from "sonner";
import { PageHeader, AccountStateBadge, ModeBadge, TierBadge, Avatar, JsonViewer, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress, Separator } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { accounts, reviews, warmingSessions, assignments, alerts } from "@/lib/mock";
import { cn, timeAgo } from "@/lib/utils";

const SIGNUP_STAGES = [
  "NEW",
  "PROVISIONING",
  "PROXY_BOUND",
  "BROWSER_UP",
  "PREWARMED",
  "FORM_FILLED",
  "CAPTCHA_SOLVED",
  "SUBMITTED",
  "ONBOARDED",
  "EMAIL_PENDING",
  "EMAIL_VERIFIED",
  "PHONE_PENDING",
  "PHONE_VERIFIED",
  "ACTIVE",
];

export default function AccountDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const account = accounts.find((a) => a.id === id) ?? accounts[0];
  const isSignup = SIGNUP_STAGES.includes(account.state);
  const stageIdx = Math.max(0, SIGNUP_STAGES.indexOf(account.state));

  const radar = [
    { component: "age", score: account.trust.age, cap: 15 },
    { component: "profile", score: account.trust.profile, cap: 15 },
    { component: "consistency", score: account.trust.consistency, cap: 12 },
    { component: "diversity", score: account.trust.diversity, cap: 18 },
    { component: "warm", score: account.trust.warm, cap: 30 },
    { component: "content", score: account.trust.content, cap: 20 },
  ];

  const sessionRows = warmingSessions.filter((s) => s.accountEmail === account.email);
  const reviewRows = reviews.filter((r) => r.accountEmail === account.email);
  const dueRows = assignments.filter((a) => a.accountEmail === account.email);
  const accountAlerts = alerts.filter((a) => a.accountEmail === account.email);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Account"
        title={`${account.firstName} ${account.lastName}`}
        description={`${account.email} · ${account.city}, ${account.state_code} · joined ${timeAgo(account.createdAt)}`}
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => navigate("/accounts")}>
              <ArrowLeft /> Back
            </Button>
            <Button variant="outline" size="sm" onClick={() => toast.info("Re-auth flow queued")}>
              <RefreshCcw /> Re-auth
            </Button>
            <Button size="sm" onClick={() => toast.success("Warming session started")}>
              <Play /> Run session
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3">
        <Avatar name={`${account.firstName} ${account.lastName}`} hue={account.avatarHue} size={40} />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <AccountStateBadge state={account.state} />
            <ModeBadge mode={account.mode} />
            <TierBadge tier={account.tier} />
            {account.blacklisted && <Badge variant="destructive">blacklisted</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span>
              <Fingerprint className="mr-1 inline h-3 w-3" />
              {account.gpmProfileId}
            </span>
            <span>proxy {account.proxy}</span>
            <span>tz {account.timezone}</span>
            <span>last active {timeAgo(account.lastActiveAt)}</span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-4 text-right">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Trust</div>
            <div className={cn("text-lg font-semibold", account.trustScore >= 75 ? "text-success" : "text-warning")}>{account.trustScore}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Reviews</div>
            <div className="text-lg font-semibold">{account.reviewsDone}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Sessions 7d</div>
            <div className="text-lg font-semibold">{account.sessions7d}</div>
          </div>
        </div>
      </div>

      {isSignup && (
        <Card>
          <CardHeader>
            <CardTitle>Signup state machine</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1">
              {SIGNUP_STAGES.map((s, i) => (
                <div
                  key={s}
                  className={cn(
                    "flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px]",
                    i < stageIdx && "border-success/30 bg-success/10 text-success",
                    i === stageIdx && "border-primary/40 bg-primary/10 text-primary",
                    i > stageIdx && "border-border text-muted-foreground"
                  )}
                >
                  {i < stageIdx ? <Check className="h-2.5 w-2.5" /> : i === stageIdx ? <CircleDashed className="h-2.5 w-2.5" /> : null}
                  {s}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="warming">Warming</TabsTrigger>
          <TabsTrigger value="reviews">Reviews</TabsTrigger>
          <TabsTrigger value="browser">Browser profile</TabsTrigger>
          <TabsTrigger value="raw">Raw</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="grid gap-3 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Trust breakdown</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <RadarChart data={radar} outerRadius="72%">
                  <PolarGrid stroke="hsl(var(--border))" />
                  <PolarAngleAxis dataKey="component" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                  <PolarRadiusAxis tick={false} axisLine={false} domain={[0, 30]} />
                  <Radar dataKey="score" stroke="hsl(221 83% 60%)" fill="hsl(221 83% 60%)" fillOpacity={0.28} />
                </RadarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <div className="space-y-3">
            <Card>
              <CardHeader>
                <CardTitle>Profile completeness</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Progress value={account.profileComplete} />
                <div className="flex justify-between text-[11px] text-muted-foreground">
                  <span>{account.profileComplete}% filled</span>
                  <span>{account.photos} photos</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Gates</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-[11px]">
                {[
                  ["Trust ≥ 75", account.trustScore >= 75],
                  ["7+ days old", true],
                  ["8+ photos", account.photos >= 8],
                  ["6 sessions / 7d", account.sessions7d >= 6],
                ].map(([label, ok]) => (
                  <div key={label as string} className="flex items-center justify-between">
                    <span className="text-muted-foreground">{label}</span>
                    <Badge variant={ok ? "success" : "muted"}>{ok ? "pass" : "blocked"}</Badge>
                  </div>
                ))}
                {account.cityLockUntil && new Date(account.cityLockUntil) > new Date() && (
                  <div className="rounded-md border border-warning/25 bg-warning/10 p-2 text-warning">
                    City change lock until {new Date(account.cityLockUntil).toLocaleString()}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="timeline">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-0">
                {[
                  { ts: account.lastActiveAt, level: "info", msg: "Warming session completed — 12 actions, trust +4" },
                  { ts: new Date(Date.now() - 5 * 3600_000).toISOString(), level: "info", msg: "Profile avatar uploaded" },
                  { ts: new Date(Date.now() - 26 * 3600_000).toISOString(), level: "warning", msg: "Session skipped — outside working hours" },
                  { ts: new Date(Date.now() - 50 * 3600_000).toISOString(), level: "info", msg: "Review assignment created for Bluebonnet Grill" },
                  { ts: account.createdAt, level: "info", msg: "Account record created" },
                ].map((e, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className={cn("mt-1.5 h-1.5 w-1.5 rounded-full", e.level === "warning" ? "bg-warning" : "bg-info")} />
                      <span className="w-px flex-1 bg-border" />
                    </div>
                    <div className="pb-3">
                      <div className="text-[11px]">{e.msg}</div>
                      <div className="text-[10px] text-muted-foreground">{new Date(e.ts).toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="warming">
          <Card>
            <CardContent className="pt-3">
              <SectionLabel>Warming sessions ({sessionRows.length})</SectionLabel>
              <div className="space-y-1">
                {sessionRows.map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <div>
                      <span className="font-medium">{s.mode}</span>
                      <span className="ml-2 text-muted-foreground">{new Date(s.startedAt).toLocaleString()}</span>
                    </div>
                    <div className="flex items-center gap-3 text-muted-foreground">
                      <span>{s.durationMin}m</span>
                      <span>{s.actions} actions</span>
                      <span className="font-mono text-success">
                        {s.trustBefore} → {s.trustAfter}
                      </span>
                    </div>
                  </div>
                ))}
                {sessionRows.length === 0 && <div className="py-6 text-center text-xs text-muted-foreground">No sessions yet.</div>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reviews">
          <Card>
            <CardContent className="pt-3 space-y-2">
              {reviewRows.map((r) => (
                <div key={r.id} className="rounded-md border border-border/60 p-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-[11px]">
                      <span className="font-medium">{r.businessName}</span>
                      <Badge variant={r.status === "posted" ? "success" : "destructive"}>{r.status}</Badge>
                      <span className="text-warning">{"★".repeat(r.rating)}</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground">{new Date(r.postedAt).toLocaleDateString()}</span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[11px] text-muted-foreground">{r.text}</p>
                </div>
              ))}
              {dueRows.filter((d) => d.status === "pending" || d.status === "assigned").length > 0 && (
                <>
                  <SectionLabel>Upcoming assignments</SectionLabel>
                  {dueRows
                    .filter((d) => d.status === "pending" || d.status === "assigned")
                    .map((d) => (
                      <div key={d.id} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                        <span>{d.clientName}</span>
                        <span className="text-muted-foreground">due {new Date(d.reviewDueAt).toLocaleString()}</span>
                      </div>
                    ))}
                </>
              )}
              {reviewRows.length === 0 && <div className="py-6 text-center text-xs text-muted-foreground">No reviews yet.</div>}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="browser" className="grid gap-3 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>GPM profile</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-[11px]">
              <Row k="Profile ID" v={account.gpmProfileId} mono />
              <Row k="Proxy" v={account.proxy} mono />
              <Row k="Proxy city" v={account.proxyCity} />
              <Row k="Timezone" v={account.timezone} />
              <Row k="Browser" v="Chrome 131 · 1536×864" />
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={() => toast.info("Opening profile in GPM…")}>
                  Open in GPM
                </Button>
                <Button size="sm" variant="ghost" onClick={() => toast.warning("Stop requested")}>
                  Stop profile
                </Button>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Fingerprint</CardTitle>
            </CardHeader>
            <CardContent>
              <JsonViewer
                data={{
                  os_type: "win",
                  browser_type: "chrome",
                  browser_version: "131.0.6778.86",
                  window_size: "1536x864",
                  timezone: account.timezone,
                  webgl_vendor: "Google Inc. (NVIDIA)",
                  canvas_noise: true,
                }}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="raw">
          <Card>
            <CardContent className="pt-3">
              <JsonViewer data={account} className="max-h-[480px]" />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{k}</span>
      <span className={cn("truncate", mono && "font-mono text-[10.5px]")}>{v}</span>
    </div>
  );
}
