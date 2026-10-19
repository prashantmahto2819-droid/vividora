# Google Drive (5 TB) के साथ Vividora — सही तरीका

**सीधा जवाब:** editing का काम Drive पर नहीं, local disk पर होना चाहिए। ffmpeg/Whisper को तेज़ random access चाहिए;
Drive को mount करके render करने पर 5–10× धीमा, timeouts, और Google API rate-limits मिलते हैं।
**Drive का सही काम = archive + backup**: approve होते ही (या N दिन बाद) raw recording, clips और work audio Drive पर चले जाते हैं,
finished videos का backup भी — server की disk खाली रहती है। दोबारा edit करना हो तो "raw वापस लाएँ" एक click।

## 1. VM की disk बढ़ाएँ (एक बार)
VMware → VM settings → Hard disk → Expand (जैसे 400 GB; D drive पर जगह हो तो)। फिर Ubuntu में:
```bash
sudo growpart /dev/sda 2 && sudo resize2fs /dev/sda2   # device नाम lsblk से देखें
df -h /srv/studio
```

## 2. rclone + Google Drive (free)
VM पर:
```bash
sudo apt install -y rclone
rclone config
# n (new) → name: gdrive → storage: drive → client_id/secret खाली छोड़ें (या अपना Google Cloud OAuth client डालें = तेज़)
# scope: 1 (full) → root_folder_id खाली → service account नहीं → auto config: n (VM headless है)
#   → यह एक command देगा "rclone authorize ..." जिसे अपने Windows PC पर rclone install करके चलाएँ, token copy करके VM में paste करें
rclone mkdir gdrive:Vividora && rclone lsd gdrive:
```
`.env`:
```
ARCHIVE_RCLONE_REMOTE=gdrive:Vividora
RCLONE_CONFIG_DIR=/home/prashant/.config/rclone
ARCHIVE_AFTER_DAYS=7
```
`docker compose up -d --build` — status page पर "archive: rclone · gdrive:Vividora" दिखेगा।

## 3. क्या होता है
- हर घंटे: approved + ARCHIVE_AFTER_DAYS से पुराने projects → raw/clips/audio Drive पर **move**, renders **copy**।
- Export dialog में "☁ archive" से तुरंत; "raw वापस लाएँ" से restore।
- Drive में structure वही: `Vividora/ws_<id>/p_<project>/raw/…`

## 4. Drive से import (भविष्य)
Drive पर रखी पुरानी recordings को सीधे project में लाना — अगले version में (rclone copy से अभी भी हो सकता है)।
