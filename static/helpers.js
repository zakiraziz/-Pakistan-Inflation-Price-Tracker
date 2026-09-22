/* ==========================================================================
   Render layer (state-free). Loaded before app.js.
   Design rules live in style.css tokens; icons are inline Lucide-style SVGs.
   ========================================================================== */
var PALETTE = ["#046A38", "#0072B2", "#E69F00", "#CC79A7", "#56B4E9",
  "#D55E00", "#6A3D9A", "#8C8C8C", "#B15928", "#4E79A7", "#009E73"];

/* Chart canvas colours (keep in sync with the tokens in style.css):
   Pakistan-flag green for brand marks, vermillion for rises, jade for falls. */
var INK = "#12211a", GRID = "#eceef1", AXIS = "#e3e6ea", TICK = "#55605a";
var BRAND = "#046a38", BRAND_SOFT = "rgba(4,106,56,.12)";
var UP = "#c2410c", DOWN = "#009e73";

var ICONS = {
  alert: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  trend: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/></svg>',
  check: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>'
};

var activeChart = null;
function el(id) { return document.getElementById(id); }
function destroyChart() { if (activeChart) { try { activeChart.destroy(); } catch (e) {} activeChart = null; } }
function todayISO() { return new Date().toISOString().slice(0, 10); }
function monthsAgo(n) { var d = new Date(); d.setMonth(d.getMonth() - n); return d.toISOString().slice(0, 10); }
function money(v) { return "Rs " + Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 }); }
function pct(v) { return (v >= 0 ? "+" : "") + Number(v).toFixed(1) + "%"; }
function pctCls(v) { return v >= 0 ? "up" : "down"; }
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function thresholdVal() { var t = el("threshold"); return t ? Number(t.value) || 5 : 5; }

/* ---------- loading / empty / error states (skeletons, never spinners) --- */
function renderSkeletons(kpiEl, viewEl) {
  var cards = "";
  for (var i = 0; i < 4; i++) {
    cards += '<div class="kpi"><span class="skeleton sk-line" style="width:40%"></span>' +
      '<span class="skeleton sk-line" style="width:60%;height:22px"></span>' +
      '<span class="skeleton sk-line" style="width:80%"></span></div>';
  }
  kpiEl.innerHTML = cards;
  viewEl.innerHTML =
    '<span class="skeleton sk-line" style="width:140px"></span>' +
    '<div class="skeleton sk-block" role="status" aria-label="Loading chart"></div>' +
    '<span class="skeleton sk-line" style="width:50%"></span>';
}

function renderError(container, message) {
  container.innerHTML =
    '<div class="state" role="alert"><span class="icon">' + ICONS.alert + '</span>' +
    '<span class="title">Something went wrong</span><span>' + esc(message) + '</span>' +
    '<button class="btn" id="retry">Try again</button></div>';
}

function renderEmpty(container, title, message, icon) {
  container.innerHTML =
    '<div class="state"><span class="icon">' + (ICONS[icon || "trend"]) + '</span>' +
    '<span class="title">' + esc(title) + '</span><span>' + esc(message) + '</span></div>';
}

/* ---------- basket filters (category chips + item checkboxes) ------------ */
/* Renders the category filter chips into #categoryFilters. `active` is a Set of
   category names (empty = "all"); onPick(name) receives "" to clear it. */
function renderCategories(container, items, active, onPick) {
  var cats = [];
  items.forEach(function (it) {
    if (cats.indexOf(it.category) === -1) cats.push(it.category);
  });
  cats.sort();
  var chip = function (label, count, on, key) {
    var s = document.createElement("span");
    s.className = "category-chip" + (on ? " on" : "");
    s.setAttribute("role", "button");
    s.setAttribute("tabindex", "0");
    s.textContent = label;
    if (count !== null) {
      var p = document.createElement("span");
      p.className = "pill";
      p.textContent = count;
      s.appendChild(p);
    }
    var pick = function () { onPick(key); };
    s.addEventListener("click", pick);
    s.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); }
    });
    return s;
  };
  container.innerHTML = "";
  container.appendChild(chip("All items", items.length, active.size === 0, ""));
  cats.forEach(function (c) {
    var n = items.filter(function (i) { return i.category === c; }).length;
    container.appendChild(chip(c, n, active.has(c), c));
  });
}

