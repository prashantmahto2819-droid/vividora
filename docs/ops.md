# Server देखभाल — ज़रूरी checklist (Ubuntu VM yt-meta)

## हर update पर
1. PowerShell: `ssh prashant@192.168.1.31` (IP router में fix किया हुआ है)
2. `cd /srv/studio/vividora`
3. `git pull`
4. `docker compose --profile tunnel up -d --build` (tunnel profile के बिना cloudflared नहीं उठता)
5. `docker compose ps` — `api` **healthy**, `cloudflared` **Up**
6. Browser में Ctrl+Shift+R

## VM को बंद/restart करना
- हमेशा `sudo shutdown now` या `sudo reboot` — VMware से सीधा power-off नहीं। (अचानक बंद होने से Docker की network database ख़राब हुई थी: `panic: page … already freed`)
- Docker ख़राब हो तो: `/var/lib/docker/network/files/local-kv.db` को backup लेकर `.corrupt` नाम से हटाएँ, `sudo systemctl reset-failed docker docker.socket && sudo systemctl start docker`।

## Services जो Docker से बाहर हैं
`systemctl is-active triposr voicestudio voicestudio-proxy` — `inactive` हो तो:
`sudo systemctl enable --now triposr voicestudio voicestudio-proxy`

## Error 1033 (Cloudflare Tunnel)
1. `docker compose logs --tail 30 cloudflared`
2. "failed to dial … quic" → compose में `TUNNEL_TRANSPORT_PROTOCOL: http2` (अब default है)
3. "Registered tunnel connection" दिखे तो tunnel ठीक; Cloudflare → Zero Trust → Networks → Tunnels में **HEALTHY**
4. Public Hostname की service: `http://api:8000` (IP नहीं)

## सुरक्षा (एक बार करें)
1. VM password बदलें: `passwd`
2. Cloudflared token पहले leak हुआ था → https://one.dash.cloudflare.com → Networks → Tunnels → tunnel → **Refresh token** → `.env` में `CLOUDFLARE_TUNNEL_TOKEN` बदलें → `docker compose --profile tunnel up -d`
3. API keys सिर्फ़ ज़रूरत भर के role से बनाएँ; लीक पर Dashboard → API & Integrations से revoke।
4. Router (Omada ER605) में VM का Address Reservation (MAC 00-0C-29-F8-ED-96 → 192.168.1.31) लगा है — हटाएँ नहीं।

## Backup
- असली data: `/srv/studio/data` (DB, settings) और `/srv/studio/media`, `/srv/studio/archive`। इन्हें समय-समय पर Windows drive पर copy करें: `sudo rsync -a /srv/studio/data /srv/studio/media <backup-जगह>/`
