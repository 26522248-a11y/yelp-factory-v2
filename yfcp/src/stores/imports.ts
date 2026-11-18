import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { readSettings, writeSettings, removeSettings } from "@/lib/bridge";

/**
 * Accounts/proxies imported from .txt files.
 *
 * Engine v2 has no account-import endpoint yet (accounts are created by the
 * signup/adopt flows), and the proxy pool has `POST /api/pool/import` which the
 * console calls when the admin API is reachable. Everything the operator loads
 * is also kept locally so the UI survives a reload and stays usable offline.
 * Desktop uses tauri-plugin-store (`settings.json`), the browser uses
 * localStorage — both through the bridge.
 */

export interface ImportedAccount {
  id: string;
  email: string;
  password: string;
  yelpUrl: string;
  accessEmailUrl: string;
  importedAt: string;
  /** Set when the engine accepted the row (future account-import endpoint). */
  synced?: boolean;
}

export interface ImportedProxy {
  id: string;
  raw: string;
  host: string;
  port: number;
  username: string;
  password: string;
  importedAt: string;
  synced?: boolean;
}

interface ImportState {
  accounts: ImportedAccount[];
  proxies: ImportedProxy[];
  lastImportAt: string | null;
  addAccounts: (
    rows: { email: string; password: string; yelpUrl: string; accessEmailUrl: string }[]
  ) => number;
  addProxies: (
    rows: { host: string; port: string; username: string; password: string; raw?: string }[]
  ) => number;
  markProxiesSynced: (ids: string[]) => void;
  removeProxy: (id: string) => void;
  removeAccount: (id: string) => void;
  clear: () => void;
}

function newId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

const storage = createJSONStorage(() => ({
  getItem: (name: string) => readSettings<string | null>(name, null),
  setItem: (name: string, value: string) => writeSettings(name, value),
  removeItem: (name: string) => removeSettings(name),
}));

export const useImports = create<ImportState>()(
  persist(
    (set, get) => ({
      accounts: [],
      proxies: [],
      lastImportAt: null,

      addAccounts: (rows) => {
        const existing = new Set(get().accounts.map((a) => a.email.toLowerCase()));
        const now = new Date().toISOString();
        const fresh: ImportedAccount[] = [];
        for (const row of rows) {
          const key = row.email.trim().toLowerCase();
          if (!key || existing.has(key)) continue;
          existing.add(key);
          fresh.push({
            id: newId("imp"),
            email: row.email.trim(),
            password: row.password,
            yelpUrl: row.yelpUrl.trim(),
            accessEmailUrl: row.accessEmailUrl.trim(),
            importedAt: now,
          });
        }
        if (fresh.length) {
          set((s) => ({ accounts: [...fresh, ...s.accounts], lastImportAt: now }));
        }
        return fresh.length;
      },

      addProxies: (rows) => {
        const existing = new Set(get().proxies.map((p) => p.raw));
        const now = new Date().toISOString();
        const fresh: ImportedProxy[] = [];
        for (const row of rows) {
          const raw = (row.raw ?? `${row.host}:${row.port}:${row.username}:${row.password}`).trim();
          if (!raw || existing.has(raw)) continue;
          existing.add(raw);
          fresh.push({
            id: newId("ipx"),
            raw,
            host: row.host.trim(),
            port: Number(row.port) || 0,
            username: row.username,
            password: row.password,
            importedAt: now,
          });
        }
        if (fresh.length) {
          set((s) => ({ proxies: [...fresh, ...s.proxies], lastImportAt: now }));
        }
        return fresh.length;
      },

      markProxiesSynced: (ids) =>
        set((s) => ({
          proxies: s.proxies.map((p) => (ids.includes(p.id) ? { ...p, synced: true } : p)),
        })),

      removeProxy: (id) => set((s) => ({ proxies: s.proxies.filter((p) => p.id !== id) })),
      removeAccount: (id) => set((s) => ({ accounts: s.accounts.filter((a) => a.id !== id) })),
      clear: () => set({ accounts: [], proxies: [], lastImportAt: null }),
    }),
    {
      name: "yfcp.imports",
      version: 1,
      storage,
      partialize: (s) => ({ accounts: s.accounts, proxies: s.proxies, lastImportAt: s.lastImportAt }),
    }
  )
);
