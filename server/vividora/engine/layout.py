"""Smart Layout Engine: intelligent B-roll placement and overlay control.

Layout modes for B-roll clips:
  behind     — B-roll replaces the background; person stays visible (matting)
  pip        — B-roll in a small configurable corner window
  split      — Frame split 50/50 or 60/40 (person side + B-roll side)
  overlay    — B-roll semi-transparent over the full frame (opacity + feathered edges)
  fullscreen — B-roll covers the entire frame (पुरानी default, backward compatible)

The `behind` mode uses the main video's cached person matte (engine/matting.py).
Compositing order: B-roll (background) → person mask on top → final frame.

Feathered edges: B-roll borders blend with a gradient mask — soft transition
instead of a hard cut.  feather_px controls the blur width (0 = sharp edge).
"""

from __future__ import annotations

from pathlib import Path

from .ffmpeg import escape_filter_path

# --- layout mode catalog ---------------------------------------------------

LAYOUT_MODES = {
    "fullscreen": "पूरा frame (पुरानी default)",
    "behind":     "B-roll पीछे, इंसान सामने (Smart B-roll)",
    "pip":        "छोटी window में (Picture-in-Picture)",
    "split":      "आधा-आधा frame (Split screen)",
    "overlay":    "पारदर्शी ऊपर (Semi-transparent overlay)",
}

PIP_CORNERS = {"tl": "ऊपर बाएँ", "tr": "ऊपर दाएँ", "bl": "नीचे बाएँ", "br": "नीचे दाएँ"}
PIP_SIZE_RANGE = (0.15, 0.40)   # fraction of frame width
SPLIT_RATIOS = {"50_50": (0.5, 0.5), "60_40": (0.6, 0.4), "40_60": (0.4, 0.6)}
SPLIT_SIDES = {"person_left": "इंसान बाएँ", "person_right": "इंसान दाएँ"}

# default feather for each mode (px at 720p; scales with resolution)
_DEFAULT_FEATHER = {"behind": 0, "pip": 6, "split": 12, "overlay": 18, "fullscreen": 0}


def _ev(v: float) -> int:
    """Round to even (ffmpeg requires even dimensions)."""
    return max(2, int(round(v / 2)) * 2)


def _feather_k(short_side: int) -> float:
    """Scale feather values from 720p reference to actual resolution."""
    return max(0.5, short_side / 720)


# ---------------------------------------------------------------------------
# Layout compositors — each returns an ffmpeg filter_complex fragment string
# ---------------------------------------------------------------------------

def behind_filter(item: dict, input_index: int, w: int, h: int,
                  in_label: str, out_label: str, idx: int,
                  main_alpha_label: str | int) -> str:
    """B-roll behind person: B-roll → person matte on top → composited frame.

    main_alpha_label: ffmpeg label (e.g. "[_mau3]") or input index of the
    MAIN VIDEO's person matte (same timeline, already cut/synced by render.py).
    The alpha is expected to be gray, on the output timeline.
    """
    from .effects import ALPHA_RANGE, edge_filter
    s, e = float(item["start"]), float(item["end"])

    # feather on the person matte edge (optional, softens the person outline)
    fe = float(item.get("edge_feather", 0) or 0)
    sh = float(item.get("edge_shrink", 0) or 0)
    edge = edge_filter(sh, fe, min(w, h))

    # resolve alpha source: label string or input index
    if isinstance(main_alpha_label, int):
        alpha_src = f"[{main_alpha_label}:v]"
    else:
        alpha_src = str(main_alpha_label)

    # B-roll input: scale to frame, set timeline
    pre = (f"[{input_index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
           f"crop={w}:{h},setpts=PTS-STARTPTS+{s:.3f}/TB[bl{idx}]")

    # person mask: range correction + optional edge refinement
    alpha_chain = (f"{alpha_src}format=gray,{ALPHA_RANGE}"
                   f"{',' + edge if edge else ''},scale={w}:{h}[pa{idx}]")

    # composite: B-roll as background, person extracted from current video on top
    # 1. split current frame: one copy for person extraction, one as fallback
    # 2. person layer = current video * person mask (alphamerge)
    # 3. where B-roll is active: B-roll underneath, person layer on top
    composite = (
        f"{pre};{alpha_chain};"
        # fade the B-roll in/out
        f"[bl{idx}]format=rgba,fade=t=in:st={s:.3f}:d=0.25:alpha=1,"
        f"fade=t=out:st={max(s, e - 0.25):.3f}:d=0.25:alpha=1[blf{idx}];"
        # split the current video: one for the person, one as fallback
        f"{in_label}split[vm{idx}][vb{idx}];"
        # extract person from current video using the matte
        f"[vm{idx}]format=rgba[vmr{idx}];[vmr{idx}][pa{idx}]alphamerge[person{idx}];"
        # where B-roll is active: overlay B-roll on the base, then overlay person on top
        f"[vb{idx}][blf{idx}]overlay=0:0:enable='between(t\\,{s:.3f}\\,{e:.3f})':eof_action=pass[vbr{idx}];"
        f"[vbr{idx}][person{idx}]overlay=0:0:enable='between(t\\,{s:.3f}\\,{e:.3f})':eof_action=pass{out_label}"
    )
    return composite


