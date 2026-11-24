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


if __name__ == "__main__":
    main()
    print("ALL PASS")
