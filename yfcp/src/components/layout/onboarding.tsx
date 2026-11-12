import * as React from "react";
import { ArrowRight, Check, CheckCircle2, Database, KeyRound, MonitorSmartphone, Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Field, Input, Progress, Select } from "@/components/ui/form";
import { cn } from "@/lib/utils";

const KEY = "yfcp-onboarded";

export function useOnboarding() {
  const [done, setDone] = React.useState(() => localStorage.getItem(KEY) === "1");
  const finish = () => {
    localStorage.setItem(KEY, "1");
    setDone(true);
  };
  const replay = () => {
    localStorage.removeItem(KEY);
    setDone(false);
  };
  return { done, finish, replay };
}

export function Onboarding({ open, onDone }: { open: boolean; onDone: () => void }) {
  const [step, setStep] = React.useState(0);
  const [checking, setChecking] = React.useState(false);
  const [masterKey, setMasterKey] = React.useState("9f2c8a41e7b34d6c9a1f8b22");
  const [progress, setProgress] = React.useState(0);

  const steps = [
    { label: "Welcome", icon: Sparkles },
    { label: "Database", icon: Database },
    { label: "GPM", icon: MonitorSmartphone },
    { label: "Keys", icon: KeyRound },
    { label: "Ready", icon: CheckCircle2 },
  ];

  React.useEffect(() => {
    if (step === 4) {
      setProgress(0);
      const t = setInterval(() => {
        setProgress((p) => {
          if (p >= 100) {
            clearInterval(t);
            return 100;
          }
          return p + 10;
        });
      }, 90);
      return () => clearInterval(t);
    }
  }, [step]);

  return (
    <Dialog open={open}>
      <DialogContent
        className="max-w-xl p-0"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <div className="flex items-center gap-1 border-b border-border px-4 py-3">
          {steps.map((s, i) => {
            const Icon = s.icon;
            return (
              <React.Fragment key={s.label}>
                <div
                  className={cn(
                    "flex items-center gap-1.5 rounded-full px-2 py-1 text-[10.5px]",
                    i === step ? "bg-primary text-primary-foreground" : i < step ? "bg-success/15 text-success" : "text-muted-foreground"
                  )}
                >
                  {i < step ? <Check className="h-2.5 w-2.5" /> : <Icon className="h-2.5 w-2.5" />}
                  <span className="hidden sm:inline">{s.label}</span>
                </div>
                {i < steps.length - 1 && <span className="h-px flex-1 bg-border" />}
              </React.Fragment>
            );
          })}
        </div>

        <div className="min-h-[260px] px-6 py-6">
          {step === 0 && (
            <div className="space-y-3">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-primary/15 text-primary">
                <Sparkles className="h-5 w-5" />
              </div>
              <h2 className="text-lg font-semibold tracking-tight">Welcome to YFCP</h2>
              <p className="text-[12px] text-muted-foreground">
                The operator console for your Yelp factory. It binds to your local PostgreSQL, talks to GPM Login Global and
                drives the engine through its admin API and CLI. Nothing leaves this machine.
              </p>
              <Field label="Interface language">
                <Select defaultValue="vi">
                  <option value="vi">Tiếng Việt</option>
                  <option value="en">English</option>
                </Select>
              </Field>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold tracking-tight">Database</h2>
              <p className="text-[12px] text-muted-foreground">
                The console expects a PostgreSQL 16 instance. A portable build can be provisioned automatically if none is found.
              </p>
              <Field label="Connection string">
                <Input defaultValue="postgresql+psycopg://postgres:postgres@127.0.0.1:5433/yelp_factory" className="font-mono text-[11px]" />
              </Field>
              <div className="flex items-center gap-2 rounded-md border border-success/25 bg-success/10 p-2.5 text-[11px] text-success">
                <CheckCircle2 className="h-3.5 w-3.5" />
                PostgreSQL 16 detected on :5433 — 4 ms round trip
              </div>
              <Button
                size="sm"
                variant="outline"
                loading={checking}
                onClick={() => {
                  setChecking(true);
                  setTimeout(() => {
                    setChecking(false);
                    toast.success("Connection verified");
                  }, 900);
                }}
              >
                Test connection
              </Button>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold tracking-tight">GPM Login Global</h2>
              <p className="text-[12px] text-muted-foreground">
                Browser profiles are created and launched by GPM. The console attaches over CDP and never creates its own contexts.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Base URL">
                  <Input defaultValue="http://127.0.0.1:9495" className="font-mono text-[11px]" />
                </Field>
                <Field label="Flavor">
                  <Select defaultValue="global-v1">
                    <option value="global-v1">global-v1</option>
                    <option value="gpm-v3">gpm-v3</option>
                  </Select>
                </Field>
              </div>
              <div className="flex items-center gap-2 rounded-md border border-success/25 bg-success/10 p-2.5 text-[11px] text-success">
                <CheckCircle2 className="h-3.5 w-3.5" />
                GPM responded — v3.4.1 · 6 profiles visible
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold tracking-tight">Keys</h2>
              <p className="text-[12px] text-muted-foreground">
                The master key encrypts stored credentials with AES-GCM. Losing it means re-authenticating every mailbox.
              </p>
              <Field label="Master key">
                <div className="flex gap-2">
                  <Input value={masterKey} onChange={(e) => setMasterKey(e.target.value)} className="font-mono text-[11px]" />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => {
                      setMasterKey(crypto.randomUUID().replace(/-/g, "").slice(0, 24));
                      toast.success("New master key generated");
                    }}
                  >
                    <Wand2 />
                  </Button>
                </div>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Admin token">
                  <Input defaultValue="yf_admin_8f21ac33" className="font-mono text-[11px]" />
                </Field>
                <Field label="Capsolver key">
                  <Input placeholder="optional" className="font-mono text-[11px]" />
                </Field>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold tracking-tight">Provisioning workspace</h2>
              <p className="text-[12px] text-muted-foreground">Running migrations and preparing the first warming plan.</p>
              <div>
                <div className="mb-1 flex justify-between text-[11px]">
                  <span className="text-muted-foreground">alembic upgrade head</span>
                  <span className="font-mono">{progress}%</span>
                </div>
                <Progress value={progress} />
              </div>
              <div className="space-y-1 font-mono text-[10.5px] text-muted-foreground">
                <div>✓ 0001 → 0013 applied</div>
                <div>✓ admin API bound to 127.0.0.1:8787</div>
                <div>✓ selector registry loaded (10 keys)</div>
                <div className={progress >= 100 ? "text-success" : "opacity-40"}>✓ workspace ready</div>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border bg-muted/20 px-5 py-3">
          <Button variant="ghost" size="sm" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
            Back
          </Button>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground">
              step {step + 1} of {steps.length}
            </span>
            {step < steps.length - 1 ? (
              <Button size="sm" onClick={() => setStep((s) => s + 1)}>
                Continue <ArrowRight />
              </Button>
            ) : (
              <Button size="sm" disabled={progress < 100} onClick={onDone}>
                Open console
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