def pip_filter(item: dict, input_index: int, w: int, h: int,
               in_label: str, out_label: str, idx: int) -> str:
    """Picture-in-Picture: B-roll in a small window in a configurable corner.

    Item fields:
      pip_corner  — tl/tr/bl/br (default: br)
      pip_size    — fraction of frame width, 0.15..0.40 (default: 0.28)
      pip_radius  — corner radius px (default: 12)
      feather     — edge feather px (default: 6)
    """
    s, e = float(item["start"]), float(item["end"])
    corner = item.get("pip_corner") or item.get("pos") or "br"
    size = max(PIP_SIZE_RANGE[0], min(PIP_SIZE_RANGE[1],
               float(item.get("pip_size", 0.28) or 0.28)))
    feather = int(item.get("feather", 6) or 6)
    radius = max(0, int(item.get("pip_radius", 12) or 12))

    bw = _ev(w * size)
    bh = _ev(h * size)
    margin = int(min(w, h) * 0.03)

    # account for captions area at bottom
    caption_margin = int(h * 0.28)
    pos_map = {
        "tl": f"{margin}:{margin}",
        "tr": f"W-w-{margin}:{margin}",
        "bl": f"{margin}:H-h-{caption_margin}",
        "br": f"W-w-{margin}:H-h-{caption_margin}",
    }
    pos = pos_map.get(corner, pos_map["br"])

    prep = (f"[{input_index}:v]scale={bw}:{bh}:force_original_aspect_ratio=increase,"
            f"crop={bw}:{bh},setpts=PTS-STARTPTS+{s:.3f}/TB")

    # rounded corners using geq (alpha mask)
    if radius > 0:
        r = min(radius, bw // 4, bh // 4)
        prep += (f",format=rgba,"
                 f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':"
                 f"a='if(lt(hypot(max(0\\,{r}-1-X)\\,max(0\\,{r}-1-Y))\\,{r})*"
                 f"lt(hypot(max(0\\,X-{bw}+{r})\\,max(0\\,{r}-1-Y))\\,{r})*"
                 f"lt(hypot(max(0\\,{r}-1-X)\\,max(0\\,Y-{bh}+{r}))\\,{r})*"
                 f"lt(hypot(max(0\\,X-{bw}+{r})\\,max(0\\,Y-{bh}+{r}))\\,{r})\\,"
                 f"255\\,0)'")
    elif feather > 0:
        # feathered edges without rounded corners
        fp = feather
        prep += (f",format=rgba,"
                 f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':"
                 f"a='255*min(min(min(X\\,{bw}-1-X)\\,min(Y\\,{bh}-1-Y))\\,{fp})/{fp}'")
    else:
        prep += ",format=rgba"

    prep += (f",fade=t=in:st={s:.3f}:d=0.2:alpha=1,"
             f"fade=t=out:st={max(s, e - 0.2):.3f}:d=0.2:alpha=1[pip{idx}]")

    return (f"{prep};{in_label}[pip{idx}]overlay={pos}:"
            f"enable='between(t\\,{s:.3f}\\,{e:.3f})':eof_action=pass{out_label}")


def split_filter(item: dict, input_index: int, w: int, h: int,
                 in_label: str, out_label: str, idx: int) -> str:
    """Split screen: frame divided into person side + B-roll side.

    Item fields:
      split_ratio  — "50_50" | "60_40" | "40_60" (default: 50_50)
      split_side   — "person_left" | "person_right" (default: person_left)
      feather      — seam feather px (default: 12)
    """
    s, e = float(item["start"]), float(item["end"])
    ratio_key = item.get("split_ratio") or "50_50"
    ratios = SPLIT_RATIOS.get(ratio_key, (0.5, 0.5))
    side = item.get("split_side") or "person_left"
    feather = int(item.get("feather", 12) or 12)

    if side == "person_left":
        broll_w = _ev(w * ratios[1])
        broll_x = w - broll_w
    else:
        broll_w = _ev(w * ratios[0])
        broll_x = 0

    # B-roll: scale to fill its side of the frame (crop from center)
    broll_prep = (f"[{input_index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                  f"crop={broll_w}:{h},setpts=PTS-STARTPTS+{s:.3f}/TB")

    # feather the seam edge
    if feather > 0:
        if side == "person_left":
            # B-roll is on the right — feather its left edge (the seam)
            broll_prep += (f",format=rgba,"
                           f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':"
                           f"a='if(lt(X\\,{feather})\\,255*X/{feather}\\,255)'")
        else:
            # B-roll is on the left — feather its right edge (the seam)
            broll_prep += (f",format=rgba,"
                           f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':"
                           f"a='if(gt(X\\,{broll_w}-1-{feather})\\,255*({broll_w}-1-X)/{feather}\\,255)'")
    else:
        broll_prep += ",format=rgba"

    broll_prep += (f",fade=t=in:st={s:.3f}:d=0.25:alpha=1,"
                   f"fade=t=out:st={max(s, e - 0.25):.3f}:d=0.25:alpha=1[sp{idx}]")

    return (f"{broll_prep};{in_label}[sp{idx}]overlay={broll_x}:0:"
            f"enable='between(t\\,{s:.3f}\\,{e:.3f})':eof_action=pass{out_label}")


def overlay_trans_filter(item: dict, input_index: int, w: int, h: int,
                         in_label: str, out_label: str, idx: int) -> str:
    """Semi-transparent overlay: B-roll at reduced opacity over the full frame.

    Item fields:
      opacity   — 0.0..1.0 (default: 0.35)
      feather   — edge feather px (default: 18)
    """
    s, e = float(item["start"]), float(item["end"])
    opacity = max(0.05, min(0.95, float(item.get("opacity", 0.35) or 0.35)))
    feather = int(item.get("feather", 18) or 18)

    prep = (f"[{input_index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setpts=PTS-STARTPTS+{s:.3f}/TB,format=rgba,"
            f"colorchannelmixer=aa={opacity:.3f}")

    # feathered edges — soft gradient at all borders
    if feather > 0:
        fp = feather
        prep += (f",geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':"
                 f"a='a(X\\,Y)*min(min(min(X\\,{w}-1-X)\\,min(Y\\,{h}-1-Y))\\,{fp})/{fp}'")

    prep += (f",fade=t=in:st={s:.3f}:d=0.3:alpha=1,"
             f"fade=t=out:st={max(s, e - 0.3):.3f}:d=0.3:alpha=1[ovl{idx}]")

    return (f"{prep};{in_label}[ovl{idx}]overlay=0:0:"
            f"enable='between(t\\,{s:.3f}\\,{e:.3f})':eof_action=pass{out_label}")


# ---------------------------------------------------------------------------
# Dispatcher: resolve the layout mode for a B-roll item and return the filter
# ---------------------------------------------------------------------------

def resolve_layout(item: dict) -> str:
    """What layout mode does this item use?  Backward compatible:
    - explicit `layout` field takes priority
    - no `layout` field → look at `fit`; fit=cover/missing → "fullscreen"
    """
    layout = item.get("layout")
    if layout and layout in LAYOUT_MODES:
        return layout
    fit = item.get("fit") or "cover"
    if fit == "pip":
        return "pip"
    if fit == "free":
        return "free"  # handled by existing compose/effects code
    return "fullscreen"


def needs_main_alpha(item: dict) -> bool:
    """Does this B-roll item need the main video's person matte?"""
    return resolve_layout(item) == "behind"


def layout_filter(item: dict, input_index: int, w: int, h: int,
                  in_label: str, out_label: str, idx: int,
                  main_alpha_index: int | None = None) -> str | None:
    """Build the ffmpeg filter for this item's layout mode.
    Returns None when the layout is not handled here (free, fullscreen = existing code)."""
    mode = resolve_layout(item)
    if mode == "behind":
        if main_alpha_index is None:
            # no matte available — fall back to fullscreen (पुराना behavior)
            return None
        return behind_filter(item, input_index, w, h, in_label, out_label, idx, main_alpha_index)
    if mode == "pip":
        return pip_filter(item, input_index, w, h, in_label, out_label, idx)
    if mode == "split":
        return split_filter(item, input_index, w, h, in_label, out_label, idx)
    if mode == "overlay":
        return overlay_trans_filter(item, input_index, w, h, in_label, out_label, idx)
    return None  # fullscreen / free — handled by existing effects.overlay_filter / compose
