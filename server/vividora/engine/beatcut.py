"""Auto beat-edit (CapCut-style "AutoCut") for many clips + one song.

music()   beats, downbeats (bar starts), loudness per beat, drops, and the best
          section of the song when it is longer than the reel
clip()    for every clip: where the good moments are (motion, sharpness, light,
          faces) and where the subject is in each moment (face → else motion/
          edge centroid) — used for auto-reframe to 9:16 / 1:1 / 16:9
plan()    cut lengths follow the song (loud part → ½–1 beat cuts, calm part →
          2–4 beats, always 0.4–2.2 s), each cut gets the best unused moment of
          some clip, an effect on strong beats (flash, zoom punch, shake, RGB
          split, blur-in, glitch) and zoom pulses on the beats inside it.
          Moments that were not used are kept as `alts`, so the creator can put
          any of them back. Every segment can be switched off / changed.
render()  the plan → one video: reframed clips, effects, colour grade, text
          lines on bar starts, the song under it.
"""

from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path

import numpy as np

from . import ffmpeg
from .montage import SR, HOP, _decode, onset_envelope, tempo

FX_STRONG = ["zoom_punch", "flash", "shake", "rgb", "glitch"]
FX_SOFT = ["zoom_punch", "blur_in", "flash"]
FX_ALL = ["cut", "zoom_punch", "flash", "shake", "rgb", "glitch", "blur_in", "zoom_in", "zoom_out", "white_fade", "black_fade"]
FX_LABELS = {"cut": "सीधा cut", "zoom_punch": "Zoom punch", "flash": "Flash", "shake": "Shake", "rgb": "RGB split",
             "glitch": "Glitch", "blur_in": "Blur in", "zoom_in": "धीरे zoom in", "zoom_out": "धीरे zoom out",
             "white_fade": "White fade", "black_fade": "Black fade"}


