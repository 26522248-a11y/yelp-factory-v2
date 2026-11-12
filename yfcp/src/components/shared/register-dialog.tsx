import * as React from "react";
import { toast } from "sonner";
import { Globe, Plus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ImportDialog, type ParsedAccount } from "@/components/shared/import-dialog";

const METROS = [
  "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
  "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
];

const CITIES_BY_METRO: Record<string, string[]> = {
  "New York": ["New York", "Brooklyn", "Queens", "Bronx", "Manhattan"],
  "Los Angeles": ["Los Angeles", "Santa Monica", "Pasadena", "Burbank"],
  "Chicago": ["Chicago", "Evanston", "Oak Park", "Cicero"],
  "Houston": ["Houston", "Sugar Land", "Katy", "Cypress"],
  "Phoenix": ["Phoenix", "Scottsdale", "Tempe", "Mesa"],
  "Philadelphia": ["Philadelphia", "Camden", "King of Prussia"],
  "San Antonio": ["San Antonio", "New Braunfels", "Schertz"],
  "San Diego": ["San Diego", "Chula Vista", "La Jolla"],
  "Dallas": ["Dallas", "Fort Worth", "Arlington", "Plano"],
  "San Jose": ["San Jose", "Santa Clara", "Sunnyvale", "Cupertino"],
};

const TIMEZONES_BY_METRO: Record<string, string> = {
  "New York": "America/New_York",
  "Los Angeles": "America/Los_Angeles",
  "Chicago": "America/Chicago",
  "Houston": "America/Chicago",
  "Phoenix": "America/Phoenix",
  "Philadelphia": "America/New_York",
  "San Antonio": "America/Chicago",
  "San Diego": "America/Los_Angeles",
  "Dallas": "America/Chicago",
  "San Jose": "America/Los_Angeles",
};

interface RegisterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RegisterDialog({ open, onOpenChange }: RegisterDialogProps) {
  const [tab, setTab] = React.useState("manual");
  const [metro, setMetro] = React.useState("New York");
  const [city, setCity] = React.useState(CITIES_BY_METRO["New York"][0]);
  const [count, setCount] = React.useState("10");
  const [proxyRaw, setProxyRaw] = React.useState("");
  const [emailProvider, setEmailProvider] = React.useState("fakemailo");
  const [captchaKey, setCaptchaKey] = React.useState("");
  const [importOpen, setImportOpen] = React.useState(false);
  const [importedAccounts, setImportedAccounts] = React.useState<ParsedAccount[]>([]);

  React.useEffect(() => {
    if (open) {
      setTab("manual");
      setImportedAccounts([]);
    }
  }, [open]);

  React.useEffect(() => {
    const cities = CITIES_BY_METRO[metro] || [];
    if (!cities.includes(city)) setCity(cities[0] || "");
  }, [metro, city]);

