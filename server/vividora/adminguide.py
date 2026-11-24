"""The admin guide of API & Keys: what every key and switch does, which job runs where, what it costs, how to test it.

One source for three places: the "📖 Guide" tab, the "ℹ️ इससे क्या होगा" note under each row (provkeys.status adds `help`),
and docs/admin-guide.md (written by `python -m vividora.adminguide`; tests/test_adminguide.py keeps the file in step).
Prices are the estimates of engine/meter.py — the real bill is on each service's own site.
"""

from __future__ import annotations

# env → [(state, what happens)] — shown under the row, and in the guide's switch list
HELP: dict[str, list[tuple[str, str]]] = {
    "PUBLIC_URL": [("भरा हो", "share links, webhook और social login के लिंक इसी पते से बनते हैं (जैसे https://studio.vividbrandify.com)"),
                   ("खाली हो", "लिंक में server का अंदरूनी पता आ सकता है — बाहर से नहीं खुलेंगे; Settings में चेतावनी दिखती है")],
    "GEMINI_API_KEY": [("डाली हो", "AI title / description / hashtags, script, Shorts के title, transcript की spelling सुधार, supporting clips को “खोलकर देखना”, visuals के सुझाव — सब चालू"),
                       ("न हो", "ये सब सादे नियमों से चलते हैं (कम समझदार); कोई काम रुकता नहीं")],
    "ANTHROPIC_API_KEY": [("डाली हो", "Gemini न हो तो वही काम Claude से (paid)। दोनों हों तो Gemini पहले"), ("न हो", "कुछ नहीं बदलता")],
    "CLOUDFLARE_ACCOUNT_ID": [("token के साथ डाली हो", "AI तस्वीरें Cloudflare Workers AI से (रोज़ की मुफ़्त सीमा के अंदर)"), ("न हो", "AI तस्वीरें मुफ़्त सार्वजनिक service से (धीमी, कभी-कभी fail)")],
    "CLOUDFLARE_API_TOKEN": [("Account ID के साथ डाली हो", "ऊपर जैसा — दोनों साथ चाहिए"), ("न हो", "ऊपर जैसा")],
    "FAL_KEY": [("डाली हो", "चार चीज़ें खुलती हैं: (1) तेज़ cloud transcript — अगर नीचे “Transcript कहाँ बने” fal.ai / Auto पर हो, (2) fal.ai की आवाज़ें voice list में — Chatterbox, Kokoro, “मेरी अपनी आवाज़”, "
                             "(3) AI से background music (Sound tab), (4) AI video clips। हर एक सिर्फ़ इस्तेमाल पर पैसा लेता है"),
                ("न हो", "ये चारों दिखते / चलते नहीं; बाकी सब पहले जैसा")],
    "ELEVENLABS_API_KEY": [("डाली हो", "ElevenLabs की आवाज़ें voice list में (महँगी, ~$0.20 / 1000 अक्षर)"), ("न हो", "वे आवाज़ें list में नहीं दिखतीं")],
    "PIXABAY_API_KEY": [("डाली हो", "“आवाज़ से visuals” और Library में stock video / photo खोज"), ("न हो", "stock खोज बंद; अपनी clips और AI तस्वीरें चलती हैं")],
    "JAMENDO_CLIENT_ID": [("डाली हो", "Library → music में Jamendo के गाने खोजकर जोड़ना"), ("न हो", "वह खोज बंद")],
    "FREESOUND_API_KEY": [("डाली हो", "sound effects की खोज (Freesound)"), ("न हो", "वह खोज बंद; starter sounds रहते हैं")],
    "TENOR_API_KEY": [("डाली हो", "GIF / sticker की खोज"), ("न हो", "वह खोज बंद")],
    "YT_API_KEY": [("डाली हो", "YouTube trends, दूसरे channels के आँकड़े, ideas"), ("न हो", "ये आँकड़े नहीं आते")],
    "YT_CLIENT_ID": [("secret के साथ डाली हो", "YouTube channel जोड़ना और वहाँ upload / schedule (auto-upload आपने बंद रखा है — हर upload आपकी मंज़ूरी से)"), ("न हो", "YouTube जोड़ने का बटन काम नहीं करता")],
    "YT_CLIENT_SECRET": [("client ID के साथ", "ऊपर जैसा — दोनों साथ चाहिए"), ("न हो", "ऊपर जैसा")],
    "META_APP_ID": [("secret के साथ डाली हो", "Instagram / Facebook page जोड़ना और post करना"), ("न हो", "वे जुड़ते नहीं")],
    "META_APP_SECRET": [("app ID के साथ", "ऊपर जैसा"), ("न हो", "ऊपर जैसा")],
    "TIKTOK_CLIENT_KEY": [("secret के साथ डाली हो", "TikTok जोड़ना"), ("न हो", "नहीं जुड़ता")],
    "TIKTOK_CLIENT_SECRET": [("client key के साथ", "ऊपर जैसा"), ("न हो", "ऊपर जैसा")],
    "TRANSCRIBE_ENGINE": [("यह server (Z440)", "transcript यहीं Whisper से — मुफ़्त, पर CPU पर धीमा (लंबी recording में कई मिनट)"),
                          ("fal.ai Whisper", "हर transcript fal.ai पर — तेज़, ~$0.006 / मिनट (अंदाज़ा)। FAL_KEY चाहिए; fal fail हो तो यहीं बनता है"),
                          ("RunPod serverless", "आपके अपने RunPod Whisper endpoint पर। RunPod key + endpoint ID चाहिए; fail हो तो यहीं बनता है"),
                          ("Auto", "छोटी recording यहीं (मुफ़्त), “Auto: कितने मिनट” से लंबी cloud पर। रोज़ के काम के लिए सबसे अच्छा"),
                          ("SRT दी हो", "यह switch लागू ही नहीं होता — transcript फ़ाइल से बनता है, कोई खर्च नहीं")],
    "TRANSCRIBE_AUTO_MIN": [("जैसे 8", "8 मिनट तक की recording यहीं, उससे लंबी cloud पर (सिर्फ़ Auto में)"), ("खाली", "8 मिनट माना जाता है")],
    "SPEND_CAP_USD": [("जैसे 5", "महीने में $5 का अंदाज़न खर्च होते ही सारे paid काम रुक जाते हैं (cloud transcript, fal / RunPod / ElevenLabs की आवाज़ें, AI music, AI video)। मुफ़्त काम चलते रहते हैं"),
                      ("0", "सारे paid काम बंद"), ("खाली", "कोई सीमा नहीं — सलाह नहीं")],
    "RUNPOD_API_KEY": [("डाली हो", "RunPod की आवाज़ें voice list में (MiniMax HD, Chatterbox Turbo), AI video के लिए RunPod चुन सकते हैं, और अपना Whisper endpoint इस्तेमाल हो सकता है"),
                       ("न हो", "RunPod की कोई चीज़ नहीं दिखती / चलती")],
    "AI_VIDEO_PROVIDER": [("Auto", "fal.ai की key हो तो fal.ai, नहीं तो RunPod"), ("fal.ai", "AI तस्वीर बनती है, फिर fal.ai उसे हिलाकर clip बनाता है"),
                          ("RunPod p-video", "बात के वर्णन से सीधा clip (~$0.02 / सेकंड, 720p)। चुनी हुई service की key न हो तो AI video बंद रहता है — चुपचाप दूसरी पर नहीं जाता")],
    "SILENCE_ENGINE": [("आवाज़ की ऊँचाई से", "पहले जैसा: जो हिस्सा धीमा है वह चुप्पी। शांत कमरे में ठीक; पंखे / traffic / music में चुप्पी छूट जाती है"),
                       ("Silero", "इंसानी आवाज़ पहचानकर: शोर में भी चुप्पी कटती है, धीमे शब्द नहीं कटते। नई upload और “transcript दोबारा बनाएँ” पर लागू। model न चले तो अपने-आप पहले वाला तरीका")],
    "WORD_ALIGN": [("बंद", "शब्दों का समय Whisper का अपना (कभी-कभी 0.1–0.3 s आगे-पीछे)"),
                   ("WhisperX", "हर शब्द आवाज़ से दोबारा मिलाया जाता है — karaoke captions और text से कट ज़्यादा सटीक। तभी चलता है जब server WITH_WHISPERX=1 से बना हो (docs/whisperx.md); नहीं तो कुछ नहीं बदलता")],
    "CLIP_MATCH": [("बंद", "supporting clips: आपका लिखा समय → Gemini → बोले गए शब्द → नाम का क्रम"),
                   ("चालू", "शब्दों के बाद एक कदम और: इसी server पर clip को देखकर सबसे मिलती line पर लगाना (बाहर कुछ नहीं जाता)। तभी चलता है जब server WITH_OPENCLIP=1 से बना हो (docs/openclip.md)")],
    "RUNPOD_WHISPER_ENDPOINT": [("भरा हो", "“Transcript कहाँ बने” में RunPod चुनने पर यही endpoint इस्तेमाल होता है (RunPod → Serverless → Faster Whisper, Min workers = 0)"), ("खाली", "RunPod transcript नहीं चल सकता")],
}

