/* Controller: state, data fetching, wiring. Depends on helpers.js. */
(function () {
  var items = [], selected = new Set(), activeCats = new Set();
  var tab = "trends", trendSub = "items", threshold = 5, start = "", end = "";
  var pivot = { dates: [], index: [], items: [] };
  var itemRows = [];

  function setStartEnd(s, e) { start = s; end = e; el("start").value = s || ""; el("end").value = e || ""; markPreset(); }
  function markPreset() {
    document.querySelectorAll(".preset").forEach(function (b) {
      var d = b.dataset;
      var on = (d.all && start === "") || (d.months && start === monthsAgo(Number(d.months)));
      b.classList.toggle("on", on);
    });
  }
  function query() {
    return "?start=" + (start || "") + "&end=" + (end || "") + "&items=" + Array.from(selected).join(",");
  }

  function loadItems() {
    fetch("/api/items").then(function (r) { return r.json(); }).then(function (data) {
      items = data; var cats = [], seen = {};
      data.forEach(function (i) {
        if (!seen[i.category]) { seen[i.category] = 1; cats.push(i.category); }
        selected.add(i.id); activeCats.add(i.category);
      });
      var catBox = el("categoryFilters");
      cats.forEach(function (c) {
        var span = document.createElement("span");
        span.textContent = c; span.className = "on";
        span.addEventListener("click", function () { toggleCategory(c, span); });
        catBox.appendChild(span);
      });
      data.forEach(function (i) {
        var label = document.createElement("label");
        label.dataset.name = i.name.toLowerCase();
        var cb = document.createElement("input");
        cb.type = "checkbox"; cb.checked = true; cb.dataset.id = i.id;
        cb.addEventListener("change", function (e) {
          e.target.checked ? selected.add(i.id) : selected.delete(i.id);
          load();
        });
        var txt = document.createElement("span");
        txt.textContent = i.name + " · " + i.unit;
        label.append(cb, txt); el("itemList").appendChild(label);
        itemRows.push({ id: i.id, label: label });
      });
      el("search").addEventListener("input", function (e) { applySearch(e.target.value); });
      setStartEnd(monthsAgo(12), todayISO()); load();
    });
  }

  function applySearch(q) {
    var s = (q || "").toLowerCase();
    itemRows.forEach(function (r) { r.label.style.display = (s && r.label.dataset.name.indexOf(s) < 0) ? "none" : ""; });
  }

  function toggleCategory(cat, span) {
    if (activeCats.has(cat)) { activeCats.delete(cat); span.className = "";
      items.forEach(function (i) { if (i.category === cat) selected.delete(i.id); });
    } else { activeCats.add(cat); span.className = "on";
      items.forEach(function (i) { if (i.category === cat) selected.add(i.id); });
    }
    document.querySelectorAll("#itemList input").forEach(function (cb) {
      var it = items.find(function (i) { return i.id == cb.dataset.id; });
      cb.checked = selected.has(it.id);
    });
    load();
  }

  function renderTab() {
    destroyChart();
    var con = el("view");
    if (tab === "trends") renderTrends(con, pivot, trendSub);
    else if (tab === "compare") renderCompare(con, pivot);
    else renderData(con, pivot);
  }

  function load() {
    if (!selected.size) { el("view").innerHTML = spinBox("Select at least one item — open the Basket panel."); return; }
    el("view").innerHTML = spinBox("Loading data…");
    var ids = query();
    Promise.all([
      fetch("/api/pivot" + ids).then(r => r.json()),
      fetch("/api/metrics" + ids).then(r => r.json()),
      fetch("/api/inflation" + ids).then(r => r.json()),
      fetch("/api/alerts" + ids + "&threshold=" + threshold).then(r => r.json())
    ]).then(function (res) {
      pivot = res[0]; var metrics = res[1], infl = res[2], alerts = res[3];
      if (!pivot.items.length) {
        el("view").innerHTML = spinBox("No data in this range — widen it or add items.");
        el("kpis").innerHTML = ""; renderAlerts(el("alertsPanel"), [], threshold);
        el("infoLine").textContent = "No data"; return;
      }
      renderKPIs(el("kpis"), metrics, infl, alerts);
      renderAlerts(el("alertsPanel"), alerts, threshold);
      el("infoLine").textContent = pivot.items.length + " items · " + pivot.dates.length + " weekly points";
      el("updatedBadge").textContent = "latest price " + pivot.dates[pivot.dates.length - 1];
      renderTab();
    }).catch(function () {
      el("view").innerHTML = spinBox("Could not reach the API — is the server running?");
    });
  }
  function updateNow() {
    var btn = el("updateNow");
    btn.disabled = true; btn.textContent = "Updating…";
    fetch("/ingest/next", { method: "POST" }).then(function (r) { return r.json(); }).then(function (j) {
      toast(j.inserted ? "✓ Ingested " + j.inserted + " new prices (week of " + j.for_week + ")" : "Already up to date.");
      btn.disabled = false; btn.textContent = "↻ Update data"; load();
    }).catch(function () { toast("Update failed — is the server running?"); btn.disabled = false; btn.textContent = "↻ Update data"; });
  }

  function exportCSV() {
    var a = document.createElement("a");
    a.href = "/api/series.csv" + query(); a.download = "prices.csv";
    document.body.appendChild(a); a.click(); a.remove(); toast("Downloading CSV…");
  }

  document.querySelectorAll(".preset").forEach(function (b) {
    b.addEventListener("click", function () {
      b.dataset.all ? setStartEnd("", "") : setStartEnd(monthsAgo(Number(b.dataset.months)), todayISO());
      load();
    });
  });
  document.querySelectorAll(".tab").forEach(function (t) {
    t.addEventListener("click", function () {
      tab = t.dataset.view;
      document.querySelectorAll(".tab").forEach(function (x) { x.className = "tab" + (x === t ? " on" : ""); });
      renderTab();
    });
  });
  el("apply").addEventListener("click", function () {
    start = el("start").value; end = el("end").value;
    threshold = Number(el("threshold").value) || 5; markPreset(); load();
  });
  el("updateNow").addEventListener("click", updateNow);
  el("export").addEventListener("click", exportCSV);
  loadItems();
})();