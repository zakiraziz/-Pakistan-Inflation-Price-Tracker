/* Pure render helpers. Loaded before app.js. */
var PALETTE = ["#f4c20d", "#22c55e", "#60a5fa", "#f472b6", "#a78bfa",
  "#34d399", "#f97316", "#38bdf8", "#e879f9", "#facc15", "#2dd4bf"];

function el(id) { return document.getElementById(id); }
function todayISO() { return new Date().toISOString().slice(0, 10); }
function monthsAgo(n) { var d = new Date(); d.setMonth(d.getMonth() - n); return d.toISOString().slice(0, 10); }
function money(v) { return "Rs " + Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 }); }
function pct(v) { return (v >= 0 ? "+" : "") + Number(v).toFixed(1) + "%"; }
function pctCls(v) { return v >= 0 ? "up" : "down"; }

function baseOptions() {
  return {
    responsive: true,
    plugins: { legend: { labels: { color: "#e2e8f0", boxPadding: 8 } },
               tooltip: { mode: "index", intersect: false,
                          titleColor: "#e2e8f0", bodyColor: "#e2e8f0" } },
    scales: {
      x: { type: "time", time: { unit: "month" },
           title: { display: true, text: "Date", color: "#94a3b8" } },
      y: { beginAtZero: false }
    }
  };
}

function beforeEachRange() { return { plugins: { legend: { onClick: function () {} } } }; }

function renderItemChart(canvas, full) {
  var names = Object.keys(full);
  var datasets = names.map(function (n, k) {
    return { label: n, data: full[n],
             borderColor: PALETTE[k % PALETTE.length],
             backgroundColor: PALETTE[k % PALETTE.length] + "22",
             borderWidth: 2, tension: 0.25, pointRadius: 0 };
  });
  var opts = baseOptions();
  opts.scales.y.title = { display: true, text: "Price (PKR)", color: "#94a3b8" };
  new Chart(canvas, { type: "line", data: { datasets: datasets }, options: opts });
}

function renderIndexChart(canvas, series) {
  var data = series.map(function (p) { return { x: p.date, y: p.index }; });
  var opts = baseOptions();
  opts.scales.y.title = { display: true, text: "Index (start = 100)", color: "#94a3b8" };
  opts.scales.y.suggestedMin = 80;
  new Chart(canvas, {
    type: "line",
    data: { datasets: [{ label: "Basket cost index", data: data,
                         borderColor: "#f4c20d", backgroundColor: "#f4c20d22",
                         borderWidth: 2.5, tension: 0.2, pointRadius: 0 }] },
    options: opts
  });
}

function renderCards(box, m, labels) {
  var mk = function (k, v, cls, extra) {
    return '<div class="card"><div class="k">' + k + '</div>' +
           '<div class="v ' + cls + '">' + v + '</div><small>' + extra + '</small></div>';
  };
  var r = m.biggest_riser, f = m.biggest_faller;
  box.innerHTML =
    mk("Basket change", pct(m.basket_pct ?? 0), pctCls(m.basket_pct ?? 0), "equal-weight, " + labels.range) +
    mk("Biggest riser", r ? r.name : "—", "up", r ? pct(r.pct) : "") +
    mk("Biggest faller", f ? f.name : "—", "down", f ? pct(f.pct) : "") +
    mk("Scope", m.count + " items", "", m.weeks + " weekly points · " + money(m.start_total) + " → " + money(m.end_total));
}

function renderAlerts(rows, thr) {
  var box = el("alertBox"), pill = el("alertCount");
  pill.textContent = rows.length ? rows.length + "" : "";
  if (!rows.length) {
    box.innerHTML = '<p class="none">✓ No item jumped ≥ ' + thr + '% week-on-week in this range.</p>';
    return;
  }
  rows.sort(function (a, b) { return b.pct - a.pct; });
  var top = rows[0];
  var badges = "";
  rows.forEach(function (r) {
    badges += '<div class="alert-chip"><span class="al-name">' + r.name + '</span>' +
              '<span class="al-cat">' + r.category + '</span>' +
              '<span class="al-date">' + r.date + '</span>' +
              '<span class="al-price">' + money(r.price) + '</span>' +
              '<span class="al-pct up">▲ ' + r.pct + '%</span></div>';
  });
  box.innerHTML =
    '<div class="alert-top">Largest jump this window: <b>' + top.name + '</b> ▲ ' + top.pct + '%' +
    ' (' + top.date + ')</div>' + badges;
}

function toast(msg) {
  var t = el("toast");
  t.textContent = msg;
  t.className = "show";
  clearTimeout(toast._t);
  toast._t = setTimeout(function () { t.className = ""; }, 2600);
}