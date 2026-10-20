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

COPY vividora ./vividora
COPY presets ./presets
COPY fonts ./fonts
COPY starter ./starter
# make the Devanagari font visible to libass
RUN mkdir -p /usr/local/share/fonts/vividora && cp fonts/*.ttf /usr/local/share/fonts/vividora/ && fc-cache -f

ENV PYTHONUNBUFFERED=1 PRESETS_DIR=/app/presets WEB_DIST=/app/web-dist
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "vividora.app:app", "--host", "0.0.0.0", "--port", "8000"]
