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
# ---- more effects (CapCut-style variety). Labels inside templates are made unique per stack position.
def _fx(id_, label, cat, ff, params=(), tags=(), css=""):
    return {"id": id_, "label": label, "cat": cat, "tags": list(tags), "preview": "css" if css else "none", "css": css,
            "params": list(params), "ffmpeg": ff}


_AMT = lambda d=0.5, lo=0.05, hi=1.0, st=0.05: P(name="amount", label="मात्रा", min=lo, max=hi, default=d, step=st)  # noqa: E731
_LEAK = "split[lka][lkb];[lkb]drawbox=x={X}:y=0:w=iw*0.45:h=ih:color={C}@0.9:t=fill,gblur=sigma=120[lkc];[lka][lkc]blend=all_mode=screen:all_opacity={amount}"
EFFECTS += [
    # glitch / digital
    _fx("rgb_glitch", "RGB glitch strong", "glitch", "rgbashift=rh={amount:int}:gv=-{amount:half}:bh=-{amount:int}", [P(name="amount", label="मात्रा", min=4, max=60, default=24, step=1)], ["glitch"]),
    _fx("invert_flash", "Invert flash", "glitch", "negate=enable='lt(mod(t\\,{period})\\,0.08)'", [P(name="period", label="हर (s)", min=0.3, max=4, default=1.2, step=0.1)], ["flash", "beat"]),
    _fx("strobe", "Strobe", "glitch", "eq=brightness='if(lt(mod(t\\,{period})\\,{period:half})\\,{amount:n0.35}\\,0)':eval=frame", [P(name="period", label="speed (s)", min=0.08, max=1, default=0.2, step=0.02), _AMT(0.6)], ["flash", "party"]),
    _fx("flicker", "Flicker", "glitch", "eq=brightness='{amount:n0.12}*sin(t*31)':eval=frame", [_AMT(0.5)], ["light"]),
    _fx("hue_cycle", "Hue cycle", "glitch", "hue=h='t*{speed}'", [P(name="speed", label="speed", min=10, max=360, default=90, step=10)], ["rainbow"]),
    _fx("rainbow", "Rainbow", "glitch", "hue=h='t*{speed}':s=1.6", [P(name="speed", label="speed", min=30, max=720, default=240, step=10)], ["color"]),
    _fx("vhs_tracking", "VHS tracking", "glitch", "chromashift=cbh=6:crh=-6,noise=alls={amount:n30}:allf=t,drawgrid=w=iw:h=4:t=1:c=black@0.25,eq=saturation=1.2", [_AMT(0.5)], ["vhs", "retro"]),
    _fx("mirror_glitch", "Mirror glitch", "glitch", "split[mga][mgb];[mgb]hflip[mgc];[mga][mgc]blend=all_mode=difference:all_opacity={amount}", [_AMT(0.4)], ["mirror"]),
    _fx("pixel_pulse", "Pixel pulse", "glitch", "pixelize=w={size:int}:h={size:int}:enable='lt(mod(t\\,{period})\\,0.12)'", [P(name="size", label="block", min=4, max=60, default=24, step=2), P(name="period", label="हर (s)", min=0.4, max=4, default=1.5, step=0.1)], ["8bit", "beat"]),
    _fx("digital_noise_color", "Color noise", "glitch", "noise=c0s={amount:int}:c1s={amount:int}:c2s={amount:int}:allf=t", [P(name="amount", label="मात्रा", min=5, max=60, default=18, step=1)], ["noise"]),
    _fx("datamosh", "Datamosh (smear)", "glitch", "tmix=frames=4:weights='1 1 2 4',chromashift=cbh=4", [], ["smear"]),
    # blur & focus
    _fx("box_blur", "Box blur", "blur", "boxblur={r:int}:1", [P(name="r", label="कितना", min=1, max=30, default=6, step=1)], ["blur"], "blur({r:px0.3})"),
    _fx("dreamy", "Dreamy", "blur", "split[dra][drb];[drb]gblur=sigma=12[drc];[dra][drc]blend=all_mode=screen:all_opacity={amount}", [_AMT(0.35)], ["soft", "glow"], "brightness(1.05) contrast(0.95)"),
    _fx("vignette_blur", "Edge blur (बीच साफ़)", "blur", "split[vba][vbb];[vbb]gblur=sigma={sigma}[vbc];[vba][vbc]blend=all_expr='if(lt(hypot(X/W-0.5\\,Y/H-0.5)\\,{r:half01})\\,A\\,B)'", [P(name="sigma", label="blur", min=2, max=30, default=12, step=1), P(name="r", label="साफ़ गोला %", min=20, max=90, default=55, step=5)], ["focus", "bokeh"]),
    _fx("frosted", "Frosted glass", "blur", "gblur=sigma={sigma},noise=alls=10:allf=t,eq=brightness=0.05", [P(name="sigma", label="blur", min=2, max=20, default=8, step=1)], ["glass"]),
    _fx("zoom_blur", "Zoom blur", "blur", "split[zba][zbb];[zbb]scale=trunc({W}*1.08/2)*2:-2,crop={W}:{H},gblur=sigma=6[zbc];[zba][zbc]blend=all_mode=normal:all_opacity={amount}", [_AMT(0.45)], ["speed", "impact"]),
    _fx("soft_focus", "Soft focus", "blur", "split[sfa][sfb];[sfb]gblur=sigma=4[sfc];[sfa][sfc]blend=all_mode=normal:all_opacity={amount}", [_AMT(0.4)], ["portrait"], "blur(0.4px)"),
    # light & lens
    _fx("leak_warm", "Light leak warm", "light", _LEAK.replace("{X}", "iw*0.6").replace("{C}", "orange"), [_AMT(0.45)], ["leak", "film"], "sepia(0.15) brightness(1.06)"),
    _fx("leak_pink", "Light leak pink", "light", _LEAK.replace("{X}", "0").replace("{C}", "hotpink"), [_AMT(0.4)], ["leak"]),
    _fx("leak_blue", "Light leak cool", "light", _LEAK.replace("{X}", "iw*0.55").replace("{C}", "deepskyblue"), [_AMT(0.4)], ["leak", "cool"]),
    _fx("leak_moving", "Light leak (चलता)", "light", "split[lma][lmb];[lmb]drawbox=x='iw*(0.5+0.5*sin(t*0.7))-iw*0.2':y=0:w=iw*0.4:h=ih:color=orange@0.9:t=fill,gblur=sigma=120[lmc];[lma][lmc]blend=all_mode=screen:all_opacity={amount}", [_AMT(0.45)], ["leak", "film burn"]),
    _fx("film_burn", "Film burn", "light", "split[fba][fbb];[fbb]drawbox=x=0:y=0:w=iw:h=ih:color=orangered@0.9:t=fill,gblur=sigma=60[fbc];[fba][fbc]blend=all_expr='min(255\\,A+B*{amount}*max(0\\,sin(T*1.3)))'", [_AMT(0.6)], ["burn", "transition"]),
    _fx("bloom", "Bloom (चमक)", "light", "split[bla][blb];[blb]lutyuv=y='if(gt(val\\,180)\\,val\\,0)',gblur=sigma=25[blc];[bla][blc]blend=all_mode=screen:all_opacity={amount}", [_AMT(0.7)], ["glow", "highlights"], "brightness(1.06)"),
    _fx("spotlight", "Spotlight", "light", "vignette=angle=PI/2.5:mode=forward,eq=brightness=0.04:contrast=1.1", [], ["focus", "stage"]),
    _fx("sun_glow", "Sun glow", "light", "split[sga][sgb];[sgb]drawbox=x=iw*0.65:y=0:w=iw*0.35:h=ih*0.35:color=yellow@0.9:t=fill,gblur=sigma=150[sgc];[sga][sgc]blend=all_mode=screen:all_opacity={amount}", [_AMT(0.5)], ["sunny", "flare"]),
    _fx("neon_edges", "Neon edges", "light", "split[nea][neb];[neb]edgedetect=low=0.08:high=0.3:mode=colormix,eq=saturation=2,gblur=sigma=2[nec];[nea][nec]blend=all_mode=screen:all_opacity={amount}", [_AMT(0.8)], ["neon", "outline"]),
    _fx("flash_pulse", "White flash pulse", "light", "eq=brightness='{amount:n0.5}*max(0\\,1-mod(t\\,{period})*6)':eval=frame", [_AMT(0.6), P(name="period", label="हर (s)", min=0.4, max=4, default=1, step=0.1)], ["beat", "flash"]),
    _fx("fisheye", "Fisheye", "light", "lenscorrection=k1=-0.35:k2=0.1", [], ["lens"]),
    # film & vintage
    _fx("super8", "Super 8", "film", "curves=vintage,noise=alls=25:allf=t,vignette=PI/3.5,eq=saturation=0.85", [], ["8mm", "home video"], "sepia(0.35) contrast(1.05)"),
    _fx("cinema_239", "Cinema 2.39:1 bars", "film", "drawbox=x=0:y=0:w=iw:h=ih*0.12:color=black:t=fill,drawbox=x=0:y=ih*0.88:w=iw:h=ih*0.12:color=black:t=fill", [], ["bars"]),
    _fx("frame_jitter", "Projector jitter", "film", "crop=iw-8:ih-8:'4+3*sin(t*13)':'4+3*cos(t*17)',scale=iw+8:ih+8", [], ["film", "old"]),
    _fx("kodak_warm", "Kodak warm", "film", "colorbalance=rs=0.08:gs=0.03:bs=-0.06:rh=0.05:bh=-0.05,eq=contrast=1.06:saturation=1.08", [], ["warm"], "sepia(0.12) saturate(1.08)"),
    _fx("bleach_fx", "Bleach bypass", "film", "eq=saturation=0.55:contrast=1.3", [], ["desaturated"], "saturate(0.55) contrast(1.3)"),
    _fx("faded_film", "Faded film", "film", "curves=m='0/0.12 1/0.92',eq=saturation=0.85", [], ["matte"], "contrast(0.88) saturate(0.85)"),
    _fx("cross_process", "Cross process", "film", "curves=cross_process", [], ["color"]),
    _fx("lomo_fx", "Lomo", "film", "curves=lighter,vignette=PI/3,eq=saturation=1.3", [], ["vignette"], "saturate(1.3)"),
    _fx("sepia_old", "Old photo", "film", "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,noise=alls=12:allf=t,vignette=PI/4", [], ["sepia"], "sepia(0.9)"),
    _fx("black_flash", "Black dip pulse", "film", "eq=brightness='-{amount:n0.6}*max(0\\,1-mod(t\\,{period})*5)':eval=frame", [_AMT(0.5), P(name="period", label="हर (s)", min=0.5, max=5, default=2, step=0.1)], ["dip"]),
    # motion & camera
    _fx("earthquake", "Earthquake", "motion", "crop=iw-40:ih-40:'20+18*sin(t*53)':'20+18*cos(t*47)',scale=iw+40:ih+40", [], ["shake", "impact"]),
    _fx("wobble", "Wobble", "motion", "rotate='{deg:n0.0175}*sin(t*3)':c=black@0:ow=iw:oh=ih,scale=iw*1.06:ih*1.06,crop=iw/1.06:ih/1.06", [P(name="deg", label="डिग्री", min=0.5, max=6, default=2, step=0.5)], ["drunk", "sway"]),
    _fx("zoom_pulse", "Zoom pulse (beat)", "motion", "scale=w='trunc({W}*(1+{amount:n0.08}*max(0\\,1-mod(t\\,{period})*4))/2)*2':h=-2:eval=frame,crop={W}:{H}", [_AMT(0.6), P(name="period", label="हर (s)", min=0.3, max=3, default=0.6, step=0.05)], ["beat", "bounce"]),
    _fx("pan_right", "Slow pan →", "motion", "scale=iw*1.15:ih*1.15,crop=iw/1.15:ih/1.15:'(iw-ow)*min(1\\,t/{seconds})':(ih-oh)/2", [P(name="seconds", label="सेकंड", min=2, max=30, default=10, step=1)], ["kenburns"]),
    _fx("pan_left", "Slow pan ←", "motion", "scale=iw*1.15:ih*1.15,crop=iw/1.15:ih/1.15:'(iw-ow)*(1-min(1\\,t/{seconds}))':(ih-oh)/2", [P(name="seconds", label="सेकंड", min=2, max=30, default=10, step=1)], ["kenburns"]),
    _fx("zoom_out_slow", "Slow zoom out", "motion", "zoompan=z='{amount}-({amount}-1)*min(1\\,on/({seconds}*{FPS}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}", [P(name="amount", label="से", min=1.05, max=1.5, default=1.2, step=0.01), P(name="seconds", label="सेकंड", min=1, max=30, default=6, step=1)], ["kenburns"]),
    _fx("flip_v", "Flip upside down", "motion", "vflip", [], ["flip"]),
    _fx("kaleido", "Mirror split", "motion", "split[kla][klb];[kla]crop=iw/2:ih:0:0[kll];[klb]crop=iw/2:ih:0:0,hflip[klr];[kll][klr]hstack", [], ["symmetry"]),
    _fx("split2", "Split screen ×2", "motion", "split[s2a][s2b];[s2a]crop=iw/2:ih:iw/4:0[s2l];[s2b]crop=iw/2:ih:iw/4:0[s2r];[s2l][s2r]hstack", [], ["duplicate"]),
    _fx("grid4", "Grid ×4", "motion", "scale=iw/2:ih/2,split=4[g4a][g4b][g4c][g4d];[g4a][g4b]hstack[g4t];[g4c][g4d]hstack[g4u];[g4t][g4u]vstack", [], ["multi"]),
    _fx("speed_lines", "Speed lines", "motion", "split[sla][slb];[slb]gblur=sigma=20:sigmaV=0.5[slc];[sla][slc]blend=all_mode=lighten:all_opacity={amount}", [_AMT(0.5)], ["anime", "fast"]),
    # stylized
    _fx("cartoon", "Cartoon", "stylized", "split[cta][ctb];[cta]lutyuv=y='trunc(val/40)*40',eq=saturation=1.5[ctc];[ctb]edgedetect=low=0.1:high=0.3,negate[ctd];[ctc][ctd]blend=all_mode=multiply", [], ["comic", "toon"]),
    _fx("pencil", "Pencil sketch", "stylized", "edgedetect=low=0.05:high=0.2:mode=wires,negate,hue=s=0", [], ["sketch", "drawing"], "grayscale(1) contrast(1.6) brightness(1.2)"),
    _fx("thermal", "Thermal camera", "stylized", "hue=s=0,pseudocolor=preset=turbo", [], ["heat", "infrared"]),
    _fx("magma", "Magma", "stylized", "hue=s=0,pseudocolor=preset=magma", [], ["false color"]),
    _fx("night_vision", "Night vision", "stylized", "hue=s=0,colorchannelmixer=rr=0.2:gg=1.2:bb=0.2,noise=alls=25:allf=t,vignette=PI/3", [], ["green", "spy"]),
    _fx("xray", "X-ray", "stylized", "hue=s=0,negate,eq=contrast=1.3", [], ["invert"], "grayscale(1) invert(1) contrast(1.3)"),
    _fx("solarize", "Solarize", "stylized", "lutyuv=y='if(gt(val\\,128)\\,255-val\\,val)'", [], ["psychedelic"]),
    _fx("emboss", "Emboss", "stylized", "convolution='-2 -1 0 -1 1 1 0 1 2:-2 -1 0 -1 1 1 0 1 2:-2 -1 0 -1 1 1 0 1 2:-2 -1 0 -1 1 1 0 1 2'", [], ["relief"]),
    _fx("pop_art", "Pop art", "stylized", "lutyuv=y='trunc(val/64)*64',eq=saturation=2.2:contrast=1.2", [], ["warhol"], "saturate(2.2) contrast(1.2)"),
    _fx("gameboy", "Retro handheld", "stylized", "pixelize=w=6:h=6,hue=s=0,colorchannelmixer=rr=0.6:gg=0.9:bb=0.3", [], ["8bit", "green"]),
    _fx("cyber_tint", "Cyber tint", "stylized", "colorbalance=rs=-0.2:bs=0.25:rh=0.25:bh=0.1,eq=contrast=1.15:saturation=1.3", [], ["neon"], "hue-rotate(-20deg) saturate(1.3)"),
    _fx("color_isolate", "Color pop (लाल रहे)", "stylized", "colorhold=color=red:similarity={amount:n0.4}:blend=0.1", [_AMT(0.6)], ["splash", "selective"]),
    {**_fx("color_pop", "Color Pop (इंसान रंगीन, बाकी B&W)", "portrait", "__color_pop__", [], ["colorpop", "bw_bg", "person_color"],
           "grayscale(0.6)"), "needs_matte": True},
    _fx("noir", "Noir", "stylized", "hue=s=0,eq=contrast=1.45:brightness=-0.03,vignette=PI/3", [], ["bw"], "grayscale(1) contrast(1.45)"),
    _fx("high_key", "High key", "stylized", "eq=brightness=0.12:contrast=0.85:saturation=0.8", [], ["bright"], "brightness(1.12) contrast(0.85)"),
    # portrait
    _fx("glam", "Glam (smooth + glow)", "portrait", "hqdn3d=4:3:6:6,split[gma][gmb];[gmb]gblur=sigma=8[gmc];[gma][gmc]blend=all_mode=screen:all_opacity=0.18", [], ["beauty"], "brightness(1.04)"),
    _fx("face_brighten", "Face brighten", "portrait", "eq=gamma=1.12:brightness=0.02", [], ["light"], "brightness(1.06)"),
    _fx("matte_skin", "Matte skin", "portrait", "hqdn3d=3:2:4:4,curves=m='0/0.04 0.5/0.5 1/0.94'", [], ["soft"]),
    _fx("vivid_eyes", "Crisp details", "portrait", "unsharp=7:7:1.2:7:7:0,eq=contrast=1.04", [], ["sharp"]),
    # texture
    _fx("crt", "CRT TV", "texture", "drawgrid=w=iw:h=3:t=1:c=black@0.35,curves=strong_contrast,vignette=PI/3.5,chromashift=crh=2:cbh=-2", [], ["tv", "retro"]),
    _fx("lcd", "LCD screen", "texture", "drawgrid=w=3:h=3:t=1:c=black@0.3", [], ["pixels"]),
    _fx("paper", "Paper texture", "texture", "noise=alls=14:allf=u,eq=saturation=0.8:brightness=0.03,colorbalance=rs=0.04:bs=-0.04", [], ["print"]),
    _fx("grid_lines", "Grid", "texture", "drawgrid=w=iw/6:h=ih/10:t=1:c=white@0.25", [], ["design"]),
    _fx("dust_heavy", "Heavy dust", "texture", "noise=c0s=45:c0f=t+p,vignette=PI/4", [], ["film"]),
    _fx("border_white", "White border", "texture", "pad=iw+iw*0.06:ih+iw*0.06:iw*0.03:iw*0.03:white,scale={W}:{H}", [], ["frame"]),
    _fx("border_black", "Black border", "texture", "pad=iw+iw*0.06:ih+iw*0.06:iw*0.03:iw*0.03:black,scale={W}:{H}", [], ["frame"]),
    _fx("rounded_frame", "Vignette frame", "texture", "vignette=angle=PI/2.2", [], ["soft frame"]),
]

