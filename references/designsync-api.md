# The DesignSync tool: what it does, what it will not tell you, and the push order

> **Verified as of 2026-09-15** by reading the tool's schema in Claude Code and executing one full push. The method set, required parameters and caps below are *observations of that day*, not a specification. Re-verify: load the tool schema (`ToolSearch select:DesignSync`) and read the current description before your first call. The write cap is a measurement: **3,137,752 bytes accepted for a single file** — re-verify with one probe (your largest file, alone, in its own `write_files` call).

## Methods, as observed

| Kind | Method | Notes |
|---|---|---|
| Read | `list_projects` | Only projects the user can **write** to. Returns `projectId`, `name`, `ownerDisplayName`, `isOwned`, `updatedAt`. No URL. |
| Read | `get_project` | `name`, `type`, `ownerDisplayName`, `canEdit`. **No `createdAt`, no URL.** Use it to confirm `type` before anything else. |
| Read | `list_files` | Every path in the project — directory entries *and* files mixed. A directory is any entry that prefixes another with `/`. |
| Read | `get_file` | One file, **capped at 256 KiB**. Returns `{content, contentType, isBase64, truncated}`; binary comes back as base64 (observed on a 1,716-byte woff2). |
| Setup | `create_project` | New design-system project owned by the user; takes `name`. |
| Boundary | `finalize_plan` | Locks exact `writes`, `deletes` and `localDir`; returns `planId`. **`deletes` must be passed explicitly even when empty** — the tool rejected the call without it. Max 256 entries per list; globs allowed (`*` one segment, `**` any depth, ≤3 wildcards per pattern). |
| Write | `write_files` | Every path must be in the plan's writes. Prefer `localPath` (the tool reads from disk; contents never enter the model's context). Max 256 files per call. Returns `{written: n}`. |
| Write | `delete_files` | Every path must be in the plan's deletes. |
| Legacy | `register_assets` / `unregister_assets` | Card registration now comes from each preview HTML's first-line `<!-- @dsCard … -->`, compiled into `_ds_manifest.json` by the app's self-check. A mid-2026 hands-on report found the automatic path not firing and fell back to explicit registration — version skew is real; check which you are on. |
| Other | `report_validate` | Aggregate counts from a render check. |

**No rename. No restore. No version history. No whoami or identity enumeration.** The tool's description says it exists to keep a local component library in sync with a project "incrementally, one component at a time, never as a wholesale replace"; a clean-in-place migration is the exact thing it disclaims.

## Project type is immutable

A design-system project is `type: PROJECT_TYPE_DESIGN_SYSTEM`, fixed at creation. Pushing files into a regular project never makes it one. Check `get_project` first; use `create_project` if there is no writable design-system project.

## Authorization and identity

- `/design-login` is a **separate** authorization from the session's own login. It works even when the session authenticates with an API key or a provider token. Until it has run, every call fails with a message telling you to run it.
- There is **no way to preview which account a login will land on**, and no method that returns the account. Identity is visible only as a side effect of project reads — `ownerDisplayName` / `isOwned` on `list_projects`, `ownerDisplayName` / `canEdit` on `get_project`. Different endpoints return **different forms of the same owner's name** (a short display name on one, a full account name on the other); do not treat that as two accounts.
- A project named in an old export's namespace stem may be in **neither** writable list (shared, org-owned, deleted). Ask the human; the tool cannot tell you.

## The mandatory push order, and why

1. **Print the plan as text before `finalize_plan`.** Every write path, the delete list stated explicitly even when empty, the target id, the local directory. Reconcile the count against your plan document; a one-off discrepancy in the recorded case was a summation error in the plan's prose, caught here and not after. The permission dialog is where the operator approves; the conversation is where they review.
2. **`finalize_plan`** — exact paths (globs are for deletes you should not be doing), `deletes: []`, `localDir` = the tree.
3. **`write_files` #1** — everything under 1 MB, by `localPath`.
4. **One `write_files` call per file ≥ 1 MB, largest last.** A cap rejection then names the file instead of killing a batch and leaving you to guess which member tripped it. If a call is rejected: **stop and report.** Do not improvise a workaround (splitting, minifying, dropping) without saying so — the workaround may change what the destination compiles.
5. **`list_files`** — set equality with the local push set, **both directions**, directory entries filtered out. Report any diff.
6. **`get_file _ds_manifest.json`** and read `.namespace` **before opening any page or pane.** Opening the pane is the likeliest trigger of a recompile; you want the pre-recompile reading on record.

## The tautology trap

The manifest you read back in step 6 is *your* file if the platform has not touched it — byte-compare it to what you pushed (it was identical, 56,449 bytes, same sha256, in the recorded case). That confirms the artifact is intact and self-consistent. **It does not test the namespace derivation rule.** Only a recompile does. Read again after the first open (`namespace.md`, "Recompile branches"). Observed 2026-09-15: opening the pane once **did** trigger the self-check — the manifest came back regenerated, `globalCssPaths` expanded to every sheet `styles.css` imports, `fonts` populated from the local `@font-face` rules, `brandFonts` extended — with the namespace unchanged. The before/after diff is the evidence that anything ran.

## Deletes, if you ever must

- Plan lists cap at 256 entries; a large remote-only set forces globs.
- Any glob broad enough to be convenient (`components/**`, `assets/**`, `tokens/**`) will also match a file you are keeping or writing. In the recorded audit the only collision-free delete set for a 333-file remote-only tree was 73 entries — 32 globs plus 41 exact leftovers — and was never executed.
- There is no restore. Archive by `get_file` first (text files; the 256 KiB cap and binary handling limit what you can save), get written consent naming the disposable content, and only then plan deletes. Freezing — zero writes, zero deletes — is almost always the right call for a source or sibling project.

## Sizes observed (2026-09-15)

| What | Value |
|---|---|
| `get_file` cap | 256 KiB (stated by the tool) |
| Largest single file accepted by `write_files` | 3,137,752 B |
| Files per `write_files` call | 206 in one call, accepted (cap stated: 256) |
| Total pushed | 209 files, 9,679,007 B, four write calls, zero rejections |
