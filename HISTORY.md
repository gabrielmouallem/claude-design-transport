# History — how each rule was bought

Every rule in this repo was paid for by hitting a wall during one real migration, executed on 2026-09-15. This is the honest account, in order, including the parts where the plan was wrong. Project names, identifiers, hostnames and product specifics are stripped; the shapes are kept, because the shapes are the lessons.

## 1. The starting problem

A Claude Design project — a design system with a fully built prototype on top of it — lived in one account and needed to be in another. There is no transfer button. Personal and organisation accounts cannot be merged, even when they share an email address. The native path that does move projects between them closes the source account and cancels its subscription on the way (see `references/account-routing.md`). So the question was never "which button"; it was "which route loses the least".

## 2. The first wrong model

The obvious move: export the ZIP, upload it into a fresh Claude Design project, and prompt the model to reproduce it faithfully. Hours went into increasingly elaborate fidelity-enforcing prompts — tripwire lists of things that must not change, canary sections that would reveal drift, a divergence-report format the model had to fill in, a local diff harness to score the result. That machinery was well built. It was aimed at the wrong target: it treated a file-transfer problem as a generation problem and accepted a lossy channel as given. The machinery survives in `references/alternatives.md`, because it is still the right tool when the door really is locked.

## 3. The reframe that unlocked it

The uploads folder is not a permission wall to be bypassed. It is a weak ingestion channel: the model reads what you upload and re-emits an interpretation. Meanwhile the DesignSync tool exposes `write_files` to arbitrary project paths, behind `finalize_plan` as an explicit write boundary. Bytes in, bytes out, no interpretation. There was never a wall — there was a door nobody had tried.

## 4. Reconnaissance changed the problem

Structural reconnaissance — shell tools only, nothing large loaded into a model's context — showed the bundle was not one artifact. It was a design system (67 exported components, 397 tokens, 2 themes, 29 preview cards) plus a fully built prototype: 23 HTML pages (18-plus product screens) driving 25 screen modules through in-browser Babel, on top of a compiled bundle. The manifest indexed the component library but pointed at nothing under the screens directory and nothing under `assets/`: a manifest-only import would have carried the library's *identity* and none of the working app.

That killed two routes at once. Element capture or prompt reproduction would have been catastrophically wrong here, because capture preserves rendered pixels and destroys exactly the layer that matters: token indirection (`var(--token)` collapses to a resolved hex that no longer knows it is reserved for anything), prop contracts, keyboard behaviour, and every state not painted on screen at the moment of capture.

## 5. The file everyone would have deleted

A 12 MB "standalone" HTML export sat at the root. The audit correctly marked it regenerable noise *for the push* — nothing referenced it — and the plan was to leave it out. It turned out to be a client-side bundler loader: a `<script type="__bundler/manifest">` carrying 78 embedded chunks, and a template with the page's stylesheets inlined. The chunks contained React, ReactDOM, `@babel/standalone`, 29 font binaries (plus four legacy SVG icon fonts, carried as `image/svg+xml`) and, inlined in the template, the icon CSS — a strict superset of the vendoring fix that the whole CSP risk depended on.

The alternative source for those fonts was a sibling project reachable only through `get_file`, which returns binary as base64 *through the model's context* and requires the model to re-emit it to disk — the silent-corruption failure class, and hundreds of thousands of tokens for a few megabytes. Decoding locally from the export was zero reads and exact bytes, verifiable against the SRI `integrity` attributes the pages already carried and against canonical npm hashes. The file dismissed as noise resolved the most dangerous open risk. The rule that came out of it: drop derived output from the *push*, never from *disk*, until you know what it regenerates.

## 6. The duplication that wasn't

17 of the 23 HTML shells were byte-identical except for three lines. The obvious optimisation — collapse them to one template plus a route table and regenerate at the destination — was wrong twice over.

First, the first-line `<!-- @dsCard … -->` comment *is* the card-registration mechanism, and the destination indexes files, not routes: collapse them and you must re-expand to files with byte-exact first lines anyway.

Second, the "only three lines vary" premise was false. **Four of the seventeen shells set a third `localStorage` key** — two a staff role, two a fresh-account flag — on the same line as the two keys every shell set, so the line count matched and the summary looked right. A route table built on the common pattern would have dropped them silently; those pages would have rendered as the wrong role, or as a returning user instead of a new one, passed a smoke test, and been wrong in the product. A pairwise diff during the audit caught one of the four by hand; the tool in this repo now compares the *shape* of the varying lines and caught all four the first time it ran. Transport's job is landing bytes faithfully; refactor afterwards, in the repo, if you want to.

