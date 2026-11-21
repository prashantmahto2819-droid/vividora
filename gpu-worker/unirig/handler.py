"""RunPod serverless handler: GLB in → UniRig (skeleton → skin weights → merge) → rigged GLB out.

Input : {"input": {"glb_b64": "<base64 .glb>", "template": "mixamo|vroid|articulationxl"}}
Output: {"glb_b64": "<base64 rigged .glb>", "template_used": "..."} or {"error": "..."}

UniRig lives in UNIRIG_DIR (default /opt/UniRig). The three stages are UniRig's own launch scripts
(launch/inference/generate_skeleton.sh, generate_skin.sh, merge.sh). Flags can differ between UniRig versions —
if a stage fails the error text (stderr tail) is returned to Vividora so you can see why. NOT verified on a real GPU
from the Vividora repo's test environment: do a first run from the RunPod console with a small .glb before relying on it.
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path

UNIRIG_DIR = os.getenv("UNIRIG_DIR", "/opt/UniRig")
STAGE_TIMEOUT = int(os.getenv("UNIRIG_STAGE_TIMEOUT", "600"))


def _stage(run, name: str, args: list[str]) -> None:
    r = run(["bash", f"launch/inference/{name}.sh", *args], cwd=UNIRIG_DIR, capture_output=True, text=True, timeout=STAGE_TIMEOUT)
    if r.returncode != 0:
        raise RuntimeError(f"{name} failed: {(r.stderr or r.stdout or '')[-400:]}")


def rig(inp: dict, run=subprocess.run) -> dict:
    try:
        glb = base64.b64decode(inp.get("glb_b64") or "")
        if glb[:4] != b"glTF":
            return {"error": "input is not a .glb"}
        template = str(inp.get("template") or "mixamo")
        with tempfile.TemporaryDirectory(prefix="unirig_") as td:
            td = Path(td)
            src, skel, skin, out = td / "in.glb", td / "skeleton.fbx", td / "skin.fbx", td / "rigged.glb"
            src.write_bytes(glb)
            _stage(run, "generate_skeleton", ["--input", str(src), "--output", str(skel)])
            _stage(run, "generate_skin", ["--input", str(skel), "--output", str(skin)])
            _stage(run, "merge", ["--source", str(skin), "--target", str(src), "--output", str(out)])
            if not out.exists() or out.read_bytes()[:4] != b"glTF":
                return {"error": "merge produced no .glb"}
            return {"glb_b64": base64.b64encode(out.read_bytes()).decode(), "template_used": os.getenv("UNIRIG_TEMPLATE", "unirig-default"), "requested": template}
    except subprocess.TimeoutExpired:
        return {"error": "UniRig stage timed out"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:400]}


def handler(event: dict) -> dict:
    return rig(event.get("input") or {})


if __name__ == "__main__":
    import runpod  # type: ignore

    runpod.serverless.start({"handler": handler})
