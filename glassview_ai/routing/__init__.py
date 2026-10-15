"""Model routing: send easy prompts to a fast model and escalate hard or
image-bearing prompts to the strong vision model, to keep latency low without
giving up quality where it matters."""

from .router import RoutePolicy, RouteResult, route

__all__ = ["RoutePolicy", "RouteResult", "route"]
