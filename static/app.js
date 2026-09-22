/* Controller: state, data fetching, wiring. Depends on helpers.js. */
(function () {
  var items = [], selected = new Set(), activeCats = new Set();
  var tab = "trends", trendSub = "items", threshold = 5, start = "", end = "";
  var pivot = { dates: [], index: [], items: [] };
  var reqId = 0;
  var selfUpdateAt = 0;   /* when this tab last wrote, so we ignore its own echo */

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
        renderWhyPanel(el("moversPanel"), pivot, metrics);
        checkWatchlist(pivot);
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
      { label: "Basket change (equal-weight)",
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
    /* Freshness semantics for a WEEKLY series: the newest point is "fresh"
       while the next observation is still due (cadence + a grace week, i.e.
       <= 13 days). Amber from day 14 means "a weekly update is overdue",
       not merely "the number is a few days old". The tooltip always states
       the exact age in days so the colour can be checked against it. */
    var dot = el("freshDot");
    if (dot && m.last_date) {
      var ms = Date.now() - new Date(m.last_date + "T00:00:00Z").getTime();
      var ageDays = Math.floor(ms / 86400000);
      var fresh = ageDays <= 13;   /* 7-day cadence + one grace week */
      dot.className = "fresh-dot " + (fresh ? "fresh" : "stale");
      dot.title = "Data through " + m.last_date + " (" + ageDays + " days old)" +
        (fresh ? " — next weekly update due" : " — weekly update overdue");
    }
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
    else if (tab === "categories") renderCategoryView(con, pivot);
    else if (tab === "mybasket") renderMyBasket(con, pivot);
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
          else if (d.days) setStartEnd(daysAgo(Number(d.days)), "");
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
        searchTimer = setTimeout(function () {
          refreshItems();
          updateSearchPanel();
        }, 150);
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
    /* JSON export for developers/journalists: items + metrics + the series. */
    var ej = el("exportJson");
    if (ej) {
      ej.addEventListener("click", function () {
        Promise.all([
          getJSON("/api/series" + query()),
          getJSON("/api/metrics" + query()),
          getJSON("/api/items"),
        ]).then(function (res) {
          var metrics = res[1] || {};
          var blob = new Blob([JSON.stringify({
            generated_at: new Date().toISOString(),
            window: {
              /* resolve what the API actually used, not what the inputs were */
              requested: { start: start || null, end: end || null },
              start: metrics.first_date || start || null,
              end: metrics.last_date || end || null,
              weeks: metrics.weeks || null,
            },
            items: res[2], metrics: metrics, series: res[0],
          }, null, 2)], { type: "application/json" });
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "pakistan-prices_" + (start || "all") + ".json";
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
          toast("JSON downloaded");
        }, function () { toast("JSON export failed"); });
      });
    }
    el("updateNow").addEventListener("click", function () {
      runUpdate();
    });
  }

  /* ---------- categories view: equal-weight change per category ---------- */
  function renderCategoryView(container, pivot) {
    if (!pivot.items.length) {
      renderEmpty(container, "No rows in this window",
        "Widen the date range or re-enable some items.", "trend");
      return;
    }
    var cats = categoryChanges(pivot);
    var maxAbs = Math.max.apply(null, cats.map(function (c) { return Math.abs(c.pct); }).concat([1]));
    var bars = cats.map(function (c) {
      return '<div class="catbar"><span class="catbar-label">' + esc(c.category) + '</span>' +
        '<span class="catbar-track"><span class="catbar-fill ' + pctCls(c.pct) +
        '" style="width:' + Math.max(2, Math.round(Math.abs(c.pct) / maxAbs * 100)) + '%"></span></span>' +
        '<span class="catbar-val ' + pctCls(c.pct) + '">' + pct(c.pct) + '</span>' +
        '<span class="catbar-sub">' + c.count + " items · " + c.up + " up / " + c.down + " down</span></div>";
    }).join("");
    container.innerHTML =
      '<div class="viewhead"><span class="viewtitle">Categories</span>' +
      '<span class="view-sub">equal-weight average change over the window</span></div>' +
      '<div class="catbars">' + bars + '</div>' +
      '<p class="hint">Each category average is the simple mean of its items\u2019 changes — ' +
      'the same equal-weight method as the headline basket, so the numbers add up.</p>';
  }

  /* ---------- my basket: personal equal-weight basket + watchlist ---------- */
  function myBasketIds() {
    try { return JSON.parse(localStorage.getItem("myBasket") || "[]"); } catch (e) { return []; }
  }
  function saveMyBasketIds(names) {
    try { localStorage.setItem("myBasket", JSON.stringify(names)); } catch (e) { /* ignore */ }
  }
  function watchIds() {
    try { return JSON.parse(localStorage.getItem("watchlist") || "[]"); } catch (e) { return []; }
  }
  function saveWatchIds(names) {
    try { localStorage.setItem("watchlist", JSON.stringify(names)); } catch (e) { /* ignore */ }
  }

  function renderMyBasket(container, pivot) {
    var chosen = myBasketIds();
    var byName = {};
    (pivot.items || []).forEach(function (it) { byName[it.name] = it; });
    var picked = chosen.filter(function (n) { return byName[n]; });
    var headline;
    if (picked.length) {
      var avg = picked.reduce(function (s, n) { return s + byName[n].pct; }, 0) / picked.length;
      headline = '<div class="mb-head"><span class="mb-total">Your basket: <b class="' +
        pctCls(avg) + '">' + pct(avg) + "</b> over this window</span>" +
        '<span class="hint">equal-weight average of ' + picked.length + " item(s)</span></div>";
    } else {
      headline = '<div class="mb-head"><span class="hint">Tick items below to build your own ' +
        'basket — the number updates with the date range you choose.</span></div>';
    }
    var watched = watchIds();
    var rows = (pivot.items || []).map(function (it) {
      var on = chosen.indexOf(it.name) !== -1;
      var bell = watched.indexOf(it.name) !== -1;
      return '<label class="mb-row' + (on ? " on" : "") + '">' +
        '<input type="checkbox" data-mb="' + esc(it.name) + '"' + (on ? " checked" : "") + "/>" +
        '<span class="mb-name">' + esc(it.name) + '</span>' +
        '<span class="al-cat">' + esc(it.category) + " · " + esc(it.unit) + '</span>' +
        '<span class="al-pct ' + pctCls(it.pct) + '">' + pct(it.pct) + "</span>" +
        '<button type="button" class="watch' + (bell ? " on" : "") +
        '" data-watch="' + esc(it.name) + '" title="Notify me when this item moves by at least the alert threshold">' +
        (bell ? "\u2605" : "\u2606") + "</button></label>";
    }).join("");
    container.innerHTML =
      '<div class="viewhead"><span class="viewtitle">My basket</span>' +
      '<span class="view-sub">your own equal-weight basket · saved on this device</span></div>' +
      headline +
      '<div class="mb-list">' + rows + "</div>" +
      '<p class="hint">The star marks watched items: while this page is open you get a toast ' +
      '(and a browser notification, if you allow it) whenever a watched item moves by at least ' +
      'the alert threshold. Device-local only — no account, no email, nothing leaves your browser.</p>';
    var boxes = container.querySelectorAll("[data-mb]");
    for (var i = 0; i < boxes.length; i++) {
      (function (box) {
        box.addEventListener("change", function () {
          var names = myBasketIds();
          var name = box.getAttribute("data-mb");
          if (box.checked) { if (names.indexOf(name) === -1) names.push(name); }
          else { names = names.filter(function (n) { return n !== name; }); }
          saveMyBasketIds(names);
          renderMyBasket(container, pivot);
        });
      })(boxes[i]);
    }
    var bells = container.querySelectorAll("[data-watch]");
    for (var j = 0; j < bells.length; j++) {
      (function (btn) {
        btn.addEventListener("click", function (ev) {
          ev.preventDefault();          /* stop the surrounding label from toggling */
          var names = watchIds();
          var name = btn.getAttribute("data-watch");
          var on = names.indexOf(name) !== -1;
          if (on) { names = names.filter(function (n) { return n !== name; }); }
          else {
            names.push(name);
            if (window.Notification && Notification.permission === "default") {
              try { Notification.requestPermission(); } catch (e) { /* ignore */ }
            }
            toast("Watching " + name + " — alerts at \u2265 " + thresholdVal() + "%");
          }
          saveWatchIds(names);
          renderMyBasket(container, pivot);
        });
      })(bells[j]);
    }
  }

  function checkWatchlist(pivot) {
    var names = watchIds();
    if (!names.length) return;
    var th = thresholdVal();
    (pivot.items || []).forEach(function (it) {
      if (names.indexOf(it.name) === -1) return;
      if (Math.abs(it.pct) >= th) {
        toast("\u23f0 " + it.name + " " + pct(it.pct) + " over the window");
        if (window.Notification && Notification.permission === "granted") {
          try {
            new Notification("Price alert: " + it.name, {
              body: pct(it.pct) + " over the selected window — now " + money(it.last) + " " + it.unit,
            });
          } catch (e) { /* ignore */ }
        }
      }
    });
  }

  /* ---------- search: instant answer card with sparkline ----------------- */
  function updateSearchPanel() {
    var panel = el("searchPanel");
    var box = el("search");
    if (!panel || !box) return;
    var term = box.value.trim().toLowerCase();
    if (!term) { panel.innerHTML = ""; return; }
    var byName = {};
    (pivot.items || []).forEach(function (it) { byName[it.name] = it; });
    var matches = items.filter(function (it) {
      return (it.name + " " + it.category).toLowerCase().indexOf(term) !== -1;
    }).slice(0, 3);
    if (!matches.length) {
      panel.innerHTML = '<span class="hint">No basket item matches \u201c' + esc(term) + '\u201d.</span>';
      return;
    }
    var lastDate = pivot.dates.length ? pivot.dates[pivot.dates.length - 1] : "\u2014";
    var cards = matches.map(function (it) {
      var p = byName[it.name];
      if (!p) return "";
      var prices = p.prices || [];
      var prev = prices.length > 1 ? prices[prices.length - 2] : p.first;
      return '<div class="search-card">' + renderSparkline(prices, 140, 40) +
        '<div class="sc-main"><span class="al-name">' + esc(it.name) + '</span>' +
        '<span class="al-cat">' + esc(it.category) + " · " + esc(it.unit) + '</span>' +
        '<span class="hint">updated ' + esc(lastDate) + '</span></div>' +
        '<div class="sc-nums"><span>prev ' + money(prev) + "</span>" +
        '<span>now <b>' + money(p.last) + "</b></span>" +
        '<span class="al-pct ' + pctCls(p.pct) + '">' + pct(p.pct) + "</span></div></div>";
    }).join("");
    panel.innerHTML = cards;
  }

  function sessionToken() {
    try { return window.sessionStorage.getItem("adminToken") || ""; } catch (e) { return ""; }
  }

  function jsonHeaders() {
    var h = { "Content-Type": "application/json" };
    var t = sessionToken();
    if (t) h["X-Admin-Token"] = t;
    return h;
  }

  function runUpdate() {
    var btn = el("updateNow");
    var badge = el("updatedBadge");
    var inner = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36L21 8"/><path d="M21 3v5h-5"/></svg> Updating\u2026';
    badge.textContent = "Updating\u2026";
    /* The write endpoint may be protected (ADMIN_TOKEN, or loopback-only on a
       public deployment). Ask for the token once on 401, and always surface the
       API's own error message instead of reporting a phantom success. */
    function attempt(alreadyPrompted) {
      fetch("/ingest/next", { method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ auto_approve: true }) })
        .then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (data) {
            return { ok: r.ok, status: r.status, data: data };
          });
        })
        .then(function (res) {
          if (!res.ok) {
            var apiErr = (res.data && res.data.error) || {};
            if (res.status === 401 && !alreadyPrompted) {
              var entered = window.prompt("Admin token (ADMIN_TOKEN) is required to update data:");
              if (entered) {
                try { window.sessionStorage.setItem("adminToken", entered); } catch (e) { /* ignore */ }
                attempt(true);
                return;
              }
            }
            toast((apiErr.message || ("Update failed (HTTP " + res.status + ")")) +
                  (apiErr.hint ? " \u2014 " + apiErr.hint : ""));
            badge.textContent = "Update blocked";
            return;
          }
          selfUpdateAt = Date.now();   /* swallow the live echo of our own write */
          if (res.data.counts && res.data.counts.pending) {
            toast("Ingested " + res.data.inserted + " point(s); " +
                  res.data.counts.pending + " pending review");
          } else {
            toast("Updated: " + res.data.inserted + " new point(s)");
          }
          badge.textContent = "Updated " + (res.data.for_week || "");
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

    attempt(false);
  }

  function toast(msg) {
    var t = el("toast");
    if (!t) return;
    t.textContent = msg;
    t.classList.add("show");
    if (toast._t) clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.classList.remove("show"); }, 3200);
  }

  /* Footer dataset stats: filled at boot, kept fresh by the live channel.
     Purely informative - a failed fetch must never disturb the dashboard. */
  function paintFootStats(data) {
    if (!data) return;
    var set = function (id, val) {
      var node = el(id);
      if (node && val != null) node.textContent = val;
    };
    set("footItems", data.items);
    set("footApproved", data.approved_points);
    set("footLatest", data.latest_date || "\u2014");
    set("footPending", data.pending_points);
  }

  function loadFootStats() {
    getJSON("/api/live").then(paintFootStats, function () { /* stay silent */ });
  }

  /* Push path: /api/stream reports a new data revision the moment the ingest
     job (or an admin approval) commits, so the view refreshes itself. */
  function onLive(data) {
    paintFootStats(data);
    if (Date.now() - selfUpdateAt < 5000) return;   /* our own write, already shown */
    if (data && data.items !== items.length) {
      toast("Basket changed \u2014 reloading");
      loadItems();                 /* the set of tracked items itself changed */
      return;
    }
    toast("New data published \u2014 view refreshed");
    load();
  }

  function init() {
    wire();
    loadItems();
    loadFootStats();
    /* Real-time transport: Server-Sent Events, with polling fallback. */
    if (window.Live) {
      Live.start({ onRefresh: onLive });
      setTimeout(function () {
        var node = el("footLive");
        if (!node) return;
        if (Live.mode() === "off") node.textContent = "static render (live updates off)";
        else if (Live.mode() === "poll") node.textContent = "polling fallback";
      }, 1500);
    } else {
      var node = el("footLive");
      if (node) node.textContent = "polling fallback";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();