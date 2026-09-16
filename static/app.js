/* Controller: state, data fetching, wiring. Depends on helpers.js. */
(function () {
  var items = [], selected = new Set(), activeCats = new Set();
  var tab = "trends", trendSub = "items", threshold = 5, start = "", end = "";
  var pivot = { dates: [], index: [], items: [] };
  var reqId = 0;

  function setStartEnd(s, e) { start = s; end = e;
    el("start").value = s || ""; el("end").value = e || ""; markPreset(); }
  function markPreset() {
    document.querySelectorAll(".preset").forEach(function (b) {
      var d = b.dataset;
      var on = (d.all && start === "") ||
               (d.months && start === monthsAgo(Number(d.months)));
      b.classList.toggle("on", on);
    });
  }
  function query() {
    return "?start=" + (start || "") + "&end=" + (end || "") +
           "&items=" + Array.from(selected).join(",");
  }
  function getJSON(url, retries) {
    retries = retries || 1;
    var lastErr;
    return fetch(url, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status + " " + r.statusText);
        return r.json();
      })
      .catch(function (err) {
        lastErr = err;
        if (retries > 0) return getJSON(url, retries - 1);
        throw lastErr;
      });
  }

  function load() {
    /* Every call takes a new request id, so a slower earlier response can never
       overwrite a newer one - and rapid clicks are never silently dropped. */
    reqId++;
    var thisReq = reqId;
    renderSkeletons(el("kpis"), el("view"));
    var base = "/api/metrics" + query();
    var pivotUrl = "/api/pivot" + query();
    /* query() already starts with "?", so threshold must be appended with "&" -
       "/api/alerts?threshold=5" + "?start=..." would 500 the endpoint. */
    var alertsUrl = "/api/alerts" + query() + "&threshold=" + threshold;
    /* Alerts load on their own: one failing endpoint must never blank the whole
       dashboard (a burst of requests trips the 300/min rate limit -> 500). */
    getJSON(alertsUrl).then(function (alerts) {
      if (thisReq === reqId) renderAlerts(el("alertsPanel"), alerts);
    }, function () {
      if (thisReq === reqId) {
        renderError(el("alertsPanel"), "Alerts are unavailable right now.");
      }
    });
    Promise.all([getJSON(base), getJSON(pivotUrl)])
      .then(function (res) {
        if (thisReq !== reqId) return;
        var metrics = res[0], p = res[1];
        pivot = p || { dates: [], index: [], items: [] };
        renderCards(el("kpis"), metrics);
        renderTab();
        renderInfo(metrics);
        refreshItems();        /* now we know the % change for each item */
      }).catch(function (err) {
        if (thisReq !== reqId) return;
        renderError(el("view"), err.message || "Could not load data");
      });
  }

  function renderCards(kpiEl, m) {
    if (!m || m.count == null) { kpiEl.innerHTML = ""; return; }
    var basketPct = m.basket_pct != null ? m.basket_pct : 0;
    var riser = m.biggest_riser || null;
    var faller = m.biggest_faller || null;
    var cards = [
      { label: "Basket change",
        value: pct(basketPct),
        sub: money(m.start_total) + " \u2192 " + money(m.end_total),
        cls: pctCls(basketPct) },
      { label: "Items in view",
        value: String(m.count),
        sub: m.weeks + " weekly observations",
        cls: "" },
      { label: "Biggest riser",
        value: esc(riser ? riser.name : "\u2014"),
        sub: riser ? pct(riser.pct) : "",
        cls: "up" },
      { label: "Biggest faller",
        value: esc(faller ? faller.name : "\u2014"),
        sub: faller ? pct(faller.pct) : "",
        cls: "down" },
    ];
    kpiEl.innerHTML = cards.map(function (c) {
      return '<div class="kpi">' +
        '<span class="kpi-label">' + c.label + '</span>' +
        '<span class="kpi-value' + (c.cls ? ' ' + c.cls : '') + '">' + c.value + '</span>' +
        '<span class="kpi-sub">' + c.sub + '</span>' +
      '</div>';
    }).join("");
  }

  function renderInfo(m) {
    var elInfo = el("infoLine");
    var badge = el("updatedBadge");
    if (!m || m.count == null) {
      elInfo.textContent = "";
      if (badge) badge.textContent = "No data";
      return;
    }
    var rng = (m.first_date && m.last_date) ? m.first_date + " → " + m.last_date : "no data";
    elInfo.textContent = m.count + " items · " + m.weeks + " weeks · " + rng;
    /* Clear the "Loading latest data…" placeholder once real data arrives. */
    if (badge) badge.textContent = "Latest week " + (m.last_date || "unknown");
  }

  function renderAlerts(panel, alerts) {
    if (!alerts || alerts.length === 0) {
      panel.innerHTML =
        '<section class="alerts">' +
        '<div class="state" style="border-style:solid"><span class="icon">' + ICONS.check + '</span>' +
        '<span class="title">No alerts</span>' +
        '<span>No price moved more than ' + threshold + '% in the selected window.</span></div>' +
        '</section>';
      return;
    }
    var top = alerts[0];
    var chips = alerts.slice().map(function (a) {
      return '<div class="alert-chip">' +
        '<span class="al-name">' + esc(a.name) + ' <span class="al-cat">· ' + esc(a.category) + '</span></span>' +
        '<span class="al-price">' + money(a.price) + '</span>' +
        '<span class="al-date">' + esc(a.date) + '</span>' +
        '<span class="al-pct">' + pct(a.pct) + ' vs ' + money(a.prev_price) + '</span>' +
      '</div>';
    }).join("");
    panel.innerHTML =
      '<section class="alerts" aria-live="polite">' +
      '<h2><span>Alerts</span><span class="pill">' + alerts.length + '</span></h2>' +
      '<div class="alert-top">' +
        '<span class="icon">' + ICONS.alert + '</span>' +
        '<span>Largest jump in this window: <strong>' + esc(top.name) +
        '</strong> ' + pct(top.pct) + ' (' + esc(top.date) + ', ' + money(top.price) + ')</span>' +
      '</div>' + chips + '</section>';
  }

  function renderTab() {
    destroyChart();
    var con = el("view");
    if (tab === "trends") renderTrends(con, pivot, trendSub);
    else if (tab === "compare") renderCompare(con, pivot);
    else renderData(con, pivot);
  }

  /* ---------- basket filters (search + categories + item picker) -------- */
  function changes() {
    var map = {};
    (pivot.items || []).forEach(function (it) { map[it.name] = it.pct; });
    return map;
  }

  function visibleItems() {
    var box = el("search");
    var term = box ? box.value.trim().toLowerCase() : "";
    return items.filter(function (it) {
      if (activeCats.size && !activeCats.has(it.category)) return false;
      if (!term) return true;
      return (it.name + " " + it.category).toLowerCase().indexOf(term) !== -1;
    });
  }

  function refreshItems() {
    renderItems(el("itemList"), visibleItems(), selected,
      function (id, on) { if (on) selected.add(id); else selected.delete(id); },
      changes());
  }

  /* Category chips decide which categories are charted; "All items" clears. */
  function pickCategory(cat) {
    if (!cat) activeCats.clear();
    else if (activeCats.has(cat)) activeCats.delete(cat);
    else activeCats.add(cat);
    selected.clear();
    visibleItems().forEach(function (it) { selected.add(it.id); });
    renderCategories(el("categoryFilters"), items, activeCats, pickCategory);
    refreshItems();
    load();
  }

  /* Boots the basket: /api/items -> chips + checkboxes -> first render. */
  function loadItems() {
    getJSON("/api/items").then(function (rows) {
      items = rows || [];
      selected.clear();
      activeCats.clear();
      items.forEach(function (it) { selected.add(it.id); });
      renderCategories(el("categoryFilters"), items, activeCats, pickCategory);
      refreshItems();
      load();
    }).catch(function (err) {
      renderError(el("view"), err.message || "Could not load the item list");
    });
  }

  function wire() {
    el("apply").addEventListener("click", function () {
      var s = el("start").value, e = el("end").value;
      if (s && e && s > e) { toast("Start date must be before end date"); return; }
      setStartEnd(s || start, e || end);
      load();
    });
    el("threshold").addEventListener("change", function () {
      threshold = thresholdVal();
      load();
    });
    var tabs = document.querySelectorAll(".tab");
    for (var i = 0; i < tabs.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          tab = btn.dataset.view;
          for (var j = 0; j < tabs.length; j++) {
            tabs[j].classList.remove("on");
            tabs[j].setAttribute("aria-selected", "false");
          }
          btn.classList.add("on");
          btn.setAttribute("aria-selected", "true");
          renderTab();
        });
      })(tabs[i]);
    }
    var presets = document.querySelectorAll(".preset");
    for (var k = 0; k < presets.length; k++) {
      (function (b) {
        b.addEventListener("click", function () {
          var d = b.dataset;
          if (d.all) setStartEnd("", "");
          else if (d.months) setStartEnd(monthsAgo(Number(d.months)), "");
          load();
        });
      })(presets[k]);
    }
    var searchBox = el("search");
    if (searchBox) {
      var searchTimer = null;
      searchBox.addEventListener("input", function () {
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = setTimeout(refreshItems, 150);
      });
    }
    el("export").addEventListener("click", function () {
      var csvUrl = "/api/series.csv" + query();
      var a = document.createElement("a");
      a.href = csvUrl;
      a.download = "pakistan-prices_" + (start || "all") + ".csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
    });
    el("updateNow").addEventListener("click", function () {
      runUpdate();
    });
  }

  function runUpdate() {
    var btn = el("updateNow");
    var badge = el("updatedBadge");
    var inner = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36L21 8"/><path d="M21 3v5h-5"/></svg> Updating\u2026';
    badge.textContent = "Updating\u2026";
    fetch("/ingest/next", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auto_approve: true }) })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.counts && data.counts.pending) {
          toast("Ingested " + data.inserted + " point(s); " +
                data.counts.pending + " pending review");
        } else {
          toast("Updated: " + data.inserted + " new point(s)");
        }
        badge.textContent = "Updated " + (data.for_week || "");
        load();
      })
      .catch(function (err) {
        toast("Update failed: " + (err.message || "unknown error"));
      })
      .finally(function () {
        btn.disabled = false;
        btn.innerHTML = inner;
      });
  }

  function toast(msg) {
    var t = el("toast");
    if (!t) return;
    t.textContent = msg;
    t.classList.add("show");
    if (toast._t) clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.classList.remove("show"); }, 3200);
  }

  function init() {
    wire();
    loadItems();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();