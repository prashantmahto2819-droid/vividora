"""HTTP client every worker uses to talk to the API. Only the standard library,
so the same file runs on the Windows GPU worker without extra packages."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class ApiClient:
    def __init__(self, base_url: str, token: str, worker: str):
        self.base = base_url.rstrip("/")
        self.token = token
        self.worker = worker

    def _req(self, method: str, path: str, data: Any = None, *, raw: bytes | Path | None = None,
             timeout: float = 60) -> Any:
        url = f"{self.base}/api{path}"
        headers = {"X-Worker-Token": self.token}
        body: bytes | Any = None
        if raw is not None:
            headers["Content-Type"] = "application/octet-stream"
            body = raw.open("rb") if isinstance(raw, Path) else raw
        elif data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                txt = r.read().decode()
                return json.loads(txt) if txt else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            raise RuntimeError(f"{method} {path} → {e.code}: {msg}") from None
        finally:
            if isinstance(raw, Path) and hasattr(body, "close"):
                body.close()

    def claim(self, kinds: list[str], info: dict | None = None) -> dict | None:
        r = self._req("POST", "/worker/claim", {"kinds": kinds, "worker": self.worker, "info": info or {}})
        return r if r.get("job") else None

    def heartbeat(self, job_id: str, progress: float | None = None, message: str | None = None) -> bool:
        r = self._req("POST", f"/worker/jobs/{job_id}/heartbeat",
                      {"progress": None if progress is None else int(progress), "message": message})
        return not r.get("cancelled")

    def done(self, job_id: str, result: dict) -> None:
        self._req("POST", f"/worker/jobs/{job_id}/done", {"result": result}, timeout=120)

    def failed(self, job_id: str, error: str, retry: bool = True) -> None:
        self._req("POST", f"/worker/jobs/{job_id}/failed", {"error": error, "retry": retry})

    def download(self, asset_id: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(f"{self.base}/api/worker/files/{asset_id}",
                                     headers={"X-Worker-Token": self.token})
        with urllib.request.urlopen(req, timeout=600) as r, dest.open("wb") as f:
            shutil.copyfileobj(r, f, 1024 * 1024)
        return dest

    def download_library(self, item_id: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(f"{self.base}/api/worker/library/{item_id}",
                                     headers={"X-Worker-Token": self.token})
        with urllib.request.urlopen(req, timeout=600) as r, dest.open("wb") as f:
            shutil.copyfileobj(r, f, 1024 * 1024)
        return dest

    def upload(self, job_id: str, path: Path, kind: str, label: str | None = None) -> dict:
        q = f"kind={kind}&name={urllib.request.quote(path.name)}"
        if label:
            q += f"&label={urllib.request.quote(label)}"
        return self._req("PUT", f"/worker/jobs/{job_id}/upload?{q}", raw=path, timeout=3600)


def run_loop(client: ApiClient, kinds: list[str], handler, *, poll: float = 3.0, info: dict | None = None,
             once: bool = False) -> None:
    """Claim → handle → report, forever. `handler(client, job, project, assets)` returns the result dict."""
    import logging
    log = logging.getLogger("vividora.worker")
    log.info("worker %s ready for %s", client.worker, kinds)
    while True:
        try:
            claimed = client.claim(kinds, info)
        except Exception as e:  # API down — wait and try again
            log.warning("API से संपर्क नहीं: %s", e)
            time.sleep(min(60, poll * 5))
            continue
        if not claimed:
            if once:
                return
            time.sleep(poll)
            continue
        job = claimed["job"]
        log.info("job %s %s (project %s)", job["id"], job["kind"], job["project_id"])
        import threading
        stop = threading.Event()

        def _keepalive():  # long steps (Whisper, TTS, big renders) may not report progress for minutes
            while not stop.wait(45):
                try:
                    client.heartbeat(job["id"])
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=_keepalive, daemon=True).start()
        try:
            result = handler(client, job, claimed["project"], claimed["assets"])
            client.done(job["id"], result)
            log.info("job %s done", job["id"])
        except Exception as e:
            import traceback
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
            log.error("job %s failed: %s", job["id"], e)
            try:
                client.failed(job["id"], err, retry=not isinstance(e, ValueError) and not getattr(e, "no_retry", False))
            except Exception as e2:
                log.error("could not report failure: %s", e2)
        stop.set()
        if once:
            return
