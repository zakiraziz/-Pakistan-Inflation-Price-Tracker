/* live.js - keeps the dashboard in sync with the server in real time.
 *
 * Transport: Server-Sent Events first - one long-lived connection, instant
 * pushes over /api/stream. If a stream cannot be kept open (old browser, a
 * proxy that buffers, a dead link) we degrade quietly to polling /api/live,
 * which returns the same small payload. Either way the payload carries a data
 * revision, so an unchanged week costs one tiny request and zero re-rendering.
 *
 * The tab is idle-aware: a hidden tab drops its connection, and reconnecting
 * sends the current revision, so the dashboard catches up on return without any
 * work when nothing actually changed.
 *
 * Exposes window.Live for app.js (and for the headless render check):
 *   Live.start({ onRefresh: fn })  - begin watching
 *   Live.state() / Live.mode() / Live.revision()  - introspect
 */
(function (global) {
  "use strict";

  var LIVE = "live", CONNECTING = "connecting", RETRYING = "retrying";
  var OFFLINE = "offline", PAUSED = "paused", STATIC = "static";
  var LABELS = {
    live: "Live", connecting: "Connecting\u2026", retrying: "Reconnecting\u2026",
    offline: "Offline", paused: "Paused", static: "Live off"
  };
  /* Static mode (?nolive=1): render the view without opening a stream. Used by
     shot.py for screenshots (a permanently-open SSE connection means a headless
     browser never reaches "network idle", so --screenshot hangs) and available
     to anyone embedding a still dashboard. */
  var NO_LIVE = /[?&]nolive=1(&|$)/.test(global.location.search);
  var MAX_BACKOFF = 30000;   /* cap (ms) on the reconnect backoff */
  var STALE_AFTER = 35000;   /* silence (ms) after which a stream is suspect */
  var STALE_LIMIT = 3;       /* consecutive stale checks before polling */
  var POLL_MS = 30000;       /* degraded-mode polling cadence */
  var TICK_MS = 1000;        /* freshness label refresh */

  var state = CONNECTING, mode = "sse";
  var source = null, retryTimer = null, pollTimer = null, tickTimer = null;
  var attempts = 0, staleStrikes = 0, lastFrameAt = 0, lastChangeAt = 0;
  var revision = null, onRefresh = null, started = false, paused = false;

  function el(id) { return document.getElementById(id); }

  function ago(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    if (s < 5) return "just now";
    if (s < 60) return s + "s ago";
    var m = Math.round(s / 60);
    if (m < 60) return m + "m ago";
    var h = Math.round(m / 60);
    return h < 24 ? h + "h ago" : Math.round(h / 24) + "d ago";
  }

  function paint() {
    var pill = el("livePill");
    if (pill) {
      if (pill.dataset.state !== state) pill.dataset.state = state;
      pill.title = "Transport: " + (mode === "sse" ? "live stream" : "polling") +
        (lastFrameAt ? " \u00b7 last signal " + ago(Date.now() - lastFrameAt) : "");
    }
    var text = el("liveText");
    if (text) text.textContent = LABELS[state] || state;
    var age = el("liveAge");
    if (age) {
      age.textContent = state === STATIC ? "live updates off"
        : paused ? "paused while hidden"
        : lastChangeAt ? "updated " + ago(Date.now() - lastChangeAt) : "syncing\u2026";
    }
  }

  function setState(next) { state = next; paint(); }

  function parse(raw) {
    try { return JSON.parse(raw); } catch (e) { return null; }
  }

  /* One place where every payload lands, whichever transport delivered it. */
  function apply(data, kind) {
    lastFrameAt = Date.now();
    attempts = 0;
    staleStrikes = 0;
    setState(LIVE);
    if (!data) return;
    var rev = data.revision || null;
    var first = revision === null;
    var changed = rev !== null && rev !== revision;
    if (changed) { revision = rev; lastChangeAt = Date.now(); }
    /* "hello" is the snapshot the page already rendered, so skip it. Any later
       frame that reveals a new revision - an explicit update, or a heartbeat or
       poll that caught a change we were not told about - reloads the view. */
    if (!first && changed && onRefresh) onRefresh(data, kind);
  }

  function closeStream() {
    if (source) {
      try { source.close(); } catch (e) { /* already closed */ }
      source = null;
    }
  }

  function scheduleRetry() {
    clearTimeout(retryTimer);
    attempts++;
    setState(attempts > 2 ? OFFLINE : RETRYING);
    var wait = Math.min(MAX_BACKOFF, 1000 * Math.pow(2, attempts - 1));
    retryTimer = setTimeout(function () {
      retryTimer = null;
      if (attempts > 2) startPolling();   /* stream looks unusable: poll instead */
      else connect();
    }, wait);
  }

  function connect() {
    clearTimeout(retryTimer);
    retryTimer = null;
    if (paused) return;
    if (typeof global.EventSource !== "function") { startPolling(); return; }
    closeStream();
    setState(CONNECTING);
    var es;
    try { es = new global.EventSource("/api/stream"); }
    catch (e) { scheduleRetry(); return; }
    source = es;
    es.addEventListener("open", function () {
      attempts = 0;
      lastFrameAt = Date.now();
      setState(LIVE);
    });
    es.addEventListener("hello", function (e) { apply(parse(e.data), "hello"); });
    es.addEventListener("heartbeat", function (e) { apply(parse(e.data), "heartbeat"); });
    es.addEventListener("update", function (e) { apply(parse(e.data), "update"); });
    es.addEventListener("error", function () {
      /* EventSource retries on its own while CONNECTING; once it has given up
         (CLOSED) we take over, so we can back off and fall back to polling. */
      if (es.readyState === 2) { closeStream(); scheduleRetry(); }
      else setState(RETRYING);
    });
  }

  function pollOnce() {
    fetch("/api/live", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) { apply(data, "poll"); })
      .catch(function () { setState(OFFLINE); });
  }

  function startPolling() {
    mode = "poll";
    closeStream();
    clearInterval(pollTimer);
    pollTimer = setInterval(function () { if (!paused) pollOnce(); }, POLL_MS);
    pollOnce();
  }

  /* If a stream stays silent well past its heartbeat it is not coming back on
     its own; degrade to polling rather than sit on a dead connection. */
  function watchdogTick() {
    if (paused || mode !== "sse") return;
    if (!lastFrameAt || Date.now() - lastFrameAt <= STALE_AFTER) {
      staleStrikes = 0;
      return;
    }
    staleStrikes++;
    if (staleStrikes >= STALE_LIMIT) { staleStrikes = 0; startPolling(); }
  }

  function pause() {
    paused = true;
    closeStream();
    clearInterval(pollTimer);
    pollTimer = null;
    clearTimeout(retryTimer);
    retryTimer = null;
    setState(PAUSED);
  }

  function resume() {
    paused = false;
    attempts = 0;
    staleStrikes = 0;
    if (mode === "poll") startPolling();
    else connect();
    /* No forced refresh here: reconnecting delivers the current revision, so
       the view only reloads if the data really moved while we were away. */
  }

  function start(opts) {
    opts = opts || {};
    onRefresh = opts.onRefresh || null;
    if (started) return;
    started = true;
    lastFrameAt = Date.now();
    lastChangeAt = Date.now();
    if (NO_LIVE) { mode = "off"; setState(STATIC); return; }  /* no timers, no stream */
    paint();
    tickTimer = setInterval(function () { paint(); watchdogTick(); }, TICK_MS);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) pause(); else resume();
    });
    if (document.hidden) pause(); else connect();
  }

  global.Live = {
    start: start,
    stop: function () {
      started = false;
      pause();
      clearInterval(tickTimer);
      tickTimer = null;
    },
    state: function () { return state; },
    mode: function () { return mode; },
    revision: function () { return revision; }
  };
})(window);