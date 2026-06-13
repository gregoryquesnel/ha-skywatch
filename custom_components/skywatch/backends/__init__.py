"""Skywatch source-adapter backends.

Public exports: the abstract `Source` base and the FR24 implementation.
Future backends register themselves by adding a new module here.
"""

from __future__ import annotations

from .base import EntryListener, ExitListener, MovementListener, Source
from .fr24 import Fr24Source

__all__ = [
    "EntryListener",
    "ExitListener",
    "Fr24Source",
    "MovementListener",
    "Source",
]
