# Vividora MCP server — Claude से सीधे Vividora चलाएँ

Claude (Claude Code / Claude Desktop) इससे आपके Vividora में **voice बना सकता है, image से 3D, 3D character video, Auto SFX** — सब आपकी API key से।
फ़ाइल: `server/tools/vividora_mcp.py` (सिर्फ़ Python 3.9+, कुछ install नहीं करना)।

## Tools
`vividora_whoami` · `vividora_list_voices` · `vividora_text_to_speech` · `vividora_image_to_3d` · `vividora_list_models3d` ·
`vividora_character_video` · `vividora_auto_sfx` · `vividora_job_status` · `vividora_download_file`

## Setup (आपके PC पर, जहाँ Claude चलता है)
1. Python 3 होना चाहिए (`python --version`)। नहीं तो https://www.python.org/downloads/
2. Vividora खोलें → **API & Integrations** → नई key बनाएँ (`vk_…`) — सिर्फ़ एक बार दिखती है, कॉपी कर लें।
3. `vividora_mcp.py` फ़ाइल अपने PC पर रखें (GitHub repo से: `server/tools/vividora_mcp.py`), जैसे `C:\tools\vividora_mcp.py`।
4. **Claude Code:** PowerShell में
   ```
   claude mcp add vividora --env VIVIDORA_URL=https://studio.vividbrandify.com --env VIVIDORA_API_KEY=vk_आपकी_key -- python C:\tools\vividora_mcp.py
   ```
5. **Claude Desktop:** Settings → Developer → Edit Config → `claude_desktop_config.json` में:
   ```json
   { "mcpServers": { "vividora": { "command": "python", "args": ["C:\\tools\\vividora_mcp.py"],
       "env": { "VIVIDORA_URL": "https://studio.vividbrandify.com", "VIVIDORA_API_KEY": "vk_आपकी_key" } } } }
   ```
   फिर Claude Desktop पूरा बंद करके दोबारा खोलें।
6. जाँच: Claude से कहें — *"vividora_whoami चलाओ"*। user और role दिखे तो जुड़ गया।

## इस्तेमाल के उदाहरण
- "इस script की हिंदी narration बनाओ और `D:\out\voice.wav` में सेव करो" → `vividora_text_to_speech`
- "chair.png से 3D model बनाओ" → `vividora_image_to_3d`
- "इस timeline पर Auto SFX की योजना बनाओ, density high" → `vividora_auto_sfx`

## सुरक्षा
- Key `viewer`/`editor` role तक सीमित रखें; admin key MCP में न डालें।
- Key लीक हो तो Dashboard से revoke करें। Config फ़ाइल किसी को न भेजें।
- Claude के हर tool call पर 120 requests/min की limit लागू है।
