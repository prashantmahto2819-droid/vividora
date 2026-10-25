FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fontconfig rclone curl ca-certificates libfribidi0 fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*
# DeepFilterNet (MIT/Apache-2.0) — studio-grade noise removal for the voice track
RUN curl -fsSL -o /usr/local/bin/deep-filter \
      https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-unknown-linux-musl \
    && chmod +x /usr/local/bin/deep-filter && deep-filter --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# yt-dlp: YouTube → Shorts/Reels converter needs it to download source videos
RUN pip install --no-cache-dir yt-dlp
# ElevenLabs + Google Cloud TTS SDKs for cloud voice generation
RUN pip install --no-cache-dir elevenlabs google-cloud-texttospeech
# 3D Studio renders three.js scenes in headless Chromium (software GL) — playwright brings the browser + its libs
RUN pip install --no-cache-dir playwright==1.56.0 && playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
ENV CHARS3D_PAGE_URL=http://api:8000/assets/3d.html

COPY vividora ./vividora
COPY presets ./presets
COPY fonts ./fonts
COPY starter ./starter
# make the Devanagari font visible to libass
RUN mkdir -p /usr/local/share/fonts/vividora && cp fonts/*.ttf /usr/local/share/fonts/vividora/ && fc-cache -f

ENV PYTHONUNBUFFERED=1 PRESETS_DIR=/app/presets WEB_DIST=/app/web-dist
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "vividora.app:app", "--host", "0.0.0.0", "--port", "8000"]
