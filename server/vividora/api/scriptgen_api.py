"""AI Script Generator API — standalone script generation for dubBox.

POST /scriptgen/generate   → full script from topic
POST /scriptgen/improve    → rewrite/improve/shorten/expand existing script
GET  /scriptgen/options    → available styles, tones, formats
"""

from __future__ import annotations

from starlette.routing import Route

from .deps import ApiError, body, need, ok, require
from ..engine import scriptgen


@require("editor")
async def generate(request, *, user):
    data = await body(request)
    need(data, "topic")
    topic = str(data["topic"]).strip()
    if len(topic) < 3:
        raise ApiError(422, "topic बहुत छोटा है — कम से कम 3 अक्षर लिखें")

    result = scriptgen.generate(
        topic,
        style=str(data.get("style") or "motivational"),
        fmt=str(data.get("format") or "short"),
        language=str(data.get("language") or "hi"),
        target_seconds=int(data["seconds"]) if data.get("seconds") else None,
        audience=str(data.get("audience") or ""),
        tone=str(data.get("tone") or "conversational"),
    )
    return ok(result)


@require("editor")
async def improve(request, *, user):
    data = await body(request)
    need(data, "script")
    script = str(data["script"]).strip()
    if len(script) < 10:
        raise ApiError(422, "script बहुत छोटा है — कम से कम 10 अक्षर चाहिए")

    result = scriptgen.improve(
        script,
        mode=str(data.get("mode") or "improve"),
        language=str(data.get("language") or "hi"),
    )
    return ok(result)


@require("viewer")
async def options(request, *, user):
    """Return available styles, tones and formats for the UI dropdowns."""
    return ok({
        "styles": [
            {"id": k, "label": v["label"]}
            for k, v in scriptgen.STYLES.items()
        ],
        "tones": [
            {"id": k, "label": k.replace("_", " ").title()}
            for k in scriptgen.TONES
        ],
        "formats": [
            {"id": k, "label": v if isinstance(v, str) else k}
            for k, v in scriptgen.FORMATS.items()
        ],
    })


routes = [
    Route("/scriptgen/generate", generate, methods=["POST"]),
    Route("/scriptgen/improve", improve, methods=["POST"]),
    Route("/scriptgen/options", options, methods=["GET"]),
]