# job → where it can run. `need` = key, `switch` = what to set, `cost` = estimate
TASKS: list[dict] = [
    {"task": "Transcript (बोली हुई बात → शब्द)", "options": [
        {"where": "यह server (Whisper)", "need": "—", "switch": "Transcript कहाँ बने = यह server", "cost": "मुफ़्त"},
        {"where": "fal.ai Whisper", "need": "fal.ai key", "switch": "Transcript कहाँ बने = fal.ai या Auto", "cost": "~$0.006 / मिनट"},
        {"where": "RunPod (अपना endpoint)", "need": "RunPod key + Whisper endpoint ID", "switch": "Transcript कहाँ बने = RunPod", "cost": "GPU के सेकंड (~$0.0004 / s)"},
        {"where": "SRT / VTT फ़ाइल", "need": "—", "switch": "upload पर “मेरे पास SRT है”, या Captions tab → SRT से transcript", "cost": "मुफ़्त"}]},
    {"task": "AI voice-over (text → आवाज़)", "options": [
        {"where": "यह server (Kokoro / Parler / VoiceStudio)", "need": "—", "switch": "voice list में चुनें", "cost": "मुफ़्त (धीमा)"},
        {"where": "fal.ai — Chatterbox हिन्दी, Kokoro, “मेरी अपनी आवाज़”", "need": "fal.ai key", "switch": "voice list में “(fal.ai)” वाली आवाज़", "cost": "~$0.02–0.025 / 1000 अक्षर"},
        {"where": "RunPod — MiniMax HD, Chatterbox Turbo (English)", "need": "RunPod key", "switch": "voice list में “(RunPod)” वाली आवाज़", "cost": "$0.05 / 1000 अक्षर · $0.001 / audio सेकंड"},
        {"where": "ElevenLabs", "need": "ElevenLabs key", "switch": "voice list में ElevenLabs वाली आवाज़", "cost": "~$0.20 / 1000 अक्षर"}]},
    {"task": "Background music", "options": [
        {"where": "Library / Jamendo", "need": "Jamendo client id (खोज के लिए)", "switch": "Sound tab → music", "cost": "मुफ़्त"},
        {"where": "AI से नया music (fal.ai)", "need": "fal.ai key", "switch": "Sound tab → “AI से नया music बनाओ”", "cost": "~$0.02 / मिनट"}]},
    {"task": "AI video clip", "options": [
        {"where": "fal.ai (तस्वीर को हिलाना)", "need": "fal.ai key", "switch": "AI video clips कहाँ बनें = Auto / fal.ai", "cost": "~$0.03 / सेकंड (अंदाज़ा)"},
        {"where": "RunPod p-video", "need": "RunPod key", "switch": "AI video clips कहाँ बनें = RunPod", "cost": "$0.02 / सेकंड (720p)"}]},
    {"task": "AI तस्वीर", "options": [
        {"where": "Cloudflare Workers AI", "need": "Cloudflare Account ID + token", "switch": "—", "cost": "रोज़ की मुफ़्त सीमा"},
        {"where": "मुफ़्त सार्वजनिक service", "need": "—", "switch": "—", "cost": "मुफ़्त (धीमी)"}]},
    {"task": "लिखना / सोचना (title, description, script, clips को देखना)", "options": [
        {"where": "Google Gemini", "need": "Gemini key", "switch": "—", "cost": "मुफ़्त सीमा के अंदर"},
        {"where": "Claude", "need": "Anthropic key", "switch": "Gemini न हो तब", "cost": "paid"},
        {"where": "बिना AI", "need": "—", "switch": "—", "cost": "मुफ़्त (सादे नियम)"}]},
    {"task": "चुप्पी / filler काटना (auto-cut)", "options": [
        {"where": "यह server — आवाज़ की ऊँचाई", "need": "—", "switch": "चुप्पी कैसे पहचानें = आवाज़ की ऊँचाई से", "cost": "मुफ़्त"},
        {"where": "यह server — Silero", "need": "—", "switch": "चुप्पी कैसे पहचानें = Silero", "cost": "मुफ़्त"}]},
    {"task": "Supporting clips को सही जगह लगाना", "options": [
        {"where": "Gemini (clip खोलकर देखता है)", "need": "Gemini key", "switch": "—", "cost": "मुफ़्त सीमा के अंदर"},
        {"where": "यह server — OpenCLIP", "need": "server WITH_OPENCLIP=1 से बना हो", "switch": "Clips को तस्वीर देखकर मिलाना = चालू", "cost": "मुफ़्त"},
        {"where": "सिर्फ़ शब्द / नाम", "need": "—", "switch": "—", "cost": "मुफ़्त"}]},
    {"task": "Podcast: बोलने वाले पर कैमरा, render, captions, effects", "options": [
        {"where": "यह server", "need": "—", "switch": "—", "cost": "मुफ़्त"}]},
]

