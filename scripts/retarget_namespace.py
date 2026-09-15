#!/usr/bin/env python3
"""retarget_namespace.py — gated rewrite of a Claude Design bundle's namespace, with hash recompute and guard install.

usage:
  retarget_namespace.py rewrite --root TREE --old OLD --new NEW [--dry-run]
        [--exclude PATTERN ...] [--remove-lines FILE] [--remove-regex FILE]
        [--apply --expect-files N --expect-occurrences M]
  retarget_namespace.py guard   --root TREE --expected NEW --anchor Component
        [--helper PATH] [--page PATH ...] [--template PATH] [--dry-run | --apply]
  retarget_namespace.py hashes  --root TREE [--apply]

THE DESIGN LESSON THIS TOOL ENCODES
  Every subcommand computes the entire new state in memory, checks preconditions and postconditions, and writes
  NOTHING unless every check passes. Then it re-reads from disk and checks again. When a gate blocks, the gate
  has done its job: fix the assertion if it was stated wrongly (in the recorded execution a helper appeared 4
  times, not once, and the assertion — not the gate — was corrected); never bypass the gate.

WHAT `rewrite` ASSUMES
  - OLD is the current namespace literal (see _ds_manifest.json "namespace"); NEW is the value the destination
    will mint (see references/namespace.md for the derivation rule and its caveats).
  - _ds_bundle.js has the observed shape: line 1 `/* @ds-bundle: {json} */` with "namespace" and "sourceHashes",
    and sourceHashes values are sha256(file)[:12]. Both are asserted, not assumed.
  - --remove-lines FILE: exact lines (one per line) to delete wherever they occur — e.g. CDN icon-CSS loaders in
    sources AND their compiled copies in the bundle. --remove-regex FILE: multi-line regexes (one per line, use
    \\n) for compiled blocks. The dry run prints how many matches each has; apply removes them all and asserts 0 left.
  - Apply is gated on the operator restating the dry run's numbers: --expect-files and --expect-occurrences must
    equal the OLD counts the tool computes. That is what "apply only after a clean dry run" means here.
  - The footprint identity (bundle count == header 1 + IIFE 2 + sum over compiled sources) proves the literal was
    fully enumerated on an UNTOUCHED export and is printed as PASS/WARN. It is enforced only with --strict-footprint,
    because once guards are installed each guarded source carries one extra literal its compiled copy lacks — and
    a re-targeting iteration (the platform minted a different value) runs on exactly such a tree.

WHAT `guard` ASSUMES
  - scripts/namespace_guard.js sits next to this file; its <Namespace>_<id6> and <ShellComponent> placeholders
    are filled from --expected and --anchor. --helper gets the guard prepended; each --page gets an inline
    <script> right after its `_ds_bundle.js"></script>` tag; --template (the canvas base loader) gets the
    template variant as `s.onload` before `document.head.appendChild(s);`. sourceHashes are recomputed if the
    helper is a hashed source.

WHAT IT REFUSES TO DO
  - Write anything when a check fails. Touch .git. Guess at counts. Bind a lookalike namespace (that is the
    guard's rule too).

Verified as of 2026-09-15 on one tree (57 files / 125 occurrences rewritten; 78 sourceHashes re-verified).
"""
import sys, os, re, json, hashlib, subprocess, argparse, fnmatch, tempfile

BUNDLE = "_ds_bundle.js"
MANIFEST = "_ds_manifest.json"
BIN_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".woff2", ".woff", ".ttf", ".otf", ".ico", ".pdf", ".zip")
HEADER_RE = re.compile(r"/\* @ds-bundle: (.*) \*/")
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)
    return cond


def finish(label):
    print("\n%s: %s" % (label, "ALL PASS" if not fails else "%d FAIL" % len(fails)))
    sys.exit(0 if not fails else 1)


class Tree:
    def __init__(self, root, excludes):
        self.root = os.path.abspath(root)
        self.excludes = list(excludes) + [".git/*", ".git"]

    def excluded(self, rel):
        return any(fnmatch.fnmatch(rel, p) or rel.startswith(p.rstrip("*").rstrip("/") + "/") for p in self.excludes)

    def text_files(self):
        for dp, dns, fns in os.walk(self.root):
            dns[:] = [d for d in dns if d != ".git"]
            for f in fns:
                rel = os.path.relpath(os.path.join(dp, f), self.root)
                if self.excluded(rel) or f.lower().endswith(BIN_EXT) or f == ".DS_Store":
                    continue
                yield rel

    def read(self, rel):
        return open(os.path.join(self.root, rel), encoding="utf-8").read()

    def read_bytes(self, rel):
        return open(os.path.join(self.root, rel), "rb").read()

    def write_all(self, contents):
        for rel, txt in contents.items():
            with open(os.path.join(self.root, rel), "w", encoding="utf-8") as fh:
                fh.write(txt)

    def scan(self, lit, override=None):
        out = {}
        for rel in self.text_files():
            try:
                t = override[rel] if override and rel in override else self.read(rel)
            except UnicodeDecodeError:
                continue
            c = t.count(lit)
            if c:
                out[rel] = c
        return out


