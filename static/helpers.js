/* ==========================================================================
   Render layer (state-free). Loaded before app.js.
   Design rules live in style.css tokens; icons are inline Lucide-style SVGs.
   ========================================================================== */
var PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9",
  "#D55E00", "#6A3D9A", "#8C8C8C", "#B15928", "#4E79A7", "#E0A106"];

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

/* ---------- charts ------------------------------------------------------ */
function baseOptions(yTitle, tooltipFmt) {
  return {
    responsive: true,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { labels: { color: "#17181c", usePointStyle: true,
        pointStyleWidth: 9, boxPadding: 8,
        font: { family: "Inter", size: 12, weight: 500 } } },
      tooltip: { backgroundColor: "#17181c", titleColor: "#ffffff",
        bodyColor: "#e7eef7", padding: 10, cornerRadius: 8, displayColors: true,
        callbacks: { label: function (c) {
          var s = c.dataset.label || "";
          return " " + s + ": " + (tooltipFmt ? tooltipFmt(c.value) : c.value);
        } } }
    },
    scales: {
      x: { grid: { color: "#eceef1" }, border: { color: "#e3e6ea" },
           ticks: { color: "#5c6470", maxTicksLimit: 10,
                    font: { family: "Inter", size: 12 } } },
      y: { beginAtZero: false, grid: { color: "#eceef1" },
           border: { display: false },
           ticks: { color: "#5c6470", font: { family: "Inter", size: 12 } },
           title: { display: !!yTitle, text: yTitle || "", color: "#5c6470",
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
        data: pivot.index, borderColor: "#b45309", borderWidth: 2,
        tension: 0.2, pointRadius: 0, fill: true,
        backgroundColor: "rgba(180,83,9,.08)" }] },
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
  var sorted = pivot.items.slice().sort(function (a, b) { return a.pct - b.pct; });
  var labels = sorted.map(function (it) { return it.name; });
  var vals = sorted.map(function (it) { return Number(it.pct.toFixed(1)); });
  var colors = vals.map(function (v) { return v >= 0 ? "#c2410c" : "#0a7d4f"; });
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
        tooltip: { backgroundColor: "#17181c", padding: 10, cornerRadius: 8,
          callbacks: { label: function (c) { return " " + pct(c.value); } } }
      },
      scales: {
        x: { grid: { color: "#eceef1" }, border: { display: false },
             ticks: { color: "#5c6470", font: { family: "Inter", size: 12 } },
             title: { display: true, text: "% change", color: "#5c6470",
                      font: { family: "Inter", size: 12 } } },
        y: { grid: { display: false }, border: { display: false },
             ticks: { color: "#17181c", font: { family: "Inter", size: 12 } } }
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