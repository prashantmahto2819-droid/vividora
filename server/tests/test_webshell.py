"""The web shell can never show an old stylesheet or script after an update: one version number in sw.js and index.html,
the service worker asks for code with that number and past the HTTP cache, the server tells browsers and CDNs not to keep
code. Also guards the phone layout rule that once left a blank sidebar column. Run: python3 tests/test_webshell.py"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = tempfile.mkdtemp(prefix="vividora-shell-")
os.environ.update({"DATA_ROOT": TMP, "DATABASE_PATH": str(Path(TMP) / "t.db"), "MEDIA_ROOT": str(Path(TMP) / "m"), "ADMIN_PASSWORD": "test-pass-123",
                   "SECRET_KEY": "unit-test-secret-key-that-is-long-enough-0123456789", "WEB_DIST": str(ROOT / "web" / "dist"),
                   "WORKER_TOKEN": "unit-test-worker-token-0123456789-abcdefghij"})
sys.path.insert(0, str(ROOT / "server"))


def main():
    sw = (ROOT / "web/dist/sw.js").read_text(encoding="utf-8")
    html = (ROOT / "web/dist/index.html").read_text(encoding="utf-8")
    v = int(re.search(r"const VERSION = (\d+);", sw).group(1))
    refs = re.findall(r'(?:href|src)="/assets/([\w.]+\.(?:css|js))(?:\?v=(\d+))?"', html)
    assert len(refs) >= 4, refs
    assert all(n == str(v) for _, n in refs), f"index.html must carry ?v={v} on every stylesheet / script: {refs}"
    assert 'searchParams.set("v", VERSION)' in sw and 'cache: "no-store"' in sw
    for name in re.findall(r'"/assets/([\w.]+\.js)"', sw):
        assert (ROOT / "web/dist/assets" / name).exists(), name
    # phone layout: the tablet rule must not reach phones (it kept a 200px sidebar column next to a hidden menu)
    css = (ROOT / "web/dist/assets/app.css").read_text(encoding="utf-8")
    for m in re.finditer(r"@media\s*\(([^{]+)\)\s*\{\s*\.app2\s*\{\s*grid-template-columns:\s*(\d+)px", css):
        assert "min-width" in m.group(1), "a fixed sidebar column needs a min-width media query: " + m.group(0)[:90]
    assert re.search(r"@media \(max-width: 900px\) \{\s*\.app2 \{ grid-template-columns: minmax\(0, 1fr\)", css)
    from starlette.testclient import TestClient

    from vividora.app import create_app
    with TestClient(create_app()) as c:
        for path in ("/assets/app.css", "/assets/app.js?v=1", "/"):
            r = c.get(path)
            assert r.status_code == 200 and r.headers["cache-control"] == "no-cache" and r.headers.get("cdn-cache-control") == "no-store", (path, dict(r.headers))
        f = c.get("/assets/fonts/Mukta-Regular.woff")
        assert "immutable" in f.headers["cache-control"] and "cdn-cache-control" not in f.headers
    print(f"web shell: version {v} in sw.js and index.html, code is never kept by browser or CDN, phone layout rule guarded ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
