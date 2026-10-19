"""Effects catalog + colour grading — typed definitions, one source of truth
for the dashboard (what to show) and the renderer (what to run).

Every effect: id, label, category, tags, params (typed, with ranges and
defaults), an ffmpeg template, and honest support flags:
  preview  "css"    the dashboard approximates it with CSS filters
           "none"   you only see it in the render
  export   True     implemented in the ffmpeg pipeline
Intensity is just a parameter like any other. Effects stack in order.
"""

from __future__ import annotations

import re

P = dict  # param helper: P(name=..., min=..., max=..., default=..., step=...)

EFFECTS: list[dict] = [
    # --- glitch / digital
    {"id": "rgb_split", "label": "RGB split", "cat": "glitch", "tags": ["glitch", "chromatic"], "preview": "none",
     "params": [P(name="amount", label="मात्रा", min=1, max=40, default=10, step=1)],
     "ffmpeg": "rgbashift=rh={amount}:bh=-{amount}"},
    {"id": "chroma_shift", "label": "Chroma shift", "cat": "glitch", "tags": ["glitch"], "preview": "none",
     "params": [P(name="amount", label="मात्रा", min=1, max=40, default=8, step=1)],
     "ffmpeg": "chromashift=cbh={amount}:crh=-{amount}"},
    {"id": "pixelate", "label": "Pixelate", "cat": "glitch", "tags": ["mosaic", "8bit"], "preview": "none",
     "params": [P(name="size", label="block", min=2, max=64, default=12, step=1)],
     "ffmpeg": "pixelize=w={size}:h={size}"},
    {"id": "scanlines", "label": "Scanlines / VHS", "cat": "glitch", "tags": ["vhs", "retro"], "preview": "none",
     "params": [P(name="strength", label="मात्रा", min=0.1, max=1, default=0.5, step=0.05)],
     "ffmpeg": "noise=alls={strength:n20}:allf=t,drawgrid=w=iw:h=3:t=1:c=black@{strength:n0.35}"},
    {"id": "noise", "label": "Digital noise", "cat": "glitch", "tags": ["noise"], "preview": "none",
     "params": [P(name="amount", label="मात्रा", min=1, max=80, default=20, step=1)],
     "ffmpeg": "noise=alls={amount}:allf=t"},
    # --- blur / focus
    {"id": "blur", "label": "Blur", "cat": "blur", "tags": ["gaussian", "soft"], "preview": "css",
     "css": "blur({sigma:px0.25})",
     "params": [P(name="sigma", label="कितना", min=0.5, max=30, default=4, step=0.5)],
     "ffmpeg": "gblur=sigma={sigma}"},
    {"id": "tilt_shift", "label": "Tilt-shift (बीच साफ़)", "cat": "blur", "tags": ["focus", "miniature"], "preview": "none",
     "params": [P(name="sigma", label="blur", min=2, max=30, default=10, step=1), P(name="band", label="साफ़ हिस्सा %", min=10, max=80, default=40, step=5)],
     "ffmpeg": ("split[tsa][tsb];[tsb]gblur=sigma={sigma}[tsblur];[tsa][tsblur]blend=all_expr="
                "'if(lt(abs(Y/H-0.5)\\,{band:half01})\\,A\\,B)'")},
    {"id": "motion_blur", "label": "Motion blur", "cat": "blur", "tags": ["smear", "speed"], "preview": "none",
     "params": [P(name="frames", label="frames", min=2, max=8, default=3, step=1)],
     "ffmpeg": "tmix=frames={frames:int}"},
    {"id": "sharpen", "label": "Sharpen", "cat": "blur", "tags": ["detail", "crisp"], "preview": "css", "css": "contrast(1.02)",
     "params": [P(name="amount", label="मात्रा", min=0.2, max=3, default=0.8, step=0.1)],
     "ffmpeg": "unsharp=5:5:{amount}:5:5:0"},
    # --- light / lens
    {"id": "glow", "label": "Soft glow", "cat": "light", "tags": ["dreamy", "bloom"], "preview": "css", "css": "brightness(1.04) contrast(0.96)",
     "params": [P(name="amount", label="मात्रा", min=0.05, max=0.6, default=0.25, step=0.05), P(name="radius", label="फैलाव", min=4, max=30, default=14, step=1)],
     "ffmpeg": "split[gl1][gl2];[gl2]gblur=sigma={radius}[glb];[gl1][glb]blend=all_mode=screen:all_opacity={amount}"},
    {"id": "light_leak", "label": "Light leak (warm)", "cat": "light", "tags": ["leak", "film"], "preview": "css", "css": "sepia(0.15) brightness(1.05)",
     "params": [P(name="amount", label="मात्रा", min=0.1, max=0.8, default=0.35, step=0.05)],
     "ffmpeg": "drawbox=x=iw*0.55:y=0:w=iw*0.45:h=ih:color=orange@{amount:n0.5}:t=fill,gblur=sigma=0.1"},
    {"id": "lens_distort", "label": "Lens distortion", "cat": "light", "tags": ["fisheye", "barrel"], "preview": "none",
     "params": [P(name="k1", label="मात्रा", min=-0.5, max=0.5, default=0.2, step=0.05)],
     "ffmpeg": "lenscorrection=k1={k1}:k2=0"},
    {"id": "light_trails", "label": "Light trails", "cat": "light", "tags": ["lagfun", "night"], "preview": "none",
     "params": [P(name="decay", label="decay", min=0.8, max=0.99, default=0.95, step=0.01)],
     "ffmpeg": "lagfun=decay={decay}"},
    # --- film / vintage
    {"id": "grain", "label": "Film grain", "cat": "film", "tags": ["35mm", "texture"], "preview": "none",
     "params": [P(name="amount", label="मात्रा", min=2, max=40, default=9, step=1)],
     "ffmpeg": "noise=alls={amount}:allf=t+u"},
    {"id": "vignette", "label": "Vignette", "cat": "film", "tags": ["dark edges"], "preview": "css", "css": "",
     "params": [P(name="angle", label="मात्रा", min=0.2, max=1.2, default=0.7, step=0.05)],
     "ffmpeg": "vignette=angle={angle}"},
    {"id": "sepia", "label": "Sepia", "cat": "film", "tags": ["old"], "preview": "css", "css": "sepia({amount})",
     "params": [P(name="amount", label="मात्रा", min=0.1, max=1, default=0.7, step=0.05)],
     "ffmpeg": "split[sp1][sp2];[sp2]colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:0:0:0:0:1[sps];[sp1][sps]blend=all_mode=normal:all_opacity={amount}"},
    {"id": "old_film", "label": "Old film", "cat": "film", "tags": ["flicker", "scratch"], "preview": "css", "css": "sepia(0.4) contrast(1.1)",
     "params": [P(name="amount", label="मात्रा", min=0.2, max=1, default=0.6, step=0.05)],
     "ffmpeg": "curves=vintage,noise=alls={amount:n30}:allf=t,eq=contrast=1.08:saturation=0.8,vignette=PI/4"},
    {"id": "letterbox", "label": "Cinematic bars", "cat": "film", "tags": ["2.39", "bars"], "preview": "none",
     "params": [P(name="size", label="बार %", min=3, max=15, default=7, step=1)],
     "ffmpeg": "drawbox=x=0:y=0:w=iw:h=ih*{size:pct}:color=black:t=fill,drawbox=x=0:y=ih*(1-{size:pct}):w=iw:h=ih*{size:pct}:color=black:t=fill"},
    # --- motion / camera
    {"id": "shake", "label": "Handheld shake", "cat": "motion", "tags": ["camera"], "preview": "none",
     "params": [P(name="amount", label="मात्रा", min=2, max=20, default=7, step=1)],
     "ffmpeg": "crop=iw-{amount:x4}:ih-{amount:x4}:'{amount:x2}+{amount}*sin(t*37)':'{amount:x2}+{amount}*cos(t*29)',scale=iw+{amount:x4}:ih+{amount:x4}:flags=bicubic"},
    {"id": "slow_zoom", "label": "Slow zoom in", "cat": "motion", "tags": ["kenburns"], "preview": "none",
     "params": [P(name="amount", label="तक", min=1.02, max=1.4, default=1.12, step=0.01), P(name="seconds", label="सेकंड", min=1, max=30, default=8, step=1)],
     "ffmpeg": "zoompan=z='1+({amount}-1)*min(1\\,on/({seconds}*{FPS}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}"},
    {"id": "mirror", "label": "Mirror (flip)", "cat": "motion", "tags": ["flip"], "preview": "css", "css": "",
     "params": [], "ffmpeg": "hflip"},
    {"id": "rotate", "label": "Rotate", "cat": "motion", "tags": ["tilt", "dutch"], "preview": "css", "css": "",
     "params": [P(name="deg", label="डिग्री", min=-15, max=15, default=3, step=0.5)],
     "ffmpeg": "rotate={deg}*PI/180:c=black@0:ow=iw:oh=ih,scale=iw*1.08:ih*1.08,crop=iw/1.08:ih/1.08"},
    # --- stylized
    {"id": "posterize", "label": "Posterize", "cat": "stylized", "tags": ["poster", "flat"], "preview": "none",
     "params": [P(name="levels", label="levels", min=2, max=16, default=6, step=1)],
     "ffmpeg": "lutyuv=y='trunc(val/(256/{levels:int}))*(256/{levels:int})'"},
    {"id": "edge", "label": "Edge / sketch", "cat": "stylized", "tags": ["comic", "lines"], "preview": "css", "css": "grayscale(1) contrast(1.4)",
     "params": [P(name="amount", label="मात्रा", min=0.1, max=1, default=0.6, step=0.05)],
     "ffmpeg": "edgedetect=low=0.1:high=0.4:mode=colormix,eq=contrast={amount:n1.5}"},
    {"id": "negative", "label": "Negative", "cat": "stylized", "tags": ["invert"], "preview": "css", "css": "invert(1)",
     "params": [], "ffmpeg": "negate"},
    {"id": "duotone", "label": "Duotone", "cat": "stylized", "tags": ["two colour"], "preview": "css", "css": "grayscale(1) sepia(0.6) hue-rotate({hue}deg) saturate(2)",
     "params": [P(name="hue", label="रंग", min=0, max=360, default=200, step=5), P(name="sat", label="saturation", min=0.2, max=2, default=1.2, step=0.1)],
     "ffmpeg": "hue=s=0,colorize=hue={hue}:saturation={sat:n0.4}:lightness=0.5:mix=0.6"},
    {"id": "bw", "label": "Black & white", "cat": "stylized", "tags": ["mono"], "preview": "css", "css": "grayscale(1) contrast({contrast})",
     "params": [P(name="contrast", label="contrast", min=0.8, max=1.6, default=1.15, step=0.05)],
     "ffmpeg": "hue=s=0,eq=contrast={contrast}"},
    # --- portrait / beauty
    {"id": "smooth_skin", "label": "Smooth skin", "cat": "portrait", "tags": ["beauty", "denoise"], "preview": "css", "css": "blur(0.3px) contrast(0.98)",
     "params": [P(name="amount", label="मात्रा", min=1, max=10, default=4, step=1)],
     "ffmpeg": "hqdn3d={amount}:{amount:half}:6:6"},
    {"id": "warm_skin", "label": "Warm skin tone", "cat": "portrait", "tags": ["warm"], "preview": "css", "css": "sepia(0.12) saturate(1.05)",
     "params": [P(name="amount", label="मात्रा", min=0.02, max=0.2, default=0.08, step=0.01)],
     "ffmpeg": "colorbalance=rm={amount}:gm={amount:half}:bm=-{amount},eq=saturation=1.05"},
    {"id": "denoise", "label": "Denoise video", "cat": "portrait", "tags": ["low light", "clean"], "preview": "none",
     "params": [P(name="amount", label="मात्रा", min=1, max=12, default=4, step=1)],
     "ffmpeg": "hqdn3d={amount}:{amount}:{amount:x2}:{amount:x2}"},
    # --- background
    {"id": "chroma_key", "label": "Green screen (chroma key)", "cat": "background", "tags": ["green", "key"], "preview": "none",
     "params": [P(name="color", label="रंग", type="color", default="#00FF00"), P(name="similarity", label="similarity", min=0.05, max=0.6, default=0.3, step=0.01), P(name="blend", label="blend", min=0, max=0.4, default=0.1, step=0.01)],
     "ffmpeg": "chromakey=color={color:hex}:similarity={similarity}:blend={blend}", "needs_background": True},
    {"id": "bg_blur", "label": "Blur background (face center)", "cat": "background", "tags": ["portrait", "bokeh"], "preview": "none",
     "params": [P(name="sigma", label="blur", min=4, max=40, default=16, step=1), P(name="width", label="साफ़ चौड़ाई %", min=20, max=80, default=45, step=5)],
     "ffmpeg": ("split[bga][bgb];[bgb]gblur=sigma={sigma}[bgblur];[bga][bgblur]blend=all_expr="
                "'if(lt(abs(X/W-0.5)\\,{width:half01})\\,A\\,B)'")},
    # --- texture / overlay
    {"id": "dust", "label": "Dust & scratches", "cat": "texture", "tags": ["film", "overlay"], "preview": "none",
     "params": [P(name="amount", label="मात्रा", min=5, max=60, default=20, step=5)],
     "ffmpeg": "noise=c0s={amount}:c0f=t+p"},
    {"id": "halftone", "label": "Halftone dots", "cat": "texture", "tags": ["print", "comic"], "preview": "none",
     "params": [P(name="size", label="dot", min=2, max=12, default=4, step=1)],
     "ffmpeg": "pixelize=w={size}:h={size},drawgrid=w={size}:h={size}:t=1:c=black@0.25"},
]
CATEGORIES = {"glitch": "Glitch", "blur": "Blur & focus", "light": "Light & lens", "film": "Film & vintage",
              "motion": "Motion & camera", "stylized": "Stylized", "portrait": "Portrait", "background": "Background",
              "texture": "Texture"}
