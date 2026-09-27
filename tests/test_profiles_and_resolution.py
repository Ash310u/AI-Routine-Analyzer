"""The two input profiles share one downstream shape and deterministic matching."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.config import Settings
from app.clients.master_api import MasterAPI, _faculty
from app.llm.extractor import RoutineExtractor
from app.ingestion.spreadsheet_routines import _activity
from app.profiles.nsec import NSECProfile
from app.resolvers import resolve
from app.schemas.canonical_raw import RoutineExtraction
from app.schemas.context import FacultyRecord, GroupRecord, RoutineContext, SectionRecord, SubjectRecord
from app.services.routine_processor import _enrich
from app.services.routine_processor import process_routine


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

    def test_nsec_multi_table_pdf_returns_document_collection(self):
        payload = [
            {"department": "AIML", "section": section,
             "slots": [{"day": "Monday", "start_time": "10:00", "end_time": "11:00",
                        "slot_type": "class", "activities": [{"subject_raw": "DSA"}]}]}
            for section in ("AIML.1", "AIML.2")
        ]
        model = FakeModel(payload)
        extracted = asyncio.run(RoutineExtractor(Settings(), NSECProfile(), model).extract(["data:image/png;base64,AA=="]))
        self.assertEqual(len(extracted), 2)

        class FakeMaster:
            async def load(self, routine, college_id):
                self.college_id = college_id
                return RoutineContext(subjects=[], faculty=[], groups=[], sections=[], college_id=college_id)

        master = FakeMaster()
        with patch("app.services.routine_processor.image_data_urls", return_value=["data:image/png;base64,AA=="]), patch(
            "app.services.routine_processor.RoutineExtractor.extract", return_value=extracted,
        ):
            result = asyncio.run(process_routine(b"pdf", Settings(), master, 1))
        self.assertEqual(master.college_id, 1)
        self.assertEqual(result.source_type, "document")
        self.assertEqual(result.college_id, 1)
        self.assertEqual(result.routine_count, 2)
        self.assertEqual([item.section.raw for item in result.routines], ["AIML.1", "AIML.2"])

    def test_alias_initials_and_department_scope_are_deterministic(self):
        context = RoutineContext(subjects=[], groups=[], sections=[], department="AIML", faculty=[
            FacultyRecord(id=1, name="Somnath Chatterjee", department="AIML", aliases=["AIML_SC"]),
            FacultyRecord(id=2, name="Sujit Chatterjee", department="CSE"),
        ])
        self.assertEqual(resolve.faculty(["AIML_SC", "SC"], context)[0].faculty_id, 1)
        self.assertEqual(resolve.faculty(["SC"], context)[0].faculty_id, 1)
        self.assertEqual(context.faculty[0].initial, "SC")
        context.department = "ECE"
        self.assertIsNone(resolve.faculty(["SC"], context)[0].faculty_id)
        context.department = "AIML"
        context.faculty.append(FacultyRecord(id=3, name="Sagar Chatterjee", department="AIML"))
        self.assertIsNone(resolve.faculty(["SC"], context)[0].faculty_id)

    def test_employee_stream_sets_faculty_scope(self):
        faculty = _faculty([{
            "EmployeeId": 7, "EmployeeName": "Somnath Chatterjee",
            "Department": "Academics", "Stream": "AIML",
        }])
        self.assertEqual(faculty[0].department, "AIML")
        self.assertEqual(faculty[0].category, "Academics")
        admin = _faculty([{"EmployeeId": 8, "EmployeeName": "Somnath Chatterjee",
                           "Department": "Admin", "Stream": None}])
        context = RoutineContext(subjects=[], faculty=admin, groups=[], sections=[], department="AIML")
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

    def test_duplicate_code_is_scoped_to_stream_and_semester(self):
        context = RoutineContext(subjects=[
            SubjectRecord(id=726, code="PCCCS301", name="DSA", stream="AIML", semester="3rd"),
            SubjectRecord(id=927, code="PCCCS301", name="DSA", stream="CSE", semester="3rd"),
        ], faculty=[], groups=[], sections=[], department="CSE", semester="3rd")
        self.assertEqual(resolve.subject("PCC-CS301", "PCC-CS301", context).subject_master_id, 927)
        context.department = "Dept of CSE"
        context.semester = "3rd Semester"
        self.assertEqual(resolve.subject("PCC-CS301", "PCC-CS301", context).subject_master_id, 927)

    def test_master_cache_is_scoped_by_college_id(self):
        settings = Settings(subject_api_base_url="https://example.test/subjects",
                            faculty_api_base_url="https://example.test/employees?department_id=2&college_id=99")
        calls = []

        def respond(request):
            calls.append(str(request.url))
            self.assertNotIn("department_id", str(request.url))
            college_id = int(request.url.params["college_id"])
            if request.url.path == "/subjects":
                return httpx.Response(200, json=[{"SubjectMasterId": college_id, "Name": "Math"}])
            return httpx.Response(200, json=[{"EmployeeId": college_id,
                                               "EmployeeName": "Somnath Chatterjee",
                                               "Department": "Academics", "Stream": "CSE"}])

        client = MasterAPI(settings)
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        routine = RoutineExtraction.model_validate({"department": "CSE", "slots": [{"activities": []}]})

        async def check():
            try:
                first = await client.load(routine, 1)
                second = await client.load(routine, 2)
                again = await client.load(routine, 1)
                self.assertEqual([first.subjects[0].id, second.subjects[0].id, again.subjects[0].id], [1, 2, 1])
                self.assertEqual(first.faculty[0].initial, "SC")
                self.assertEqual(len(calls), 4)
            finally:
                await client.aclose()

        asyncio.run(check())

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

    def test_tint_lab_venue_is_not_faculty(self):
        activity = _activity("PCC-CS392 (TD+SC) Gr-B (H/W Lab)", "2nd year", 4, 7)
        self.assertEqual(activity.subject_raw, "PCC-CS392")
        self.assertEqual(activity.faculty_raw, ["TD", "SC"])
        self.assertEqual(activity.group_raw, "Gr-B")
        self.assertEqual(activity.room_raw, "H/W Lab")


if __name__ == "__main__":
    unittest.main()
