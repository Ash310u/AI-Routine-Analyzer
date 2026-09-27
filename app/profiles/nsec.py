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
- Each separately labeled section/year timetable belongs in its own object
  inside routines[]. Read its visible heading for section and other metadata,
  and keep every day and slot with that object. A single table still produces
  routines[] with one object. Never merge different sections into one routine.
"""

    @staticmethod
    def adapt(raw: NsecRawExtraction) -> RoutineExtraction:
        return RoutineExtraction.model_validate(raw.model_dump())
