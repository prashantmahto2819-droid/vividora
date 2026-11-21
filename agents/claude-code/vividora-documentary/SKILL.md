---
name: vividora-documentary
description: Produce a narrated documentary (and Shorts, and a private YouTube draft) by driving the Vividora studio through its MCP tools. Use when the user wants a video made from a topic or script.
---

# Vividora documentary pipeline (agent skill)

Needs the Vividora MCP server (`server/tools/vividora_mcp.py`, see docs/mcp.md): tools `vividora_documentary_plan`,
`vividora_documentary_build`, `vividora_documentary_shorts`, `vividora_documentary_series`, `vividora_job_status`, `vividora_download_file`.
Stages mirror a normal agentic video pipeline (research → proposal → script → scenes → assets → compose → review). **Ask the user to approve at the marked gates.**

1. **Proposal (gate).** Restate the topic, length (minutes), language (hi/en/hinglish), shape (landscape / portrait), and whether AI pictures (`ai_images`) or paid AI video (`ai_video`, per-scene `motion: true`) are allowed. Say that AI video costs money per clip; default to none.
2. **Scenes.** `vividora_documentary_plan {topic, minutes, language}` — facts are grounded in Wikipedia and returned in `sources`. If the user has their own script pass `{script}` instead. Show the scenes (narration, visual keywords, on_screen) and let the user edit them. **(gate)** Never invent numbers, dates or names that are not in the sources or the user's script.
3. **Build.** `vividora_documentary_build {scenes, title, voice, orientation, music_id?, ai_images, wait:true}`. It takes minutes; report progress from `vividora_job_status` if `wait:false`. Use Kokoro/Parler voices for public videos (Voice Studio is personal-use only).
4. **Review (gate).** Download with `vividora_download_file` if the user wants to watch it. Check the description (chapters, sources, credits) and the thumbnail in the Library.
5. **Shorts (optional).** `vividora_documentary_shorts {scenes, count:3}` returns candidate runs; confirm which, then call again with `build:true, pick:[…]`.
6. **Series (optional).** `vividora_documentary_series {topic, episodes:4}` for an outline, let the user rename episodes, then `build:true, episodes:[…]`.
7. **Publish.** Uploading to YouTube is a human step: in the Vividora Auto Documentary page the user presses "Private draft" (always private) and publishes from YouTube Studio. Do not try to publish publicly, and do not turn on auto-upload.

Rules: pictures are Library → AI image → Pixabay → title card; keep `credits` and the "synthetic" disclosure intact; one job at a time per workspace.
