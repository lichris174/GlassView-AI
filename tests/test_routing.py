from __future__ import annotations

from glassview_ai.routing import RoutePolicy, route

POLICY = RoutePolicy(fast="fast-llm:1b", strong="qwen3-vl:8b")


def test_image_forces_strong() -> None:
    r = route("what is this", has_image=True, policy=POLICY)
    assert r.model == POLICY.strong and "vision" in r.reason


def test_short_simple_uses_fast() -> None:
    r = route("what time is it", has_image=False, policy=POLICY)
    assert r.model == POLICY.fast


def test_reasoning_cue_escalates() -> None:
    r = route("explain why this crashes", has_image=False, policy=POLICY)
    assert r.model == POLICY.strong and "cue" in r.reason


def test_long_prompt_escalates() -> None:
    r = route("a " * 200, has_image=False, policy=POLICY)
    assert r.model == POLICY.strong and r.reason == "long prompt"