CATEGORIES = {"glitch": "Glitch", "blur": "Blur & focus", "light": "Light & lens", "film": "Film & vintage",
              "motion": "Motion & camera", "stylized": "Stylized", "portrait": "Portrait", "background": "Background",
              "texture": "Texture"}
# 🔥 trending pack (engine/trending.py): animated, duration-aware effects built from ffmpeg filters only
from .trending import TRENDING  # noqa: E402
EFFECTS += TRENDING
CATEGORIES = {"trending": "🔥 Trending", **CATEGORIES}
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
    P(name="tone_shadows", label="Shadows tone (teal ↔ warm)", min=-1, max=1, default=0, step=0.02),
    P(name="tone_highlights", label="Highlights tone (cool ↔ warm)", min=-1, max=1, default=0, step=0.02),
    P(name="grain", label="Film grain", min=0, max=1, default=0, step=0.02),
]
GRADE_DEFAULT = {p["name"]: p["default"] for p in GRADE_PARAMS}

_G = [  # id, label, category, params — every look is just numbers for the sliders (editable after picking)
    # Cinematic
    ("teal_orange", "Teal & Orange", "cinematic", dict(temperature=.2, tint=-.05, contrast=.12, saturation=.1, shadows=-.1, highlights=.05, tone_shadows=-.45, tone_highlights=.35)),
    ("cool_cinema", "Cool Cinema", "cinematic", dict(temperature=-.3, contrast=.15, saturation=-.12, shadows=-.08, vignette=.3)),
    ("blockbuster", "Blockbuster", "cinematic", dict(contrast=.25, saturation=.05, tone_shadows=-.5, tone_highlights=.4, vignette=.25, sharpness=.2)),
    ("noir_teal", "Noir Teal", "cinematic", dict(exposure=-.15, contrast=.3, saturation=-.35, tone_shadows=-.6, blacks=-.15, vignette=.4)),
    ("desert", "Desert Heat", "cinematic", dict(temperature=.45, contrast=.12, saturation=-.05, highlights=-.1, tone_highlights=.4, fade=.08)),
    ("arctic", "Arctic", "cinematic", dict(temperature=-.45, exposure=.08, saturation=-.2, whites=.1, tone_shadows=-.3)),
    ("matrix", "Matrix Green", "cinematic", dict(tint=-.35, contrast=.2, saturation=-.25, tone_shadows=-.2, vignette=.3)),
    ("bleach", "Bleach Bypass", "cinematic", dict(saturation=-.45, contrast=.35, highlights=.1, blacks=-.15, sharpness=.25)),
    ("kodak2383", "Film Print 2383", "cinematic", dict(contrast=.2, tone_shadows=-.25, tone_highlights=.3, saturation=.05, blacks=-.08, grain=.15)),
    ("eterna", "Eterna", "cinematic", dict(contrast=-.1, saturation=-.2, fade=.1, tone_shadows=-.2, tone_highlights=.15)),
    ("cyberpunk", "Cyberpunk", "cinematic", dict(tint=.3, temperature=-.25, contrast=.25, vibrance=.35, tone_shadows=-.4, tone_highlights=-.2)),
    ("dune", "Dune Gold", "cinematic", dict(temperature=.5, saturation=-.15, contrast=.15, fade=.1, tone_highlights=.5)),
    ("interstellar", "Space Drama", "cinematic", dict(temperature=-.1, contrast=.22, saturation=-.25, blacks=-.2, vignette=.35)),
    ("epic_dark", "Epic Dark", "cinematic", dict(exposure=-.2, contrast=.3, saturation=-.1, tone_shadows=-.35, vignette=.5)),
    # Film / vintage
    ("warm_film", "Warm Film", "film", dict(temperature=.3, contrast=.06, fade=.12, saturation=-.05, vignette=.25, grain=.15)),
    ("vintage_fade", "Vintage Fade", "film", dict(fade=.3, saturation=-.25, temperature=.15, contrast=-.05, vignette=.35, grain=.2)),
    ("polaroid", "Polaroid", "film", dict(fade=.22, temperature=.18, tint=.08, contrast=-.08, highlights=-.1, grain=.15)),
    ("kodachrome", "Kodachrome", "film", dict(contrast=.18, saturation=.2, temperature=.1, blacks=-.1, grain=.1)),
    ("portra", "Portra", "film", dict(temperature=.12, saturation=-.08, contrast=-.05, fade=.08, tone_highlights=.2, grain=.12)),
    ("ektar", "Ektar Vivid", "film", dict(saturation=.25, contrast=.12, vibrance=.15, temperature=.05)),
    ("super8", "Super 8", "film", dict(temperature=.35, fade=.18, saturation=-.1, vignette=.5, grain=.45, contrast=.05)),
    ("seventies", "70s", "film", dict(temperature=.4, tint=.1, fade=.2, saturation=-.15, grain=.25)),
    ("vhs80s", "80s VHS", "film", dict(tint=.12, saturation=.2, contrast=-.1, fade=.15, grain=.35, sharpness=0)),
    ("sepia", "Sepia", "film", dict(saturation=-.75, temperature=.55, fade=.12, contrast=.05, grain=.15)),
    ("matte", "Faded Matte", "film", dict(fade=.35, contrast=-.12, saturation=-.1)),
    ("cross", "Cross Process", "film", dict(tint=-.2, contrast=.25, saturation=.2, tone_shadows=-.4, tone_highlights=.4)),
    ("lomo", "Lomo", "film", dict(saturation=.3, contrast=.25, vignette=.7, temperature=.1)),
    ("expired", "Expired Film", "film", dict(tint=.2, temperature=.2, fade=.25, saturation=-.2, grain=.35)),
    # Portrait / skin
    ("natural_skin", "Natural Skin", "portrait", dict(temperature=.08, vibrance=.08, saturation=-.04, contrast=.04)),
    ("soft_glow", "Soft Glow", "portrait", dict(exposure=.12, contrast=-.12, highlights=.1, fade=.06, saturation=-.05)),
    ("peach", "Peach", "portrait", dict(temperature=.18, tint=.1, exposure=.06, saturation=-.05)),
    ("rosy", "Rosy", "portrait", dict(tint=.18, temperature=.06, vibrance=.1)),
    ("bronze", "Bronze", "portrait", dict(temperature=.3, contrast=.12, saturation=-.1, tone_highlights=.3)),
    ("porcelain", "Porcelain", "portrait", dict(exposure=.15, temperature=-.08, saturation=-.15, contrast=-.05)),
    ("golden_skin", "Golden Skin", "portrait", dict(temperature=.25, vibrance=.12, highlights=-.08)),
    ("studio_clean", "Studio Clean", "portrait", dict(contrast=.08, whites=.1, sharpness=.25, vibrance=.05)),
    ("beauty", "Beauty", "portrait", dict(exposure=.1, contrast=-.08, saturation=-.06, tint=.05, highlights=.05)),
    ("warm_portrait", "Warm Portrait", "portrait", dict(temperature=.2, contrast=.06, shadows=.1)),
    ("cool_portrait", "Cool Portrait", "portrait", dict(temperature=-.15, contrast=.08, saturation=-.08)),
    ("fresh_face", "Fresh", "portrait", dict(exposure=.08, vibrance=.18, contrast=.05)),
    # Vlog / bright
    ("clean_commercial", "Clean Commercial", "bright", dict(exposure=.1, contrast=.08, whites=.1, vibrance=.15, sharpness=.3)),
    ("bright_airy", "Bright & Airy", "bright", dict(exposure=.25, contrast=-.12, highlights=.1, saturation=-.08, fade=.05)),
    ("pop_vlog", "Pop Vlog", "bright", dict(vibrance=.35, contrast=.12, exposure=.05, sharpness=.2)),
    ("sunny", "Sunny Day", "bright", dict(temperature=.2, exposure=.12, vibrance=.2)),
    ("fresh_day", "Fresh Day", "bright", dict(temperature=-.05, vibrance=.2, exposure=.08, contrast=.06)),
    ("yt_pop", "YouTube Pop", "bright", dict(contrast=.18, saturation=.18, sharpness=.3, shadows=.08)),
    ("punchy", "Punchy", "bright", dict(contrast=.3, vibrance=.25, blacks=-.1)),
    ("crisp", "Crisp", "bright", dict(sharpness=.5, contrast=.12, whites=.08)),
    ("clear_sky", "Clear Sky", "bright", dict(temperature=-.12, vibrance=.25, highlights=-.12)),
    ("white_studio", "White Studio", "bright", dict(exposure=.2, whites=.2, saturation=-.1, contrast=-.05)),
    # Moody / dark
    ("moody", "Moody Contrast", "moody", dict(exposure=-.2, contrast=.3, saturation=-.2, blacks=-.2, vignette=.45)),
    ("dark_teal", "Dark Teal", "moody", dict(exposure=-.15, tone_shadows=-.6, saturation=-.2, contrast=.2)),
    ("shadow_play", "Shadow Play", "moody", dict(shadows=-.3, contrast=.25, vignette=.5)),
    ("rainy", "Rainy Day", "moody", dict(temperature=-.25, saturation=-.3, fade=.12, contrast=-.05)),
    ("gloomy", "Gloomy", "moody", dict(exposure=-.1, saturation=-.4, temperature=-.1, fade=.1)),
    ("stormy", "Stormy", "moody", dict(contrast=.3, saturation=-.35, temperature=-.2, blacks=-.15, vignette=.4)),
    ("deep_blue", "Deep Blue", "moody", dict(temperature=-.4, exposure=-.12, contrast=.15, tone_shadows=-.4)),
    ("crimson", "Crimson Dark", "moody", dict(tint=.25, temperature=.15, exposure=-.15, contrast=.25, saturation=-.1, vignette=.4)),
    ("forest_dark", "Dark Forest", "moody", dict(tint=-.25, exposure=-.15, saturation=-.15, contrast=.2)),
    ("midnight", "Midnight", "moody", dict(exposure=-.3, temperature=-.35, saturation=-.2, contrast=.15, vignette=.5)),
    # Nature / travel
    ("golden_hour", "Golden Hour", "nature", dict(temperature=.45, exposure=.05, highlights=-.1, saturation=.1, vignette=.2)),
    ("green_lush", "Green Lush", "nature", dict(tint=-.15, vibrance=.35, contrast=.08)),
    ("ocean", "Ocean", "nature", dict(temperature=-.25, vibrance=.3, contrast=.1, hue=-4)),
    ("mountain", "Mountain", "nature", dict(contrast=.18, saturation=-.05, temperature=-.1, sharpness=.3, highlights=-.15)),
    ("autumn", "Autumn", "nature", dict(temperature=.35, hue=-6, saturation=.15, contrast=.1)),
    ("spring", "Spring", "nature", dict(tint=-.08, vibrance=.25, exposure=.1, contrast=-.04)),
    ("tropical", "Tropical", "nature", dict(vibrance=.45, saturation=.1, temperature=.08, contrast=.1)),
    ("sunset", "Sunset Orange", "nature", dict(temperature=.6, tint=.1, saturation=.15, contrast=.12)),
    ("misty", "Misty", "nature", dict(fade=.25, contrast=-.2, saturation=-.15, exposure=.08)),
    ("sand", "Desert Sand", "nature", dict(temperature=.35, saturation=-.1, fade=.08, contrast=.08)),
    # Night / neon
    ("night_neon", "Night Neon", "neon", dict(exposure=-.1, contrast=.25, vibrance=.4, temperature=-.2, tint=.15, blacks=-.2)),
    ("neon_pink", "Neon Pink", "neon", dict(tint=.35, vibrance=.4, contrast=.2, temperature=-.1)),
    ("neon_blue", "Neon Blue", "neon", dict(temperature=-.5, vibrance=.4, contrast=.2)),
    ("city_night", "City Night", "neon", dict(temperature=-.2, contrast=.2, tone_highlights=.4, blacks=-.15)),
    ("purple_haze", "Purple Haze", "neon", dict(tint=.3, temperature=-.25, fade=.1, saturation=.1)),
    ("tokyo", "Tokyo Night", "neon", dict(temperature=-.3, tint=.2, contrast=.25, vibrance=.3, tone_shadows=-.3)),
    ("vapor", "Vaporwave", "neon", dict(tint=.35, temperature=-.15, fade=.18, vibrance=.25)),
    ("club", "Club Lights", "neon", dict(vibrance=.55, contrast=.3, exposure=-.1, blacks=-.2)),
    # B&W
    ("bw", "Black & White", "bw", dict(saturation=-1, contrast=.2, blacks=-.1)),
    ("bw_high", "B&W High Contrast", "bw", dict(saturation=-1, contrast=.45, blacks=-.25, whites=.15)),
    ("bw_soft", "B&W Soft", "bw", dict(saturation=-1, contrast=-.1, fade=.15)),
    ("bw_noir", "Noir", "bw", dict(saturation=-1, contrast=.4, exposure=-.15, vignette=.6, grain=.3)),
    ("selenium", "Selenium", "bw", dict(saturation=-.95, tint=.08, temperature=-.05, contrast=.2)),
    ("cyanotype", "Cyanotype", "bw", dict(saturation=-.9, temperature=-.6, contrast=.15)),
    ("sepia_mono", "Sepia Mono", "bw", dict(saturation=-.9, temperature=.5, contrast=.1, grain=.2)),
    ("silver", "Silver", "bw", dict(saturation=-1, exposure=.1, contrast=.15, whites=.15, sharpness=.3)),
    # Pastel / soft
    ("soft_pastel", "Soft Pastel", "pastel", dict(exposure=.15, contrast=-.15, saturation=-.1, fade=.2, temperature=.05)),
    ("dreamy", "Dreamy", "pastel", dict(exposure=.18, contrast=-.2, fade=.15, highlights=.15, saturation=-.1)),
    ("cotton_candy", "Cotton Candy", "pastel", dict(tint=.2, temperature=-.05, fade=.2, exposure=.1)),
    ("mint", "Mint", "pastel", dict(tint=-.2, temperature=-.1, fade=.18, exposure=.1)),
    ("lavender", "Lavender", "pastel", dict(tint=.18, temperature=-.2, fade=.15, saturation=-.1)),
    ("baby_blue", "Baby Blue", "pastel", dict(temperature=-.25, exposure=.12, fade=.15, saturation=-.15)),
    ("cream", "Cream", "pastel", dict(temperature=.2, fade=.2, contrast=-.1, saturation=-.15)),
    ("haze", "Haze", "pastel", dict(fade=.3, exposure=.12, contrast=-.2)),
    # Indian / festive
    ("wedding_gold", "Wedding Gold", "indian", dict(temperature=.35, vibrance=.2, highlights=-.08, tone_highlights=.4, vignette=.2)),
    ("haldi", "Haldi Yellow", "indian", dict(temperature=.4, tint=-.05, vibrance=.3, exposure=.08)),
    ("holi", "Holi Colours", "indian", dict(vibrance=.6, saturation=.2, contrast=.15)),
    ("diwali", "Diwali Glow", "indian", dict(temperature=.45, exposure=-.05, vibrance=.3, vignette=.35, tone_highlights=.5)),
    ("saffron", "Saffron", "indian", dict(temperature=.3, tint=.08, saturation=.15, contrast=.1)),
    ("royal_maroon", "Royal Maroon", "indian", dict(tint=.2, temperature=.2, contrast=.2, saturation=.05, vignette=.3)),
    ("mehendi", "Mehendi Green", "indian", dict(tint=-.2, temperature=.15, vibrance=.25)),
    ("temple", "Temple Warm", "indian", dict(temperature=.4, contrast=.15, fade=.06, vignette=.35)),
    ("monsoon", "Monsoon", "indian", dict(tint=-.15, temperature=-.2, saturation=.05, contrast=.1, fade=.06)),
    ("bolly90s", "90s Bollywood", "indian", dict(temperature=.2, saturation=.25, fade=.12, contrast=-.05, grain=.2)),
    # Food
    ("food_warm", "Food Warm", "food", dict(temperature=.25, vibrance=.3, contrast=.12, sharpness=.3)),
    ("food_fresh", "Food Fresh", "food", dict(vibrance=.35, exposure=.1, sharpness=.35)),
    ("dessert", "Dessert", "food", dict(exposure=.12, tint=.08, fade=.1, saturation=.05)),
    ("coffee", "Coffee", "food", dict(temperature=.3, contrast=.15, saturation=-.15, vignette=.3)),
    ("spicy", "Spicy", "food", dict(temperature=.3, tint=.1, vibrance=.4, contrast=.15)),
    ("bakery", "Bakery", "food", dict(temperature=.3, fade=.1, exposure=.08)),
    # Neutral
    ("documentary", "Documentary Neutral", "neutral", dict(contrast=.04, saturation=-.02, sharpness=.2)),
    ("rec709", "Rec.709 Clean", "neutral", dict(contrast=.06)),
    ("log_fix", "Flat → Normal (Log fix)", "neutral", dict(contrast=.35, saturation=.25, blacks=-.12, whites=.1)),
    ("low_light_fix", "Low light fix", "neutral", dict(exposure=.35, shadows=.25, contrast=.05, sharpness=.15)),
    ("overexposed_fix", "Overexposed fix", "neutral", dict(exposure=-.3, highlights=-.3, contrast=.08)),
]
GRADE_CATS = {"cinematic": "Cinematic", "film": "Film / Vintage", "portrait": "Portrait / Skin", "bright": "Vlog / Bright",
              "moody": "Moody / Dark", "nature": "Nature / Travel", "neon": "Night / Neon", "bw": "Black & White",
              "pastel": "Pastel / Soft", "indian": "Indian / त्योहार", "food": "Food", "neutral": "Neutral / Fix"}
