"""Matching pictures to spoken lines on this server, without any outside AI (optional): multilingual CLIP via open_clip.

A CLIP model turns a picture and a sentence into two lists of numbers; the closer they are, the better the sentence
describes the picture. The default model reads Hindi and English text (XLM-RoBERTa text side). It needs
`pip install open_clip_torch` (PyTorch, ~2 GB) and downloads its weights once (~1.5 GB) — so it is off unless
CLIP_MATCH=on (API & Keys) AND the package is installed (image built with WITH_OPENCLIP=1, docs/openclip.md).
Gemini, when its key is set, still describes the clips; CLIP only places what words and Gemini could not.
"""

from __future__ import annotations

import base64
import importlib.util
import logging
import os

log = logging.getLogger("vividora.clip")
_MODEL: dict = {}


def wanted() -> bool:
    return (os.getenv("CLIP_MATCH") or "").strip().lower() in ("on", "1", "true", "yes")


def available() -> bool:
    return importlib.util.find_spec("open_clip") is not None and importlib.util.find_spec("torch") is not None


def model_name() -> str:
    return os.getenv("CLIP_MODEL") or "xlm-roberta-base-ViT-B-32"


def _load():
    if "m" not in _MODEL:
        import open_clip
        import torch
        torch.set_num_threads(max(1, int(os.getenv("CLIP_THREADS") or 4)))
        name = model_name()
        m, _, pre = open_clip.create_model_and_transforms(name, pretrained=os.getenv("CLIP_PRETRAINED") or "laion5b_s13b_b90k")
        m.eval()
        _MODEL.update(m=m, pre=pre, tok=open_clip.get_tokenizer(name), torch=torch)
    return _MODEL


def embed_images(jpegs: list[bytes]):
    """→ float32 array (n, d), each row of length 1."""
    import io

    import numpy as np
    from PIL import Image
    M = _load()
    torch = M["torch"]
    out = []
    with torch.no_grad():
        for i in range(0, len(jpegs), 16):
            batch = torch.stack([M["pre"](Image.open(io.BytesIO(b)).convert("RGB")) for b in jpegs[i:i + 16]])
            v = M["m"].encode_image(batch)
            out.append((v / v.norm(dim=-1, keepdim=True)).cpu().numpy().astype(np.float32))
    return np.concatenate(out) if out else np.zeros((0, 1), dtype=np.float32)


def embed_texts(texts: list[str]):
    import numpy as np
    M = _load()
    torch = M["torch"]
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 64):
            v = M["m"].encode_text(M["tok"]([t[:300] for t in texts[i:i + 64]]))
            out.append((v / v.norm(dim=-1, keepdim=True)).cpu().numpy().astype(np.float32))
    return np.concatenate(out) if out else np.zeros((0, 1), dtype=np.float32)


def pack(vec) -> str:
    """A picture's numbers as a short string (kept in the Library item, so a clip is looked at only once)."""
    import numpy as np
    return base64.b64encode(np.asarray(vec, dtype=np.float16).tobytes()).decode()


def unpack(s: str):
    import numpy as np
    v = np.frombuffer(base64.b64decode(s), dtype=np.float16).astype(np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def rank(clip_vecs: dict, line_vecs, *, top: int = 3, min_sim: float | None = None, lead: float | None = None) -> dict:
    """{clip id: vector (mean of its frames)} × lines → {clip id: [(line index, score 0…1), …]} best first.
    A line counts only when it is clearly above that clip's usual level: similarity ≥ `min_sim` AND at least `lead`
    standard deviations above the clip's mean over all lines (a picture that looks a bit like everything matches nothing).
    `lead` defaults to what the best of that many unrelated lines would reach by chance: √(2·ln n)."""
    import numpy as np
    if min_sim is None:
        try:
            min_sim = float(os.getenv("CLIP_MIN_SIM") or 0.18)
        except ValueError:
            min_sim = 0.18
    L = np.asarray(line_vecs, dtype=np.float32)
    out: dict = {}
    if L.ndim != 2 or not len(L):
        return out
    for cid, v in clip_vecs.items():
        sims = L @ np.asarray(v, dtype=np.float32)
        mu, sd = float(sims.mean()), float(sims.std())
        need = lead if lead is not None else float(np.sqrt(2 * np.log(max(2, len(sims)))))
        order = np.argsort(-sims)[:top]
        got = [(int(i), round(float(sims[i]), 3)) for i in order
               if sims[i] >= min_sim and (len(sims) < 4 or sd < 1e-6 or (sims[i] - mu) / sd >= need)]
        if got:
            out[cid] = got
    return out
