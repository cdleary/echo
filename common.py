"""Commonly used utility functions."""

import dis
import types
from typing import Any, Text
from io import StringIO


def get_code(x: Any) -> types.CodeType:
    return x.__code__


def dis_to_str(x: Any) -> Text:
    out = StringIO()
    dis.dis(x, file=out)
    return out.getvalue()