GRADE_PRESETS: dict[str, dict] = {gid: {"label": label, "cat": cat, **params} for gid, label, cat, params in _G}


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
    if v["tone_shadows"] or v["tone_highlights"]:
        # split toning: + warm (orange), − cool (teal/blue)
        ts, th = v["tone_shadows"] * .25, v["tone_highlights"] * .2
        parts.append(f"colorbalance=rs={ts:.3f}:gs={ts * .2:.3f}:bs={-ts:.3f}:rh={th:.3f}:gh={th * .3:.3f}:bh={-th:.3f}")
    if v["sharpness"]:
        parts.append(f"unsharp=5:5:{v['sharpness'] * 1.5:.2f}:5:5:0")
    if v["grain"]:
        parts.append(f"noise=alls={int(v['grain'] * 22)}:allf=t")
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


def _effect_chain(e: dict, params: dict, ctx: dict) -> str:
    if e.get("build"):
        return e["build"]({**params}, ctx)
    return _apply(e["ffmpeg"], {**ctx, **params})


def stack_filter(stack: list[dict] | None, w: int = 1080, h: int = 1920, fps: float = 30, dur: float | None = None) -> str:
    """[{id, params, enabled, kf?}] → ffmpeg chain (export). W/H/FPS/DUR of the output frame / clip are
    available to templates and builders. `kf` ({param: keyframes}) animates numeric params (stepped)."""
    parts = []
    ctx = {"W": w, "H": h, "FPS": int(round(fps)), "DUR": float(dur or 5.0)}
    for item in stack or []:
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        e = BY_ID.get(item.get("id"))
        if not e or not (e.get("ffmpeg") or e.get("build")):
            continue
        base = _clean_params(e, item.get("params"))
        kf = None
        if item.get("kf"):
            from . import keyframes as K
            kf = {k: v for k, v in K.norm_map(item["kf"]).items() if k in base and not isinstance(base[k], str) and K.animated(v)}
        if kf:
            from . import keyframes as K
            f = K.stepped("", "", ctx["DUR"], fps, lambda t, e=e, base=base, kf=kf: _effect_chain(e, _clean_params(e, K.params_at(base, kf, t)), ctx),
                          uid=f"kfs{len(parts)}")
        else:
            f = _effect_chain(e, base, ctx)
        idx = len(parts)
        parts.append(re.sub(r"\[([A-Za-z]\w*)\]", lambda m: f"[{m.group(1)}_{idx}]", f))
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
            "effects": [{k: v for k, v in e.items() if k not in ("ffmpeg", "build")} for e in EFFECTS],
            "grade_params": GRADE_PARAMS, "grade_cats": GRADE_CATS,
            "grade_presets": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in GRADE_PRESETS.items()}}
