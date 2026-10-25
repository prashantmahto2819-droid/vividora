"""Multi-format smart reframing — one source → multiple aspect ratios with
subject-aware cropping.

Uses face-track data (from prepare step) to compute per-format optimal crop
parameters instead of applying one static focus_x to every platform.

Key ideas:
  1. Each aspect ratio has its own ideal crop window based on where the
     subject(s) actually are in the video.
  2. For 9:16 (vertical): center on the speaker, narrow crop — face must stay
     inside safe zone (the middle 60%).
  3. For 1:1 (square): more relaxed centering, faces can be wider apart.
  4. For 16:9 (landscape): usually no crop needed (source is 16:9), but if
     source is vertical → blur-pad or pick the widest scene.
  5. For 4:5 (portrait feed): mild vertical crop of 16:9, faces stay in frame.

The engine never re-runs face detection: it reads the keyframes already in
`meta["face_track"]` (produced by facetrack.py during `prepare`).
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

log = logging.getLogger("vividora.multiformat")

# Aspect ratios we recognize with their target dimensions
FORMATS = {
    "9:16": {"w": 1080, "h": 1920, "ratio": 9 / 16, "label": "Vertical (Shorts/Reels)"},
    "1:1":  {"w": 1080, "h": 1080, "ratio": 1.0, "label": "Square (Post)"},
    "16:9": {"w": 1920, "h": 1080, "ratio": 16 / 9, "label": "Landscape (YouTube)"},
    "4:5":  {"w": 1080, "h": 1350, "ratio": 4 / 5, "label": "Portrait Feed (FB/IG)"},
}

# Maps preset IDs → canonical aspect ratio key
PRESET_TO_RATIO = {
    "yt-long": "16:9", "yt-short": "9:16",
    "ig-reel": "9:16", "ig-story": "9:16", "ig-post": "1:1",
    "fb-reel": "9:16", "fb-post": "4:5",
    "linkedin": "1:1", "whatsapp": "9:16",
}


def _face_centroid(keyframes: list[list[float]], t_start: float = 0, t_end: float | None = None) -> float:
    """Weighted average of face x-positions over [t_start, t_end].

    More recent and more central faces get slightly higher weight (subjects
    that are on-screen longer matter more).  Returns 0.5 if no data.
    """
    if not keyframes:
        return 0.5
    pts = [(t, cx) for t, cx in keyframes
           if t >= t_start and (t_end is None or t <= t_end)]
    if not pts:
        return 0.5
    total_w = 0.0
    total_cx = 0.0
    for t, cx in pts:
        # weight: slightly prefer centre-ish faces (they're more likely the speaker)
        w = 1.0 + 0.3 * (1.0 - abs(cx - 0.5) * 2)
        total_w += w
        total_cx += cx * w
    return total_cx / total_w if total_w else 0.5


def _face_spread(keyframes: list[list[float]], t_start: float = 0, t_end: float | None = None) -> float:
    """How much the face moves horizontally — 0 = static, 1 = full width.

    Used to decide whether the crop can be static or needs face-tracking
    movement.
    """
    if not keyframes:
        return 0.0
    pts = [cx for t, cx in keyframes
           if t >= t_start and (t_end is None or t <= t_end)]
    if len(pts) < 2:
        return 0.0
    return max(pts) - min(pts)


def _safe_focus(cx: float, ratio_key: str) -> float:
    """Clamp the focus so the crop doesn't push important content off-screen.

    For vertical formats the safe zone is the middle ~65% (phones have UI
    overlays top and bottom).  For square/landscape we're more relaxed.
    """
    if ratio_key == "9:16":
        # keep subject in the central 60% of the frame
        return max(0.20, min(0.80, cx))
    if ratio_key in ("1:1", "4:5"):
        return max(0.15, min(0.85, cx))
    # 16:9 — barely any crop, face can be anywhere
    return max(0.10, min(0.90, cx))


def analyze(meta: dict, presets: list[str] | None = None) -> dict[str, dict]:
    """Compute per-preset smart reframing parameters.

    Args:
        meta: project meta (has face_track, width, height, duration)
        presets: list of preset IDs to analyze (None = all known presets)

    Returns:
        {preset_id: {"focus_x": float, "focus_y": float, "fit": str,
                      "needs_tracking": bool, "confidence": float}}
    """
    kf = meta.get("face_track") or []
    src_w = int(meta.get("width", 1920))
    src_h = int(meta.get("height", 1080))
    src_ratio = src_w / max(1, src_h)
    duration = float(meta.get("duration", 0))

    centroid = _face_centroid(kf)
    spread = _face_spread(kf)
    has_face = len(kf) > 0

    result: dict[str, dict] = {}
    check_presets = presets or list(PRESET_TO_RATIO.keys())

    for pid in check_presets:
        ratio_key = PRESET_TO_RATIO.get(pid)
        if not ratio_key:
            # unknown preset — use defaults
            result[pid] = {"focus_x": 0.5, "focus_y": 0.5, "fit": "crop",
                           "needs_tracking": False, "confidence": 0.0}
            continue

        fmt = FORMATS[ratio_key]
        dst_ratio = fmt["ratio"]

        # Does this conversion need cropping?
        needs_crop = abs(src_ratio - dst_ratio) / max(dst_ratio, 0.01) > 0.05

        if not needs_crop:
            # Same ratio → just scale, no reframing needed
            result[pid] = {"focus_x": 0.5, "focus_y": 0.5, "fit": "crop",
                           "needs_tracking": False, "confidence": 1.0}
            continue

        if src_ratio > dst_ratio:
            # Landscape → narrower (e.g. 16:9 → 9:16, 16:9 → 1:1)
            # Horizontal crop — face tracking matters
            if has_face:
                fx = _safe_focus(centroid, ratio_key)
                # If face moves a lot, enable dynamic tracking
                needs_tracking = spread > 0.15 and ratio_key == "9:16"
                confidence = min(1.0, len(kf) / max(1, duration * 2))
            else:
                fx = 0.5  # no face → center crop
                needs_tracking = False
                confidence = 0.3

            # For extreme ratio changes (16:9 → 9:16), decide: crop vs blur
            ratio_diff = src_ratio / dst_ratio
            if ratio_diff > 2.5 and not has_face:
                # Very wide → very tall with no face: use blur background
                fit = "blur"
            else:
                fit = "crop"

            result[pid] = {"focus_x": round(fx, 3), "focus_y": 0.5,
                           "fit": fit, "needs_tracking": needs_tracking,
                           "confidence": round(confidence, 2)}

        else:
            # Narrow → wider (e.g. 9:16 → 16:9, 9:16 → 1:1)
            # Vertical crop or pad/blur
            if ratio_key == "16:9" and src_ratio < 1.0:
                # Vertical source → landscape: always blur-pad (cropping top/bottom
                # would lose the face)
                fit = "blur"
                result[pid] = {"focus_x": 0.5, "focus_y": 0.5, "fit": fit,
                               "needs_tracking": False, "confidence": 0.8}
            else:
                # Mild vertical → slightly wider (e.g. 4:5 → 1:1)
                fy = 0.4 if has_face else 0.5  # slightly above center (faces are top-heavy)
                result[pid] = {"focus_x": 0.5, "focus_y": round(fy, 3),
                               "fit": "crop", "needs_tracking": False,
                               "confidence": 0.7 if has_face else 0.4}

    return result


def suggested_presets(meta: dict) -> list[dict]:
    """Return a ranked list of recommended presets for this video.

    Based on source aspect ratio + duration, suggests the best platforms.
    """
    src_w = int(meta.get("width", 1920))
    src_h = int(meta.get("height", 1080))
    src_ratio = src_w / max(1, src_h)
    duration = float(meta.get("duration", 0))

    suggestions = []
    for pid, ratio_key in PRESET_TO_RATIO.items():
        fmt = FORMATS[ratio_key]
        dst_ratio = fmt["ratio"]
        score = 1.0

        # Prefer presets whose ratio is close to source
        ratio_diff = abs(src_ratio - dst_ratio) / max(dst_ratio, 0.01)
        score -= min(0.5, ratio_diff * 0.2)

        # Duration constraints — penalize if video is too long for the platform
        max_secs = {"yt-short": 180, "ig-reel": 180, "ig-story": 60,
                    "fb-reel": 180, "whatsapp": 30, "ig-post": 60}.get(pid)
        if max_secs and duration > max_secs:
            score -= 0.3

        # Long-form prefers landscape
        if pid == "yt-long" and src_ratio >= 1.5:
            score += 0.2
        elif pid == "yt-long" and src_ratio < 1.0:
            score -= 0.2

        suggestions.append({
            "preset": pid,
            "ratio": ratio_key,
            "label": fmt["label"],
            "score": round(max(0.0, min(1.0, score)), 2),
            "native": ratio_diff < 0.05,
        })

    suggestions.sort(key=lambda s: -s["score"])
    return suggestions


def batch_focus(meta: dict, presets: list[str]) -> dict[str, float]:
    """Quick helper: returns just {preset: focus_x} for each preset.

    Used by the render pipeline to override the single global focus_x with
    per-preset optimal values.
    """
    analysis = analyze(meta, presets)
    return {pid: info["focus_x"] for pid, info in analysis.items()}


def preview_crop(meta: dict, preset_id: str, frame_w: int = 640) -> dict:
    """Compute crop rectangle for a single frame preview.

    Returns {"x": int, "y": int, "w": int, "h": int, "src_w": int, "src_h": int}
    at the given preview width — useful for the frontend to draw a crop overlay.
    """
    src_w = int(meta.get("width", 1920))
    src_h = int(meta.get("height", 1080))
    ratio_key = PRESET_TO_RATIO.get(preset_id, "16:9")
    fmt = FORMATS.get(ratio_key, FORMATS["16:9"])
    dst_ratio = fmt["ratio"]

    analysis = analyze(meta, [preset_id])
    info = analysis.get(preset_id, {"focus_x": 0.5, "focus_y": 0.5, "fit": "crop"})

    # Scale to preview size
    scale = frame_w / src_w
    pw = frame_w
    ph = int(src_h * scale)

    if info["fit"] != "crop":
        # blur/pad — the full source is visible
        return {"x": 0, "y": 0, "w": pw, "h": ph,
                "crop_w": pw, "crop_h": ph,
                "src_w": pw, "src_h": ph, "fit": info["fit"]}

    src_ratio = src_w / max(1, src_h)
    if src_ratio > dst_ratio:
        # horizontal crop
        crop_h = ph
        crop_w = int(crop_h * dst_ratio)
        cx = int((pw - crop_w) * info["focus_x"])
        cy = 0
    else:
        # vertical crop
        crop_w = pw
        crop_h = int(crop_w / dst_ratio)
        cy = int((ph - crop_h) * info["focus_y"])
        cx = 0

    return {"x": max(0, cx), "y": max(0, cy),
            "crop_w": min(crop_w, pw), "crop_h": min(crop_h, ph),
            "src_w": pw, "src_h": ph, "fit": "crop"}