def sha12(b):
    return hashlib.sha256(b).hexdigest()[:12]


def parse_header(bundle_text):
    line1, rest = bundle_text.split("\n", 1)
    m = HEADER_RE.fullmatch(line1)
    if not m:
        raise SystemExit("bundle header not recognised: expected `/* @ds-bundle: {...} */` on line 1")
    return json.loads(m.group(1)), m.group(1), rest


def dump_header(h):
    return json.dumps(h, separators=(",", ":"), ensure_ascii=False)


def recompute_hashes(tree, bundle_text, new_contents):
    h, raw, rest = parse_header(bundle_text)
    changed = []
    for path, old in h.get("sourceHashes", {}).items():
        b = new_contents[path].encode("utf-8") if path in new_contents else tree.read_bytes(path)
        new = sha12(b)
        if new != old:
            changed.append(path)
            h["sourceHashes"][path] = new
    return "/* @ds-bundle: " + dump_header(h) + " */\n" + rest, changed


def hashes_consistent(tree, bundle_text, new_contents=None):
    h, _, _ = parse_header(bundle_text)
    bad = []
    for path, val in h.get("sourceHashes", {}).items():
        try:
            b = (new_contents or {}).get(path)
            b = b.encode("utf-8") if b is not None else tree.read_bytes(path)
        except FileNotFoundError:
            bad.append(path + " (missing)"); continue
        if sha12(b) != val:
            bad.append(path)
    return bad


def node_check(text, esm=False):
    with tempfile.NamedTemporaryFile("w", suffix=".mjs" if esm else ".js", delete=False, encoding="utf-8") as fh:
        fh.write(text); p = fh.name
    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
    os.unlink(p)
    return r.returncode == 0, r.stderr.strip()[:300]


