/*
 * tests/test_js_helpers.js
 * ------------------------
 * Front-end logic tests for static/helpers.js (the inflation-intelligence
 * layer). Run with:
 *
 *     node tests/test_js_helpers.js
 *
 * Dependency-free on purpose: the helper file is loaded into a bare V8
 * context with a stub DOM, so the pure functions can be asserted directly
 * instead of through a browser. Exits non-zero when anything fails, so it can
 * gate CI alongside pytest.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const HELPERS = path.join(__dirname, "..", "static", "helpers.js");

/* Minimal environment: helpers.js only touches document/Chart at call time. */
const sandbox = {
  document: { getElementById: () => null },
  Chart: function () {},
  window: {},
  console: console,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(HELPERS, "utf8"), sandbox, { filename: HELPERS });

let passed = 0;
let failed = 0;
const failures = [];

function check(name, ok, detail) {
  if (ok) {
    passed++;
    console.log("  ok   " + name);
  } else {
    failed++;
    failures.push(name + (detail ? " — " + detail : ""));
    console.log("  FAIL " + name + (detail ? "  (" + detail + ")" : ""));
  }
}
function eq(name, actual, expected) {
  check(name, actual === expected, "got " + JSON.stringify(actual) +
    ", expected " + JSON.stringify(expected));
}
function contains(name, haystack, needle) {
  check(name, String(haystack).indexOf(needle) !== -1, "missing " + JSON.stringify(needle));
}

/* A small, hand-built window with known answers. */
const PIVOT = {
  dates: ["2026-07-01", "2026-07-08", "2026-07-15"],
  index: [100, 110, 121],
  items: [
    { name: "Onion", category: "Fresh produce", unit: "per kg",
      first: 100, last: 90, pct: -10, prices: [100, 95, 90] },
    { name: "Wheat flour (atta)", category: "Grocery", unit: "per 20 kg bag",
      first: 1000, last: 1200, pct: 20, prices: [1000, 1100, 1200] },
    { name: "Sugar", category: "Grocery", unit: "per kg",
      first: 100, last: 110, pct: 10, prices: [100, 105, 110] },
    { name: "Electricity", category: "Energy", unit: "per kWh",
      first: 40, last: 60, pct: 50, prices: [40, 50, 60] },
  ],
};
const EMPTY = { dates: [], index: [], items: [] };
const METRICS = { weeks: 3, count: 4, first_date: "2026-07-01", last_date: "2026-07-15" };

console.log("\nformatting helpers");
eq("pct(12.34)", sandbox.pct(12.34), "+12.3%");
eq("pct(-3)", sandbox.pct(-3), "-3.0%");
eq("pct(0)", sandbox.pct(0), "+0.0%");
contains("money(1234.5) has thousands separator", sandbox.money(1234.5), "1,234.5");
eq("esc escapes <", sandbox.esc("<b>"), "&lt;b&gt;");
check("daysAgo(7) looks like an ISO date", /^\d{4}-\d{2}-\d{2}$/.test(sandbox.daysAgo(7)));
(function () {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  eq("daysAgo(7) is seven days back", sandbox.daysAgo(7), d.toISOString().slice(0, 10));
})();

console.log("\ncategoryChanges");
const cats = sandbox.categoryChanges(PIVOT);
eq("three categories", cats.length, 3);
eq("sorted by pct desc", cats.map((c) => c.category).join(","), "Energy,Grocery,Fresh produce");
eq("Energy average", cats[0].pct, 50);
eq("Grocery equal-weight average", cats[1].pct, 15);
eq("Grocery counts 2 items", cats[1].count, 2);
eq("Grocery up/down split", cats[1].up + "/" + cats[1].down, "2/0");
eq("Fresh produce is negative", cats[2].pct, -10);
eq("Fresh produce down count", cats[2].down, 1);

console.log("\ntopMovers");
const movers = sandbox.topMovers(PIVOT, 2);
eq("risers desc", movers.risers.map((i) => i.name).join(","), "Electricity,Wheat flour (atta)");
eq("fallers only negatives", movers.fallers.map((i) => i.name).join(","), "Onion");
check("no negative item in risers", movers.risers.every((i) => i.pct > 0));
check("no positive item in fallers", movers.fallers.every((i) => i.pct < 0));
eq("k=10 cannot invent rows", sandbox.topMovers(PIVOT, 10).risers.length, 3);

