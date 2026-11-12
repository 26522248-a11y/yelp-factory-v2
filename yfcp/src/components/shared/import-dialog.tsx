import * as React from "react";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2, FileText, Upload, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export type ParsedAccount = {
  email: string;
  password: string;
  yelpUrl: string;
  accessEmailUrl: string;
  raw: string;
  index: number;
};

export type ParsedProxy = {
  host: string;
  port: string;
  username: string;
  password: string;
  raw: string;
  index: number;
};

type ImportType = "accounts" | "proxies";

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  type: ImportType;
  onImport?: (result: (ParsedAccount | ParsedProxy)[]) => void;
}

export function ImportDialog({ open, onOpenChange, type, onImport }: ImportDialogProps) {
  const [rawText, setRawText] = React.useState("");
  const [parsed, setParsed] = React.useState<(ParsedAccount | ParsedProxy)[]>([]);
  const [errors, setErrors] = React.useState<string[]>([]);
  const [fileLoaded, setFileLoaded] = React.useState("");

  const isAccount = type === "accounts";
  const title = isAccount ? "Import Accounts" : "Import Proxies";
  const format = isAccount
    ? "email,password,yelp_url,access_email_url"
    : "host:port:user:pass";

  React.useEffect(() => {
    if (open) {
      setRawText("");
      setParsed([]);
      setErrors([]);
      setFileLoaded("");
    }
  }, [open]);

  const parseText = React.useCallback(
    (text: string) => {
      const lines = text
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("#"));

      const items: (ParsedAccount | ParsedProxy)[] = [];
      const errs: string[] = [];

      lines.forEach((line, i) => {
        if (isAccount) {
          const parts = line.split(",");
          if (parts.length < 4) {
            errs.push(`Line ${i + 1}: need 4 fields (email,password,yelp_url,access_url) — got ${parts.length}`);
          } else {
            const [email, password, yelpUrl, accessEmailUrl] = parts.map((p) => p.trim());
            if (!email.includes("@") || !email.includes(".")) {
              errs.push(`Line ${i + 1}: invalid email "${email}"`);
            } else {
              items.push({ email, password, yelpUrl, accessEmailUrl, raw: line, index: i + 1 });
            }
          }
        } else {
          const parts = line.split(":");
          if (parts.length < 4) {
            errs.push(`Line ${i + 1}: need 4 fields (host:port:user:pass) — got ${parts.length}`);
          } else {
            const [host, port, username, password] = parts.map((p) => p.trim());
            if (!host || !port || isNaN(Number(port))) {
              errs.push(`Line ${i + 1}: invalid host:port "${host}:${port}"`);
            } else {
              items.push({ host, port, username, password, raw: line, index: i + 1 });
            }
          }
        }
      });

      setParsed(items);
      setErrors(errs);
    },
    [isAccount]
  );

  const handleFileSelect = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setFileLoaded(file.name);
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result as string;
        setRawText(text);
        parseText(text);
      };
      reader.readAsText(file);
    },
    [parseText]
  );

  const handleImport = () => {
    if (parsed.length === 0) {
      toast.error("No valid rows to import");
      return;
    }
    onImport?.(parsed);
    toast.success(`${parsed.length} ${isAccount ? "accounts" : "proxies"} ready for processing`);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-primary" />
            <DialogTitle>{title}</DialogTitle>
          </div>
          <DialogDescription>
            Paste lines or load a <code className="text-[11px]">.txt</code> file. Each line = one record.
            <br />
            <span className="font-mono text-[10.5px] text-muted-foreground">Format: {format}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* File picker */}
          <div className="flex items-center gap-2">
            <input type="file" id="import-file" accept=".txt,.csv" className="hidden" onChange={handleFileSelect} />
            <Button variant="outline" size="sm" onClick={() => document.getElementById("import-file")?.click()}>
              <FileText className="h-4 w-4" />
              {fileLoaded || "Choose .txt file"}
            </Button>
            {fileLoaded && (
              <span className="text-[11px] text-muted-foreground">
                Loaded <b>{fileLoaded}</b> — parsed below
              </span>
            )}
          </div>

          {/* Text area */}
          <textarea
            className="h-36 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-[11px] text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            placeholder={`Paste lines here, e.g.:\n${format}`}
            value={rawText}
            onChange={(e) => {
              setRawText(e.target.value);
              setFileLoaded("pasted");
              parseText(e.target.value);
            }}
          />

          {/* Summary */}
          {rawText && (
            <div className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-[11px]">
              <span className="text-muted-foreground">
                Lines: <b className="text-foreground">{rawText.split(/\r?\n/).filter((l) => l.trim() && !l.trim().startsWith("#")).length}</b>
              </span>
              <span
                className={cn(
                  "flex items-center gap-1",
                  errors.length > 0 ? "text-warning" : "text-success"
                )}
              >
                {errors.length > 0 ? (
                  <AlertCircle className="h-3.5 w-3.5" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                )}
                Valid: <b>{parsed.length}</b>
              </span>
              {errors.length > 0 && (
                <span className="text-warning">
                  Errors: <b>{errors.length}</b>
                </span>
              )}
            </div>
          )}

          {/* Error list */}
          {errors.length > 0 && (
            <div className="max-h-28 overflow-auto rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
              {errors.slice(0, 10).map((err, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[10.5px] text-destructive">
                  <X className="mt-0.5 h-3 w-3 shrink-0" />
                  {err}
                </div>
              ))}
              {errors.length > 10 && (
                <div className="mt-1 text-[10px] text-muted-foreground">
                  …and {errors.length - 10} more errors
                </div>
              )}
            </div>
          )}

          {/* Preview table */}
          {parsed.length > 0 && (
            <div className="rounded-md border border-border/60">
              <div className="max-h-44 overflow-auto">
                <table className="w-full text-[10.5px]">
                  <thead className="sticky top-0 bg-muted/80 text-muted-foreground">
                    <tr>
                      <th className="px-2 py-1 text-left font-medium">#</th>
                      {isAccount ? (
                        <>
                          <th className="px-2 py-1 text-left font-medium">Email</th>
                          <th className="px-2 py-1 text-left font-medium">Password</th>
                          <th className="px-2 py-1 text-left font-medium">Yelp URL</th>
                        </>
                      ) : (
                        <>
                          <th className="px-2 py-1 text-left font-medium">Host</th>
                          <th className="px-2 py-1 text-left font-medium">Port</th>
                          <th className="px-2 py-1 text-left font-medium">User</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.slice(0, 20).map((item) => (
                      <tr key={item.index} className="border-t border-border/40 font-mono">
                        <td className="px-2 py-1 text-muted-foreground">{item.index}</td>
                        {isAccount ? (
                          <>
                            <td className="px-2 py-1">{(item as ParsedAccount).email}</td>
                            <td className="px-2 py-1">{"•".repeat((item as ParsedAccount).password.length)}</td>
                            <td className="px-2 py-1 truncate max-w-[200px]">{(item as ParsedAccount).yelpUrl}</td>
                          </>
                        ) : (
                          <>
                            <td className="px-2 py-1">{(item as ParsedProxy).host}</td>
                            <td className="px-2 py-1">{(item as ParsedProxy).port}</td>
                            <td className="px-2 py-1">{(item as ParsedProxy).username}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {parsed.length > 20 && (
                <div className="border-t border-border/60 px-2 py-1 text-[10px] text-muted-foreground">
                  Showing 20 of {parsed.length} rows
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleImport} disabled={parsed.length === 0}>
            <Upload className="h-4 w-4" />
            Import {parsed.length} {isAccount ? "accounts" : "proxies"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
