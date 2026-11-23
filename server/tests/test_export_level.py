"""Export box: the simple Quality level (high / standard / small) is an offset on the platform's / codec's own CRF.
    cd server && python3 tests/test_export_level.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vividora.engine import encode  # noqa: E402
from vividora.engine.presets import platform  # noqa: E402

pre = platform("yt-long")
meta = {"width": 1920, "height": 1080, "fps": 30}
base = encode.plan({}, pre, meta, 30)["crf"]
assert encode.plan({"level": "standard"}, pre, meta, 30)["crf"] == base
hi, lo = encode.plan({"level": "high"}, pre, meta, 30), encode.plan({"level": "small"}, pre, meta, 30)
assert hi["crf"] == base - 3 and lo["crf"] == base + 6, (base, hi["crf"], lo["crf"])
assert "-crf" in hi["vargs"] and str(hi["crf"]) in hi["vargs"]
assert encode.plan({"level": "junk"}, pre, meta, 30)["crf"] == base
assert encode.plan({"level": "high", "crf": 30}, pre, meta, 30)["crf"] == 30              # an exact CRF from Advanced wins
if "h265" in encode.available()["codecs"]:
    assert encode.plan({"level": "high", "codec": "h265"}, pre, meta, 30)["crf"] == encode.CODECS["h265"]["crf"] - 3   # relative per codec
b = [encode.estimate_bytes({"level": lv}, pre, meta, 60) for lv in ("small", "standard", "high")]
assert b[0] < b[1] < b[2], b                                                                # the size estimate follows
r1080, r720 = encode.plan({"resolution": "1080p"}, pre, meta, 30), encode.plan({"resolution": "720p"}, pre, meta, 30)
assert min(r1080["width"], r1080["height"]) == 1080 and min(r720["width"], r720["height"]) == 720
print("OK")
