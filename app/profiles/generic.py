"""Fallback profile for workbooks outside the TINT block layout."""

from app.llm.prompts import EXTRACTION_PROMPT
from app.schemas.canonical_raw import RoutineExtraction


class GenericProfile:
    name = "generic"
    raw_schema = RoutineExtraction
    prompt = EXTRACTION_PROMPT

    @staticmethod
    def adapt(raw: RoutineExtraction) -> RoutineExtraction:
        return RoutineExtraction.model_validate(raw.model_dump())