# ------------------------------------------------------------------ rewrite
def cmd_rewrite(a):
    tree = Tree(a.root, a.exclude or [])
    old, new = a.old, a.new
    lines_to_remove = [l.rstrip("\n") for l in open(a.remove_lines, encoding="utf-8")] if a.remove_lines else []
    lines_to_remove = [l for l in lines_to_remove if l.strip()]
    regexes = [re.compile(l.rstrip("\n").encode().decode("unicode_escape")) for l in open(a.remove_regex, encoding="utf-8") if l.strip()] if a.remove_regex else []

    print("== preconditions ==")
    occ = tree.scan(old)
    files_n, occ_n = len(occ), sum(occ.values())
    print("info OLD literal %s: %d files / %d occurrences" % (old, files_n, occ_n))
    for rel, c in sorted(occ.items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
        print("      %4d  %s" % (c, rel))
    if files_n > 15: print("      … %d more files" % (files_n - 15))
    check(files_n > 0, "the OLD literal occurs somewhere")
    check(BUNDLE in occ, "the bundle carries the literal")
    bundle = tree.read(BUNDLE)
    h, raw, _ = parse_header(bundle)
    check(dump_header(h) == raw, "bundle header JSON re-serialises byte-identically (compact separators, key order)")
    check(h.get("namespace") == old, "bundle header namespace == OLD")
    n_hash = len(h.get("sourceHashes", {}))
    bad = hashes_consistent(tree, bundle)
    check(not bad, "all %d sourceHashes == sha256[:12] of current files (bad: %s)" % (n_hash, bad[:5] or "none"))
    per_src = sum(c for rel, c in occ.items() if rel in h.get("sourceHashes", {}))
    print("info bundle occurrences %d; header 1 + IIFE 2 + compiled sources %d = %d" % (occ[BUNDLE], per_src, 3 + per_src))
    footprint_ok = occ[BUNDLE] == 3 + per_src
    if a.strict_footprint:
        check(footprint_ok, "bundle count == header + IIFE + sum of compiled sources' counts (--strict-footprint)")
    else:
        print(("PASS " if footprint_ok else "WARN ") + "footprint: bundle count %s header + IIFE + compiled-source sum — equal on an untouched export; after guards are installed each guarded source carries one extra literal its compiled copy lacks (pass --strict-footprint to enforce)" % ("==" if footprint_ok else "!="))
    manifest = tree.read(MANIFEST) if os.path.exists(os.path.join(tree.root, MANIFEST)) else None
    if manifest is not None:
        check(json.loads(manifest).get("namespace") == old, "manifest namespace == OLD")
    line_counts = {l: sum(tree.read(rel).count(l + "\n") for rel in tree.text_files()) for l in lines_to_remove}
    for l, c in line_counts.items(): print("info remove-line ×%d: %s" % (c, l[:100]))
    regex_counts = {r.pattern: sum(len(r.findall(tree.read(rel))) for rel in tree.text_files()) for r in regexes}
    for p, c in regex_counts.items(): print("info remove-regex ×%d: %s" % (c, p[:100]))
    if fails:
        finish("rewrite preconditions")

    if not a.apply:
        print("\nDRY RUN — nothing written. To apply, restate these numbers:\n  --apply --expect-files %d --expect-occurrences %d" % (files_n, occ_n))
        sys.exit(0)
    check(a.expect_files == files_n and a.expect_occurrences == occ_n, "operator restated the dry-run numbers (files %s==%d, occurrences %s==%d)" % (a.expect_files, files_n, a.expect_occurrences, occ_n))
    if fails:
        finish("rewrite gate")

    print("\n== mutations (in memory) ==")
    new_contents = {rel: tree.read(rel).replace(old, new) for rel in occ}
    for rel in list(tree.text_files()):
        t = new_contents.get(rel, None)
        src = t if t is not None else tree.read(rel)
        changed = src
        for l in lines_to_remove:
            changed = changed.replace(l + "\n", "")
        for r in regexes:
            changed = r.sub("", changed)
        if changed != src:
            new_contents[rel] = changed
    b, changed_hashes = recompute_hashes(tree, new_contents[BUNDLE], new_contents)
    new_contents[BUNDLE] = b

    print("\n== postconditions ==")
    check(sum(tree.scan(old, new_contents).values()) == 0, "OLD literal count after rewrite = 0")
    newc = tree.scan(new, new_contents)
    check(len(newc) == files_n and sum(newc.values()) == occ_n, "NEW literal: %d files / %d occurrences == OLD's %d / %d" % (len(newc), sum(newc.values()), files_n, occ_n))
    for l in lines_to_remove:
        check(sum(new_contents.get(rel, tree.read(rel)).count(l + "\n") for rel in tree.text_files()) == 0, "removed everywhere: %s" % l[:80])
    for r in regexes:
        check(sum(len(r.findall(new_contents.get(rel, tree.read(rel)))) for rel in tree.text_files()) == 0, "regex removed everywhere: %s" % r.pattern[:80])
    hh, _, _ = parse_header(b)
    check(hh.get("namespace") == new, "bundle header namespace == NEW")
    expected_changed = sorted(p for p in hh.get("sourceHashes", {}) if p in new_contents and new_contents[p] != tree.read(p))
    check(sorted(changed_hashes) == expected_changed, "sourceHashes recomputed for exactly the edited hashed sources (%d)" % len(changed_hashes))
    check(not hashes_consistent(tree, b, new_contents), "all sourceHashes consistent with the new contents")
    ok, err = node_check(b)
    check(ok, "node --check on the rewritten bundle (%s)" % (err or "ok"))
    if manifest is not None:
        check(json.loads(new_contents[MANIFEST]).get("namespace") == new, "manifest namespace == NEW")
    if fails:
        finish("rewrite postconditions (nothing written)")
    tree.write_all(new_contents)
    print("\nwrote %d files" % len(new_contents))
    check(not hashes_consistent(tree, tree.read(BUNDLE)), "disk re-read: all sourceHashes consistent")
    check(sum(tree.scan(old).values()) == 0, "disk re-read: OLD literal = 0")
    finish("rewrite")


# ------------------------------------------------------------------ guard
def load_guard(expected, anchor):
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "namespace_guard.js"), encoding="utf-8").read()
    main_part, _, template_part = src.partition("/* TEMPLATE VARIANT")
    iife = main_part[main_part.index("(function () {"):].rstrip() + "\n"   # drop the file's doc header; inject only the guard
    main_part = ("/* namespace-guard: runs after _ds_bundle.js and before any screen. Fails loud; never guesses. */\n" + iife).replace("<Namespace>_<id6>", expected).replace("<ShellComponent>", anchor)
    tmpl_lines = [l[3:] if l.startswith(" * ") else l for l in template_part.split("\n") if l.strip().startswith("*")]
    tmpl = "\n".join(l for l in tmpl_lines if l.startswith("  s.onload") or l.startswith("    ") or l.startswith("  };"))
    tmpl = tmpl.replace("<Namespace>_<id6>", expected).replace("<ShellComponent>", anchor) + "\n"
    return main_part, tmpl


