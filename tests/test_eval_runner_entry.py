"""The eval CLI runs as ``python -m glassview_ai.evals.runner`` without warnings."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_runner_module_runs_without_runpy_warning() -> None:
    cmd = [sys.executable, "-W", "error::RuntimeWarning", "-m", "glassview_ai.evals.runner"]
    proc = subprocess.run(
        [*cmd, "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "RuntimeWarning" not in proc.stderr


def test_package_still_exports_the_runner_api() -> None:
    from glassview_ai.evals import EvalReport, run_eval

    assert callable(run_eval) and EvalReport.__name__ == "EvalReport"


def test_package_dir_lists_the_lazy_exports() -> None:
    import glassview_ai.evals as evals

    assert {"run_eval", "EvalReport"} <= set(dir(evals))
