"""Tiny LLM client (stdlib only). Gemini first (cheap), Claude if configured.

Set GEMINI_API_KEY (and optionally GEMINI_MODEL) or ANTHROPIC_API_KEY
(ANTHROPIC_MODEL). Every call asks for JSON and returns the parsed object,
or None when no key is set or the call fails — callers always have a
heuristic fallback, so the product works offline too.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


def available() -> str | None:
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    return None


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0] or [0])
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None


def _cache_dir() -> Path:
    d = Path(os.getenv("DATA_ROOT", "./data")).resolve() / "cache" / "llm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _model(which: str) -> str:
    return _gemini_model() if which == "gemini" else os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")


def _stat(key: str) -> None:
    f = _cache_dir() / "_stats.json"
    try:
        st = json.loads(f.read_text()) if f.exists() else {}
    except ValueError:
        st = {}
    st[key] = st.get(key, 0) + 1
    try:
        f.write_text(json.dumps(st))
    except OSError:
        pass


def stats() -> dict:
    f = _cache_dir() / "_stats.json"
    try:
        st = json.loads(f.read_text()) if f.exists() else {}
    except ValueError:
        st = {}
    return {"provider": available(), "calls": st.get("calls", 0), "saved": st.get("hits", 0), "last_error": LAST_ERROR}


def ask_json(prompt: str, *, system: str = "", max_tokens: int = 2048, timeout: float = 90, cache: bool = True):
    """Same question twice → answered from disk, no new credit spent (set LLM_CACHE=0 to disable)."""
    which = available()
    if which is None:
        return None
    use_cache = cache and os.getenv("LLM_CACHE", "1") != "0"
    key = hashlib.sha256(f"{which}|{_model(which)}|{system}|{max_tokens}|{prompt}".encode()).hexdigest()[:32]
    cf = _cache_dir() / f"{key}.json"
    if use_cache and cf.exists():
        try:
            _stat("hits")
            return json.loads(cf.read_text())
        except ValueError:
            pass
    if not _gate():
        return None
    res = _ask(which, prompt, system=system, max_tokens=max_tokens, timeout=timeout)
    _stat("calls")
    _count()
    if use_cache and res is not None:
        try:
            cf.write_text(json.dumps(res, ensure_ascii=False))
        except OSError:
            pass
    return res


LAST_ERROR = ""   # shown in the UI when AI falls back to templates
BUDGET = 10**9    # worker: AI calls allowed for the current job's workspace (set from the claim); API: via saas


def _gate() -> bool:
    global LAST_ERROR
    try:
        from .. import saas
        if not saas.llm_gate():
            LAST_ERROR = "AI credits इस महीने के पूरे हो गए — plan बढ़ाएँ"
            return False
    except Exception:  # noqa: BLE001 — worker process without DB access: use the claim-time budget
        pass
    if BUDGET <= 0:
        LAST_ERROR = "AI credits इस महीने के पूरे हो गए — plan बढ़ाएँ"
        return False
    return True


def _count() -> None:
    global BUDGET
    BUDGET -= 1
    try:
        from .. import saas
        saas.llm_count(1)
    except Exception:  # noqa: BLE001
        pass


def _gemini_models_auto() -> str | None:
    """Google retires models regularly ("no longer available to new users"). Ask the API which
    models this key can use and pick the newest stable Flash; remembered on disk."""
    f = _cache_dir() / "_gemini_model.txt"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key={os.environ['GEMINI_API_KEY']}"
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None
    best, best_key = None, None
    for m in data.get("models") or []:
        name = str(m.get("name", "")).split("/")[-1]
        if "generateContent" not in (m.get("supportedGenerationMethods") or []) or "flash" not in name:
            continue
        if any(x in name for x in ("image", "tts", "audio", "live", "thinking", "embed", "8b")):
            continue
        ver = re.findall(r"gemini-(\d+(?:\.\d+)?)", name)
        v = float(ver[0]) if ver else 0.0
        key = (v, "lite" not in name, "preview" not in name and "exp" not in name, -len(name))
        if best_key is None or key > best_key:
            best, best_key = name, key
    if best:
        try:
            f.write_text(best)
        except OSError:
            pass
    return best


def _gemini_model() -> str:
    env = os.getenv("GEMINI_MODEL", "").strip()
    if env:
        return env
    f = _cache_dir() / "_gemini_model.txt"
    try:
        if f.exists() and f.read_text().strip():
            return f.read_text().strip()
    except OSError:
        pass
    return _gemini_models_auto() or "gemini-flash-latest"


def _gemini_call(model: str, prompt: str, system: str, max_tokens: int, timeout: float) -> str:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
           f"?key={os.environ['GEMINI_API_KEY']}")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])


def _ask(which: str, prompt: str, *, system: str, max_tokens: int, timeout: float):
    global LAST_ERROR
    try:
        if which == "gemini":
            model = _gemini_model()
            try:
                text = _gemini_call(model, prompt, system, max_tokens, timeout)
            except urllib.error.HTTPError as e:
                if e.code not in (400, 404):
                    raise
                # model retired / renamed → find a current one and retry once
                (_cache_dir() / "_gemini_model.txt").unlink(missing_ok=True)
                alt = _gemini_models_auto()
                if not alt or alt == model:
                    raise
                text = _gemini_call(alt, prompt, system, max_tokens, timeout)
        else:
            model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
            body = {"model": model, "max_tokens": max_tokens, "system": system or "Reply with JSON only.",
                    "messages": [{"role": "user", "content": prompt}]}
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                         method="POST", headers={"Content-Type": "application/json",
                                                                 "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                                                 "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
            text = "".join(p.get("text", "") for p in data.get("content", []))
        LAST_ERROR = ""
        return _extract_json(text)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            msg = ""
        LAST_ERROR = f"AI ({which}) HTTP {e.code}: {msg[:160]}"
        return None
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError) as e:
        LAST_ERROR = f"AI ({which}): {str(e)[:160]}"
        return None
