"""Tiny LLM client (stdlib only). Gemini first (cheap), Claude if configured.

Set GEMINI_API_KEY (and optionally GEMINI_MODEL) or ANTHROPIC_API_KEY
(ANTHROPIC_MODEL). Every call asks for JSON and returns the parsed object,
or None when no key is set or the call fails — callers always have a
heuristic fallback, so the product works offline too.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


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


def ask_json(prompt: str, *, system: str = "", max_tokens: int = 2048, timeout: float = 90):
    which = available()
    if which is None:
        return None
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
