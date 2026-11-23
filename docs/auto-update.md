# Auto-update (अपने-आप update)

`scripts/auto-update.sh` GitHub से नया code लाकर server को सुरक्षित तरीके से update करता है।

- हर घंटे cron से चलता है, पर काम सिर्फ़ रात **2–5 बजे (भारत समय)** के बीच करता है।
- कोई render / job चल रहा हो या क़तार में हो → उस बार छोड़ देता है।
- server code बदला हो तभी containers दोबारा बनते हैं; सिर्फ़ web UI बदला हो तो restart नहीं होता।
- restart के बाद `/api/health` जवाब न दे → पिछले version पर वापस जाकर उसे चला देता है, और उस ख़राब version को दोबारा नहीं आज़माता।
- tracked files में हाथ से किए बदलाव कभी नहीं मिटाता (रुककर बता देता है)। `.env` सुरक्षित रहता है।

## चालू करना (sudo नहीं चाहिए)
```
crontab -e
```
सबसे नीचे यह line जोड़ें:
```
7 * * * * /srv/studio/vividora/scripts/auto-update.sh >> $HOME/vividora-update.log 2>&1
```

## हाथ से
```
scripts/auto-update.sh --check    # कोई update बाकी है?
scripts/auto-update.sh --now      # अभी update करो (render चल रहा हो तो नहीं करेगा)
tail -20 ~/vividora-update.log    # पिछली बार क्या हुआ
```
समय बदलना हो: cron line में `UPDATE_HOURS="1 2 3"` आगे लगाएँ (भारत समय के घंटे)।

नए effects, looks, themes और sounds तभी आते हैं जब वे repo में जोड़े जाएँ — यह script उन्हें server तक पहुँचाता है, खुद नहीं बनाता।
Starter pack की नई sounds / stickers server चालू होते ही हर workspace की Library में अपने-आप जुड़ जाती हैं।
