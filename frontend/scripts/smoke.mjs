/**
 * Headless render check.
 *
 * Builds are rendered in jsdom with a ResizeObserver that reports a real size,
 * so Recharts actually draws the charts instead of bailing out at zero width -
 * that is where data-shape crashes (empty axes, all-null series) show up.
 *
 *   node scripts/smoke.mjs                      # against the local backend
 *   API_BASE=http://127.0.0.1:8099 node ...     # against the hostile stub API
 *
 * Exits non-zero if anything throws or logs an error.
 */

import { JSDOM } from "jsdom";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fetch as undiciFetch } from "undici";

const dist = "dist";
const API_BASE = process.env.API_BASE ?? "http://127.0.0.1:8000";

const html = fs.readFileSync(path.join(dist, "index.html"), "utf8");
const dom = new JSDOM(html, {
  url: "http://localhost:5173/",
  pretendToBeVisual: true,
  runScripts: "outside-only",
});
const { window } = dom;

for (const key of [
  "window", "document", "HTMLElement", "Element", "Node", "SVGElement",
  "getComputedStyle", "localStorage", "MutationObserver", "Event",
  "CustomEvent", "DOMParser",
]) {
  try {
    globalThis[key] = window[key];
  } catch {
    /* read-only global */
  }
}
globalThis.window = window;
globalThis.document = window.document;
try {
  Object.defineProperty(globalThis, "navigator", {
    value: window.navigator,
    configurable: true,
  });
} catch {
  /* node >= 21 exposes a read-only navigator */
}
window.matchMedia = globalThis.matchMedia = () => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
});

// Report a real box so Recharts renders its SVG (jsdom has no layout engine).
class SizedResizeObserver {
  constructor(callback) {
    this.callback = callback;
  }
  observe(element) {
    const contentRect = { width: 960, height: 340, top: 0, left: 0 };
    element.getBoundingClientRect = () => ({ ...contentRect, bottom: 340, right: 960 });
    setTimeout(() => this.callback([{ target: element, contentRect }], this), 0);
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = window.ResizeObserver = SizedResizeObserver;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
window.SVGElement.prototype.getBBox ??= () => ({ x: 0, y: 0, width: 40, height: 12 });

globalThis.fetch = async (input, init) => {
  const url = typeof input === "string" ? input : input.url;
  return undiciFetch(url.startsWith("http") ? url : API_BASE + url, init);
};

const errors = [];
window.addEventListener("error", (event) => errors.push(`window.error: ${event.message}`));
const require = createRequire(import.meta.url);
void require;
const originalError = console.error;
console.error = (...args) => {
  errors.push(`console.error: ${args.map(String).join(" ").slice(0, 400)}`);
  originalError(...args);
};

const entry = fs
  .readdirSync(path.join(dist, "assets"))
  .find((file) => file.endsWith(".js"));
await import(path.resolve(dist, "assets", entry));

await new Promise((resolve) => setTimeout(resolve, 3000));

const root = window.document.getElementById("root");
const text = root.textContent ?? "";
const svgCount = root.querySelectorAll("svg.recharts-surface").length;
const pathCount = root.querySelectorAll("path.recharts-curve").length;

console.log(`API base      : ${API_BASE}`);
console.log(`Root HTML     : ${root.innerHTML.length} chars`);
console.log(`Charts drawn  : ${svgCount} surfaces, ${pathCount} curves`);

// On the default (Market Health) page we expect these panels.
const marketHealthExpected = [
  "Market breadth",
  "Advance / Decline",
  "Global markets today",
  "Commodities",
  "Data status",
];
// The nav row has all 6 page tabs.
const navTabs = [
  "Market Health",
  "Sector Performance",
  "Scanner",
  "Portfolio",
  "Terminal",
  "Trade Leader",
];
const missingOnMarket = marketHealthExpected.filter((n) => !text.includes(n));
const missingTabs = navTabs.filter((n) => !text.includes(n));

// Click the Sector Performance tab and wait for its panel to render.
let sectorMissing = [];
let sectorSvgCount = 0;
const sectorTab = [...document.querySelectorAll('[role="tab"]')].find(
  (el) => el.textContent?.includes("Sector Performance"),
);
if (sectorTab) {
  sectorTab.click();
  await new Promise((r) => setTimeout(r, 800));
  const sectorText = root.textContent ?? "";
  sectorMissing = ["Sector & thematic ETFs"].filter((n) => !sectorText.includes(n));
  sectorSvgCount = root.querySelectorAll("svg.recharts-surface").length;
}

console.log(`API base      : ${API_BASE}`);
console.log(`Root HTML     : ${root.innerHTML.length} chars`);
console.log(`Charts drawn  : ${svgCount} surfaces, ${pathCount} curves`);
console.log(`Market Health : ${missingOnMarket.length ? `MISSING ${missingOnMarket.join(", ")}` : "all present"}`);
console.log(`Nav tabs      : ${missingTabs.length ? `MISSING ${missingTabs.join(", ")}` : "all present"}`);
console.log(`Sector page   : ${sectorMissing.length ? `MISSING ${sectorMissing.join(", ")}` : `ETF panel rendered (${sectorSvgCount} charts)`}`);
console.log(`Errors        : ${errors.length ? "" : "none"}`);
for (const error of errors.slice(0, 6)) console.log(`  - ${error}`);

const blank = root.innerHTML.length < 2000;
if (blank) console.log("FAIL: the page rendered blank");

const fail =
  errors.length ||
  missingOnMarket.length ||
  missingTabs.length ||
  sectorMissing.length ||
  blank;
process.exit(fail ? 1 : 0);