BY_ID = {e["id"]: e for e in EFFECTS}

# ---------- colour grading
GRADE_PARAMS = [
    P(name="exposure", label="Exposure", min=-2, max=2, default=0, step=0.05),
    P(name="contrast", label="Contrast", min=-1, max=1, default=0, step=0.02),
    P(name="highlights", label="Highlights", min=-1, max=1, default=0, step=0.02),
    P(name="shadows", label="Shadows", min=-1, max=1, default=0, step=0.02),
    P(name="whites", label="Whites", min=-1, max=1, default=0, step=0.02),
    P(name="blacks", label="Blacks", min=-1, max=1, default=0, step=0.02),
    P(name="saturation", label="Saturation", min=-1, max=1, default=0, step=0.02),
    P(name="vibrance", label="Vibrance", min=-1, max=1, default=0, step=0.02),
    P(name="temperature", label="Temperature", min=-1, max=1, default=0, step=0.02),
    P(name="tint", label="Tint", min=-1, max=1, default=0, step=0.02),
    P(name="hue", label="Hue", min=-180, max=180, default=0, step=1),
    P(name="fade", label="Fade", min=0, max=1, default=0, step=0.02),
    P(name="vignette", label="Vignette", min=0, max=1, default=0, step=0.02),
    P(name="sharpness", label="Sharpness", min=0, max=1, default=0, step=0.02),
]
GRADE_DEFAULT = {p["name"]: p["default"] for p in GRADE_PARAMS}

