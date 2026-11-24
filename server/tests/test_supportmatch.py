"""Supporting clips find their place in a talk: by a written time, by the words (Hindi spoken, Latin file names), by the
LLM when there is one, and the rest spread in name order — never two on one spot, never inside a removed part.

    python3 tests/test_supportmatch.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import supportmatch as sm  # noqa: E402

LINES = ["नमस्ते दोस्तों आज के podcast में आपका स्वागत है",
         "पिछले महीने मैं आगरा गया था और ताज महल देखा",
         "वहाँ की भीड़ देखकर मैं हैरान रह गया",
         "फिर हमने दिल्ली में लाल किला भी घूमा",
         "खाने में सबसे अच्छी चीज़ थी पराठे वाली गली के पराठे",
         "अब बात करते हैं investment की, mutual fund में पैसा कैसे लगाएँ",
         "मैंने अपना पहला laptop दो हज़ार पंद्रह में खरीदा था",
         "और आख़िर में channel को subscribe करना मत भूलना"]
SEGS = [{"start": i * 10.0 + 1, "end": i * 10.0 + 8, "text": t} for i, t in enumerate(LINES)]


def by_id(res):
    return {r["id"]: r for r in res}


def main() -> None:
    assert sm.translit("ताज") == "taj" and sm.translit("महल") == "mahal" and sm.translit("दिल्ली") == "dilli" and sm.translit("किला") == "kila"
    assert sm.tokens("IMG_2041_taj-mahal.JPG") == ["taj", "mahal"] and sm.tokens("VID20261101.mp4") == []
    assert sm.explicit_time("यह 1:23 पर") == 83 and sm.explicit_time("at 2m10s") == 130 and sm.explicit_time("laptop 2015") is None
    print("PASS helpers: Devanagari ↔ Latin, file-name words, written times")

    clips = [{"id": "taj", "name": "taj mahal.jpg", "kind": "image"},
             {"id": "fort", "name": "Lal_Qila_Delhi.mp4", "kind": "video", "duration": 20},
             {"id": "food", "name": "IMG_5521.jpg", "kind": "image", "note": "पराठे"},
             {"id": "mf", "name": "mutual-fund-chart.png", "kind": "image"},
             {"id": "fixed", "name": "b-roll.mp4", "kind": "video", "duration": 3, "note": "इसे 1:05 पर लगाओ"},
             {"id": "x1", "name": "extra 1.jpg", "kind": "image"},
             {"id": "x2", "name": "extra 2.jpg", "kind": "image"}]
    r = by_id(sm.match(SEGS, clips, duration=80.0))
    assert r["taj"]["how"] == "words" and r["taj"]["i"] == 1 and r["taj"]["start"] == 11.0 and r["taj"]["end"] == 15.0, r["taj"]
    assert r["fort"]["i"] == 3 and r["fort"]["end"] - r["fort"]["start"] == 6.0, r["fort"]                # a long clip is shown for 6 s
    assert r["food"]["i"] == 4 and r["food"]["how"] == "words", r["food"]                                  # from the note, not the camera's file name
    assert r["mf"]["i"] == 5, r["mf"]
    assert r["fixed"]["how"] == "time" and r["fixed"]["start"] == 65.0 and r["fixed"]["end"] == 68.0, r["fixed"]
    assert r["x1"]["how"] == r["x2"]["how"] == "order" and r["x1"]["start"] < r["x2"]["start"], (r["x1"], r["x2"])
    starts = sorted(v["start"] for v in r.values())
    assert all(b - a >= 2.5 for a, b in zip(starts, starts[1:])), starts
    print("PASS words: Hindi speech ↔ Latin names, note beats a camera file name, written time, the rest in name order")

    # without "spread" the unknown ones stay unplaced; nothing lands in a removed part
    r = by_id(sm.match(SEGS, clips, duration=80.0, spread=False, cuts=[{"start": 10, "end": 20, "enabled": True}]))
    assert r["x1"]["start"] is None and r["x1"]["how"] == "none" and r["taj"]["start"] is None, (r["x1"], r["taj"])
    assert r["fort"]["i"] == 3
    print("PASS no spread → unplaced; a line inside a cut is never used")

    # the LLM decides where it can; a wrong / broken answer falls back to the words
    def ask(prompt, system=""):
        assert "SPOKEN LINES" in prompt and "taj mahal" in prompt
        return [{"clip": "A", "line": 2}, {"clip": "ZZ", "line": 1}, {"clip": "B", "line": 99}]
    r = by_id(sm.match(SEGS, clips[:2], duration=80.0, ask=ask))
    assert r["taj"]["how"] == "ai" and r["taj"]["i"] == 2 and r["fort"]["how"] == "words" and r["fort"]["i"] == 3, r

    def boom(prompt, system=""):
        raise RuntimeError("no network")
    r = by_id(sm.match(SEGS, clips[:2], duration=80.0, ask=boom))
    assert r["taj"]["how"] == "words" and r["taj"]["i"] == 1
    print("PASS LLM used when it answers, ignored when it is wrong or down")

    # two clips about the same line do not sit on top of each other; a visual stops before the next one
    two = [{"id": "a", "name": "taj mahal front.jpg", "kind": "image"}, {"id": "b", "name": "taj mahal side.jpg", "kind": "image"}]
    r = by_id(sm.match(SEGS, two, duration=80.0))
    assert r["a"]["how"] == r["b"]["how"] == "words" and r["a"]["i"] == r["b"]["i"] == 1, r                # both in the Taj line …
    first, second = sorted((r["a"], r["b"]), key=lambda x: x["start"])
    assert first["start"] == 11.0 and second["start"] == 13.5 and first["end"] <= second["start"] - 0.15 + 1e-6, (first, second)   # … one after the other
    assert sm.match([], two) and all(x["start"] is None for x in sm.match([], two))
    print("PASS no two clips on one spot, no overlap, empty transcript is safe")


def test_look_inside() -> None:
    """A clip with a camera file name is placed by what it SHOWS (vision model stand-in): frames are made, described in
    English + Hindi, and the Hindi words match the spoken line."""
    import subprocess
    import tempfile
    t = Path(tempfile.mkdtemp(prefix="vividora-see-"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:d=6:r=10", "-pix_fmt", "yuv420p", str(t / "v.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=orange:s=2000x1000", "-frames:v", "1", str(t / "p.jpg")], check=True)
    fv, fp = sm.frames_of(t / "v.mp4", "video", 6.0), sm.frames_of(t / "p.jpg", "image")
    assert len(fv) == 2 and len(fp) == 1 and all(x[:2] == b"\xff\xd8" for x in fv + fp) and len(fp[0]) < 60_000

    asked = []

    def see(prompt, images, system=""):
        asked.append((prompt, len(images)))
        assert "Clip 1: pictures 1, 2" in prompt and "Clip 2: picture 3" in prompt and len(images) == 3
        return [{"clip": 1, "en": "laptop on a desk, hands typing", "hi": "मेज़ पर laptop, टाइप करते हाथ"}, {"clip": 2, "en": "Taj Mahal at sunrise", "hi": "सुबह का ताज महल"},
                {"clip": 9, "en": "ignored"}, "junk"]
    seen = sm.describe([{"id": "a", "frames": fv}, {"id": "b", "frames": fp}, {"id": "c", "frames": []}], see)
    assert set(seen) == {"a", "b"} and "ताज महल" in seen["b"] and seen["a"].startswith("laptop on a desk") and len(asked) == 1
    clips = [{"id": "a", "name": "VID_20261101.mp4", "kind": "video", "duration": 6, "seen": seen["a"]},
             {"id": "b", "name": "IMG_5521.jpg", "kind": "image", "seen": seen["b"]}]
    r = by_id(sm.match(SEGS, clips, duration=80.0, spread=False))
    assert r["b"]["how"] == "words" and r["b"]["i"] == 1 and r["a"]["i"] == 6, r               # Taj line, laptop line — from the pictures alone
    assert sm.describe([{"id": "a", "frames": fv}], lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))) == {}
    print("PASS looking inside: frames → descriptions (en + hi) → the right line, without any file name or note")


def test_vision_call() -> None:
    """llm.ask_json_images: the request carries the pictures for Gemini and for Anthropic, the answer is parsed and cached."""
    import base64
    import os
    import tempfile
    os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="vividora-llmc-")
    from vividora.engine import llm
    for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_URL", "LLM_PROVIDER"):
        os.environ.pop(k, None)
    assert llm.ask_json_images("x", [b"abc"]) is None                                   # no key → no call
    os.environ["GEMINI_API_KEY"] = "g-key"
    os.environ["GEMINI_MODEL"] = "gemini-test"
    calls = []

    def http(url, body, headers):
        calls.append((url, body, headers))
        if "googleapis" in url:
            assert "gemini-test:generateContent?key=g-key" in url
            parts = body["contents"][0]["parts"]
            assert parts[0]["text"] == "what?" and base64.b64decode(parts[1]["inline_data"]["data"]) == b"JPEG1" and parts[2]["inline_data"]["mime_type"] == "image/jpeg"
            return {"candidates": [{"content": {"parts": [{"text": '[{"clip": 1, "en": "a cat"}]'}]}}]}
        assert headers["x-api-key"] == "a-key" and body["messages"][0]["content"][0]["source"]["data"] == base64.b64encode(b"JPEG1").decode()
        assert body["messages"][0]["content"][-1] == {"type": "text", "text": "what?"}
        return {"content": [{"type": "text", "text": '{"items": [{"clip": 1, "en": "a dog"}]}'}]}
    assert llm.ask_json_images("what?", [b"JPEG1", b"JPEG2"], http=http) == [{"clip": 1, "en": "a cat"}] and len(calls) == 1
    assert llm.ask_json_images("what?", [b"JPEG1", b"JPEG2"], http=http) == [{"clip": 1, "en": "a cat"}] and len(calls) == 1      # cached
    assert llm.ask_json_images("what?", [b"JPEG1", b"OTHER"], http=lambda *a: (_ for _ in ()).throw(TimeoutError("slow"))) is None  # failure → None
    os.environ.pop("GEMINI_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "a-key"
    assert llm.ask_json_images("what?", [b"JPEG1"], http=http) == {"items": [{"clip": 1, "en": "a dog"}]}
    os.environ.pop("ANTHROPIC_API_KEY")
    print("PASS vision call: Gemini + Anthropic request shapes, cache, failure is None")


def test_clip_look() -> None:
    """CLIP on this server (engine/clipsee.py): ranking rules with made-up vectors, and its place in the matching order."""
    import os

    import numpy as np

    from vividora.engine import clipsee
    os.environ.pop("CLIP_MATCH", None)
    assert not clipsee.wanted()
    os.environ["CLIP_MATCH"] = "on"
    assert clipsee.wanted()
    os.environ.pop("CLIP_MATCH")
    rng = np.random.default_rng(0)
    lines = rng.normal(size=(8, 32)).astype(np.float32)
    lines /= np.linalg.norm(lines, axis=1, keepdims=True)
    hill = lines[5] * 0.9 + rng.normal(size=32).astype(np.float32) * 0.05          # a picture that is line 5
    hill /= np.linalg.norm(hill)
    vague = lines.mean(axis=0)                                                    # looks a little like every line
    vague /= np.linalg.norm(vague)
    got = clipsee.rank({"hill": hill, "vague": vague}, lines, min_sim=0.18)
    assert got["hill"][0][0] == 5 and got["hill"][0][1] > 0.8, got
    assert "vague" not in got, got                                                # nothing stands out → no placement
    v2 = clipsee.unpack(clipsee.pack(hill))
    assert abs(float(v2 @ hill) - 1) < 1e-3                                       # stored in the Library item and read back
    segs = [{"start": i * 5.0, "end": i * 5.0 + 4.5, "text": t} for i, t in enumerate(
        ["नमस्ते दोस्तों", "आज मौसम अच्छा है", "मैं सुबह जल्दी उठा", "फिर चाय पी", "रास्ता लंबा था", "ऊपर से नज़ारा कमाल था", "थोड़ा आराम किया", "फिर लौट आए"])]
    clips = [{"id": "hill", "name": "IMG_0001.jpg", "kind": "image"}, {"id": "tea", "name": "चाय.jpg", "kind": "image"},
             {"id": "x", "name": "IMG_0002.jpg", "kind": "image"}]
    res = {r["id"]: r for r in sm.match(segs, clips, look={"hill": [(5, 0.31)], "tea": [(0, 0.3)]}, spread=False)}
    assert res["hill"]["how"] == "look" and res["hill"]["i"] == 5 and res["hill"]["start"] == 25.0, res["hill"]
    assert res["tea"]["how"] == "words" and res["tea"]["i"] == 3, res["tea"]         # spoken words win over the look
    assert res["x"]["start"] is None
    print("PASS CLIP look: a clear match is placed, a vague picture is not, words come first, vectors survive storage")


if __name__ == "__main__":
    test_vision_call()
    test_look_inside()
    test_clip_look()
    main()
    print("ALL PASS")
