/* Render layer (pure, state-free, loaded before app.js). */
var PALETTE = ["#f4c20d", "#22c55e", "#60a5fa", "#f472b6", "#a78bfa",
  "#34d399", "#f97316", "#38bdf8", "#e879f9", "#facc15", "#2dd4bf"];
var activeChart = null;

function el(id) { return document.getElementById(id); }
function destroyChart() { if (activeChart) { try { activeChart.destroy(); } catch (e) {} activeChart = null; } }
function todayISO() { return new Date().toISOString().slice(0, 10); }
function monthsAgo(n) { var d = new Date(); d.setMonth(d.getMonth() - n); return d.toISOString().slice(0, 10); }
function money(v) { return "Rs " + Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 }); }
function pct(v) { return (v >= 0 ? "+" : "") + Number(v).toFixed(1) + "%"; }
function pctCls(v) { return v >= 0 ? "up" : "down"; }
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

function baseOptions(yTitle, yFmt) {
  return {
    responsive: true,
    plugins: {
      legend: { labels: { color: "#dfe8f5", usePointStyle: true, pointStyleWidth: 9, boxPadding: 8, font: { family: "Inter", size: 12 } } },
      tooltip: { backgroundColor: "#101828", borderColor: "#f4c20d", borderWidth: 1, titleColor: "#ffffff", bodyColor: "#dfe8f5", padding: 10, cornerRadius: 8, callbacks: { label: function (c) { var s = c.dataset.label || ""; if (yFmt) { return " " + s + ": " + yFmt(c.value); } return " " + s; } } }
    },
    scales: {
      x: { grid: { color: "#ffffff14" }, ticks: { color: "#8ba0b8", font: { family: "Inter", size: 11 }, maxTicksLimit: 14 }, title: { display: false } },
      y: { beginAtZero: false, grid: { color: "#ffffff14" }, ticks: { color: "#8ba0b8", font: { family: "Inter", size: 11 } }, title: { display: true, text: yTitle || "", color: "#8ba0b8", font: { family: "Inter", size: 12 } } }
    }
  };
}

function spinBox(msg) { return '<div class="loading">' + (msg || "Loading…") + "</div>"; }

function renderKPIs(container, metrics, infl, alerts) {
  var card = function (k, v, cls, sub, accent) {
    return '<div class="kpi" style="' + (accent ? "border-color:" + accent + ";" : "") + '">' +
      '<span class="k">' + k + '</span><span class="v ' + cls + '">' + v + '</span>' +
      '<span class="s">' + sub + '</span></div>';
  };
  var has = metrics && metrics.count;
  var b = has ? metrics.basket_pct : 0;
  var range = (metrics.first_date || "—") + " → " + (metrics.last_date || "—");
  var ann = infl && infl.annualized_pct;
  var yoy = infl && infl.yoy_pct;
  container.innerHTML =
    card("Basket cost change", pct(b), pctCls(b), "equal-weight · " + (metrics.weeks || 0) + " wks · " + range) +
    card("Annualized inflation", (ann === undefined ? "—" : pct(ann)), pctCls(ann || 0), "implied per-year cost growth") +
    card("Year-over-year", (yoy === undefined || yoy === null) ? "n/a" : pct(yoy), pctCls(yoy || 0), "last 52 wks vs prior year") +
    card("Price jumps", alerts.length || 0, alerts.length ? "up" : "", "≥ " + (thresholdVal() || "5") + "% week-over-week");
}

function thresholdVal() { var t = el("threshold"); return t ? Number(t.value) || 5 : 5; }