# set on the server (file .env), not in the dashboard — they change what is installed or which machine does heavy work
SERVER_SWITCHES: list[tuple[str, str, str]] = [
    ("TRANSCRIBE_LOCAL=1", "यह server खुद transcript बना सकता है (default चालू)", "0 करने पर transcript सिर्फ़ cloud या GPU worker से बनेगा"),
    ("TTS_LOCAL=1", "यह server खुद AI आवाज़ (Kokoro / Parler) बना सकता है — CPU पर धीमा", "खाली हो तो local आवाज़ें GPU worker का इंतज़ार करती हैं; cloud आवाज़ें (fal / RunPod / ElevenLabs) फिर भी चलती हैं"),
    ("WITH_WHISPERX=1", "image में WhisperX install होता है (+2 GB) — तभी “शब्दों का सटीक समय” काम करता है", "docs/whisperx.md; गड़बड़ी पर यह line हटाकर दोबारा build"),
    ("WITH_OPENCLIP=1", "image में OpenCLIP install होता है (+2 GB, model +1.5 GB) — तभी “Clips को तस्वीर देखकर मिलाना” काम करता है", "docs/openclip.md"),
    ("PRICE_…", "खर्च के अंदाज़े की दरें (जैसे PRICE_FAL_WHISPER_MIN=0.004)", "असली bill से मिलाकर ठीक करें; नाम 💰 खर्च tab में लिखे हैं"),
]

