"""TripoSR HTTP API for Vividora (copy to /srv/studio/triposr/api_server.py).
Follows the official run.py preprocessing: foreground on a *mid-grey (0.5)* background — TripoSR is trained on that,
a white background gives scattered junk. Input that is already transparent skips background removal."""
import os, tempfile, uuid, sys
import numpy as np
import torch
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from tsr.system import TSR
from tsr.utils import remove_background, resize_foreground

MC_RESOLUTION = int(os.getenv("TRIPOSR_MC_RESOLUTION", "256"))
FG_RATIO = float(os.getenv("TRIPOSR_FG_RATIO", "0.85"))

app = FastAPI(title="TripoSR API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
model = None


@app.on_event("startup")
async def load_model():
    global model
    print("Loading TripoSR model...")
    model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
    model.renderer.set_chunk_size(8192)
    model.to("cpu")
    print("Model loaded!")


def _prepare(path: str) -> Image.Image:
    img = Image.open(path)
    has_alpha = img.mode in ("RGBA", "LA") and np.array(img.convert("RGBA"))[:, :, 3].min() < 250
    if has_alpha:
        img = img.convert("RGBA")
    else:
        img = remove_background(img.convert("RGB"), rembg_session=None)
    img = resize_foreground(img, FG_RATIO)
    a = np.array(img.convert("RGBA")).astype(np.float32) / 255.0
    a = a[:, :, :3] * a[:, :, 3:4] + (1 - a[:, :, 3:4]) * 0.5  # grey background, as in the official run.py
    return Image.fromarray((a * 255.0).astype(np.uint8))


def _clean(mesh):
    """Drop floating specks: keep connected parts with at least 3% of the biggest part's faces."""
    try:
        parts = mesh.split(only_watertight=False)
        if len(parts) > 1:
            big = max(len(p.faces) for p in parts)
            keep = [p for p in parts if len(p.faces) >= 0.03 * big]
            import trimesh
            mesh = trimesh.util.concatenate(keep)
    except Exception as e:  # noqa: BLE001
        print("mesh clean skipped:", e)
    return mesh


@app.post("/api/image-to-3d")
async def image_to_3d(image: UploadFile = File(...)):
    job_id = str(uuid.uuid4())[:8]
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, f"{job_id}_input.png")
    glb_path = os.path.join(temp_dir, f"{job_id}.glb")
    with open(input_path, "wb") as f:
        f.write(await image.read())
    img = _prepare(input_path)
    img.save(os.path.join(temp_dir, f"{job_id}_prepared.png"))
    with torch.no_grad():
        scene_codes = model([img], device="cpu")
        meshes = model.extract_mesh(scene_codes, has_vertex_color=True, resolution=MC_RESOLUTION)
    mesh = _clean(meshes[0])
    print(f"mesh: {len(mesh.vertices)} verts, {len(mesh.faces)} faces")
    mesh.export(glb_path)
    return FileResponse(glb_path, media_type="model/gltf-binary", filename=f"{job_id}.glb")


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}
