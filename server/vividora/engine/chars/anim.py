"""Pose clips: keyframed tracks on rig pose params, looped. pose_at(clip, t) → pose dict.

A clip = {"len": seconds, "loop": bool, "tracks": {param: [[t, value], …]}, "ease": "smooth"|"linear"}.
Values between keys are interpolated (smoothstep by default). Clips compose: idle breathing +
blink run under everything; `talk` adds hand gestures while a line is spoken.
"""

from __future__ import annotations

import math
import random

CLIPS: dict[str, dict] = {
    "idle": {"label": "खड़ा (साँस)", "len": 3.2, "loop": True, "tracks": {
        "bob": [[0, 0], [1.6, 3], [3.2, 0]], "l_sh": [[0, 8], [1.6, 10], [3.2, 8]], "r_sh": [[0, 8], [1.6, 10], [3.2, 8]],
        "head_tilt": [[0, 0], [1.6, 1.5], [3.2, 0]]}},
    "talk": {"label": "बोलते हुए (हाथ)", "len": 4.0, "loop": True, "tracks": {
        "r_sh": [[0, 12], [0.6, 48], [1.4, 30], [2.2, 55], [3.0, 22], [4.0, 12]], "r_el": [[0, 12], [0.6, -70], [1.4, -50], [2.2, -80], [3.0, -40], [4.0, 12]],
        "l_sh": [[0, 8], [1.8, 30], [2.6, 14], [4.0, 8]], "l_el": [[0, 10], [1.8, -40], [2.6, -20], [4.0, 10]],
        "head_tilt": [[0, 0], [1.0, -3], [2.0, 2], [3.0, -2], [4.0, 0]], "head_turn": [[0, 0], [1.2, 0.25], [2.4, -0.2], [4.0, 0]],
        "bob": [[0, 0], [2.0, 2], [4.0, 0]]}},
    "walk": {"label": "चलना", "len": 1.0, "loop": True, "tracks": {
        "l_hip": [[0, 22], [0.5, -22], [1.0, 22]], "r_hip": [[0, -22], [0.5, 22], [1.0, -22]],
        "l_knee": [[0, 0], [0.25, 0], [0.5, 35], [0.75, 10], [1.0, 0]], "r_knee": [[0, 35], [0.25, 10], [0.5, 0], [0.75, 0], [1.0, 35]],
        "l_sh": [[0, -24], [0.5, 26], [1.0, -24]], "r_sh": [[0, 26], [0.5, -24], [1.0, 26]], "l_el": [[0, -15], [1.0, -15]], "r_el": [[0, -15], [1.0, -15]],
        "bob": [[0, 0], [0.25, -6], [0.5, 0], [0.75, -6], [1.0, 0]]}},
    "run": {"label": "दौड़ना", "len": 0.6, "loop": True, "tracks": {
        "l_hip": [[0, 40], [0.3, -35], [0.6, 40]], "r_hip": [[0, -35], [0.3, 40], [0.6, -35]],
        "l_knee": [[0, 10], [0.3, 70], [0.6, 10]], "r_knee": [[0, 70], [0.3, 10], [0.6, 70]],
        "l_sh": [[0, -45], [0.3, 50], [0.6, -45]], "r_sh": [[0, 50], [0.3, -45], [0.6, 50]], "l_el": [[0, -70], [0.6, -70]], "r_el": [[0, -70], [0.6, -70]],
        "lean": [[0, 10], [0.6, 10]], "bob": [[0, -4], [0.15, -14], [0.3, -4], [0.45, -14], [0.6, -4]]}},
    "sit": {"label": "बैठना", "len": 3.0, "loop": True, "tracks": {
        "l_hip": [[0, 85], [3.0, 85]], "r_hip": [[0, 85], [3.0, 85]], "l_knee": [[0, 85], [3.0, 85]], "r_knee": [[0, 85], [3.0, 85]],
        "l_sh": [[0, 30], [3.0, 30]], "r_sh": [[0, 30], [3.0, 30]], "l_el": [[0, -70], [3.0, -70]], "r_el": [[0, -70], [3.0, -70]],
        "bob": [[0, 120], [1.5, 122], [3.0, 120]]}},
    "wave": {"label": "हाथ हिलाना", "len": 1.6, "loop": True, "tracks": {
        "r_sh": [[0, 150], [1.6, 150]], "r_el": [[0, -40], [0.4, -75], [0.8, -40], [1.2, -75], [1.6, -40]],
        "head_tilt": [[0, 0], [0.8, 4], [1.6, 0]], "smile": [[0, 0.8], [1.6, 0.8]]}},
    "point": {"label": "इशारा", "len": 2.0, "loop": True, "tracks": {
        "r_sh": [[0, 20], [0.4, 80], [1.6, 82], [2.0, 20]], "r_el": [[0, 0], [0.4, -8], [2.0, 0]], "r_hand": "point",
        "head_turn": [[0, 0], [0.4, 0.5], [1.6, 0.5], [2.0, 0]]}},
    "type": {"label": "टाइप करना", "len": 0.5, "loop": True, "tracks": {
        "l_sh": [[0, 26], [0.5, 26]], "r_sh": [[0, 26], [0.5, 26]], "l_el": [[0, -88], [0.25, -92], [0.5, -88]], "r_el": [[0, -92], [0.25, -88], [0.5, -92]],
        "head_tilt": [[0, 4], [0.5, 4]], "gaze_y": [[0, 1], [0.5, 1]]}},
    "nod": {"label": "हाँ (सिर हिलाना)", "len": 1.2, "loop": True, "tracks": {
        "head_tilt": [[0, 0], [0.3, 3], [0.6, 0], [0.9, 3], [1.2, 0]], "bob": [[0, 0], [0.3, 6], [0.6, 0], [0.9, 6], [1.2, 0]], "gaze_y": [[0, 0], [0.3, 1], [0.6, 0], [0.9, 1], [1.2, 0]], "smile": [[0, 0.5], [1.2, 0.5]]}},
    "laugh": {"label": "हँसना", "len": 1.0, "loop": True, "tracks": {
        "bob": [[0, 0], [0.25, 6], [0.5, 0], [0.75, 6], [1.0, 0]], "head_tilt": [[0, -6], [0.5, -10], [1.0, -6]], "eye_open": [[0, 0.3], [1.0, 0.3]],
        "smile": [[0, 1], [1.0, 1]], "viseme": "AA", "mouth_open": [[0, 0.6], [0.25, 1], [0.5, 0.6], [0.75, 1], [1.0, 0.6]],
        "l_sh": [[0, 20], [1.0, 20]], "l_el": [[0, -90], [1.0, -90]], "expr": "happy"}},
    "cry": {"label": "रोना", "len": 2.0, "loop": True, "tracks": {
        "head_tilt": [[0, 6], [1.0, 9], [2.0, 6]], "bob": [[0, 4], [0.5, 8], [1.0, 4], [1.5, 8], [2.0, 4]], "eye_open": [[0, 0.2], [2.0, 0.2]],
        "brow": [[0, -0.8], [2.0, -0.8]], "smile": [[0, -0.9], [2.0, -0.9]], "l_sh": [[0, 40], [2.0, 40]], "l_el": [[0, -120], [2.0, -120]], "expr": "sad"}},
    "dance1": {"label": "डांस (गरबा)", "len": 1.2, "loop": True, "tracks": {
        "l_sh": [[0, 60], [0.6, 120], [1.2, 60]], "r_sh": [[0, 120], [0.6, 60], [1.2, 120]], "l_el": [[0, -40], [0.6, -80], [1.2, -40]], "r_el": [[0, -80], [0.6, -40], [1.2, -80]],
        "lean": [[0, -8], [0.6, 8], [1.2, -8]], "bob": [[0, 0], [0.3, -8], [0.6, 0], [0.9, -8], [1.2, 0]], "l_hip": [[0, 14], [0.6, -8], [1.2, 14]], "r_hip": [[0, -8], [0.6, 14], [1.2, -8]],
        "head_tilt": [[0, -8], [0.6, 8], [1.2, -8]], "smile": [[0, 0.9], [1.2, 0.9]]}},
    "dance2": {"label": "डांस (भांगड़ा)", "len": 0.8, "loop": True, "tracks": {
        "l_sh": [[0, 160], [0.4, 140], [0.8, 160]], "r_sh": [[0, 160], [0.4, 140], [0.8, 160]], "l_el": [[0, -30], [0.4, -60], [0.8, -30]], "r_el": [[0, -30], [0.4, -60], [0.8, -30]],
        "l_knee": [[0, 30], [0.4, 0], [0.8, 30]], "r_knee": [[0, 0], [0.4, 30], [0.8, 0]], "l_hip": [[0, 12], [0.4, -4], [0.8, 12]], "r_hip": [[0, -4], [0.4, 12], [0.8, -4]],
        "bob": [[0, -4], [0.2, -16], [0.4, -4], [0.6, -16], [0.8, -4]], "smile": [[0, 1], [0.8, 1]], "head_tilt": [[0, 6], [0.4, -6], [0.8, 6]]}},
    "teach": {"label": "पढ़ाना (बोर्ड की ओर)", "len": 3.0, "loop": True, "tracks": {
        "r_sh": [[0, 90], [1.0, 120], [2.0, 100], [3.0, 90]], "r_el": [[0, -20], [1.0, -10], [2.0, -30], [3.0, -20]], "r_hand": "point",
        "head_turn": [[0, 0.6], [1.5, 0.3], [3.0, 0.6]], "l_sh": [[0, 14], [3.0, 14]], "l_el": [[0, -30], [3.0, -30]]}},
    "drive": {"label": "गाड़ी चलाना", "len": 2.0, "loop": True, "tracks": {
        "l_sh": [[0, 34], [1.0, 38], [2.0, 34]], "r_sh": [[0, 34], [1.0, 30], [2.0, 34]], "l_el": [[0, -95], [2.0, -95]], "r_el": [[0, -95], [2.0, -95]],
        "l_hip": [[0, 80], [2.0, 80]], "r_hip": [[0, 80], [2.0, 80]], "l_knee": [[0, 70], [2.0, 70]], "r_knee": [[0, 70], [2.0, 70]], "bob": [[0, 110], [2.0, 110]],
        "l_hand": "fist", "r_hand": "fist"}},
    "think": {"label": "सोचना", "len": 2.4, "loop": True, "tracks": {
        "r_sh": [[0, 18], [2.4, 18]], "r_el": [[0, -140], [2.4, -140]], "head_tilt": [[0, 6], [1.2, 9], [2.4, 6]], "gaze_x": [[0, 0.8], [2.4, 0.8]], "gaze_y": [[0, -1], [2.4, -1]], "expr": "thinking"}},
    "clap": {"label": "ताली", "len": 0.5, "loop": True, "tracks": {
        "l_sh": [[0, 40], [0.25, 28], [0.5, 40]], "r_sh": [[0, 40], [0.25, 28], [0.5, 40]], "l_el": [[0, -95], [0.5, -95]], "r_el": [[0, -95], [0.5, -95]], "smile": [[0, 0.8], [0.5, 0.8]]}},
}
NUMERIC = {"bob", "lean", "head_tilt", "head_turn", "l_sh", "l_el", "r_sh", "r_el", "l_hip", "l_knee", "r_hip", "r_knee",
           "eye_open", "gaze_x", "gaze_y", "brow", "smile", "mouth_open", "squash"}