/* Renders the item checkboxes into #itemList. `selected` is a Set of item ids,
   `changes` an optional map of item name -> % change over the current window. */
function renderItems(container, items, selected, onToggle, changes) {
  container.innerHTML = "";
  if (!items.length) {
    renderEmpty(container, "No items match",
      "Clear the search box or pick another category.", "trend");
    return;
  }
  items.forEach(function (it) {
    var row = document.createElement("label");
    row.className = "item-row";
    var check = document.createElement("span");
    check.className = "ir-check";
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = selected.has(it.id);
    box.value = String(it.id);
    check.appendChild(box);
    var body = document.createElement("span");
    body.className = "ir-body";
    var nm = document.createElement("span");
    nm.className = "ir-name";
    nm.textContent = it.name;
    var cat = document.createElement("span");
    cat.className = "ir-cat";
    cat.textContent = it.category;
    body.appendChild(nm);
    body.appendChild(cat);
    var meta = document.createElement("span");
    meta.className = "ir-meta";
    var ch = changes ? changes[it.name] : undefined;
    if (typeof ch === "number") {
      var sp = document.createElement("span");
      sp.className = "ir-ch " + pctCls(ch);
      sp.textContent = pct(ch);
      meta.appendChild(sp);
      meta.appendChild(document.createTextNode(" \u00b7 " + it.unit));
    } else {
      meta.textContent = it.unit;
    }
    box.addEventListener("change", function () { onToggle(it.id, box.checked); });
    row.appendChild(check);
    row.appendChild(body);
    row.appendChild(meta);
    container.appendChild(row);
  });
}

/* Chart.js comes from a CDN; degrade gracefully when it did not load. */
function hasChart() { return typeof Chart !== "undefined"; }

/* ---------- charts ------------------------------------------------------ */
function baseOptions(yTitle, tooltipFmt) {
  return {
    responsive: true,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { labels: { color: INK, usePointStyle: true,
        pointStyleWidth: 9, boxPadding: 8,
        font: { family: "Inter", size: 12, weight: 500 } } },
      tooltip: { backgroundColor: INK, titleColor: "#ffffff",
        bodyColor: "#e7eef7", padding: 10, cornerRadius: 8, displayColors: true,
        callbacks: { label: function (c) {
          var s = c.dataset.label || "";
          return " " + s + ": " + (tooltipFmt ? tooltipFmt(c.value) : c.value);
        } } }
    },
    scales: {
      x: { grid: { color: GRID }, border: { color: AXIS },
           ticks: { color: TICK, maxTicksLimit: 10,
                    font: { family: "Inter", size: 12 } } },
      y: { beginAtZero: false, grid: { color: GRID },
           border: { display: false },
           ticks: { color: TICK, font: { family: "Inter", size: 12 } },
           title: { display: !!yTitle, text: yTitle || "", color: TICK,
                    font: { family: "Inter", size: 12 } } }
    }
  };
}
function renderKPIs(container, metrics, infl, alerts) {
  var has = metrics && metrics.count;
  var b = has ? metrics.basket_pct : 0;
  var range = (metrics.first_date || "—") + " to " + (metrics.last_date || "—");
  var ann = infl && infl.annualized_pct;
  var yoy = infl && infl.yoy_pct;
  var card = function (k, v, cls, sub) {
    return '<div class="kpi"><span class="k">' + k + '</span>' +
      '<span class="v ' + cls + '">' + v + '</span><span class="s">' + sub + '</span></div>';
  };
  container.innerHTML =
    card("Basket cost change", pct(b), pctCls(b),
         "equal-weight · " + (metrics.weeks || 0) + " wks · " + range) +
    card("Annualised inflation", ann === undefined ? "—" : pct(ann),
         pctCls(ann || 0), "implied per-year cost growth") +
    card("Year-over-year", (yoy === undefined || yoy === null) ? "n/a" : pct(yoy),
         pctCls(yoy || 0), "latest 52 weeks vs prior year") +
    card("Price jumps", alerts.length || 0, alerts.length ? "up" : "",
         "≥ " + thresholdVal() + "% week-over-week");
}

