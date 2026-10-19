"""Small HTTP helpers (stdlib) shared by the YouTube and Meta clients."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class PublishError(RuntimeError):
    def __init__(self, message: str, *, retry: bool = False):
        super().__init__(message)
        self.retry = retry


def request(method: str, url: str, *, params: dict | None = None, data: Any = None, form: dict | None = None,
            headers: dict | None = None, timeout: float = 120) -> dict:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    h = dict(headers or {})
    body: bytes | None = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt.strip() else {}
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:800]
        try:
            j = json.loads(msg)
            err = j.get("error", j)
            msg = err.get("message") if isinstance(err, dict) else str(err)
        except ValueError:
            pass
        raise PublishError(f"{e.code}: {msg}", retry=e.code in (429, 500, 502, 503, 504)) from None
    except urllib.error.URLError as e:
        raise PublishError(f"network: {e.reason}", retry=True) from None


def upload_file(url: str, path: Path, *, headers: dict, chunk: int = 8 * 1024 * 1024,
                on_progress=None, timeout: float = 600) -> dict:
    """Resumable upload of a whole file in sequential chunks (Google style
    Content-Range). Returns the final JSON body."""
    size = path.stat().st_size
    sent = 0
    with path.open("rb") as f:
        while sent < size:
            part = f.read(chunk)
            end = sent + len(part) - 1
            h = {**headers, "Content-Length": str(len(part)), "Content-Range": f"bytes {sent}-{end}/{size}"}
            req = urllib.request.Request(url, data=part, method="PUT", headers=h)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    txt = r.read().decode()
                    sent = end + 1
                    if on_progress:
                        on_progress(sent / size)
                    if r.status in (200, 201):
                        return json.loads(txt) if txt.strip() else {}
            except urllib.error.HTTPError as e:
                if e.code == 308:  # resume incomplete: Google tells us how far it got
                    rng = e.headers.get("Range")
                    sent = int(rng.split("-")[1]) + 1 if rng else sent + len(part)
                    f.seek(sent)
                    if on_progress:
                        on_progress(sent / size)
                    continue
                msg = e.read().decode(errors="replace")[:500]
                raise PublishError(f"upload {e.code}: {msg}", retry=e.code in (429, 500, 502, 503, 504)) from None
            except urllib.error.URLError as e:
                raise PublishError(f"upload network: {e.reason}", retry=True) from None
    return {}
