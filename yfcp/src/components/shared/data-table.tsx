import * as React from "react";
import {
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type RowSelectionState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, ChevronsUpDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  searchPlaceholder?: string;
  toolbar?: React.ReactNode;
  pageSize?: number;
  onRowClick?: (row: TData) => void;
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: (s: RowSelectionState) => void;
  getRowId?: (row: TData) => string;
  dense?: boolean;
  hideSearch?: boolean;
  emptyState?: React.ReactNode;
  footer?: React.ReactNode;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  searchPlaceholder = "Search…",
  toolbar,
  pageSize = 12,
  onRowClick,
  rowSelection,
  onRowSelectionChange,
  getRowId,
  dense,
  hideSearch,
  emptyState,
  footer,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = React.useState("");

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnFilters, globalFilter, ...(rowSelection ? { rowSelection } : {}) },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: onRowSelectionChange as never,
    getRowId,
    enableRowSelection: !!rowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  return (
    <div className="flex min-h-0 flex-col">
      {(!hideSearch || toolbar) && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          {!hideSearch && (
            <div className="relative w-56">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
                placeholder={searchPlaceholder}
                className="h-7 pl-7 text-xs"
              />
            </div>
          )}
          <div className="flex flex-1 flex-wrap items-center gap-2">{toolbar}</div>
          {rowSelection && Object.keys(rowSelection).length > 0 && (
            <span className="text-[11px] text-muted-foreground">{Object.keys(rowSelection).length} selected</span>
          )}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto scrollbar-thin">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 z-10 bg-card/95 backdrop-blur">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-border">
                {hg.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      className={cn(
                        "whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground",
                        header.column.getCanSort() && "cursor-pointer select-none hover:text-foreground"
                      )}
                      style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <span className="inline-flex items-center gap-1">
                        {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() ? (
                          sorted === "asc" ? (
                            <ChevronUp className="h-3 w-3" />
                          ) : sorted === "desc" ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronsUpDown className="h-3 w-3 opacity-40" />
                          )
                        ) : null}
                      </span>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-14 text-center">
                  {emptyState ?? <span className="text-xs text-muted-foreground">No results.</span>}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => onRowClick?.(row.original)}
                  className={cn(
                    "border-b border-border/60 transition-colors last:border-0 hover:bg-accent/40",
                    onRowClick && "cursor-pointer",
                    row.getIsSelected() && "bg-primary/5"
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className={cn("px-3 align-middle", dense ? "py-1" : "py-1.5")}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border px-3 py-2">
        <div className="text-[11px] text-muted-foreground">
          {footer ?? (
            <>
              {table.getFilteredRowModel().rows.length} rows · page {table.getState().pagination.pageIndex + 1} of{" "}
              {Math.max(1, table.getPageCount())}
            </>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
            <ChevronLeft />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
            <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function SortHeader({ children }: { children: React.ReactNode }) {
  return <span>{children}</span>;
}
