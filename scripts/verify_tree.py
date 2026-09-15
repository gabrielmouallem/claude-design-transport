#!/usr/bin/env python3
"""verify_tree.py — the assertion battery to run before any push (and again after any edit).

usage:
  verify_tree.py --root TREE --old OLD --new NEW --expect-new-occurrences N [--expect-new-files F]
        [--exclude PATTERN ...] [--check-js PATH ...] [--allow-host HOST ...] [--allow-host-in PATH ...]
        [--sha256sums FILE --sha-root DIR] [--fontface-css PATH --expect-fontface K]

WHAT IT ASSERTS
  - The OLD namespace literal occurs 0 times (outside excluded paths).
  - The NEW literal occurs exactly N times (and in F files if given). N must account for guard constants:
    every installed guard carries the literal once.
  - `node --check` passes on _ds_bundle.js and on every --check-js file (plain scripts; not JSX/ESM).
  - Bundle header namespace and manifest namespace both equal NEW.
  - Every sourceHashes entry equals sha256(file)[:12] of the file on disk — ALL of them, not a sample.
  - No CDN host literal remains in any text file — unpkg, cdnjs, jsdelivr, Google Fonts, esm.sh, Tailwind CDN,
    jQuery CDN by default; add more with --cdn-host — except hosts on --allow-host or files on --allow-host-in
    (e.g. a canvas loader you deliberately deferred). Every offending host and file is listed. --all-hosts widens
    the check to every external host; expect content links in demo data to surface then, and review them by hand.
  - Optionally: vendored files match a SHA256SUMS file (relative to --sha-root), and a generated @font-face
    stylesheet has exactly K rules.

WHAT IT REFUSES TO DO
  - Modify anything. Read multi-megabyte files it was told to exclude. Treat a sample as proof.

Exit code 0 only when every line is PASS. Verified as of 2026-09-15 (16/16 on the recorded tree).
"""
import sys, os, re, json, hashlib, subprocess, argparse, fnmatch, tempfile

