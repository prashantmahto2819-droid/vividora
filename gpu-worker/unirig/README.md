# UniRig cloud-GPU worker (auto-rigging)

Vividora's server has no CUDA, so **🦴 Rig (cloud GPU)** on a 3D model sends the .glb to a serverless GPU worker running
[UniRig](https://github.com/VAST-AI-Research/UniRig) (skeleton + skin weights) and saves the rigged .glb in the Library.
You pay only while a rig job runs (RunPod serverless: per second of GPU; cold start 1–3 min the first time).

## One-time setup (RunPod)
1. Account + credit: https://www.runpod.io/console/user/billing (a few dollars is plenty to start).
2. Build and push the image (on any PC/VM with Docker; or use RunPod's GitHub build):
   ```
   cd gpu-worker/unirig
   docker build -t YOURDOCKERUSER/vividora-unirig:1 .
   docker push YOURDOCKERUSER/vividora-unirig:1
   ```
3. https://www.runpod.io/console/serverless → **New Endpoint** → Custom image `YOURDOCKERUSER/vividora-unirig:1`,
   GPU: a 24 GB card (e.g. RTX 4090/A5000), Max workers 1, Idle timeout ~30 s, Execution timeout 900 s.
4. Copy the **Endpoint ID** (and create an API key at https://www.runpod.io/console/user/settings → API Keys).
5. On the Vividora VM, in `/srv/studio/vividora/.env`:
   ```
   UNIRIG_ENDPOINT_ID=xxxxxxxx
   RUNPOD_API_KEY=rpa_xxxxxxxx
   ```
   then `docker compose --profile tunnel up -d --build`.
6. Vividora → 3D models → **🦴 Rig (cloud GPU)** on a model. Start with a small humanoid .glb (< 8 MB).

## Notes / honest limits
* `handler.py` was written from UniRig's documented launch scripts and tested only with stubbed stages (no GPU in the
  build environment). Do a first run from the RunPod console ("Requests" tab) with a small .glb; if a stage fails, the error
  tail comes back to Vividora and into the job message — flags may need a small tweak for your UniRig version.
* The `template` choice (mixamo/vroid/articulationxl) is passed through but the shipped handler uses UniRig's default skeleton.
* UniRig's license/model terms apply to its output pipeline — check the repo's license before commercial use.
* Not using RunPod? Any host that serves `POST /run` + `GET /status/{id}` (see `server/vividora/engine/unirig.py`) works via `UNIRIG_URL` (+ `UNIRIG_TOKEN`).