def _smooth(u: float) -> float:
    return u * u * (3 - 2 * u)


def sample(track, t: float, length: float, loop: bool, ease: str = "smooth") -> float:
    if not isinstance(track, list):
        return float(track)
    if loop and length > 0:
        t = t % length
    if t <= track[0][0]:
        return float(track[0][1])
    if t >= track[-1][0]:
        return float(track[-1][1])
    for (t0, v0), (t1, v1) in zip(track, track[1:]):
        if t0 <= t <= t1:
            u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            if ease == "smooth":
                u = _smooth(u)
            return float(v0) + (float(v1) - float(v0)) * u
    return float(track[-1][1])


def pose_at(clip: str | dict, t: float, phase: float = 0.0) -> dict:
    c = CLIPS.get(clip, CLIPS["idle"]) if isinstance(clip, str) else clip
    out: dict = {}
    L, loop, ease = float(c.get("len", 1)), bool(c.get("loop", True)), c.get("ease", "smooth")
    for k, tr in (c.get("tracks") or {}).items():
        if k in NUMERIC:
            out[k] = sample(tr, t + phase, L, loop, ease)
        else:
            out[k] = tr
    return out


def blink_at(t: float, seed: int = 0) -> float:
    """Eye openness: a blink every ~3–5 s (deterministic per seed), 0.14 s long."""
    r = random.Random(seed)
    cursor = 1.2 + r.random() * 2
    while cursor < t + 0.2:
        if cursor <= t < cursor + 0.14:
            u = (t - cursor) / 0.14
            return 1.0 - math.sin(math.pi * u)
        cursor += 2.8 + r.random() * 2.2
    return 1.0


def compose(t: float, base: str = "idle", gesture: str | None = None, seed: int = 0, phase: float = 0.0) -> dict:
    """Idle breathing + blink, with a gesture clip layered on top (its tracks win)."""
    pose = pose_at("idle", t, phase)
    if base != "idle":
        pose.update(pose_at(base, t, phase))
    if gesture and gesture in CLIPS and gesture != base:
        pose.update(pose_at(gesture, t, phase))
    pose["eye_open"] = min(float(pose.get("eye_open", 1.0)), blink_at(t, seed))
    return pose


def clip_list() -> list[dict]:
    return [{"id": k, "label": v["label"], "len": v["len"]} for k, v in CLIPS.items()]
