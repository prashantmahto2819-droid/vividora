"""Who is speaking? → camera plan for a podcast / interview (no GPU, no model download).

One wide shot with two (or three) people, or two cameras recorded at the same time:

* `scan`    — one pass over the video at 5 fps (480 px, gray): the faces that stay in the picture (OpenCV Haar,
              looked for once a second) and, for every face, how much its MOUTH area moves compared to its forehead
              (a nodding head moves both; a talking one moves the mouth).
* `turns`   — who has the floor, second by second: the face whose mouth moves most while words are spoken, with
              hysteresis (a short "हाँ" from the listener does not flip the camera) and the switch snapped to the
              start of a word.
* `shots`   — the camera plan: close-up of the speaker, a wide shot at the start and inside long answers.
* `sync_offset` / `with_camera` — a second camera file: found by its sound (cross-correlation of the loudness
              curve), then its face competes with the faces of the main camera.

Everything is in SOURCE seconds of the main video. The editor turns close-ups into "Close-up" effect clips and
second-camera shots into overlay clips (so every one of them can be moved, trimmed or deleted on the timeline),
and vertical renders follow the active speaker (render.py, `effects.speaker`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SAMPLE_W = 480
FPS = 5.0
DETECT_EVERY = 5          # frames → faces are looked for once a second
CELL = 8                  # motion is kept on an 8 px grid (36 MB for an hour instead of 2 GB of frames)
MAX_FACES = 3


def _haar():
    try:
        import cv2  # noqa: WPS433
    except ImportError:
        return None
    base = Path(cv2.data.haarcascades)
    front, prof = base / "haarcascade_frontalface_default.xml", base / "haarcascade_profileface.xml"
    if not front.exists():
        return None
    f = cv2.CascadeClassifier(str(front))
    p = cv2.CascadeClassifier(str(prof)) if prof.exists() else None

    def detect(frame):
        ms = max(20, frame.shape[1] // 22)
        got = [tuple(int(v) for v in r) for r in f.detectMultiScale(frame, scaleFactor=1.12, minNeighbors=5, minSize=(ms, ms))]
        if len(got) < 2 and p is not None:      # people in a podcast look at each other: 3/4 and side faces
            w = frame.shape[1]
            got += [tuple(int(v) for v in r) for r in p.detectMultiScale(frame, scaleFactor=1.12, minNeighbors=5, minSize=(ms, ms))]
            got += [(w - int(x) - int(bw), int(y), int(bw), int(bh))
                    for x, y, bw, bh in p.detectMultiScale(frame[:, ::-1].copy(), scaleFactor=1.12, minNeighbors=5, minSize=(ms, ms))]
        return got
    return detect


def _cluster(dets: list[tuple], n_looks: int) -> list[dict]:
    """Detections [(frame, cx, cy, w, h)] → the faces that stay: [{x, y, w, h, seen, at: [frames], box: [...]}], left → right."""
    import numpy as np
    if not dets:
        return []
    dets = sorted(dets, key=lambda d: d[1])
    med_w = float(np.median([d[3] for d in dets]))
    gap = max(0.07, 0.6 * med_w)
    groups, cur = [], [dets[0]]
    for d in dets[1:]:
        if d[1] - cur[-1][1] > gap:
            groups.append(cur)
            cur = [d]
        else:
            cur.append(d)
    groups.append(cur)
    faces = []
    for g in groups:
        frames = sorted({d[0] for d in g})
        seen = len(frames) / max(1, n_looks)
        if len(frames) < 3 or seen < 0.12:
            continue                      # a face on a poster / a false hit now and then
        g = sorted(g, key=lambda d: d[0])
        arr = np.array([d[1:] for d in g], dtype=np.float32)
        faces.append({"x": float(np.median(arr[:, 0])), "y": float(np.median(arr[:, 1])), "w": float(np.median(arr[:, 2])),
                      "h": float(np.median(arr[:, 3])), "seen": round(seen, 3), "at": np.array([d[0] for d in g]), "box": arr})
    if not faces:
        return []
    big = max(f["h"] for f in faces)
    faces = [f for f in faces if f["h"] >= 0.45 * big]         # people far in the background are not in the talk
    faces = sorted(faces, key=lambda f: -f["seen"])[:MAX_FACES]
    return sorted(faces, key=lambda f: f["x"])


def scan(video: Path, duration: float, width: int, height: int, *, max_seconds: float = 7200,
         detect=None, progress=None) -> dict:
    """→ {fps, n, faces: [{x, y, w, h, seen}], scores: float32 array (n, faces)}. `detect(gray_frame) → [(x, y, w, h)]`
    can be given (tests); the default is OpenCV's Haar cascades. No OpenCV / no face → faces = []."""
    import numpy as np

    from . import ffmpeg as _ff
    detect = detect or _haar()
    if detect is None or duration <= 0 or width <= 0 or height <= 0:
        return {"fps": FPS, "n": 0, "faces": [], "scores": np.zeros((0, 0), dtype=np.float32)}
    sw = SAMPLE_W
    sh = max(2, int(round(height * sw / width / 2)) * 2)
    gw, gh = sw // CELL, sh // CELL
    span = min(duration, max_seconds)
    cmd = ["ffmpeg", "-v", "error", "-i", str(video), "-t", f"{span:.2f}", "-an",
           "-vf", f"fps={FPS:.3f},scale={sw}:{sh}", "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    _ff.track(proc)
    total = max(1, int(span * FPS))
    grids, dets, looks, prev, n = [], [], 0, None, 0
    size = sw * sh
    assert proc.stdout is not None
    try:
        while True:
            _ff.check_cancel()
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(sh, sw)
            f16 = frame.astype(np.int16)
            if prev is None:
                grids.append(np.zeros((gh, gw), dtype=np.uint8))
            else:
                d = np.abs(f16 - prev)[:gh * CELL, :gw * CELL].reshape(gh, CELL, gw, CELL).mean(axis=(1, 3))
                grids.append(np.clip(d * 4, 0, 255).astype(np.uint8))
            prev = f16
            if n % DETECT_EVERY == 0:
                looks += 1
                for x, y, bw, bh in detect(frame):
                    dets.append((n, (x + bw / 2) / sw, (y + bh / 2) / sh, bw / sw, bh / sh))
                if progress and looks % 20 == 0:
                    progress(min(0.99, n / total))
            n += 1
    finally:
        proc.stdout.close()
        proc.wait()
        _ff.untrack(proc)
    faces = _cluster(dets, looks)
    scores = np.zeros((n, len(faces)), dtype=np.float32)
    if n and faces:
        g = np.stack(grids).astype(np.float32) / 4.0
        for k, f in enumerate(faces):
            idx = np.clip(np.searchsorted(f["at"], np.arange(n)), 0, len(f["at"]) - 1)
            left = np.clip(idx - 1, 0, len(f["at"]) - 1)
            idx = np.where(np.abs(f["at"][left] - np.arange(n)) <= np.abs(f["at"][idx] - np.arange(n)), left, idx)
            last = None
            for i in range(n):
                b = idx[i]
                if b != last:
                    cx, cy, bw, bh = (float(v) for v in f["box"][b])
                    x0, x1 = int((cx - 0.30 * bw) * gw), int((cx + 0.30 * bw) * gw) + 1
                    my0, my1 = int((cy + 0.08 * bh) * gh), int((cy + 0.55 * bh) * gh) + 1
                    uy0, uy1 = int((cy - 0.45 * bh) * gh), int((cy - 0.05 * bh) * gh) + 1
                    x0, x1 = max(0, min(gw - 1, x0)), max(1, min(gw, x1))
                    my0, my1 = max(0, min(gh - 1, my0)), max(1, min(gh, my1))
                    uy0, uy1 = max(0, min(gh - 1, uy0)), max(1, min(gh, uy1))
                    last = b
                m = g[i, my0:my1, x0:x1]
                u = g[i, uy0:uy1, x0:x1]
                scores[i, k] = max(0.0, float(m.mean() if m.size else 0) - 0.7 * float(u.mean() if u.size else 0))
    return {"fps": FPS, "n": n, "faces": [{k: round(float(v), 4) for k, v in f.items() if k in ("x", "y", "w", "h", "seen")} for f in faces],
            "scores": scores}


def _speech_mask(words: list[dict], n: int, fps: float, pad: float = 0.15):
    import numpy as np
    if not words:
        return np.ones(n, dtype=bool)
    m = np.zeros(n, dtype=bool)
    for w in words:
        try:
            a, b = float(w["start"]) - pad, float(w["end"]) + pad
        except (KeyError, TypeError, ValueError):
            continue
        m[max(0, int(a * fps)):max(0, min(n, int(b * fps) + 1))] = True
    return m


def _snap(t: float, words: list[dict], reach: float = 0.7) -> float:
    """The camera changes when a word starts (best: the first word after a breath), never in the middle of one."""
    best, best_d = None, reach
    prev_end = -9.0
    for w in words:
        try:
            s, e = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if s > t + reach:
            break
        d = abs(s - t) - (0.25 if s - prev_end >= 0.12 else 0.0)
        if abs(s - t) <= reach and d < best_d:
            best, best_d = s, d
        prev_end = e
    return t if best is None else max(0.0, best - 0.06)


def turns(scores, fps: float, words: list[dict] | None = None, *, min_turn: float = 1.8, lead: float = 1.3,
          hold: float = 0.8, norm: bool = False, duration: float | None = None) -> list[dict]:
    """scores (n, k) → [{start, end, who}] covering 0 … duration. One column → nobody to switch between → []."""
    import numpy as np
    sc = np.asarray(scores, dtype=np.float32)
    if sc.ndim != 2 or sc.shape[1] < 2 or sc.shape[0] < 3:
        return []
    n, k = sc.shape
    words = sorted([w for w in (words or []) if isinstance(w, dict) and "start" in w and "end" in w], key=lambda w: float(w["start"]))
    win = max(1, int(round(1.2 * fps)))
    ker = np.ones(win, dtype=np.float32) / win
    sm = np.stack([np.convolve(sc[:, j], ker, mode="same") for j in range(k)], axis=1)
    if norm:      # two cameras frame their person differently: compare each face with its own lively moments
        sm = sm / (np.percentile(sm, 90, axis=0) + 1e-6)
    speech = _speech_mask(words, n, fps)
    top = sm.max(axis=1)
    floor = 0.25 * float(np.median(top[speech])) if speech.any() else 0.0
    need = max(1, int(round(hold * fps)))
    marks: list[list] = []
    cur, run_j, run_start = None, None, 0
    for i in range(n):
        if not speech[i]:
            run_j = None
            continue
        j = int(np.argmax(sm[i]))
        if cur is None:
            cur = j
            marks.append([0.0, j])
            continue
        if j != cur and sm[i, j] > lead * sm[i, cur] + floor:
            if run_j != j:
                run_j, run_start = j, i
            if i - run_start + 1 >= need:
                cur = j
                marks.append([_snap(max(0.0, run_start / fps - 0.3), words), j])
                run_j = None
        else:
            run_j = None
    total = float(duration) if duration else n / fps
    if not marks:
        return []
    out: list[dict] = []
    for i, (t, j) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else total
        if out and (end - t < min_turn or t <= out[-1]["start"]):
            out[-1]["end"] = end              # a short interjection: the camera stays where it is
            continue
        if out and out[-1]["who"] == j:
            out[-1]["end"] = end
            continue
        if out:
            out[-1]["end"] = t
        out.append({"start": round(t, 3), "end": round(end, 3), "who": j})
    merged: list[dict] = []
    for t in out:
        if merged and merged[-1]["who"] == t["who"]:
            merged[-1]["end"] = t["end"]
        else:
            merged.append(dict(t))
    for t in merged:
        t["end"] = round(float(t["end"]), 3)
    return merged


def closeup(face: dict, zoom: float = 1.0) -> dict:
    """The close-up of one face: {zoom, x, y} for the `closeup` effect (x / y = where the window sits, 0 … 1)."""
    z = max(1.15, min(3.0, max(1.25, min(2.4, 0.36 / max(0.05, float(face["h"])))) * max(0.5, min(2.0, float(zoom)))))
    cx, cy = float(face["x"]), float(face["y"]) + 0.05 * float(face["h"])
    slack = 1.0 - 1.0 / z
    x = (cx - 0.5 / z) / slack
    y = (cy - 0.42 / z) / slack                # the face a little above the middle, room for the shoulders
    return {"zoom": round(z, 3), "x": round(max(0.0, min(1.0, x)), 4), "y": round(max(0.0, min(1.0, y)), 4)}


def shots(turn_list: list[dict], faces: list[dict], duration: float, *, style: str = "mix", zoom: float = 1.0,
          cams: dict | None = None, main_close: bool = True) -> list[dict]:
    """Turns → shots [{start, end, who, shot: close | wide | cam, zoom?, x?, y?, cx}].
    style: mix (close-ups + a wide shot at the start and inside long answers) | close (always the speaker) |
    wide_long (wide by default, close-up only in answers longer than 6 s).
    `cams` {who: {…}} marks the candidates that are another camera (their shot is `cam`, no zoom).
    main_close=False: the main camera already shows one person only — its shots stay as they are (`wide`)."""
    cams = cams or {}
    out: list[dict] = []

    def add(a: float, b: float, who: int, kind: str) -> None:
        if b - a < 0.2:
            return
        s = {"start": round(a, 3), "end": round(b, 3), "who": who, "shot": kind}
        if who in cams:
            if kind != "wide":
                s["shot"] = "cam"
        elif who < len(faces):
            s["cx"] = faces[who]["x"]
            if kind == "close" and main_close:
                s.update(closeup(faces[who], zoom))
            else:
                s["shot"] = "wide"
        if out and out[-1]["who"] == who and out[-1]["shot"] == s["shot"]:
            out[-1]["end"] = s["end"]
        else:
            out.append(s)
    for i, t in enumerate(turn_list):
        a, b, who = float(t["start"]), float(t["end"]), int(t["who"])
        own_cam = who in cams
        if style == "close" or own_cam and style != "mix":
            add(a, b, who, "close")
            continue
        if style == "wide_long":
            if b - a >= 6.0:
                add(a, a + 1.2, who, "wide")
                add(a + 1.2, b, who, "close")
            else:
                add(a, b, who, "wide")
            continue
        if i == 0 and b - a >= 4.0:
            add(a, a + 2.5, who, "wide")      # the room first, then the person
            a += 2.5
        while b - a >= 18.0:
            add(a, a + 10.0, who, "close")
            add(a + 10.0, a + 13.5, who, "wide")
            a += 13.5
        add(a, b, who, "close")
    if out:
        out[0]["start"] = 0.0
        out[-1]["end"] = round(max(out[-1]["end"], float(duration or out[-1]["end"])), 3)
    return out


# ---------------------------------------------------------------- second camera


def _envelope(path: Path, seconds: float, rate: int = 100):
    """Loudness curve at `rate` Hz (rises only: the starts of sounds line two recordings up best)."""
    import numpy as np
    sr = 8000
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-t", f"{seconds:.1f}", "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=600).stdout
    a = np.frombuffer(raw[:len(raw) // 2 * 2], dtype=np.int16).astype(np.float32)
    hop = sr // rate
    if len(a) < hop * 20:
        return np.zeros(0, dtype=np.float32)
    env = np.log1p(np.abs(a[:len(a) // hop * hop]).reshape(-1, hop).mean(axis=1))
    on = np.maximum(0.0, np.diff(env, prepend=env[0]))
    return (on - on.mean()) / (on.std() + 1e-6)


def sync_offset(main: Path, other: Path, *, seconds: float = 900, rate: int = 100) -> tuple[float, float]:
    """→ (offset, confidence): what is heard at second t of `main` is at second t + offset of `other`.
    confidence = how far the best match stands out (a real match is far above 10; pure chance reaches about 5, so the caller asks for ≥ 7.5)."""
    import numpy as np
    a, b = _envelope(main, seconds, rate), _envelope(other, seconds, rate)
    if not len(a) or not len(b):
        return 0.0, 0.0
    size = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    corr = np.fft.irfft(np.conj(np.fft.rfft(a, size)) * np.fft.rfft(b, size), size)
    lag = int(np.argmax(corr))
    peak = float(corr[lag])
    conf = (peak - float(corr.mean())) / (float(corr.std()) + 1e-9)
    if lag > size // 2:
        lag -= size
    return round(lag / rate, 3), round(conf, 2)


def with_camera(main: dict, cam: dict, offset: float, words: list[dict] | None = None) -> tuple:
    """Scores of the main camera + the face of the second one on the main clock.
    → (scores (n, k), who_is: [{"cam": 1, "face": i} | {"cam": 2}], faces_for_main_columns).
    If the wide main shot also shows the person of camera 2 (their mouths move together), that face is dropped from
    the main candidates — camera 2 is the better picture of that person."""
    import numpy as np
    ms, cs = np.asarray(main["scores"], dtype=np.float32), np.asarray(cam["scores"], dtype=np.float32)
    n, fps = ms.shape[0], float(main["fps"])
    col = np.zeros(n, dtype=np.float32)
    if cs.size:
        best = int(np.argmax([f["seen"] * f["h"] for f in cam["faces"]]))
        src = np.arange(n) + int(round(offset * fps))
        ok = (src >= 0) & (src < cs.shape[0])
        col[ok] = cs[src[ok], best]
    keep = list(range(ms.shape[1]))
    if ms.shape[1] >= 2 and col.any():
        sp = _speech_mask(sorted(words or [], key=lambda w: float(w.get("start", 0))), n, fps)
        cc = []
        for j in keep:
            x, y = ms[sp, j], col[sp]
            cc.append(float(np.corrcoef(x, y)[0, 1]) if x.std() > 1e-6 and y.std() > 1e-6 else 0.0)
        g = int(np.argmax(cc))
        if cc[g] > 0.2:
            keep.remove(g)
    scores = np.concatenate([ms[:, keep], col[:, None]], axis=1) if keep else col[:, None]
    who = [{"cam": 1, "face": j} for j in keep] + [{"cam": 2}]
    return scores, who, [main["faces"][j] for j in keep]


def cover_focus(face_x: float, src_ar: float, out_ar: float) -> float:
    """Where a cover-fitted clip must be cut so that the face at `face_x` (0 … 1 of its width) is in the middle
    of a narrower frame: the window position 0 … 1 (0.5 = centre)."""
    if src_ar <= out_ar * 1.01:
        return 0.5
    win = out_ar / src_ar
    return round(max(0.0, min(1.0, (face_x - win / 2) / (1 - win))), 4)


def track_points(shot_list: list[dict], faces: list[dict], starts: list[float]) -> list[list[float]]:
    """Shots → [[t, cx]] for the vertical crop (facetrack.crop_commands): the window jumps to the active speaker.
    A wide shot cannot be shown in 9:16 — the window stays on whoever spoke last. `starts` = extra source times where the
    position must be written again (the first frame after every cut)."""
    pts, last = [], None
    rows = sorted((s for s in shot_list if isinstance(s, dict)), key=lambda s: float(s.get("start", 0)))

    def cx_at(t: float):
        got = None
        for s in rows:
            if float(s["start"]) <= t + 1e-6:
                if s.get("cx") is not None and s.get("shot") != "cam":
                    got = float(s["cx"])
            else:
                break
        return got
    for t in sorted({0.0, *[float(s["start"]) for s in rows], *[float(x) for x in starts]}):
        cx = cx_at(t)
        if cx is None:
            cx = last if last is not None else (faces[0]["x"] if faces else 0.5)
        pts.append([round(t, 3), round(cx, 4)])
        last = cx
    return pts
