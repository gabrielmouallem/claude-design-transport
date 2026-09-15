#!/usr/bin/env python3
"""vendor_from_export.py — decode vendor files (React, ReactDOM, Babel, fonts, icon CSS) from a Claude Design
standalone HTML export, verify them, and generate the local @font-face stylesheet.

usage:
  vendor_from_export.py EXPORT.html --list
  vendor_from_export.py EXPORT.html --out DIR [--sri-from PAGE.html ...] [--canonical] [--fonts-rel ../assets/fonts]

WHAT IT ASSUMES
  - EXPORT.html is a standalone export: it contains `<script type="__bundler/manifest">` (a JSON object of chunks
    keyed by uuid, each {mime, compressed, data(base64)}; compressed chunks are zlib/gzip) and
    `<script type="__bundler/template">` (a JSON string holding the page HTML with stylesheets inlined and
    `@font-face` rules whose `src: url("<uuid>")` point at chunk keys). Observed 2026-09-15; the tool prints what
    it cannot parse instead of guessing.
  - Vendor JS is identified by banner: react(.development|.production.min).js, react-dom(...).js, and
    @babel/standalone (largest text/javascript chunk mentioning Babel). Nothing else is extracted as "vendor".
  - Icon-font stylesheets are the `<style>` blocks in the template that contain an `@font-face` AND hundreds of
    `:before { content: … }` glyph rules. Google-served typefaces are every other `@font-face` family.

WHAT IT REFUSES TO DO
  - Fetch anything from the network unless --canonical is given (then it fetches the exact versioned URLs found
    in --sri-from pages to compare sha256; nothing is written from the network).
  - Read the export through a language model. This is why the tool exists: `get_file` on a sibling project
    returns binaries as base64 through the model's context; decoding locally is zero reads and exact bytes.
  - Invent hashes. The export carries no per-chunk hash, so verification uses what exists nearby: the pages' own
    SRI `integrity` attributes (--sri-from), canonical npm files (--canonical), and structural checks on fonts.

OUTPUT (under --out)
  js/<name>                    the vendor scripts
  fonts/<slug>[-N].<ext>       every font binary the template's @font-face rules reference
  icons/<slug>.css             icon stylesheets verbatim (uuid urls)     icons/<slug>.local.css  url() → ../fonts/<slug>.woff2 only
  fonts.css                    generated @font-face for the Google-served families, one rule per (weight × subset),
                               src → <fonts-rel>/<file>, unicode-range and font-display preserved
  MANIFEST.json, SHA256SUMS.txt

Keep the pages' `integrity` attributes when repointing to these files: the extracted JS matches them, so SRI
then guards the local copies. Verified as of 2026-09-15 on one export (3/3 JS matched SRI and canonical;
33 font files structurally valid; 4 icon sheets identical to the published package after url() normalisation).
"""
import sys, os, re, json, base64, zlib, hashlib, struct, argparse, urllib.request
from collections import OrderedDict, defaultdict

