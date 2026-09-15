---
name: claude-design-transport
description: "Move a Claude Design project or design system between accounts or projects with fidelity, using the DesignSync write API (finalize_plan + write_files) instead of ZIP upload and prompt reproduction or element capture. Also use for: backing up or version-controlling a Claude Design export; pushing a local component library into a fresh design-system project; diagnosing screens that went blank with a clean console after a project rename, duplicate or move (the compiled bundle's namespace global is undefined); removing CDN dependencies (unpkg, Google Fonts) so a design system renders offline or under a strict CSP; auditing an unfamiliar design bundle before touching it (what is source, what is generated, what is dead, what does it depend on); and the gated safe-mutation pattern itself — precondition-gated rewrites, negative-tested fail-loud guards, set-equality after bulk writes. Triggers: move my design system to another account, transfer a Claude Design project, migrate the design system, back up my design system, version control for Claude Design, push my component library into Claude Design, screens went blank after I renamed the project, namespace is undefined, TypeError destructuring window global, remove the CDN dependencies, make this work offline, vendor the fonts, what is in this design export, audit this bundle before I touch it, DesignSync push, finalize_plan, write_files."
---

# Claude Design transport

Move a Claude Design design-system project between accounts or projects as a **file transfer** — bytes written through the DesignSync API — rather than as a generation task. The same procedure backs up a project, bootstraps a design-system project from a repo, de-CDNs a prototype, and diagnoses the blank-screen failure that follows any rename, duplicate or move.

Extracted from one completed execution on 2026-09-15 (209 files, zero deletes, set equality both ways). Every observed behaviour below is dated in `references/`; re-verify before relying on a number.

## Non-negotiables

1. **Never load a multi-megabyte export or bundle into the model's context.** Characterise with shell tools and small parsers (`scripts/recon.py`). Read headers, first lines, counts.
2. **Every mutation is gated.** Compute the new state in memory, check pre- and post-conditions, write nothing unless all pass, re-verify from disk after writing. When a gate blocks, loosen the *assertion* if it was wrong — never the gate.
3. **Irreversible steps last, and each in its own call.** Local edits, then commits, then verification, then remote writes. No deletes on the remote unless explicitly asked; exact paths, never convenient globs.
4. **Fail loud, never guess.** No heuristic fallbacks that bind "whatever looks right". A blank screen with a clean console is the worst outcome; design so it cannot occur.
5. **The source project is frozen.** Read from it if you must; never write to or delete from it. It is the rollback.
6. **Commit before you touch anything, and commit per step.** The tree as downloaded is `main`; work on a branch; a hard reset must have a named target.
7. **Records over recollection.** Ground every claim in files on disk. Date observed behaviour. Flag any number that disagrees with the record instead of picking one.

## Prerequisites

- The source project exported as a ZIP and unpacked into a directory you control; ideally the dated snapshot ZIPs too (they are your only history — see `references/reconnaissance.md`).
- Claude Code with the `DesignSync` tool available and **`/design-login`** completed (a separate authorization from the session login; the tool tells you when it is missing).
- A destination project of type `PROJECT_TYPE_DESIGN_SYSTEM`. The type is immutable at creation: pushing to a regular project never makes it one. Verify with `get_project`.
- Python 3.9+, Node ≥ 22, git, and a browser you can drive headless for verification.

## The route

### Phase 0 — Safety net (gates everything)

- `git init` and commit the tree **exactly as downloaded**, before any modification. That commit is the rollback point.
- Copy every dated snapshot ZIP and any standalone export you have to a durable folder outside `~/Downloads`, with SHA-256 sums.
- Do **not** delete anything from disk. Derived output can be excluded from the push and still be needed (Phase 3).

### Phase 1 — Reconnaissance (`scripts/recon.py`)

Answer, from structure alone:

- Is this a design system, a prototype, or both? Read `_ds_manifest.json` (components, cards, tokens, themes, templates, `globalCssPaths`). Note what the manifest does **not** enumerate — screens, assets, demo data — because a manifest-only import carries the library's identity and not a working app.
- What is source, what is generated, what is design-time input? Pasted reference images in `uploads/` are input and need not travel. `_ds_bundle.js` and `_ds_manifest.json` are compiled output (regenerable, but every page loads the bundle directly). A huge HTML with `<script type="__bundler/manifest">` is a standalone export: derived output — **and the vendor-file source for Phase 3**.
- Which pages carry a first-line `<!-- @dsCard … -->`? Their presence means the tree was authored for design-sync and the push route is correct. Their count should equal the manifest's cards.
- Diff seemingly identical shells **pairwise**. Do not trust "only N lines vary" — shells setting an extra `localStorage` key on a shared line are exactly what a template-plus-route-table would silently drop (four of seventeen did, in two different ways).
- Assets: referenced vs orphaned vs referenced-but-missing, accounting for `../` depth prefixes, and grep for dynamically built paths a literal grep would miss.
- Every external host literal, per file: CDNs for React/Babel/icons, font imports in the token CSS, loaders compiled into the bundle.
- The bundle header: `format`, `namespace`, `sourceHashes` (verify the hash scheme on several files, not one), and which paths it names — dead code named there may still need to ship (`references/reconnaissance.md`).

Write the audit down (`transfer.md` shape: payload, screen inventory, noise, assets, tooling, size). Then decide the route with `references/alternatives.md` open: capture is right only when redesigning; prompt reproduction only when no write API exists.

### Phase 2 — Decide destination and freeze the source

- `list_projects` / `get_project`: confirm the target's type and `canEdit`. Note the owner as the tool reports it; there is no whoami.
- If a candidate destination already has content, `list_files` it and diff against your tree before deciding anything. A project that *looks* related may be a divergent sibling holding files that exist nowhere else. Freeze anything you will not overwrite deliberately.
- Read one manifest from any design-system project you can see and check its `.namespace` against its name and id. This is how the derivation rule was found, and how you re-verify it (`references/namespace.md`).

### Phase 3 — Vendor the CDN dependencies (`scripts/vendor_from_export.py`)

If the pages load React, Babel, icon fonts or typefaces from CDNs, assume the destination sandbox may block them silently (`references/vendoring.md`). Do not repoint to a different CDN; vendor locally so the question stops applying.

- Decode the vendor files from the standalone export's embedded chunks — zero remote reads, exact bytes. Never pull binaries through `get_file` (base64 through the model's context, re-emitted by the model: the silent-corruption class).
- Verify without per-chunk hashes: sha384 against the `integrity` attributes the pages already carry; sha256 against canonical npm files if network is available; structural checks on fonts.
- Route icon CSS through the stylesheet chain, not per-page pre-links; rewrite its `url()`s to the local woff2. Generate one `@font-face` stylesheet that reproduces the CDN's rules exactly. Keep the `integrity` attributes when repointing script tags — SRI then guards the local copies.

### Phase 4 — Retarget the namespace (`scripts/retarget_namespace.py`)

- Predict the destination's namespace: `<display name with non-alphanumerics removed>_<first 6 hex of project id>`. Confirmed for Title Case names only; see the caveats.
- Enumerate every occurrence of the current literal — screen sources, helper files, card pages, canvas template attributes, the manifest, the bundle header, the bundle IIFE, and every compiled block in the bundle body. Never hardcode counts; the tool prints them.
- Dry-run: the tool computes everything in memory and prints file/occurrence counts, removed CDN loaders, hash changes, `node --check`. Apply only by restating the dry-run's numbers as expectations. It refuses to write on any mismatch.
- **Recompute `sourceHashes`** (`sha256(file)[:12]`) for every source you changed and re-verify all entries. Skipping this manufactures the staleness signal that triggers the recompile you are trying to avoid.