GRADE_PRESETS: dict[str, dict] = {
    "teal_orange": {"label": "Teal & Orange", "temperature": 0.2, "tint": -0.05, "contrast": 0.12, "saturation": 0.1, "shadows": -0.1, "highlights": 0.05, "_tint_shadows": "teal"},
    "warm_film": {"label": "Warm Film", "temperature": 0.3, "contrast": 0.06, "fade": 0.12, "saturation": -0.05, "vignette": 0.25},
    "cool_cinema": {"label": "Cool Cinema", "temperature": -0.3, "contrast": 0.15, "saturation": -0.12, "shadows": -0.08, "vignette": 0.3},
    "moody": {"label": "Moody Contrast", "exposure": -0.2, "contrast": 0.3, "saturation": -0.2, "blacks": -0.2, "vignette": 0.45},
    "clean_commercial": {"label": "Clean Commercial", "exposure": 0.1, "contrast": 0.08, "whites": 0.1, "vibrance": 0.15, "sharpness": 0.3},
    "natural_skin": {"label": "Natural Skin", "temperature": 0.08, "vibrance": 0.08, "saturation": -0.04, "contrast": 0.04},
    "vintage_fade": {"label": "Vintage Fade", "fade": 0.3, "saturation": -0.25, "temperature": 0.15, "contrast": -0.05, "vignette": 0.35},
    "bw": {"label": "Black & White", "saturation": -1, "contrast": 0.2, "blacks": -0.1},
    "soft_pastel": {"label": "Soft Pastel", "exposure": 0.15, "contrast": -0.15, "saturation": -0.1, "fade": 0.2, "temperature": 0.05},
    "night_neon": {"label": "Night Neon", "exposure": -0.1, "contrast": 0.25, "vibrance": 0.4, "temperature": -0.2, "tint": 0.15, "blacks": -0.2},
    "golden_hour": {"label": "Golden Hour", "temperature": 0.45, "exposure": 0.05, "highlights": -0.1, "saturation": 0.1, "vignette": 0.2},
    "documentary": {"label": "Documentary Neutral", "contrast": 0.04, "saturation": -0.02, "sharpness": 0.2},
}


