"""SRT / VTT → transcript (engine/srtimport.py). Run: python3 tests/test_srtimport.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vividora.engine import captions, srtimport  # noqa: E402
from vividora.engine.autocut import words_of  # noqa: E402

SRT = """﻿1
00:00:01,000 --> 00:00:03,000
नमस्ते दोस्तों
<i>आज की बात</i>

2
00:00:02,800 --> 00:00:05,500
{\\an8}यह दूसरी line है

3
00:00:07,000 --> 00:00:07,000
खाली समय

4
00:01:10,250 --> 00:01:12,000
2024
"""
VTT = """WEBVTT

NOTE made elsewhere

00:01.000 --> 00:02.500 align:start
Hello <c.yellow>world</c>

cue-2
00:03.000 --> 00:04.000
second line
"""


def main():
    tr = srtimport.parse(SRT)
    sg = tr["segments"]
    assert [s["text"] for s in sg] == ["नमस्ते दोस्तों आज की बात", "यह दूसरी line है", "2024"], [s["text"] for s in sg]
    assert sg[0]["start"] == 1.0 and sg[0]["end"] == 2.8, sg[0]          # the overlap with cue 2 is removed
    assert sg[2]["start"] == 70.25
    w = sg[0]["words"]
    assert [x["w"] for x in w] == ["नमस्ते", "दोस्तों", "आज", "की", "बात"]
    assert all(w[i]["end"] <= w[i + 1]["start"] + 1e-6 for i in range(len(w) - 1)) and w[0]["start"] == 1.0 and w[-1]["end"] <= 2.8
    assert w[1]["end"] - w[1]["start"] > w[3]["end"] - w[3]["start"], "longer words get more time"
    short = srtimport.parse(SRT, duration=6.0)
    assert len(short["segments"]) == 2 and short["segments"][1]["end"] == 5.5
    v = srtimport.parse(VTT)
    assert v["imported"] == "vtt" and [s["text"] for s in v["segments"]] == ["Hello world", "second line"], v
    assert v["segments"][0]["start"] == 1.0 and v["segments"][0]["end"] == 2.5
    for bad in ("", "just some text\nwithout times", "1\n00:00:05,000 --> 00:00:02,000\nbackwards"):
        try:
            srtimport.parse(bad)
            raise AssertionError("must refuse: " + bad[:20])
        except ValueError:
            pass
    # the rest of the app can use it: words → karaoke captions
    words = words_of(tr)
    assert len(words) == 10
    ass = captions.build_ass(words, {"mode": "karaoke"}, 1080, 1920, margin_v_ratio=0.2)
    assert ass.count("Dialogue:") == 10
    print("srt import: cues → segments, tags / index numbers / overlaps handled, VTT too, karaoke captions from it ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
