"""TINT Department-block workbook profile."""

from app.config import Settings
from app.ingestion.spreadsheet_routines import extract_workbook_routines
from app.schemas.canonical_raw import RoutineExtraction


class TINTProfile:
    name = "tint"

    @staticmethod
    def extract(data: bytes, settings: Settings) -> list[RoutineExtraction]:
        return extract_workbook_routines(data, settings)

    @staticmethod
    def adapt(raw: RoutineExtraction) -> RoutineExtraction:
        return RoutineExtraction.model_validate(raw.model_dump())
