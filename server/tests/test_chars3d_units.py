"""3D Studio unit checks — profiles, lip-sync tables, and (when Chromium is around) the rig built by chars3d.js:
bone count, skin weights normalised, 13 morph targets (8 visemes + 5 expressions), every profile builds.
Run: python3 tests/test_chars3d_units.py [--no-browser]"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vividora.engine import chars3d as c3  # noqa: E402
from vividora.engine.chars3d.profiles import PROFILES  # noqa: E402

PASS = 0


def check(cond, label, detail=""):
    global PASS
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {detail}"))
    if cond:
        PASS += 1
    else:
        raise SystemExit(1)


def test_profiles():
    ids = [p["id"] for p in PROFILES]
    check(len(PROFILES) >= 60, f"{len(PROFILES)} profiles (≥ 60)")
    check(len(ids) == len(set(ids)), "profile ids unique")
    cats = {p["category"] for p in PROFILES}
    check(len(cats) >= 7, f"{len(cats)} categories")
    looks = {json.dumps({k: v for k, v in p["spec"].items()}, sort_keys=True) for p in PROFILES}
    check(len(looks) == len(PROFILES), "every profile has a distinct look (not just a name)")
    outfits = {p["spec"]["outfit"] for p in PROFILES}
    check(len(outfits) >= 15, f"{len(outfits)} distinct outfits", str(outfits))
    check(any(p["spec"].get("age") == "child" for p in PROFILES) and any(p["spec"].get("age") == "old" for p in PROFILES), "children and elders present")
    check(sum(1 for p in PROFILES if p["spec"].get("gender") == "f") >= 20, "≥ 20 women")


def test_visemes():
    check(c3.visemes_for_word("नमस्ते") and all(0 <= v < 8 for v in c3.visemes_for_word("नमस्ते")), "Devanagari → visemes")
    check(c3.visemes_for_word("hello") == [1, 2, 7, 7, 3], "Latin → visemes", str(c3.visemes_for_word("hello")))
    ev = c3.viseme_events([{"w": "नमस्ते", "start": 0.0, "end": 0.5}, {"w": "दोस्तों", "start": 0.6, "end": 1.0}])
    check(ev and ev[0][0] == 0.0 and ev[-1][0] <= 1.0 and all(len(e) == 3 for e in ev), f"{len(ev)} viseme events in time order")
    check(all(ev[i][0] <= ev[i + 1][0] for i in range(len(ev) - 1)), "events sorted")
    env = [0.1] * 25 + [1.0] * 25
    ev2 = c3.viseme_events([{"w": "आ", "start": 0.0, "end": 1.0}], env)
    check(ev2[0][2] < ev2[-1][2], "jaw follows the audio envelope")


def test_rig_in_browser():
    if "--no-browser" in sys.argv:
        print("SKIP rig (no browser)")
        return
    from playwright.sync_api import sync_playwright
    page = (ROOT.parent / "web" / "dist" / "assets" / "3d.html").resolve()
    check(page.exists(), "render page exists")
    js = """
    async (profiles) => {
      const m = await import('./chars3d.js');
      const out = { bones: 0, weightsOk: true, morphs: 0, anims: 0, built: 0, scenes: 0, errors: [] };
      const rig = m.buildCharacter(profiles[0].spec);
      out.bones = rig.skeleton.bones.length;
      const sw = rig.body.geometry.getAttribute('skinWeight');
      for (let i = 0; i < sw.count; i += 97) { const s = sw.getX(i) + sw.getY(i) + sw.getZ(i) + sw.getW(i); if (Math.abs(s - 1) > 1e-4) { out.weightsOk = false; break; } }
      out.morphs = rig.head.morphTargetInfluences.length; out.morphNames = Object.keys(rig.head.morphTargetDictionary);
      for (const a of m.ANIMATIONS) { const c = m.makeClip(a, rig); if (c.tracks.length > 10 && c.duration > 0) out.anims++; }
      for (const p of profiles) { try { m.buildCharacter(p.spec); out.built++; } catch (e) { out.errors.push(p.id + ': ' + e.message); } }
      for (const s of m.SCENES) { const sc = m.buildScene(s, 'day'); if (sc.userData.slots.length >= 3) out.scenes++; }
      rig.setViseme([0, 1, 0, 0, 0, 0, 0, 0]); out.aaOpen = rig.head.morphTargetInfluences[rig.head.morphTargetDictionary.aa];
      return out;
    }"""
    with sync_playwright() as p:
        b = c3._browser(p)
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        # serve the dist folder from the dev server if running, else from the file system through a tiny route
        url = os.getenv("CHARS3D_PAGE_URL") or "http://127.0.0.1:8116/assets/3d.html"
        try:
            pg.goto(url, timeout=15000)
        except Exception:  # noqa: BLE001
            pg.route("**/*", lambda route: route.fulfill(path=str(page.parent / route.request.url.split("/assets/")[-1])) if "/assets/" in route.request.url else route.continue_())
            pg.goto("http://localhost/assets/3d.html")
        pg.wait_for_function("window.__ready", timeout=30000)
        out = pg.evaluate(js, PROFILES)
        b.close()
    check(not errs, "no page errors", "; ".join(errs)[:300])
    check(out["bones"] == 19, f"skeleton has 19 bones", str(out["bones"]))
    check(out["weightsOk"], "skin weights sum to 1")
    check(out["morphs"] == 13 and "aa" in out["morphNames"] and "smile" in out["morphNames"], "13 morph targets (8 visemes + 5 expressions)", str(out["morphNames"]))
    check(out["anims"] == len(c3.ANIMATIONS), f"{out['anims']} animation clips build")
    check(out["built"] == len(PROFILES) and not out["errors"], f"all {out['built']} profiles build", "; ".join(out["errors"])[:300])
    check(out["scenes"] == len(c3.SCENES), f"{out['scenes']} scenes with ≥ 3 character slots")
    check(out["aaOpen"] == 1, "viseme drives the head morph")


if __name__ == "__main__":
    test_profiles()
    test_visemes()
    test_rig_in_browser()
    print(f"OK — {PASS} checks")
