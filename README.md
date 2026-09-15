# claude-design-transport

**Move a Claude Design project or design system from one account or project to another, with fidelity, by using the DesignSync write API instead of file uploads.**

That is the primary purpose, and it is a narrow, infrequent job. The pieces it is built from are not. Read the next section before deciding this is a one-off you can skip.

## Why install it even if you never migrate

Each of these stands on its own:

1. **Backup and version control.** Claude Design has no version history and no restore. Exporting on a cadence, committing to git, and knowing which files in the bundle are *source* and which are *derived output* is a discipline the reconnaissance and inventory phases give you for free. Anyone with a design system worth keeping needs this whether or not they ever move it.
2. **Bootstrapping a design-system project from an existing repo.** The push route also runs in the direction nobody calls migration: local component library → fresh design-system project. Same tooling, same gating, same verification. This is the common case for a team adopting Claude Design with a codebase that predates it.
3. **Diagnosing blank screens after any move, rename or duplicate.** A compiled Claude Design bundle binds one global named from the project's own name and id, and pages destructure it unguarded. Rename the project, duplicate it, or move it, and the global ceases to exist — TypeError, blank screen, clean console. The derivation rule and the fail-loud guard in `references/namespace.md` fix this regardless of how the project got moved.
4. **De-CDN'ing a design system.** Vendoring React, Babel, icon fonts and typefaces out of a project so it renders in restricted or offline environments — air-gapped review, CSP-constrained sandboxes, or simply not wanting prototypes to break when a CDN has a bad day. Independent of transport entirely.
5. **Auditing an unfamiliar design bundle.** The reconnaissance phase answers "what is actually in here, what is source, what is generated, what is dead, what does it depend on" for any Claude Design export — when inheriting a project, when deciding whether a bundle is worth keeping, or before any operation on a tree you did not author.
6. **A safe-mutation pattern worth stealing outright.** Precondition-gated rewrite tooling that refuses to write on mismatch, negative-tested guards, evidence-backed verification, irreversible steps last, set-equality checks after any bulk write. None of it is specific to Claude Design. It is the most portable thing in this repo.

## Is this for you?

| Situation | |
|---|---|
| A Claude Design project sits in a personal account and must end up in an org account (or the reverse) | **Yes** — this is the primary case |
| You have a React component library in git and want a Claude Design design-system project built from it | **Yes** — the push route, bootstrapping direction |
| Screens went blank after renaming or duplicating a design-system project, and the console is clean | **Yes** — `references/namespace.md`, `scripts/namespace_guard.js` |
| Your prototypes must render with no outbound network, or a CSP blocks `unpkg`/Google Fonts | **Yes** — `references/vendoring.md` |
| You inherited a Claude Design export and do not know what is in it | **Yes** — `references/reconnaissance.md`, `scripts/recon.py` |
| You want the screens' *look* as reference material to redesign from scratch | **No** — use capture or screenshots; this skill preserves, it does not reinterpret |
| You want to move a regular canvas project rather than a design system | **Partly** — the write API targets design-system projects only; recon and backup still apply; see `references/designsync-api.md` and `references/alternatives.md` |
| You expect a one-click transfer | **No such thing exists.** This is the disciplined route, and it is several hours of careful work the first time |

## Install

The repository root **is** the skill directory (`SKILL.md`, `references/`, `scripts/` at top level), so installing is a single clone and updating is `git pull`:

```sh
# every project on this machine (user scope)
git clone https://github.com/gabrielmouallem/claude-design-transport.git ~/.claude/skills/claude-design-transport

# one project only (project scope; commit the directory or add it as a submodule)
git clone https://github.com/gabrielmouallem/claude-design-transport.git .claude/skills/claude-design-transport
```

If you run Claude Code with a custom `CLAUDE_CONFIG_DIR` (see `references/account-routing.md`), clone into `$CLAUDE_CONFIG_DIR/skills/claude-design-transport` instead. Claude Code discovers the skill from `SKILL.md`'s frontmatter at the start of the next session; verify by typing `/claude-design-transport` or asking "what is in this design export?".