console.log("\nnarrative");
const text = sandbox.narrative(PIVOT, METRICS);
contains("states how many rose", text, "3 of 4 tracked items rose");
contains("states the window length", text, "(3 weeks)");
contains("states the average move", text, "+17.5%");   /* (50+20+10-10)/4 */
contains("names the leading category", text, "Energy moved most (+50.0% average across 1 items");
contains("names the calmest category", text, "Fresh produce was calmest (-10.0%)");
contains("cites the biggest rise with prices", text,
  "Electricity +50.0% (Rs 40 \u2192 Rs 60 per kWh)");
contains("cites the biggest fall", text, "Biggest fall: Onion -10.0%.");
contains("disclaims hidden estimation", text, "no model, no estimates");
eq("empty pivot -> empty string", sandbox.narrative(EMPTY, METRICS), "");
eq("null metrics tolerated", typeof sandbox.narrative(PIVOT, null), "string");

console.log("\nrenderSparkline");
eq("needs two points", sandbox.renderSparkline([5], 100, 40), "");
eq("needs data at all", sandbox.renderSparkline(null, 100, 40), "");
(function () {
  const up = sandbox.renderSparkline([1, 2, 3], 100, 40);
  contains("renders a polyline", up, "<polyline");
  const pts = up.match(/points="([^"]+)"/)[1].split(" ");
  eq("one coordinate per point", pts.length, 3);
  contains("rising line uses the 'up' colour", up, "#c2410c");
  const down = sandbox.renderSparkline([3, 2, 1], 100, 40);
  contains("falling line uses the 'down' colour", down, "#009e73");
  check("flat line does not produce NaN",
    sandbox.renderSparkline([2, 2, 2], 100, 40).indexOf("NaN") === -1);
})();

console.log("\nrenderWhyPanel");
(function () {
  const box = { innerHTML: "" };
  sandbox.renderWhyPanel(box, PIVOT, METRICS);
  const html = box.innerHTML;
  contains("has an increases column", html, "Biggest increases");
  contains("has a decreases column", html, "Biggest decreases");
  contains("has category bars", html, "By category (average change)");
  contains("discloses the weighting", html, "equal-weight");
  contains("includes the narrative", html, "why-note");
  contains("lists the top riser", html, "Electricity");
  contains("lists the faller", html, "Onion");
  check("bar widths are percentages", /width:\d+%/.test(html));

  const empty = { innerHTML: "previous" };
  sandbox.renderWhyPanel(empty, EMPTY, METRICS);
  eq("empty pivot clears the panel", empty.innerHTML, "");

  const onlyRises = {
    dates: ["a", "b"], index: [100, 101],
    items: [PIVOT.items[1]],
  };
  const box2 = { innerHTML: "" };
  sandbox.renderWhyPanel(box2, onlyRises, METRICS);
  contains("all-rise window says so", box2.innerHTML, "Nothing fell in this window");
})();

console.log("\nescaping (untrusted item names from the database)");
(function () {
  const evil = {
    dates: ["a", "b"], index: [100, 101],
    items: [{ name: '<img src=x onerror="alert(1)">', category: "Grocery",
              unit: "per kg", first: 1, last: 2, pct: 100, prices: [1, 2] }],
  };
  const box = { innerHTML: "" };
  sandbox.renderWhyPanel(box, evil, METRICS);
  check("why-panel escapes markup", box.innerHTML.indexOf("<img") === -1);
  const note = sandbox.narrative(evil, METRICS);
  check("narrative escapes markup", note.indexOf("<img") === -1);
  contains("escaped name is shown literally", note, "&lt;img");
})();

console.log("\n" + "=".repeat(62));
console.log("  " + passed + " passed, " + failed + " failed");
if (failed) {
  console.log("\n  Failures:");
  failures.forEach(function (f) { console.log("    - " + f); });
  console.log("\n  FRONT-END TESTS FAILED");
  process.exit(1);
}
console.log("\n  FRONT-END TESTS PASSED");