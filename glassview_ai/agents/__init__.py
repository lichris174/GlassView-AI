"""Bounded tool-use agent loop.

The model is asked to either call a registered tool (by emitting a JSON object)
or return a final answer. The loop executes the requested tool, feeds the
observation back, and repeats up to a step budget. It is transport-agnostic: a
``complete`` callable produces model output, so tests run it with a scripted
fake and production wires the Ollama client.
"""

from .loop import AgentResult, AgentStep, run_agent
from .registry import Tool, ToolRegistry

__all__ = ["AgentResult", "AgentStep", "run_agent", "Tool", "ToolRegistry"]
