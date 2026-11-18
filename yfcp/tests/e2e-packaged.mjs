/**
 * End-to-end checks against the *packaged* Tauri app.
 *
 * The app must be started with WebView2 remote debugging enabled:
 *   $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9222'
 *   .\src-tauri\target\release\yfcp.exe
 *
 * Then run one phase at a time (some phases need an app restart):
 *   node tests/e2e-packaged.mjs setup
 *   node tests/e2e-packaged.mjs persist
 *   node tests/e2e-packaged.mjs bad-url
 *   node tests/e2e-packaged.mjs engine-down
 *
 * The engine fixture (npm run fixture) should be running on 8799 with the
 * default token for the "setup" phase.
 */
import { chromium } from "playwright-core";

const PHASE = process.argv[2] ?? "setup";
const CDP = process.env.CDP ?? "http://127.0.0.1:9222";
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8799";
const API_TOKEN = process.env.API_TOKEN ?? "fixture-token";

function assert(condition, message) {
  if (!condition) throw new Error(`ASSERT FAILED: ${message}`);
  console.log(`  ok — ${message}`);
}

async function connect() {
  const browser = await chromium.connectOverCDP(CDP);
  const context = browser.contexts()[0];
  const page = context.pages().find((p) => p.url().startsWith("http://tauri.localhost")) ?? context.pages()[0];
  if (!page) throw new Error("no WebView2 page found over CDP");
  page.setDefaultTimeout(15_000);
  return { browser, page };
}

async function finishOnboarding(page) {
  const dialog = page.getByRole("dialog");
  if ((await dialog.count()) === 0) return;
  for (let step = 0; step < 7; step += 1) {
    if ((await page.getByRole("dialog").count()) === 0) break;
    const next = page
      .getByRole("dialog")
      .getByRole("button", { name: /Continue|Enter workspace|Finish|Get started|Open console|Start/i })
      .last();
    if ((await next.count()) === 0) break;
    console.log(`  onboarding: ${(await next.innerText()).trim()}`);
    await next.click();
    await page.waitForTimeout(350);
  }
  assert((await page.getByRole("dialog").count()) === 0, "onboarding wizard dismissed");
}

async function go(page, hash) {
  await page.evaluate((target) => {
    window.location.hash = target;
  }, hash);
  await page.waitForTimeout(700);
}

async function setConnection(page, url, token) {
  await go(page, "/config");
  const card = page.locator("#config-connection");
  await card.scrollIntoViewIfNeeded();
  await card.getByPlaceholder("http://127.0.0.1:8787").fill(url);
  await card.getByPlaceholder("YF_ADMIN_TOKEN").fill(token);
  await card.getByRole("button", { name: /Save connection/i }).click();
}

