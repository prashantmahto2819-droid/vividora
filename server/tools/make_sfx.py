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
    for n, fn in SOUNDS.items():
        write(n, fn(), out); print("ok", n)
