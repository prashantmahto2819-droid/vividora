"""Timeline markers / chapters (render settings `markers`). No effect on the picture.

marker = {"id": "m1", "t": 12.5, "label": "Intro", "kind": "chapter|note|todo", "color": "#F2B33D"}
t is on the OUTPUT timeline (after cuts), like titles / overlays.

Chapters for YouTube come from kind == "chapter" markers when there are any (engine/metadata.py);
YouTube's rules are enforced: first chapter at 00:00, ≥ 3 chapters, each ≥ 10 s long.
"""

from __future__ import annotations

KINDS = {"chapter": "Chapter (YouTube)", "note": "Note", "todo": "To-do"}


def clean(markers) -> list[dict]:
    out = []
    for i, m in enumerate(markers if isinstance(markers, list) else []):
        if not isinstance(m, dict):
            continue
        try:
            t = max(0.0, float(m.get("t", 0)))
        except (TypeError, ValueError):
            continue
        out.append({"id": str(m.get("id") or f"m{i + 1}"), "t": round(t, 3), "label": str(m.get("label") or "")[:100],
                    "kind": m.get("kind") if m.get("kind") in KINDS else "note", "color": str(m.get("color") or "#F2B33D")[:9]})
    return sorted(out, key=lambda m: m["t"])


def chapters(markers, out_duration: float | None = None, min_len: float = 10.0) -> list[tuple[float, str]]:
    ch = [m for m in clean(markers) if m["kind"] == "chapter" and (out_duration is None or m["t"] < out_duration - min_len)]
    if not ch:
        return []
    marks: list[tuple[float, str]] = []
    for m in ch:
        t = 0.0 if not marks and m["t"] < min_len else m["t"]
        label = m["label"] or f"Part {len(marks) + 1}"
        if not marks and t > 0:
            marks.append((0.0, "Intro"))
        if marks and t - marks[-1][0] < min_len:
            continue
        marks.append((t, label))
    return marks if len(marks) >= 3 else []
