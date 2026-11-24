# Windows app (.exe) और Android app (.apk)

दोनों app आपकी Vividora site की “खिड़की” हैं: अंदर वही site खुलती है, login वहीं होता है, सारा काम server करता है।
इसलिए site update होते ही app भी नई हो जाती है — app दोबारा बनाने की ज़रूरत सिर्फ़ तब है जब site का पता बदले।

> ये दोनों build GitHub के computers पर बनते हैं। इन्हें लिखते समय चलाकर नहीं देखा जा सका — पहली बार चलाने पर कोई कदम लाल (failed) हो
> तो उसका नाम और आख़िरी 20 lines भेज दें।

## सबसे आसान: बिना कुछ बनाए (आज ही)

Vividora browser से ही app की तरह install होता है:

- **Windows / Mac (Chrome या Edge):** site खोलें → address bar के दाएँ कोने में ⊕ “Install” → अलग खिड़की और Desktop icon।
- **Android (Chrome):** menu ⋮ → “Add to Home screen” / “Install app”।
- **iPhone (Safari):** Share → “Add to Home Screen”।

## असली .exe और .apk बनाना

1. GitHub पर repo खोलें: https://github.com/prashantmahto2819-droid/vividora
2. ऊपर **Actions** tab → बाईं ओर **Apps** → दाईं ओर **Run workflow**।
3. “Your Vividora address” में `https://studio.vividbrandify.com` रहने दें → हरा **Run workflow** बटन।
4. 10–15 मिनट रुकें। Run पर click करें → नीचे **Artifacts** में दो फ़ाइलें: `Vividora-Windows` (अंदर `Vividora-Setup.exe`) और
   `Vividora-Android` (अंदर `Vividora.apk`)। दोनों download करके zip खोल लें।
5. Vividora → **Settings → API & Keys → 🔑 keys जोड़ें** → सबसे नीचे **📦 Windows / Android app की फ़ाइलें** → दोनों फ़ाइलें upload करें।
6. अब Home page (login से पहले) और “सीखें” page पर download के बटन दिखेंगे।

(Repo public हो तो फ़ाइलें release `apps-latest` में भी आती हैं; तब upload की जगह उनके link `APP_WINDOWS_URL` / `APP_ANDROID_URL` में भी डाल सकते हैं।)

## लोगों को install करते समय क्या दिखेगा

- **Windows:** फ़ाइल पर किसी company का digital signature नहीं है, इसलिए “Windows protected your PC” आ सकता है →
  **More info → Run anyway**। (Signature के लिए सालाना paid certificate लगता है — corporate model के समय।)
- **Android:** Play Store से नहीं है, इसलिए phone पूछेगा “unknown app install करने दें?” → अनुमति दें। पहली बार camera / mic की अनुमति भी माँगेगा।

## Android update की एक बात

बिना अपनी signing key के हर build अलग key से बनता है — नया APK पुराने के ऊपर install नहीं होगा (पहले पुराना हटाना पड़ेगा)।
इसे ठीक करने के लिए एक बार key बनाकर GitHub में रख दें:

1. किसी computer पर (Java हो): `keytool -genkeypair -v -keystore vividora.jks -alias vividora -keyalg RSA -keysize 2048 -validity 10000`
2. `base64 -w0 vividora.jks` का output copy करें।
3. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:
   `ANDROID_KEYSTORE_B64` = वह output, `ANDROID_KEYSTORE_PASSWORD` = key का password।
4. `vividora.jks` और password संभालकर रखें — खो गए तो पुराने users को app हटाकर दोबारा डालनी पड़ेगी।

## Files

- `apps/windows/` — Electron (main.js: सिर्फ़ आपकी site, camera / mic उसी को, बाहर के link browser में)।
- `apps/android/` — Capacitor (`capacitor.config.json` में site का पता)।
- `.github/workflows/apps.yml` — दोनों build।
- Server: `GET /api/app-links` (public), `PUT|DELETE /api/app-files/{windows|android}` (सिर्फ़ मालिक), `GET /api/app-files/{kind}` (public download)।
