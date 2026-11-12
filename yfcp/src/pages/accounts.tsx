import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import type { ColumnDef, RowSelectionState } from "@tanstack/react-table";
import { Download, Eye, MoreHorizontal, Pause, Play, Plus, Trash2, Upload, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, AccountStateBadge, ModeBadge, TierBadge, Avatar } from "@/components/shared/bits";
import { DataTable } from "@/components/shared/data-table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox, Select } from "@/components/ui/form";
import { Dropdown, DropdownContent, DropdownItem, DropdownSeparator, DropdownTrigger } from "@/components/ui/primitives";
import { ImportDialog } from "@/components/shared/import-dialog";
import { RegisterDialog } from "@/components/shared/register-dialog";
import { accounts } from "@/lib/mock";
import type { Account } from "@/types";
import { timeAgo, cn } from "@/lib/utils";

export default function Accounts() {
  const navigate = useNavigate();
  const [selection, setSelection] = React.useState<RowSelectionState>({});
  const [stateFilter, setStateFilter] = React.useState("all");
  const [modeFilter, setModeFilter] = React.useState("all");
  const [cityFilter, setCityFilter] = React.useState("all");
  const [importOpen, setImportOpen] = React.useState(false);
  const [importType, setImportType] = React.useState<"accounts" | "proxies">("accounts");
  const [registerOpen, setRegisterOpen] = React.useState(false);
  const [importedCount, setImportedCount] = React.useState(0);

  const handleImport = (result: unknown[]) => {
    if (Array.isArray(result)) {
      setImportedCount((p) => p + result.length);
    }
  };

  const cities = React.useMemo(() => Array.from(new Set(accounts.map((a) => a.city))).sort(), []);

  const data = React.useMemo(
    () =>
      accounts.filter(
        (a) =>
          (stateFilter === "all" || a.state === stateFilter) &&
          (modeFilter === "all" || a.mode === modeFilter) &&
          (cityFilter === "all" || a.city === cityFilter)
      ),
    [stateFilter, modeFilter, cityFilter]
  );

  const columns: ColumnDef<Account>[] = [
    {
      id: "select",
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          onCheckedChange={(v) => table.toggleAllPageRowsSelected(v)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox checked={row.getIsSelected()} onCheckedChange={(v) => row.toggleSelected(v)} aria-label="Select row" />
      ),
      size: 32,
      enableSorting: false,
    },
    {
      accessorKey: "email",
      header: "Account",
      cell: ({ row }) => {
        const a = row.original;
        return (
          <div className="flex items-center gap-2">
            <Avatar name={`${a.firstName} ${a.lastName}`} hue={a.avatarHue} />
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 truncate text-[12px] font-medium">
                {a.firstName} {a.lastName}
                {a.adoptedAt && <Badge variant="muted" className="text-[9px]">adopted</Badge>}
              </div>
              <div className="truncate text-[10.5px] text-muted-foreground">{a.email}</div>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "state",
      header: "State",
      cell: ({ row }) => <AccountStateBadge state={row.original.state} />,
    },
    {
      accessorKey: "trustScore",
      header: "Trust",
      cell: ({ row }) => {
        const v = row.original.trustScore;
        return (
          <div className="flex items-center gap-2">
            <span className={cn("w-6 font-mono text-[11px]", v >= 75 ? "text-success" : v >= 50 ? "text-warning" : "text-destructive")}>{v}</span>
            <div className="h-1 w-12 overflow-hidden rounded-full bg-secondary">
              <div
                className={cn("h-full rounded-full", v >= 75 ? "bg-success" : v >= 50 ? "bg-warning" : "bg-destructive")}
                style={{ width: `${v}%` }}
              />
            </div>
          </div>
        );
      },
    },
    {
      id: "location",
      header: "City",
      accessorFn: (r) => `${r.city}, ${r.state_code}`,
      cell: ({ row }) => (
        <div className="text-[11px]">
          {row.original.city}, {row.original.state_code}
          {row.original.cityLockUntil && (
            <Badge variant="warning" className="ml-1.5 text-[9px]">
              city lock
            </Badge>
          )}
        </div>
      ),
    },
    {
      accessorKey: "phase",
      header: "Phase",
      cell: ({ row }) => (
        <span className="font-mono text-[11px] text-muted-foreground">
          {row.original.phase} · d{row.original.phaseDay}
        </span>
      ),
    },
    {
      accessorKey: "mode",
      header: "Mode",
      cell: ({ row }) => <ModeBadge mode={row.original.mode} />,
    },
    {
      accessorKey: "reviewsDone",
      header: "Reviews",
      cell: ({ row }) => <span className="font-mono text-[11px]">{row.original.reviewsDone}</span>,
    },
    {
      accessorKey: "tier",
      header: "Tier",
      cell: ({ row }) => <TierBadge tier={row.original.tier} />,
    },
    {
      accessorKey: "lastActiveAt",
      header: "Last active",
      cell: ({ row }) => <span className="text-[11px] text-muted-foreground">{timeAgo(row.original.lastActiveAt)}</span>,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <Dropdown>
          <DropdownTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={(e) => e.stopPropagation()}>
              <MoreHorizontal />
            </Button>
          </DropdownTrigger>
          <DropdownContent align="end">
            <DropdownItem onClick={() => navigate(`/accounts/${row.original.id}`)}>
              <Eye /> Open detail
            </DropdownItem>
            <DropdownItem onClick={() => toast.info(`Queued a warming session for ${row.original.email}`)}>
              <Play /> Run session now
            </DropdownItem>
            <DropdownItem onClick={() => toast.warning(`Paused ${row.original.email}`)}>
              <Pause /> Pause account
            </DropdownItem>
            <DropdownSeparator />
            <DropdownItem className="text-destructive focus:text-destructive" onClick={() => toast.error("Delete requires typed confirmation")}>
              <Trash2 /> Delete
            </DropdownItem>
          </DropdownContent>
        </Dropdown>
      ),
      size: 36,
      enableSorting: false,
    },
  ];

  const selectedCount = Object.keys(selection).length;

  return (
    <div className="flex h-[calc(100vh-6.5rem)] flex-col">
      <PageHeader
        eyebrow="Inventory"
        title="Accounts"
        description="Every identity under management — signup pipeline, warming phase, trust gate and review eligibility."
        actions={
          <>
            <Link to="/adopt">
              <Button variant="outline" size="sm">
                <UserPlus /> Adopt
              </Button>
            </Link>
            <Button variant="outline" size="sm" onClick={() => { setImportType("accounts"); setImportOpen(true); }}>
              <Upload /> Import
              {importedCount > 0 && <Badge variant="success" className="ml-1.5 text-[9px]">{importedCount}</Badge>}
            </Button>
            <Button size="sm" onClick={() => setRegisterOpen(true)}>
              <Plus /> New account
            </Button>
          </>
        }
      />

      <div className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
        <DataTable
          columns={columns}
          data={data}
          getRowId={(r) => r.id}
          rowSelection={selection}
          onRowSelectionChange={setSelection}
          onRowClick={(r) => navigate(`/accounts/${r.id}`)}
          searchPlaceholder="Search email, city…"
          pageSize={14}
          toolbar={
            <>
              <Select className="h-7 w-36 text-xs" value={stateFilter} onChange={(e) => setStateFilter(e.target.value)}>
                <option value="all">All states</option>
                {["ACTIVE", "WARMING", "READY", "COOLDOWN", "NEEDS_MANUAL", "BANNED", "DEAD"].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
              <Select className="h-7 w-36 text-xs" value={modeFilter} onChange={(e) => setModeFilter(e.target.value)}>
                <option value="all">All modes</option>
                <option value="post_review">Post-review</option>
                <option value="full_warm">Full warm</option>
                <option value="view_only">View only</option>
              </Select>
              <Select className="h-7 w-36 text-xs" value={cityFilter} onChange={(e) => setCityFilter(e.target.value)}>
                <option value="all">All metros</option>
                {cities.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
              {selectedCount > 0 && (
                <div className="flex items-center gap-1.5 rounded-md border border-primary/25 bg-primary/5 px-2 py-0.5">
                  <span className="text-[11px] text-primary">{selectedCount} selected</span>
                  <Button size="sm" variant="ghost" onClick={() => toast.success(`Resumed ${selectedCount} accounts`)}>
                    Resume
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => toast.warning(`Paused ${selectedCount} accounts`)}>
                    Pause
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => toast.success("CSV export queued")}>
                    <Download /> Export
                  </Button>
                </div>
              )}
            </>
          }
        />
      </div>

      {/* Dialogs */}
      <ImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        type={importType}
        onImport={handleImport}
      />
      <RegisterDialog open={registerOpen} onOpenChange={setRegisterOpen} />
    </div>
  );
}
