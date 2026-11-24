# WhisperX — exact word times (optional, experimental)

Off by default. It changes nothing until **both** are true: the image was built with WhisperX, and
API & Keys → “शब्दों का सटीक समय” is set to WhisperX.

## Turn on

1. On the server: `cd /srv/studio/vividora && nano .env` → add the line `WITH_WHISPERX=1` → save.
2. Rebuild (takes 10–15 minutes the first time, the image grows by about 2 GB):
   `git pull && docker compose --profile tunnel up -d --build && docker compose ps`
3. Dashboard → Settings → API & Keys → “कहाँ चलाएँ · खर्च” → **शब्दों का सटीक समय** → *WhisperX* → save.
4. Upload a short video (or “transcript दोबारा बनाएँ”). The first run downloads the language's alignment model
   (Hindi: about 1.2 GB) into the worker; the job log shows “शब्दों का समय ठीक कर रहा हूँ (WhisperX)”.

## If something breaks

WhisperX pins its own versions of some packages; if the build fails or transcripts stop working after step 2,
remove `WITH_WHISPERX=1` from `.env` and run the command of step 2 again — the image is back to what it was.

## What it does

`engine/align.py` sends the finished transcript to `whisperx.align`. Word times are taken only where safe (same word count
in the line, no jump over 1 s, no overlap); numbers and anything the aligner cannot place keep Whisper's time. Any error
leaves the transcript untouched.
