/* namespace_guard.js — reference fail-loud guard for pages built on a Claude Design bundle.
 *
 * WHAT IT ASSUMES
 *   - _ds_bundle.js has already executed (this script runs after it and before any screen script).
 *   - The page loads React, ReactDOM and (if screens are text/babel) @babel/standalone before the bundle.
 *   - The bundle exposes ONE global, window.<EXPECTED>, carrying the component library, and ANCHOR is a
 *     component that must exist on it as a function (pick the root layout / shell component).
 *
 * WHAT IT REFUSES TO DO
 *   - It never binds a lookalike. If the expected global is missing, it lists every namespace-shaped
 *     global that IS present so a platform-minted value surfaces verbatim — and then it throws.
 *   - It never fails quietly. Overlay first, then throw, so neither "blank screen" nor "clean console" occurs.
 *
 * WHERE IT GOES
 *   1. Top of the shared helper script every bundle-loading page loads (covers them all).
 *   2. Inline <script> right after the bundle tag in each *.card.html (cards do not load the helper).
 *   3. The canvas template's base loader: use TEMPLATE VARIANT below in the dynamic script's onload.
 *
 * Verified as of 2026-09-15 by two negative tests on throwaway commits (wrong EXPECTED; broken vendor path).
 */
(function () {
  var EXPECTED = "<Namespace>_<id6>";      // e.g. "DesignSystem_9f8e7d" — the value the pages were rewritten to
  var ANCHOR = "<ShellComponent>";          // a component the bundle must expose, e.g. the root layout
  var VENDOR = ["React", "ReactDOM", "Babel"]; // drop "Babel" if your screens are precompiled

  var missing = VENDOR.filter(function (g) { return !window[g]; });
  var ns = window[EXPECTED];
  var ok = !missing.length && ns && typeof ns === "object" && typeof ns[ANCHOR] === "function";
  if (ok) return;

  var shaped = Object.keys(window).filter(function (k) {
    return /^[A-Z][A-Za-z0-9]*_[0-9a-f]{6}$/.test(k) && window[k] && typeof window[k] === "object";
  });
  var msg = "Design-system bootstrap error\n"
    + (missing.length ? "vendor globals missing: " + missing.join(", ") + " (script path or SRI failure; check the network panel)\n" : "")
    + "expected design-system global: window." + EXPECTED
    + (ns ? " - defined, but " + ANCHOR + " is " + typeof ns[ANCHOR] + " (keys: " + Object.keys(ns).slice(0, 10).join(", ")
            + (ns.__errors ? "; " + ns.__errors.length + " bundle block errors" : "") + ")"
          : " - not defined after _ds_bundle.js")
    + "\nnamespace-shaped globals present: " + (shaped.length ? shaped.join(", ") : "none")
    + "\nlikely cause: the bundle was (re)compiled under a different project name or id."
    + "\nfix: re-run the namespace rewrite with the value listed above. This guard does not bind to it.";

  var pre = document.createElement("pre");
  pre.setAttribute("role", "alert");
  pre.style.cssText = "position:fixed;inset:12px;z-index:2147483647;margin:0;padding:16px;overflow:auto;"
    + "background:#2a1215;color:#ff8a80;border:1px solid #5c2b2e;border-radius:8px;"
    + "font:13px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap";
  pre.textContent = msg;
  (document.body || document.documentElement).appendChild(pre);
  throw new Error(msg.replace(/\n/g, " | "));
})();

/* TEMPLATE VARIANT — for the canvas template's base loader (the script that appends _ds_bundle.js dynamically).
 * The canvas loads React/Babel asynchronously through its own support script, so a vendor check here would
 * false-positive; only the namespace is checked. Attach as `s.onload` before `document.head.appendChild(s)`.
 *
 *   s.onload = () => {
 *     const EXPECTED = "<Namespace>_<id6>", ANCHOR = "<ShellComponent>";
 *     const ns = window[EXPECTED];
 *     if (ns && typeof ns === "object" && typeof ns[ANCHOR] === "function") return;
 *     const shaped = Object.keys(window).filter((k) => /^[A-Z][A-Za-z0-9]*_[0-9a-f]{6}$/.test(k) && window[k] && typeof window[k] === "object");
 *     const msg = "Design-system bootstrap error | expected design-system global: window." + EXPECTED
 *       + (ns ? " - defined, but " + ANCHOR + " is " + typeof ns[ANCHOR] : " - not defined after _ds_bundle.js")
 *       + " | namespace-shaped globals present: " + (shaped.length ? shaped.join(", ") : "none")
 *       + " | likely cause: the bundle was (re)compiled under a different project name or id.";
 *     const pre = document.createElement("pre"); pre.setAttribute("role", "alert");
 *     pre.style.cssText = "position:fixed;inset:12px;z-index:2147483647;margin:0;padding:16px;overflow:auto;background:#2a1215;color:#ff8a80;border:1px solid #5c2b2e;border-radius:8px;font:13px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap";
 *     pre.textContent = msg; (document.body || document.documentElement).appendChild(pre);
 *     throw new Error(msg);
 *   };
 */
