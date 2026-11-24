"""Word alignment hook (engine/align.py): the merge rules and the safety net. Run: python3 tests/test_align.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vividora.engine import align  # noqa: E402

TR = {"language": "hi", "segments": [
    {"start": 1.0, "end": 3.0, "text": "नमस्ते दोस्तों 2024", "words": [{"w": "नमस्ते", "start": 1.0, "end": 1.8}, {"w": "दोस्तों", "start": 1.8, "end": 2.5}, {"w": "2024", "start": 2.5, "end": 3.0}]},
    {"start": 4.0, "end": 5.0, "text": "फिर मिलेंगे", "words": [{"w": "फिर", "start": 4.0, "end": 4.4}, {"w": "मिलेंगे", "start": 4.4, "end": 5.0}]}]}


def main():
    good = [{"words": [{"word": "नमस्ते", "start": 1.12, "end": 1.70}, {"word": "दोस्तों", "start": 1.74, "end": 2.41}, {"word": "2024"}]},   # numbers get no time
            {"words": [{"word": "फिर", "start": 4.05, "end": 4.38}, {"word": "मिलेंगे", "start": 9.0, "end": 9.5}]}]                    # a wild jump
    tr, n = align.merge(TR, good)
    w = tr["segments"][0]["words"]
    assert (w[0]["start"], w[0]["end"], w[1]["start"]) == (1.12, 1.7, 1.74) and (w[2]["start"], w[2]["end"]) == (2.5, 3.0), w
    w2 = tr["segments"][1]["words"]
    assert w2[0]["start"] == 4.05 and (w2[1]["start"], w2[1]["end"]) == (4.4, 5.0), w2          # the jump is refused
    assert n == 3 and tr["aligned"] == "whisperx" and [x["w"] for x in w] == ["नमस्ते", "दोस्तों", "2024"]
    for sg in tr["segments"]:
        ws = sg["words"]
        assert all(ws[i]["end"] <= ws[i + 1]["start"] + 0.021 for i in range(len(ws) - 1)) and all(x["end"] > x["start"] for x in ws)
    # another word count in a segment → that segment is left alone; another segment count → nothing changes
    odd = [{"words": [{"word": "नमस्ते", "start": 1.1, "end": 1.7}]}, good[1]]
    tr2, n2 = align.merge(TR, odd)
    assert tr2["segments"][0] == TR["segments"][0] and n2 == 1
    assert align.merge(TR, good[:1]) == (TR, 0)
    # off by default; on but not installed → untouched; a failing aligner → untouched
    os.environ.pop("WORD_ALIGN", None)
    assert not align.wanted() and align.refine(TR, Path("x.wav"), "hi") == (TR, 0)
    os.environ["WORD_ALIGN"] = "whisperx"
    assert align.wanted()
    if not align.available():
        assert align.refine(TR, Path("x.wav"), "hi") == (TR, 0)
    def boom(*a):
        raise RuntimeError("model download failed")
    assert align.refine(TR, Path("x.wav"), "hi", backend=boom) == (TR, 0)
    seen = {}
    def fake(segs, audio, lang):
        seen.update(lang=lang, n=len(segs), text=segs[0]["text"])
        return good
    tr3, n3 = align.refine(TR, Path("x.wav"), None, backend=fake)
    assert n3 == 3 and seen == {"lang": "hi", "n": 2, "text": "नमस्ते दोस्तों 2024"}
    print("alignment: times taken where safe, numbers / wild jumps / odd counts keep their own, failures change nothing ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
