# Vividora को SaaS की तरह चलाना (plans, quota, Razorpay)

Default में app **self-hosted** mode में है — एक workspace, कोई limit नहीं, signup बंद। public करने के लिए `.env` में:

```
SAAS_MODE=1
SECRET_KEY=<32+ अक्षर random>        # python3 -c "import secrets;print(secrets.token_urlsafe(48))"
WORKER_TOKEN=<16+ अक्षर random>
PUBLIC_URL=https://studio.example.com
RAZORPAY_KEY_ID=rzp_live_xxx
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=xxx          # Razorpay dashboard → Webhooks में वही secret
RAZORPAY_PLAN_creator_monthly=plan_xxx   # हर plan × cycle के लिए Razorpay का plan id
RAZORPAY_PLAN_creator_annual=plan_xxx
RAZORPAY_PLAN_studio_monthly=plan_xxx
GST_RATE=0.18                        # कीमत GST-inclusive मानी जाती है; receipt में अलग दिखती है
BILLING_SELLER_NAME=आपकी firm         BILLING_GSTIN=...
TRIAL_DAYS=14                        # signup पर Free trial
SIGNUP_OPEN=1  INVITE_ONLY=0         # INVITE_ONLY=1 → सिर्फ़ invite link से signup
REQUIRE_EMAIL_VERIFY=0               # 1 करने पर verify token बनता है (mail भेजना अभी manual है)
OPERATOR_WORKSPACE=<आपका workspace id>   # खाली = सबसे पहला workspace (bootstrap वाला)
BACKUP_KEEP_DAYS=7
```

`SAAS_MODE=1` में default/छोटे `SECRET_KEY`/`WORKER_TOKEN` पर app **start ही नहीं होता** (जानबूझकर)।

## Plans और कीमत

Plans की कीमत code में नहीं है। क्रम: `PLANS_JSON` (env में JSON list) → `server/presets/plans.json` → built-in seed (Free/Creator/Studio, ₹0 placeholder)।
Format (`presets/plans.example.json` देखें):

```json
[{"id":"creator","name":"Creator","order":1,
  "price_inr":{"monthly":499,"quarterly":1299,"annual":4499},
  "limits":{"ai_credits":300,"render_minutes":300,"storage_gb":50,"max_export_height":1080,
            "concurrent_jobs":1,"premium_voices":true,"music_gen":false,"templates":100}}]
```

Limits कहाँ लगते हैं:

| Limit | कहाँ रुकता है | message |
|---|---|---|
| `storage_gb` | upload शुरू करते समय, library upload | 402 `quota: storage` |
| `render_minutes` | Export / render request (output seconds × platforms) | 402 `quota: render_minutes` |
| `max_export_height` | Export (platform preset या Advanced resolution) | 402 `quota: export_height` |
| `ai_credits` | हर नया LLM call (cache से जवाब free) — API और worker दोनों | AI fallback + "credits पूरे" |
| `concurrent_jobs` | queue claim — workspace के इतने job एक साथ | job कतार में रहता है |
| `premium_voices` | AI voice-over (Parler/custom आवाज़ें; Kokoro हमेशा free) | 402 `quota: premium_voices` |

Queue अब **fair** है: हर workspace अपनी limit तक, फिर जिसने सबसे देर से job पाया उसे पहले — एक user पूरी कतार नहीं रोक सकता।

## Subscription का जीवन

| घटना | Razorpay event | status | असर |
|---|---|---|---|
| Signup | — | `trialing` (Free, TRIAL_DAYS) | Free limits |
| "यह लें" → hosted checkout | `subscription.activated` / `charged` | `active`, period Razorpay से | plan limits; invoice row |
| हर renewal | `subscription.charged` | `active`, नया period | usage नया period |
| payment fail | `payment.failed` / `subscription.pending` | `past_due` | AI 0, render 0, upload बंद (देख सकते हैं, download कर सकते हैं) |
| user ने cancel दबाया | `subscription.cancelled` (cycle end) | `cancelled` | period खत्म होते ही expired limits |
| trial/period की तारीख़ निकल गई | — | `expired` | same as past_due |
| Upgrade/downgrade | नया checkout → नया subscription | पुराना cancel at cycle end करें | Razorpay में proration नहीं है — नया plan अगले cycle से |

Admin (operator workspace) किसी भी workspace को हाथ से plan दे सकता है: Admin → Workspaces → "plan दें" (30 दिन) — offline payment / comp के लिए।

## Webhook

Razorpay dashboard → Webhooks → URL `https://<PUBLIC_URL>/api/hooks/razorpay`, secret = `RAZORPAY_WEBHOOK_SECRET`, events: `subscription.activated, subscription.charged, subscription.pending, subscription.halted, subscription.cancelled, subscription.completed, payment.captured, payment.failed`.
Signature (`X-Razorpay-Signature`, HMAC-SHA256 of raw body) गलत → 401, कुछ नहीं लिखा जाता। हर event `billing_events` में id से एक बार ही लगता है (duplicate delivery safe)। Cloudflare Access पर `/api/hooks/*` bypass रखें।

## Security (हमेशा चालू, SAAS_MODE के बिना भी)

- `connections.secrets` (YouTube/Meta tokens) DB में **Fernet-encrypted** (`SECRET_KEY` से key)। पुराने plaintext rows पहले start पर encrypt हो जाते हैं। `SECRET_KEY` बदलने पर tokens नहीं पढ़े जा सकते → channel दोबारा connect।
- Login: 5 गलत → 15 मिनट lock (email+IP); `/api/auth/*`, uploads, library, hooks पर per-IP rate limit (429)।
- Password: 8+, अक्षर+अंक, आम passwords मना। Password बदलने या "सब devices से बाहर" पर पुराने tokens मर जाते हैं (`token_version`)।
- Upload: finish पर ffprobe से असली video/audio की जाँच; library में image/font के magic bytes।
- Worker file routes: worker हर request में `X-Job` भेजता है → सिर्फ़ उसी job के workspace की files मिलती हैं।
- Backup: रोज़ एक SQLite backup `DATA_ROOT/backups/` (7 दिन), archive remote (rclone/Drive) पर भी copy। Admin → "अभी backup लें"। Restore: app बंद → file को `vividora.db` पर copy (-wal/-shm हटाएँ) → start।
- Audit log: Admin page पर (login, signup, user/role, publish, billing, backup)।

## अभी नहीं है (जानबूझकर)

- Email भेजना (verify/invite mail) — `REQUIRE_EMAIL_VERIFY=1` पर token बनता है, mail आप खुद भेजें या SMTP जोड़ें।
- Proration, refunds, GST invoice PDF — receipt HTML (print) है।
- Multi-node rate limit (in-memory है — एक server के लिए ठीक)।
