"""Compatibility imports; downstream processing uses the canonical raw model."""

from app.schemas.canonical_raw import ActivityExtraction, RoutineCollectionExtraction, RoutineExtraction, SlotExtraction

__all__ = ["ActivityExtraction", "RoutineCollectionExtraction", "RoutineExtraction", "SlotExtraction"]
