# OpenCLIP — match clips by looking at them, on this server (optional, experimental)

Off by default. It changes nothing until **both** are true: the image was built with OpenCLIP, and
API & Keys → “Clips को तस्वीर देखकर मिलाना” is on.

## Turn on

1. Check the disk first: `df -h /` — keep at least 10 GB free (PyTorch about 2 GB, the model about 1.5 GB).
2. `cd /srv/studio/vividora && nano .env` → add `WITH_OPENCLIP=1` → save.
3. `git pull && docker compose --profile tunnel up -d --build && docker compose ps` (10–15 minutes the first time).
4. Dashboard → Settings → API & Keys → “कहाँ चलाएँ · खर्च” → **Clips को तस्वीर देखकर मिलाना** → *चालू* → save.
5. Editor → AI Studio → supporting clips → “सही जगह ढूँढो”. The first run downloads the model (about 1.5 GB) and is slow;
   clips placed this way are labelled “👁 तस्वीर देखकर मिलाया (CLIP — जाँच लें)”.

## Turn off / undo

Switch it off in API & Keys (instant). To remove it from the image: delete `WITH_OPENCLIP=1` from `.env` and run step 3 again.

## What it does

`engine/clipsee.py`: every clip (two frames of a video, or the photo) and every spoken line become vectors with a multilingual
CLIP model (`CLIP_MODEL`, default `xlm-roberta-base-ViT-B-32` / `laion5b_s13b_b90k`, reads Hindi and English). A clip is placed on a
line only when that line stands clearly above the clip's own average (and above `CLIP_MIN_SIM`, default 0.18). Order of trust
stays: a time you wrote → Gemini reading the talk → spoken words → CLIP → name order. The picture's vector is kept in the Library
item, so each clip is looked at once.

The threshold was chosen without real footage; if it places too much or too little, set `CLIP_MIN_SIM` in `.env` (0.15 looser … 0.25 stricter).
