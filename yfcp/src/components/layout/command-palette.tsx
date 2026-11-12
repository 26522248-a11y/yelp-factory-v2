import * as React from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Search } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useUi } from "@/stores/ui";
import { NAV } from "./nav";
import { cn } from "@/lib/utils";
import { Kbd } from "@/components/ui/form";

export function CommandPalette() {
  const { commandOpen, setCommandOpen } = useUi();
  const navigate = useNavigate();
  const [q, setQ] = React.useState("");
  const [idx, setIdx] = React.useState(0);

  const items = NAV.filter(
    (n) =>
      n.label.toLowerCase().includes(q.toLowerCase()) ||
      (n.hint ?? "").toLowerCase().includes(q.toLowerCase())
  );

  React.useEffect(() => {
    setIdx(0);
  }, [q, commandOpen]);

  React.useEffect(() => {
    if (!commandOpen) setQ("");
  }, [commandOpen]);

  const run = (path: string) => {
    setCommandOpen(false);
    navigate(path);
  };

  return (
    <Dialog open={commandOpen} onOpenChange={setCommandOpen}>
      <DialogContent className="top-[28%] max-w-xl translate-y-0 p-0">
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIdx((i) => Math.min(items.length - 1, i + 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setIdx((i) => Math.max(0, i - 1));
              }
              if (e.key === "Enter" && items[idx]) run(items[idx].path);
            }}
            placeholder="Search pages, actions, modules…"
            className="h-10 flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground/60"
          />
          <Kbd>esc</Kbd>
        </div>
        <div className="max-h-72 overflow-y-auto p-1.5 scrollbar-thin">
          {items.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">No matches.</div>
          ) : (
            items.map((item, i) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.path}
                  onMouseEnter={() => setIdx(i)}
                  onClick={() => run(item.path)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                    i === idx ? "bg-accent text-foreground" : "text-muted-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span className="flex-1">{item.label}</span>
                  {item.hint ? <span className="text-[10px] text-muted-foreground/60">{item.hint}</span> : null}
                  {i === idx ? <CornerDownLeft className="h-3 w-3 opacity-60" /> : null}
                </button>
              );
            })
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