CHECKLIST: list[str] = [
    "PUBLIC_URL भरें → Settings की चेतावनी हटनी चाहिए।",
    "खर्च-सीमा $5 रखें (पहले यही — फिर कोई key डालें)।",
    "Gemini key डालें → किसी project में AI title बनवाकर देखें।",
    "fal.ai key डालें → voice list में “(fal.ai)” आवाज़ें दिखें; एक line की voice-over बनाएँ; 💰 खर्च में entry आए।",
    "“Transcript कहाँ बने” = Auto → 1 छोटी और 1 लंबी (8 मिनट से ऊपर) recording upload करें; लंबी वाली का खर्च दिखे।",
    "SRT के साथ एक वीडियो upload करें → कोई transcribe काम न बने, captions तुरंत आएँ।",
    "Sound tab → “AI से नया music” 20 सेकंड का बनाएँ।",
    "Silero चालू करें → शोर वाली recording upload करें → Cuts tab देखें; पसंद न आए तो वापस।",
    "RunPod key (ज़रूरत हो तब) → “(RunPod)” आवाज़ से एक हिन्दी line सुनें।",
    "WhisperX / OpenCLIP सबसे आख़िर में, एक-एक करके (docs/whisperx.md, docs/openclip.md)।",
]


def data() -> dict:
    from . import provkeys
    rows = [{"env": c["env"], "label": c["label"], "group": provkeys.GROUPS[c["group"]], "kind": "switch" if c.get("choices") else "number" if c.get("number") else "key",
             "states": [{"state": s, "effect": e} for s, e in HELP.get(c["env"], [])]} for c in provkeys.CATALOG]
    return {"tasks": TASKS, "rows": rows, "server": [{"name": n, "does": d, "note": x} for n, d, x in SERVER_SWITCHES], "checklist": CHECKLIST}


