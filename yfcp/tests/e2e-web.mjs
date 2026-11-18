/**
 * Browser-mode integration test: vite dev server + fixture engine.
 *
 *   npm run fixture          # terminal 1 (127.0.0.1:8799)
 *   npm run dev              # terminal 2 (127.0.0.1:1420)
 *   node tests/e2e-web.mjs
 *
 * Verifies the plain-fetch fallback path and the live-data hooks without Tauri.
 */
import { chromium } from "playwright-core";

const APP_URL = process.env.APP_URL ?? "http://localhost:1420";
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8799";
const API_TOKEN = process.env.API_TOKEN ?? "fixture-token";
const CHROME = process.env.CHROME ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PHASE = process.argv[2] ?? "live";

function assert(condition, message) {
  if (!condition) throw new Error(`ASSERT FAILED: ${message}`);
  console.log(`  ok — ${message}`);
}

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await context.addInitScript(
  ({ api }) => {
    localStorage.setItem("yfcp-onboarded", "1");
    localStorage.setItem(
      "yfcp-ui",
      JSON.stringify({ state: { theme: "dark", sidebarCollapsed: false, commandOpen: false }, version: 0 })
    );
    localStorage.setItem("yfcp.api", JSON.stringify(api));
  },
  { api: { baseUrl: API_URL, token: API_TOKEN } }
);
const page = await context.newPage();
page.setDefaultTimeout(15_000);
const errors = [];
page.on("pageerror", (error) => errors.push(String(error)));

try {
  if (PHASE === "offline") {
    await page.goto(`${APP_URL}/#/`, { waitUntil: "networkidle" });
    await page.getByText(/Engine offline — showing sample data/i).waitFor();
    assert(true, "global banner distinguishes an unreachable engine");
    assert((await page.getByRole("button", { name: /Retry/i }).count()) > 0, "banner exposes a Retry action");
    assert(/sample data/.test(await page.locator("body").innerText()), "pages still render the fallback dataset");
    assert(errors.length === 0, `no unhandled page errors (${errors.join(" | ")})`);
    console.log("WEB OFFLINE PHASE OK");
  } else {
    await page.goto(`${APP_URL}/#/`, { waitUntil: "networkidle" });
    await page.getByText("live engine").first().waitFor();
    const dashboard = await page.locator("body").innerText();
    assert(/TOTAL ACCOUNTS\s*31/.test(dashboard), "dashboard totals from /report (browser fetch path)");

    await page.goto(`${APP_URL}/#/pools`, { waitUntil: "networkidle" });
    await page.getByText(/43 available/).first().waitFor();
    assert(true, "pool counters from /api/pool (CORS preflight)");

    await page.goto(`${APP_URL}/#/accounts`, { waitUntil: "networkidle" });
    await page.getByText("fixture.one@example.com").first().waitFor();
    await page.getByText("live engine").first().waitFor();
    assert(true, "account rows come from /api/accounts");

    await page.goto(`${APP_URL}/#/accounts/11111111-1111-4111-8111-111111111111`, { waitUntil: "networkidle" });
    await page.getByText("Amelia Hart").first().waitFor();
    assert(/fixture\.one@example\.com/.test(await page.locator("body").innerText()), "account detail resolves a live UUID");

    await page.goto(`${APP_URL}/#/nodes`, { waitUntil: "networkidle" });
    await page.getByText(/Machines online/i).first().waitFor();
    await page.getByText("console").first().waitFor();
    const nodesText = await page.locator("body").innerText();
    const onlineMatch = nodesText.match(/machines online\s*(\d+)\s*\/\s*(\d+)/i);
    assert(!!onlineMatch && Number(onlineMatch[1]) >= 1, `console heartbeat registers this machine (online ${onlineMatch?.[1]}/${onlineMatch?.[2]})`);
    await page.getByText("fixture-worker").first().waitFor();
    assert(true, "worker node with shared progress is listed");

    await page.goto(`${APP_URL}/#/logs`, { waitUntil: "networkidle" });
    await page.getByText(/warming session completed/i).first().waitFor();
    assert(true, "event stream from /events");

    await page.goto(`${APP_URL}/#/config`, { waitUntil: "networkidle" });
    const card = page.locator("#config-connection");
    await card.scrollIntoViewIfNeeded();
    assert(/connected · ok/.test(await card.innerText()), "connection panel reports the fixture as connected");

    await page.goto(`${APP_URL}/#/clients`, { waitUntil: "networkidle" });
    await page.getByText("endpoint not wired").first().waitFor();
    assert(true, "resources the engine does not expose are labelled 'endpoint not wired'");

    assert(errors.length === 0, `no unhandled page errors (${errors.join(" | ")})`);
    console.log("WEB PHASE OK");
  }
} finally {
  await browser.close();
}