def grade_filter(g: dict | None) -> str:
    """Colour grade → ffmpeg filter chain. Each slider maps to a real filter;
    the dashboard preview approximates the same with CSS (see grade_css)."""
    if not g:
        return ""
    v = {**GRADE_DEFAULT, **{k: float(x) for k, x in g.items() if k in GRADE_DEFAULT and x not in (None, "")}}
    parts = []
    if v["exposure"]:
        parts.append(f"exposure=exposure={v['exposure']:.3f}")
    if v["temperature"] or v["tint"]:
        # 6500 K neutral; warmer = lower K in the filter means "correct for" — so invert
        k = 6500 - v["temperature"] * 2500
        parts.append(f"colortemperature=temperature={int(k)}:mix=1")
        if v["tint"]:
            parts.append(f"colorbalance=gm={-v['tint'] * 0.3:.3f}:gs={-v['tint'] * 0.15:.3f}")
    if v["highlights"] or v["shadows"] or v["whites"] or v["blacks"] or v["fade"]:
        # curves master: blacks/fade lift the toe, shadows/highlights bend the middle, whites the shoulder
        toe = max(0.0, min(0.3, 0.12 * v["fade"] * 2 + 0.08 * max(0.0, v["blacks"])))
        p25 = max(0.05, min(0.45, 0.25 + 0.1 * v["shadows"] + 0.05 * v["blacks"]))
        p75 = max(0.55, min(0.95, 0.75 + 0.1 * v["highlights"] + 0.05 * v["whites"]))
        top = max(0.7, min(1.0, 1.0 - 0.1 * max(0.0, -v["whites"]) - 0.06 * v["fade"]))
        parts.append(f"curves=m='0/{toe:.3f} 0.25/{p25:.3f} 0.75/{p75:.3f} 1/{top:.3f}'")
    if v["contrast"] or v["saturation"]:
        parts.append(f"eq=contrast={1 + v['contrast'] * 0.6:.3f}:saturation={max(0.0, 1 + v['saturation']):.3f}")
    if v["vibrance"]:
        parts.append(f"vibrance=intensity={v['vibrance']:.3f}")
    if v["hue"]:
        parts.append(f"hue=h={v['hue']:.1f}")
    if v["sharpness"]:
        parts.append(f"unsharp=5:5:{v['sharpness'] * 1.5:.2f}:5:5:0")
    if v["vignette"]:
        parts.append(f"vignette=angle={0.25 + v['vignette'] * 0.6:.3f}")
    return ",".join(parts)


