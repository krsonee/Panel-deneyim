(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var API = (script.getAttribute("data-api") || "").replace(/\/$/, "");
  if (!API) {
    try { API = new URL(script.src).origin; } catch (e) { return; }
  }

  var VISITOR_KEY = "affiliate_visitor_id";
  var domain = (window.location.hostname || "").toLowerCase().replace(/^www\./, "");
  if (domain === "127.0.0.1") domain = "localhost";
  var params = new URLSearchParams(window.location.search);
  var refCode = params.get("ref") || "";

  var visitorId = localStorage.getItem(VISITOR_KEY);
  if (!visitorId) {
    visitorId = "v_" + Date.now() + "_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem(VISITOR_KEY, visitorId);
  }

  var tracked = false;
  var seconds = 0;
  var games = [];
  var tickTimer = null;
  var heartbeatTimer = null;

  function post(path, body) {
    return fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive: true
    }).then(function (r) { return r.json(); }).catch(function () { return null; });
  }

  function init() {
    if (!domain) return;

    post("/api/track/init", {
      session_id: visitorId,
      domain: domain,
      ref_code: refCode
    }).then(function (res) {
      if (!res || !res.tracked) return;
      tracked = true;
      visitorId = res.session_id || visitorId;
      localStorage.setItem(VISITOR_KEY, visitorId);
      seconds = res.total_seconds || 0;
      games = res.games || [];
      startTimers();
    });
  }

  function sendHeartbeat() {
    if (!tracked) return;
    post("/api/track/heartbeat", {
      session_id: visitorId,
      domain: domain,
      ref_code: refCode,
      total_seconds: seconds,
      games: games
    });
  }

  function startTimers() {
    if (tickTimer) return;

    tickTimer = setInterval(function () {
      seconds += 1;
    }, 1000);

    heartbeatTimer = setInterval(sendHeartbeat, 10000);
    sendHeartbeat();
  }

  function trackGame(gameName) {
    if (!tracked || !gameName) return;

    if (games.indexOf(gameName) === -1) {
      games.push(gameName);
    }

    post("/api/track/event", {
      session_id: visitorId,
      domain: domain,
      ref_code: refCode,
      game: gameName,
      elapsed: seconds
    });
  }

  window.AffiliateTracker = {
    trackGame: trackGame,
    isTracked: function () { return tracked; },
    getSessionId: function () { return visitorId; },
    getSeconds: function () { return seconds; }
  };

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-track-game]");
    if (btn) {
      trackGame(btn.getAttribute("data-track-game"));
    }
  });

  window.addEventListener("pagehide", function () {
    sendHeartbeat();
  });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      sendHeartbeat();
    }
  });

  init();
})();