function renderAlerts(container, rows, thr) {
  var pill = rows.length ? '<span class="pill">' + rows.length + '</span>' : "";
  container.innerHTML = "<h2>" + ICONS.alert + " Price-jump alerts " + pill + "</h2>";
  var box = document.createElement("div");
  if (!rows.length) {
    box.innerHTML = '<p class="none">No item moved ≥ ' + thr +
      '% week-over-week in this range.</p>';
  } else {
    var sorted = rows.slice().sort(function (a, b) { return b.pct - a.pct; });
    var top = sorted[0];
    box.innerHTML =
      '<div class="alert-top">Largest jump: <b>' + esc(top.name) + '</b> ▲ ' +
      top.pct + '% (' + top.date + ')</div>' +
      sorted.map(function (r) {
        return '<div class="alert-chip"><span class="al-name">' + esc(r.name) + '</span>' +
          '<span class="al-cat">' + esc(r.category) + '</span>' +
          '<span class="al-date">' + r.date + '</span>' +
          '<span class="al-price">' + money(r.price) + '</span>' +
          '<span class="al-pct">+' + r.pct + '%</span></div>';
      }).join("");
  }
  container.appendChild(box);
}

function toast(msg) {
  var t = el("toast");
  t.textContent = msg;
  t.className = "show";
  clearTimeout(toast._t);
  toast._t = setTimeout(function () { t.className = ""; }, 2600);
}

/* ---------- views: trends / compare / data ------------------------------ */
function renderTrends(container, pivot, sub) {
  if (!hasChart()) {
    renderEmpty(container, "Charts unavailable",
      "Chart.js could not be loaded. Check your connection, or use the Data tab.", "trend");
    return;
  }
  container.innerHTML =
    '<div class="viewhead"><span class="viewtitle">Trends</span>' +
    '<div class="subnav" role="tablist">' +
    '<button class="subtab' + (sub === "items" ? " on" : "") + '" data-sub="items" role="tab">Item prices</button>' +
    '<button class="subtab' + (sub === "index" ? " on" : "") + '" data-sub="index" role="tab">Basket index</button>' +
    '</div></div><div class="chartbox"><canvas id="trendCanvas" role="img" aria-label="Price trends chart"></canvas></div>' +
    '<p class="hint">' + (sub === "items"
      ? "Hover the chart to read exact prices. Toggle to the basket index to compare overall cost of living."
      : "Equal-weight cost of the whole basket, indexed to 100 at the start of the range.") + '</p>';
  container.querySelectorAll(".subtab").forEach(function (b) {
    b.addEventListener("click", function () { renderTrends(container, pivot, b.dataset.sub); });
  });
  destroyChart();
  var canvas = el("trendCanvas");
  var labels = pivot.dates;
  if (sub === "index") {
    activeChart = new Chart(canvas, {
      type: "line",
      data: { labels: labels, datasets: [{ label: "Basket cost index",
        data: pivot.index, borderColor: BRAND, borderWidth: 2,
        tension: 0.2, pointRadius: 0, fill: true,
        backgroundColor: BRAND_SOFT }] },
      options: baseOptions("Index (start = 100)", function (v) { return Number(v).toFixed(1); })
    });
  } else {
    var sets = pivot.items.map(function (it, k) {
      return { label: it.name, data: it.prices, borderColor: PALETTE[k % PALETTE.length],
               borderWidth: 2, tension: 0.25, pointRadius: 0 };
    });
    activeChart = new Chart(canvas, {
      type: "line",
      data: { labels: labels, datasets: sets },
      options: baseOptions("Price (PKR)", money)
    });
  }
}