## 7. The landmine

The compiled bundle binds one global, `window.<Namespace>`, and the namespace is derived from the project itself. Every screen destructures it unguarded — `const { Shell, Header } = window.<Namespace>;`. Reading one remote manifest from a sibling project revealed the derivation rule: `<display name with non-alphanumerics removed>_<first six hex of the project id>`. Move the project — new name, new id — and the global the pages expect ceases to exist. TypeError, blank screen, clean console.

54 files were hard-bound in the runtime form; 57 carried the literal in some form (add the manifest, a readme line, and canvas-template attributes); 59 occurrences sat inside the bundle alone — its header, its IIFE, and every compiled per-file block. Neither the original transport recommendation nor its first revision had seen any of it. It was found by adversarial review: three independent reviewers were asked to break the plan, and all three converged on the same point.

## 8. The rejected fix

The first remedy proposed was a shim that located the namespace by shape-matching window globals — find the first object that has the shell and header components on it, and bind to that. It was rejected, correctly, by the human in the loop: if a recompile exposes a partial object or two candidates, it binds the wrong one silently, and the failure surfaces later as inexplicable behaviour with nothing in the console pointing at the cause. *A blank screen with a clean console is the worst possible failure mode.*

The replacement was deterministic rewriting — the literal replaced with the predicted value in every file, `sourceHashes` recomputed so the bundle stays hash-consistent — plus a guard that fails loud: it paints an overlay naming the expected global, whether it is absent or malformed, every namespace-shaped global actually present (so a value minted by the platform surfaces verbatim), and any vendor script that failed to load; then it throws. It never binds a candidate. It was negative-tested on throwaway commits before anything was pushed: a wrong expected value produced the overlay with the real value listed under "present"; a broken vendor path produced a 404 in the network panel and an overlay naming the missing global.

## 9. The inversion that made it safe

If you push a self-consistent bundle — namespace literal, header, `sourceHashes` and manifest all agreeing with the pushed sources — and the app leaves it alone, then *you* set the namespace, and the prediction was never load-bearing. The prediction matters only on the recompile path, and there the guard turns a wrong guess into a one-iteration fix with the right value printed on screen. That is what let the push proceed with one genuine uncertainty still open — whether the stem uses the project's name at compile time or at creation — because every branch ended in either a working page or a named error.

## 10. The outcome

209 files, 9,679,007 bytes, zero deletes. `finalize_plan` with exact paths and an explicitly empty delete list; four `write_files` calls, each file over 1 MB in its own call so a cap rejection would name the file instead of killing a batch; `list_files` set equality passing in both directions; no size cap hit at 3,137,752 bytes; the manifest read back with the intended namespace *before* any page was opened, since opening the pane is the likeliest trigger for a recompile. Locally, every verified page made zero external network requests: 162 requests, 162 × HTTP 200, one host.

## Two corrections the process made to itself

They are recorded because they demonstrate what gated tooling is for.

- **The rewrite tool refused to write.** A postcondition asserted that a compiled helper function appeared exactly once in the bundle after the edit. It appeared four times — it always had; the assertion was stated too strictly. Nothing was written. The assertion was changed to "count unchanged before and after", which is what the check had meant, and the run was repeated. A gate that blocks a bad rewrite has done its job; the fix is to loosen the assertion, never the gate.
- **The plan's file count was off by one.** The approved plan said 208 files; the set derived from git said 209. The plan's own layout table had summed three copied groups to 28 and listed the generated font stylesheet as a fourth row without adding it. The discrepancy was caught by set arithmetic *before* the plan was approved, when the reviewer asked for the full path list as text and for the count to be explained, rather than after a push. The error was in the prose, not the set.

## Smaller things the plan got wrong, for the record

- An earlier tally called the identical shells "16 of 23"; pairwise diff made it 17.
- The audit attributed a quoted sentence to the wrong document, and mis-stated which pages carried card markers; both were corrected by grep before they mattered.
- The first transport recommendation assumed the destination should be a freshly created project; the file diff of the existing candidates showed that a supposedly related project was in fact a divergent sibling with 268 files that existed nowhere else — which is how the "freeze it, touch nothing" rule and the sibling-manifest read that revealed the namespace rule both came about.

All small, all caught by checking the tree rather than trusting memory or prose. That is the point of the whole repo.