function renderAlerts(container, rows, thr) {
  var pill = rows.length ? '<span class="pill">' + rows.length + "</span>" : "";
  container.innerHTML = "<h2>⚠️ Price-jump alerts " + pill + "</h2>";
  var box = document.createElement("div");
  if (!rows.length) {
    box.innerHTML = '<p class="none">✓ No item jumped ≥ ' + thr + '% week-on-week in this range.</p>';
  } else {
    var sorted = rows.slice().sort(function (a, b) { return b.pct - a.pct; });
    var top = sorted[0];
    var chips = sorted.map(function (r) {
      return '<div class="alert-chip"><span class="al-name">' + esc(r.name) + '</span>' +
        '<span class="al-cat">' + esc(r.category) + '</span>' +
        '<span class="al-date">' + r.date + '</span>' +
        '<span class="al-price">' + money(r.price) + '</span>' +
        '<span class="al-pct up">▲ ' + r.pct + '%</span></div>';
    }).join("");
    box.innerHTML = '<div class="alert-top">Largest jump: <b>' + esc(top.name) + '</b> ▲ ' + top.pct + '% (' + top.date + ")</div>" + chips;
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
function renderTrends(container, pivot, sub) {
  container.innerHTML =
    '<div class="viewhead"><span class="viewtitle">Trends</span>' +
    '<div class="subnav"><button class="subtab' + (sub === "items" ? " on" : "") + '" data-sub="items">Item prices</button>' +
    '<button class="subtab' + (sub === "index" ? " on" : "") + '" data-sub="index">Basket index</button></div></div>' +
    '<div class="chartbox"><canvas id="trendCanvas"></canvas></div>' +
    '<p class="hint">' + (sub === "items" ? "Hover or drag to inspect prices per item." : "Equal-weight cost of the whole basket, indexed to 100 at the range start.") + "</p>";
  document.querySelectorAll(".subtab").forEach(function (b) {
    b.addEventListener("click", function () { renderTrends(container, pivot, b.dataset.sub); });
  });
  destroyChart();
  var canvas = el("trendCanvas");
  var labels = pivot.dates;
  if (sub === "index") {
    activeChart = new Chart(canvas, {
      type: "line",
      data: { labels: labels, datasets: [{ label: "Basket cost index", data: pivot.index, borderColor: "#f4c20d", borderWidth: 2.5, tension: 0.2, pointRadius: 0, fill: true, backgroundColor: "#f4c20d22" }] },
      options: baseOptions("Index (start = 100)", null)
    });
  } else {
    var sets = pivot.items.map(function (it, k) {
      return { label: it.name, data: it.prices, borderColor: PALETTE[k % PALETTE.length],
               borderWidth: 2, tension: 0.25, pointRadius: 0, fill: false };
    });
    activeChart = new Chart(canvas, {
      type: "line",
      data: { labels: labels, datasets: sets },
      options: baseOptions("Price (PKR)", null)
    });
  }
}

function renderCompare(container, pivot) {
  var sorted = pivot.items.slice().sort(function (a, b) { return a.pct - b.pct; });
  var labels = sorted.map(function (it) { return it.name; });
  var vals = sorted.map(function (it) { return Number(it.pct.toFixed(1)); });
  var colors = vals.map(function (v) { return v >= 0 ? "#ef4444" : "#22c55e"; });
  container.innerHTML =
    '<div class="viewhead"><span class="viewtitle">Compare basket</span><span class="view-sub">% change since range start</span></div>' +
    '<div class="chartbox"><canvas id="compareCanvas"></canvas></div>' +
    '<p class="hint">Read left-to-right: which goods rose (or fell) most over the selected period.</p>';
  destroyChart();
  activeChart = new Chart(el("compareCanvas"), {
    type: "bar",
    data: { labels: labels, datasets: [{ data: vals, backgroundColor: colors, borderRadius: 6, barWidth: 18 }] },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#101828", borderColor: "#f4c20d", borderWidth: 1, padding: 10, cornerRadius: 8, bodyColor: "#dfe8f5", callbacks: { label: function (c) { return " " + (c.value >= 0 ? "+" : "") + c.value + "%"; } } }
      },
      scales: {
        x: { grid: { color: "#ffffff14" }, ticks: { color: "#8ba0b8", font: { family: "Inter", size: 11 } }, title: { display: true, text: "% change", color: "#8ba0b8" } },
        y: { grid: { display: false }, ticks: { color: "#dfe8f5", font: { family: "Inter", size: 12 } } }
      }
    }
  });
}

function renderData(container, pivot) {
  var sorted = pivot.items.slice().sort(function (a, b) { return b.pct - a.pct; });
  var rows = sorted.map(function (it) {
    return "<tr><td class='nm'>" + esc(it.name) + "</td><td>" + esc(it.category) + "</td>" +
      "<td>" + it.unit + "</td><td>" + money(it.first) + "</td><td>" + money(it.last) + "</td>" +
      "<td class='chg " + pctCls(it.pct) + "'>" + pct(it.pct) + "</td></tr>";
  }).join("");
  container.innerHTML =
    '<div class="viewhead"><span class="viewtitle">Data</span><span class="view-sub">' + pivot.items.length + " items · " + pivot.dates.length + " weekly points</span></div>" +
    '<div class="tablebox"><table><thead><tr><th>Item</th><th>Category</th><th>Unit</th><th>Range start</th><th>Latest</th><th>Change</th></tr></thead><tbody>' +
    rows + "</tbody></table></div>";
}