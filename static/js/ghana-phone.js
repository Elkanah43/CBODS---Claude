/* Ghanaian mobile phone field: fixed +233 prefix, exactly 9 digits, live
 * network detection, and submit blocking. Shared by every form that collects
 * a phone number (individual signup, hospital signup, donor/hospital profile
 * edits, staff provisioning).
 *
 * Frontend validation is a USER-EXPERIENCE layer only. The Django backend is
 * the final authority — it re-validates and normalises every value server-side
 * (cbods.validators.validate_ghana_phone_number), so a hand-crafted request is
 * rejected even with JavaScript disabled. The two layers are kept in step by
 * the backend prefix table rendered into #ghana-network-prefixes; the copy in
 * FALLBACK_PREFIXES only exists for pages that do not render that element.
 */
(function () {
  "use strict";

  var FALLBACK_PREFIXES = {
    "MTN Ghana": ["24", "25", "53", "54", "55", "59"],
    "Telecel Ghana": ["20", "50"],
    "AirtelTigo Ghana": ["26", "27", "56", "57"]
  };

  function loadPrefixes() {
    var el = document.getElementById("ghana-network-prefixes");
    if (!el) { return FALLBACK_PREFIXES; }
    try {
      return JSON.parse(el.textContent) || FALLBACK_PREFIXES;
    } catch (err) {
      return FALLBACK_PREFIXES;
    }
  }

  var NETWORK_PREFIXES = loadPrefixes();

  function detectGhanaNetwork(digits) {
    if (!digits || digits.length < 2) { return null; }
    var prefix = digits.slice(0, 2);
    for (var network in NETWORK_PREFIXES) {
      if (Object.prototype.hasOwnProperty.call(NETWORK_PREFIXES, network) &&
          NETWORK_PREFIXES[network].indexOf(prefix) !== -1) {
        return network;
      }
    }
    return null;
  }

  /* The one reusable validation entry point.
   * Returns { valid: true, network, formatted: "+233XXXXXXXXX" } or
   *         { valid: false, error: "user-friendly message" }.
   */
  function validateGhanaPhoneNumber(phone) {
    // 1. Remove unnecessary spaces (and other grouping characters).
    var cleaned = String(phone == null ? "" : phone).replace(/[\s()\-.]/g, "");
    if (cleaned === "") {
      return { valid: false, error: "Phone number is required." };
    }
    // 2. Digits only.
    if (!/^\d+$/.test(cleaned)) {
      return { valid: false, error: "Please enter numbers only." };
    }
    // 3. Exactly 9 digits.
    if (cleaned.length !== 9) {
      return { valid: false, error: "Phone number must contain exactly 9 digits." };
    }
    // 4. The first two digits must be a valid Ghanaian mobile prefix.
    var network = detectGhanaNetwork(cleaned);
    if (!network) {
      return { valid: false, error: "Invalid Ghana mobile network prefix." };
    }
    return { valid: true, network: network, formatted: "+233" + cleaned };
  }

  // Exposed so other scripts and browser consoles can reuse the exact logic.
  window.validateGhanaPhoneNumber = validateGhanaPhoneNumber;
  window.detectGhanaNetwork = detectGhanaNetwork;

  function nationalDigits(value) {
    /* Turn whatever is in the box into the 9 national digits: tolerate a
     * pasted "+233241234567" and legacy "0241234567", then cap at 9. */
    var d = String(value == null ? "" : value).replace(/\D/g, "");
    if (d.length === 12 && d.indexOf("233") === 0) { d = d.slice(3); }
    else if (d.length === 10 && d.indexOf("0") === 0) { d = d.slice(1); }
    return d.slice(0, 9);
  }

  function initGhanaPhoneField(input) {
    if (input.dataset.ghanaPhoneReady) { return; }
    input.dataset.ghanaPhoneReady = "1";

    var container = input.parentNode;
    var group = document.createElement("div");
    group.className = "input-group";
    var prefix = document.createElement("span");
    prefix.className = "input-group-text ghana-phone-prefix";
    prefix.textContent = "+233";
    prefix.setAttribute("aria-hidden", "true");

    container.insertBefore(group, input);
    group.appendChild(prefix);
    group.appendChild(input);

    var hint = document.createElement("div");
    hint.className = "ghana-phone-hint form-text small mt-1";
    hint.hidden = true;
    container.insertBefore(hint, group.nextSibling);

    var error = document.createElement("div");
    error.className = "ghana-phone-error text-danger small mt-1";
    error.hidden = true;
    container.insertBefore(error, hint.nextSibling);

    // The HTML contract: numeric, exactly 9 characters, digits only.
    input.classList.add("form-control");
    input.setAttribute("inputmode", "numeric");
    input.setAttribute("maxlength", "9");
    input.setAttribute("pattern", "[0-9]{9}");
    if (!input.getAttribute("autocomplete")) { input.setAttribute("autocomplete", "tel"); }

    // Edit forms arrive with the stored +233XXXXXXXXX form; show only the 9
    // national digits, since the prefix already sits beside the box.
    input.value = nationalDigits(input.value);

    function paint() {
      var d = input.value;
      var network = detectGhanaNetwork(d);
      if (d.length < 2) {
        hint.hidden = true;
        hint.textContent = "";
        return;
      }
      hint.hidden = false;
      if (network) {
        hint.classList.remove("text-danger");
        hint.classList.add("text-success");
        hint.textContent = network;
      } else {
        hint.classList.remove("text-success");
        hint.classList.add("text-danger");
        hint.textContent = "Invalid Ghana mobile network prefix.";
      }
    }

    function showError(message) {
      error.textContent = message;
      error.hidden = false;
      input.classList.add("is-invalid");
    }

    function clearError() {
      error.hidden = true;
      error.textContent = "";
      input.classList.remove("is-invalid");
    }

    input.addEventListener("input", function () {
      var next = nationalDigits(input.value);
      if (next !== input.value) { input.value = next; }
      clearError();
      paint();
    });

    var form = input.closest("form");
    if (form) {
      form.addEventListener("submit", function (ev) {
        var result = validateGhanaPhoneNumber(input.value);
        if (!result.valid) {
          ev.preventDefault();
          showError(result.error);
          input.focus();
        }
      });
    }

    paint();
  }

  function boot() {
    var inputs = document.querySelectorAll("input[data-ghana-phone]");
    Array.prototype.forEach.call(inputs, initGhanaPhoneField);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();