"""Run the golden set through an answer function and report pass rate.

``run_eval`` takes an async ``answer_fn`` so the harness is testable with a fake
(no network). ``main`` wires the real Ollama client and exits non-zero when the
pass rate drops below the threshold, which is what CI gates on.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from .cases import DEFAULT_GOLDEN, EvalCase, load_cases
from .scorer import CaseResult, score_case

AnswerFn = Callable[[EvalCase], Awaitable[str]]


@dataclass(frozen=True)
class EvalReport:
    results: list[CaseResult]
    threshold: float

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 1.0

    @property
    def passed(self) -> bool:
        return self.pass_rate >= self.threshold

    def render(self) -> str:
        lines = [f"GlassView eval: {len(self.results)} cases", ""]
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            lines.append(f"[{mark}] {r.case_id}  ({r.score:.0%})")
            for c in r.checks:
                if not c.passed:
                    extra = f" - {c.detail}" if c.detail else ""
                    lines.append(f"        x {c.name}{extra}")
        gate = "PASS" if self.passed else "FAIL"
        lines += ["", f"pass rate {self.pass_rate:.0%} (threshold {self.threshold:.0%}) -> {gate}"]
        return "\n".join(lines)


async def run_eval(
    cases: list[EvalCase], answer_fn: AnswerFn, *, threshold: float = 1.0
) -> EvalReport:
    results: list[CaseResult] = []
    for case in cases:
        try:
            answer = await answer_fn(case)
        except Exception as exc:  # noqa: BLE001 - a failed call is a failed case
            answer = f"[error] {exc}"
        results.append(score_case(case, answer))
    return EvalReport(results=results, threshold=threshold)


def _load_image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def make_ollama_answer_fn(golden_dir: Path) -> AnswerFn:
    """Build an answer function backed by the live Ollama client."""
    from .. import config
    from ..ollama_client import OllamaClient, build_messages

    settings = config.load_settings(require_model=True)
    client = OllamaClient(settings.ollama_host, settings.model)

    async def answer(case: EvalCase) -> str:
        img_path = case.image_path(golden_dir)
        image = _load_image_b64(img_path) if img_path else None
        messages = build_messages(config.SYSTEM_PROMPT, [], case.question, image)
        return "".join([chunk async for chunk in client.stream_chat(messages)])

    return answer


async def _amain(golden_dir: Path, threshold: float) -> int:
    cases = load_cases(golden_dir)
    answer_fn = make_ollama_answer_fn(golden_dir)
    report = await run_eval(cases, answer_fn, threshold=threshold)
    print(report.render())
    return 0 if report.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the GlassView eval golden set.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--threshold", type=float, default=1.0)
    args = parser.parse_args(argv)
    return asyncio.run(_amain(args.golden, args.threshold))


if __name__ == "__main__":
    sys.exit(main())
