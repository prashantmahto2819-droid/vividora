"""Silence by voice detection (engine/vad.py). The model itself ships with faster-whisper on the server; here its answer is
given by the test, so the wiring around it is what is checked. Run: python3 tests/test_vad.py"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vividora.engine import autocut, vad  # noqa: E402


def main():
    assert vad.gaps([(1.0, 3.0), (3.2, 5.0), (7.0, 9.5)], 10.0) == [(0.0, 1.0), (5.0, 7.0), (9.5, 10.0)]     # 0.2 s is a breath, not a cut
    assert vad.gaps([], 4.0) == [(0.0, 4.0)] and vad.gaps([(0.0, 4.0)], 4.0) == []
    os.environ.pop("SILENCE_ENGINE", None)
    assert vad.engine_setting() == "loudness"
    os.environ["SILENCE_ENGINE"] = "Silero"
    assert vad.engine_setting() == "silero"
    os.environ["SILENCE_ENGINE"] = "nonsense"
    assert vad.engine_setting() == "loudness"
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "a.wav"
        # a loud hum all the way through (the loudness rule finds no silence at all) with "speech" from 1–3 s and 6–8 s
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=120:d=10", "-af", "volume=0.5", "-ar", "16000", "-ac", "1", str(wav)], check=True)
        from vividora.engine import ffmpeg as ff
        assert ff.silences(wav) == [], "the hum must fool the loudness rule (that is the case this feature is for)"
        seen = {}

        def fake(audio, ms, pad_ms, th):
            seen.update(n=len(audio), ms=ms, pad=pad_ms, th=th)
            return [{"start": 16000, "end": 48000}, {"start": 96000, "end": 128000}]
        sil = vad.silences(wav, 10.0, detect=fake)
        assert sil == [(0.0, 1.0), (3.0, 6.0), (8.0, 10.0)], sil
        assert abs(seen["n"] - 160000) < 400 and seen["ms"] == 450 and seen["th"] == 0.5, seen
        # no voice heard at all (a music clip) → None: the caller keeps the loudness rule, nothing is cut away wholesale
        assert vad.silences(wav, 10.0, detect=lambda *a: []) is None
        # the model is missing / breaks → None, never an exception
        def boom(*a):
            raise RuntimeError("model file missing")
        assert vad.silences(wav, 10.0, detect=boom) is None
        try:
            import faster_whisper  # noqa: F401
            real = vad.speech(wav)
            print("real Silero on a pure hum:", real)
        except ImportError:
            assert vad.speech(wav) is None           # this machine has no faster-whisper: falls back quietly
        # the cut list built from these silences
        tr = {"segments": [{"start": 1.0, "end": 3.0, "text": "पहली बात", "words": [{"w": "पहली", "start": 1.0, "end": 2.0}, {"w": "बात", "start": 2.0, "end": 3.0}]},
                           {"start": 6.0, "end": 8.0, "text": "दूसरी बात", "words": [{"w": "दूसरी", "start": 6.0, "end": 7.0}, {"w": "बात", "start": 7.0, "end": 8.0}]}]}
        edl = autocut.build_edl(tr, 10.0, sil, None)
        cuts = [(round(c["start"], 1), round(c["end"], 1)) for c in edl["cuts"] if c.get("enabled", True)]
        assert any(a <= 3.6 and b >= 5.4 for a, b in cuts), cuts          # the 3 s pause between the two lines is cut
        assert not any(a < 2.9 and b > 1.1 for a, b in cuts), cuts        # no cut reaches into the words
        none = autocut.build_edl(tr, 10.0, [], None)
        print(f"voice-based silences {sil} → cuts {cuts}; with the loudness rule on this hum: {len([c for c in none['cuts'] if c.get('reason') == 'silence'])} silence cuts")
    print("ALL PASS")


if __name__ == "__main__":
    main()
