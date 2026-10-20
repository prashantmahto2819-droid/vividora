"""Everything the editor UI needs to list the pro features (served in GET /api/presets → "pro"
and GET /api/pro/catalog). Contract: docs/editor-schema.md."""

from __future__ import annotations

from . import catalog, colorpro, compose, keyframes, markers, masks, protools

PRO_DEFAULTS = {
    "stabilize": {"enabled": False, "strength": 0.5, "zoom": 0},
    "denoise": {"enabled": False, "method": "hqdn3d", "strength": 0.4},
    "sharpen": {"enabled": False, "method": "cas", "amount": 0.4},
    "face_refine": {"enabled": False, "strength": 0.5, "brighten": 0.3, "eyes": 0.3},
    "speed_warp": "off",
    "color": {},
    "morph_cut": {"enabled": False, "all": False, "frames": 8, "mode": "flow"},
    "mask": {},
}


def pro_json() -> dict:
    trending = [{k: v for k, v in e.items() if k not in ("ffmpeg", "build")} for e in catalog.EFFECTS if e.get("cat") == "trending"]
    return {
        "trending": trending,
        "masks": {"shapes": masks.SHAPES, "params": masks.PARAMS, "animatable": list(masks.ANIM_KEYS),
                  "bg": ["black", "blur", "#rrggbb"]},
        "blend_modes": compose.BLEND_MODES,
        "keyframe_eases": keyframes.EASES,
        "keyframe_params": {
            "clip": {k: {"min": lo, "max": hi} for k, (lo, hi) in compose.KF_PARAMS.items()},
            "main_transform": {"x": {"min": -1, "max": 1}, "y": {"min": -1, "max": 1}, "scale": {"min": 0.05, "max": 5},
                               "rotation": {"min": -3600, "max": 3600}, "opacity": {"min": 0, "max": 1}},
            "mask": list(masks.ANIM_KEYS), "crop": ["x", "y", "w", "h"],
            "effect_params": "any numeric param of a catalog effect (stepped every 1/8 s)",
        },
        "speed": {"min": 0.25, "max": 4.0, "warp": compose.SPEED_WARP},
        "tools": protools.TOOLS,
        "color": {"wheels": list(colorpro.WHEELS), "channels": ["r", "g", "b", "y"], "range": [-1, 1],
                  "curves": ["master", "r", "g", "b"],
                  "hsl_item": {"hue": 30, "range": 40, "softness": 20, "sat": 0.0, "lum": 0.0, "hue_shift": 0}},
        "markers": markers.KINDS,
        "defaults": PRO_DEFAULTS,
        "capabilities": {"stabilize": protools.can_stabilize()},
    }