async function importProxies(page, lines) {
  await go(page, "/pools");
  await page.getByRole("button", { name: /^Import$/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("textarea").fill(lines.join("\n"));
  await dialog.getByRole("button", { name: /Import \d+ proxies?/ }).click();
  await page.waitForTimeout(1200);
}

function proxiesSavedInData(page) {
  return page.evaluate(() => {
    const text = document.body.innerText;
    const match = text.match(/Accounts:\s*(\d+)\s*·\s*Proxies:\s*(\d+)/);
    return match ? { accounts: Number(match[1]), proxies: Number(match[2]) } : null;
  });
}

const { browser, page } = await connect();
console.log(`phase=${PHASE} url=${page.url()}`);

try {
  if (PHASE === "setup") {
    await finishOnboarding(page);

    await setConnection(page, API_URL, API_TOKEN);
    await page.getByText(/connected · ok/).waitFor({ timeout: 15_000 });
    assert(true, "admin_request relay reached the fixture and /health reported ok");

    await go(page, "/");
    await page.getByText("live engine").first().waitFor({ timeout: 15_000 });
    const dash = await page.locator("body").innerText();
    assert(/TOTAL ACCOUNTS\s*31/.test(dash), "dashboard total accounts came from /report (31)");
    assert(/ACTIVE TODAY\s*12/.test(dash), "dashboard active count came from /report (12)");

    await go(page, "/pools");
    await page.getByText(/43 available/).first().waitFor({ timeout: 10_000 });
    assert(true, "pool counters came from /api/pool");

    await go(page, "/accounts");
    await page.getByText("fixture.one@example.com").first().waitFor({ timeout: 10_000 });
    await page.getByText("live engine").first().waitFor({ timeout: 10_000 });
    assert(true, "account rows came from /api/accounts");

    await go(page, "/accounts/11111111-1111-4111-8111-111111111111");
    await page.getByText("Amelia Hart").first().waitFor({ timeout: 10_000 });
    assert(true, "account detail resolves a live UUID");

    await go(page, "/nodes");
    await page.getByText(/Machines online/i).first().waitFor({ timeout: 15_000 });
    await page.getByText("console").first().waitFor({ timeout: 15_000 });
    const nodesText = await page.locator("body").innerText();
    const onlineMatch = nodesText.match(/machines online\s*(\d+)\s*\/\s*(\d+)/i);
    assert(!!onlineMatch && Number(onlineMatch[1]) >= 1, `console heartbeat registers this machine (online ${onlineMatch?.[1]}/${onlineMatch?.[2]})`);
    await page.getByText("fixture-worker").first().waitFor();
    assert(true, "worker node with shared progress is listed");

    await go(page, "/logs");
    await page.getByText(/warming session completed/i).first().waitFor({ timeout: 10_000 });
    assert(true, "logs stream came from /events");

    await go(page, "/clients");
    await page.getByText("endpoint not wired").first().waitFor({ timeout: 10_000 });
    assert(true, "unimplemented resources are labelled 'endpoint not wired'");

    const lines = ["10.0.0.1:8001:user1:pass1", "10.0.0.2:8002:user2:pass2"];
    await importProxies(page, lines);
    await go(page, "/data");
    await page.getByRole("tab", { name: "Import" }).click();
    await page.waitForTimeout(400);
    const counts = await proxiesSavedInData(page);
    assert(counts?.proxies === 2, `saved imports show 2 proxies (got ${JSON.stringify(counts)})`);
  }

  if (PHASE === "persist") {
    await go(page, "/data");
    await page.getByRole("tab", { name: "Import" }).click();
    await page.waitForTimeout(400);
    const before = await proxiesSavedInData(page);
    assert(before?.proxies === 2, `2 saved proxies survived the restart (got ${JSON.stringify(before)})`);

    await importProxies(page, ["10.0.0.1:8001:user1:pass1", "10.0.0.2:8002:user2:pass2"]);
    await go(page, "/data");
    await page.getByRole("tab", { name: "Import" }).click();
    await page.waitForTimeout(400);
    const after = await proxiesSavedInData(page);
    assert(after?.proxies === 2, `re-importing the same lines did not duplicate rows (got ${JSON.stringify(after)})`);
  }

  if (PHASE === "bad-url") {
    await setConnection(page, "http://8.8.8.8:8787", API_TOKEN);
    await page.getByText(/plain HTTP is only allowed/i).waitFor({ timeout: 10_000 });
    assert(true, "public HTTP endpoint rejected by the relay with a clear message");
    const card = page.locator("#config-connection");
    assert(/connected · ok/.test(await card.innerText()), "previous connection stayed intact after the refused save");
    await setConnection(page, API_URL, API_TOKEN);
    await page.getByText(/connected · ok/).waitFor({ timeout: 15_000 });
    assert(true, "valid connection restored");
  }

  if (PHASE === "remote") {
    const remote = process.env.REMOTE_API_URL;
    assert(!!remote, "REMOTE_API_URL is required for the remote phase");
    await setConnection(page, remote, API_TOKEN);
    await page.getByText(/connected · ok/).waitFor({ timeout: 20_000 });
    assert(true, `connected to a remote engine at ${remote}`);

    await go(page, "/");
    await page.getByText("live engine").first().waitFor({ timeout: 15_000 });
    const body = await page.locator("body").innerText();
    assert(/TOTAL ACCOUNTS\s*31/.test(body), "remote data matches the shared engine (/report)");

    await go(page, "/accounts");
    await page.getByText("fixture.one@example.com").first().waitFor({ timeout: 15_000 });
    assert(true, "remote account inventory is shared across machines");

    await setConnection(page, API_URL, API_TOKEN);
    await page.getByText(/connected · ok/).waitFor({ timeout: 15_000 });
    assert(true, "restored the local fixture endpoint");
  }

  if (PHASE === "engine-down") {
    // Point at a closed local port: transport failure, not a relay refusal.
    await setConnection(page, "http://127.0.0.1:8798", API_TOKEN);
    await go(page, "/");
    await page.getByText(/Engine offline — showing sample data/i).waitFor({ timeout: 15_000 });
    assert(true, "global banner distinguishes an unreachable engine");
    assert((await page.getByRole("button", { name: /Retry/i }).count()) > 0, "banner exposes a Retry action");

    await go(page, "/config");
    const card = page.locator("#config-connection");
    await card.getByRole("button", { name: /Test connection/i }).click();
    await page.waitForTimeout(2500);
    const text = await card.innerText();
    assert(/unreachable/i.test(text), `engine-down shows a friendly message (${text.match(/.*unreachable.*/i)?.[0] ?? "no match"})`);
    assert(!/ at .*:\d+:\d+/.test(text), "no raw stack trace in the error state");
    await setConnection(page, API_URL, API_TOKEN);
    await page.getByText(/connected · ok/).waitFor({ timeout: 15_000 });
    assert(true, "valid connection restored after the offline test");
  }

  console.log("PHASE OK");
} finally {
  await browser.close();
}
