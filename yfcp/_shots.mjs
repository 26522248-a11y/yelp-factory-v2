import { chromium } from "playwright-core";
import fs from "node:fs";

const out = "C:/Users/PC/AppData/Local/Temp/yfcp-shots";
fs.mkdirSync(out, { recursive: true });

const routes = process.argv.slice(2);
const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--force-device-scale-factor=1", "--hide-scrollbars"],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await context.addInitScript(() => {
  try {
    localStorage.setItem("yfcp-onboarded", "1");
    localStorage.setItem("yfcp-ui", JSON.stringify({ state: { theme: "dark", sidebarCollapsed: false, commandOpen: false }, version: 0 }));
  } catch {}
});
const page = await context.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
let n = 0;
for (const route of routes) {
  n++;
  await page.goto(`http://localhost:1420/?n=${n}#${route}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  const name = (route === "/" ? "dashboard" : route.replaceAll("/", "-").replace(/^-/, "")) || "root";
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: false });
  const text = await page.evaluate(() => document.querySelector("main")?.innerText.length ?? 0);
  console.log(name, "maintext", text, "hash", await page.evaluate(() => location.hash));
}
console.log("ERRORS", JSON.stringify(errors, null, 2));
await browser.close();
