// Full-journey check against the running stack (Next :3000, agent :8000, MCP, Databricks).
//   node e2e/journey.mjs [screenshotDir]
import { chromium } from "playwright";

const URL = process.env.WORKBENCH_URL || "http://localhost:3000";
const OUT = process.argv[2] || ".";
const log = (...a) => console.log("[e2e]", ...a);

const browser = await chromium.launch(
  process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {}
);
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(String(e)));
const llmCalls = [];
page.on("request", (r) => {
  if (r.url().includes("/api/copilotkit")) llmCalls.push(r.url());
});

const connected = page.waitForResponse((r) => r.url().includes("/agent/sandbox_agent/connect"), { timeout: 60000 });
await page.goto(URL);
const input = page.locator("textarea").first();
await input.waitFor({ timeout: 30000 });
await connected; // a human never types before the agent handshake finishes
await page.waitForTimeout(1500);

const prompt =
  "Build a small micro-app to track customers with name, email, company and status (active/lead/churned). Run it and show it to me.";
await input.fill(prompt);
await input.press("Enter");
log("prompt sent; waiting for the app to be published (can take a few minutes)…");

// A published table shows up in the canvas.
await page.waitForSelector("table thead th", { timeout: 420000 });
log("table rendered");
await page.screenshot({ path: `${OUT}/01-table-empty.png` });

const headers = (await page.locator("table thead th").allInnerTexts()).map((t) => t.trim().toLowerCase());
log("columns:", headers.join(", "));

// Paste rows directly into the grid (spreadsheet-style); this must NOT touch the LLM.
const tag = String(Date.now()).slice(-5);
const people = [
  [`Ada Lovelace ${tag}`, "ada@analytical.io", "Analytical Engines", "active"],
  [`Grace Hopper ${tag}`, "grace@navy.mil", "US Navy", "lead"],
  [`Alan Turing ${tag}`, "alan@bletchley.uk", "Bletchley", "churned"],
];
const tsv = people.map((r) => r.join("\t")).join("\n");
const before = llmCalls.length;
await page.evaluate((text) => {
  const target = document.querySelector(".sheet") || document.querySelector("table");
  const dt = new DataTransfer();
  dt.setData("text/plain", text);
  target.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
}, tsv);

// Input values are not part of innerText, so read them explicitly.
const namesOnPage = () =>
  page.evaluate(() => [
    ...[...document.querySelectorAll("table tbody input.cell")].map((i) => i.value), // table kind
    ...[...document.querySelectorAll(".sheet tbody td.cell")].map((c) => c.innerText.trim()), // sheet kind
  ]);
const hasAll = async () => {
  const vals = await namesOnPage();
  return people.every(([n]) => vals.includes(n));
};
const deadline = Date.now() + 90000;
while (!(await hasAll()) && Date.now() < deadline) await page.waitForTimeout(500);
const pasted = await hasAll();
log("all pasted rows visible in the table:", pasted);
await page.screenshot({ path: `${OUT}/02-after-paste.png` });
const llmDuringPaste = llmCalls.length - before;
log("copilotkit requests during paste:", llmDuringPaste);

// Reload: the thread is restored (canvas comes back) and the data lives in the sandbox app.
await page.reload();
await page.waitForSelector("table tbody tr", { timeout: 90000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/03-after-reload.png` });
const survived = await hasAll();
log("pasted rows still present after reload:", survived);
log("page errors:", consoleErrors.length ? consoleErrors : "none");
await browser.close();

if (!pasted || !survived || llmDuringPaste !== 0) process.exit(1);