def grade_css(g: dict | None) -> str:
    if not g:
        return ""
    v = {**GRADE_DEFAULT, **{k: float(x) for k, x in g.items() if k in GRADE_DEFAULT and x not in (None, "")}}
    css = [f"brightness({1 + v['exposure'] * 0.35 + v['whites'] * 0.08 - v['blacks'] * 0.05:.3f})",
           f"contrast({1 + v['contrast'] * 0.6 - v['fade'] * 0.25 + v['shadows'] * -0.1:.3f})",
           f"saturate({max(0.0, 1 + v['saturation'] + v['vibrance'] * 0.6):.3f})"]
    if v["hue"]:
        css.append(f"hue-rotate({v['hue']:.0f}deg)")
    if v["temperature"] > 0:
        css.append(f"sepia({v['temperature'] * 0.35:.3f})")
    elif v["temperature"] < 0:
        css.append(f"hue-rotate({v['temperature'] * 12:.0f}deg)")
    return " ".join(css)


# ---------- effect stack
_FMT = re.compile(r"\{(\w+)(?::([\w.]+))?\}")


def _conv(val, mode: str | None):
    if mode is None:
        return f"{val:g}" if isinstance(val, float) else str(val)
    if mode == "int":
        return str(int(round(float(val))))
    if mode == "half":
        return f"{float(val) / 2:g}"
    if mode == "half01":
        return f"{float(val) / 200:g}"
    if mode == "pct":
        return f"{float(val) / 100:g}"
    if mode == "hex":
        return "0x" + str(val).lstrip("#")
    m = re.match(r"([xnpx]+)([\d.]+)", mode)
    if m:
        op, num = m.group(1), float(m.group(2))
        if op == "x":
            return f"{float(val) * num:g}"
        if op == "n":
            return f"{float(val) * num:g}"
        if op == "px":
            return f"{float(val) * num:g}px"
    return str(val)


