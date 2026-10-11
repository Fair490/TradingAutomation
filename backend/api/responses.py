"""
JSON response class that can never emit NaN or Infinity.

Python happily serialises float('nan') as the bare token `NaN`, which is not
valid JSON - the browser's JSON.parse() then throws and the whole panel fails
to load. Any non-finite float becomes null instead.
"""

from __future__ import annotations

import json
import math
from typing import Any

from fastapi.responses import JSONResponse


def sanitise(value: Any) -> Any:
    """Recursively replace NaN / Infinity with None."""
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {k: sanitise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitise(v) for v in value]
    return value


class SafeJSONResponse(JSONResponse):
    """JSONResponse with non-finite floats stripped out."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            sanitise(content),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
