"""The two input profiles share one downstream shape and deterministic matching."""

import asyncio
import json
import unittest
from types import SimpleNamespace

from app.config import Settings
from app.clients.master_api import MasterAPI
from app.llm.extractor import RoutineExtractor
from app.profiles.nsec import NSECProfile
from app.resolvers import resolve
from app.schemas.canonical_raw import RoutineExtraction
from app.schemas.context import FacultyRecord, GroupRecord, RoutineContext, SectionRecord, SubjectRecord
from app.services.routine_processor import _enrich


class FakeModel:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=json.dumps(self.payload))


class ProfilesAndResolutionTest(unittest.TestCase):
    def test_nsec_model_output_crosses_canonical_boundary(self):
        model = FakeModel({
            "department": "AIML", "section": "AIML.4",
            "slots": [{"day": "Monday", "start_period": 4, "end_period": 5,
                       "start_time": "11:50", "end_time": "13:30", "slot_type": "class",
                       "activities": [{"subject_raw": "AI-ML", "faculty_raw": ["AIML_SC"]}]},
                      ],
        })
        raw = asyncio.run(RoutineExtractor(Settings(), NSECProfile(), model).extract(["data:image/png;base64,AA=="]))
        self.assertIs(type(raw), RoutineExtraction)
        self.assertEqual(raw.slots[0].end_period, 5)
        self.assertEqual(raw.slots[0].activities[0].faculty_raw, ["AIML_SC"])
        self.assertIn("NSEC format rules", model.messages[0]["content"][0]["text"])

    def test_alias_initials_and_department_scope_are_deterministic(self):
        context = RoutineContext(subjects=[], groups=[], sections=[], department="AIML", faculty=[
            FacultyRecord(id=1, name="Somnath Chatterjee", department="AIML", aliases=["AIML_SC"]),
            FacultyRecord(id=2, name="Sujit Chatterjee", department="CSE"),
        ])
        self.assertEqual(resolve.faculty(["AIML_SC", "SC"], context)[0].faculty_id, 1)
        self.assertEqual(resolve.faculty(["SC"], context)[0].faculty_id, 1)
        context.faculty.append(FacultyRecord(id=3, name="Sagar Chatterjee", department="AIML"))
        self.assertIsNone(resolve.faculty(["SC"], context)[0].faculty_id)

    def test_code_beats_subject_text_and_group_is_section_scoped(self):
        context = RoutineContext(
            subjects=[SubjectRecord(id=8, code="PCC-CS392", name="Hardware Laboratory"),
                      SubjectRecord(id=9, code="ESC-391", name="Analog and Digital Lab")],
            faculty=[], sections=[SectionRecord(id=4, name="1"), SectionRecord(id=5, name="2")],
            groups=[GroupRecord(id=91, name="Group A", section_id=4),
                    GroupRecord(id=92, name="Group A", section_id=5)],
            section="1",
        )
        self.assertEqual(resolve.subject("H/W Lab", "PCC-CS392", context).subject_master_id, 8)
        self.assertEqual(resolve.group("Gr-A", context).group_id, 91)
        routine = RoutineExtraction.model_validate({"section": "2", "slots": [{
            "day": "Monday", "start_time": "10:00", "end_time": "11:00", "slot_type": "class",
            "activities": [{"group_raw": "Gr-A", "subject_code_raw": "ESC-391"}],
        }]})
        caches = ({}, {}, {})
        result = _enrich(routine, context, caches)
        self.assertEqual(result.slots[0].activities[0].group.group_id, 92)
        first_section = routine.model_copy(update={"section": "1"})
        self.assertEqual(_enrich(first_section, context, caches).slots[0].activities[0].group.group_id, 91)

    def test_nsec_does_not_reuse_tint_master_urls(self):
        settings = Settings(subject_api_url="https://example.test/tint/subjects",
                            faculty_api_url="https://example.test/tint/faculty")
        client = MasterAPI(settings)
        try:
            context = asyncio.run(client.load(RoutineExtraction.model_validate({
                "department": "AIML", "slots": [{"activities": []}],
            }), profile="nsec"))
            self.assertEqual(context.subjects, [])
            self.assertEqual(context.faculty, [])
        finally:
            asyncio.run(client.aclose())

    def test_overlapping_group_activity_requires_review(self):
        routine = RoutineExtraction.model_validate({"section": "1", "slots": [
            {"day": "Monday", "start_time": "10:00", "end_time": "11:00", "slot_type": "class",
             "activities": [{"group_raw": "Gr-A", "subject_raw": "DSA"}]},
            {"day": "Monday", "start_time": "10:30", "end_time": "11:30", "slot_type": "class",
             "activities": [{"group_raw": "Gr-A", "subject_raw": "Math"}]},
        ]})
        context = RoutineContext(subjects=[], faculty=[],
                                 groups=[GroupRecord(id=91, name="Group A")], sections=[])
        result = _enrich(routine, context, ({}, {}, {}))
        self.assertTrue(all(slot.activities[0].requires_review for slot in result.slots))
        self.assertTrue(all(any("Overlapping activity" in reason for reason in slot.activities[0].review_reasons)
                            for slot in result.slots))


if __name__ == "__main__":
    unittest.main()
