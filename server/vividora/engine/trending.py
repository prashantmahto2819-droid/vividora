"""🔥 Trending pack — CapCut / Instagram-trend style animated effects, built only from ffmpeg
filters (no stock footage, nothing to license).

Every effect is an ordinary catalog effect (category "trending") with a `build(params, ctx)`
function instead of a template; ctx = {W, H, FPS, DUR}. Use them like any effect:
  * as a time-ranged effect clip  fxclips: [{"kind": "effect", "id": "tr_glitch", "params": {...}, "start", "end"}]
    → t runs 0…DUR inside the clip, so in/out animations follow the clip length;
  * in the global stack, on an overlay clip's own stack, etc.
The relative render cost is in each effect's "cost" (1 = cheap, 3 = heavy) and documented in
docs/editor-schema.md.
"""

from __future__ import annotations

import math

P = dict


def _p(name, label, lo, hi, d, step):
    return P(name=name, label=label, min=lo, max=hi, default=d, step=step)


def _amt(d=0.6):
    return _p("amount", "मात्रा · Amount", 0.05, 1.0, d, 0.05)


def _ev(x: int) -> int:
    return max(2, int(x) // 2 * 2)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    s = str(hex_color or "#ffffff").lstrip("#")
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except (ValueError, IndexError):
        return 255, 255, 255


def _shift_planes(W: int, H: int, d_expr: str, margin: int) -> str:
    """RGB split: red plane moved right by d(t), blue left (true per-plane shift, any amount)."""
    m = margin
    # extractplanes emits its outputs in fixed r, g, b order whatever the flag order
    return (f"format=gbrp,extractplanes=r+g+b[tr][tg][tb];"
            f"[tr]pad=iw+{2 * m}:ih:{m}:0,crop={W}:{H}:'{m}-({d_expr})':0[tr2];"
            f"[tb]pad=iw+{2 * m}:ih:{m}:0,crop={W}:{H}:'{m}+({d_expr})':0[tb2];"
            f"[tg][tb2][tr2]mergeplanes=0x001020:gbrp,format=yuv420p")


# ---------------------------------------------------------------- builders
def b_beat_shake(p, c):
    W, H = c["W"], c["H"]
    A = W * p["amount"] / 100
    m = int(math.ceil(A * 1.6)) + 2
    P_ = 60.0 / p["bpm"]
    k = f"exp(-mod(t\\,{P_:.4f})*{p['decay']:.2f})"
    return (f"scale={_ev(W + 2 * m)}:{_ev(H + 2 * m)}:flags=bicubic,"
            f"crop={W}:{H}:'{m}+{A:.2f}*{k}*sin(t*83)':'{m}+{A:.2f}*{k}*cos(t*71)'")


def b_camera_shake(p, c):
    W, H = c["W"], c["H"]
    A = W * p["amount"] / 100
    s = p["speed"]
    rot = p["rotate"] * math.pi / 180
    m = int(math.ceil(A * 1.2 + max(W, H) * math.sin(rot) * 0.6)) + 4
    dx = f"{A:.2f}*(0.6*sin(t*{2.1 * s:.3f})+0.3*sin(t*{5.3 * s:.3f}+1)+0.1*sin(t*{13.1 * s:.3f}+2))"
    dy = f"{A:.2f}*(0.6*cos(t*{1.7 * s:.3f})+0.3*sin(t*{4.4 * s:.3f}+2)+0.1*cos(t*{11.3 * s:.3f}))"
    chain = f"scale={_ev(W + 2 * m)}:{_ev(H + 2 * m)}:flags=bicubic,"
    if rot > 0:
        chain += f"rotate='{rot:.5f}*sin(t*{1.3 * s:.3f})':c=black,"
    return chain + f"crop={W}:{H}:'{m}+{dx}':'{m}+{dy}'"


def b_glitch(p, c):
    W = c["W"]
    R, a = p["rate"], p["amount"]
    on = f"lt(mod(t*{R:.3f}\\,1)\\,{0.25 + 0.3 * a:.3f})"
    on2 = f"lt(mod(t*{R:.3f}+0.37\\,1)\\,{0.2 + 0.25 * a:.3f})"
    sh = int(16 + 50 * a)
    slice_y = f"ih*mod(floor(t*{R:.3f})*0.37\\,0.85)"
    return (f"split[ga][gb];[gb]crop=iw:ih/7:0:'{slice_y}'[gs];"
            f"[ga][gs]overlay=x='{W * 0.08 * a:.1f}*sin(floor(t*{R:.3f})*12.9898)':y='H*mod(floor(t*{R:.3f})*0.37\\,0.85)':enable='{on}',"
            f"rgbashift=rh={sh}:bh=-{sh}:gv={sh // 3}:enable='{on2}',"
            f"noise=alls={int(20 + 40 * a)}:allf=t:enable='{on}',"
            f"tmix=frames=3:weights='1 1 3':enable='{on2}'")


def b_rgb_split(p, c):
    A, S = p["amount"], p["speed"]
    d = f"{A:.2f}*(0.55+0.45*sin(t*{S * 6.2832:.4f}))"
    return _shift_planes(c["W"], c["H"], d, int(A) + 4)


def b_chroma_pulse(p, c):
    W, H = c["W"], c["H"]
    A, P_ = p["amount"], 60.0 / p["bpm"]
    k = f"exp(-mod(t\\,{P_:.4f})*7)"
    z = p["zoom"]
    chain = _shift_planes(W, H, f"{A:.2f}*{k}", int(A) + 4)
    if z > 0:
        chain += f",scale=w='trunc({W}*(1+{z:.3f}*{k})/2)*2':h=-2:eval=frame,crop={W}:{H}"
    return chain


def _zoom_layer(W, H, k, alpha, label, burst, dur):
    f = f"scale={_ev(W * k)}:{_ev(H * k)}:flags=bilinear,crop={W}:{H},gblur=sigma=1.5,format=yuva420p,colorchannelmixer=aa={alpha:.3f}"
    if burst:
        f += f",fade=t=in:st=0:d={dur / 2:.3f}:alpha=1,fade=t=out:st={dur / 2:.3f}:d={dur / 2:.3f}:alpha=1"
    return f + label


def b_zoom_blur(p, c):
    W, H, D = c["W"], c["H"], c["DUR"]
    a, burst = p["amount"], p["burst"] >= 0.5
    return (f"split=3[za][zb][zc];[zb]{_zoom_layer(W, H, 1 + 0.06 * a, 0.5, '[zb2]', burst, D)};"
            f"[zc]{_zoom_layer(W, H, 1 + 0.13 * a, 0.36, '[zc2]', burst, D)};"
            f"[za][zb2]overlay=format=auto[zab];[zab][zc2]overlay=format=auto,format=yuv420p")


def b_radial_blur(p, c):
    W, H, D = c["W"], c["H"], c["DUR"]
    ang = p["angle"] * math.pi / 180
    m = 1 + math.sin(ang) * 1.3
    spin = f"sin(PI*min(t/{D:.3f}\\,1))" if p["burst"] >= 0.5 else "1"

    def layer(sign, alpha, lab):
        return (f"scale={_ev(W * m)}:{_ev(H * m)},rotate='{sign}{ang:.5f}*{spin}':c=black,crop={W}:{H},format=yuva420p,"
                f"colorchannelmixer=aa={alpha}{lab}")
    return (f"split=3[ra][rb][rc];[rb]{layer('', 0.45, '[rb2]')};[rc]{layer('-', 0.33, '[rc2]')};"
            f"[ra][rb2]overlay=format=auto[rab];[rab][rc2]overlay=format=auto,format=yuv420p")


def b_motion_blur(p, c):
    n = int(p["frames"])
    return f"tmix=frames={n}"


def _gen_layer(c, colors: list[str], speed: float, fade_in: float, fade_out: float, seed: int, extra: str = "") -> str:
    W, H, D, F = c["W"], c["H"], c["DUR"], c["FPS"]
    cs = ":".join(f"c{i}={col}" for i, col in enumerate(colors))
    f = (f"gradients=s={W}x{H}:{cs}:n={len(colors)}:speed={speed:.4f}:d={D + 0.5:.3f}:r={F}:seed={seed}")
    if extra:
        f += "," + extra
    if fade_in > 0:
        f += f",fade=t=in:st=0:d={fade_in:.3f}"
    if fade_out > 0:
        f += f",fade=t=out:st={max(0.0, D - fade_out):.3f}:d={fade_out:.3f}"
    return f + ",format=gbrp"


def b_light_leak(p, c):
    D = c["DUR"]
    lay = _gen_layer(c, ["0xff5e00", "0xffc23d", "black", "0xff2a6d", "black"], 0.004 + 0.02 * p["speed"],
                     min(0.6, D / 4), min(0.6, D / 4), int(p["seed"]), "gblur=sigma=40")
    return f"format=gbrp[la];{lay}[lg];[la][lg]blend=all_mode=screen:all_opacity={p['amount']:.3f}:shortest=1,format=yuv420p"


def b_film_burn(p, c):
    D = c["DUR"]
    lay = _gen_layer(c, ["white", "0xffb000", "0xff3a00", "0x400000", "black"], 0.03 + 0.05 * p["speed"],
                     D * 0.45, D * 0.45, int(p["seed"]), "gblur=sigma=25,eq=brightness=0.08:contrast=1.4")
    return f"format=gbrp[fa];{lay}[fg];[fa][fg]blend=all_mode=screen:all_opacity={p['amount']:.3f}:shortest=1,format=yuv420p"


def b_vhs(p, c):
    H = c["H"]
    a = p["amount"]
    return (f"chromashift=cbh={int(2 + 6 * a)}:crh=-{int(2 + 6 * a)},gblur=sigma={0.6 + 1.2 * a:.2f}:sigmaV=0.1,"
            f"eq=saturation={1.1 + 0.3 * a:.2f}:contrast=0.95:brightness=0.02,noise=alls={int(8 + 22 * a)}:allf=t,"
            f"drawgrid=w=iw:h=4:t=1:c=black@{0.12 + 0.2 * a:.2f},"
            f"split[va][vb];[vb]crop=iw:{_ev(H * 0.04)}:0:'mod(t*{H * 0.35:.1f}\\,ih-{_ev(H * 0.04)})',eq=brightness=0.12,"
            f"noise=alls=60:allf=t[vt];[va][vt]overlay=x='{6 + 10 * a:.0f}*sin(t*30)':y='mod(t*{H * 0.35:.1f}\\,H-h)'")


def b_old_film(p, c):
    a = p["amount"]
    return ("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,"
            f"noise=alls={int(10 + 25 * a)}:allf=t+u,"
            f"eq=brightness='{0.05 * a:.3f}*sin(t*43)+{0.03 * a:.3f}*(random(1)-0.5)':contrast=1.08:eval=frame,"
            f"drawbox=x='iw*mod(t*7.31\\,1)':y=0:w=2:h=ih:color=white@{0.2 + 0.2 * a:.2f}:t=fill:enable='lt(mod(t*2.7\\,1)\\,0.4)',"
            f"drawbox=x='iw*mod(t*3.17+0.5\\,1)':y=0:w=1:h=ih:color=black@0.35:t=fill:enable='lt(mod(t*1.9\\,1)\\,0.5)',"
            f"vignette=PI/{4.5 - 1.5 * a:.2f},"
            f"crop=iw-8:ih-8:'4+{2 + 2 * a:.1f}*sin(t*13)':'4+{2 + 2 * a:.1f}*cos(t*17)',scale={c['W']}:{c['H']}")


def b_freeze(p, c):
    W, H, D, F = c["W"], c["H"], c["DUR"], c["FPS"]
    z, fl = p["zoom"], p["flash"]
    f = f"loop=loop=-1:size=1:start=0,setpts=N/{F}/TB,trim=duration={D:.3f}"
    if z > 1.001:
        u = f"min(1\\,t/{max(0.2, D * 0.6):.3f})"
        f += f",scale=w='trunc({W}*(1+({z:.3f}-1)*{u}*{u}*(3-2*{u}))/2)*2':h=-2:eval=frame,crop={W}:{H}"
    if fl > 0:
        f += f",eq=brightness='{0.7 * fl:.3f}*max(0\\,1-t*7)':eval=frame"
    return f


def b_flash(p, c):
    a, r = p["amount"], p["rate"]
    e = f"{0.8 * a:.3f}*max(0\\,1-t*{p['decay']:.2f})"
    if r > 0:
        e += f"+{0.6 * a:.3f}*lt(mod(t*{r:.3f}\\,1)\\,0.35)"
    return f"eq=brightness='min(1\\,{e})':eval=frame"


def b_zoom_3d(p, c):
    W, H, D, F = c["W"], c["H"], c["DUR"], c["FPS"]
    a = p["amount"]
    u = f"min(1\\,t/{D:.3f})"
    s = f"({u}*{u}*(3-2*{u}))"
    return (f"split[da][db];[da]scale=w='trunc({W}*(1+{0.22 * a:.4f}*{s})/2)*2':h=-2:eval=frame,crop={W}:{H},format=yuva420p[dfa];"
            f"color=white:s={W}x{H}:r={F}:d={D + 0.5:.3f},format=gray,vignette=angle={0.75 + 0.3 * a:.3f}:mode=forward,"
            f"lutyuv=y='clip((val-30)*1.6\\,0\\,255)'[dm];[dfa][dm]alphamerge[dfg];"
            f"[db]scale=w='trunc({W}*(1.02+{0.07 * a:.4f}*{s})/2)*2':h=-2:eval=frame,crop={W}:{H},gblur=sigma={1 + 4 * a:.2f}[dbg];"
            f"[dbg][dfg]overlay=format=auto:shortest=1,format=yuv420p")


def b_spotlight(p, c):
    R, S = p["move"], p["speed"]
    return (f"vignette=angle={p['size']:.3f}:x0='w/2+w*{R:.3f}*sin(t*{S:.3f})':y0='h/2+h*{R * 0.6:.3f}*cos(t*{S * 0.8:.3f})':eval=frame,"
            f"eq=contrast=1.1:brightness=0.03")


def b_duotone(p, c):
    r1, g1, b1 = _rgb(p["shadow"])
    r2, g2, b2 = _rgb(p["highlight"])
    k = p["contrast"]

    def ch(a, b):
        return f"'clip({a}+({b - a})*((val/255-0.5)*{k:.3f}+0.5)\\,0\\,255)'"
    return f"hue=s=0,format=rgb24,lutrgb=r={ch(r1, r2)}:g={ch(g1, g2)}:b={ch(b1, b2)},format=yuv420p"


def b_lens_flare(p, c):
    W, H, D, F = c["W"], c["H"], c["DUR"], c["FPS"]
    sw, sh = _ev(W * 1.4), _ev(H * 0.7)
    x0, x1, y = p["x_from"], p["x_to"], p["y"]
    r, g, b = _rgb(p["color"])
    spr = (f"color=black:s={sw}x{sh}:r={F}:d={1.0 / F:.4f},format=gray,"
           f"geq=lum='clip(255*pow(max(0\\,1-hypot(X-W/2\\,Y-H/2)/(H*0.45))\\,2.4)"
           f"+190*exp(-abs(Y-H/2)/(H*0.012))*pow(max(0\\,1-abs(X-W/2)/(W/2))\\,1.5)"
           f"+90*pow(max(0\\,1-hypot(X-W*0.3\\,Y-H*0.62)/(H*0.07))\\,1.5)\\,0\\,255)',"
           f"loop=loop=-1:size=1:start=0,setpts=N/{F}/TB,trim=duration={D + 0.5:.3f},format=gbrp,"
           f"colorchannelmixer=rr={r / 255:.3f}:gg={g / 255:.3f}:bb={b / 255:.3f}")
    xe = f"{W:.0f}*({x0:.3f}+({x1 - x0:.3f})*min(1\\,t/{D:.3f}))-w/2"
    return (f"format=gbrp[lf];{spr}[lsp];color=black:s={W}x{H}:r={F}:d={D + 0.5:.3f},format=gbrp[lcv];"
            f"[lcv][lsp]overlay=x='{xe}':y='{H * y:.0f}-h/2':shortest=1,format=gbrp[lfl];"
            f"[lf][lfl]blend=all_mode=screen:all_opacity={p['amount']:.3f}:shortest=1,format=yuv420p")


def b_pixelate(p, c):
    D, mx, mode = c["DUR"], int(p["size"]), int(round(p["mode"]))
    if mode == 2:
        return f"pixelize=w={mx}:h={mx}"
    n = 8
    parts = []
    for i in range(n):
        frac = 1 - i / n if mode == 0 else (i + 1) / n
        size = int(round(mx * frac))
        if size < 2:
            continue
        a, b = D * i / n, D * (i + 1) / n + (10 if i == n - 1 else 0)
        parts.append(f"pixelize=w={size}:h={size}:enable='between(t\\,{a:.3f}\\,{b:.3f})'")
    return ",".join(parts) or "null"


def b_kaleido(p, c):
    W, H = c["W"], c["H"]
    S = p["speed"]
    qw, qh = _ev(W / 2), _ev(H / 2)
    chain = (f"scale={_ev(W * 1.3)}:{_ev(H * 1.3)},crop={qw}:{qh}:'(iw-{qw})/2+(iw-{qw})/2*0.8*sin(t*{S:.3f})':"
             f"'(ih-{qh})/2+(ih-{qh})/2*0.8*cos(t*{S * 0.7:.3f})',split=4[k1][k2][k3][k4];"
             f"[k2]hflip[k2f];[k3]vflip[k3f];[k4]hflip,vflip[k4f];[k1][k2f]hstack[kt];[k3f][k4f]hstack[kb];[kt][kb]vstack,scale={W}:{H}")
    if p["spin"] > 0:
        chain += f",scale={_ev(W * 1.5)}:{_ev(H * 1.5)},rotate='t*{p['spin']:.3f}':c=black,crop={W}:{H}"
    return chain


def b_bw_pop(p, c):
    ramp = p["ramp"]
    hold = f"colorhold=color=0x{str(p['color']).lstrip('#')}:similarity={p['similarity']:.3f}:blend=0.12,eq=contrast=1.12"
    if ramp <= 0:
        return hold
    return f"split[ba][bb];[bb]{hold},format=yuva420p,fade=t=in:st=0:d={ramp:.3f}:alpha=1[bh];[ba][bh]overlay=format=auto,format=yuv420p"


def b_slow_shutter(p, c):
    return f"tmix=frames={int(p['frames'])},lagfun=decay={p['decay']:.3f}"


def b_neon(p, c):
    # white edge lines → tinted neon (magenta), hue cycling; the picture itself only dims
    return (f"format=gbrp,split[na][nb];[nb]edgedetect=low=0.08:high=0.25:mode=wires,format=gbrp,"
            f"colorchannelmixer=rr=1:gg=0.25:bb=1,hue=h='t*{p['speed']:.1f}':s=2,"
            f"format=gbrp,split[n1][n2];[n2]gblur=sigma={p['glow']:.1f},format=gbrp[ng];[n1][ng]blend=all_mode=screen,format=gbrp[ne];"
            f"[na]eq=brightness=-{p['dim']:.3f}:saturation=0.8,format=gbrp[nd];[nd][ne]blend=all_mode=screen,format=yuv420p")


def b_retro_tv(p, c):
    a = p["amount"]
    return (f"lenscorrection=k1={0.08 + 0.12 * a:.3f}:k2={0.02 + 0.06 * a:.3f},chromashift=crh={int(2 + 3 * a)}:cbh=-{int(2 + 3 * a)},"
            f"drawgrid=w=iw:h=3:t=1:c=black@{0.25 + 0.2 * a:.2f},eq=saturation=1.25:contrast=1.1:brightness='0.03*sin(t*55)':eval=frame,"
            f"noise=alls={int(6 + 14 * a)}:allf=t,vignette=angle={0.6 + 0.4 * a:.3f}")


def b_letterbox(p, c):
    W, H, D, F = c["W"], c["H"], c["DUR"], c["FPS"]
    bh = _ev(H * p["size"] / 100)
    a = max(0.05, p["anim"])
    k = f"min(1\\,min(t/{a:.3f}\\,({D:.3f}-t)/{a:.3f}))" if p["out"] >= 0.5 else f"min(1\\,t/{a:.3f})"
    k = f"(1-pow(1-max(0\\,{k})\\,3))"
    return (f"null[lb0];color=black:s={W}x{bh}:r={F}:d={D + 0.5:.3f},split[lbt][lbb];"
            f"[lb0][lbt]overlay=x=0:y='-h+h*{k}':eval=frame:shortest=1[lb1];[lb1][lbb]overlay=x=0:y='H-h*{k}':eval=frame:shortest=1")


# ---------------------------------------------------------------- catalog entries
def _fx(id_, label, build, params, tags, cost=1, css=""):
    return {"id": id_, "label": label, "cat": "trending", "tags": ["trending", *tags], "preview": "css" if css else "none",
            "css": css, "params": params, "build": build, "cost": cost, "anim": "duration"}


TRENDING: list[dict] = [
    _fx("tr_beat_shake", "बीट शेक · Beat shake", b_beat_shake,
        [_p("bpm", "BPM", 60, 180, 120, 1), _p("amount", "झटका % · Amount %", 0.5, 8, 3, 0.5), _p("decay", "decay", 3, 20, 9, 0.5)], ["beat", "shake"]),
    _fx("tr_camera_shake", "कैमरा शेक · Camera shake", b_camera_shake,
        [_p("amount", "हिलना % · Amount %", 0.3, 6, 1.6, 0.1), _p("speed", "speed", 0.3, 4, 1.2, 0.1), _p("rotate", "घुमाव ° · Tilt °", 0, 3, 0.6, 0.1)], ["handheld"]),
    _fx("tr_glitch", "ग्लिच / डेटामोश · Glitch datamosh", b_glitch,
        [_amt(0.6), _p("rate", "हर सेकंड · per second", 1, 12, 4, 0.5)], ["glitch", "datamosh"], 2),
    _fx("tr_rgb_split", "RGB स्प्लिट · RGB split (wave)", b_rgb_split,
        [_p("amount", "दूरी px · Distance px", 2, 60, 16, 1), _p("speed", "speed (Hz)", 0.2, 8, 1.5, 0.1)], ["chromatic"], 2),
    _fx("tr_chroma_pulse", "क्रोमा पल्स · Chromatic pulse", b_chroma_pulse,
        [_p("amount", "दूरी px · Distance px", 4, 60, 22, 1), _p("bpm", "BPM", 60, 180, 120, 1), _p("zoom", "zoom bump", 0, 0.15, 0.05, 0.01)], ["beat", "chromatic"], 2),
    _fx("tr_zoom_blur", "ज़ूम ब्लर · Zoom blur", b_zoom_blur, [_amt(0.7), _p("burst", "बीच में तेज़ · Burst (0/1)", 0, 1, 1, 1)], ["speed", "impact"], 2),
    _fx("tr_radial_blur", "स्पिन ब्लर · Radial blur", b_radial_blur,
        [_p("angle", "कोण ° · Angle °", 0.5, 8, 2.5, 0.5), _p("burst", "बीच में तेज़ · Burst (0/1)", 0, 1, 1, 1)], ["spin"], 2),
    _fx("tr_motion_blur", "मोशन ब्लर · Motion blur", b_motion_blur, [_p("frames", "frames", 2, 10, 4, 1)], ["smear"]),
    _fx("tr_light_leak", "लाइट लीक · Light leak", b_light_leak,
        [_amt(0.55), _p("speed", "speed", 0, 1, 0.4, 0.05), _p("seed", "pattern", 1, 50, 7, 1)], ["leak", "film"], 2, "sepia(0.15) brightness(1.08)"),
    _fx("tr_film_burn", "फ़िल्म बर्न · Film burn", b_film_burn,
        [_amt(0.85), _p("speed", "speed", 0, 1, 0.5, 0.05), _p("seed", "pattern", 1, 50, 3, 1)], ["burn", "transition"], 2, "brightness(1.2) sepia(0.3)"),
    _fx("tr_vhs", "VHS टेप · VHS", b_vhs, [_amt(0.6)], ["retro", "90s"], 2, "saturate(1.2) contrast(0.95)"),
    _fx("tr_old_film", "पुरानी फ़िल्म · Old film", b_old_film, [_amt(0.6)], ["vintage", "sepia"], 1, "sepia(0.8) contrast(1.08)"),
    _fx("tr_freeze", "फ़्रीज़ फ़्रेम · Freeze frame", b_freeze,
        [_p("zoom", "zoom in", 1, 1.4, 1.12, 0.01), _p("flash", "flash", 0, 1, 0.6, 0.05)], ["freeze", "pause"]),
    _fx("tr_flash", "फ़्लैश / स्ट्रोब · Flash & strobe", b_flash,
        [_amt(0.8), _p("rate", "strobe Hz (0 = सिर्फ़ flash)", 0, 15, 0, 0.5), _p("decay", "flash decay", 2, 20, 7, 0.5)], ["flash", "strobe"], 1, "brightness(1.3)"),
    _fx("tr_zoom_3d", "3D ज़ूम · 3D zoom (parallax)", b_zoom_3d, [_amt(0.7)], ["parallax", "dolly"], 2),
    _fx("tr_spotlight", "स्पॉटलाइट · Spotlight", b_spotlight,
        [_p("size", "अँधेरा · Darkness", 0.4, 1.4, 0.9, 0.05), _p("move", "घूमना · Move", 0, 0.35, 0.18, 0.01), _p("speed", "speed", 0.2, 4, 1.2, 0.1)], ["stage", "focus"]),
    _fx("tr_duotone", "ड्यूओटोन · Duotone", b_duotone,
        [P(name="shadow", label="Shadow रंग", type="color", default="#1B0B4A"), P(name="highlight", label="Highlight रंग", type="color", default="#FF7A3D"),
         _p("contrast", "contrast", 0.6, 2, 1.15, 0.05)], ["two colour", "poster"], 1, "grayscale(1) sepia(0.6) saturate(2)"),
    _fx("tr_lens_flare", "लेंस फ़्लेयर · Lens flare", b_lens_flare,
        [_amt(0.8), _p("x_from", "शुरू X · From X", -0.3, 1.3, 0.1, 0.05), _p("x_to", "अंत X · To X", -0.3, 1.3, 0.9, 0.05),
         _p("y", "ऊँचाई · Y", 0, 1, 0.3, 0.05), P(name="color", label="रंग · Colour", type="color", default="#FFD8A0")], ["flare", "sun"], 2, "brightness(1.08)"),
    _fx("tr_pixelate", "पिक्सेल · Pixelate (animated)", b_pixelate,
        [_p("size", "block", 4, 80, 40, 1), _p("mode", "0 = साफ़ होता, 1 = धुँधला होता, 2 = स्थिर", 0, 2, 0, 1)], ["8bit", "censor", "reveal"]),
    _fx("tr_kaleido", "कैलिडोस्कोप · Kaleidoscope", b_kaleido,
        [_p("speed", "चाल · Drift", 0, 3, 0.6, 0.1), _p("spin", "घूमना · Spin", 0, 2, 0, 0.05)], ["mirror", "symmetry"], 2),
    _fx("tr_bw_pop", "B&W पॉप (रंग बचे) · Colour keep", b_bw_pop,
        [P(name="color", label="बचने वाला रंग · Keep colour", type="color", default="#D0202A"), _p("similarity", "similarity", 0.05, 0.8, 0.35, 0.01),
         _p("ramp", "रंग से B&W (s) · Ramp s", 0, 3, 0.4, 0.1)], ["splash", "selective"], 1, "grayscale(0.85)"),
    _fx("tr_slow_shutter", "स्लो शटर · Slow shutter", b_slow_shutter,
        [_p("frames", "frames", 2, 10, 5, 1), _p("decay", "trail", 0.8, 0.99, 0.93, 0.01)], ["ghost", "trails"]),
    _fx("tr_neon", "नियॉन एज ग्लो · Edge glow / neon", b_neon,
        [_p("glow", "glow", 1, 20, 8, 1), _p("speed", "रंग घूमे · Hue speed", 0, 360, 90, 10), _p("dim", "पीछे अँधेरा · Dim", 0, 0.6, 0.25, 0.05)], ["outline", "neon"], 3),
    _fx("tr_retro_tv", "रेट्रो टीवी · Retro TV", b_retro_tv, [_amt(0.6)], ["crt", "tv"], 2, "contrast(1.1) saturate(1.2)"),
    _fx("tr_letterbox", "लेटरबॉक्स इन/आउट · Letterbox in/out", b_letterbox,
        [_p("size", "पट्टी % · Bar %", 4, 20, 11, 1), _p("anim", "animation (s)", 0.1, 2, 0.45, 0.05), _p("out", "अंत में हटे · Out (0/1)", 0, 1, 1, 1)], ["cinematic", "bars"]),
]
