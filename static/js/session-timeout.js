/* Idle session timeout.
   The server owns the deadline: SESSION_COOKIE_AGE (15 minutes) with
   SESSION_SAVE_EVERY_REQUEST rolls it forward on every request, and each page
   render carries the fresh deadline in <body data-session-deadline> (epoch
   seconds). This script mirrors that deadline in the browser so the user gets
   a countdown warning before it hits and is logged out automatically at it.
   Deferred; included only on authenticated pages; exits if the attribute is
   missing (e.g. a page that forgot it). */
(function () {
  var body = document.body;
  var deadlineAttr = body && body.getAttribute("data-session-deadline");
  if (!deadlineAttr) { return; }

  var IDLE_MS = 15 * 60 * 1000; // must match SESSION_COOKIE_AGE in settings.py
  var WARN_MS = 60 * 1000;      // warn this long before the deadline
  var DEBOUNCE_MS = 1000;       // don't reset the clock more than once a second

  var deadline = Number(deadlineAttr) * 1000; // epoch seconds -> ms
  var tickTimer = null;
  var warned = false;
  var banner = null;
  var countEl = null;
  var lastActivityAt = 0;

  function fmt(sec) {
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function hideWarning() {
    if (banner) { banner.hidden = true; }
    warned = false;
  }

  function showWarning(leftMs) {
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "session-timeout-banner";
      banner.setAttribute("role", "status");

      var text = document.createElement("span");
      text.textContent = "Your session expires in ";
      countEl = document.createElement("strong");
      text.appendChild(countEl);

      var stay = document.createElement("button");
      stay.type = "button";
      stay.className = "btn btn-sm btn-brand";
      stay.textContent = "Stay signed in";
      /* A real request: the server rolls the deadline, and the reloaded page
         carries the fresh one, so the banner clears. */
      stay.addEventListener("click", function () { window.location.reload(); });

      banner.append(text, stay);
      document.body.appendChild(banner);
    }
    banner.hidden = false;
    countEl.textContent = fmt(Math.ceil(leftMs / 1000));
    warned = true;
  }

  function logout() {
    if (tickTimer) { clearInterval(tickTimer); }
    var form = document.getElementById("logout-form");
    if (form) { form.submit(); return; }
    /* No form to submit (defensive): reload and the server bounces the
       expired session to the login page. */
    window.location.reload();
  }

  function tick() {
    var leftMs = deadline - Date.now();
    if (leftMs <= 0) { logout(); return; }
    if (leftMs <= WARN_MS) { showWarning(leftMs); }
  }

  /* User activity resets the countdown. The server mirrors the reset on the
     user's next request (SESSION_SAVE_EVERY_REQUEST); the rare click that
     makes no request is the only divergence, and the server's own deadline
     still wins on the next request either way. */
  function onActivity() {
    var nowMs = Date.now();
    if (nowMs - lastActivityAt < DEBOUNCE_MS) { return; }
    lastActivityAt = nowMs;
    deadline = nowMs + IDLE_MS;
    if (warned) { hideWarning(); }
  }

  ["click", "keydown", "touchstart"].forEach(function (type) {
    document.addEventListener(type, onActivity, { passive: true });
  });

  tick();
  tickTimer = setInterval(tick, 1000);
})();
