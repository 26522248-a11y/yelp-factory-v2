/**
 * Runtime bridge between the console UI and the Tauri shell.
 *
 * Everything degrades to a browser-safe implementation so the same bundle can
 * run in `vite dev` during development and inside the desktop shell in
 * production. Nothing here mutates the engine — writes always go through the
 * yf CLI or the local admin API.
 */

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export interface AppInfo {
  name: string;
  version: string;
  engine: string;
}

export async function appInfo(): Promise<AppInfo> {
  if (!isTauri) return { name: "YFCP", version: "0.1.0", engine: "yelp-factory-v2" };
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<AppInfo>("app_info");
}

export async function notify(title: string, body: string) {
  if (!isTauri) return false;
  const { isPermissionGranted, requestPermission, sendNotification } = await import("@tauri-apps/plugin-notification");
  let granted = await isPermissionGranted();
  if (!granted) {
    const permission = await requestPermission();
    granted = permission === "granted";
  }
  if (granted) {
    sendNotification({ title, body });
    return true;
  }
  return false;
}

export async function pickFile(filters?: { name: string; extensions: string[] }[]) {
  if (!isTauri) return null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({ multiple: false, directory: false, filters });
  return typeof selected === "string" ? selected : null;
}

export async function openExternal(url: string) {
  if (!isTauri) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

export async function windowAction(action: "minimize" | "maximize" | "close") {
  if (!isTauri) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const w = getCurrentWindow();
  if (action === "minimize") await w.minimize();
  if (action === "maximize") await w.toggleMaximize();
  if (action === "close") await w.close();
}

export async function readSettings<T>(key: string, fallback: T): Promise<T> {
  if (!isTauri) {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  }
  const { load } = await import("@tauri-apps/plugin-store");
  const store = await load("settings.json", { autoSave: false });
  return (await store.get<T>(key)) ?? fallback;
}

export async function writeSettings<T>(key: string, value: T) {
  if (!isTauri) {
    localStorage.setItem(key, JSON.stringify(value));
    return;
  }
  const { load } = await import("@tauri-apps/plugin-store");
  const store = await load("settings.json", { autoSave: true });
  await store.set(key, value);
  await store.save();
}
