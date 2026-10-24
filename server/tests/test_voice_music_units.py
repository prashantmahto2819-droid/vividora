"""Voice Studio (line cache, markers, speakers, per-line redo), music tagging and the reference analyzer.
Run: python3 tests/test_voice_music_units.py   (fake TTS backend, ffmpeg needed)"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["VIVIDORA_TTS"] = "fake"
TMP = Path(tempfile.mkdtemp(prefix="vm_units_"))
os.environ["TTS_LINE_CACHE"] = str(TMP / "cache")

from vividora.engine import dub, musictag, refanalyze, tts  # noqa: E402


def test_text_helpers():
    assert tts.speaker_of("रोहित: नमस्ते दोस्तों") == ("रोहित", "नमस्ते दोस्तों")
    assert tts.speaker_of("[Divya] hello there") == ("Divya", "hello there")
    assert tts.speaker_of("Note: this is not a speaker line with many words") == (None, "Note: this is not a speaker line with many words")
    assert tts.speaker_of("सिर्फ़ एक line") == (None, "सिर्फ़ एक line")
    items = tts.script_lines("रोहित: पहली बात। दूसरी बात।\n\nदिव्या: ठीक है।")
    assert [i.get("speaker") for i in items] == ["रोहित", "रोहित", "दिव्या"], items
    assert tts.speakers_in("A: x\nB: y\nA: z") == ["A", "B"]
    pieces = tts.parse_pieces("यह *बहुत* ज़रूरी है [pause 0.5] सुनो")
    assert [p.get("text", p.get("gap")) for p in pieces] == ["यह", "बहुत", "ज़रूरी है", 0.5, "सुनो"], pieces
    assert pieces[1]["emph"] is True
    assert tts.plain_text("यह *बहुत* ज़रूरी है [pause 0.5] सुनो") == "यह बहुत ज़रूरी है सुनो"
    assert tts.apply_fixes("Vividora is SEO ready", {"Vividora": "विविडोरा", "seo": "एस ई ओ"}) == "विविडोरा is एस ई ओ ready"
    assert dub.fixes_map("Vividora = विविडोरा\nbad line\n SEO=एस ई ओ ") == {"Vividora": "विविडोरा", "SEO": "एस ई ओ"}
    print("PASS text helpers")


def test_line_cache_and_track():
    work = TMP / "w1"
    payload = {"mode": "script", "language": "hi", "voice": {"id": "hi_rohit_deep", "engine": "parler", "gender": "m"},
               "segments": [{"text": "पहली line यहाँ है।", "pause": 0.3}, {"text": "दूसरी *ज़ोर* वाली line [pause 0.4] है।", "pause": 0.5, "pitch": 2},
                            {"text": "तीसरी line।", "pause": 0.3, "speaker": "दिव्या"}],
               "speakers": {"दिव्या": {"voice": {"id": "hi_divya_soft", "engine": "parler", "gender": "f"}, "pitch": -2}}}
    r1 = tts.build_track(payload, work)
    assert r1["cached"] == 0 and len(r1["segments"]) == 3
    assert r1["segments"][2]["speaker"] == "दिव्या"
    assert r1["segments"][1]["words"][1]["w"] == "ज़ोर", r1["segments"][1]["words"]
    # the same again: everything from the cache
    r2 = tts.build_track(payload, TMP / "w2")
    assert r2["cached"] == 3, r2["cached"]
    assert abs(r1["duration"] - r2["duration"]) < 0.02
    # a per-line redo: only line 1 re-made (seed bumped), 0 and 2 cached
    asset = {"id": "old", "meta": {"mode": "script", "language": "hi", "voice": payload["voice"], "speed": 1.0, "pitch": 0,
                                   "segments": r2["segments"], "speakers": payload["speakers"], "total": 0}}
    pl = dub.redo_payload(asset, [{"i": 1, "redo": True}])
    assert pl["replace"] == "old" and pl["changed"] == 1 and pl["segments"][1].get("seed") is not None
    assert pl["segments"][1]["pitch"] == 2 and pl["segments"][2]["speaker"] == "दिव्या"
    r3 = tts.build_track(pl, TMP / "w3")
    assert r3["cached"] == 2, r3["cached"]
    # text edit counts as a change; no edit → error
    pl2 = dub.redo_payload(asset, [{"i": 0, "text": "नई पहली line।"}])
    assert pl2["changed"] == 1 and pl2["segments"][0]["text"] == "नई पहली line।"
    try:
        dub.redo_payload(asset, [{"i": 0}])
        raise AssertionError("no-change should fail")
    except ValueError:
        pass
    # pitch filter: rubberband or the asetrate fallback, length kept within 3 %
    src = TMP / "w1" / "dub_hi.m4a"
    assert src.exists()
    pf = tts.pitch_filter(3)
    assert pf
    out = TMP / "p.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", pf, "-ac", "1", "-ar", "48000", str(out)], check=True)
    d0 = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout)
    d1 = tts.wav_seconds(out)
    assert abs(d0 - d1) / d0 < 0.03, (d0, d1)
    print(f"PASS line cache + track + redo (pitch via {'rubberband' if 'rubberband' in pf else 'asetrate'})")


def _tone(path: Path, bpm: float, seconds: float = 20, bright: bool = False) -> Path:
    # a click track at `bpm` with a sustained tone: tempo detectable, brightness controllable
    period = 60 / bpm
    f = 2200 if bright else 160
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={f}:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=1200:duration={seconds}",
                    "-filter_complex", f"[1:a]volume='if(lt(mod(t,{period:.4f}),0.05),1,0)':eval=frame[c];[0:a]volume=0.3[t];[t][c]amix=inputs=2:normalize=0,volume=0.5",
                    "-ar", "44100", "-ac", "1", str(path)], check=True)
    return path


def test_musictag():
    fast = musictag.analyze(_tone(TMP / "fast.wav", 128, bright=True), "gym_hype", "")
    slow = musictag.analyze(_tone(TMP / "slow.wav", 70), "emotional_piano_70bpm", "")
    assert fast["analysed"] and slow["analysed"]
    assert fast["bpm"] > slow["bpm"], (fast["bpm"], slow["bpm"])
    assert fast["brightness"] > slow["brightness"]
    assert "energetic" in fast["moods"], fast
    assert "emotional" in slow["moods"] and "piano" in slow["genres"], slow
    m, g = musictag.guess_tags(72, 0.2, 0.3, 0.1, "")
    assert "calm" in m or "emotional" in m
    m, g = musictag.guess_tags(140, 0.8, 0.7, 0.3, "")
    assert "energetic" in m and "electronic" in g
    assert musictag.commercial_ok("CC0") is True and musictag.commercial_ok("CC BY-NC 4.0") is False and musictag.commercial_ok("") is None
    print("PASS musictag", fast["bpm"], fast["moods"], slow["bpm"], slow["moods"], slow["genres"])


def test_refanalyze():
    # a reference with hard cuts every 1.5 s (colour changes) + a click track
    v = TMP / "ref.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x224466:s=320x180:r=25:d=12",
                    "-f", "lavfi", "-i", "color=c=0xcc8833:s=320x180:r=25:d=12",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
                    "-filter_complex", "[0:v][1:v]blend=all_expr='if(lt(mod(T,3),1.5),A,B)'[v]",
                    "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(v)], check=True)
    res = refanalyze.analyze(v)
    m, g, t = res["measured"], res["guessed"], res["theme"]
    assert m["cuts"] >= 5, m
    assert 1.0 <= m["avg_shot"] <= 2.2, m
    assert g["pace"] == "medium", g
    assert t["montage"]["pace"] == "medium" and t["label"]
    assert "reference" in t and t["reference"]["measured"]["cuts"] == m["cuts"]
    print("PASS refanalyze", m["cuts"], m["avg_shot"], g["grade_preset"], g["music_mood"])


if __name__ == "__main__":
    try:
        test_text_helpers()
        test_line_cache_and_track()
        test_musictag()
        test_refanalyze()
        print("OK")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
