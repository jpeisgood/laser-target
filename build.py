#!/usr/bin/env python3
"""Build the deployable page.

src/app.html is written as page *content* (no <html>/<head>/<body>) so the same file can be
published as a claude.ai artifact. This script wraps it into docs/index.html, a normal standalone
page that can be hosted anywhere over https (GitHub Pages, school server, ...), and copies the
printable target PDFs next to it.
"""
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src" / "app.html"
DIST = ROOT / "docs"  # GitHub Pages serves this folder (Settings > Pages > main /docs)


def build() -> pathlib.Path:
    src = SRC.read_text(encoding="utf-8")
    # version = fingerprint of the sources; the app compares it with docs/version.json to pick up new builds
    version = hashlib.sha1((src + (ROOT / "src" / "target.html").read_text(encoding="utf-8")).encode()).hexdigest()[:10]
    cut = src.index('<div id="app"')
    head, body = src[:cut].strip(), src[cut:].strip()
    doc = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1412">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}</style>
<script>window.LT_STANDALONE = true; window.LT_VERSION = "{version}";</script>
{head}
</head>
<body>
{body}
</body>
</html>
"""
    DIST.mkdir(exist_ok=True)
    out = DIST / "index.html"
    out.write_text(doc, encoding="utf-8")
    for pdf in (ROOT / "target").glob("*.pdf"):
        shutil.copy2(pdf, DIST / pdf.name)
    shutil.copy2(ROOT / "src" / "target.html", DIST / "target.html")  # 과녁 만들기 (size editor + print)
    (DIST / "version.json").write_text(json.dumps({"v": version}) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print("built", build())