  const handleCreate = () => {
    const n = parseInt(count, 10) || 0;
    if (n <= 0) {
      toast.error("Enter a valid account count");
      return;
    }
    toast.success(`Batch created — ${n} accounts in ${metro}/${city} (signup pipeline)`);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-primary" />
            <DialogTitle>Register New Accounts</DialogTitle>
          </div>
          <DialogDescription>
            Create a signup batch — new accounts will go through the full registration pipeline.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-3">
            <TabsTrigger value="manual">Batch signup</TabsTrigger>
            <TabsTrigger value="import">Import from file</TabsTrigger>
          </TabsList>

          <TabsContent value="manual" className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <Field label="Metro">
                <Select value={metro} onChange={(e) => setMetro(e.target.value)}>
                  {METROS.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </Select>
              </Field>
              <Field label="City">
                <Select value={city} onChange={(e) => setCity(e.target.value)}>
                  {(CITIES_BY_METRO[metro] || []).map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Timezone">
                <Input value={TIMEZONES_BY_METRO[metro] || ""} readOnly className="bg-muted/40" />
              </Field>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <Field label="Count">
                <Input type="number" min={1} max={500} value={count} onChange={(e) => setCount(e.target.value)} />
              </Field>
              <Field label="Email provider">
                <Select value={emailProvider} onChange={(e) => setEmailProvider(e.target.value)}>
                  <option value="fakemailo">Fakemailo</option>
                  <option value="graph">Microsoft Graph</option>
                  <option value="imap">IMAP</option>
                </Select>
              </Field>
              <Field label="Captcha">
                <Input placeholder="Capsolver / 2captcha key" value={captchaKey} onChange={(e) => setCaptchaKey(e.target.value)} />
              </Field>
            </div>

            <Field label="Default proxy (optional)">
              <Input placeholder="pr.oxylabs.io:7777:user:pass" value={proxyRaw} onChange={(e) => setProxyRaw(e.target.value)} />
            </Field>

            <div className="flex items-center gap-4 rounded-md border border-border/60 px-3 py-2">
              <span className="text-[11px] text-muted-foreground">Pipeline</span>
              <div className="flex items-center gap-2">
                <Switch checked onCheckedChange={() => {}} />
                <span className="text-[11px]">Auto-warm P0→P1</span>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked onCheckedChange={() => {}} />
                <span className="text-[11px]">Auto-verify email</span>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={false} onCheckedChange={() => {}} />
                <span className="text-[11px]">Phone verify</span>
              </div>
            </div>

            <div className="flex items-center gap-2 rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-[11px]">
              <Users className="h-4 w-4 text-primary" />
              <span>
                <b>{count}</b> accounts → <b>{city}</b> ({TIMEZONES_BY_METRO[metro]})
              </span>
              <Badge variant="muted" className="ml-auto">
                {importedAccounts.length} imported
              </Badge>
            </div>
          </TabsContent>

          <TabsContent value="import" className="space-y-2">
            <ImportDialog
              open={importOpen}
              onOpenChange={setImportOpen}
              type="accounts"
              onImport={(r) => setImportedAccounts(r as ParsedAccount[])}
            />
            <p className="text-[11px] text-muted-foreground">
              Import accounts from a <code>.txt</code> file. Each line:
            </p>
            <p className="font-mono text-[10.5px] text-muted-foreground">
              email,password,yelp_url,access_email_url
            </p>
            <Button size="sm" onClick={() => setImportOpen(true)}>
              <Plus className="h-4 w-4" />
              {importedAccounts.length > 0 ? `Re-import (${importedAccounts.length} loaded)` : "Choose .txt file"}
            </Button>
            {importedAccounts.length > 0 && (
              <div className="mt-2 space-y-1">
                <div className="text-[11px] font-medium">Preview ({importedAccounts.length} accounts):</div>
                <div className="max-h-40 overflow-auto rounded-md border border-border/60">
                  <table className="w-full text-[10.5px]">
                    <thead className="sticky top-0 bg-muted/80 text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1 text-left">#</th>
                        <th className="px-2 py-1 text-left">Email</th>
                        <th className="px-2 py-1 text-left">Yelp URL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {importedAccounts.slice(0, 15).map((a) => (
                        <tr key={a.index} className="border-t border-border/40 font-mono">
                          <td className="px-2 py-1 text-muted-foreground">{a.index}</td>
                          <td className="px-2 py-1">{a.email}</td>
                          <td className="px-2 py-1 truncate max-w-[200px]">{a.yelpUrl}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {importedAccounts.length > 15 && (
                    <div className="border-t border-border/60 px-2 py-1 text-[10px] text-muted-foreground">
                      …{importedAccounts.length - 15} more
                    </div>
                  )}
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleCreate}>
            <Globe className="h-4 w-4" />
            {tab === "import"
              ? `Create batch with ${importedAccounts.length} imported accounts`
              : `Create batch — ${count} accounts`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
