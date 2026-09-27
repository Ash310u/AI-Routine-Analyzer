"""Parse a literal PDF/image transcription from Excel into canonical routines."""

from app.llm.prompts import EXTRACTION_PROMPT
from app.schemas.canonical_raw import RoutineExtraction


class ConvertedWorkbookProfile:
    name = "converted_workbook"
    raw_schema = RoutineExtraction
    prompt = EXTRACTION_PROMPT + """

Converted workbook rules:
- The workbook is a literal transcription of visible PDF/image cells. Its
  generated sheet names (Table 1, Table 2, ...) are not source data.
- Read only cell values and their row, column, and merged-span relationships.
  Never supply a value solely because a timetable normally has that field.
- Set each missing course, department, year, semester, section, room, period,
  time, subject, faculty, and group field to null (or [] for faculty_raw).
- Preserve raw subject and faculty strings, including prefixes and numbers.
  Never invent a teacher name, employee ID, subject name, or subject master ID.
- Keep every independently visible timetable in its own routines[] entry.
"""

    @staticmethod
    def adapt(raw: RoutineExtraction) -> RoutineExtraction:
        return RoutineExtraction.model_validate(raw.model_dump())