BIN_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".woff2", ".woff", ".ttf", ".otf", ".ico", ".pdf", ".zip")
HOST_RE = re.compile(r"https?://([a-z0-9.-]+\.[a-z]{2,})", re.I)
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True); ap.add_argument("--old", required=True); ap.add_argument("--new", required=True)
    ap.add_argument("--expect-new-occurrences", type=int, required=True); ap.add_argument("--expect-new-files", type=int)
    ap.add_argument("--exclude", action="append", default=[]); ap.add_argument("--check-js", action="append", default=[])
    ap.add_argument("--allow-host", action="append", default=[]); ap.add_argument("--allow-host-in", action="append", default=[])
    ap.add_argument("--cdn-host", action="append", default=[], help="additional CDN hosts to forbid"); ap.add_argument("--all-hosts", action="store_true", help="forbid every external host, not only CDNs")
    ap.add_argument("--sha256sums"); ap.add_argument("--sha-root"); ap.add_argument("--fontface-css"); ap.add_argument("--expect-fontface", type=int)
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    excl = a.exclude + [".git"]

    def excluded(rel):
        return any(fnmatch.fnmatch(rel, p) or rel == p or rel.startswith(p.rstrip("/") + "/") for p in excl)

    texts = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git"]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), root)
            if excluded(rel) or f.lower().endswith(BIN_EXT) or f == ".DS_Store":
                continue
            try:
                texts[rel] = open(os.path.join(root, rel), encoding="utf-8").read()
            except UnicodeDecodeError:
                pass

    old_hits = {r: t.count(a.old) for r, t in texts.items() if a.old in t}
    check(not old_hits, "OLD literal %s = 0 occurrences (found in: %s)" % (a.old, sorted(old_hits) or "none"))
    new_hits = {r: t.count(a.new) for r, t in texts.items() if a.new in t}
    n_occ, n_files = sum(new_hits.values()), len(new_hits)
    check(n_occ == a.expect_new_occurrences, "NEW literal %s: %d occurrences (expect %d) in %d files" % (a.new, n_occ, a.expect_new_occurrences, n_files))
    if a.expect_new_files is not None:
        check(n_files == a.expect_new_files, "NEW literal in %d files (expect %d)" % (n_files, a.expect_new_files))

    def node_check(text, name):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(text); p = fh.name
        r = subprocess.run(["node", "--check", p], capture_output=True, text=True); os.unlink(p)
        check(r.returncode == 0, "node --check %s (%s)" % (name, r.stderr.strip()[:200] or "ok"))

    bundle = texts.get("_ds_bundle.js")
    if bundle is None:
        check(False, "_ds_bundle.js present and readable")
    else:
        node_check(bundle, "_ds_bundle.js")
        line1 = bundle.split("\n", 1)[0]
        m = re.fullmatch(r"/\* @ds-bundle: (.*) \*/", line1)
        check(bool(m), "bundle header recognised")
        if m:
            h = json.loads(m.group(1))
            check(h.get("namespace") == a.new, "bundle header namespace == NEW (got %s)" % h.get("namespace"))
            bad = []
            for path, val in h.get("sourceHashes", {}).items():
                fp = os.path.join(root, path)
                if not os.path.exists(fp):
                    bad.append(path + " (missing)"); continue
                if hashlib.sha256(open(fp, "rb").read()).hexdigest()[:12] != val:
                    bad.append(path)
            check(not bad, "all %d sourceHashes == sha256[:12] of files on disk (bad: %s)" % (len(h.get("sourceHashes", {})), bad[:8] or "none"))
    for p in a.check_js:
        node_check(texts.get(p, ""), p)
    if "_ds_manifest.json" in texts:
        check(json.loads(texts["_ds_manifest.json"]).get("namespace") == a.new, "manifest namespace == NEW")

    CDN_DEFAULT = ["unpkg.com", "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com", "esm.sh", "cdn.tailwindcss.com", "code.jquery.com"]
    watched = None if a.all_hosts else {h.lower() for h in CDN_DEFAULT + a.cdn_host}
    offenders = {}
    for rel, t in texts.items():
        if rel in a.allow_host_in:
            continue
        hosts = {hh.lower() for hh in HOST_RE.findall(t)} - {x.lower() for x in a.allow_host}
        if watched is not None:
            hosts = {hh for hh in hosts if any(hh == w or hh.endswith("." + w) for w in watched)}
        if hosts:
            offenders[rel] = sorted(hosts)
    check(not offenders, "no %s host literals outside the allowlist (offenders: %s)" % ("external" if a.all_hosts else "CDN", json.dumps(offenders)[:600] if offenders else "none"))
    if a.allow_host_in:
        print("info deferred files still carrying hosts: %s" % {p: sorted({hh.lower() for hh in HOST_RE.findall(texts.get(p, ""))}) for p in a.allow_host_in})

    if a.sha256sums and a.sha_root:
        sums = {l.split("  ", 1)[1].strip(): l.split("  ", 1)[0] for l in open(a.sha256sums) if "  " in l}
        bad = []
        for rel, digest in sums.items():
            fp = os.path.join(a.sha_root, rel)
            if not os.path.exists(fp) or hashlib.sha256(open(fp, "rb").read()).hexdigest() != digest:
                bad.append(rel)
        check(not bad, "%d vendored files match SHA256SUMS (bad: %s)" % (len(sums), bad[:8] or "none"))
    if a.fontface_css and a.expect_fontface is not None:
        n = texts.get(a.fontface_css, "").count("@font-face")
        check(n == a.expect_fontface, "%s has %d @font-face rules (expect %d)" % (a.fontface_css, n, a.expect_fontface))

    print("\nverify: %s" % ("ALL PASS" if not fails else "%d FAIL" % len(fails)))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
