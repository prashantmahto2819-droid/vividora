"""Template studio unit checks — formats, adaptation, placeholder fill, variations. Run: python3 tests/test_template_units.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import thumbnail as T  # noqa: E402
from vividora.engine import templates as TP  # noqa: E402


def test_formats_render_without_video():
    for fmt in ["yt", "vertical", "square", "portrait", "fb", "custom"]:
        s = {"template": "face_right", "size": fmt, "custom_size": [800, 1000], "text": "बड़ी *खबर* आज",
             "stickers": [{"uid": "a", "shape": "rrect", "x": .5, "y": .8, "w": .5, "stroke": "#fff", "stroke_w": .02, "shadow": 1, "fill": 1},
                          {"uid": "b", "shape": "disc", "x": .2, "y": .2, "w": .1, "color": "#E50914"},
                          {"uid": "c", "shape": "line", "x": .5, "y": .6, "w": .6}],
             "layout": {fmt: {"text": {"op": .8}, "s:a": {"locked": True}}}}
        img, info = T.render(None, s, layers=True)
        assert img.size == T.size_px(s), (fmt, img.size)
        assert info["size"] == fmt
        ids = {l["id"]: l for l in info["_layers"]["layers"]}
        assert "s:a" in ids and ids["s:a"]["locked"], "lock from layout"
        assert ids["text"].get("op") == .8, "opacity from layout"
        assert ids["s:a"]["img"].width > ids["s:b"]["img"].width


def test_adapt_keeps_anchor_and_margins():
    s = {"template": "face_right", "size": "yt", "text": "hi", "stickers": [{"uid": "a", "shape": "disc", "x": .98, "y": .02, "w": .2}],
         "layout": {"yt": {"text": {"x": .3, "y": .5, "s": 1.2}, "s:a": {"x": 1.4, "y": .5}}}}
    out = TP.adapt(s, "square")
    assert out["size"] == "square"
    lay = out["layout"]["square"]
    assert abs(lay["text"]["x"] - .3) < 1e-6 and 0.6 < lay["text"]["s"] <= 1.2  # anchor carried, size toned down
    assert lay["s:a"]["x"] <= 1 - TP.SAFE and out["stickers"][0]["x"] <= 1 - TP.SAFE  # pulled into the safe area
    assert out["stickers"][0]["y"] >= TP.SAFE
    assert out["custom_size"] == list(T.FORMATS["square"][:2])
    # a second switch back keeps the original yt placement untouched
    back = TP.adapt(out, "yt")
    assert back["layout"]["yt"]["text"]["x"] == .3


def test_fill_and_variations():
    tpl = TP.builtin("clinic_offer")
    assert tpl and tpl["industry"] == "healthcare"
    filled = TP.fill(tpl, {"business": "शर्मा क्लिनिक", "offer": "पहली जाँच मुफ़्त", "phone": "98765 43210"})
    txt = TP.all_text(filled)
    assert "शर्मा क्लिनिक" in txt and "पहली जाँच मुफ़्त" in txt and "98765 43210" in txt
    assert "{{" not in txt, "no placeholder left behind"
    vs = TP.variations(filled, 3)
    assert len(vs) == 3 and len({v["accent"] for v in vs}) == 3
    img, _ = T.render(None, filled)
    assert img.size == T.size_px(filled)


def test_bulk_rows():
    tpl = TP.builtin("grocery_sale")
    rows = TP.parse_csv("business,offer,phone\nराम किराना,20% छूट,9000000001\nश्याम स्टोर,BOGO,9000000002\n")
    assert len(rows) == 2 and rows[1]["business"] == "श्याम स्टोर"
    assert len(TP.BUILTIN) >= 24 and len({t["industry"] for t in TP.BUILTIN}) >= 10


def test_trend_analyse_and_original():
    from PIL import Image, ImageDraw
    from vividora.engine import trendtpl as TT
    im = Image.new("RGB", (640, 360), (20, 30, 60))
    d = ImageDraw.Draw(im)
    for i in range(14):  # busy "text" block on the left
        d.rectangle((20, 30 + i * 20, 300, 38 + i * 20), fill=(255, 220, 0))
    st = TT.analyse(im)
    assert st["text_side"] == "left" and st["text_area"] > 0 and len(st["colors"]) >= 2
    h1 = TT.layout_hash(st)
    assert h1 == TT.layout_hash(dict(st)) and len(h1) == 12
    t = TT.original_template({"id": "x", "channel": "demo", "stats": st})
    assert t["settings"]["template"] in ("headline", "spotlight", "face_right", "face_left") and t["format"] == "yt"
    img, _ = T.render(None, t["settings"])
    assert img.size == (1280, 720)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("OK")
