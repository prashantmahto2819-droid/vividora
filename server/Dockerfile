FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vividora ./vividora
COPY presets ./presets
COPY fonts ./fonts
# make the Devanagari font visible to libass
RUN mkdir -p /usr/local/share/fonts/vividora && cp fonts/*.ttf /usr/local/share/fonts/vividora/ && fc-cache -f

ENV PYTHONUNBUFFERED=1 PRESETS_DIR=/app/presets WEB_DIST=/app/web-dist
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "vividora.app:app", "--host", "0.0.0.0", "--port", "8000"]
