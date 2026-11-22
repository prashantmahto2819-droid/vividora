"""Themes + beat-plan upgrade: pure-function checks (no server, no media). Run: python3 tests/test_themes_units.py"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="vividora-themes-")
os.environ.setdefault("DATA_ROOT", _tmp)
os.environ.setdefault("MEDIA_ROOT", _tmp)
os.environ.setdefault("DATABASE_PATH", str(Path(_tmp) / "v.db"))

from vividora.engine import beatcut, themes  # noqa: E402
from vividora.engine.presets import caption_styles  # noqa: E402
from vividora.service import DEFAULT_RENDER  # noqa: E402


class ThemeTests(unittest.TestCase):
    def test_00_colour_feel_and_beat_colour(self):
        import subprocess
        from vividora.engine import beatcut
        from vividora.engine.catalog import GRADE_PRESETS, grade_filter
        b = themes.builtin()

        def look(vf: str) -> tuple[float, float]:
            """(mean brightness 0-255, mean colourfulness 0-255) of a test picture after a filter chain."""
            src = "testsrc2=s=320x180:d=1,eq=brightness=-0.12:saturation=0.8"     # a slightly dark, normal-coloured picture
            raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", src, "-vf", (vf + "," if vf else "") + "format=rgb24",
                                  "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
            px = [raw[i:i + 3] for i in range(0, len(raw), 3)]
            return (sum(sum(p) / 3 for p in px) / len(px), sum(max(p) - min(p) for p in px) / len(px))
        base = look("")
        for tid in ("luxury", "cinematic", "diwali", "bw_classic", "night_neon"):          # dark / one-colour themes
            g = {k: v for k, v in GRADE_PRESETS[b[tid]["grade_preset"]].items() if k not in ("label", "cat")}
            theme_l, theme_c = look(grade_filter(g))
            lv = themes.colour_feel(g, "light_vivid")
            l, c = look(grade_filter(lv))
            self.assertGreater(l, base[0] + 4, tid)                 # brighter than the untouched picture …
            self.assertGreater(l, theme_l, tid)                     # … and than the theme's own grade
            self.assertGreater(c, base[1], tid)                     # more colourful than the source (also for the B&W theme)
            self.assertGreaterEqual(lv.get("shadows", 0), 0.25, tid)
            self.assertNotIn("vignette", lv)
            for feel in themes.FEEL_IDS:                            # every feel gives a chain ffmpeg accepts
                look(grade_filter(themes.colour_feel(g, feel)))
        g = {"temperature": 0.4, "contrast": 0.2, "vignette": 0.4}
        self.assertEqual(themes.colour_feel(g, "theme"), g)
        self.assertEqual(themes.colour_feel(g, "nonsense"), g)
        self.assertEqual(themes.colour_feel(g, "theme_lite")["temperature"], 0.2)
        self.assertNotIn("temperature", themes.colour_feel(g, "bright_clean"))               # no colour cast at all
        # applying a theme with a feel
        rs, _, _ = themes.apply({}, b["luxury"], ["look"], feel="light_vivid")
        e = rs["effects"]
        self.assertEqual((e["grade_feel"], e["grade_preset"]), ("light_vivid", ""))
        self.assertNotIn("vignette", e["extras"])
        rs, _, _ = themes.apply({}, b["luxury"], ["look"])
        self.assertEqual((rs["effects"]["grade_feel"], rs["effects"]["grade_preset"]), ("theme", "epic_dark"))
        self.assertIn("vignette", rs["effects"]["extras"])
        # colour on the beat follows the song's BPM; choosing "none" later removes it again
        lib = [{"id": "m1", "kind": "music", "name": "song", "tags": "", "meta": {"bpm": 150, "moods": ["energetic"]}}]
        rs, _, _ = themes.apply({}, b["viral"], ["effects", "music"], library=lib, beat_colour="pulse")
        st = [x for x in rs["effects"]["stack"] if x.get("beat_colour")]
        self.assertEqual((st[0]["id"], st[0]["params"]["bpm"]), ("tr_chroma_pulse", 75))     # 150 bpm → every second beat
        rs2, _, _ = themes.apply(rs, b["viral"], ["effects"], beat_colour="flash")
        st = [x for x in rs2["effects"]["stack"] if x.get("beat_colour")]
        self.assertEqual([x["id"] for x in st], ["flash_pulse"])
        rs3, _, _ = themes.apply(rs2, b["viral"], ["effects"], beat_colour="none")
        self.assertFalse([x for x in rs3["effects"]["stack"] if x.get("beat_colour")])
        self.assertEqual(themes.beat_colour_stack("pulse", None)[0]["params"]["bpm"], 110)
        # montage: the feel rides on the look string
        dark = beatcut._grade("grade:epic_dark", 0.5)
        lite = beatcut._grade("grade:epic_dark@light_vivid", 0.5)
        self.assertNotEqual(dark, lite)
        self.assertGreater(look(lite)[0], look(dark)[0])
        self.assertTrue(beatcut._grade("none@light_vivid", 0.5) and beatcut._grade("auto@punchy", 0.5))
        self.assertEqual(beatcut._grade("grade:epic_dark", 0.5), dark)
        self.assertEqual(beatcut._grade("none", 0.5), "")

    def test_00_new_themes_and_own_text_colour(self):
        from vividora.engine import beatcut
        from vividora.engine.textfx import _STYLES
        b = themes.builtin()
        self.assertGreaterEqual(len(b), 27)
        sty = {x[0] for x in _STYLES}
        for tid in ("travel", "food", "wedding", "festival", "diwali", "news", "tech", "fitness", "nature", "vintage", "night_neon", "pastel",
                    "luxury", "kids", "monsoon", "sunset", "education", "bw_classic"):
            t = b[tid]
            self.assertIn(t["text_style"], sty, tid)
            self.assertTrue(all(x in beatcut.FX_ALL for x in t["montage"]["fx_strong"] + t["montage"]["fx_soft"]), tid)
            self.assertEqual(len(t["swatch"]), 2, tid)
            _, applied, skipped = themes.apply({}, t, None, has_transcript=True)
            self.assertEqual(set(applied), set(themes.PART_IDS), (tid, skipped))     # every part of every new theme really applies
        # own text colour: plain style → letter colour (a too-similar outline flips so it stays readable)
        d = themes.apply({}, b["viral"], ["text"], text_color="#00ff88")[0]["effects"]["text_default"]
        self.assertEqual((d["color"], d["outline"]), ("#00FF88", "#000000"))
        d = themes.apply({}, b["motivational"], ["text"], text_color="#101010")[0]["effects"]["text_default"]
        self.assertEqual((d["color"], d["outline"]), ("#101010", "#FFFFFF"))
        # boxed style → the box takes the colour, the letters turn black / white
        d = themes.apply({}, b["business"], ["text"], text_color="#ffe000")[0]["effects"]["text_default"]
        self.assertEqual((d["box_color"], d["color"]), ("#FFE000", "#111111"))
        d = themes.apply({}, b["education"], ["text"], text_color="#102040")[0]["effects"]["text_default"]
        self.assertEqual((d["box_color"], d["color"]), ("#102040", "#FFFFFF"))
        # junk is ignored, no colour = the theme's own
        own = themes.text_style("neon_pink")["color"]
        self.assertEqual(themes.apply({}, b["viral"], ["text"], text_color="red; drop")[0]["effects"]["text_default"]["color"], own)
        self.assertEqual(themes.apply({}, b["viral"], ["text"])[0]["effects"]["text_default"]["color"], own)

    def test_builtin_themes_reference_real_ids(self):
        from vividora.engine.catalog import EFFECTS, GRADE_PRESETS
        from vividora.engine.effects import TRANSITIONS, VOICE_PRESETS
        fx = {e["id"] for e in EFFECTS}
        b = themes.builtin()
        self.assertGreaterEqual(len(b), 9)
        for t in b.values():
            self.assertIn(t["grade_preset"], GRADE_PRESETS, t["id"])
            self.assertIn(t["caption_style"], caption_styles(), t["id"])
            self.assertIn(t["transition"], TRANSITIONS, t["id"])
            self.assertIn(t["voice"], VOICE_PRESETS, t["id"])
            self.assertTrue(themes.text_style(t["text_style"]), t["id"])
            for s in t.get("stack") or []:
                self.assertIn(s["id"], fx, t["id"])

    def test_apply_all_parts(self):
        t = themes.builtin()["cinematic"]
        lib = [{"id": "m1", "kind": "music", "name": "bg cinematic tension", "tags": ""}, {"id": "m2", "kind": "music", "name": "upbeat", "tags": "upbeat"}]
        rs, applied, skipped = themes.apply(DEFAULT_RENDER, t, None, has_transcript=True, library=lib, seed="x")
        self.assertEqual(set(applied), set(themes.PART_IDS))
        self.assertEqual(skipped, [])
        self.assertEqual(rs["caption_style"], "minimal")
        e = rs["effects"]
        self.assertEqual(e["grade_preset"], "teal_orange")
        self.assertEqual(e["transition"], "dip")
        self.assertEqual(e["music"]["id"], "m1")
        self.assertEqual(e["voice"]["preset"], "soft")
        self.assertTrue(any(s["id"] == "tr_letterbox" and s["theme"] for s in e["stack"]))
        self.assertEqual(rs["theme_id"], "cinematic")
        self.assertEqual(rs["theme_montage"]["pace"], "slow")

    def test_captions_skipped_without_transcript_and_partial_parts(self):
        t = themes.builtin()["viral"]
        rs, applied, skipped = themes.apply(DEFAULT_RENDER, t, ["captions", "look"], has_transcript=False)
        self.assertEqual(applied, ["look"])
        self.assertTrue(skipped and "transcript" in skipped[0])
        self.assertEqual(rs["caption_style"], DEFAULT_RENDER["caption_style"])

    def test_theme_stack_replaces_only_theme_effects(self):
        base = {**DEFAULT_RENDER, "effects": {**DEFAULT_RENDER["effects"], "stack": [{"id": "grain", "params": {}, "enabled": True}, {"id": "tr_vhs", "params": {}, "theme": True}]}}
        rs, _, _ = themes.apply(base, themes.builtin()["motivational"], ["effects"])
        ids = [s["id"] for s in rs["effects"]["stack"]]
        self.assertIn("grain", ids)
        self.assertNotIn("tr_vhs", ids)
        self.assertIn("tr_light_leak", ids)

    def test_text_part_restyles_titles(self):
        base = {**DEFAULT_RENDER, "effects": {**DEFAULT_RENDER["effects"], "titles": [{"text": "hi", "color": "#123456", "font": "Lora", "start": 0, "end": 1}]}}
        rs, _, _ = themes.apply(base, themes.builtin()["devotional"], ["text"])
        self.assertEqual(rs["effects"]["titles"][0]["color"], "#FF9933")
        self.assertEqual(rs["effects"]["text_default"]["template"], "saffron")

    def test_from_project_round_trip(self):
        t = themes.builtin()["business"]
        rs, _, _ = themes.apply(DEFAULT_RENDER, t, None)
        back = themes.from_project({"title": "x", "settings": {"render": rs, "montage": {}}}, "mine")
        self.assertEqual(back["grade_preset"], "clean_commercial")
        self.assertEqual(back["caption_style"], "boxed")
        self.assertEqual(back["text_style"], "white_box")


def _fake_music(n_beats=64, period=0.5, drops=(16, 40)):
    beats = [round(i * period, 3) for i in range(n_beats)]
    energy = [0.9 if i in drops else (0.7 if i % 4 == 0 else 0.3) for i in range(n_beats)]
    strength = [0.9 if i % 4 == 0 else 0.3 for i in range(n_beats)]
    return {"bpm": 120.0, "period": period, "duration": n_beats * period, "beats": beats, "strength": strength, "energy": energy,
            "bar0": 0, "drops": list(drops), "start_i": 0}


def _fake_clip(cid, dur, score=0.6, face=False):
    n = int(dur * 4)
    return {"id": cid, "kind": "video", "duration": dur, "w": 1080, "h": 1920, "t": [i / 4 for i in range(n)], "score": [score] * n,
            "motion": [0.5] * n, "fx": [.5] * n, "fy": [.5] * n, "face": [face] * n, "audio": [0.0] * n,
            "thumbs": [[(cid.__hash__() + i // 8) % 255] * 36 for i in range(n)]}


class PlanTests(unittest.TestCase):
    def test_cuts_land_on_drops_and_theme_pools(self):
        mu = _fake_music()
        clips = [_fake_clip("a", 20), _fake_clip("b", 20), _fake_clip("c", 12)]
        pl = beatcut.plan(mu, clips, max_seconds=30, pace="slow", effects="strong", fx_strong=["glitch", "rgb"], fx_soft=["flash"],
                          speed_ramp=True, intro=True, outro=True, pins=["c"])
        starts = {round(s["dur"], 3) for s in pl["segments"]}
        self.assertTrue(starts)
        # a cut begins exactly on every drop (beat 16 → 8.0 s, beat 40 → 20.0 s)
        acc, begins = 0.0, []
        for s in pl["segments"]:
            begins.append(round(acc, 2)); acc += s["dur"]
        self.assertIn(8.0, begins); self.assertIn(20.0, begins)
        self.assertTrue(pl["segments"][0].get("intro") and pl["segments"][-1].get("outro"))
        self.assertTrue(set(s["fx"] for s in pl["segments"]) <= {"cut", "glitch", "rgb", "flash", "zoom_in", "zoom_out"})
        self.assertTrue(any(s.get("ramp") for s in pl["segments"]), "slow-mo ramp before a drop")
        self.assertTrue(any(s["clip"] == "c" for s in pl["segments"]), "pinned clip present")
        self.assertEqual(len(pl["beat_strength"]), len(pl["beats"]))
        self.assertAlmostEqual(pl["total"], 30, delta=mu["period"])
        # variety: no clip twice in a row except deliberate stutter on a drop
        for x, y in zip(pl["segments"], pl["segments"][1:]):
            if x["clip"] == y["clip"]:
                self.assertEqual(x.get("beat"), y.get("beat"), "same clip in a row only as a drop stutter")

    def test_full_song_length(self):
        mu = _fake_music(n_beats=40)
        pl = beatcut.plan(mu, [_fake_clip("a", 30), _fake_clip("b", 30)], max_seconds=0, pace="fast", effects="none")
        self.assertTrue(pl["full"])
        self.assertGreater(pl["total"], 18)
        self.assertTrue(all(s["fx"] in ("cut", "zoom_out", "zoom_in") for s in pl["segments"]))

    def test_dedup_penalises_identical_takes(self):
        mu = _fake_music(n_beats=24)
        same = _fake_clip("a", 10)
        twin = {**_fake_clip("b", 10), "thumbs": same["thumbs"]}   # identical pictures
        other = {**_fake_clip("c", 10, score=0.5), "thumbs": [[200] * 36] * 40}
        pl = beatcut.plan(mu, [same, twin, other], max_seconds=10, pace="fast", effects="none")
        self.assertGreaterEqual(sum(1 for s in pl["segments"] if s["clip"] == "c"), 2, "the different-looking clip gets picked despite a lower score")


if __name__ == "__main__":
    unittest.main(verbosity=1)