def cmd_guard(a):
    tree = Tree(a.root, [])
    guard, tmpl_guard = load_guard(a.expected, a.anchor)
    print("== preconditions ==")
    ok, err = node_check(guard); check(ok, "guard snippet parses (%s)" % (err or "ok"))
    new = {}
    if a.helper:
        t = tree.read(a.helper); check("bootstrap error" not in t, "%s has no guard yet" % a.helper); new[a.helper] = guard + "\n" + t
    for p in a.page or []:
        t = tree.read(p); tag = '_ds_bundle.js"></script>\n'
        check(t.count(tag) == 1 and "bootstrap error" not in t, "%s: one bundle tag, no guard yet" % p)
        i = t.index(tag) + len(tag) if tag in t else 0
        new[p] = t[:i] + "<script>\n" + guard + "</script>\n" + t[i:]
    if a.template:
        t = tree.read(a.template); anchor_line = "  document.head.appendChild(s);\n"
        check(t.count(anchor_line) == 1 and "s.onload" not in t, "%s: one appendChild(s), no onload yet" % a.template)
        new[a.template] = t.replace(anchor_line, tmpl_guard + anchor_line, 1)
        ok, err = node_check(new[a.template]); check(ok, "template loader parses after insertion (%s)" % (err or "ok"))
    if fails:
        finish("guard preconditions")
    bundle_new, changed = recompute_hashes(tree, tree.read(BUNDLE), new)
    if changed:
        new[BUNDLE] = bundle_new
    print("\n== postconditions ==")
    print("info sourceHashes changed: %s" % (changed or "none"))
    check(not hashes_consistent(tree, new.get(BUNDLE, tree.read(BUNDLE)), new), "all sourceHashes consistent with new contents")
    g = tree.scan("Design-system bootstrap error", new)
    check(len(g) == len([x for x in (a.helper, a.template) if x]) + len(a.page or []), "guard present in every requested place: %s" % sorted(g))
    if fails or not a.apply:
        print("\n%s — nothing written." % ("DRY RUN" if not fails else "FAILED"))
        finish("guard")
    tree.write_all(new)
    check(not hashes_consistent(tree, tree.read(BUNDLE)), "disk re-read: all sourceHashes consistent")
    finish("guard")


# ------------------------------------------------------------------ hashes
def cmd_hashes(a):
    tree = Tree(a.root, [])
    b, changed = recompute_hashes(tree, tree.read(BUNDLE), {})
    print("entries that would change: %d %s" % (len(changed), changed[:10]))
    if a.apply and changed:
        tree.write_all({BUNDLE: b}); check(not hashes_consistent(tree, tree.read(BUNDLE)), "disk re-read consistent")
    finish("hashes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rewrite"); r.add_argument("--root", required=True); r.add_argument("--old", required=True); r.add_argument("--new", required=True)
    r.add_argument("--exclude", action="append", help="glob or dir prefix to leave alone (audit dirs, large exports)")
    r.add_argument("--remove-lines"); r.add_argument("--remove-regex"); r.add_argument("--dry-run", action="store_true"); r.add_argument("--apply", action="store_true")
    r.add_argument("--expect-files", type=int); r.add_argument("--expect-occurrences", type=int)
    r.add_argument("--strict-footprint", action="store_true", help="fail unless bundle count == header + IIFE + compiled-source sum (use on an untouched export)")
    g = sub.add_parser("guard"); g.add_argument("--root", required=True); g.add_argument("--expected", required=True); g.add_argument("--anchor", required=True)
    g.add_argument("--helper"); g.add_argument("--page", action="append"); g.add_argument("--template"); g.add_argument("--dry-run", action="store_true"); g.add_argument("--apply", action="store_true")
    hcmd = sub.add_parser("hashes"); hcmd.add_argument("--root", required=True); hcmd.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    {"rewrite": cmd_rewrite, "guard": cmd_guard, "hashes": cmd_hashes}[a.cmd](a)