### Phase 5 — Guard, then negative-test it (`scripts/namespace_guard.js`)

- Install the guard after the bundle and before any screen: in the shared helper script (covers bundle-loading pages), inline in card pages (they do not load the helper), and in the canvas template's dynamic-script `onload` (namespace-only there; React arrives asynchronously in the canvas).
- Negative-test on **throwaway commits**, then `git reset --hard <named commit>`, then prove the revert by grep — not by assertion. Test A: wrong expected value → overlay names it and lists the real global under "present". Test B: broken vendor path → network panel shows the 404, overlay names the missing global.

### Phase 6 — Repoint and verify locally

- Repoint script tags to `vendor/`, the token CSS to the local `@font-face` sheet, the stylesheet chain to the icon CSS. Remove the CDN loaders from sources **and** from their compiled copies in the bundle.
- Serve the tree (`python3 -m http.server`) and drive a headless browser over the DevTools protocol: for each page, every request host, status, load failures, exceptions, console, whether the guard overlay exists, fonts loaded, glyphs rendered. Screenshots. The pass condition is zero external hosts, zero non-2xx, zero exceptions, guard silent.
- Run `scripts/verify_tree.py`. Commit the record with its evidence.

### Phase 7 — Push, in this order (`references/designsync-api.md`)

1. **Print the exact plan as text first** — every write path, the delete list (empty, stated explicitly), the target id, the local directory — and reconcile the count against the plan before asking for approval. The permission dialog is where the operator approves; the conversation is where they review.
2. `finalize_plan` — exact paths, `deletes: []` (the tool requires the field even when empty), `localDir` = the tree.
3. `write_files` #1 — everything under 1 MB, by `localPath`.
4. One `write_files` call **per file over 1 MB**, largest last, so a cap rejection names the file instead of killing a batch. If one is rejected: stop and report; do not improvise a workaround silently.
5. `list_files` — set equality against the local push set, **both directions**, with directory entries filtered out.
6. `get_file _ds_manifest.json` — read `.namespace` **before opening any page**; opening the pane may be what triggers a recompile. Byte-compare it to what you pushed: identical means the platform has not touched it yet, which confirms the artifact and *does not* test the derivation rule (the tautology trap).

### Phase 8 — After the first open

Re-read the manifest. Unchanged → the rule held or no recompile ran. Changed to the predicted value → the rule is confirmed. Changed to anything else → the guard is already naming it on every page; re-run Phase 4 with the real value, re-push only the changed paths. **Do not rename the destination project** until you know which of these happened — renaming is exactly the action that can mint a new stem.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/recon.py` | Structural characterisation of an export tree; never reads large files whole |
| `scripts/retarget_namespace.py` | Gated namespace rewrite + CDN-loader removal + `sourceHashes` recompute; `guard` subcommand installs the guard |
| `scripts/verify_tree.py` | Assertion battery: old literal 0, new literal count, syntax, hashes, external hosts, vendor sums |
| `scripts/vendor_from_export.py` | Decode React/Babel/fonts/icon CSS from a standalone export; verify against SRI and canonical hashes; generate the font stylesheet |
| `scripts/namespace_guard.js` | The reference fail-loud guard (page variant and canvas-template variant) |

## References

| File | Read it when |
|---|---|
| `references/namespace.md` | Anything is blank after a move/rename; before rewriting; to understand `sourceHashes` and the recompile branches |
| `references/vendoring.md` | Pages load anything from a CDN; the destination may be network-restricted |
| `references/designsync-api.md` | Before the first DesignSync call; for the push order and its reasons |
| `references/reconnaissance.md` | Before touching any tree you did not author |
| `references/account-routing.md` | Two accounts are involved; deciding which account does what; the native migration path |
| `references/alternatives.md` | Deciding whether this route is even the right one |

`HISTORY.md` tells how each of these rules was bought. Read it once; it is the fastest way to calibrate what is expensive.