def _apply(template: str, params: dict) -> str:
    return _FMT.sub(lambda m: _conv(params.get(m.group(1)), m.group(2)), template)


def _clean_params(e: dict, given: dict | None) -> dict:
    out = {}
    for p in e.get("params", []):
        val = (given or {}).get(p["name"], p.get("default"))
        if p.get("type") == "color":
            s = str(val or p.get("default", "#00FF00")).lstrip("#")
            out[p["name"]] = "#" + (s if re.fullmatch(r"[0-9a-fA-F]{6}", s) else "00FF00")
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            f = float(p.get("default", 0))
        f = max(float(p["min"]), min(float(p["max"]), f))
        out[p["name"]] = int(f) if float(p.get("step", 1)) == 1 and float(p["min"]).is_integer() else f
    return out


def stack_filter(stack: list[dict] | None, w: int = 1080, h: int = 1920, fps: float = 30) -> str:
    """[{id, params, enabled}] → ffmpeg chain (export). W/H/FPS of the output frame are available to templates."""
    parts = []
    ctx = {"W": w, "H": h, "FPS": int(round(fps))}
    for item in stack or []:
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        e = BY_ID.get(item.get("id"))
        if not e or not e.get("ffmpeg"):
            continue
        parts.append(_apply(e["ffmpeg"], {**ctx, **_clean_params(e, item.get("params"))}))
    return ",".join(parts)


def stack_css(stack: list[dict] | None) -> str:
    """Preview approximation for the dashboard (only effects with preview=css)."""
    parts = []
    for item in stack or []:
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        e = BY_ID.get(item.get("id"))
        if not e or e.get("preview") != "css" or not e.get("css"):
            continue
        parts.append(_apply(e["css"], _clean_params(e, item.get("params"))))
    return " ".join(p for p in parts if p)


def catalog_json() -> dict:
    return {"categories": CATEGORIES,
            "effects": [{k: v for k, v in e.items() if k != "ffmpeg"} for e in EFFECTS],
            "grade_params": GRADE_PARAMS, "grade_presets": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                                                           for k, v in GRADE_PRESETS.items()}}