function renderCompare(container, pivot) {
  if (!hasChart()) {
    renderEmpty(container, "Charts unavailable",
      "Chart.js could not be loaded. Check your connection, or use the Data tab.", "trend");
    return;
  }
  var sorted = pivot.items.slice().sort(function (a, b) { return a.pct - b.pct; });
  var labels = sorted.map(function (it) { return it.name; });
  var vals = sorted.map(function (it) { return Number(it.pct.toFixed(1)); });
  var colors = vals.map(function (v) { return v >= 0 ? UP : DOWN; });
  container.innerHTML =
    '<div class="viewhead"><span class="viewtitle">Compare basket</span>' +
    '<span class="view-sub">% change since the start of the range</span></div>' +
    '<div class="chartbox"><canvas id="compareCanvas" role="img" aria-label="Basket comparison chart"></canvas></div>' +
    '<p class="hint">Which goods rose (or fell) most over the selected period.</p>';
  destroyChart();
  activeChart = new Chart(el("compareCanvas"), {
    type: "bar",
    data: { labels: labels, datasets: [{ data: vals, backgroundColor: colors,
      borderRadius: 6, categoryPercentage: 0.7, barPercentage: 0.8 }] },
    options: {
      indexAxis: "y", responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: INK, padding: 10, cornerRadius: 8,
          callbacks: { label: function (c) { return " " + pct(c.value); } } }
      },
      scales: {
        x: { grid: { color: GRID }, border: { display: false },
             ticks: { color: TICK, font: { family: "Inter", size: 12 } },
             title: { display: true, text: "% change", color: TICK,
                      font: { family: "Inter", size: 12 } } },
        y: { grid: { display: false }, border: { display: false },
             ticks: { color: INK, font: { family: "Inter", size: 12 } } }
      }
    }
  });
}

function renderData(container, pivot) {
  if (!pivot.items.length) {
    renderEmpty(container, "No rows in this window",
      "Widen the date range or re-enable some items.", "trend");
    return;
  }
  var sorted = pivot.items.slice().sort(function (a, b) { return b.pct - a.pct; });
  var rows = sorted.map(function (it) {
    return "<tr><td class='nm'>" + esc(it.name) + "</td><td>" + esc(it.category) +
      "</td><td>" + esc(it.unit) + "</td><td>" + money(it.first) + "</td><td>" +
      money(it.last) + "</td><td class='chg " + pctCls(it.pct) + "'>" + pct(it.pct) +
      "</td></tr>";
  }).join("");
  container.innerHTML =
    '<div class="viewhead"><span class="viewtitle">Data</span>' +
    '<span class="view-sub">' + pivot.items.length + " items · " + pivot.dates.length +
    " weekly points · <a href='/methodology'>methodology</a></span></div>" +
    '<div class="tablebox"><table><thead><tr><th scope="col">Item</th>' +
    '<th scope="col">Category</th><th scope="col">Unit</th>' +
    '<th scope="col">Range start</th><th scope="col">Latest</th>' +
    '<th scope="col">Change</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
}

/* ==========================================================================
   Inflation-intelligence helpers (pure functions over the pivot window).
   Everything these produce is computed from the numbers already on screen —
   no model, no estimates, nothing hidden.
   ========================================================================== */