# ------------------------------------------------------------------ music
def music(path: Path, max_seconds: float = 30.0) -> dict:
    y = _decode(path)
    dur = len(y) / SR
    env = onset_envelope(y)
    bpm = tempo(env)
    fps = SR / HOP
    period = 60 / bpm
    step = period * fps
    best, phase = -1.0, 0.0
    for ph in np.linspace(0, step, 24, endpoint=False):
        idx = np.arange(ph, len(env), step).astype(int)
        s = float(env[idx].sum()) if len(idx) else 0.0
        if s > best:
            best, phase = s, ph
    beats = np.arange(phase / fps, max(dur - 0.05, 0), period)
    if len(beats) < 4:
        beats = np.arange(0, max(dur, 4), 0.5)
    # strength (onset at the beat) and loudness (RMS of the beat)
    strength, energy = [], []
    for i, b in enumerate(beats):
        k = int(b * fps)
        strength.append(float(env[max(0, k - 2):k + 3].max()) if k < len(env) else 0.0)
        a, z = int(b * SR), int((beats[i + 1] if i + 1 < len(beats) else b + period) * SR)
        seg = y[a:z]
        energy.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    energy = np.array(energy)
    if energy.max() > 0:
        lo, hi = np.percentile(energy, 10), np.percentile(energy, 95)
        energy = np.clip((energy - lo) / ((hi - lo) or 1), 0, 1)
    strength = np.array(strength)
    # bar starts: the 4-beat phase with the strongest beats
    bar0 = int(np.argmax([strength[p::4].sum() for p in range(4)])) if len(strength) >= 8 else 0
    # drops: loudness jumps well above the last two bars
    drops = []
    for i in range(8, len(energy)):
        if energy[i] - energy[i - 8:i].mean() > 0.35 and energy[i] > 0.6 and (not drops or i - drops[-1] > 8):
            drops.append(i)
    # best section: loudest window of max_seconds, starting on a bar
    n = len(beats)
    win = max(1, int(round(max_seconds / period)))
    start_i = 0
    if beats[-1] > max_seconds + 2 and n > win:
        best_v = -1.0
        for i in range(bar0, n - win, 4):
            v = float(energy[i:i + win].mean()) + (0.15 if any(i <= d < i + win // 3 for d in drops) else 0)
            if v > best_v:
                best_v, start_i = v, i
    return {"bpm": round(bpm, 1), "period": period, "duration": round(dur, 2), "beats": [round(float(b), 3) for b in beats],
            "strength": [round(float(s), 3) for s in strength], "energy": [round(float(e), 3) for e in energy],
            "bar0": bar0, "drops": drops, "start_i": start_i}


# ------------------------------------------------------------------ clips
def _detector():
    try:
        import cv2
    except ImportError:
        return None, None
    if not hasattr(cv2, "CascadeClassifier"):
        return cv2, None
    p = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    return cv2, (cv2.CascadeClassifier(str(p)) if p.exists() else None)


def _focus(frame: np.ndarray, prev: np.ndarray | None, det) -> tuple[float, float, bool]:
    h, w = frame.shape
    if det is not None:
        faces = det.detectMultiScale(frame, scaleFactor=1.15, minNeighbors=4, minSize=(max(14, w // 20),) * 2)
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            return (x + fw / 2) / w, (y + fh * 0.6) / h, True   # a bit below the face centre keeps head-room
    if prev is not None:
        m = np.abs(frame.astype(np.int16) - prev.astype(np.int16)).astype(np.float32)
    else:  # edges: where the detail is
        f = frame.astype(np.float32)
        m = np.abs(np.diff(f, axis=0, prepend=f[:1])) + np.abs(np.diff(f, axis=1, prepend=f[:, :1]))
    m[m < np.percentile(m, 80)] = 0
    tot = float(m.sum())
    if tot <= 0:
        return 0.5, 0.5, False
    ys, xs = np.indices(m.shape)
    cx, cy = float((m * xs).sum() / tot / w), float((m * ys).sum() / tot / h)
    # pull toward centre — saliency guesses are less certain than faces
    return 0.5 + (cx - 0.5) * 0.7, 0.5 + (cy - 0.5) * 0.7, False


def clip(path: Path, kind: str = "video", fps: float = 4.0, max_seconds: float = 300) -> dict:
    info = ffmpeg.probe(path)
    w, h = int(info.get("width") or 1080), int(info.get("height") or 1920)
    dur = float(info.get("duration") or 0) if kind == "video" else 0.0
    sw = 256
    sh = max(2, int(round(h * sw / max(w, 1) / 2)) * 2)
    cv2, det = _detector()
    if kind == "image" or dur <= 0:
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", f"scale={sw}:{sh}",
                              "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        fr = np.frombuffer(out[:sw * sh], dtype=np.uint8).reshape(sh, sw) if len(out) >= sw * sh else np.zeros((sh, sw), np.uint8)
        fx, fy, face = _focus(fr, None, det)
        return {"kind": "image", "duration": 0, "w": w, "h": h, "t": [0.0], "score": [0.6], "motion": [0.0],
                "fx": [round(fx, 3)], "fy": [round(fy, 3)], "face": [face]}
    cmd = ["ffmpeg", "-v", "error", "-t", f"{min(dur, max_seconds):.2f}", "-i", str(path), "-vf", f"fps={fps},scale={sw}:{sh}",
           "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ts, mot, sharp, bright, fxs, fys, faces = [], [], [], [], [], [], []
    prev = None
    n = 0
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(sw * sh)
        if len(buf) < sw * sh:
            break
        fr = np.frombuffer(buf, dtype=np.uint8).reshape(sh, sw)
        f = fr.astype(np.float32)
        ts.append(n / fps)
        mot.append(float(np.abs(f - prev.astype(np.float32)).mean() / 255) if prev is not None else 0.0)
        lap = f[1:-1, 1:-1] * 4 - f[:-2, 1:-1] - f[2:, 1:-1] - f[1:-1, :-2] - f[1:-1, 2:]
        sharp.append(float(lap.var()))
        bright.append(float(f.mean() / 255))
        # faces every 2nd sample (cheap enough at 256 px)
        if n % 2 == 0 or not fxs:
            fx, fy, face = _focus(fr, prev, det)
        else:
            fx, fy, face = fxs[-1], fys[-1], faces[-1]
        fxs.append(round(fx, 3)); fys.append(round(fy, 3)); faces.append(face)
        prev = fr
        n += 1
    proc.wait()
    if not ts:
        return {"kind": "video", "duration": dur, "w": w, "h": h, "t": [0.0], "score": [0.3], "motion": [0.0], "fx": [.5], "fy": [.5], "face": [False]}
    m = np.array(mot)
    if len(m) > 1:
        m[0] = m[1]
    s = np.array(sharp)
    b = np.array(bright)
    mn = m / (np.percentile(m, 90) or 1)
    sn = s / (np.percentile(s, 90) or 1)
    shake = (m > max(0.12, float(np.percentile(m, 97)))) & (sn < 0.5)       # whip / blur from camera shake
    score = 0.4 * np.clip(mn, 0, 1.3) + 0.4 * np.clip(sn, 0, 1.2) + 0.25 * np.array(faces, float)
    score -= 0.5 * ((b < 0.1) | (b > 0.96)) + 0.4 * shake
    # the first/last half-second of phone clips is usually the hand on the button
    edge = int(fps * 0.5)
    score[:edge] -= 0.25
    if len(score) > edge:
        score[-edge:] -= 0.25
    return {"kind": "video", "duration": round(dur, 2), "w": w, "h": h, "t": [round(x, 2) for x in ts],
            "score": [round(float(x), 3) for x in score], "motion": [round(float(x), 4) for x in mn],
            "fx": fxs, "fy": fys, "face": faces}


def _window(c: dict, a: float, d: float) -> tuple[float, float, float, float, bool]:
    """mean score, mean motion, focus x, focus y, has face for [a, a+d]."""
    t = c["t"]
    if c["kind"] == "image" or len(t) == 1:
        return c["score"][0], 0.0, c["fx"][0], c["fy"][0], bool(c["face"][0])
    step = t[1] - t[0] if len(t) > 1 else 0.25
    i0, i1 = int(a / step), max(int(a / step) + 1, int(math.ceil((a + d) / step)))
    sc = c["score"][i0:i1] or [0.0]
    mo = c["motion"][i0:i1] or [0.0]
    fx = c["fx"][i0:i1] or [.5]
    fy = c["fy"][i0:i1] or [.5]
    fc = c["face"][i0:i1] or [False]
    return float(np.mean(sc)), float(np.mean(mo)), float(np.median(fx)), float(np.median(fy)), any(fc)


# ------------------------------------------------------------------ plan
def plan(mu: dict, clips: list[dict], *, max_seconds: float = 30, pace: str = "auto", effects: str = "auto",
         min_cut: float = 0.4, max_cut: float = 2.2, slowmo: bool = True, seed: int = 7) -> dict:
    """clips: [{id, ...clip() result}]"""
    rnd = random.Random(seed)
    beats, energy, strength = mu["beats"], mu["energy"], mu["strength"]
    period = mu["period"]
    n = len(beats)
    start_i = mu.get("start_i", 0)
    t0 = beats[start_i]
    limit = t0 + max_seconds
    drops = set(mu.get("drops") or [])
    bar0 = mu.get("bar0", 0)
    # 1) cut points on the beat grid
    cuts: list[tuple[float, float, int, float]] = []   # (a, b, beat index, energy)
    i = start_i
    while i < n - 1 and beats[i] < limit - min_cut:
        e = energy[i]
        if pace == "fast":
            nb = 1 if e > 0.3 else 2
        elif pace == "slow":
            nb = 2 if e > 0.7 else 4
        elif pace == "medium":
            nb = 1 if e > 0.75 else 2
        else:
            nb = 1 if e > 0.66 else 2 if e > 0.33 else 4
        # stay inside 0.4–2.2 s
        while nb > 1 and nb * period > max_cut:
            nb //= 2
        while nb * period < min_cut and nb < 8:
            nb *= 2
        # land long cuts on bar starts
        if nb >= 2 and (i - bar0) % 2:
            nb = 1 if period >= min_cut else 2
        j = min(n - 1, i + nb)
        a, b = beats[i], beats[j]
        if b > limit:
            b = limit
            if b - a < min_cut:
                break
        # stutter on a drop: two half-beat cuts of the same moment
        if i in drops and effects != "none" and period / 2 >= 0.22 and nb == 1:
            cuts.append((a, a + period / 2, i, e))
            cuts.append((a + period / 2, b, i, e))
        else:
            cuts.append((a, b, i, e))
        i = j
    if not cuts:
        raise ValueError("music बहुत छोटा है")
    # 2) best unused moment for each cut
    used: dict[str, list[tuple[float, float]]] = {c["id"]: [] for c in clips}
    count: dict[str, int] = {c["id"]: 0 for c in clips}
    segs = []
    last = None
    prev_window = None
    for k, (a, b, bi, e) in enumerate(cuts):
        d = b - a
        stutter_repeat = k > 0 and cuts[k - 1][2] == bi and prev_window is not None
        best = None
        for c in clips:
            cid = c["id"]
            if c["kind"] == "image":
                sc = c["score"][0] - 0.2 * count[cid] - (0.6 if cid == last else 0)
                cand = [(sc, 0.0, 1.0)]
            else:
                speed = 0.5 if (slowmo and e < 0.3 and pace != "fast" and c["duration"] > d * 0.6 + 1) else 1.0
                need = d * speed
                if c["duration"] < need + 0.1:
                    continue
                cand = []
                st = 0.0
                while st + need <= c["duration"] - 0.05:
                    if not any(st < y and st + need > x for x, y in used[cid]):
                        sc, mo, *_ = _window(c, st, need)
                        sc += (0.25 * min(mo, 1.5) if e > 0.6 else -0.1 * max(0, mo - 1))   # loud → movement
                        sc -= 0.12 * count[cid] + (0.6 if cid == last and len(clips) > 1 else 0)
                        cand.append((sc, st, speed))
                    st += 0.25
            for sc, st, speed in cand:
                if best is None or sc > best[0]:
                    best = (sc, cid, st, speed)
        if best is None:   # every moment used — allow re-use
            c = max(clips, key=lambda c: c.get("duration", 0))
            best = (0.0, c["id"], rnd.uniform(0, max(0, c["duration"] - d)) if c["kind"] != "image" else 0.0, 1.0)
        sc, cid, st, speed = best
        if stutter_repeat:
            cid, st, speed = prev_window
        c = next(x for x in clips if x["id"] == cid)
        _, _, fx, fy, face = _window(c, st, d * speed)
        if not stutter_repeat:
            used[cid].append((st, st + d * speed))
            count[cid] += 1
        prev_window = (cid, st, speed)
        last = cid
        # effect at the start of this cut
        if k == 0:
            fxn = "zoom_out" if c["kind"] != "image" else "zoom_in"
        elif effects == "none":
            fxn = "cut"
        elif bi in drops or (strength[bi] > 0.75 and e > 0.6):
            fxn = rnd.choice(FX_STRONG if effects != "subtle" else FX_SOFT)
        elif (bi - bar0) % 4 == 0 and e > 0.35:
            fxn = rnd.choice(FX_SOFT if effects != "strong" else FX_STRONG)
        elif c["kind"] == "image":
            fxn = rnd.choice(["zoom_in", "zoom_out"])
        else:
            fxn = "cut"
        pulses = [round(beats[x] - a, 3) for x in range(bi + 1, n) if a < beats[x] < b - 0.08] if effects != "none" and e > 0.45 else []
        segs.append({"i": k, "clip": cid, "src_in": round(st, 2), "dur": round(d, 3), "speed": speed, "fx": fxn,
                     "pulse": pulses, "focus": [round(fx, 3), round(fy, 3)], "face": face, "score": round(sc, 2),
                     "energy": round(e, 2), "keep": True, "kind": c["kind"]})
    # highlights = best quarter of the chosen moments
    if segs:
        thr = float(np.percentile([s["score"] for s in segs], 75))
        for s in segs:
            s["highlight"] = s["score"] >= thr
    # 3) good moments that were not used → alts (put back by the creator)
    alts = []
    for c in clips:
        if c["kind"] == "image":
            continue
        cands = []
        st = 0.0
        while st + 1.0 <= c["duration"]:
            if not any(st < y and st + 1.0 > x for x, y in used[c["id"]]):
                sc, _, fx, fy, face = _window(c, st, 1.0)
                cands.append((sc, st, fx, fy, face))
            st += 0.5
        cands.sort(reverse=True)
        took: list[float] = []
        for sc, st, fx, fy, face in cands:
            if all(abs(st - x) >= 1.0 for x in took):
                took.append(st)
                alts.append({"clip": c["id"], "src_in": round(st, 2), "score": round(sc, 2), "focus": [round(fx, 3), round(fy, 3)], "face": face})
            if len(took) >= 4:
                break
    alts.sort(key=lambda x: -x["score"])
    return {"bpm": mu["bpm"], "period": round(period, 4), "music_start": round(t0, 3), "segments": segs, "alts": alts[:40],
            "beats": [round(b - t0, 3) for b in beats[start_i:] if b - t0 <= max_seconds + 1],
            "bars": [round(beats[x] - t0, 3) for x in range(start_i, n) if (x - bar0) % 4 == 0 and beats[x] - t0 <= max_seconds + 1],
            "total": round(sum(s["dur"] for s in segs), 3)}


# ------------------------------------------------------------------ render
def _reframe(W: int, H: int, fx: float, fy: float, mode: str, src_w: int, src_h: int, margin: float = 1.0, n: int = 0) -> str:
    """Scale/crop one clip to W×H keeping the subject in frame."""
    if mode == "fit" and abs(src_w / max(src_h, 1) - W / H) > 0.15:
        return (f"split[bg{n}][fg{n}];[bg{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2,eq=brightness=-0.08[bgb{n}];"
                f"[fg{n}]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs{n}];[bgb{n}][fgs{n}]overlay=(W-w)/2:(H-h)/2")
    MW, MH = int(W * margin) // 2 * 2, int(H * margin) // 2 * 2
    if mode == "center":
        fx, fy = 0.5, 0.5
    return (f"scale={MW}:{MH}:force_original_aspect_ratio=increase,"
            f"crop={MW}:{MH}:x='min(max(0\\,{fx:.3f}*iw-{MW}/2)\\,iw-{MW})':y='min(max(0\\,{fy:.3f}*ih-{MH}/2)\\,ih-{MH})'")


def _fx_chain(s: dict, W: int, H: int, fps: int) -> str:
    """Effect + beat pulses for one segment (input already W×H, or W*1.1 for shake)."""
    d = s["dur"]
    fx = s.get("fx") or "cut"
    z = "1"
    if fx == "zoom_punch":
        z = "1+0.22*max(0\\,1-in_time/0.28)"
    elif fx == "zoom_in":
        z = f"1+0.10*in_time/{d:.3f}"
    elif fx == "zoom_out":
        z = f"1.12-0.12*in_time/{d:.3f}"
    pul = s.get("pulse") or []
    if pul:
        z += "+" + "+".join(f"0.05*exp(-pow((in_time-{p:.3f})/0.07\\,2))" for p in pul[:8])
    out = []
    if fx == "shake":
        out.append(f"crop={W}:{H}:x='(iw-ow)/2+if(lt(t\\,0.35)\\,{W * 0.018:.0f}*sin(t*95)\\,0)':y='(ih-oh)/2+if(lt(t\\,0.35)\\,{H * 0.012:.0f}*cos(t*80)\\,0)'")
    if z != "1":
        out.append(f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps}")
    if fx == "flash":
        out.append("fade=t=in:st=0:d=0.16:color=white")
    elif fx == "white_fade":
        out.append("fade=t=in:st=0:d=0.3:color=white")
    elif fx == "black_fade":
        out.append("fade=t=in:st=0:d=0.3:color=black")
    elif fx == "rgb":
        out.append(f"rgbashift=rh=-{W // 70}:bh={W // 70}:enable='lt(t\\,0.18)'")
    elif fx == "glitch":
        out.append(f"rgbashift=rh={W // 50}:gv=-{H // 120}:bh=-{W // 50}:enable='lt(t\\,0.14)',noise=alls=45:allf=t:enable='lt(t\\,0.14)'")
    elif fx == "blur_in":
        out.append("gblur=sigma=22:steps=2:enable='lt(t\\,0.12)'")
    return ",".join(out)


def _grade(look: str | None, mean_energy: float) -> str:
    from .catalog import GRADE_PRESETS, grade_filter
    from .effects import LOOKS
    if not look or look == "none":
        return ""
    if look == "auto":
        look = "grade:" + ("punchy" if mean_energy > 0.55 else "teal_orange" if mean_energy > 0.35 else "warm_film")
    if look.startswith("grade:") and look[6:] in GRADE_PRESETS:
        return grade_filter({k: v for k, v in GRADE_PRESETS[look[6:]].items() if k not in ("label", "cat")})
    return LOOKS.get(look, LOOKS["none"])["filter"]


def render(*, pl: dict, clips: dict[str, dict], music_path: Path, out_dir: Path, name: str, preset: dict,
           texts: list[str] | None = None, look: str = "auto", reframe: str = "smart", font: str = "Poppins",
           text_color: str = "#FFFFFF", text_size: float = 0.07, watermark: Path | None = None,
           fonts_dir: Path | None = None, encoder_preset: str | None = None, on_progress=None) -> dict:
    """clips: id → {path, kind, w, h}"""
    from .captions import _esc, _t, ass_color
    segs = [s for s in pl["segments"] if s.get("keep", True) and s.get("clip") in clips]
    if not segs:
        raise ValueError("कोई segment चालू नहीं है")
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / f".{name}"
    work.mkdir(exist_ok=True)
    W, H = int(preset["width"]), int(preset["height"])
    fps = 30
    inputs: list[str] = []
    chains: list[str] = []
    labels = []
    for n, s in enumerate(segs):
        c = clips[s["clip"]]
        d = float(s["dur"])
        speed = float(s.get("speed") or 1)
        fx, fy = (s.get("focus") or [.5, .5])[:2]
        margin = 1.1 if s.get("fx") == "shake" else 1.0
        if c["kind"] == "image":
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{d + 0.1:.3f}", "-i", str(c["path"])]
            pre = f"[{n}:v]fps={fps},"
        else:
            src = d * speed
            inputs += ["-ss", f"{float(s['src_in']):.3f}", "-t", f"{src + 0.25:.3f}", "-i", str(c["path"])]
            pre = f"[{n}:v]setpts=(PTS-STARTPTS)/{speed},fps={fps},"
        rf = _reframe(W, H, fx, fy, "smart" if margin != 1.0 and reframe == "fit" else reframe,
                      int(c.get("w") or W), int(c.get("h") or H), margin, n)
        chains.append(f"{pre}{rf}[r{n}]")
        src_lbl = f"[r{n}]"
        fxc = _fx_chain(s, W, H, fps)
        chains.append(f"{src_lbl}{fxc + ',' if fxc else ''}scale={W}:{H},trim=duration={d:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[s{n}]")
        labels.append(f"[s{n}]")
    total = sum(float(s["dur"]) for s in segs)
    chains.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[vcat]")
    tail = ""
    g = _grade(look, float(np.mean([s.get("energy", .5) for s in segs])))
    if g:
        tail += g + ","
    lines = [x.strip() for x in (texts or []) if x and x.strip()][:12]
    if lines:
        # each line starts on a bar start of the edited timeline
        starts, acc = [], 0.0
        for s in segs:
            if s.get("fx") not in ("cut",) or not starts:
                starts.append(acc)
            acc += float(s["dur"])
        per = max(1, len(starts) // len(lines))
        base = min(W, H)
        size = round(text_size * base)
        ass = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
               "[V4+ Styles]",
               "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
               "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
               f"Style: M,{font},{size},{ass_color(text_color)},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
               f"{round(0.006 * base, 1)},{round(0.004 * base, 1)},5,{round(0.08 * W)},{round(0.08 * W)},0,1",
               "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        for k, line in enumerate(lines):
            a = starts[min(len(starts) - 1, k * per)]
            b = starts[min(len(starts) - 1, (k + 1) * per)] if k < len(lines) - 1 and (k + 1) * per < len(starts) else total
            if b <= a:
                b = min(total, a + 2)
            ass.append(f"Dialogue: 0,{_t(a)},{_t(b)},M,,0,0,0,,{{\\fad(90,140)\\fscx80\\fscy80\\t(0,180,\\fscx100\\fscy100)}}{_esc(line).replace('|', chr(92) + 'N')}")
        f = work / "beat.ass"
        f.write_text("\n".join(ass) + "\n", encoding="utf-8")
        fonts = fonts_dir or Path(__file__).resolve().parent.parent.parent / "fonts"
        tail += f"ass=filename='{ffmpeg.escape_filter_path(f)}':fontsdir='{ffmpeg.escape_filter_path(fonts)}':shaping=complex,"
    mi = len(segs)
    inputs += ["-ss", f"{float(pl.get('music_start', 0)):.3f}", "-t", f"{total + 0.5:.3f}", "-i", str(music_path)]
    if watermark is not None:
        inputs += ["-i", str(watermark)]
        chains.append(f"[{mi + 1}:v]scale={int(W * 0.14)}:-1,format=rgba,colorchannelmixer=aa=0.75[wm]")
        chains.append(f"[vcat]{tail}format=yuv420p[vt];[vt][wm]overlay=W-w-{int(min(W, H) * 0.035)}:{int(min(W, H) * 0.035)}[v]")
    else:
        chains.append(f"[vcat]{tail}format=yuv420p[v]")
    a_cfg = preset.get("audio", {})
    chains.append(f"[{mi}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, total - 1.0):.3f}:d=1.0,"
                  f"loudnorm=I={a_cfg.get('loudness', -14)}:TP={a_cfg.get('true_peak', -1.5)}:LRA=11,aresample=48000[a]")
    script = work / "filter.txt"
    script.write_text(";\n".join(chains), encoding="utf-8")
    out = out_dir / f"{name}.mp4"
    vcfg = preset.get("video", {})
    ffmpeg.run([*inputs, "-filter_complex_script", str(script), "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", encoder_preset or vcfg.get("preset", "medium"), "-crf", str(vcfg.get("crf", 20)),
                "-g", str(fps * 2), "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)],
               duration=total, on_progress=on_progress, label="beat edit रेंडर")
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    return {"files": [{"kind": "render", "path": out, "mime": "video/mp4", "label": preset["id"],
                       "meta": {"preset": preset["id"], "width": W, "height": H, "duration": round(total, 2), "fps": fps,
                                "montage": True, "bpm": pl.get("bpm"), "segments": len(segs), "effects": {"look": look, "music": True}}}],
            "duration": round(total, 2), "bpm": pl.get("bpm"), "segments": len(segs), "warnings": []}
