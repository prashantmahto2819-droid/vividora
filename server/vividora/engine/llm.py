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
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if which == "gemini" else os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")


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
    return {"provider": available(), "calls": st.get("calls", 0), "saved": st.get("hits", 0)}


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
    res = _ask(which, prompt, system=system, max_tokens=max_tokens, timeout=timeout)
    _stat("calls")
    if use_cache and res is not None:
        try:
            cf.write_text(json.dumps(res, ensure_ascii=False))
        except OSError:
            pass
    return res


def _ask(which: str, prompt: str, *, system: str, max_tokens: int, timeout: float):
    try:
        if which == "gemini":
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
            text = data["candidates"][0]["content"]["parts"][0]["text"]
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
        return _extract_json(text)
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None
