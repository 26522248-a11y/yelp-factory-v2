import { appInfo, isTauri, readSettings, writeSettings, type NodeHeartbeat } from "@/lib/bridge";

/**
 * Stable identity for this console machine. The id is generated once and kept in
 * the same store as the rest of the workspace settings; hostname/version are
 * refreshed from the OS on every launch.
 */
let cached: NodeHeartbeat | null = null;

export async function nodeIdentity(): Promise<NodeHeartbeat> {
  if (cached) return cached;

  let id = await readSettings<string>("yfcp.node.id", "");
  if (!id) {
    id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `node-${Date.now().toString(36)}`;
    await writeSettings("yfcp.node.id", id);
  }

  let hostname = typeof window !== "undefined" ? window.location.hostname || "browser" : "browser";
  if (isTauri) {
    try {
      const os = await import("@tauri-apps/plugin-os");
      hostname = (await os.hostname()) || hostname;
    } catch {
      // plugin unavailable — keep the fallback
    }
  }

  const info = await appInfo();
  cached = {
    node_id: id,
    name: hostname || "console",
    hostname,
    role: "console",
    version: info.version,
    capacity: 0,
    meta: {
      app: info.name,
      platform: typeof navigator !== "undefined" ? navigator.platform : "unknown",
    },
  };
  return cached;
}
