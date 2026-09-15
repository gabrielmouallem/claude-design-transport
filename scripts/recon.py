#!/usr/bin/env python3
"""recon.py — structural characterisation of a Claude Design export tree.

usage: recon.py <tree> [--json OUT] [--max-read-mb 2] [--snapshots-dir DIR]

WHAT IT ASSUMES
  - <tree> is an unpacked Claude Design export (a design-system project, a prototype, or both).
  - Standard artifact names: _ds_manifest.json, _ds_bundle.js, first-line "<!-- @dsCard ... -->" markers,
    "<script type=\"__bundler/manifest\">" in standalone exports. Anything else is reported as "not recognised",
    not guessed at.

WHAT IT REFUSES TO DO
  - It never reads a file larger than --max-read-mb whole. Large files get their first 64 KB (enough for the
    bundle header line and the bundler-loader markers) and their byte size. Nothing here belongs in a model's
    context window.
  - It does not modify the tree. It does not call any remote API.

WHAT IT REPORTS (stdout, plus --json)
  inventory      totals, top-level directories, largest files, which files were not read whole
  manifest       namespace, counts (components/cards/tokens/themes/templates/globalCssPaths/fonts/startingPoints),
                 card groups, whether component/card paths resolve, whether "assets/" appears at all
  bundle         header keys, format, namespace, sourceHashes count, hash-scheme check (sha256[:12]) over ALL
                 entries, the IIFE global, how many times the namespace literal occurs, external hosts inside it
  loaders        HTML files that are standalone bundler exports (derived output — decode before discarding)
  cards          first-line @dsCard markers by group, compared to the manifest's cards
  shells         clusters of near-identical HTML shells and members whose varying-line count differs from the mode
  hosts          every external https host literal, per file
  namespace      per-file occurrence counts of the manifest's namespace literal, split by "window." form
  assets         referenced / orphaned / missing under assets/, with a warning if paths are built dynamically
  inputs         design-time inputs (uploads/pasted-*.png) that need not travel
  snapshots      (optional) dated ZIPs: file counts and manifest namespace per snapshot

Verified as of 2026-09-15 against one export. Formats may change; the tool prints what it could not parse.
"""
import sys, os, re, json, hashlib, zipfile
from collections import Counter, defaultdict