function daysAgo(n) {
  var d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

/* Equal-weight per-category summary of the selected window. */
function categoryChanges(pivot) {
  var byCat = {};
  (pivot.items || []).forEach(function (it) {
    (byCat[it.category] = byCat[it.category] || []).push(it.pct);
  });
  return Object.keys(byCat).map(function (cat) {
    var arr = byCat[cat], sum = 0, up = 0, down = 0;
    arr.forEach(function (v) { sum += v; if (v >= 0) up++; else down++; });
    return { category: cat, count: arr.length, pct: sum / arr.length, up: up, down: down };
  }).sort(function (a, b) { return b.pct - a.pct; });
}

function topMovers(pivot, k) {
  var sorted = (pivot.items || []).slice().sort(function (a, b) { return b.pct - a.pct; });
  var risers = sorted.filter(function (it) { return it.pct > 0; }).slice(0, k);
  var fallers = sorted.filter(function (it) { return it.pct < 0; }).slice(-k).reverse();
  return { risers: risers, fallers: fallers };
}

/* Rules-based plain-language summary. It only cites numbers that are rendered
   next to it - transparent by construction. */
function narrative(pivot, metrics) {
  if (!pivot.items || !pivot.items.length) return "";
  var m = topMovers(pivot, 1);
  var cats = categoryChanges(pivot);
  var risen = pivot.items.filter(function (it) { return it.pct >= 0; }).length;
  var avg = pivot.items.reduce(function (s, it) { return s + it.pct; }, 0) / pivot.items.length;
  var parts = [];
  parts.push(
    risen + " of " + pivot.items.length + " tracked items rose over this window" +
    (metrics && metrics.weeks ? " (" + metrics.weeks + " weeks)" : "") +
    "; the average move was " + pct(avg) + "."
  );
  if (cats.length) {
    var lead = cats[0], lag = cats[cats.length - 1];
    parts.push(
      esc(lead.category) + " moved most (" + pct(lead.pct) + " average across " +
      lead.count + " items — " + lead.up + " up, " + lead.down + " down)" +
      (lag !== lead ? ", while " + esc(lag.category) + " was calmest (" + pct(lag.pct) + ")." : ".")
    );
  }
  if (m.risers.length) {
    var r = m.risers[0];
    parts.push("Biggest rise: " + esc(r.name) + " " + pct(r.pct) +
      " (" + money(r.first) + " → " + money(r.last) + " " + esc(r.unit) + ").");
  }
  if (m.fallers.length) {
    var f = m.fallers[0];
    parts.push("Biggest fall: " + esc(f.name) + " " + pct(f.pct) + ".");
  }
  parts.push("Generated from the visible numbers only — no model, no estimates.");
  return parts.join(" ");
}

function renderSparkline(prices, w, h, color) {
  var data = (prices || []).filter(function (v) { return v != null; });
  if (data.length < 2) return "";
  var min = Math.min.apply(null, data), max = Math.max.apply(null, data);
  var span = (max - min) || 1;
  var step = w / (data.length - 1);
  var pts = data.map(function (v, i) {
    return (i * step).toFixed(1) + "," + (h - 2 - ((v - min) / span) * (h - 4)).toFixed(1);
  }).join(" ");
  var up = data[data.length - 1] >= data[0];
  var c = color || (up ? UP : DOWN);
  return '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" width="' + w +
    '" height="' + h + '" role="img" aria-label="Price trend">' +
    '<polyline fill="none" stroke="' + c + '" stroke-width="2" points="' + pts + '"/></svg>';
}

/* "What changed & why" panel: top movers, per-category bars, and the summary. */
function renderWhyPanel(container, pivot, metrics) {
  if (!pivot.items || !pivot.items.length) { container.innerHTML = ""; return; }
  var m = topMovers(pivot, 3);
  var cats = categoryChanges(pivot);
  var maxAbs = Math.max.apply(null, cats.map(function (c) { return Math.abs(c.pct); }).concat([1]));
  var chip = function (it) {
    return '<div class="why-chip"><span class="al-name">' + esc(it.name) +
      '</span><span class="al-cat">' + esc(it.category) + '</span>' +
      '<span class="al-pct ' + pctCls(it.pct) + '">' + pct(it.pct) + '</span></div>';
  };
  var bars = cats.map(function (c) {
    return '<div class="catbar"><span class="catbar-label">' + esc(c.category) + '</span>' +
      '<span class="catbar-track"><span class="catbar-fill ' + pctCls(c.pct) +
      '" style="width:' + Math.max(2, Math.round(Math.abs(c.pct) / maxAbs * 100)) + '%"></span></span>' +
      '<span class="catbar-val ' + pctCls(c.pct) + '">' + pct(c.pct) + '</span>' +
      '<span class="catbar-sub">' + c.count + " items</span></div>";
  }).join("");
  container.innerHTML =
    '<div class="viewhead"><span class="viewtitle">What changed &amp; why</span>' +
    '<span class="view-sub">equal-weight · computed from the visible numbers</span></div>' +
    '<div class="why-grid">' +
      '<div class="why-box"><h3>Biggest increases</h3>' + m.risers.map(chip).join("") + '</div>' +
      '<div class="why-box"><h3>Biggest decreases</h3>' +
        (m.fallers.length ? m.fallers.map(chip).join("") : '<p class="hint">Nothing fell in this window.</p>') +
      '</div>' +
      '<div class="why-box why-cats"><h3>By category (average change)</h3>' + bars + '</div>' +
    '</div>' +
    '<p class="why-note">' + narrative(pivot, metrics) + '</p>';
}