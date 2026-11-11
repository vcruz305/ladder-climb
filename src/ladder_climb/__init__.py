"""Atomic, agent-friendly ladder-climb tracking with a live local dashboard."""

from .schema import ValidationError, champion, load_board, validate_board
from .store import initialize, upsert_rung

__all__ = [
    "ValidationError",
    "champion",
    "initialize",
    "load_board",
    "upsert_rung",
    "validate_board",
]
__version__ = "0.2.0"
