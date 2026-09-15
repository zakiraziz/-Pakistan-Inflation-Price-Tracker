/* Temporary QA harness (not part of the app): runs the real helpers.js + app.js
   against the live server in Node with a tiny DOM stub, so every tab and the
   basket filters can be exercised without a browser.  node _render_check.js  */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const BASE = process.env.BASE || "http://127.0.0.1:5010";
const HERE = __dirname;
const realFetch = global.fetch;

let passes = 0, fails = 0;
function check(label, cond, extra) {
  if (cond) { passes++; console.log("  OK   " + label); }
  else { fails++; console.log("  FAIL " + label + (extra ? "  :: " + extra : "")); }
}

/* ---------- minimal DOM -------------------------------------------------- */
function serialize(n) {
  if (n.nodeType === 3) return n._text;
  var attrs = Object.entries(n._attrs || {}).map(function (kv) {
    return " " + kv[0] + '="' + kv[1] + '"';
  }).join("");
  var cls = n.className ? ' class="' + n.className + '"' : "";
  var id = n.id ? ' id="' + n.id + '"' : "";
  return "<" + n.tag + id + cls + attrs + ">" + (n._html || "") +
    n.children.map(serialize).join("") + (n._text || "") + "</" + n.tag + ">";
}

class El {
  constructor(tag, id, cls, dataset) {
    this.tag = tag || "div"; this.id = id || ""; this.className = cls || "";
    this.dataset = dataset || {}; this.nodeType = 1;
    this.value = ""; this.checked = false; this.disabled = false;
    this._html = ""; this._text = ""; this.children = []; this._attrs = {}; this._h = {};
    this.classList = {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    };
  }
  set innerHTML(v) { this._html = v; this.children = []; this._text = ""; }
  get innerHTML() {
    return (this._html || "") + this.children.map(serialize).join("") + (this._text || "");
  }
  set textContent(v) { this._text = String(v); this.children = []; this._html = ""; }
  get textContent() {
    return (this._text || "") + this.children.map(function (c) {
      return c.nodeType === 3 ? c._text : c.textContent;
    }).join("") + (this._html || "");
  }
  appendChild(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this._attrs[k] = v; }
  getAttribute(k) { return this._attrs[k]; }
  addEventListener(ev, fn) { (this._h[ev] = this._h[ev] || []).push(fn); }
  fire(ev) { (this._h[ev] || []).forEach(function (f) { f({ preventDefault() {} }); }); }
  querySelectorAll() { return { forEach() {} }; }
  remove() {} click() {}
}
function mkEl(id, cls, dataset) { return new El("div", id, cls, dataset); }
function mkText(t) { return { nodeType: 3, _text: t }; }

const byId = {};
["kpis", "view", "alertsPanel", "itemList", "categoryFilters", "search", "start",
 "end", "threshold", "apply", "export", "updateNow", "updatedBadge", "infoLine",
 "toast"].forEach((id) => { byId[id] = mkEl(id); });
byId.threshold.value = "5";

const tabs = ["trends", "compare", "data"].map((v) => mkEl("", "tab", { view: v }));
const presets = [
  mkEl("", "preset", { months: "3" }), mkEl("", "preset", { months: "6" }),
  mkEl("", "preset", { months: "12" }), mkEl("", "preset", { all: "1" }),
];

const document = {
  readyState: "complete",
  getElementById: (id) => byId[id] || null,
  querySelectorAll: (sel) => {
    if (sel === ".tab") return tabs;
    if (sel === ".preset") return presets;
    return { forEach() {} };
  },
  createElement: (tag) => new El(tag),
  createTextNode: (t) => mkText(t),
  addEventListener() {},
  body: mkEl("body"),
};

let lastChart = null;
class Chart {
  constructor(canvas, cfg) { this.canvas = canvas; this.cfg = cfg; lastChart = this; }
  destroy() { this.destroyed = true; }
}

const ctx = {
  document, Chart, console, setTimeout, clearTimeout, Number, String, Math, Date,
  JSON, Promise, Array, Object, Set, fetch: (u, o) => realFetch(BASE + u, o),
};
ctx.window = ctx;
vm.createContext(ctx);

vm.runInContext(fs.readFileSync(path.join(HERE, "static", "helpers.js"), "utf8"), ctx, { filename: "helpers.js" });
vm.runInContext(fs.readFileSync(path.join(HERE, "static", "app.js"), "utf8"), ctx, { filename: "app.js" });

