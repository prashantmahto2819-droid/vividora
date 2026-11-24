"""Speaker switch (engine/speakers.py): faces + mouth motion → turns → camera plan; second camera by sound.
Run: python3 tests/test_speakers.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vividora.engine import catalog, effects, speakers  # noqa: E402

W, H, FPS = 1280, 720, 25
# who talks when (seconds): left, right, left — with a short "हाँ" of the left person inside the right one's answer
TALK = [(0.0, 6.0, 0), (6.0, 9.0, 1), (9.0, 9.6, 0), (9.6, 14.0, 1), (14.0, 18.0, 0)]
BOX = [(190, 160, 300), (790, 160, 300)]     # x, y, size of each face on the canvas


def face_img():
    """A stand-in "face": a textured box (the sandbox has no cascade files, the detector is given by the test)."""
    rng = np.random.default_rng(1)
    g = np.clip(150 + rng.normal(0, 18, (230, 230, 1)), 0, 255).astype(np.uint8)
    return np.repeat(g, 3, axis=2)


def fake_detect(only: bool = False):
    """Returns the true boxes (a little shaky, sometimes one missing, sometimes a false hit on the wall)."""
    rng = np.random.default_rng(7)

    def detect(frame):
        k = frame.shape[1] / W
        out = []
        for x, y, s_ in ([(490, 160, 300)] if only else BOX):
            if rng.random() < 0.15:
                continue
            j = rng.integers(-3, 4, 2)
            out.append((int(x * k) + int(j[0]), int(y * k) + int(j[1]), int(s_ * k), int(s_ * k)))
        if rng.random() < 0.08:
            out.append((int(rng.integers(0, 380)), 5, 40, 40))
        return out
    return detect


def make_video(path: Path, *, only: int | None = None, audio_delay: float = 0.0, seconds: float = 18.0) -> bool:
    """Two still faces on a grey wall; the mouth area of whoever talks flickers. Sound: a click train while anyone talks."""
    import cv2
    face = face_img()
    rng = np.random.default_rng(3)
    n = int(seconds * FPS)
    sr = 16000
    snd = np.zeros(int((seconds + audio_delay) * sr), dtype=np.float32)
    for a, b, _ in TALK:
        t = a
        while t < b:
            i = int((t + audio_delay) * sr)
            snd[i:i + 400] += rng.normal(0, 0.5, 400).astype(np.float32)[:max(0, len(snd) - i)][:400]
            t += float(rng.uniform(0.12, 0.4))
    wav = path.with_suffix(".raw")
    (snd * 20000).astype(np.int16).tofile(wav)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", str(wav), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], stdin=subprocess.PIPE)
    base = np.full((H, W, 3), 90, dtype=np.uint8)
    faces = [k for k in (0, 1) if only is None or k == only]
    for k in faces:
        x, y, s = BOX[k] if only is None else (490, 160, 300)
        base[y:y + s, x:x + s] = cv2.resize(face, (s, s))
    for i in range(n):
        t = i / FPS
        fr = base.copy()
        who = next((w for a, b, w in TALK if a <= t < b), None)
        if who in faces:
            x, y, s = BOX[who] if only is None else (490, 160, 300)
            mx0, mx1, my0, my1 = x + int(s * 0.3), x + int(s * 0.7), y + int(s * 0.68), y + int(s * 0.88)
            patch = fr[my0:my1, mx0:mx1].astype(np.int16) + rng.integers(-60, 60, (my1 - my0, mx1 - mx0, 1))
            fr[my0:my1, mx0:mx1] = np.clip(patch, 0, 255).astype(np.uint8)
        proc.stdin.write(fr.tobytes())
    proc.stdin.close()
    proc.wait()
    wav.unlink(missing_ok=True)
    return path.exists()


def words():
    out = []
    for a, b, _ in TALK:
        t = a + 0.05
        while t < b - 0.2:
            out.append({"start": round(t, 2), "end": round(t + 0.3, 2), "w": "शब्द"})
            t += 0.4
    return out


def test_turns_unit():
    fps, n = 5.0, 150
    sc = np.zeros((n, 2), dtype=np.float32) + 0.05
    sc[0:50, 0] = 1.0            # A: 0–10 s
    sc[50:100, 1] = 1.0          # B: 10–20 s
    sc[70:73, 0] = 2.0           # A says "हाँ" for 0.6 s inside B's answer
    sc[100:150, 0] = 1.0         # A: 20–30 s
    tl = speakers.turns(sc, fps, duration=30.0)
    assert [t["who"] for t in tl] == [0, 1, 0], tl
    assert abs(tl[1]["start"] - 10) < 0.8 and abs(tl[2]["start"] - 20) < 0.8, tl
    assert tl[0]["start"] == 0 and tl[-1]["end"] == 30.0
    assert speakers.turns(sc[:, :1], fps) == []                 # one person → nothing to switch
    # the switch is put on the start of the first word after a pause
    ws = [{"start": 9.2, "end": 9.5}, {"start": 10.31, "end": 10.6}, {"start": 10.65, "end": 11}]
    assert abs(speakers._snap(10.0, ws) - 10.25) < 0.01
    print("turns: 3 turns, interjection ignored, snapped to a word ✓")


def test_shots_unit():
    faces = [{"x": 0.25, "y": 0.4, "w": 0.2, "h": 0.36, "seen": 1}, {"x": 0.75, "y": 0.4, "w": 0.1, "h": 0.18, "seen": 1}]
    tl = [{"start": 0, "end": 30, "who": 0}, {"start": 30, "end": 36, "who": 1}]
    sh = speakers.shots(tl, faces, 36, style="mix")
    assert sh[0]["shot"] == "wide" and sh[0]["end"] == 2.5, sh[0]
    assert [s["shot"] for s in sh] == ["wide", "close", "wide", "close", "close"], [s["shot"] for s in sh]
    assert sh[-1]["who"] == 1 and sh[-1]["end"] == 36
    assert all(abs(sh[i]["end"] - sh[i + 1]["start"]) < 1e-6 for i in range(len(sh) - 1))
    c0, c1 = sh[1], sh[-1]
    assert c0["zoom"] < c1["zoom"], "the smaller (farther) face needs more zoom"
    assert c0["x"] < 0.3 and c1["x"] > 0.7
    # the window really contains the face
    for c, f in ((c0, faces[0]), (c1, faces[1])):
        left = (1 - 1 / c["zoom"]) * c["x"]
        assert left <= f["x"] - f["w"] / 2 + 0.02 and f["x"] + f["w"] / 2 <= left + 1 / c["zoom"] + 0.02, (c, f)
    cl = speakers.shots(tl, faces, 36, style="close")
    assert [s["shot"] for s in cl] == ["close", "close"]
    cam = speakers.shots(tl, faces[:1], 36, style="close", cams={1: True})
    assert cam[1]["shot"] == "cam" and "zoom" not in cam[1] and cam[0]["shot"] == "close"
    solo = speakers.shots(tl, faces[:1], 36, style="close", cams={1: True}, main_close=False)
    assert [s["shot"] for s in solo] == ["wide", "cam"], solo        # camera 1 already shows one person: no zoom
    pts = speakers.track_points(sh, faces, [12.0])
    assert pts[0] == [0.0, 0.25] and pts[-1][1] == 0.75 and [12.0, 0.25] in pts, pts
    assert speakers.cover_focus(0.8, 16 / 9, 9 / 16) > 0.8 and speakers.cover_focus(0.5, 16 / 9, 16 / 9) == 0.5
    print("shots: wide intro, wide inside a long answer, close-up window holds the face, vertical track ✓")


def test_scan_real(tmp: Path):
    v = tmp / "two.mp4"
    make_video(v)
    res = speakers.scan(v, 18.0, W, H, detect=fake_detect())
    fs = res["faces"]
    assert len(fs) == 2, fs
    assert abs(fs[0]["x"] - (190 + 150) / W) < 0.04 and abs(fs[1]["x"] - (790 + 150) / W) < 0.04, fs
    tl = speakers.turns(res["scores"], res["fps"], words(), duration=18.0)
    assert [t["who"] for t in tl] == [0, 1, 0], tl
    assert abs(tl[1]["start"] - 6.0) < 0.6 and abs(tl[2]["start"] - 14.0) < 0.6, tl
    print(f"scan: 2 faces found (x {fs[0]['x']:.2f}, {fs[1]['x']:.2f}); turns at {tl[1]['start']}s and {tl[2]['start']}s (true 6 / 14) ✓")
    return v, res


def test_two_cameras(tmp: Path, main):
    v, res = main
    cam = tmp / "cam2.mp4"
    make_video(cam, only=1, audio_delay=1.7, seconds=18.0)      # camera 2 was started 1.7 s earlier, shows the right person
    off, conf = speakers.sync_offset(v, cam)
    assert abs(off - 1.7) < 0.05 and conf > 6, (off, conf)
    other = tmp / "other.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=18:c=pink:a=0.3", "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=18",
                    "-shortest", str(other)], check=True)
    _, conf_bad = speakers.sync_offset(v, other)
    assert conf_bad < conf / 2, (conf_bad, conf)
    # camera 2's picture is NOT delayed in this test file (only its sound), so its mouth moves on the main clock
    c2 = speakers.scan(cam, 18.0, W, H, detect=fake_detect(True))
    assert len(c2["faces"]) == 1
    scores, who, faces = speakers.with_camera(res, c2, 0.0, words())
    assert [w["cam"] for w in who] == [1, 2] and len(faces) == 1 and faces[0]["x"] < 0.4, (who, faces)   # the right face left the main candidates
    tl = speakers.turns(scores, res["fps"], words(), norm=True, duration=18.0)
    assert [t["who"] for t in tl] == [0, 1, 0], tl
    sh = speakers.shots(tl, faces, 18.0, style="close", cams={1: True})
    assert [s["shot"] for s in sh] == ["close", "cam", "close"], sh
    print(f"two cameras: sound offset {off}s (true 1.7, confidence {conf}; unrelated file {conf_bad}); camera 2 takes its person ✓")


def test_filters(tmp: Path):
    # close-up effect: a white square at the right must fill most of the frame after a 2× close-up on it
    chain = catalog.stack_filter([{"id": "closeup", "params": {"zoom": 2, "x": 1, "y": 0.5}}], 640, 360, 25, 1)
    out = tmp / "cu.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1,drawbox=x=480:y=120:w=120:h=120:c=white:t=fill",
                    "-vf", chain, "-frames:v", "1", str(out)], check=True)
    import cv2
    im = cv2.imread(str(out), 0)
    assert im.shape == (360, 640)
    ys, xs = np.where(im > 200)
    assert xs.min() in range(310, 330) and xs.max() in range(550, 570) and ys.max() - ys.min() in range(230, 250), (xs.min(), xs.max(), ys.min(), ys.max())
    # cover fill with a focus point: the subject at 80 % of a wide clip stays inside a vertical frame
    f = effects.cover_fill({"focus_x": 0.8}, 180, 320)
    out2 = tmp / "cf.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1,drawbox=x=492:y=100:w=40:h=160:c=white:t=fill",
                    "-vf", f, "-frames:v", "1", str(out2)], check=True)
    im2 = cv2.imread(str(out2), 0)
    assert im2.shape == (320, 180)
    xs2 = np.where(im2 > 200)[1]
    assert len(xs2) and abs((xs2.min() + xs2.max()) / 2 - 90) < 6, (xs2.min(), xs2.max())
    assert effects.cover_fill({}, 180, 320).endswith("crop=180:320")
    print("filters: close-up window lands on the subject; cover fill keeps the focus point ✓")


def test_render(tmp: Path):
    """The whole render: close-up clip on a wide output, the window on the speaker in a vertical one, coloured captions."""
    from vividora.engine import presets, render
    v = tmp / "two.mp4"
    if not v.exists():
        make_video(v)
    meta = {"width": W, "height": H, "fps": FPS, "duration": 18.0, "has_audio": True}
    shots = [{"start": 0, "end": 6, "who": 0, "shot": "close", "cx": 0.2656, **speakers.closeup({"x": 0.2656, "y": 0.43, "w": 0.23, "h": 0.2})},
             {"start": 6, "end": 14, "who": 1, "shot": "close", "cx": 0.7344, **speakers.closeup({"x": 0.7344, "y": 0.43, "w": 0.23, "h": 0.2})},
             {"start": 14, "end": 18, "who": 0, "shot": "wide", "cx": 0.2656}]
    fxclips = [{"_spk": True, "kind": "effect", "id": "closeup", "params": {k: s[k] for k in ("zoom", "x", "y")}, "start": s["start"], "end": s["end"],
                "track": 0, "enabled": True} for s in shots if s["shot"] == "close"]
    def seg(a, words_):
        return {"start": a, "end": a + len(words_), "text": " ".join(words_),
                "words": [{"w": w_, "start": a + i, "end": a + i + 0.9} for i, w_ in enumerate(words_)]}
    tr = {"segments": [seg(0.2, ["HELLO", "FRIENDS"]), seg(7.0, ["YES", "RIGHT", "TRUE"])]}
    eff = {"speaker": {"enabled": True, "shots": shots, "faces": [{"x": 0.2656}, {"x": 0.7344}], "caption_colors": ["#FF0000", "#00FF00"]},
           "fxclips": fxclips}
    edl = {"duration": 18.0, "cuts": [{"start": 2.0, "end": 4.0, "enabled": True, "reason": "silence"}]}      # 2 s removed before the switch

    def frame(f: Path, t: float, w: int, h: int):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(f), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(int)

    def bright(im):          # where the grey "face" boxes are, as fractions of the width
        g = im.mean(axis=2)[: int(im.shape[0] * 0.75)]
        xs = np.where((g > 125).mean(axis=0) > 0.2)[0]
        return (float(round(xs.min() / im.shape[1], 2)), float(round(xs.max() / im.shape[1], 2))) if len(xs) else None
    style = presets.caption_style("karaoke") if "karaoke" in presets.caption_styles() else next(iter(presets.caption_styles().values()))
    wide = {"id": "t-wide", "label": "t", "width": 640, "height": 360, "fit": "crop", "burn_captions": True, "caption_margin_v": 0.08,
            "video": {"crf": 23, "preset": "ultrafast", "fps_max": 60}, "audio": {"loudness": -14, "true_peak": -1.5}}
    tall = {**wide, "id": "t-tall", "width": 360, "height": 640, "caption_margin_v": 0.2}
    r = render.render(video=v, audio=None, meta=meta, edl=edl, transcript=tr, preset=wide, style=style, out_dir=tmp / "ow", name="w",
                      effects=json_copy(eff), encoder_preset="ultrafast")
    f = Path(r["files"][0]["path"])
    a, b, c = (frame(f, t, 640, 360) for t in (1.0, 6.0, 14.0))        # output seconds: left close-up, right close-up (4 s = source 6 s), wide
    ba, bb, bc = bright(a), bright(b), bright(c)
    # one face, 1.8× larger, as near the middle as the edge of the picture allows: the left one ends up a little left of centre,
    # the right one a little right of it
    assert abs(ba[0] - 0.27) < 0.03 and abs(ba[1] - 0.69) < 0.03, ba
    assert abs(bb[0] - 0.31) < 0.03 and abs(bb[1] - 0.73) < 0.03 and bb[0] > ba[0], bb
    assert bc[0] < 0.2 and bc[1] > 0.8, bc                               # both again
    assert bright(frame(f, 3.5, 640, 360)) == ba, "the switch moves with the cut (source 6 s = output 4 s)"
    # caption colours: red while the first person talks, green for the second
    def cap_col(im):
        low = im[int(im.shape[0] * 0.72):]
        red = ((low[..., 0] > 180) & (low[..., 1] < 90) & (low[..., 2] < 90)).sum()
        green = ((low[..., 1] > 180) & (low[..., 0] < 90) & (low[..., 2] < 90)).sum()
        return red, green
    ra, ga = cap_col(frame(f, 0.6, 640, 360))             # "HELLO" is being said: "FRIENDS" waits in the first person's colour
    rb, gb = cap_col(frame(f, 5.5, 640, 360))             # source 7.5 s: the second person
    assert ra > 30 and ga == 0 and gb > 30 and rb == 0, (ra, ga, rb, gb)
    r = render.render(video=v, audio=None, meta=meta, edl=edl, transcript=tr, preset=tall, style=style, out_dir=tmp / "ot", name="t",
                      effects=json_copy(eff), encoder_preset="ultrafast")
    f = Path(r["files"][0]["path"])
    ta, tb = bright(frame(f, 1.0, 360, 640)), bright(frame(f, 6.0, 360, 640))
    # one face fills the vertical frame both times (the window went from the left person to the right one); without the plan the
    # window would sit in the middle and show the wall between them
    assert ta and tb and ta[0] < 0.2 and ta[1] > 0.8 and tb[0] < 0.2 and tb[1] > 0.8, (ta, tb)
    off = json_copy(eff)
    off["speaker"]["enabled"] = False
    off["fxclips"] = []
    r = render.render(video=v, audio=None, meta=meta, edl=edl, transcript=tr, preset=tall, style=style, out_dir=tmp / "on", name="n",
                      effects=off, encoder_preset="ultrafast")
    tn = bright(frame(Path(r["files"][0]["path"]), 1.0, 360, 640))
    assert tn is None or tn != ta, (tn, ta)
    print(f"render: wide close-ups {ba} → {bb} → wide {bc}; vertical window on the speaker {ta} / {tb} (without the plan: {tn}); caption colours follow ✓")


def json_copy(x):
    import json
    return json.loads(json.dumps(x))


if __name__ == "__main__":
    test_turns_unit()
    test_shots_unit()
    with tempfile.TemporaryDirectory(prefix="vividora-spk-") as d:
        tmp = Path(d)
        test_filters(tmp)
        main = test_scan_real(tmp)
        test_two_cameras(tmp, main)
        test_render(tmp)
    print("ALL PASS")
