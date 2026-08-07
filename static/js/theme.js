/* Colour theme. Loaded synchronously in <head> so the stored choice is applied
   before first paint — deferring this gives a white flash on every page load
   for dark-theme users. */
(function () {
  var KEY = "cbods-theme";
  var root = document.documentElement;

  function stored() {
    try {
      var saved = localStorage.getItem(KEY);
      return saved === "light" || saved === "dark" ? saved : null;
    } catch (e) {
      return null; // private browsing, or storage disabled
    }
  }

  function apply(theme) {
    root.setAttribute("data-bs-theme", theme);
    // Anything that samples theme colours in JS rather than CSS — the dashboard
    // charts draw to a canvas, so they cannot inherit — has to be told. Without
    // this their labels keep the colour of whichever theme was active at load
    // and vanish against the other one.
    window.dispatchEvent(new CustomEvent("cbods:theme", { detail: { theme: theme } }));
  }

  function systemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  apply(stored() || systemTheme());

  // Follow the OS until the user states a preference of their own.
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
    if (!stored()) { apply(e.matches ? "dark" : "light"); }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.querySelector(".theme-toggle");
    if (!btn) { return; }

    function label() {
      var next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
      btn.setAttribute("aria-label", "Switch to " + next + " theme");
    }

    btn.addEventListener("click", function () {
      var next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
      apply(next);
      try { localStorage.setItem(KEY, next); } catch (e) { /* nothing to do */ }
      label();
    });

    label();
  });
})();
