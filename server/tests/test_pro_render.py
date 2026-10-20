#!/usr/bin/env python3
"""Pro render-engine tests: every feature renders a real short clip through engine/render.py, then
frames are pulled out and checked numerically; a contact sheet (PNG) per feature is written for a
visual check.

    cd server && python3 tests/test_pro_render.py [--out DIR] [--only name1,name2] [--list]

Test media is generated with ffmpeg (testsrc2 / mandelbrot / colour sources, a face picture,
a beat track) into DIR/media. Results: DIR/results.json, DIR/sheets/*.png, DIR/renders/*.mp4.
Exit code 1 when any check fails.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vividora.engine import colorpro, compose, masks, metadata, musicfit, protools, render, scenes, textedit  # noqa: E402
from vividora.engine import keyframes as K  # noqa: E402
from vividora.engine.trending import TRENDING  # noqa: E402

OUT = Path(os.getenv("VIVIDORA_TEST_OUT", "/tmp/vividora_pro_tests"))
FPS = 30


# ------------------------------------------------------------------ helpers
def ff(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-800:])


def probe(p: Path) -> dict:
    from vividora.engine.ffmpeg import probe as pr
    return pr(p)


def frame(path: Path, t: float) -> np.ndarray:
    info = probe(path)
    w, h = info["width"], info["height"]
    # frame-exact: decode from the start and pick frame n = t × fps (an input -ss can land a frame off)
    n = int(round(t * float(info.get("fps") or FPS)))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})", "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3).astype(np.float32)


def frames(path: Path, start: float, dur: float, scale_w: int = 320) -> np.ndarray:
    info = probe(path)
    w, h = scale_w, int(round(info["height"] * scale_w / info["width"] / 2)) * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(path),
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)


def preset(w: int, h: int, fit: str = "crop", pid: str = "test", crf: int = 20) -> dict:
    return {"id": pid, "label": pid, "width": w, "height": h, "fit": fit, "burn_captions": False,
            "video": {"crf": crf, "preset": "ultrafast", "fps_max": 60}, "audio": {"loudness": -14, "true_peak": -1.5}}


def meta_of(p: Path) -> dict:
    i = probe(p)
    return {"width": i["width"], "height": i["height"], "fps": i.get("fps", FPS), "duration": i["duration"], "has_audio": i["has_audio"]}


def do_render(name: str, video: Path, effects: dict | None = None, *, edl: dict | None = None, pre: dict | None = None,
              transcript: dict | None = None, audio: Path | None = None) -> tuple[Path, float, dict]:
    m = meta_of(video)
    edl = edl or {"duration": m["duration"], "cuts": []}
    t0 = time.time()
    res = render.render(video=video, audio=audio, meta=m, edl=edl, transcript=transcript, preset=pre or preset(640, 360),
                        style=None, out_dir=OUT / "renders", name=name, effects=effects or {}, face_track="off",
                        encoder_preset="ultrafast", burn_captions=False)
    return Path(res["files"][0]["path"]), time.time() - t0, res


def sheet(name: str, items: list[tuple[np.ndarray, str]], cols: int = 5, tw: int = 300) -> Path:
    from PIL import Image, ImageDraw
    thumbs = []
    for img, label in items:
        im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        th = max(1, int(im.height * tw / im.width))
        im = im.resize((tw, th))
        canvas = Image.new("RGB", (tw, th + 18), (20, 20, 20))
        canvas.paste(im, (0, 18))
        ImageDraw.Draw(canvas).text((4, 3), label[:48], fill=(255, 220, 120))
        thumbs.append(canvas)
    rows = math.ceil(len(thumbs) / cols)
    cw, chh = tw, max(t.height for t in thumbs)
    out = Image.new("RGB", (cw * min(cols, len(thumbs)), chh * rows), (0, 0, 0))
    for i, t in enumerate(thumbs):
        out.paste(t, ((i % cols) * cw, (i // cols) * chh))
    p = OUT / "sheets" / f"{name}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    out.save(p)
    return p


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def check(self, label: str, cond: bool, value=None) -> bool:
        self.items.append({"check": label, "ok": bool(cond), "value": value})
        return bool(cond)


def centroid(img: np.ndarray, mask: np.ndarray) -> tuple[float, float] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) < 10:
        return None
    return float(xs.mean()) / img.shape[1], float(ys.mean()) / img.shape[0]


def lap_energy(gray: np.ndarray) -> float:
    g = gray.astype(np.float32)
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(np.mean(np.abs(lap)))


def gray(img: np.ndarray) -> np.ndarray:
    return img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114


def shift(a: np.ndarray, b: np.ndarray) -> float:
    """Global translation between two gray frames (phase correlation), pixels."""
    A, B = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean())
    R = A * np.conj(B)
    r = np.abs(np.fft.ifft2(R / (np.abs(R) + 1e-6)))
    y, x = np.unravel_index(np.argmax(r), r.shape)
    if y > a.shape[0] // 2:
        y -= a.shape[0]
    if x > a.shape[1] // 2:
        x -= a.shape[1]
    return math.hypot(x, y)


# ------------------------------------------------------------------ media
M: dict[str, Path] = {}


def make_media() -> None:
    d = OUT / "media"
    d.mkdir(parents=True, exist_ok=True)

    def mk(name: str, fn) -> None:
        p = d / name
        if not p.exists():
            fn(p)
        M[name.split(".")[0]] = p
    face_png = d / "face.png"
    if not face_png.exists():
        try:
            from skimage import data
            from PIL import Image
            Image.fromarray(data.astronaut()).save(face_png)
        except Exception:  # noqa: BLE001 — a drawn face when scikit-image is not installed
            from PIL import Image, ImageDraw
            im = Image.new("RGB", (512, 512), (40, 60, 110))
            dr = ImageDraw.Draw(im)
            dr.ellipse((150, 90, 360, 370), fill=(224, 172, 140))
            dr.ellipse((200, 190, 240, 215), fill=(40, 30, 30)); dr.ellipse((275, 190, 315, 215), fill=(40, 30, 30))
            dr.arc((215, 260, 300, 320), 20, 160, fill=(150, 60, 60), width=6)
            im.save(face_png)
    speech = "aevalsrc='0.3*sin(2*PI*180*t)*(0.5+0.5*sin(2*PI*3*t))*gt(sin(2*PI*0.7*t)\\,-0.3)':s=48000:d=8"
    mk("face.mp4", lambda p: ff("-loop", "1", "-i", str(face_png), "-f", "lavfi", "-i", speech,
                                "-filter_complex", "[0:v]scale=900:900,pad=1280:900:190:0:color=0x284878,"
                                "zoompan=z='1.05+0.03*sin(on/40)':x='iw/2-(iw/zoom/2)+20*sin(on/23)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30,"
                                "format=yuv420p[v]", "-map", "[v]", "-map", "1:a", "-t", "8", "-c:v", "libx264", "-preset", "veryfast",
                                "-crf", "16", "-c:a", "aac", "-shortest", str(p)))
    mk("noisy.mp4", lambda p: ff("-i", str(M["face"]), "-vf", "noise=alls=28:allf=t", "-c:v", "libx264", "-preset", "veryfast",
                                 "-crf", "14", "-c:a", "copy", str(p)))
    mk("shaky.mp4", lambda p: ff("-loop", "1", "-i", str(face_png), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                                 "-filter_complex", "[0:v]scale=1600:1600,crop=1440:810:80+40*sin(t*7.1)+22*sin(t*13.7)+12*sin(t*29.3):"
                                 "300+36*cos(t*6.3)+20*sin(t*11.9)+10*cos(t*31.1),scale=1280:720,fps=30,format=yuv420p[v]",
                                 "-map", "[v]", "-map", "1:a", "-t", "6", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                                 "-c:a", "aac", str(p)))
    mk("ov.mp4", lambda p: ff("-f", "lavfi", "-i", "mandelbrot=s=640x360:r=30", "-f", "lavfi", "-i", "sine=f=440:r=48000",
                              "-t", "8", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p)))
    mk("timecode.mp4", lambda p: ff("-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=10", "-f", "lavfi", "-i", "sine=f=660:r=48000:d=10",
                                    "-vf", "geq=lum='min(235\\,16+T*40)':cb=128:cr=128,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                                    "-qp", "0", "-c:a", "aac", "-shortest", str(p)))
    mk("gray.mp4", lambda p: ff("-f", "lavfi", "-i", "color=c=0x808080:s=1280x720:r=30:d=8", "-f", "lavfi",
                                "-i", "aevalsrc='0.02*sin(2*PI*100*t)':s=48000:d=8", "-c:v", "libx264", "-preset", "veryfast",
                                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p)))
    mk("black.mp4", lambda p: ff("-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30:d=8", "-c:v", "libx264", "-preset", "veryfast",
                                 "-pix_fmt", "yuv420p", str(p)))
    mk("box.mp4", lambda p: ff("-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30:d=8", "-vf",
                               "drawbox=x=560:y=280:w=160:h=160:color=white:t=fill,format=yuv420p", "-c:v", "libx264",
                               "-preset", "veryfast", str(p)))
    mk("magenta.png", lambda p: ff("-f", "lavfi", "-i", "color=c=0xFF00FF:s=200x200", "-frames:v", "1", str(p)))
    mk("white.png", lambda p: ff("-f", "lavfi", "-i", "color=c=white:s=640x360", "-frames:v", "1", str(p)))
    beat = ("aevalsrc='0.8*sin(2*PI*55*t)*exp(-mod(t\\,0.5)*18)*(1+0.6*lt(mod(t\\,2)\\,0.5))"
            "+0.15*sin(2*PI*(220+110*floor(mod(t\\,8)/2))*t)':s=44100:d=20")
    mk("music.wav", lambda p: ff("-f", "lavfi", "-i", beat, "-af", "afade=t=out:st=18:d=2", str(p)))
    mk("scenes.mp4", lambda p: ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=2", "-f", "lavfi", "-i", "mandelbrot=s=640x360:r=30",
                                  "-f", "lavfi", "-i", "smptebars=s=640x360:r=30:d=2", "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=2",
                                  "-filter_complex", "[1:v]trim=duration=2,setpts=PTS-STARTPTS[m];[0:v][m][2:v][3:v]concat=n=4:v=1:a=0,format=yuv420p[v]",
                                  "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", str(p)))


# ------------------------------------------------------------------ tests
TESTS = {}


def test(fn):
    TESTS[fn.__name__.removeprefix("t_")] = fn
    return fn


@test
def t_overlay_keyframes(c: Checks):
    """Keyframed position / scale / rotation / opacity on an overlay (image) + per-clip grade+effect+colour."""
    kfx = [{"t": 0, "v": 0.2, "ease": "linear"}, {"t": 4, "v": 0.8, "ease": "linear"}]
    items = [
        {"path": str(M["magenta"]), "type": "image", "fit": "free", "scale": 0.12, "x": 0.2, "y": 0.13, "start": 1.0, "end": 5.0,
         "kf": {"x": kfx}},
        {"path": str(M["ov"]), "type": "video", "fit": "free", "scale": 0.22, "x": 0.85, "y": 0.8, "start": 0.5, "end": 5.5,
         "grade_preset": "teal_orange", "stack": [{"id": "vignette"}], "color": {"wheels": {"gain": {"r": 0.3}}}},
        {"path": str(M["white"]), "type": "image", "fit": "free", "scale": 0.2, "x": 0.45, "y": 0.55, "start": 0.5, "end": 5.5,
         "kf": {"scale": [{"t": 0, "v": 1, "ease": "inout"}, {"t": 5, "v": 2}], "rotation": [{"t": 0, "v": 0}, {"t": 5, "v": 90}],
                "opacity": [{"t": 0, "v": 0.2, "ease": "out"}, {"t": 0.4, "v": 1}]}},
    ]
    out, dt, _ = do_render("overlay_keyframes", M["gray"], {"broll": items}, pre=preset(960, 540))
    shots = []
    for t, exp in ((1.5, 0.2 + 0.6 * 0.5 / 4), (3.0, 0.2 + 0.6 * 2 / 4), (4.5, 0.2 + 0.6 * 3.5 / 4)):
        f = frame(out, t)
        m = (f[..., 0] > 180) & (f[..., 2] > 180) & (f[..., 1] < 90)
        cen = centroid(f, m)
        c.check(f"magenta centre x at {t}s ≈ {exp:.3f}", cen is not None and abs(cen[0] - exp) < 0.02, cen and round(cen[0], 4))
        shots.append((f, f"t={t} x≈{exp:.2f}"))
    a0 = frame(out, 1.0); a1 = frame(out, 5.3)
    mag = lambda f: (f[..., 0] > 180) & (f[..., 2] > 180) & (f[..., 1] < 90)  # noqa: E731
    area0 = int(((a0.min(-1) > 200) & ~mag(a0)).sum())
    area1 = int(((a1.min(-1) > 200) & ~mag(a1)).sum())
    exp = (1 + (2 - 1) * (lambda u: u * u * (3 - 2 * u))(4.8 / 5)) ** 2 / (1 + (lambda u: u * u * (3 - 2 * u))(0.5 / 5)) ** 2
    c.check(f"scale kf 1→2 (inout): overlay area grows ≈ {exp:.2f}×", abs(area1 / max(1, area0) - exp) / exp < 0.15,
            [area0, area1, round(area1 / max(1, area0), 2)])
    shots += [(a0, "t=1.0 small/transparent"), (a1, "t=5.3 2x + 90°")]
    sheet("overlay_keyframes", shots, cols=5)
    return {"render_s": round(dt, 2), "file": str(out)}


@test
def t_overlay_speed(c: Checks):
    """Speed ramp (0.5→2×) and constant 0.5× with Speed Warp, trim_in, own audio (atempo)."""
    ramp = [{"t": 0, "v": 0.5, "ease": "linear"}, {"t": 2, "v": 2.0, "ease": "linear"}]
    it1 = {"path": str(M["timecode"]), "type": "video", "fit": "cover", "fade": False, "start": 0.0, "end": 3.0, "trim_in": 1.0,
           "speed_ramp": ramp, "volume": 1.0}
    it2 = {"path": str(M["timecode"]), "type": "video", "fit": "cover", "fade": False, "start": 3.0, "end": 5.5, "trim_in": 2.0,
           "speed": 0.5, "volume": 1.0}
    it3 = {"path": str(M["ov"]), "type": "video", "fit": "cover", "fade": False, "start": 5.5, "end": 8.0, "speed": 0.5, "speed_warp": "fast"}
    out, dt, _ = do_render("overlay_speed", M["gray"], {"broll": [it1, it2, it3]}, pre=preset(640, 360, crf=2))
    pieces = compose.ramp_pieces(it1, 3.0, 9.0)

    def src_at(t_out: float) -> float:
        o = 0.0
        for a, ln, v in pieces:
            if o + ln / v >= t_out:
                return a + (t_out - o) * v
            o += ln / v
        return pieces[-1][0] + pieces[-1][1]
    shots = []
    for t in (0.5, 1.5, 2.5):
        f = frame(out, t)
        y = float(gray(f)[150:210, 280:360].mean())
        meas = y * 219 / 255 / 40 - 1.0
        exp = src_at(t)
        c.check(f"ramp: source time at out {t}s ≈ {exp:.2f}", abs(meas - exp) < 0.09, round(meas, 3))
        shots.append((f, f"ramp t={t} src≈{exp:.2f}"))
    for t in (3.5, 5.0):
        f = frame(out, t)
        meas = float(gray(f)[150:210, 280:360].mean()) * 219 / 255 / 40 - 2.0
        exp = (t - 3.0) * 0.5
        c.check(f"0.5×: source time at out {t}s ≈ {exp:.2f}", abs(meas - exp) < 0.09, round(meas, 3))
        shots.append((f, f"0.5x t={t}"))
    fr = frames(out, 5.7, 2.0, 160)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    dup = float((d < 0.05).mean())
    c.check("speed warp (fast): ≤ 10 % duplicated frames at 0.5×", dup <= 0.1, round(dup, 3))
    vol = subprocess.run(["ffmpeg", "-i", str(out), "-t", "3", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    mv = float(vol.split("mean_volume:")[1].split("dB")[0]) if "mean_volume:" in vol else -99
    c.check("overlay clip's own audio is mixed in (mean > -40 dB)", mv > -40, mv)
    c.check("output duration = base video (8 s)", abs(probe(out)["duration"] - 8.0) < 0.1, probe(out)["duration"])
    sheet("overlay_speed", shots, cols=5)
    return {"render_s": round(dt, 2), "file": str(out)}


@test
def t_blend_modes(c: Checks):
    modes = ["screen", "multiply", "difference", "overlay", "add", "darken"]
    items = [{"path": str(M["ov"]), "type": "video", "fit": "cover", "fade": False, "start": i, "end": i + 1.0, "blend_mode": m}
             for i, m in enumerate(modes)]
    out, dt, _ = do_render("blend_modes", M["gray"], {"broll": items}, pre=preset(640, 360))
    ov = frame(M["ov"], 0.5)
    shots = []
    for i, m in enumerate(modes):
        f = frame(out, i + 0.5)
        lum = gray(f)
        if m == "screen":
            c.check("screen ≥ base (128) everywhere (p5)", np.percentile(lum, 5) >= 124, float(np.percentile(lum, 5)))
        elif m == "multiply":
            c.check("multiply ≤ base (128) everywhere (p95)", np.percentile(lum, 95) <= 132, float(np.percentile(lum, 95)))
        elif m == "difference":
            c.check("difference differs from base and overlay", abs(lum.mean() - 128) > 5, float(lum.mean()))
        elif m == "add":
            c.check("add ≥ base", np.percentile(lum, 5) >= 124, float(np.percentile(lum, 5)))
        elif m == "darken":
            c.check("darken ≤ base", np.percentile(lum, 95) <= 132, float(np.percentile(lum, 95)))
        else:
            c.check(f"{m} renders (not flat)", lum.std() > 3, float(lum.std()))
        shots.append((f, m))
    shots.append((ov, "overlay source"))
    sheet("blend_modes", shots, cols=4)
    return {"render_s": round(dt, 2), "file": str(out)}


@test
def t_masks(c: Checks):
    W = H = None
    seq = [
        ("circle (animated w)", {"shape": "circle", "w": 0.2, "feather": 0.0, "kf": {"w": [{"t": 0, "v": 0.2}, {"t": 1.0, "v": 0.5}]}}),
        ("heart", {"shape": "heart", "w": 0.5, "h": 0.8, "feather": 0.01}),
        ("star", {"shape": "star", "w": 0.5, "h": 0.85, "feather": 0.0}),
        ("rect rounded inverted", {"shape": "rect", "w": 0.5, "h": 0.5, "roundness": 0.4, "invert": True, "feather": 0.0}),
        ("linear wipe 30°", {"shape": "linear", "rotation": 30, "feather": 0.05}),
        ("mirror band", {"shape": "mirror", "h": 0.3, "rotation": -10, "feather": 0.02}),
    ]
    items = [{"path": str(M["white"]), "type": "image", "fit": "cover", "fade": False, "start": i, "end": i + 1.0, "mask": m}
             for i, (_, m) in enumerate(seq)]
    out, dt, _ = do_render("masks", M["black"], {"broll": items}, pre=preset(640, 360))
    shots = []
    for i, (label, m) in enumerate(seq):
        f = gray(frame(out, i + 0.5))
        H, W = f.shape
        cen, corner = f[H // 2, W // 2], f[4, 4]
        if label.startswith("rect"):
            c.check("inverted rect: centre black, corner white", cen < 40 and corner > 215, [float(cen), float(corner)])
        elif label.startswith("linear"):
            c.check("linear: left side white, right side black", f[H // 2, 10] > 215 and f[H // 2, W - 10] < 40,
                    [float(f[H // 2, 10]), float(f[H // 2, W - 10])])
        else:
            c.check(f"{label}: centre white, corner black", cen > 215 and corner < 40, [float(cen), float(corner)])
        shots.append((frame(out, i + 0.5), label))
    a0 = (gray(frame(out, 0.1)) > 128).sum()
    a1 = (gray(frame(out, 0.9)) > 128).sum()
    exp = (0.2 + 0.3 * 0.9) ** 2 / (0.2 + 0.3 * 0.1) ** 2
    c.check(f"animated circle area grows ≈ {exp:.1f}×", abs(a1 / max(1, a0) - exp) / exp < 0.2, round(a1 / max(1, a0), 2))
    r_meas = math.sqrt(a1 / math.pi) / W
    c.check("circle radius at 0.9 s ≈ w/2 of layer width", abs(r_meas - (0.2 + 0.3 * 0.9) / 2) < 0.01, round(r_meas, 4))
    sheet("masks", shots, cols=3)
    return {"render_s": round(dt, 2), "file": str(out)}


@test
def t_main_transform_mask(c: Checks):
    eff = {"transform": {"bg": "black", "kf": {"x": [{"t": 0, "v": 0.0}, {"t": 6, "v": 0.2}],
                                               "rotation": [{"t": 0, "v": 0}, {"t": 6, "v": 45, "ease": "inout"}]}},
           "pro": {"mask": {"shape": "ellipse", "w": 0.9, "h": 0.9, "feather": 0.0, "bg": "#203040"}}}
    out, dt, _ = do_render("main_transform_mask", M["box"], eff, pre=preset(960, 540, "crop"))
    shots = []
    for t in (0.1, 3.0, 5.5):
        f = frame(out, t)
        cen = centroid(f, gray(f) > 200)
        exp = 0.5 + 0.2 * t / 6
        c.check(f"main x keyframe at {t}s ≈ {exp:.3f}", cen is not None and abs(cen[0] - exp) < 0.02, cen and round(cen[0], 4))
        shots.append((f, f"t={t}"))
    f = frame(out, 3.0)
    c.check("mask bg colour #203040 in the corner", np.allclose(f[3, 3], [32, 48, 64], atol=10), f[3, 3].tolist())
    sheet("main_transform_mask", shots, cols=3)
    return {"render_s": round(dt, 2), "file": str(out)}


def _trending_batch(orient: str, c: Checks) -> list:
    pre = preset(1080, 1920, "crop", "yt-short") if orient == "9x16" else preset(1920, 1080, "blur", "yt-long")
    base, _, _ = do_render(f"trending_base_{orient}", M["face"], {}, pre=pre)
    shots = []
    per = 5
    for b in range(0, len(TRENDING), per):
        batch = TRENDING[b:b + per]
        fxc = [{"kind": "effect", "id": e["id"], "start": i * 1.2, "end": i * 1.2 + 1.2, "track": 0} for i, e in enumerate(batch)]
        try:
            out, dt, _ = do_render(f"trending_{orient}_{b // per}", M["face"], {"fxclips": fxc}, pre=pre)
            ok = True
        except Exception as ex:  # noqa: BLE001
            ok = False
            c.check(f"{orient} batch {b // per} renders", False, str(ex)[-400:])
        if not ok:
            continue
        c.check(f"{orient} batch {b // per} renders ({', '.join(e['id'] for e in batch)})", True, round(dt, 1))
        for i, e in enumerate(batch):
            t = i * 1.2 + (0.1 if e["id"] in ("tr_flash",) else 0.7)  # a flash peaks at the clip start
            f, g0 = frame(out, t), frame(base, t)
            diff = float(np.abs(f - g0).mean())
            c.check(f"{orient} {e['id']} visibly changes the picture", diff > 0.8, round(diff, 2))
            shots.append((f, f"{e['id']} Δ{diff:.0f}"))
    return shots


@test
def t_trending_9x16(c: Checks):
    shots = _trending_batch("9x16", c)
    sheet("trending_9x16", shots, cols=9, tw=200)


@test
def t_trending_16x9(c: Checks):
    shots = _trending_batch("16x9", c)
    sheet("trending_16x9", shots, cols=5, tw=300)


@test
def t_effect_param_keyframes(c: Checks):
    fxc = [{"kind": "effect", "id": "blur", "params": {"sigma": 0.5}, "kf": {"sigma": [{"t": 0, "v": 0.5}, {"t": 4, "v": 14}]},
            "start": 1, "end": 5}]
    out, dt, _ = do_render("effect_param_kf", M["face"], {"fxclips": fxc}, pre=preset(640, 360))
    es = [lap_energy(gray(frame(out, t))[::2, ::2].reshape(90, 2, 160, 2).mean(axis=(1, 3))) for t in (1.2, 2.5, 3.8, 4.9)]
    c.check("blur sigma keyframes: sharpness falls over the clip", es[0] > es[1] > es[2] > es[3], [round(x, 2) for x in es])
    sheet("effect_param_kf", [(frame(out, t), f"t={t}") for t in (1.2, 2.5, 3.8, 4.9)], cols=4)
    return {"render_s": round(dt, 2)}


@test
def t_morph_cut(c: Checks):
    edl = {"duration": 8.0, "cuts": [{"id": "c1", "start": 2.0, "end": 2.9, "enabled": True, "reason": "silence"},
                                     {"id": "c2", "start": 4.5, "end": 5.6, "enabled": True, "reason": "silence", "morph": True}]}
    off, _, _ = do_render("morph_off", M["face"], {}, edl=edl, pre=preset(640, 360))
    on, dt, _ = do_render("morph_on", M["face"], {"pro": {"morph_cut": {"enabled": True, "all": True, "frames": 10}}}, edl=edl,
                          pre=preset(640, 360))
    shots, real = [], 0
    for tc in (2.0, 2.0 + (4.5 - 2.9)):
        a, b = frames(off, tc - 0.4, 0.8), frames(on, tc - 0.4, 0.8)
        ja = float(np.abs(np.diff(a, axis=0)).mean(axis=(1, 2)).max())
        jb = float(np.abs(np.diff(b, axis=0)).mean(axis=(1, 2)).max())
        if ja > 15:  # only cuts that really jump can be judged
            real += 1
            c.check(f"cut at {tc:.2f}s: biggest frame-to-frame jump ≥ 50 % smaller with morph", jb < ja * 0.5, [round(ja, 2), round(jb, 2)])
        for dtt in (-0.1, 0.0, 0.1):
            shots.append((frame(on, tc + dtt), f"morph {tc:.2f}{dtt:+.1f}"))
    c.check("at least one visible jump cut was tested", real >= 1, real)
    c.check("duration unchanged by morph", abs(probe(on)["duration"] - probe(off)["duration"]) < 0.05,
            [probe(off)["duration"], probe(on)["duration"]])
    sheet("morph_cut", shots, cols=6)
    return {"render_s": round(dt, 2)}


@test
def t_stabilize(c: Checks):
    off, _, _ = do_render("stab_off", M["shaky"], {}, pre=preset(640, 360))
    on, dt, res = do_render("stab_on", M["shaky"], {"pro": {"stabilize": {"enabled": True, "strength": 0.8}}}, pre=preset(640, 360))
    a, b = frames(off, 0.5, 4.0), frames(on, 0.5, 4.0)
    sa = float(np.mean([shift(a[i], a[i + 1]) for i in range(len(a) - 1)]))
    sb = float(np.mean([shift(b[i], b[i + 1]) for i in range(len(b) - 1)]))
    c.check(f"stabilisation ({protools.can_stabilize()}) reduces frame-to-frame motion ≥ 40 %", sb < sa * 0.6, [round(sa, 2), round(sb, 2)])
    sheet("stabilize", [(frame(off, 2.0), "shaky"), (frame(on, 2.0), "stabilised")], cols=2)
    return {"render_s": round(dt, 2), "mode": protools.can_stabilize(), "notes": res["files"][0]["meta"].get("pro")}


@test
def t_denoise_sharpen(c: Checks):
    base, _, _ = do_render("dn_off", M["noisy"], {}, pre=preset(640, 360))
    h, t1, _ = do_render("dn_hqdn3d", M["noisy"], {"pro": {"denoise": {"enabled": True, "strength": 0.8}}}, pre=preset(640, 360))
    n, t2, _ = do_render("dn_nlmeans", M["noisy"], {"pro": {"denoise": {"enabled": True, "method": "nlmeans", "strength": 0.5}}}, pre=preset(640, 360))
    s, t3, _ = do_render("sharpen_cas", M["face"], {"pro": {"sharpen": {"enabled": True, "amount": 1.0}}}, pre=preset(640, 360))
    p, _, _ = do_render("sharpen_off", M["face"], {}, pre=preset(640, 360))
    clean = gray(frame(p, 3.0))
    e0, e1, e2 = (float(np.abs(gray(frame(x, 3.0)) - clean).mean()) for x in (base, h, n))
    c.check("hqdn3d: error vs the clean picture ≥ 15 % lower", e1 < e0 * 0.85, [round(e0, 2), round(e1, 2)])
    c.check("nlmeans: error vs the clean picture ≥ 30 % lower", e2 < e0 * 0.7, [round(e0, 2), round(e2, 2)])
    s0, s1 = lap_energy(clean), lap_energy(gray(frame(s, 3.0)))
    c.check("cas sharpen raises detail energy", s1 > s0 * 1.1, [round(s0, 2), round(s1, 2)])
    sheet("denoise_sharpen", [(frame(base, 3.0), "noisy"), (frame(h, 3.0), "hqdn3d"), (frame(n, 3.0), "nlmeans"),
                              (frame(p, 3.0), "plain"), (frame(s, 3.0), "cas 1.0")], cols=5)
    return {"render_s": {"hqdn3d": round(t1, 2), "nlmeans": round(t2, 2), "cas": round(t3, 2)}}


@test
def t_face_refine(c: Checks):
    boxes = protools.detect_faces(M["face"], 6.0)
    c.check("a face is found (Haar or skin fallback)", len(boxes) > 5, len(boxes))
    off, _, _ = do_render("face_off", M["face"], {}, pre=preset(1280, 720))
    on, dt, res = do_render("face_on", M["face"], {"pro": {"face_refine": {"enabled": True, "strength": 0.8, "brighten": 0.4, "eyes": 0.5}}},
                            pre=preset(1280, 720))
    t = 3.0
    a, b = frame(off, t), frame(on, t)
    bx = min(boxes, key=lambda x: abs(x[0] - t))
    H, W = a.shape[:2]
    x0, x1 = int((bx[1] - bx[3] * 0.3) * W), int((bx[1] + bx[3] * 0.3) * W)
    y0, y1 = int((bx[2] - bx[4] * 0.1) * H), int((bx[2] + bx[4] * 0.35) * H)
    ea, eb = lap_energy(gray(a[y0:y1, x0:x1])), lap_energy(gray(b[y0:y1, x0:x1]))
    c.check("skin inside the face is smoother", eb < ea * 0.9, [round(ea, 2), round(eb, 2)])
    corner = float(np.abs(a[:80, :80] - b[:80, :80]).mean())
    c.check("background outside the face unchanged (Δ < 2)", corner < 2, round(corner, 2))
    sheet("face_refine", [(a, "off"), (b, "refined"), (a[y0:y1, x0:x1], "skin off"), (b[y0:y1, x0:x1], "skin on")], cols=4)
    return {"render_s": round(dt, 2), "faces": len(boxes), "notes": res["files"][0]["meta"].get("pro")}


@test
def t_speed_warp_main(c: Checks):
    edl = {"duration": 8.0, "cuts": [], "speed": [{"start": 1.0, "end": 3.0, "rate": 0.5}]}
    off, _, _ = do_render("warp_off", M["ov"], {}, edl=edl, pre=preset(640, 360, crf=2))
    on, dt, _ = do_render("warp_balanced", M["ov"], {"pro": {"speed_warp": "balanced"}}, edl=edl, pre=preset(640, 360, crf=2))
    da = np.abs(np.diff(frames(off, 1.2, 3.0, 160), axis=0)).mean(axis=(1, 2))
    db = np.abs(np.diff(frames(on, 1.2, 3.0, 160), axis=0)).mean(axis=(1, 2))
    ra, rb = float((da < 0.15).mean()), float((db < 0.15).mean())
    c.check("without warp ~half the slowed frames are repeats", ra > 0.35, round(ra, 3))
    c.check("Speed Warp (balanced): ≤ 10 % repeats", rb <= 0.1, round(rb, 3))
    c.check("duration 10 s (2 s at 0.5× → 4 s)", abs(probe(on)["duration"] - 10.0) < 0.1, probe(on)["duration"])
    sheet("speed_warp", [(frame(off, 2.0), "off t=2.0"), (frame(off, 2.0 + 1 / 30), "off +1f"), (frame(on, 2.0), "warp t=2.0"),
                         (frame(on, 2.0 + 1 / 30), "warp +1f")], cols=4)
    return {"render_s": round(dt, 2)}


@test
def t_color(c: Checks):
    ref_img = OUT / "media" / "ref_warm.png"
    ff("-ss", "2", "-i", str(M["face"]), "-frames:v", "1", "-vf", "colorbalance=rs=0.3:gs=0.05:bs=-0.3,eq=brightness=0.06", str(ref_img))
    src = colorpro.frame_rgb(M["face"], 3.0)
    ref = colorpro.frame_rgb(ref_img)
    mt = colorpro.match(src, ref)
    specs = {
        "plain": {},
        "wheels gain R+": {"wheels": {"gain": {"r": 0.6}, "lift": {"b": 0.2}}},
        "curves S": {"curves": {"master": [[0, 0], [0.25, 0.15], [0.75, 0.88], [1, 1]]}},
        "HSL blue→sat 0": {"hsl": [{"hue": 215, "range": 60, "softness": 20, "sat": -1}]},
        "match → warm ref": mt,
    }
    outs = {}
    for k, sp in specs.items():
        o, dt, _ = do_render("color_" + k.split()[0], M["face"], {"pro": {"color": sp}} if sp else {}, pre=preset(640, 360))
        outs[k] = frame(o, 3.0)
    p = outs["plain"]
    c.check("gain R raises red", outs["wheels gain R+"][..., 0].mean() > p[..., 0].mean() + 10,
            [round(float(p[..., 0].mean()), 1), round(float(outs["wheels gain R+"][..., 0].mean()), 1)])
    c.check("S-curve raises contrast", gray(outs["curves S"]).std() > gray(p).std() * 1.08,
            [round(float(gray(p).std()), 1), round(float(gray(outs["curves S"]).std()), 1)])
    bg = (p[..., 2] > p[..., 0] + 40)
    sat = lambda im: (im.max(-1) - im.min(-1))  # noqa: E731
    c.check("HSL: blue background desaturated", sat(outs["HSL blue→sat 0"])[bg].mean() < sat(p)[bg].mean() * 0.4,
            [round(float(sat(p)[bg].mean()), 1), round(float(sat(outs["HSL blue→sat 0"])[bg].mean()), 1)])
    lab = lambda im: colorpro.rgb_to_lab(im.reshape(-1, 3) / 255.0).mean(0)  # noqa: E731
    r_lab, p_lab, m_lab = lab(ref * 255), lab(p), lab(outs["match → warm ref"])
    d0, d1 = float(np.linalg.norm(p_lab - r_lab)), float(np.linalg.norm(m_lab - r_lab))
    c.check("colour match moves the clip ≥ 60 % closer to the reference (Lab mean)", d1 < d0 * 0.4, [round(d0, 2), round(d1, 2)])
    sheet("color", [(v, k) for k, v in outs.items()] + [(ref * 255, "reference")], cols=6, tw=240)
    return {"match_params": mt}


@test
def t_music_fit(c: Checks):
    res = {}
    for target in (13.3, 31.0):
        pl = musicfit.plan(M["music"], target)
        out = musicfit.render(M["music"], pl, OUT / "renders" / f"music_fit_{target}.wav")
        d = probe(out)["duration"]
        c.check(f"remix to {target}s → length within 0.08 s", abs(d - target) < 0.08, round(d, 3))
        from vividora.engine.beatcut import music as beat_music
        bars = musicfit._bars(beat_music(M["music"], max_seconds=40))
        joins = [p_[0] for p_ in pl["pieces"][1:]] + [p_[1] for p_ in pl["pieces"][:-1]]
        c.check(f"remix to {target}s cuts / joins only on detected bar starts ({pl['bpm']} BPM)",
                all(min(abs(j - b) for b in bars) < 0.01 for j in joins), pl["pieces"])
        res[str(target)] = pl
    out, dt, _ = do_render("music_fit_render", M["face"], {"music": {"path": str(M["music"]), "fit": True, "volume": 0.3, "duck": False}},
                           pre=preset(640, 360))
    c.check("render with music.fit has audio", probe(out)["has_audio"], True)
    return {"plans": res}


@test
def t_scenes(c: Checks):
    sc = scenes.detect(M["scenes"], 0.3)
    ts = [s["t"] for s in sc]
    c.check("scene changes at ≈ 2, 4, 6 s", len(ts) == 3 and all(abs(a - b) < 0.1 for a, b in zip(ts, [2, 4, 6])), sc)
    return {"scenes": sc}


@test
def t_textedit(c: Checks):
    W = [("नमस्ते", 0.2, 0.6), ("अं", 0.8, 1.0), ("आज", 1.1, 1.4), ("हम", 1.5, 1.7), ("बात", 1.8, 2.1), ("करेंगे", 2.2, 2.7),
         ("एक", 4.5, 4.7), ("नई", 4.8, 5.0), ("चीज़", 5.1, 5.5), ("उम", 5.7, 5.9), ("के", 6.0, 6.2), ("बारे", 6.3, 6.6), ("में", 6.7, 7.0)]
    tr = {"segments": [{"start": 0.2, "end": 7.0, "text": " ".join(w for w, _, _ in W),
                        "words": [{"w": w, "start": a, "end": b} for w, a, b in W]}]}
    manual = {"id": "c9", "start": 7.2, "end": 7.6, "enabled": True, "reason": "manual"}
    edl = {"duration": 8.0, "cuts": [manual]}
    r = textedit.apply(edl, tr, {"delete": [4], "fillers": True, "silences_over": 1.0})
    rw = set(r["removed_words"])
    c.check("deleted word + fillers are removed", {1, 4, 9} <= rw and not ({0, 2, 3, 5, 6} & rw), sorted(rw))
    c.check("silence 2.7–4.5 cut, keeping breathing room", any(cu["reason"] == "silence" and cu["start"] <= 2.9 and cu["end"] >= 4.3
                                                                for cu in r["edl"]["cuts"]), r["edl"]["cuts"])
    c.check("manual cut untouched", manual in r["edl"]["cuts"], True)
    r2 = textedit.apply(r["edl"], tr, {"restore": [4]})
    c.check("restore brings the word back", 4 not in r2["removed_words"] and 1 in r2["removed_words"], r2["removed_words"])
    r3 = textedit.apply(edl, tr, {"keep_text": "नमस्ते आज हम बात करेंगे एक नई चीज़ के बारे में"})
    c.check("keep_text deletes the words not in the text", set(r3["removed_words"]) == {1, 9}, r3["removed_words"])
    out, dt, _ = do_render("textedit", M["face"], {}, edl=r["edl"], pre=preset(640, 360), transcript=tr)
    d = probe(out)["duration"]
    c.check("render length = stats.final_seconds", abs(d - r["edl"]["stats"]["final_seconds"]) < 0.1, [d, r["edl"]["stats"]["final_seconds"]])
    return {"cuts": r["edl"]["cuts"], "stats": r["edl"]["stats"]}


@test
def t_markers_chapters(c: Checks):
    proj = {"meta": {"duration": 600}, "edl": {"duration": 600, "cuts": []}, "transcript": {"segments": []},
            "settings": {"render": {"markers": [{"t": 3, "label": "शुरुआत", "kind": "chapter"}, {"t": 95, "label": "Setup", "kind": "chapter"},
                                                {"t": 100, "label": "too close", "kind": "chapter"}, {"t": 300, "label": "Result", "kind": "chapter"},
                                                {"t": 200, "label": "fix audio", "kind": "todo"}]}}}
    ch = metadata.chapters(proj)
    c.check("chapters from markers: 00:00 first, ≥10 s apart, notes ignored",
            [t for t, _ in ch] == [0.0, 95, 300] and ch[0][1] == "शुरुआत", ch)
    desc = metadata.finalize({"description": "hello"}, proj, "youtube", "yt-long")["description"]
    c.check("chapters land in the YouTube description", "00:00 शुरुआत" in desc and "05:00 Result" in desc, desc)
    return {"chapters": ch}


@test
def t_legacy_unchanged(c: Checks):
    it = {"path": str(M["ov"]), "type": "video", "fit": "pip", "pos": "tr", "start": 1, "end": 4}
    c.check("legacy overlay is not routed to the pro compositor", not compose.is_pro(it), False)
    out, dt, res = do_render("legacy", M["face"], {"broll": [it], "grade": {"contrast": 0.2}, "stack": [{"id": "vignette"}],
                                                   "titles": [{"start": 0.5, "end": 3, "text": "नमस्ते", "pos": "top"}]},
                             pre=preset(640, 360))
    c.check("legacy render ok", out.exists() and probe(out)["duration"] > 7.9, probe(out)["duration"])
    c.check("no pro notes on a plain render", res["files"][0]["meta"].get("pro") is None, res["files"][0]["meta"].get("pro"))
    return {"render_s": round(dt, 2)}


@test
def t_catalogs(c: Checks):
    from vividora.engine import procatalog
    j = procatalog.pro_json()
    json.dumps(j)
    c.check("25 trending effects in the catalog", len(j["trending"]) == 25, len(j["trending"]))
    c.check("catalog lists masks / blend modes / eases / tools",
            all(k in j for k in ("masks", "blend_modes", "keyframe_eases", "tools", "defaults")), list(j))
    c.check("keyframe expression matches python sampling",
            abs(K.sample(K.normalize([{"t": 0, "v": 0, "ease": "inout"}, {"t": 2, "v": 10}]), 0.5) - 1.5625) < 1e-6, True)
    arr = masks.draw(masks.clean({"shape": "heart", "w": 0.6, "h": 0.8}), 320, 320)
    c.check("heart mask non-empty", 0.15 < arr.mean() < 0.6, round(float(arr.mean()), 3))


# ------------------------------------------------------------------ main
def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(TESTS))
        return 0
    OUT = Path(a.out)
    OUT.mkdir(parents=True, exist_ok=True)
    make_media()
    only = [x for x in a.only.split(",") if x]
    results, failed = {}, 0
    for name, fn in TESTS.items():
        if only and name not in only:
            continue
        c = Checks()
        t0 = time.time()
        try:
            info = fn(c) or {}
            err = None
        except Exception:  # noqa: BLE001
            info, err = {}, traceback.format_exc()[-2500:]
        ok = err is None and all(i["ok"] for i in c.items)
        failed += 0 if ok else 1
        results[name] = {"ok": ok, "seconds": round(time.time() - t0, 1), "checks": c.items, "info": info, "error": err}
        print(f"{'PASS' if ok else 'FAIL'} {name} ({results[name]['seconds']} s)")
        for i in c.items:
            if not i["ok"] or os.getenv("VERBOSE"):
                print(f"   {'ok ' if i['ok'] else 'BAD'} {i['check']}: {str(i['value'])[:300]}")
        if err:
            print(err)
    prev = {}
    rp = OUT / "results.json"
    if rp.exists() and only:
        try:
            prev = json.loads(rp.read_text())
        except ValueError:
            prev = {}
    rp.write_text(json.dumps({**prev, **results}, ensure_ascii=False, indent=1, default=str))
    print(f"\n{len(results) - failed}/{len(results)} passed · sheets in {OUT / 'sheets'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
