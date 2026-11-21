#!/usr/bin/env python3
"""Vividora MCP server — lets Claude (Claude Code / Claude Desktop / any MCP client) drive Vividora through its /api/v1.

No dependencies (Python 3.9+ standard library only). Talks MCP over stdio (newline-delimited JSON-RPC).

    VIVIDORA_URL      https://studio.vividbrandify.com        (no trailing /api)
    VIVIDORA_API_KEY  vk_…                                    (Dashboard → API & Integrations)

Claude Code:   claude mcp add vividora --env VIVIDORA_URL=https://studio.… --env VIVIDORA_API_KEY=vk_… -- python3 /path/to/vividora_mcp.py
Claude Desktop: see docs/mcp.md
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = (os.environ.get("VIVIDORA_URL") or "").rstrip("/")
KEY = os.environ.get("VIVIDORA_API_KEY") or ""
PROTOCOL = "2024-11-05"
WAIT_SECONDS = 300


class ToolError(Exception):
    pass


def _req(method: str, path: str, body: dict | None = None, raw: bytes | None = None, ctype: str | None = None, timeout: int = 120):
    if not BASE or not KEY:
        raise ToolError("VIVIDORA_URL और VIVIDORA_API_KEY environment variables सेट करें")
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Authorization": f"Bearer {KEY}", "User-Agent": "vividora-mcp/1"}
    if data is not None:
        h["Content-Type"] = ctype or "application/json"
    r = urllib.request.Request(BASE + "/api" + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            blob = resp.read()
            if "json" in (resp.headers.get("content-type") or ""):
                return json.loads(blob or b"null")
            return blob
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read() or b"{}").get("error")
        except ValueError:
            msg = None
        raise ToolError(f"Vividora {e.code}: {msg or e.reason}")
    except urllib.error.URLError as e:
        raise ToolError(f"Vividora तक पहुँच नहीं: {e.reason}")


def _wait(job_id: str) -> dict:
    t0 = time.time()
    while True:
        j = _req("GET", f"/v1/jobs/{job_id}")
        if j.get("status") in ("done", "failed", "error"):
            return j
        if time.time() - t0 > WAIT_SECONDS:
            j["note"] = f"अभी भी चल रहा है — vividora_job_status से देखते रहें (job_id={job_id})"
            return j
        time.sleep(3)


def _save(file_id: str, save_to: str) -> str:
    blob = _req("GET", f"/v1/files/{file_id}", timeout=300)
    p = Path(save_to).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(blob if isinstance(blob, bytes) else json.dumps(blob).encode())
    return str(p)


def _finish(job: dict, save_to: str | None) -> dict:
    f = job.get("file")
    if job.get("status") == "done" and f and save_to:
        job["saved_to"] = _save(f["id"], save_to)
    return job


def t_whoami(a):
    return _req("GET", "/v1/me")


def t_voices(a):
    return _req("GET", "/v1/voices")


def t_tts(a):
    body = {k: a[k] for k in ("text", "voice", "lang", "speed", "name") if a.get(k) not in (None, "")}
    if not body.get("text"):
        raise ToolError("text चाहिए")
    j = _req("POST", "/v1/text-to-speech", body)
    if a.get("wait", True) is False:
        return j
    return _finish(_wait(j["job_id"]), a.get("save_to"))


def t_job(a):
    return _req("GET", f"/v1/jobs/{a['job_id']}")


def t_download(a):
    return {"saved_to": _save(a["file_id"], a["save_to"])}


def t_image_to_3d(a):
    p = Path(a["image_path"]).expanduser()
    if not p.is_file():
        raise ToolError(f"image file नहीं मिली: {p}")
    bnd = uuid.uuid4().hex
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    parts = [f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="{p.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),
             p.read_bytes(), b"\r\n"]
    if a.get("name"):
        parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="name"\r\n\r\n{a["name"]}\r\n'.encode())
    parts.append(f"--{bnd}--\r\n".encode())
    j = _req("POST", "/v1/image-to-3d", raw=b"".join(parts), ctype=f"multipart/form-data; boundary={bnd}", timeout=300)
    if a.get("wait", True) is False:
        return j
    return _finish(_wait(j["job_id"]), a.get("save_to"))


def t_models(a):
    return _req("GET", "/v1/models3d")


def t_character_video(a):
    body = {k: v for k, v in a.items() if k not in ("wait", "save_to") and v not in (None, "")}
    j = _req("POST", "/v1/character-video", body)
    if a.get("wait", True) is False:
        return j
    return _finish(_wait(j["job_id"]), a.get("save_to"))


def t_auto_sfx(a):
    body = {k: a[k] for k in ("project_id", "effects", "duration", "cut_times", "density", "level") if a.get(k) is not None}
    return _req("POST", "/v1/auto-sfx", body)


def t_doc_plan(a):
    body = {k: a[k] for k in ("topic", "script", "minutes", "language") if a.get(k) not in (None, "")}
    return _req("POST", "/v1/documentary/plan", body, timeout=180)


def t_doc_build(a):
    body = {k: a[k] for k in ("title", "scenes", "voice", "lang", "speed", "orientation", "music_id", "stock", "ai_images", "ai_video") if a.get(k) is not None}
    j = _req("POST", "/v1/documentary/build", body)
    if a.get("wait", True) is False:
        return j
    global WAIT_SECONDS
    old, WAIT_SECONDS = WAIT_SECONDS, 1500
    try:
        return _finish(_wait(j["job_id"]), a.get("save_to"))
    finally:
        WAIT_SECONDS = old


def _batch(j: dict, save_to: str | None) -> dict:
    global WAIT_SECONDS
    old, WAIT_SECONDS = WAIT_SECONDS, 3600
    try:
        return _wait(j["job_id"])
    finally:
        WAIT_SECONDS = old


def t_doc_shorts(a):
    body = {k: a[k] for k in ("scenes", "title", "count", "pick", "voice", "lang", "orientation", "music_id", "ai_images", "stock") if a.get(k) is not None}
    body["build"] = bool(a.get("build"))
    j = _req("POST", "/v1/documentary/shorts", body)
    if not body["build"] or a.get("wait", True) is False:
        return j
    return _batch(j, None)


def t_doc_series(a):
    body = {k: a[k] for k in ("topic", "episodes", "series", "language", "minutes", "voice", "lang", "orientation", "music_id", "ai_images", "stock", "ground") if a.get(k) is not None}
    body["build"] = bool(a.get("build"))
    j = _req("POST", "/v1/documentary/series", body, timeout=180)
    if not body["build"] or a.get("wait", True) is False:
        return j
    return _batch(j, None)


_WAIT = {"wait": {"type": "boolean", "description": "true (default): काम पूरा होने तक रुकें; false: सिर्फ़ job_id लौटाएँ"},
         "save_to": {"type": "string", "description": "नतीजा इस local path पर सेव करें (वैकल्पिक)"}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


TOOLS = {
    "vividora_whoami": (t_whoami, "API key जाँचें — user, role, workspace", _obj({})),
    "vividora_list_voices": (t_voices, "text-to-speech के लिए उपलब्ध voices", _obj({})),
    "vividora_text_to_speech": (t_tts, "Text → narration (WAV) Vividora Voice से। Hindi/English आदि।", _obj({
        "text": {"type": "string"}, "voice": {"type": "string", "description": "id from vividora_list_voices"},
        "lang": {"type": "string", "description": "जैसे hi, en"}, "speed": {"type": "number"}, "name": {"type": "string"}, **_WAIT}, ["text"])),
    "vividora_image_to_3d": (t_image_to_3d, "Image → 3D model (.glb), 1–3 मिनट", _obj({
        "image_path": {"type": "string", "description": "local image file path"}, "name": {"type": "string"}, **_WAIT}, ["image_path"])),
    "vividora_list_models3d": (t_models, "आपके 3D models की list (character video के लिए glb id)", _obj({})),
    "vividora_character_video": (t_character_video, "3D character का बोलता वीडियो (transparent webm)", _obj({
        "glb": {"type": "string", "description": "3D model id"}, "profile": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "voice": {"type": "string"}}}},
        "animation": {"type": "string"}, "camera": {"type": "string", "enum": ["full", "medium", "close", "wide"]},
        "seconds": {"type": "number"}, **_WAIT})),
    "vividora_auto_sfx": (t_auto_sfx, "Timeline (title/B-roll/sticker/cut) देखकर whoosh/pop/tick sound effects की योजना बनाता है; सेव नहीं करता", _obj({
        "project_id": {"type": "string"}, "effects": {"type": "object"}, "duration": {"type": "number"},
        "cut_times": {"type": "array", "items": {"type": "number"}}, "density": {"type": "string", "enum": ["low", "normal", "high"]},
        "level": {"type": "number"}})),
    "vividora_documentary_plan": (t_doc_plan, "Topic (AI key चाहिए) या अपनी script → documentary scenes [{narration, visual, on_screen}]", _obj({
        "topic": {"type": "string"}, "script": {"type": "string"}, "minutes": {"type": "number"}, "language": {"type": "string", "enum": ["hi", "en", "hinglish"]}})),
    "vividora_documentary_build": (t_doc_build, "Scenes → narrated documentary MP4 (Library में + वैकल्पिक local save)। बनने में मिनट लगते हैं", _obj({
        "title": {"type": "string"}, "scenes": {"type": "array", "items": {"type": "object", "properties": {
            "narration": {"type": "string"}, "visual": {"type": "string"}, "on_screen": {"type": "string"}, "library_id": {"type": "string"}}}},
        "voice": {"type": "string"}, "lang": {"type": "string"}, "speed": {"type": "number"},
        "orientation": {"type": "string", "enum": ["landscape", "portrait", "square"]}, "music_id": {"type": "string"},
        "stock": {"type": "boolean"}, "ai_images": {"type": "boolean", "description": "AI-generated pictures via the configured GPU API (default true)"}, **_WAIT}, ["scenes"])),
    "vividora_documentary_shorts": (t_doc_shorts, "Documentary scenes → best 20–58 s Shorts/Reels (build=false: सिर्फ़ plan; build=true: portrait videos बनाता है)", _obj({
        "scenes": {"type": "array", "items": {"type": "object"}}, "title": {"type": "string"}, "count": {"type": "integer"}, "build": {"type": "boolean"},
        "pick": {"type": "array", "items": {"type": "integer"}}, "voice": {"type": "string"}, "ai_images": {"type": "boolean"}, "stock": {"type": "boolean"}, **_WAIT}, ["scenes"])),
    "vividora_documentary_series": (t_doc_series, "Topic → series outline (build=false), या episodes देकर build=true से पूरी series बनती है (हर episode की scenes AI लिखता है)", _obj({
        "topic": {"type": "string"}, "episodes": {"description": "outline के लिए संख्या; build के लिए [{title, summary}]"}, "series": {"type": "string"},
        "build": {"type": "boolean"}, "language": {"type": "string"}, "minutes": {"type": "number"}, "voice": {"type": "string"}, "ai_images": {"type": "boolean"}, **_WAIT})),
    "vividora_job_status": (t_job, "किसी job की स्थिति (running/done/failed + file)", _obj({"job_id": {"type": "string"}}, ["job_id"])),
    "vividora_download_file": (t_download, "Library की file (wav/glb/webm/mp4) local path पर सेव करें", _obj({
        "file_id": {"type": "string"}, "save_to": {"type": "string"}}, ["file_id", "save_to"])),
}


def handle(msg: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:  # notification
        return None
    try:
        if method == "initialize":
            res = {"protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "vividora", "version": "1.0"}}
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items()]}
        elif method == "tools/call":
            name = params.get("name")
            if name not in TOOLS:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
            try:
                out = TOOLS[name][0](params.get("arguments") or {})
                res = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}]}
            except ToolError as e:
                res = {"content": [{"type": "text", "text": str(e)}], "isError": True}
            except KeyError as e:
                res = {"content": [{"type": "text", "text": f"missing argument: {e}"}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": res}
    except Exception as e:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        out = handle(msg)
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