def markdown() -> str:
    d = data()
    out = ["# Vividora — Admin guide: keys, switches, where each job runs", "",
           "यह फ़ाइल `server/vividora/adminguide.py` से बनती है (dashboard → Settings → API & Keys → 📖 Guide में यही दिखता है)।",
           "दाम अंदाज़े हैं; असली bill हर service की अपनी site पर देखें। कोई भी cloud service तभी पैसा लेती है जब कोई काम उसे बुलाए।", "",
           "## 1. कौन सा काम कहाँ चलता है", ""]
    for t in d["tasks"]:
        out += [f"### {t['task']}", "", "| कहाँ | क्या चाहिए | कौन सा switch / कहाँ चुनें | दाम |", "|---|---|---|---|"]
        out += [f"| {o['where']} | {o['need']} | {o['switch']} | {o['cost']} |" for o in t["options"]] + [""]
    out += ["## 2. हर key और switch — क्या करने से क्या होगा", ""]
    grp = None
    for r in d["rows"]:
        if r["group"] != grp:
            grp = r["group"]
            out += [f"### {grp}", ""]
        kind = {"switch": "switch", "number": "संख्या", "key": "key"}[r["kind"]]
        out += [f"**{r['label']}** — {kind} · `{r['env']}`", ""] + [f"- **{s['state']}:** {s['effect']}" for s in r["states"]] + [""]
    out += ["## 3. Server की फ़ाइल `.env` वाले switch (dashboard में नहीं)", "",
            "बदलने के बाद: `cd /srv/studio/vividora && docker compose --profile tunnel up -d --build`", "", "| line | क्या करता है | ध्यान दें |", "|---|---|---|"]
    out += [f"| `{s['name']}` | {s['does']} | {s['note']} |" for s in d["server"]]
    out += ["", "## 4. पहली बार जाँचने का क्रम", ""] + [f"{i}. {c}" for i, c in enumerate(d["checklist"], 1)] + [""]
    return "\n".join(out)


if __name__ == "__main__":
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "docs" / "admin-guide.md"
    p.write_text(markdown(), encoding="utf-8")
    print("wrote", p)
