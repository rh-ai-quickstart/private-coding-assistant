"""TrustyAI detection outcome: parse, hits, and block text."""

from __future__ import annotations

from collections import namedtuple

DetectorHit = namedtuple(
    "DetectorHit",
    "detector_id detection_type detection text score direction",
)
# action: "" allowed, "block" empty choices, "warn" flagged with choices kept
GuardrailsOutcome = namedtuple("GuardrailsOutcome", "action hits")


def header(incoming, name):
    if incoming is None:
        return None
    getter = getattr(incoming, "get", None)
    if not callable(getter):
        return None
    value = getter(name) or getter(name.lower())
    if value:
        return str(value)
    return None


def parse_guardrails_outcome(body):
    """Parse TrustyAI chat-completions-detection JSON into a domain outcome."""
    if not isinstance(body, dict):
        return GuardrailsOutcome("", ())
    hits = []
    detections = body.get("detections") or {}
    if not isinstance(detections, dict):
        detections = {}
    for direction in ("input", "output"):
        for msg_det in detections.get(direction) or []:
            if not isinstance(msg_det, dict):
                continue
            for raw in msg_det.get("results") or []:
                if not isinstance(raw, dict):
                    continue
                hits.append(
                    DetectorHit(
                        detector_id=str(raw.get("detector_id") or "unknown"),
                        detection_type=str(raw.get("detection_type") or ""),
                        detection=str(raw.get("detection") or ""),
                        text=str(raw.get("text") or ""),
                        score=raw.get("score", 0) or 0,
                        direction=direction,
                    )
                )
    warnings = body.get("warnings") or []
    flagged = bool(hits) or bool(warnings)
    if not flagged:
        return GuardrailsOutcome("", tuple(hits))
    choices = body.get("choices") or []
    action = "block" if not choices else "warn"
    return GuardrailsOutcome(action, tuple(hits))


def hit_reason(hit):
    """One human-readable line for a detector hit (SSE block body and Langfuse)."""
    try:
        score = float(hit.score)
        conf = f"{score:.1%}"
    except (TypeError, ValueError):
        conf = str(hit.score)
    label = hit.detection or hit.detector_id
    if hit.detector_id == "prompt_injection":
        return f"Prompt injection detected (confidence: {conf})"
    if hit.detection_type == "pii":
        return f'PII detected: {label} — "{hit.text}"'
    return f'Credential/secret detected: {label} — "{hit.text}"'


def blocked_message(hits):
    reasons = [hit_reason(h) for h in hits]
    if not reasons:
        reasons = ["Unsuitable input detected."]
    return "**Guardrails blocked your message.**\n\n" + "\n".join(f"- {r}" for r in reasons)
