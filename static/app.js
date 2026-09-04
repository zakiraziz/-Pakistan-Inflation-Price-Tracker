(function () {
  var items = [], selected = new Set(), activeCats = new Set();
  var mode = "items", threshold = 5, start = "", end = "";
  var charts = {}, loaded = false;
  function setStartEnd(s, e) { start = s; end = e; el("start").value = s || ""; el("end").value = e || ""; markPreset(); }
  function markPreset() {
    document.querySelectorAll(".preset").forEach(function (b) {
      var d = b.dataset;
      var on = (d.all && start === "") || (d.months && start === monthsAgo(Number(d.months)));
      b.classList.toggle("on", on);
    });
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
        var cb = document.createElement("input");
        cb.type = "checkbox"; cb.checked = true; cb.dataset.id = i.id;
        cb.addEventListener("change", function (e) {
          e.target.checked ? selected.add(i.id) : selected.delete(i.id);
          if (loaded) load();
        });
        var txt = document.createElement("span");
        txt.textContent = i.name + " · " + i.unit;
        label.append(cb, txt); el("itemList").appendChild(label);
      });
      loaded = true;
      setStartEnd(monthsAgo(12), todayISO()); load();
    });
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
    if (loaded) load();
  }
  function query() {
    return "?start=" + (start || "") + "&end=" + (end || "") + "&items=" + Array.from(selected).join(",");
  }
  function fresh(canvas) { if (charts[canvas.id]) charts[canvas.id].destroy(); return canvas; }
  function draw(m) {
    el("itemChart").style.display = m === "items" ? "" : "none";
    el("indexChart").style.display = m === "index" ? "" : "none";
    document.querySelectorAll(".tab").forEach(function (t) { t.className = t.dataset.view === m ? "tab on" : "tab"; });
  }
  function load() {
    if (!selected.size) {
      el("chartHint").textContent = "Select at least one item (see Basket panel).";
      el("cards").innerHTML = ""; el("alertBox").innerHTML = '<p class="none">Select items to see alerts.</p>';
      el("alertCount").textContent = ""; el("infoLine").textContent = ""; return;
    }
    var ids = query();
    Promise.all([
      mode === "items" ? fetch("/api/series" + ids).then(r => r.json()) : Promise.resolve(null),
      mode === "index" ? fetch("/api/index" + ids).then(r => r.json()) : Promise.resolve(null),
      fetch("/api/metrics" + ids).then(r => r.json()),
      fetch("/api/alerts" + ids + "&threshold=" + threshold).then(r => r.json())
    ]).then(function (res) {
      var series = res[0], index = res[1], metrics = res[2], alerts = res[3];
      if (mode === "items") {
        var full = {};
        series.forEach(function (r) { (full[r.name] = full[r.name] || []).push({ x: r.date, y: r.price }); });
        renderItemChart(fresh(el("itemChart")), full);
        el("chartHint").textContent = "Hover / drag to inspect " + metrics.count + " item(s).";
      } else {
        renderIndexChart(fresh(el("indexChart")), index);
        el("chartHint").textContent = "Equal-weight basket cost, indexed to 100 at range start.";
      }
      var range = metrics.first_date + " → " + metrics.last_date + " (" + metrics.weeks + " wks)";
      renderCards(el("cards"), metrics, { range: range });
      renderAlerts(alerts, threshold);
      el("infoLine").textContent = range + " · " + metrics.count + " items · alert ≥" + threshold + "%";
    });
  }
  function updateNow() {
    var btn = el("updateNow");
    btn.disabled = true; btn.textContent = "Updating…";
    fetch("/ingest/next", { method: "POST" }).then(function (r) { return r.json(); }).then(function (j) {
      toast(j.inserted ? "✓ Ingested " + j.inserted + " new prices (week of " + j.for_week + ")" : "Already up to date.");
      btn.disabled = false; btn.textContent = "↻ Update now (ingest)"; load();
    }).catch(function () {
      toast("Update failed — is the server running?");
      btn.disabled = false; btn.textContent = "↻ Update now (ingest)";
    });
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
    t.addEventListener("click", function () { mode = t.dataset.view; draw(mode); load(); });
  });
  el("apply").addEventListener("click", function () {
    start = el("start").value; end = el("end").value;
    threshold = Number(el("threshold").value) || 5; markPreset(); load();
  });
  el("updateNow").addEventListener("click", updateNow);
  el("export").addEventListener("click", exportCSV);
  loadItems();
})();