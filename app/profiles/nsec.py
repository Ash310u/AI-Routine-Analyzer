"""NSEC PDF/image profile."""

from app.llm.prompts import EXTRACTION_PROMPT
from app.schemas.canonical_raw import RoutineExtraction


class NsecRawExtraction(RoutineExtraction):
    """Validated NSEC extraction output, before the canonical adapter."""


class NSECProfile:
    name = "nsec"
    raw_schema = NsecRawExtraction
    prompt = EXTRACTION_PROMPT + """

NSEC format rules:
- AI-ML and AIML are visible subject or department text, never faculty names.
- AIML_SC, AIML_SV, AI-ML_SD and similar identifiers belong in faculty_raw.
- A merged cell covering multiple period headers is one slot spanning those periods.
- Keep handwritten timetable changes that clearly replace printed entries.
- If the document contains multiple independent section/year routine tables,
  return a JSON array with one complete routine object per table. For one table,
  return one routine object. Never merge different sections into one routine.
"""

    @staticmethod
    def adapt(raw: NsecRawExtraction) -> RoutineExtraction:
        return RoutineExtraction.model_validate(raw.model_dump())
