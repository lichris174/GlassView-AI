"""Heuristic model router.

A screenshot always needs the vision model. For text-only turns, short and
simple questions go to the fast model, while long prompts or ones with
reasoning cues ("why", "debug", "explain step by step") escalate to the strong
model. The policy carries the concrete model tags so callers can wire whatever
is installed; when only one model exists, fast and strong are the same tag and
routing is a no-op with a recorded reason.
"""

from __future__ import annotations

from dataclasses import dataclass

# Cues that a text prompt is doing real reasoning and deserves the strong model.
_HARD_HINTS = (
    "why", "explain", "debug", "trace", "prove", "derive", "step by step",
    "architecture", "optimize", "refactor", "root cause", "analyze",
)
_LONG_PROMPT_CHARS = 280


@dataclass(frozen=True)
class RoutePolicy:
    fast: str
    strong: str


@dataclass(frozen=True)
class RouteResult:
    model: str
    reason: str


def route(text: str, *, has_image: bool, policy: RoutePolicy) -> RouteResult:
    if has_image:
        return RouteResult(policy.strong, "image input requires the vision model")
    lowered = (text or "").lower()
    if len(lowered) > _LONG_PROMPT_CHARS:
        return RouteResult(policy.strong, "long prompt")
    hint = next((h for h in _HARD_HINTS if h in lowered), None)
    if hint:
        return RouteResult(policy.strong, f"reasoning cue '{hint}'")
    return RouteResult(policy.fast, "short simple prompt")
