# बड़ी original files Windows की D: drive पर

Vividora में upload हुई original videos (raw recordings, clips) और library की videos/music
VM की disk की जगह Windows की **D: drive** पर रखी जा सकती हैं। Editing हमेशा VM पर बनी
छोटी **proxy** (720p) से होती है, और renders व database VM की तेज़ disk पर रहते हैं।
इससे VM की disk नहीं भरती और बड़ी files से system hang नहीं होता।

| क्या | कहाँ |
|---|---|
| Upload की गई original video, clips | D: drive (`RAW_DIR`) |
| Library की videos, music, images | D: drive |
| Proxy (720p), audio, cutout, temp files | VM disk (`MEDIA_DIR`) |
| Final renders, thumbnails | VM disk |
| Database | VM disk (`DATA_DIR`) |

## 1. Windows पर (एक बार)

1. D: drive में एक folder बनाएँ: `D:\VividoraRaw`
2. उस folder के अंदर एक खाली file बनाएँ जिसका नाम हो: `.vividora-share`
   (PowerShell: `New-Item D:\VividoraRaw\.vividora-share -ItemType File`)
   — यह निशान बताता है कि share सच में जुड़ा है।
3. VMware Workstation → **yt-meta** VM → **Settings → Options → Shared Folders** →
   **Always enabled** → **Add** → Host path `D:\VividoraRaw`, Name `VividoraRaw` → Enable → OK।

## 2. VM (Ubuntu) में (एक बार)

```bash
sudo apt-get install -y open-vm-tools
vmware-hgfsclient                       # "VividoraRaw" दिखना चाहिए
sudo mkdir -p /mnt/vividora-raw
echo ".host:/VividoraRaw /mnt/vividora-raw fuse.vmhgfs-fuse defaults,allow_other,uid=0,gid=0,nofail 0 0" | sudo tee -a /etc/fstab
sudo mount -a
ls -la /mnt/vividora-raw                # .vividora-share दिखनी चाहिए
```

फिर `/srv/studio/app/.env` में:
```
RAW_DIR=/mnt/vividora-raw
```
और:
```bash
cd /srv/studio/app && docker compose --profile tunnel up -d --force-recreate api
```

Studio → **Status** → Disk में "D: drive (originals) · ✓ चालू" दिखना चाहिए।

## ध्यान रखें

- Windows या VM restart के बाद Status में "✗ बंद" दिखे, तो VM में `sudo mount -a` और फिर
  `docker compose --profile tunnel restart api` चलाएँ। बंद रहने पर app files को VM disk पर
  रखता है (कुछ नहीं खोता) — share वापस आने पर नई files फिर D: पर जाएँगी।
- पुरानी files जहाँ हैं वहीं से मिलती रहेंगी; सिर्फ़ नई uploads D: पर जाएँगी।
- D: drive का `VividoraRaw` folder हाथ से न बदलें/हटाएँ — project हटाने पर app खुद साफ़ करता है।