TEXT_EXT = (".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".css", ".md", ".json", ".txt", ".svg")
HOST_RE = re.compile(r"https?://([a-z0-9.-]+\.[a-z]{2,})", re.I)


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return "%.1f %s" % (n, u) if u != "B" else "%d B" % n
        n /= 1024.0


def head_bytes(path, n=65536):
    with open(path, "rb") as fh:
        return fh.read(n).decode("utf-8", "ignore")


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__); sys.exit(2)
    root = os.path.abspath(args[0])
    out_json = args[args.index("--json") + 1] if "--json" in args else None
    max_read = float(args[args.index("--max-read-mb") + 1]) * 1024 * 1024 if "--max-read-mb" in args else 2 * 1024 * 1024
    snaps = args[args.index("--snapshots-dir") + 1] if "--snapshots-dir" in args else None
    R = {}

    # ---------------- inventory
    files = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git"]
        for f in fns:
            p = os.path.join(dp, f)
            files[os.path.relpath(p, root)] = os.path.getsize(p)
    total = sum(files.values())
    big = {p: s for p, s in files.items() if s > max_read}
    R["inventory"] = {"files": len(files), "bytes": total, "top_level": dict(Counter((p.split("/")[0] if "/" in p else "(root)") for p in files)),
                      "largest": sorted(files.items(), key=lambda kv: -kv[1])[:8], "not_read_whole": sorted(big)}
    print("== inventory: %d files, %s ==" % (len(files), human(total)))
    for k, v in sorted(R["inventory"]["top_level"].items()): print("  %4d  %s" % (v, k))
    print("  largest:"); [print("    %10s  %s" % (human(s), p)) for p, s in R["inventory"]["largest"]]
    if big: print("  NOT read whole (> %s): %s" % (human(max_read), ", ".join(sorted(big))))

    def text(rel):
        p = os.path.join(root, rel)
        if files[rel] > max_read:
            return head_bytes(p)
        try:
            return open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            return ""

    text_files = [p for p in files if p.lower().endswith(TEXT_EXT)]

    # ---------------- manifest
    namespace = None
    if "_ds_manifest.json" in files:
        try:
            m = json.loads(text("_ds_manifest.json"))
            namespace = m.get("namespace")
            cards = m.get("cards", []); comps = m.get("components", [])
            card_paths = [c.get("path") for c in cards]; comp_paths = sorted({c.get("sourcePath") for c in comps})
            R["manifest"] = {
                "namespace": namespace, "components": len(comps), "component_source_files": len(comp_paths),
                "cards": len(cards), "card_groups": dict(Counter(c.get("group") for c in cards)),
                "tokens": len(m.get("tokens", [])), "token_kinds": dict(Counter(t.get("kind") for t in m.get("tokens", []))),
                "themes": [t.get("selector") for t in m.get("themes", [])], "templates": len(m.get("templates", [])),
                "globalCssPaths": m.get("globalCssPaths"), "fonts": m.get("fonts"), "brandFonts": len(m.get("brandFonts", [])),
                "startingPoints": m.get("startingPoints"), "source": m.get("source"),
                "card_paths_missing": [p for p in card_paths if p and p not in files],
                "component_paths_missing": [p for p in comp_paths if p and p not in files],
                "mentions_assets_dir": '"assets/' in text("_ds_manifest.json"),
            }
            print("\n== manifest ==")
            for k in ("namespace", "components", "component_source_files", "cards", "card_groups", "tokens", "token_kinds", "themes", "templates", "globalCssPaths", "fonts", "brandFonts", "startingPoints", "source", "card_paths_missing", "component_paths_missing", "mentions_assets_dir"):
                print("  %-25s %s" % (k, R["manifest"][k]))
            if not R["manifest"]["mentions_assets_dir"]:
                print("  NOTE: the manifest names no asset; a manifest-only import would carry none of assets/")
        except Exception as e:
            R["manifest"] = {"error": str(e)}; print("\n== manifest: could not parse: %s" % e)
    else:
        print("\n== manifest: _ds_manifest.json not found ==")

    # ---------------- bundle
    if "_ds_bundle.js" in files:
        p = os.path.join(root, "_ds_bundle.js")
        with open(p, "rb") as fh:
            line1 = fh.readline().decode("utf-8", "ignore").rstrip("\n")
            rest_head = fh.read(4096).decode("utf-8", "ignore")
        mm = re.fullmatch(r"/\* @ds-bundle: (.*) \*/", line1)
        B = {"bytes": files["_ds_bundle.js"]}
        if mm:
            try:
                h = json.loads(mm.group(1))
                B.update({"header_keys": list(h), "format": h.get("format"), "namespace": h.get("namespace"),
                          "components": len(h.get("components", [])), "sourceHashes": len(h.get("sourceHashes", {}))})
                match = mis = missing = 0; bad = []
                for path, val in h.get("sourceHashes", {}).items():
                    fp = os.path.join(root, path)
                    if not os.path.exists(fp): missing += 1; continue
                    if hashlib.sha256(open(fp, "rb").read()).hexdigest()[:12] == val: match += 1
                    else: mis += 1; bad.append(path)
                B["hash_check"] = {"scheme": "sha256[:12]", "match": match, "mismatch": mis, "missing_files": missing, "mismatched_paths": bad[:10]}
                B["header_roundtrip_compact"] = json.dumps(h, separators=(",", ":"), ensure_ascii=False) == mm.group(1)
            except Exception as e:
                B["header_error"] = str(e)
        g = re.search(r"window\.([A-Za-z0-9_]+) = window\.\1 \|\| \{\}", rest_head)
        B["iife_global"] = g.group(1) if g else None
        # occurrence counts and hosts: stream the file in one pass (it may be > max_read; counting is safe)
        data = open(p, encoding="utf-8", errors="ignore").read()
        if namespace:
            B["namespace_literal_occurrences"] = data.count(namespace)
            B["namespace_window_form"] = data.count("window." + namespace)
        B["external_hosts"] = dict(Counter(h.lower() for h in HOST_RE.findall(data)))
        B["not_minified_hint"] = data.count("\n") > 1000
        del data
        R["bundle"] = B
        print("\n== bundle ==")
        for k, v in B.items(): print("  %-30s %s" % (k, v))

    # ---------------- bundler loaders (standalone exports)
    loaders = []
    for rel in files:
        if rel.lower().endswith((".html", ".htm")) and "__bundler/manifest" in head_bytes(os.path.join(root, rel)):
            loaders.append({"path": rel, "bytes": files[rel]})
    R["loaders"] = loaders
    print("\n== standalone bundler exports (derived output; decode before discarding — see vendoring.md) ==")
    print("  " + ("\n  ".join("%10s  %s" % (human(l["bytes"]), l["path"]) for l in loaders) if loaders else "none"))

    # ---------------- cards
    cards_by_group = Counter(); card_files = []
    for rel in files:
        if rel.lower().endswith(".html"):
            first = head_bytes(os.path.join(root, rel), 400).split("\n", 1)[0]
            if first.startswith("<!-- @dsCard"):
                grp = re.search(r'group="([^"]*)"', first); cards_by_group[grp.group(1) if grp else "?"] += 1; card_files.append(rel)
    R["cards"] = {"first_line_markers": len(card_files), "by_group": dict(cards_by_group), "files": sorted(card_files)}
    print("\n== first-line @dsCard markers: %d  %s ==" % (len(card_files), dict(cards_by_group)))
    if R.get("manifest", {}).get("cards") is not None:
        mc = set(R["manifest"].get("card_paths_missing", []))
        print("  manifest cards: %d  (%s)" % (R["manifest"]["cards"], "equal" if R["manifest"]["cards"] == len(card_files) else "DIFFERENT — reconcile"))

    # ---------------- shells: cluster by skeleton, then compare the SHAPE of the varying lines.
    # "Only N lines vary" is not enough: an extra statement on a shared line (a third localStorage key, say) keeps
    # the line count identical. Blank every string literal in the varying lines and compare the resulting shapes.
    VARY = ("@dsCard", "<title>", "localStorage.setItem", ".render(")

    def shape(line):
        line = re.sub(r"<title>.*?</title>", "<title></title>", line)
        return re.sub(r"'[^']*'", "''", re.sub(r'"[^"]*"', '""', line))

    clusters = defaultdict(list)
    for rel in files:
        if not rel.lower().endswith(".html") or files[rel] > max_read: continue
        lines = text(rel).split("\n")
        skel = "\n".join(l for l in lines if not any(v in l for v in VARY))
        shapes = tuple(sorted(shape(l) for l in lines if any(v in l for v in VARY)))
        clusters[(os.path.dirname(rel), hashlib.sha256(skel.encode()).hexdigest()[:12])].append((rel, shapes))
    shell_report = []
    for (d, k), members in clusters.items():
        if len(members) < 2: continue
        mode = Counter(s for _, s in members).most_common(1)[0][0]
        outliers = [r for r, s in members if s != mode]
        shell_report.append({"dir": d, "members": len(members), "varying_lines": len(mode), "shape_outliers": outliers})
    R["shells"] = shell_report
    print("\n== near-identical shell clusters — members whose varying-line SHAPES differ from the cluster: diff them by hand ==")
    for s in shell_report:
        print("  %s: %d members share a skeleton; %d varying lines; shape outliers=%s" % (s["dir"] or ".", s["members"], s["varying_lines"], s["shape_outliers"] or "none"))
    if not shell_report: print("  none")

    # ---------------- hosts
    hosts = defaultdict(Counter)
    for rel in text_files:
        if rel in big and not rel.endswith(".js"): continue
        for h in HOST_RE.findall(text(rel)): hosts[h.lower()][rel] += 1
    R["hosts"] = {h: dict(c) for h, c in hosts.items()}
    print("\n== external hosts (files referencing) ==")
    for h, c in sorted(hosts.items(), key=lambda kv: -len(kv[1])): print("  %-32s %3d files" % (h, len(c)))

    # ---------------- namespace footprint
    if namespace:
        occ = {}
        for rel in text_files:
            t = text(rel); c = t.count(namespace)
            if c: occ[rel] = {"total": c, "window_form": t.count("window." + namespace)}
        R["namespace"] = {"literal": namespace, "files": len(occ), "occurrences": sum(v["total"] for v in occ.values()),
                          "window_form_files": sum(1 for v in occ.values() if v["window_form"]), "per_file": occ}
        print("\n== namespace literal %s: %d files, %d occurrences (%d files in window. form) ==" % (namespace, len(occ), R["namespace"]["occurrences"], R["namespace"]["window_form_files"]))

    # ---------------- assets
    present = {p[len("assets/"):] for p in files if p.startswith("assets/")}
    refd = set(); dynamic = []
    for rel in text_files:
        if rel in big: continue
        t = text(rel)
        for m in re.finditer(r"(?:\.\./)*assets/([A-Za-z0-9_./-]+)", t): refd.add(m.group(1))
        if re.search(r"[\"']assets/[\"']\s*\+|`[^`]*assets/\$\{", t): dynamic.append(rel)
    R["assets"] = {"present": len(present), "used": sorted(present & refd), "orphaned": sorted(present - refd), "missing": sorted(refd - present), "dynamic_path_construction_in": dynamic}
    print("\n== assets: %d present, %d used, %d orphaned, %d referenced-but-missing ==" % (len(present), len(present & refd), len(present - refd), len(refd - present)))
    if present - refd: print("  orphaned: %s" % ", ".join(sorted(present - refd)))
    if refd - present: print("  MISSING:  %s" % ", ".join(sorted(refd - present)))
    if dynamic: print("  WARNING dynamic asset paths in: %s (literal grep may miss references)" % ", ".join(dynamic))

    # ---------------- design-time inputs
    pasted = [p for p in files if p.startswith("uploads/") and "pasted-" in p]
    R["inputs"] = {"uploads_pasted": len(pasted), "bytes": sum(files[p] for p in pasted)}
    print("\n== design-time inputs: %d pasted images under uploads/ (%s) — need not travel ==" % (len(pasted), human(R["inputs"]["bytes"])))

    # ---------------- snapshots
    if snaps and os.path.isdir(snaps):
        rows = []
        for z in sorted(os.listdir(snaps)):
            if not z.endswith(".zip"): continue
            try:
                zf = zipfile.ZipFile(os.path.join(snaps, z)); names = zf.namelist()
                man = next((n for n in names if n.endswith("_ds_manifest.json")), None)
                ns = json.loads(zf.read(man)).get("namespace") if man else None
                rows.append({"zip": z, "files": sum(1 for n in names if not n.endswith("/")), "namespace": ns})
            except Exception as e:
                rows.append({"zip": z, "error": str(e)})
        R["snapshots"] = rows
        print("\n== snapshots ==")
        for r in rows: print("  %s" % r)
        nss = {r.get("namespace") for r in rows if r.get("namespace")}
        if len(nss) == 1: print("  namespace stable across %d snapshots → project-bound, not content-derived" % len(rows))

    if out_json:
        json.dump(R, open(out_json, "w"), indent=1, default=str); print("\njson → %s" % out_json)


if __name__ == "__main__":
    main()