Scripts need Python 3.9+ (standard library only) and Node ≥ 22 (`node --check`, and the global `WebSocket` used by the headless-Chrome verification pattern). Writing to a Claude Design project needs design-system authorization in Claude Code: run `/design-login`. It is a separate channel from the session's own login.

## The core insight, in one paragraph

The uploads folder is a weak ingestion channel, not a permission wall: whatever you upload, the model re-emits an interpretation of. The DesignSync tool, by contrast, writes bytes to arbitrary project paths behind an explicit plan boundary. So a "migration" is a file transfer with three complications — the compiled bundle's global is named after the project it was built in and must be retargeted deterministically; the pages depend on CDNs the destination may block, and the standalone export you were about to delete already contains every vendor file needed to fix that; and the platform can recompile behind your back, so the artifact you push must be self-consistent (namespace, `sourceHashes`, manifest and sources agreeing) and every page must fail loud, naming what it expected and what it found, rather than rendering blank with a clean console. Do those three things, push in a fixed order with the large files isolated, and prove the result by set equality before you open anything.

## Porting this to another team

Everything in this repo that is *observed* rather than *documented* carries a **Verified as of** block with the date and a one-line re-verification. Do not trust numbers you found in a repo online; each of these is cheap to re-check:

- **The namespace derivation rule** (`<display name with non-alphanumerics removed>_<first 6 hex of project id>`) is empirical, confirmed on exactly one project whose name was Title Case words. Lowercase-first words, digits and punctuation are untested, and whether the stem uses the name at compile time or at creation could not be distinguished. Re-verify with one read: `get_file _ds_manifest.json` on any design-system project you can see, compare `.namespace` to its name and id.
- **The write cap** is a measurement with a date (3,137,752 bytes accepted on 2026-09-15), not a spec. Re-verify with one probe: your largest file, alone, in its own `write_files` call, after the small files.
- **The `get_file` cap** (256 KiB) is stated by the tool's own description; re-read that description — the method set may change.
- **Sandbox CSP behaviour** was *inferred* from the CSP that Artifacts enforce (scripts only from a short allowlist; `unpkg` blocked silently). It was never confirmed for the Design System pane. The vendoring route makes the question moot rather than answering it. Re-verify by opening one pushed page with the network panel open.
- **The tool's method set and required parameters** (for example `finalize_plan` refusing to run without an explicit `deletes`, even empty) were observed on 2026-09-15. Re-read the tool schema before relying on any of `references/designsync-api.md`.

## Provenance

This skill was extracted from **one completed execution on 2026-09-15**: a design system of 67 exported components, 397 tokens and 29 preview cards, plus a fully built prototype of 23 HTML pages, moved between two design-system projects on different accounts. 209 files, 9,679,007 bytes, zero deletes; `list_files` set equality passing in both directions; no size cap hit; the manifest read back with the intended namespace before any page was opened; every locally verified page making zero external network requests.

There are **no synthetic evaluations** in this repo, deliberately. Testing this skill for real means performing another irreversible migration against a live account; a benchmark loop would either be fake or dangerous. The real test already happened, once, and its records are the basis for every claim here. `HISTORY.md` tells how it went, including where the plan was wrong.

## Repo map

```
SKILL.md                      the procedure — under 500 lines; depth lives in references/
HISTORY.md                    how each rule was bought, in order, honestly
references/
  namespace.md                derivation rule, where the literal lives, sourceHashes, the guard, recompile branches
  vendoring.md                the CDN risk, decoding vendor files from the export, SRI verification, icon CSS
  designsync-api.md           methods, caps, project type, authorization, the mandatory push order, the tautology trap
  reconnaissance.md           characterising a bundle structurally without loading it into context
  account-routing.md          personal vs org accounts, parallel logins, model routing, the native-migration trap
  alternatives.md             capture, prompt reproduction, deploy-and-recapture, reimplementations — and when each is right
scripts/
  recon.py                    structural characterisation; never reads large files whole
  retarget_namespace.py       the gated rewrite: dry-run, then apply only with the dry-run's numbers restated
  verify_tree.py              the assertion battery
  vendor_from_export.py       decode React/Babel/fonts/icon CSS from a standalone export and verify them
  namespace_guard.js          the reference fail-loud guard
```

MIT licensed. See `LICENSE`.
