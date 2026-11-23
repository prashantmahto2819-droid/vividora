"""Generate extra CC0 sound effects with numpy (no downloads, no licences): python tools/make_sfx.py [outdir]
Writes WAV then encodes MP3 (needs ffmpeg). Deterministic (fixed seed)."""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def t(d): return np.arange(int(SR * d)) / SR


def lp(x, fc):  # one-pole low-pass
    a = np.exp(-2 * np.pi * fc / SR); y = np.zeros_like(x); s = 0.0
    for i, v in enumerate(x):
        s = (1 - a) * v + a * s; y[i] = s
    return y


def sweep_noise(d, f0, f1, peak=0.5):
    """band-ish noise whose centre frequency glides f0→f1 with a bell envelope (whoosh)."""
    n = int(SR * d); tt = t(d); noise = rng.standard_normal(n)
    f = np.geomspace(f0, f1, n); ph = 2 * np.pi * np.cumsum(f) / SR
    y = noise * (0.5 + 0.5 * np.sin(ph))  # amplitude-modulated noise; ear hears a moving band
    y = lp(y, 5000) - lp(y, 300)
    env = np.sin(np.pi * np.clip(tt / d, 0, 1)) ** (1 + 2 * peak)
    return y * env


def pop(d=0.18, f=520, drop=260):
    tt = t(d); fr = f - drop * (tt / d)
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 26)


def tick(d=0.06):
    tt = t(d); return (rng.standard_normal(len(tt)) * 0.35 + np.sin(2 * np.pi * 1800 * tt)) * np.exp(-tt * 90)


def hit(d=0.9):
    tt = t(d); fr = 90 * np.exp(-tt * 5) + 38
    body = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 4.2)
    snap = lp(rng.standard_normal(len(tt)), 2500) * np.exp(-tt * 40) * 0.6
    return body + snap


def slide(d=0.45):
    return sweep_noise(d, 900, 2600, 0.2) * 0.9


def bubble(d=0.22):
    tt = t(d); fr = 300 + 900 * (tt / d) ** 2
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 18)


# ---- pack 2: transitions, cinematic hits, UI / reaction sounds ------------------------------------------------------
def env_ad(tt, a=0.005, d=8.0):
    return np.minimum(tt / a, 1.0) * np.exp(-tt * d)


def tone(f, d, decay=8.0, harm=()):
    tt = t(d); y = np.sin(2 * np.pi * f * tt)
    for k, g in harm:
        y = y + g * np.sin(2 * np.pi * f * k * tt)
    return y * env_ad(tt, 0.004, decay)


def glide(f0, f1, d, decay=6.0, curve=1.0):
    tt = t(d); fr = f0 + (f1 - f0) * (tt / d) ** curve
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * env_ad(tt, 0.004, decay)


def seq(parts, gap=0.0):
    """Lay sounds one after another (gap seconds between starts when > 0, else back to back)."""
    out = np.zeros(1)
    pos = 0
    for y in parts:
        n = pos + len(y)
        if n > len(out):
            out = np.concatenate([out, np.zeros(n - len(out))])
        out[pos:n] += y
        pos += int(SR * gap) if gap else len(y)
    return out


def noise(d, fc=6000, hp=200):
    y = rng.standard_normal(int(SR * d)); return lp(y, fc) - lp(y, hp)


def riser(d=2.4, f0=250, f1=5000):
    tt = t(d); n = noise(d, 8000, 150); f = np.geomspace(f0, f1, len(tt))
    y = n * (0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR)) + 0.25 * np.sin(2 * np.pi * np.cumsum(f * 0.5) / SR)
    return y * (tt / d) ** 2.2


def braam(d=2.0, f=55):
    tt = t(d); y = sum(np.sin(2 * np.pi * f * k * tt + k) / k for k in (1, 2, 3, 4, 5, 7))
    y = np.tanh(y * 1.8) * np.minimum(tt / 0.05, 1) * np.exp(-tt * 1.6)
    return y + 0.4 * lp(rng.standard_normal(len(tt)), 400) * np.exp(-tt * 6)


def clap(n=3):
    burst = lambda dly: np.concatenate([np.zeros(int(SR * dly)), noise(0.09, 3500, 700) * np.exp(-t(0.09) * 45)])  # noqa: E731
    parts = [burst(0.012 * i) for i in range(n)]
    L = max(map(len, parts)); return sum(np.pad(p, (0, L - len(p))) for p in parts)


def ticks(d, rate, jitter=0.0, f=1800):
    out = np.zeros(int(SR * d)); pos = 0.0
    while pos < d - 0.07:
        k = tick(0.05) * (0.7 + 0.3 * rng.random()); i = int(pos * SR); out[i:i + len(k)] += k[:len(out) - i]
        pos += 1.0 / rate * (1 + jitter * (rng.random() - 0.5))
    return out


def roll(d=1.4):
    out = np.zeros(int(SR * d)); pos = 0.0; step = 0.11
    while pos < d - 0.06:
        k = noise(0.05, 5000, 900) * np.exp(-t(0.05) * 60) * (0.4 + 0.6 * pos / d); i = int(pos * SR); out[i:i + len(k)] += k[:len(out) - i]
        pos += step; step = max(0.028, step * 0.93)
    return out


