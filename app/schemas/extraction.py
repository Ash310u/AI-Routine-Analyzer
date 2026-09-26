"""Compatibility imports; downstream processing uses the canonical raw model."""

from app.schemas.canonical_raw import ActivityExtraction, RoutineExtraction, SlotExtraction

__all__ = ["ActivityExtraction", "RoutineExtraction", "SlotExtraction"]
