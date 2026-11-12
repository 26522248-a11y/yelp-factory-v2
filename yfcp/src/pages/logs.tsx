import * as React from "react";
import { Download, Pause, Play, Search, Terminal, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile } from "@/components/shared/bits";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Select, Switch } from "@/components/ui/form";
import { cn } from "@/lib/utils";

type Level = "INFO" | "WARN" | "ERROR" | "DEBUG";
interface Line {
  id: number;
  ts: string;
  level: Level;
  account: string;
  msg: string;
}

const ACCOUNTS = ["marcus.reed41@outlook.com", "nina.patel88@hotmail.com", "sofia.novak9@outlook.com", "owen.doyle7@live.com"];
const TEMPLATES: { level: Level; msg: string }[] = [
  { level: "INFO", msg: "warming session started — mode=post_review plan={plan_id}" },
  { level: "INFO", msg: "action=search q=\"bbq near me\" results=18" },
  { level: "INFO", msg: "action=pageview url=/biz/bluebonnet-grill-austin dwell=42s" },
  { level: "DEBUG", msg: "selector hit key=warm.search_box strategy=css#search_description" },
  { level: "DEBUG", msg: "scroll delta=412 direction=down" },
  { level: "WARN", msg: "selector miss key=login.submit_button attempt=1 fallback=text" },
  { level: "WARN", msg: "session gap below minimum — delaying 90m" },
  { level: "ERROR", msg: "captcha timeout provider=capsolver after 120s" },
  { level: "INFO", msg: "trust recomputed 68 → 72 (warm +4)" },
  { level: "INFO", msg: "review posted biz=copper-kettle-bbq rating=5 photo=1" },
];

let seq = 1;
function makeLine(): Line {
  const t = TEMPLATES[Math.floor(Math.random() * TEMPLATES.length)];
  return {
    id: seq++,
    ts: new Date().toISOString(),
    level: t.level,
    account: ACCOUNTS[Math.floor(Math.random() * ACCOUNTS.length)],
    msg: t.msg,
  };
}

export default function Logs() {
  const [lines, setLines] = React.useState<Line[]>(() => Array.from({ length: 40 }).map(makeLine));
  const [live, setLive] = React.useState(true);
  const [level, setLevel] = React.useState("all");
  const [q, setQ] = React.useState("");
  const [autoscroll, setAutoscroll] = React.useState(true);
  const boxRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setLines((prev) => [...prev.slice(-400), makeLine()]), 1400);
    return () => clearInterval(t);
  }, [live]);

  React.useEffect(() => {
    if (autoscroll && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines, autoscroll]);

  const visible = lines.filter(
    (l) => (level === "all" || l.level === level) && (q === "" || `${l.account} ${l.msg}`.toLowerCase().includes(q.toLowerCase()))
  );

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="System"
        title="Logs"
        description="Structured log stream from every worker. Filter by level or account, follow live, or export the slice you need."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => { setLines([]); toast.success("Buffer cleared"); }}>
              <Trash2 /> Clear
            </Button>
            <Button variant="outline" size="sm" onClick={() => toast.success("Filtered logs exported")}>
              <Download /> Export
            </Button>
            <Button size="sm" variant={live ? "destructive" : "success"} onClick={() => setLive((v) => !v)}>
              {live ? <Pause /> : <Play />} {live ? "Pause" : "Resume"}
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Lines buffered" value={lines.length} icon={<Terminal className="h-4 w-4" />} />
        <StatTile label="Errors" value={lines.filter((l) => l.level === "ERROR").length} tone="danger" />
        <StatTile label="Warnings" value={lines.filter((l) => l.level === "WARN").length} tone="warning" />
        <StatTile label="Stream" value={live ? "live" : "paused"} tone={live ? "success" : "warning"} />
      </div>

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <div className="relative w-64">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search message or account…" className="h-7 pl-7 text-xs" />
          </div>
          <Select className="h-7 w-28 text-xs" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="all">All levels</option>
            <option value="INFO">INFO</option>
            <option value="WARN">WARN</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
          </Select>
          <div className="ml-auto flex items-center gap-2 text-[11px] text-muted-foreground">
            autoscroll <Switch checked={autoscroll} onCheckedChange={setAutoscroll} />
          </div>
        </div>

        <div ref={boxRef} className="h-[440px] overflow-y-auto bg-[#070a10] p-3 font-mono text-[11px] leading-relaxed scrollbar-thin">
          {visible.map((l) => (
            <div key={l.id} className="flex gap-2 hover:bg-white/[0.03]">
              <span className="shrink-0 text-muted-foreground/60">{l.ts.slice(11, 23)}</span>
              <span
                className={cn(
                  "w-12 shrink-0 font-semibold",
                  l.level === "ERROR" && "text-destructive",
                  l.level === "WARN" && "text-warning",
                  l.level === "INFO" && "text-info",
                  l.level === "DEBUG" && "text-muted-foreground"
                )}
              >
                {l.level}
              </span>
              <span className="w-52 shrink-0 truncate text-muted-foreground">{l.account}</span>
              <span className="min-w-0 flex-1 text-foreground/85">{l.msg}</span>
            </div>
          ))}
          {visible.length === 0 && <div className="py-10 text-center text-muted-foreground">No lines match this filter.</div>}
        </div>

        <div className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[10.5px] text-muted-foreground">
          <span>
            {visible.length} of {lines.length} lines
          </span>
          <div className="flex items-center gap-2">
            <Badge variant="muted">json</Badge>
            <Badge variant="muted">PII redacted</Badge>
            <span className="font-mono">tail -f</span>
          </div>
        </div>
      </div>
    </div>
  );
}
