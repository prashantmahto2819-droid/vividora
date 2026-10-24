"""Character Studio units: rig validation, profile variety, visemes, pose clips, scene placement,
storyboard normalisation, and one real SVG→PNG/webm render. Run: python3 tests/test_chars_units.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATA_ROOT", tempfile.mkdtemp(prefix="vchars_"))

from vividora.engine.chars import anim, catalog, lipsync, render, rig, scenes2d, storyboard  # noqa: E402

fails = 0


def check(cond, label, val=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  → {str(val)[:300]}"))
    fails += 0 if cond else 1


# --- library: 200 distinct profiles, every category represented, every profession used
lib = catalog.library()
check(len(lib) == 200, "200 profiles", len(lib))
keys = {tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in p["params"].items() if k not in ("name", "profession"))) for p in lib}
check(len(keys) == 200, "no two profiles share a visual tuple", len(keys))
check({p["category"] for p in lib} == set(catalog.CATEGORIES), "every category used", {p["category"] for p in lib} ^ set(catalog.CATEGORIES))
check(len({p["profession"] for p in lib}) == len(catalog.PROFESSIONS), "every profession used")
check(len({p["params"]["outfit"] for p in lib}) >= 20, "≥20 outfits in use", len({p["params"]["outfit"] for p in lib}))
check(len({p["params"]["skin"] for p in lib}) == 8, "all 8 skin tones used")
check(all(len(p["id"]) == 4 and p["label"] for p in lib), "ids + labels")
for p in lib:
    rig.validate(p["params"])  # raises on a bad combination
check(True, "all profiles validate")

# --- validation rejects junk
for bad, key in (({"hair": "mohawk"}, "hair"), ({"outfit": "spacesuit"}, "outfit"), ({"skin": "brown"}, "skin"), ({"accessories": ["crown"]}, "accessory")):
    try:
        rig.validate({**lib[0]["params"], **bad})
        check(False, f"rejects bad {key}")
    except ValueError as e:
        check(key in str(e) or "रंग" in str(e), f"rejects bad {key}", e)

# --- svg: every outfit / hair / hat / prop / viseme / expression draws
for o in catalog.OUTFITS:
    s = rig.svg({**lib[0]["params"], "outfit": o})
    check(s.startswith("<svg") and s.endswith("</svg>") and s.count("<g") == s.count("</g>"), f"outfit {o} draws balanced svg")
for h in catalog.HAIR:
    rig.svg({**lib[0]["params"], "hair": h})
for h in catalog.HATS:
    rig.svg({**lib[0]["params"], "hat": h})
for pr in catalog.PROPS:
    rig.svg({**lib[0]["params"], "prop": pr})
for v in catalog.VISEMES:
    s = rig.svg(lib[0]["params"], {"viseme": v, "mouth_open": .8})
    check("<svg" in s, f"viseme {v}")
for e in catalog.EXPRESSIONS:
    rig.svg(lib[0]["params"], {"expr": e})
check(len({rig.svg(lib[0]["params"], {"viseme": v, "mouth_open": .8}) for v in catalog.VISEMES}) == len(catalog.VISEMES), "8 visemes give 8 different mouths")
check(rig.svg(lib[0]["params"], {"flip": 1}) != rig.svg(lib[0]["params"]), "flip mirrors")

# --- visemes
check(lipsync.visemes_of("मम्मी") [0] == "MBP", "म → MBP", lipsync.visemes_of("मम्मी"))
check("OO" in lipsync.visemes_of("ऊपर") and "EE" in lipsync.visemes_of("ईद") and "AA" in lipsync.visemes_of("आम"), "Devanagari vowels")
check(lipsync.visemes_of("family") [0] == "FV" and "L" in lipsync.visemes_of("family"), "Latin f/l", lipsync.visemes_of("family"))
check(lipsync.visemes_of("!!") == ["DD"], "punctuation falls back")
sched = lipsync.schedule([{"w": "नमस्ते", "start": 0.0, "end": 0.5}, {"w": "दोस्तों", "start": 0.8, "end": 1.3}])
check(lipsync.viseme_at(sched, 0.1) != "rest" and lipsync.viseme_at(sched, 0.65) == "rest" and lipsync.viseme_at(sched, 2.0) == "rest", "schedule: speech vs gaps")
check(lipsync.mouth_at(sched, None, 0.65) == ("rest", 0.0), "rest = closed mouth")

# --- pose clips
for cid in anim.CLIPS:
    p0 = anim.pose_at(cid, 0.0)
    p1 = anim.pose_at(cid, anim.CLIPS[cid]["len"] * 0.27)
    check(isinstance(p0, dict) and all(isinstance(v, (int, float, str)) for v in p0.values()), f"clip {cid} samples")
    if cid != "sit" and cid != "drive":
        check(p0 != p1, f"clip {cid} moves", (p0, p1))
check(anim.sample([[0, 0], [1, 10]], 0.5, 1.0, True) == 5.0, "smoothstep midpoint")
check(anim.sample([[0, 0], [1, 10]], 1.5, 1.0, True) == 5.0, "loops")
b = [anim.blink_at(t, 3) for t in [i * 0.02 for i in range(500)]]
check(min(b) < 0.2 and max(b) == 1.0, "blink closes the eyes sometimes")

# --- scenes
check(len(scenes2d.ENVS) >= 15, "≥15 environments", len(scenes2d.ENVS))
for env in scenes2d.ENVS:
    s = scenes2d.scene_svg({"env": env, "chars": [{"params": lib[3]["params"], "x": .5, "y": .99, "s": 1}]}, 960, 540)
    check(s.startswith("<svg") and 'data-char="0"' in s, f"env {env} renders with a character")
for pid in scenes2d.PROPS:
    check(scenes2d.prop_svg(pid), f"prop {pid}")
for fr in scenes2d.FRAMING:
    for size in ((1920, 1080), (1080, 1920)):
        pl = scenes2d.char_place({"x": .5, "y": .99, "s": 1}, *size, {"framing": fr})
        check(0 <= pl["x"] <= 1 and 0 < pl["scale"] < 1 and 0 < pl["y"] < 1.5, f"placement {fr} {size}", pl)
wide = scenes2d.scene_svg({"env": "office", "framing": "wide"}, 1080, 1920)
check('viewBox="' in wide and "preserveAspectRatio" in wide, "9:16 framing")

# --- storyboard normalisation
spec = storyboard.normalise({"title": "t", "preset": "ig-reel", "scenes": [{"env": "gym", "chars": [{"profile": "c001"}, {"profile": "c002"}],
                                                                         "lines": [{"char": 1, "text": "hi", "expr": "happy"}, {"char": 0, "text": " "}]}]})
check(spec["scenes"][0]["chars"][0]["params"]["age"] in catalog.AGES and len(spec["scenes"][0]["lines"]) == 1, "normalise fills params, drops empty lines")
check(spec["scenes"][0]["chars"][1]["flip"] is True and spec["scenes"][0]["chars"][0]["x"] == scenes2d.ENVS["gym"]["slots"][0][0], "slots + flip defaults")
for bad in ({"scenes": []}, {"scenes": [{"env": "moon"}]}, {"scenes": [{"env": "gym", "chars": [{"profile": "zzz"}]}]}, {"preset": "tv", "scenes": [{"env": "gym"}]}):
    try:
        storyboard.normalise(bad)
        check(False, f"rejects {bad}")
    except ValueError:
        check(True, f"rejects bad storyboard {list(bad)[0]}")
v = storyboard.suggest_voice({"gender": "f", "age": "child"})
check(v["id"].startswith("hi_") and v["gender"] == "f" and v["speed"] > 1, "voice suggestion child/f", v)

# --- real rasterisation (ffmpeg librsvg): png with transparency + a short alpha webm
png = render.preview_png(lib[7]["params"], {"expr": "happy"}, 120, 240)
check(png.exists() and png.stat().st_size > 1000, "preview png")
try:
    from PIL import Image
    im = Image.open(png)
    check(im.mode == "RGBA" and im.getpixel((2, 2))[3] == 0 and im.getpixel((60, 110))[3] == 255, "png transparent outside, opaque on the body", (im.mode, im.getpixel((2, 2)), im.getpixel((60, 110))))
except ImportError:
    pass
webm = render.clip_webm(lib[7]["params"], {"dur": 1.0, "base": "idle", "gesture": "talk", "seed": 1,
                                             "lip": {"words": [{"w": "नमस्ते दोस्तों", "start": 0.1, "end": 0.9}], "wav": None, "wav_sig": "x"}}, 240, 480)
check(webm.exists() and webm.stat().st_size > 2000, "alpha webm")
import subprocess
pf = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_name,nb_read_frames:stream_tags=alpha_mode", "-count_frames", "-of", "csv=p=0", str(webm)], capture_output=True, text=True).stdout
check("vp9" in pf and ",25,1" in pf.replace("\n", ""), "25 frames, alpha_mode=1", pf)
check(render.clip_webm(lib[7]["params"], {"dur": 1.0, "base": "idle", "gesture": "talk", "seed": 1,
                                            "lip": {"words": [{"w": "नमस्ते दोस्तों", "start": 0.1, "end": 0.9}], "wav": None, "wav_sig": "x"}}, 240, 480) == webm, "cache hit")

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