def scratch(d=0.5):
    tt = t(d); f = 600 + 1800 * np.abs(np.sin(2 * np.pi * 3.2 * tt))
    return noise(d, 7000, 500) * (0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.sin(np.pi * tt / d) ** 0.5


def sparkle(d=0.9, n=14, lo=2200, hi=6500):
    out = np.zeros(int(SR * d))
    for _ in range(n):
        y = tone(rng.uniform(lo, hi), 0.16, 22) * rng.uniform(0.4, 1); i = int(rng.uniform(0, d - 0.17) * SR); out[i:i + len(y)] += y
    return out


def heart(rate=2.2, beats=4):
    one = np.concatenate([tone(62, 0.16, 22), np.zeros(int(SR * 0.05)), tone(52, 0.2, 18) * 0.8])
    return seq([one] * beats, gap=1.0 / rate)


PACK2 = {
    # transitions / movement
    "riser_long": lambda: riser(2.4), "riser_short": lambda: riser(1.0, 400, 6000), "downlifter": lambda: riser(1.6)[::-1],
    "reverse_cymbal": lambda: (noise(1.4, 9000, 2500) * (t(1.4) / 1.4) ** 3),
    "swoosh_up": lambda: sweep_noise(0.45, 400, 4200, 0.3), "swoosh_down": lambda: sweep_noise(0.5, 4200, 350, 0.3),
    "whoosh_deep": lambda: sweep_noise(0.9, 120, 700, 0.5), "page_flip": lambda: sweep_noise(0.22, 1800, 5200, 0.1) * 0.8,
    "tape_stop": lambda: glide(900, 60, 0.7, 1.5, 0.6), "record_scratch": scratch,
    # hits / cinematic
    "braam": braam, "sub_drop": lambda: glide(130, 32, 1.3, 2.2, 0.5), "bass_hit": lambda: glide(110, 45, 0.5, 7) + 0.3 * tone(55, 0.5, 5),
    "punch": lambda: glide(180, 60, 0.18, 22) + 0.5 * noise(0.18, 2500, 300) * np.exp(-t(0.18) * 50),
    "impact_metal": lambda: hit(1.1) + 0.35 * sum(tone(f, 1.1, 5) for f in (523, 811, 1217, 1733)),
    "stinger": lambda: seq([riser(0.7, 500, 5000) * 0.7, hit(0.9)]),
    # UI / reactions
    "pop_high": lambda: pop(0.12, 900, 380), "click_soft": lambda: tick(0.035) * 0.8, "text_blip": lambda: tone(1250, 0.07, 45),
    "ui_select": lambda: seq([tone(880, 0.07, 40), tone(1320, 0.1, 30)]), "snap": lambda: noise(0.06, 7000, 1500) * np.exp(-t(0.06) * 80),
    "clap": clap, "coin": lambda: seq([tone(988, 0.08, 30, ((2, .3),)), tone(1319, 0.42, 9, ((2, .3),))]),
    "level_up": lambda: seq([tone(f, 0.11, 18, ((2, .25),)) for f in (523, 659, 784)] + [tone(1047, 0.45, 7, ((2, .25),))]),
    "success_chime": lambda: sum(np.pad(tone(f, 0.9, 5, ((2, .2), (3, .1))), (int(SR * dly), int(SR * (0.2 - dly)))) for f, dly in ((784, 0), (988, 0.08), (1175, 0.16))),
    "fail_tone": lambda: seq([np.tanh(3 * tone(311, 0.2, 8)), np.tanh(3 * tone(233, 0.45, 6))]),
    "error_soft": lambda: seq([tone(330, 0.1, 25), tone(262, 0.2, 14)]),
    "notification_soft": lambda: seq([tone(1047, 0.1, 22), tone(1397, 0.32, 10)]),
    "camera_focus": lambda: seq([tone(2100, 0.05, 50), np.zeros(int(SR * 0.07)), tone(2100, 0.05, 50)]),
    "laser": lambda: glide(2400, 250, 0.3, 9, 0.5), "zap": lambda: glide(1800, 200, 0.16, 16) + 0.5 * noise(0.16, 8000, 2000) * np.exp(-t(0.16) * 30),
    "boing": lambda: np.sin(2 * np.pi * np.cumsum(180 + 120 * np.sin(2 * np.pi * 9 * t(0.6)) * np.exp(-t(0.6) * 4)) / SR) * np.exp(-t(0.6) * 5),
    "sparkle_up": lambda: sparkle(0.9), "shimmer": lambda: sparkle(1.6, 26, 3000, 8000) * np.sin(np.pi * t(1.6) / 1.6),
    # rhythm / ambience
    "clock_tick": lambda: seq([tick(0.05), tick(0.05) * 0.7] * 2, gap=0.5), "typing_fast": lambda: ticks(1.2, 11, 0.6),
    "drum_roll": roll, "heartbeat_fast": lambda: heart(2.2, 4), "kick_soft": lambda: glide(120, 45, 0.3, 12),
}

SOUNDS = {
    "whoosh_soft": lambda: sweep_noise(0.7, 300, 1500, 0.5) * 0.9,
    "whoosh_fast": lambda: sweep_noise(0.32, 700, 3500, 0.2),
    "pop_soft": lambda: pop(0.16, 440, 180) * 0.9,
    "tick": tick,
    "hit_deep": hit,
    "slide": slide,
    "bubble_pop": bubble,
}


def write(name, y, out):
    y = np.asarray(y, float); y = y / (np.max(np.abs(y)) + 1e-9) * 0.89
    fade = int(SR * 0.004); y[:fade] *= np.linspace(0, 1, fade); y[-fade:] *= np.linspace(1, 0, fade)
    wav = out / f"{name}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((y * 32767).astype("<i2").tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "128k", str(out / f"{name}.mp3")], check=True)
    wav.unlink()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "starter" / "sfx")
    out.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[2:])               # optional: names to (re)generate — default everything
    for n, fn in {**SOUNDS, **PACK2}.items():
        if only and n not in only and "pack2" not in only:
            continue
        if "pack2" in only and n not in PACK2:
            continue
        write(n, fn(), out); print("ok", n)