FMT_EXT = {"woff2": "woff2", "woff": "woff", "truetype": "ttf", "opentype": "otf", "svg": "svg"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def tag(txt, t):
    m = re.search(r'<script type="%s">(.*?)</script>' % re.escape(t), txt, re.S)
    return m.group(1) if m else None


def decode(chunk):
    b = base64.b64decode(chunk["data"])
    if not chunk.get("compressed"):
        return b
    for w in (15, 31, -15):
        try:
            return zlib.decompress(b, w)
        except Exception:
            pass
    raise ValueError("undecodable chunk")


def check_font(data, ext):
    if ext == "woff2":
        return data[:4] == b"wOF2" and struct.unpack(">I", data[8:12])[0] == len(data), "wOF2 magic+length"
    if ext == "woff":
        return data[:4] == b"wOFF" and struct.unpack(">I", data[8:12])[0] == len(data), "wOFF magic+length"
    if ext == "ttf":
        if data[:4] not in (b"\x00\x01\x00\x00", b"true"):
            return False, "TTF magic"
        n = struct.unpack(">H", data[4:6])[0]
        ok = all(struct.unpack(">I", data[12 + 16 * i + 8:12 + 16 * i + 12])[0] + struct.unpack(">I", data[12 + 16 * i + 12:12 + 16 * i + 16])[0] <= len(data) for i in range(n))
        return ok, "TTF %d tables in bounds" % n
    if ext == "svg":
        return b"<font" in data[:50000], "SVG font markup"
    return True, "no structural check"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export"); ap.add_argument("--list", action="store_true"); ap.add_argument("--out")
    ap.add_argument("--sri-from", action="append", default=[]); ap.add_argument("--canonical", action="store_true")
    ap.add_argument("--fonts-rel", default="../assets/fonts")
    a = ap.parse_args()
    txt = open(a.export, "rb").read().decode("utf-8")
    man_raw, tpl_raw = tag(txt, "__bundler/manifest"), tag(txt, "__bundler/template")
    if not man_raw:
        sys.exit("no <script type=\"__bundler/manifest\"> found — not a standalone export?")
    man = json.loads(man_raw)
    html = json.loads(tpl_raw) if tpl_raw else ""
    html = html if isinstance(html, str) else html.get("html", "")
    keys = set(); [keys.update(c.keys()) for c in man.values()]
    print("chunks: %d  keys: %s  per-chunk hash: %s" % (len(man), sorted(keys), "NONE" if not any(re.search(r"hash|sha|digest|integrity", k, re.I) for k in keys) else "present"))
    by_mime = defaultdict(int)
    for c in man.values(): by_mime[c.get("mime", "?")] += 1
    for k, v in sorted(by_mime.items(), key=lambda kv: -kv[1]): print("  %4d  %s" % (v, k))
    if a.list or not a.out:
        return

    out = a.out
    for d in ("js", "fonts", "icons"): os.makedirs(os.path.join(out, d), exist_ok=True)
    records = []

    # ---- fonts: every @font-face in the template
    faces = OrderedDict()   # uuid -> {family, style, formats, rules[(weight, unicode_range, display)]}
    for body in re.findall(r"@font-face\s*\{([^}]*)\}", html):
        fam = re.search(r"font-family:\s*[\"']?([^;\"']+)", body); w = re.search(r"font-weight:\s*([^;]+)", body)
        st = re.search(r"font-style:\s*([^;]+)", body); ur = re.search(r"unicode-range:\s*([^;]+)", body); disp = re.search(r"font-display:\s*([^;]+)", body)
        for u, fmt in re.findall(r"url\([\"']?([0-9a-fA-F-]{36})[\"']?(?:#[^)\"']*)?[\"']?\)\s*(?:format\([\"']?(\w+)[\"']?\))?", body):
            e = faces.setdefault(u, {"family": fam.group(1).strip() if fam else "?", "style": st.group(1).strip() if st else "normal", "formats": set(), "rules": []})
            e["formats"].add(fmt or "?")
            r = (w.group(1).strip() if w else "?", ur.group(1).strip() if ur else "", disp.group(1).strip() if disp else "")
            if r not in e["rules"]: e["rules"].append(r)
    fam_count = defaultdict(int)
    for u in faces:
        if u in man and str(man[u].get("mime", "")).startswith(("font/", "image/svg")): fam_count[faces[u]["family"]] += 1
    idx = defaultdict(int)
    for u, e in faces.items():
        if u not in man: print("  WARN @font-face references chunk %s which is not in the manifest" % u[:8]); continue
        c = man[u]; data = decode(c)
        fmt = next(iter(e["formats"])); ext = FMT_EXT.get(fmt, c.get("mime", "bin").split("/")[-1])
        multi = fam_count[e["family"]] > 1 and ext == "woff2" and "svg" not in e["formats"] and len(e["formats"]) == 1
        if multi:
            idx[e["family"]] += 1; name = "%s-%d.%s" % (slug(e["family"]), idx[e["family"]], ext)
        else:
            name = "%s.%s" % (slug(e["family"]), ext)
        ok, note = check_font(data, ext)
        open(os.path.join(out, "fonts", name), "wb").write(data)
        records.append({"file": "fonts/" + name, "uuid": u, "mime": c.get("mime"), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "family": e["family"], "style": e["style"], "weights": sorted({r[0] for r in e["rules"]}), "unicode_range": next((r[1] for r in e["rules"] if r[1]), ""),
                        "font_display": next((r[2] for r in e["rules"] if r[2]), ""), "check": note, "ok": ok, "kind": "font"})
        print("  font %-34s %9d B  %-22s %s %s" % (name, len(data), e["family"], "OK" if ok else "FAIL", note))

    # ---- icon stylesheets vs Google-served families
    icon_families = set()
    for attrs, body in re.findall(r"<style([^>]*)>(.*?)</style>", html, re.S):
        fam = re.search(r"@font-face\s*\{[^}]*font-family:\s*[\"']?([^;\"']+)", body)
        if fam and len(re.findall(r":before\s*\{\s*content:", body)) > 200:
            family = fam.group(1).strip(); icon_families.add(family); s = slug(family)
            open(os.path.join(out, "icons", s + ".css"), "w", encoding="utf-8").write(body)
            local, n = re.subn(r"src:\s*url\([^;]*?\)\s*format\([^;]*?\)(?:\s*,\s*url\([^;]*?\)\s*format\([^;]*?\))*\s*;",
                               'src: url("../fonts/%s.woff2") format("woff2");' % s, body, count=1)
            open(os.path.join(out, "icons", s + ".local.css"), "w", encoding="utf-8").write(local)
            records.append({"file": "icons/%s.css" % s, "bytes": len(body.encode()), "sha256": hashlib.sha256(body.encode()).hexdigest(), "family": family, "kind": "icon-css",
                            "glyph_rules": len(re.findall(r":before\s*\{\s*content:", body)), "local_rewrite_ok": n == 1 and not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", local)})
            print("  icon css %-30s %9d B  %d glyph rules  local rewrite %s" % (s + ".css", len(body.encode()), records[-1]["glyph_rules"], "OK" if records[-1]["local_rewrite_ok"] else "FAIL"))

    # ---- vendor JS by banner
    want = {}
    for u, c in man.items():
        if "javascript" not in str(c.get("mime", "")): continue
        data = decode(c); head = data[:1500].decode("utf-8", "ignore")
        for pat, name in (("react-dom.development.js", "react-dom.development.js"), ("react-dom.production.min.js", "react-dom.production.min.js"),
                          ("react.development.js", "react.development.js"), ("react.production.min.js", "react.production.min.js")):
            if pat in head and name not in want: want[name] = data; break
        else:
            if len(data) > 1_000_000 and re.search(r"@babel/standalone|Babel", head) and "babel.min.js" not in want:
                want["babel.min.js"] = data
    for name, data in want.items():
        open(os.path.join(out, "js", name), "wb").write(data)
        records.append({"file": "js/" + name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "sha384_b64": base64.b64encode(hashlib.sha384(data).digest()).decode(), "kind": "js"})
        print("  js   %-34s %9d B  sha256 %s…" % (name, len(data), records[-1]["sha256"][:16]))
    if not want: print("  WARN no vendor JS identified by banner")

    # ---- SRI from pages, canonical from network (opt-in)
    sri = {}
    for page in a.sri_from:
        for src, integ in re.findall(r'src="(https?://[^"]+)"\s+integrity="sha384-([^"]+)"', open(page, encoding="utf-8").read()):
            sri[src.split("/")[-1]] = (integ, src)
    for r in records:
        if r["kind"] != "js": continue
        name = r["file"].split("/")[-1]
        if name in sri:
            r["sri_match"] = (sri[name][0] == r["sha384_b64"]); print("  SRI  %-34s %s" % (name, "MATCH" if r["sri_match"] else "MISMATCH"))
            if a.canonical:
                try:
                    b = urllib.request.urlopen(urllib.request.Request(sri[name][1], headers={"User-Agent": "curl/8"}), timeout=30).read()
                    r["canonical_match"] = hashlib.sha256(b).hexdigest() == r["sha256"]; r["canonical_url"] = sri[name][1]
                    print("  canonical %-29s %s" % (name, "MATCH" if r["canonical_match"] else "MISMATCH"))
                except Exception as e:
                    r["canonical_match"] = None; print("  canonical %-29s unavailable: %s" % (name, type(e).__name__))

    # ---- fonts.css for Google-served families
    rules = []
    for r in records:
        if r["kind"] != "font" or r["family"] in icon_families or not r["file"].endswith(".woff2"): continue
        for w in r["weights"]:
            rules.append('@font-face {\n  font-family: "%s";\n  font-style: %s;\n  font-weight: %s;\n  font-display: %s;\n  src: url("%s/%s") format("woff2");%s\n}'
                         % (r["family"], r["style"], w, r["font_display"] or "swap", a.fonts_rel.rstrip("/"), os.path.basename(r["file"]), ("\n  unicode-range: %s;" % r["unicode_range"]) if r["unicode_range"] else ""))
    if rules:
        open(os.path.join(out, "fonts.css"), "w", encoding="utf-8").write("/* Generated from a standalone export's inlined font CSS; replaces the CDN @import. One rule per (weight x subset). */\n\n" + "\n\n".join(rules) + "\n")
        print("  fonts.css: %d @font-face rules" % len(rules))

    json.dump({"source": os.path.abspath(a.export), "source_sha256": hashlib.sha256(txt.encode()).hexdigest(), "records": records}, open(os.path.join(out, "MANIFEST.json"), "w"), indent=1, default=list)
    with open(os.path.join(out, "SHA256SUMS.txt"), "w") as fh:
        for r in records: fh.write("%s  %s\n" % (r["sha256"], r["file"]))
    total = sum(r["bytes"] for r in records)
    print("\n%d files, %d bytes → %s   (structural checks: %s)" % (len(records), total, out, "all OK" if all(r.get("ok", True) for r in records) else "FAILURES"))


if __name__ == "__main__":
    main()
