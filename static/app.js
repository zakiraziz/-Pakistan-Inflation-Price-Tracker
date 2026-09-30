/* Dashboard controller: fetch data, render Chart.js, surface alerts. */
(async function () {
  var PALETTE = ["#f4c20d", "#22c55e", "#60a5fa", "#f472b6", "#a78bfa",
    "#34d399", "#f97316", "#38bdf8", "#e879f9", "#facc15", "#2dd4bf"];
  var items = [], selected = new Set(), activeCategories = new Set();
  var $ = function (id) { return document.getElementById(id); };

  function todayISO() { return new Date().toISOString().slice(0, 10); }
  function monthsAgo(n) { var d = new Date(); d.setMonth(d.getMonth() - n); return d.toISOString().slice(0, 10); }

  async function loadItems() {
    items = await (await fetch("/api/items")).json();
    var cats = [], seen = {};
    items.forEach(function (i) { if (!seen[i.category]) { seen[i.category] = 1; cats.push(i.category); } selected.add(i.id); activeCategories.add(i.category); });
    var catBox = $("categoryFilters");
    cats.forEach(function (c) {
      var span = document.createElement("span");
      span.textContent = c; span.className = "on";
      span.addEventListener("click", function () { toggleCategory(c, span); });
      catBox.appendChild(span);
    });
    var il = $("itemList");
    items.forEach(function (i) {
      var label = document.createElement("label");
      var cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = true; cb.dataset.id = i.id;
      cb.addEventListener("change", function (e) { e.target.checked ? selected.add(i.id) : selected.delete(i.id); load(); });
      var txt = document.createElement("span"); txt.textContent = i.name + " · " + i.unit;
      label.append(cb, txt); il.appendChild(label);
    });
  }

  function toggleCategory(cat, span) {
    if (activeCategories.has(cat)) {
      activeCategories.delete(cat); span.className = "";
      items.forEach(function (i) { if (i.category === cat) selected.delete(i.id); });
    } else {
      activeCategories.add(cat); span.className = "on";
      items.forEach(function (i) { if (i.category === cat) selected.add(i.id); });
    }
    document.querySelectorAll("#itemList input").forEach(function (cb) {
      var it = items.find(function (i) { return i.id == cb.dataset.id; });
      cb.checked = selected.has(it.id);
    });
    load();
  }

  var full = {};
  async function fetchSeries(start, end) {
    var ids = Array.from(selected).join(",");
    var rows = await (await fetch("/api/series?start=" + start + "&end=" + end + "&items=" + ids)).json();
    full = {};
    rows.forEach(function (r) { (full[r.name] = full[r.name] || []).push({ x: r.date, y: r.price }); });
  }

  function renderChart() {
    var names = Object.keys(full);
    var datasets = names.map(function (n, k) {
      return { label: n, data: full[n], borderColor: PALETTE[k % PALETTE.length],
        backgroundColor: PALETTE[k % PALETTE.length] + "22", borderWidth: 2, tension: 0.25, pointRadius: 0 };
    });
    new Chart($("priceChart"), {
      type: "line", data: { datasets: datasets },
      options: {
        responsive: true,
        plugins: { tooltip: { mode: "index", intersect: false }, legend: { labels: { color: "#e2e8f0" } } },
        scales: {
          x: { type: "time", time: { unit: "month" }, title: { display: true, text: "Date", color: "#94a3b8" } },
          y: { title: { display: true, text: "Price (PKR)", color: "#94a3b8" }, beginAtZero: false }
        }
      }
    });
  }

  function renderCards() {
    var names = Object.keys(full), gainers = [], losers = [], tS = 0, tE = 0, n = 0;
    names.forEach(function (name) {
      var d = full[name]; if (d.length < 2) return;
      var f = d[0].y, l = d[d.length - 1].y; tS += f; tE += l; n++;
      var pct = (l - f) / f * 100; gainers.push({ name: name, pct: pct }); losers.push({ name: name, pct: pct });
    });
    gainers.sort(function (a, b) { return b.pct - a.pct; });
    losers.sort(function (a, b) { return a.pct - b.pct; });
    var basket = n ? (tE - tS) / tS * 100 : 0;
    var mk = function (k, v, cls, extra) { return '<div class="card"><div class="k">' + k + '</div><div class="v ' + cls + '">' + v + '</div><small>' + extra + '</small></div>'; };
    $("cards").innerHTML =
      mk("Basket change (avg)", basket.toFixed(1) + "%", basket >= 0 ? "up" : "down", "since " + $("start").value) +
      mk("Biggest riser", gainers[0] ? gainers[0].name : "-", "up", gainers[0] ? "+" + gainers[0].pct.toFixed(1) + "%" : "") +
      mk("Biggest fall", losers.length ? losers[0].name : "-", "down", losers.length ? losers[0].pct.toFixed(1) + "%" : "");
  }

  async function renderAlerts() {
    var thr = $("threshold").value;
    var rows = await (await fetch("/api/alerts?threshold=" + thr)).json();
    var box = $("alertBox");
    if (!rows.length) { box.innerHTML = '<p class="none">No items jumped &ge; ' + thr + '% week-on-week.</p>'; return; }
    var t = "<table><tr><th>Item</th><th>Category</th><th>Week</th><th>Price</th><th>Jump</th></tr>";
    rows.forEach(function (r) {
      t += "<tr><td>" + r.name + "</td><td>" + r.category + "</td><td>" + r.date +
           "</td><td>Rs " + r.price.toFixed(2) + "</td><td class=\"up\">+" + r.pct + "%</td></tr>";
    });
    box.innerHTML = t + "</table>";
  }

  async function load() {
    $("chartHint").textContent = selected.size ? "Showing " + selected.size + " item(s). Hover to inspect." : "Select at least one item.";
    if (!selected.size) return;
    await fetchSeries($("start").value, $("end").value);
    renderChart(); renderCards(); renderAlerts();
  }

  function resetDates() { if (!$("end").value) $("end").value = todayISO(); if (!$("start").value) $("start").value = monthsAgo(12); }

  $("apply").addEventListener("click", load);
  await loadItems();
  resetDates();
  await load();
})();