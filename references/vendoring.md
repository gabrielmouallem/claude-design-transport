# Vendoring: taking React, Babel, icon fonts and typefaces off the CDN

> **Verified as of 2026-09-15.** The CDN risk itself is an *inference* from the Content-Security-Policy that Claude Artifacts enforce (scripts only from a short allowlist; `unpkg` blocked, silently) — it was never confirmed for the Design System pane. Vendoring makes the question irrelevant rather than answering it. Re-verify: open one pushed page with the network panel open; any blocked or external request shows there. The export chunk format (`{mime, compressed, data}`, no per-chunk hash) and the vendor-file set were observed on one export; re-verify by running `scripts/vendor_from_export.py --list` on yours.

## The risk

A prototype built the Claude Design way loads, on every page:

- React and ReactDOM from `unpkg.com` (development builds, in the observed case);
- `@babel/standalone` from `unpkg.com`, because screens ship as `<script type="text/babel">` and compile in the browser;
- an icon font's CSS (four weights) from `unpkg.com`, injected at runtime by code **compiled into the bundle**;
- typefaces via `@import url("https://fonts.googleapis.com/…")` inside the token CSS.

If the destination sandbox enforces an Artifacts-like CSP, every one of those is blocked **silently** — no error, no fallback. Losing Babel and React means every `text/babel` page renders nothing at all. Losing the typefaces is milder but bites where it is most visible: no tabular numerals, so every money column misaligns.

## Do not move the dependency — remove it

Repointing `unpkg` → `cdnjs` (or any other allowlisted host) moves the risk to a different allowlist and a different outage. Vendor the files into the project so the pages load nothing external. The push carries them like any other file; in the recorded case 28 files, 5.75 MB, of which one (`babel.min.js`, 3.14 MB) became the write-cap probe.

## Source the files from the standalone export, not from `get_file`

Two sources exist for the same bytes:

- **A sibling project reachable only through `get_file`.** It returns binary as base64 *through the model's context*, capped at 256 KiB per file, and the model must re-emit it to disk. Megabytes of base64 transcribed by a language model is the silent-corruption failure class, and hundreds of thousands of tokens.
- **The standalone HTML export** (`<script type="__bundler/manifest">`) that the audit had marked as regenerable noise. Its chunks contained React, ReactDOM, `@babel/standalone`, 29 font binaries (plus four legacy SVG icon fonts as `image/svg+xml`) and — inlined in the `__bundler/template` — the icon CSS. Decoding locally is zero remote reads and exact bytes.

Chunk shape observed: `{ "mime": "...", "compressed": true|false, "data": "<base64>" }` keyed by uuid; compressed chunks are zlib/gzip. The template is a JSON string of the page HTML with `@font-face` rules whose `src: url("<uuid>")` point at chunk keys. `scripts/vendor_from_export.py` does the whole extraction.

## Verifying without per-chunk hashes

The export's manifest carries **no hash per chunk**. Use the hashes that already exist nearby:

- **SRI.** The pages' `<script src="https://unpkg.com/…" integrity="sha384-…">` attributes are hashes of the exact canonical files. Compute sha384 of each extracted JS file and compare. Three of three matched in the recorded case.
- **Canonical npm files.** If the machine has network, fetch the exact versioned URLs and compare sha256. Three of three matched.
- **Icon CSS.** Byte-identical to the published package after normalising `url()` references (the export rewrote `./Icons.woff2` → blob uuids).
- **Fonts.** Structural: `wOF2`/`wOFF` magic and header length field, TTF table directory bounds, SVG `<font>` markup. If any copy exists elsewhere, byte-compare one.

Keep the `integrity` attributes when you repoint `src` to `vendor/…` — SRI applies to same-origin scripts too, so it now guards the local copies against a wrong or corrupted file, and the guard names the missing global when SRI blocks one.

## Layout that worked

```
vendor/react.development.js
vendor/react-dom.development.js
vendor/babel.min.js
assets/fonts/*.woff2               (only woff2; drop woff/ttf/svg fallbacks — 14.5 MB of legacy formats for nothing)
assets/icons/<weight>.css          (url() rewritten to ../fonts/<file>.woff2, fallback formats removed)
tokens/fonts.css                   (generated: one @font-face per (weight × subset), unicode-range, font-display, src → ../assets/fonts/)
styles.css                         (@import tokens/fonts.css first, the token sheets, then the icon sheets last)
```

Pages at depth two use `../../vendor/…`; card pages at depth one use `../vendor/…`. Derive the prefix from each page's existing bundle path rather than assuming.

## Icon CSS: stylesheet chain, not pre-links

The bundle's compiled loader injects `<link>` tags for the icon CSS only if no element with the expected id exists. Two ways to make it local:

- **Pre-link per page** with the bundle's own ids so the loader no-ops. Works, but every page must remember to do it, and the CDN literals stay in the bundle as never-executed fallbacks.
- **Route the icon CSS through the stylesheet chain** (`styles.css` imports it) and **remove** the runtime loaders from the sources *and* from their compiled copies in the bundle. Recommended: CSS `@import`/`url()` resolve relative to the importing sheet, so it works at every page depth and in consuming projects; and a page that forgets the stylesheet loses icons **visibly**, instead of having a silently blocked request.

## Font stylesheet: reproduce the CDN's rules exactly

Google-served CSS declares one `@font-face` per (weight × unicode-range subset), all pointing at the same variable-font file for a given subset. Reproduce that exactly (66 rules in the recorded case) rather than collapsing to weight ranges — zero behavioural change, and the browser fetches only the subsets it uses.

## The platform recognises vendored fonts

After the first open of the destination's pane, the regenerated manifest listed every local `@font-face` rule under `fonts` (70 entries in the recorded case, each with `cssPath` and the `files` under `assets/fonts/`) and resolved the brand typefaces through the generated stylesheet in `brandFonts`; the icon weights appeared with `status: "unreferenced"`, which is correct — they are used by CSS class, not by token. Vendoring is therefore platform-legible, not a hack the app tolerates. (Observed 2026-09-15.)

## Known residuals

- **Canvas template loaders** (`templates/…/support.js`) may want *production* builds of React/ReactDOM with their own SRI constants, which a development-build export does not contain. They also have a `window.__resources` substitution hook. Decide after observing the pane; a one-time canonical fetch verified against those SRI constants is the clean fix.
- **Development builds** are large (React DOM dev ≈ 1.08 MB) and log to the console. Swapping to production requires updating every page's `integrity` attribute.
- **The largest vendored file becomes the write-cap probe.** Push it alone, last. If it is rejected, the clean fallback is to precompile the `text/babel` screens locally and ship plain JS — which also removes the in-browser compile step.
- An icon weight loaded on every page but used nowhere is a design decision, not a transport one. Note it; do not drop it as part of transport.
