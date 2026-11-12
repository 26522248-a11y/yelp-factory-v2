import * as React from "react";
import { CheckCircle2, CircleAlert, FileUp, Flame, Eye, ListChecks, Plus, Search, Sparkles, Upload } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, SectionLabel, ModeBadge, AccountStateBadge } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox, Field, Input, Select, Switch } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const preview = [
  { profile: "gpm-2214", email: "marcus.reed41@outlook.com", proxy: "res.proxy-44.net:8412", valid: true, reason: "profile found" },
  { profile: "gpm-2215", email: "nina.patel88@hotmail.com", proxy: "res.proxy-51.net:8103", valid: true, reason: "profile found" },
  { profile: "gpm-2216", email: "owen.doyle7@live.com", proxy: "—", valid: false, reason: "proxy missing" },
  { profile: "gpm-2217", email: "sofia.novak9@outlook.com", proxy: "mobile.mx-12.net:9001", valid: true, reason: "profile found" },
  { profile: "gpm-2218", email: "daniel.fischer22@outlook.com", proxy: "res.proxy-77.net:8322", valid: false, reason: "proxy failed probe" },
];

export default function Adopt() {
  const [step, setStep] = React.useState(0);
  const [mode, setMode] = React.useState<"post_review" | "full_warm" | "view_only">("post_review");
  const [autoDetect, setAutoDetect] = React.useState(true);
  const [probing, setProbing] = React.useState(false);
  const [bulkBusy, setBulkBusy] = React.useState(false);

  const steps = ["Account", "Proxy", "Mode"];
  const validCount = preview.filter((p) => p.valid).length;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Onboarding"
        title="Adopt accounts"
        description="Bring in identities that already exist in GPM. We bind the profile, attach a proxy and start the chosen nurture cadence — without touching the original fingerprint."
        actions={
          <Button variant="outline" size="sm" onClick={() => toast.success("Template downloaded")}>
            <FileUp /> Template
          </Button>
        }
      />

      <Tabs defaultValue="single">
        <TabsList>
          <TabsTrigger value="single">Single account</TabsTrigger>
          <TabsTrigger value="bulk">Bulk import</TabsTrigger>
          <TabsTrigger value="list">Adopted accounts</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="single" className="grid gap-3 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Adoption wizard</CardTitle>
              <div className="flex items-center gap-1">
                {steps.map((s, i) => (
                  <div key={s} className="flex items-center gap-1">
                    <div
                      className={`flex h-5 items-center gap-1 rounded-full px-2 text-[10px] ${
                        i === step ? "bg-primary text-primary-foreground" : i < step ? "bg-success/15 text-success" : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      {i < step ? <CheckCircle2 className="h-2.5 w-2.5" /> : <span>{i + 1}</span>}
                      {s}
                    </div>
                    {i < steps.length - 1 && <span className="h-px w-3 bg-border" />}
                  </div>
                ))}
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {step === 0 && (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="GPM profile ID" hint="Must already exist in GPM Login Global">
                      <div className="flex gap-2">
                        <Input placeholder="gpm-2214" />
                        <Button variant="outline" size="icon" onClick={() => toast.info("Scanning GPM API…")}>
                          <Search />
                        </Button>
                      </div>
                    </Field>
                    <Field label="Email">
                      <Input placeholder="account@outlook.com" />
                    </Field>
                    <Field label="Password (optional)" hint="Only needed if the session expires">
                      <Input type="password" placeholder="••••••••" />
                    </Field>
                    <Field label="Yelp user ID (optional)">
                      <Input placeholder="auto-probe" />
                    </Field>
                    <Field label="First name">
                      <Input placeholder="Marcus" />
                    </Field>
                    <Field label="Last name">
                      <Input placeholder="Reed" />
                    </Field>
                  </div>
                  <div className="flex items-center gap-3 rounded-md border border-border/60 bg-background/40 p-2.5">
                    <Switch checked={autoDetect} onCheckedChange={setAutoDetect} />
                    <div className="text-[11px]">
                      Auto-detect profile info from GPM
                      <div className="text-[10px] text-muted-foreground">Email, fingerprint, window size and browser version are read from the profile.</div>
                    </div>
                  </div>
                </>
              )}

              {step === 1 && (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Proxy source">
                      <Select defaultValue="pool">
                        <option value="pool">Pick from proxy pool</option>
                        <option value="manual">Enter manually</option>
                        <option value="none">No proxy (local IP)</option>
                      </Select>
                    </Field>
                    <Field label="Proxy">
                      <Select defaultValue="res.proxy-44.net:8412">
                        <option>res.proxy-44.net:8412 — Austin, TX · 92ms</option>
                        <option>res.proxy-51.net:8103 — Dallas, TX · 118ms</option>
                        <option>mobile.mx-12.net:9001 — Phoenix, AZ · 210ms</option>
                      </Select>
                    </Field>
                  </div>
                  <div className="rounded-md border border-border/60 bg-background/40 p-3">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">Resolved egress</span>
                      <Button size="sm" variant="outline" loading={probing} onClick={() => { setProbing(true); setTimeout(() => { setProbing(false); toast.success("Proxy OK — 92ms, AS22773"); }, 900); }}>
                        Probe proxy
                      </Button>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                      <KV k="IP" v="73.44.19.208" />
                      <KV k="City" v="Austin, TX" />
                      <KV k="ASN" v="AS22773" />
                      <KV k="Latency" v="92 ms" />
                    </div>
                  </div>
                  <div className="rounded-md border border-primary/20 bg-primary/5 p-2.5 text-[11px] text-primary">
                    Fingerprint stays untouched — the proxy is applied at the GPM profile boundary, not by injecting a new context.
                  </div>
                </>
              )}

              {step === 2 && (
                <>
                  <SectionLabel>Nurture mode</SectionLabel>
                  <div className="grid gap-2 sm:grid-cols-3">
                    {[
                      { id: "post_review", icon: Flame, title: "Post-review warm", desc: "P0→P4 ladder, no review until trust gate is open." },
                      { id: "full_warm", icon: Sparkles, title: "Full warm", desc: "Search, browse, vote, save — reviews when eligible." },
                      { id: "view_only", icon: Eye, title: "View only", desc: "Track the account, never run automated sessions." },
                    ].map((m) => {
                      const Icon = m.icon;
                      return (
                        <button
                          key={m.id}
                          onClick={() => setMode(m.id as never)}
                          className={`rounded-lg border p-2.5 text-left transition ${
                            mode === m.id ? "border-primary/50 bg-primary/5" : "border-border hover:bg-accent/40"
                          }`}
                        >
                          <Icon className={`h-4 w-4 ${mode === m.id ? "text-primary" : "text-muted-foreground"}`} />
                          <div className="mt-1.5 text-[12px] font-medium">{m.title}</div>
                          <div className="text-[10.5px] text-muted-foreground">{m.desc}</div>
                        </button>
                      );
                    })}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Bind to client (optional)">
                      <Select defaultValue="later">
                        <option value="later">Assign later</option>
                        <option>Bluebonnet Grill</option>
                        <option>Copper Kettle BBQ</option>
                        <option>Saguaro Auto Care</option>
                      </Select>
                    </Field>
                    <Field label="Batch">
                      <Select defaultValue="bat_002">
                        <option value="bat_002">Adopted Phoenix Set</option>
                        <option value="bat_new">Create new batch…</option>
                      </Select>
                    </Field>
                  </div>
                  <div className="flex items-start gap-2 rounded-md border border-warning/25 bg-warning/10 p-2.5 text-[11px] text-warning">
                    <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    I confirm this GPM profile already exists and holds a valid Yelp session.
                  </div>
                </>
              )}

              <div className="flex items-center justify-between border-t border-border pt-3">
                <Button variant="ghost" size="sm" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
                  Back
                </Button>
                {step < 2 ? (
                  <Button size="sm" onClick={() => setStep((s) => s + 1)}>
                    Continue
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => {
                      toast.success("Account adopted — warming plan created");
                      setStep(0);
                    }}
                  >
                    <Plus /> Adopt & start
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>What happens on adopt</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5 text-[11px] text-muted-foreground">
              {[
                ["Account row", "Created in READY or WARMING depending on session state."],
                ["Profile bind", "Existing GPM profile is linked — no new fingerprint generated."],
                ["Proxy reserve", "Proxy is probed, reserved and pinned to the account."],
                ["Warming plan", "A plan is generated for the selected mode and metro timezone."],
                ["First task", "Queued inside the local working window (06:00–23:00)."],
              ].map(([title, desc]) => (
                <div key={title} className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                  <div>
                    <div className="text-[11px] font-medium text-foreground">{title}</div>
                    <div>{desc}</div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="bulk" className="space-y-3">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Bulk import</CardTitle>
              <Badge variant="muted">CSV · JSON · TXT</Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border py-8">
                <Upload className="h-5 w-5 text-muted-foreground" />
                <div className="text-[12px]">Drop a file or browse</div>
                <div className="text-[10.5px] text-muted-foreground">gpm_profile_id, email, password, proxy, city, mode</div>
                <Button size="sm" variant="outline" onClick={() => toast.info("File picker would open here")}>
                  Choose file
                </Button>
              </div>

              <div className="panel overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Profile</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Proxy</TableHead>
                      <TableHead>Validation</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.map((p) => (
                      <TableRow key={p.profile}>
                        <TableCell className="font-mono text-[11px]">{p.profile}</TableCell>
                        <TableCell className="text-[11px]">{p.email}</TableCell>
                        <TableCell className="font-mono text-[10.5px] text-muted-foreground">{p.proxy}</TableCell>
                        <TableCell>
                          <Badge variant={p.valid ? "success" : "destructive"}>
                            {p.valid ? <CheckCircle2 className="h-2.5 w-2.5" /> : <CircleAlert className="h-2.5 w-2.5" />}
                            {p.reason}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <div className="flex items-center justify-between">
                <div className="text-[11px] text-muted-foreground">
                  {validCount} valid · {preview.length - validCount} invalid
                </div>
                <div className="flex items-center gap-2">
                  <Select className="h-7 w-40 text-xs" defaultValue="post_review">
                    <option value="post_review">Default: Post-review</option>
                    <option value="full_warm">Default: Full warm</option>
                    <option value="view_only">Default: View only</option>
                  </Select>
                  <Button
                    size="sm"
                    loading={bulkBusy}
                    onClick={() => {
                      setBulkBusy(true);
                      setTimeout(() => {
                        setBulkBusy(false);
                        toast.success(`Adopted ${validCount} accounts`);
                      }, 1400);
                    }}
                  >
                    <ListChecks /> Import {validCount}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="list">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-1">
                {["marcus.reed41@outlook.com", "nina.patel88@hotmail.com", "sofia.novak9@outlook.com"].map((email) => (
                  <div key={email} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5">
                    <div className="flex items-center gap-2 text-[11px]">
                      <span>{email}</span>
                      <ModeBadge mode="post_review" />
                    </div>
                    <div className="flex items-center gap-2">
                      <AccountStateBadge state="WARMING" />
                      <span className="text-[10px] text-muted-foreground">gpm-2214</span>
                      <Button size="sm" variant="ghost" onClick={() => toast.info("Re-detecting profile…")}>
                        Re-detect
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="settings" className="max-w-2xl">
          <Card>
            <CardContent className="space-y-4 pt-3">
              <Field label="Default mode for new adoptions">
                <Select defaultValue="post_review">
                  <option value="post_review">Post-review warm</option>
                  <option value="full_warm">Full warm</option>
                </Select>
              </Field>
              <RowSwitch title="Auto-probe proxy on adopt" desc="Validate geo, ASN and latency before binding." defaultOn />
              <RowSwitch title="Auto-detect profile from GPM" desc="Pull email, fingerprint and browser version from the profile." defaultOn />
              <RowSwitch title="Skip validation (dangerous)" desc="Only for trusted supplier batches. Disables duplicate and probe checks." />
              <Button size="sm" onClick={() => toast.success("Adopt settings saved")}>
                Save
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className="truncate font-mono text-[11px]">{v}</div>
    </div>
  );
}

function RowSwitch({ title, desc, defaultOn }: { title: string; desc: string; defaultOn?: boolean }) {  const [on, setOn] = React.useState(!!defaultOn);
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border border-border/60 p-2.5">
      <div>
        <div className="text-[12px]">{title}</div>
        <div className="text-[10.5px] text-muted-foreground">{desc}</div>
      </div>
      <Switch checked={on} onCheckedChange={setOn} />
    </div>
  );
}
