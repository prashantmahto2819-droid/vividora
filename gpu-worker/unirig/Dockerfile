# UniRig auto-rigging worker for RunPod serverless (or any GPU host: run handler.py behind your own HTTP shim).
# Build:  docker build -t YOURUSER/vividora-unirig gpu-worker/unirig   → push → RunPod "New Endpoint" from this image.
# Check UniRig's README for the current torch/spconv versions if the pip lines below drift.
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 HF_HOME=/opt/hf
RUN apt-get update && apt-get install -y --no-install-recommends python3.11 python3.11-dev python3-pip git wget ca-certificates \
    libgl1 libxi6 libxkbcommon0 libsm6 libxrender1 libxfixes3 && rm -rf /var/lib/apt/lists/* && ln -sf /usr/bin/python3.11 /usr/local/bin/python
RUN git clone --depth 1 https://github.com/VAST-AI-Research/UniRig /opt/UniRig
WORKDIR /opt/UniRig
RUN python -m pip install torch==2.3.1 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 \
 && python -m pip install -r requirements.txt \
 && python -m pip install spconv-cu120 \
 && python -m pip install torch-scatter torch-cluster -f https://data.pyg.org/whl/torch-2.3.1+cu121.html \
 && python -m pip install numpy==1.26.4 runpod
COPY handler.py /handler.py
CMD ["python", "-u", "/handler.py"]