/* ---------- assertions --------------------------------------------------- */
(async () => {
  await new Promise((r) => setTimeout(r, 3000));      // let init()'s fetches settle
  if (process.env.DEBUG) {
    console.log("DEBUG view  :", JSON.stringify(byId.view.innerHTML.slice(0, 240)));
    console.log("DEBUG items :", JSON.stringify(byId.itemList.innerHTML.slice(0, 120)));
    console.log("DEBUG chips :", JSON.stringify(byId.categoryFilters.innerHTML.slice(0, 120)));
    console.log("DEBUG errmsg:", /<span>([^<]{0,200})<\/span><button/.exec(byId.view.innerHTML) ? /<span>([^<]{0,200})<\/span><button/.exec(byId.view.innerHTML)[1] : "n/a");
    console.log("DEBUG has renderItems?", typeof ctx.renderItems, "renderCategories?", typeof ctx.renderCategories);
  }

  console.log("\n--- boot: /api/items -> filters -> first render ---");
  check("category chips rendered", /category-chip/.test(byId.categoryFilters.innerHTML));
  check("item checkboxes rendered", (byId.itemList.innerHTML.match(/item-row/g) || []).length === 11,
    String((byId.itemList.innerHTML.match(/item-row/g) || []).length));
  check("KPI cards rendered", (byId.kpis.innerHTML.match(/kpi-value/g) || []).length === 4);
  check("updatedBadge no longer says Loading",
    !/Loading latest data/.test(byId.updatedBadge.textContent), byId.updatedBadge.textContent);
  check("infoLine populated", /items/.test(byId.infoLine.textContent), byId.infoLine.textContent);
  check("alerts panel rendered", /Largest jump|No alerts/.test(byId.alertsPanel.innerHTML));
  check("trends view has a canvas", /trendCanvas/.test(byId.view.innerHTML));
  check("chart got 11 datasets (all items)",
    !!lastChart && lastChart.cfg.data.datasets.length === 11,
    lastChart ? String(lastChart.cfg.data.datasets.length) : "no chart");
  check("no error state shown", !/Something went wrong/.test(byId.view.innerHTML));

  console.log("\n--- tabs (helpers render layer) ---");
  const pivot = { dates: ["2026-01-04", "2026-01-11"], index: [100, 101.5], items: [
    { name: "Wheat flour (atta)", category: "Grocery", unit: "per 20 kg bag",
      first: 4300, last: 4192, pct: -2.5, prices: [4300, 4192] },
    { name: "Onion", category: "Fresh produce", unit: "per kg",
      first: 90, last: 140, pct: 55.6, prices: [90, 140] },
  ] };
  const box = mkEl("view");
  try { ctx.renderTrends(box, pivot, "items"); check("renderTrends(items)", /trendCanvas/.test(box.innerHTML)); }
  catch (e) { check("renderTrends(items)", false, e.message); }
  check("trends chart has 2 datasets", lastChart.cfg.data.datasets.length === 2);
  try { ctx.renderTrends(box, pivot, "index"); check("renderTrends(index)", /Basket cost index/.test(JSON.stringify(lastChart.cfg.data))); }
  catch (e) { check("renderTrends(index)", false, e.message); }
  try { ctx.renderCompare(box, pivot); check("renderCompare", /compareCanvas/.test(box.innerHTML) && lastChart.cfg.type === "bar"); }
  catch (e) { check("renderCompare", false, e.message); }
  try { ctx.renderData(box, pivot); check("renderData", /<table>/.test(box.innerHTML) && /Wheat flour/.test(box.innerHTML)); }
  catch (e) { check("renderData", false, e.message); }

  console.log("\n--- interactions (fired through the real listeners) ---");
  const before = lastChart;
  tabs[1].fire("click"); check("Compare tab click re-renders", before !== lastChart && /compareCanvas/.test(byId.view.innerHTML));
  tabs[2].fire("click"); check("Data tab click re-renders", /<table>/.test(byId.view.innerHTML));
  tabs[0].fire("click"); check("Trends tab click re-renders", /trendCanvas/.test(byId.view.innerHTML));
  presets[0].fire("click"); check("3M preset sets start date", /^\d{4}-\d{2}-\d{2}$/.test(byId.start.value), byId.start.value);
  byId.search.value = "onion";
  byId.search.fire("input");
  await new Promise((r) => setTimeout(r, 400));
  check("search filters the item list", !/Wheat flour/.test(byId.itemList.innerHTML) && /Onion/.test(byId.itemList.innerHTML));
  byId.search.value = "";
  byId.search.fire("input");
  await new Promise((r) => setTimeout(r, 400));
  check("clearing search restores all items",
    (byId.itemList.innerHTML.match(/item-row/g) || []).length === 11);

  console.log("\n" + "=".repeat(52));
  console.log("RENDER CHECK: " + passes + " passed, " + fails + " failed");
  console.log("=".repeat(52));
  process.exit(fails ? 1 : 0);
})();

