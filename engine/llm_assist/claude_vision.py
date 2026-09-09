"""Claude-vision implementation of `VisionAssistProvider`.

Sends the page/region image plus a strict JSON-schema instruction and
parses the model's structured response. If the API key isn't configured,
`is_available()` returns False and the pipeline/UI fall back to
deterministic-only mode with a clear message — never a silent failure.
"""

from __future__ import annotations

import base64
import json
import os
import re

from engine.llm_assist.provider import SuggestedEntity, VisionAssistProvider, VisionSuggestion

DEFAULT_MODEL = os.environ.get("ANTHROPIC_VISION_MODEL", "claude-sonnet-5")

_SYSTEM_PROMPT = """\
You are assisting a structural/civil engineering drawing digitization tool.
You will be shown a raster image of a (possibly old, faded, or noisy)
scanned engineering drawing, along with a summary of what a deterministic
computer-vision pass already detected, and optionally notes a human drew
directly on the drawing to flag errors or missing content.

Your job: identify structural drawing entities (lines, polylines, arcs,
circles, text/dimension labels, hatch boundaries) that the deterministic
pass likely missed, got wrong, or that the human's annotation is pointing
at. Do NOT re-list everything already confidently detected — focus on
gaps, corrections, and the annotated area.

Respond with ONLY a single JSON object, no prose, no markdown fences,
matching exactly this schema:

{
  "summary": "<one or two sentence overview of what you found/changed>",
  "entities": [
    {
      "type": "line|polyline|arc|circle|text|dimension|hatch",
      "points_norm": [[x, y], ...],
      "layer_hint": "S-GRID|S-COLS|S-BEAM|S-WALL|S-SLAB|S-FDTN|S-REBAR|S-DIMS|S-ANNO-TEXT|S-ANNO-TTLB|S-HATCH|S-UNCLASSIFIED",
      "text": "<only for text/dimension>",
      "radius_norm": <only for arc/circle, radius as a fraction of image width>,
      "start_angle_deg": <only for arc>,
      "end_angle_deg": <only for arc>,
      "confidence": <0..1, your own confidence in this specific suggestion>,
      "note": "<why you're suggesting this, e.g. 'wall continues behind text block'>"
    }
  ]
}

All coordinates in "points_norm" and "radius_norm" MUST be normalized to
the 0.0-1.0 range relative to the image's width/height (x: left=0,
right=1; y: top=0, bottom=1). If you find nothing to add or correct,
return an empty "entities" list rather than inventing content.
"""


class ClaudeVisionProvider(VisionAssistProvider):
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def suggest_entities(
        self,
        image_bytes: bytes,
        media_type: str,
        deterministic_summary: str,
        annotation_notes: list[str],
    ) -> VisionSuggestion:
        if not self.is_available():
            return VisionSuggestion(summary="Claude vision assist unavailable: no API key configured.")

        client = self._get_client()
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")

        user_text = f"Deterministic pass summary:\n{deterministic_summary}\n"
        if annotation_notes:
            user_text += "\nUser annotation notes on this region:\n"
            user_text += "\n".join(f"- {n}" for n in annotation_notes)

        response = client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )

        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return _parse_response(raw_text)


def _parse_response(raw_text: str) -> VisionSuggestion:
    cleaned = re.sub(r"^```(json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return VisionSuggestion(
            summary="Could not parse model response as JSON.", raw_response=raw_text
        )

    entities = []
    for item in data.get("entities", []):
        try:
            entities.append(
                SuggestedEntity(
                    type=item["type"],
                    points_norm=[tuple(p) for p in item.get("points_norm", [])],
                    layer_hint=item.get("layer_hint"),
                    text=item.get("text"),
                    radius_norm=item.get("radius_norm"),
                    start_angle_deg=item.get("start_angle_deg"),
                    end_angle_deg=item.get("end_angle_deg"),
                    self_reported_confidence=float(item.get("confidence", 0.5)),
                    note=item.get("note", ""),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue  # skip malformed suggestions rather than failing the whole batch

    return VisionSuggestion(
        entities=entities, summary=data.get("summary", ""), raw_response=raw_text
    )
