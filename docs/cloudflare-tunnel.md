# Cloudflare Tunnel + Access (free) — Vividora को बाहर से खोलना

बिना port forward, बिना public IP। सिर्फ़ Tunnel + Access, कोई R2/Workers नहीं।

## 1. Tunnel (VM पर, एक बार)
```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared
cloudflared tunnel login            # browser खुलेगा, domain चुनें
cloudflared tunnel create vividora
cloudflared tunnel route dns vividora studio.YOURDOMAIN.com
```
`~/.cloudflared/config.yml`:
```yaml
tunnel: vividora
credentials-file: /home/prashant/.cloudflared/<TUNNEL-ID>.json
ingress:
  - hostname: studio.YOURDOMAIN.com
    service: http://localhost:8000
  - service: http_status:404
```
```bash
sudo cloudflared service install && sudo systemctl enable --now cloudflared
```

## 2. Access (login wall)
Zero Trust dashboard → Access → Applications → Add → Self-hosted
- Application domain: `studio.YOURDOMAIN.com`
- Policy "team": Allow · Emails → आपके और team के emails (One-time PIN login)
- **दूसरी policy "bypass"** (ऊपर रखें): Action **Bypass** · Everyone · path `/pub/*` और `/api/connect/*` और `/api/hooks/*`
  (Instagram/Facebook वीडियो `/pub/...` से उठाते हैं; Google/Meta OAuth callback और WhatsApp replies बिना login आते हैं — इन paths पर Vividora की अपनी signed-token/secret जाँच है)

## 3. .env
```
PUBLIC_URL=https://studio.YOURDOMAIN.com
CORS_ORIGINS=https://studio.YOURDOMAIN.com
```
`docker compose up -d` — बस। फ़ोन से भी वही URL, PWA install कर सकते हैं।
