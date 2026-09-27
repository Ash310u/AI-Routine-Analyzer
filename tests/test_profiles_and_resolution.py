"""The two input profiles share one downstream shape and deterministic matching."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.config import Settings
from app.clients.master_api import MasterAPI, _faculty
from app.llm.extractor import ExtractionError
from app.llm.extractor import RoutineExtractor
from app.main import app
from app.ingestion.spreadsheet_routines import NoRoutineBlocks, _activity
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
        model = FakeModel({"routines": [{
            "course": "B.Tech", "department": "AIML", "year": "2", "semester": "3",
            "section": "AIML.4", "default_room": "R-318",
            "slots": [{"day": "Monday", "start_period": 4, "end_period": 5,
                       "start_time": "11:50", "end_time": "13:30", "slot_type": "class",
                       "activities": [{"subject_raw": "AI-ML", "faculty_raw": ["AIML_SC"],
                                       "room_raw": "Lab 1", "notes": "Visible note"}]},
                      ],
        }]})
        raw = asyncio.run(RoutineExtractor(Settings(), NSECProfile(), model).extract(["data:image/png;base64,AA=="]))
        self.assertEqual(len(raw), 1)
        self.assertIs(type(raw[0]), RoutineExtraction)
        self.assertEqual((raw[0].course, raw[0].department, raw[0].year, raw[0].semester,
                          raw[0].section, raw[0].default_room),
                         ("B.Tech", "AIML", "2", "3", "AIML.4", "R-318"))
        self.assertEqual(raw[0].slots[0].end_period, 5)
        self.assertEqual(raw[0].slots[0].activities[0].faculty_raw, ["AIML_SC"])
        self.assertEqual(raw[0].slots[0].activities[0].room_raw, "Lab 1")
        self.assertEqual(raw[0].slots[0].activities[0].notes, "Visible note")
        self.assertIn("NSEC format rules", model.messages[0]["content"][0]["text"])
        self.assertIn('"routines": [', model.messages[0]["content"][0]["text"])

    def test_nsec_multi_table_pdf_returns_document_collection(self):
        payload = {"routines": [
            {"course": course, "department": department, "year": str(year),
             "semester": str(semester), "section": section,
             "slots": [{"day": "Monday", "start_time": "10:00", "end_time": "11:00",
                        "slot_type": "class", "activities": [{"subject_raw": "DSA"}]}]}
            for course, department, section, year, semester in (
                ("B.Tech", "AIML", "AIML.1", 2, 3),
                ("M.Tech", "CSE", "CSE.2", 1, 1),
            )
        ]}
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
        self.assertEqual([item.course for item in result.routines], ["B.Tech", "M.Tech"])
        self.assertEqual([item.department for item in result.routines], ["AIML", "CSE"])
        self.assertEqual([item.section.raw for item in result.routines], ["AIML.1", "CSE.2"])
        self.assertEqual([item.year for item in result.routines], ["2", "1"])
        self.assertEqual([item.semester for item in result.routines], ["3", "1"])
        self.assertEqual([item.slots[0].activities[0].subject.raw for item in result.routines], ["DSA", "DSA"])

    def test_nsec_single_table_returns_routines_array_with_complete_slot(self):
        extracted = RoutineExtraction.model_validate({
            "course": "B.Tech", "department": "AIML", "year": "2", "semester": "3",
            "section": "AIML.2A", "default_room": "R-318", "routine_version": "V1",
            "slots": [{
                "day": "Monday", "start_period": 4, "end_period": 5,
                "start_time": "11:50", "end_time": "13:30", "slot_type": "class",
                "activities": [{"group_raw": "Gr-A", "subject_raw": "DSA Lab",
                                "subject_code_raw": "PCC-CS392", "subject_type_raw": "Lab",
                                "faculty_raw": ["AIML_SC", "AIML_SS"], "room_raw": "Lab 1",
                                "notes": "Printed note"}],
            }],
        })

        class FakeMaster:
            async def load(self, routine, college_id):
                return RoutineContext(subjects=[], faculty=[], groups=[], sections=[], college_id=college_id)

        with patch("app.services.routine_processor.image_data_urls", return_value=["data:image/png;base64,AA=="]), patch(
            "app.services.routine_processor.RoutineExtractor.extract", return_value=[extracted],
        ):
            result = asyncio.run(process_routine(b"pdf", Settings(), FakeMaster(), 1))
        payload = result.model_dump(mode="json")
        self.assertEqual((payload["source_type"], payload["routine_count"], len(payload["routines"])),
                         ("document", 1, 1))
        routine = payload["routines"][0]
        self.assertEqual((routine["course"], routine["department"], routine["year"],
                          routine["semester"], routine["section"]["raw"], routine["default_room"]),
                         ("B.Tech", "AIML", "2", "3", "AIML.2A", "R-318"))
        slot = routine["slots"][0]
        self.assertEqual((slot["day"], slot["start_period"], slot["end_period"],
                          slot["start_time"], slot["end_time"], slot["slot_type"]),
                         ("Monday", 4, 5, "11:50:00", "13:30:00", "class"))
        activity = slot["activities"][0]
        self.assertEqual((activity["group"]["raw"], activity["subject"]["raw"],
                          activity["subject"]["code_raw"], activity["subject_type_raw"],
                          [person["raw"] for person in activity["faculty"]],
                          activity["room"]["raw"], activity["notes"]),
                         ("Gr-A", "DSA Lab", "PCC-CS392", "Lab", ["AIML_SC", "AIML_SS"],
                          "Lab 1", "Printed note"))

    def test_extractor_rejects_missing_routines_array(self):
        model = FakeModel({"section": "AIML.2A", "slots": [{"activities": []}]})
        with self.assertRaises(ExtractionError):
            asyncio.run(RoutineExtractor(Settings(), NSECProfile(), model).extract([]))

    def test_single_nsec_api_response_and_saved_file_use_routines_array(self):
        extracted = RoutineExtraction.model_validate({"course": "B.Tech", "department": "AIML",
            "year": "2", "semester": "3", "section": "AIML.2A", "slots": [{
                "day": "Monday", "start_period": 4, "end_period": 5,
                "start_time": "11:50", "end_time": "13:30", "slot_type": "class",
                "activities": [{"subject_raw": "DSA Lab", "faculty_raw": ["AIML_SC"]}],
            }],
        })

        class FakeMaster:
            async def load(self, routine, college_id):
                return RoutineContext(subjects=[], faculty=[], groups=[], sections=[], college_id=college_id)

        with tempfile.TemporaryDirectory() as directory:
            app.state.master_api = FakeMaster()
            with patch("app.main.Settings", return_value=Settings(output_dir=directory)), patch(
                "app.services.routine_processor.image_data_urls", return_value=["data:image/png;base64,AA=="],
            ), patch("app.services.routine_processor.RoutineExtractor.extract", return_value=[extracted]):
                async def request():
                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        return await client.post("/routines/standardize?college_id=1", files={
                            "file": ("nsec.pdf", b"pdf", "application/pdf"),
                        })
                response = asyncio.run(request())

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["source_type"], "document")
            self.assertEqual(payload["routine_count"], 1)
            self.assertEqual(len(payload["routines"]), 1)
            routine = payload["routines"][0]
            self.assertEqual((routine["course"], routine["department"], routine["year"],
                              routine["semester"], routine["section"]["raw"]),
                             ("B.Tech", "AIML", "2", "3", "AIML.2A"))
            self.assertEqual(routine["slots"][0]["start_period"], 4)
            self.assertEqual(routine["slots"][0]["end_period"], 5)
            self.assertEqual(routine["slots"][0]["activities"][0]["faculty"][0]["raw"], "AIML_SC")
            self.assertEqual(json.loads(Path(payload["output_file"]).read_text()), payload)

    def test_generic_workbook_fallback_keeps_routines_wrapper(self):
        extracted = RoutineExtraction.model_validate({"department": "ECE", "section": "ECE.1",
            "slots": [{"day": "Monday", "start_time": "10:00", "end_time": "11:00",
                       "slot_type": "class", "activities": [{"subject_raw": "Circuits"}]}],
        })

        class FakeMaster:
            async def load(self, routine, college_id):
                return RoutineContext(subjects=[], faculty=[], groups=[], sections=[], college_id=college_id)

        with patch("app.services.routine_processor.is_excel_workbook", return_value=True), patch(
            "app.services.routine_processor.TINTProfile.extract", side_effect=NoRoutineBlocks("Other layout"),
        ), patch("app.services.routine_processor.workbook_text", return_value="Sheet: Routine"), patch(
            "app.services.routine_processor.RoutineExtractor",
        ) as extractor_type:
            extractor_type.return_value.extract = AsyncMock(return_value=[extracted])
            result = asyncio.run(process_routine(b"workbook", Settings(), FakeMaster(), 2))

        self.assertEqual(extractor_type.call_args.args[1].name, "generic")
        self.assertEqual(result.source_type, "workbook")
        self.assertEqual(result.routine_count, 1)
        self.assertEqual(result.routines[0].section.raw, "ECE.1")
        self.assertEqual(result.routines[0].slots[0].activities[0].subject.raw, "Circuits")

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

    def test_prefixed_nsec_faculty_uses_suffix_from_cached_api_records(self):
        context = RoutineContext(subjects=[], groups=[], sections=[], department="AIML", faculty=_faculty([
            {"EmployeeId": 41, "EmployeeName": "Sanjay Ghosh", "Stream": "AIML", "Department": "Academics"},
            {"EmployeeId": 42, "EmployeeName": "Suman Gupta", "Stream": "CSE", "Department": "Academics"},
            {"EmployeeId": 43, "EmployeeName": "Tapan Das", "Stream": "CSE", "Department": "Academics"},
        ]))
        resolved = resolve.faculty(["AIML_SG", "NSEC_AIML_SG", "TD"], context)
        self.assertEqual([item.faculty_id for item in resolved], [41, 41, 43])
        self.assertEqual([item.raw for item in resolved], ["AIML_SG", "NSEC_AIML_SG", "TD"])

        routine = RoutineExtraction.model_validate({"department": "AIML", "slots": [{
            "day": "Monday", "start_time": "10:00", "end_time": "11:00", "slot_type": "class",
            "activities": [{"subject_raw": "AI-ML", "faculty_raw": ["AIML_SG"]}],
        }]})
        result = _enrich(routine, context, ({}, {}, {}))
        self.assertEqual(result.slots[0].activities[0].faculty[0].faculty_id, 41)
        self.assertEqual(result.slots[0].activities[0].faculty[0].raw, "AIML_SG")

    def test_prefixed_initial_remains_unresolved_when_department_tie_remains(self):
        context = RoutineContext(subjects=[], groups=[], sections=[], department="AIML", faculty=[
            FacultyRecord(id=41, name="Sanjay Ghosh", department="AIML"),
            FacultyRecord(id=44, name="Suman Gupta", department="AIML"),
            FacultyRecord(id=42, name="Sagar Ghosh", department="CSE"),
        ])
        self.assertIsNone(resolve.faculty(["AIML_SG"], context)[0].faculty_id)
        self.assertIsNone(resolve.faculty(["AIML_"], context)[0].faculty_id)

    def test_class_section_department_breaks_faculty_ties_without_cache_leak(self):
        context = RoutineContext(subjects=[], groups=[], sections=[], faculty=[
            FacultyRecord(id=41, name="Sourav Chandra", department="CSE"),
            FacultyRecord(id=42, name="Soma Chatterjee", department="ECE"),
        ])
        caches = ({}, {}, {})

        def routine(section):
            return RoutineExtraction.model_validate({"section": section, "slots": [{
                "day": "Monday", "start_time": "10:00", "end_time": "11:00", "slot_type": "class",
                "activities": [{"subject_raw": "Class", "faculty_raw": ["SC"]}],
            }]})

        cse = _enrich(routine("CSE.2A"), context, caches)
        ece = _enrich(routine("ECE.2A"), context, caches)
        self.assertEqual(cse.slots[0].activities[0].faculty[0].faculty_id, 41)
        self.assertEqual(ece.slots[0].activities[0].faculty[0].faculty_id, 42)
        self.assertEqual(cse.slots[0].activities[0].faculty[0].raw, "SC")
        self.assertIsNone(resolve.faculty(["ZZ"], context)[0].faculty_id)
        self.assertIsNone(resolve.faculty(["SC"], context)[0].faculty_id)

    def test_routine_department_takes_priority_over_section_for_faculty(self):
        context = RoutineContext(subjects=[], groups=[], sections=[], department="CSE", section="ECE.2A", faculty=[
            FacultyRecord(id=41, name="Sourav Chandra", department="CSE"),
            FacultyRecord(id=42, name="Soma Chatterjee", department="ECE"),
        ])
        self.assertEqual(resolve.faculty(["SC"], context)[0].faculty_id, 41)

    def test_numbered_initials_and_department_ties_across_routines(self):
        context = RoutineContext(subjects=[], groups=[], sections=[], faculty=_faculty([
            {"EmployeeId": 41, "EmployeeName": "Debashis Bose", "Stream": "ECE", "Department": "Academics", "Abbreviation": "DB"},
            {"EmployeeId": 42, "EmployeeName": "Dipak Banerjee", "Stream": "CSE", "Department": "Academics", "Abbreviation": "DB"},
            {"EmployeeId": 43, "EmployeeName": "Dinesh Chandra", "Stream": "CSE", "Department": "Academics", "Abbreviation": "DB12"},
        ]))
        caches = ({}, {}, {})

        def routine(department, raw):
            return RoutineExtraction.model_validate({"department": department, "slots": [{
                "day": "Monday", "start_time": "10:00", "end_time": "11:00", "slot_type": "class",
                "activities": [{"subject_raw": "Class", "faculty_raw": [raw]}],
            }]})

        cse = _enrich(routine("CSE", "DB"), context, caches)
        ece = _enrich(routine("ECE", "DB"), context, caches)
        numbered = _enrich(routine("CSE", "CSE_DB12"), context, caches)
        self.assertEqual(cse.slots[0].activities[0].faculty[0].faculty_id, 42)
        self.assertEqual(ece.slots[0].activities[0].faculty[0].faculty_id, 41)
        self.assertEqual(numbered.slots[0].activities[0].faculty[0].faculty_id, 43)
        self.assertEqual(_activity("Class (DB12)", "Sheet", 1, 1).faculty_raw, ["DB12"])
        self.assertIsNone(resolve.faculty(["DB13"], context)[0].faculty_id)

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
