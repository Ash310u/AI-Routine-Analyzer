"""Classroom lookup joins each routine to one parent and only its children."""

import asyncio
import unittest
from collections import Counter
from unittest.mock import patch

import httpx

from app.clients.master_api import MasterAPI
from app.clients.classroom_api import match_parent, query_scopes
from app.config import Settings
from app.schemas.context import RoutineContext, SectionRecord, SubjectRecord
from app.schemas.extraction import RoutineExtraction
from app.services.routine_processor import _enrich, process_routine


def routine(section: str | None, department: str = "CSE", group: str | None = "Gr-A") -> RoutineExtraction:
    return RoutineExtraction.model_validate({
        "department": department, "year": "2nd", "semester": "3rd", "section": section,
        "slots": [{"day": "Monday", "start_time": "10:00", "end_time": "11:00",
                   "slot_type": "class", "activities": [
                       {"subject_raw": "Algorithms", "group_raw": group},
                       {"subject_raw": "Algorithms"},
                   ]}],
    })


def parent(record_id: int, class_id: int, name: str, college: int, session: int,
           course: int, stream: int) -> dict:
    return {"ID": record_id, "ClassId": class_id, "ClassName": name,
            "COLLEGE_MASTER_ID": college, "SESSION_MASTER_ID": session,
            "COURSE_MASTER_ID": course, "STREAM_MASTER_ID": stream, "SEMESTER_MASTER_ID": 3}


def child(record_id: int, class_id: int, name: str, parent_id: int, college: int) -> dict:
    return {"ID": record_id, "ClassId": class_id, "ClassName": name,
            "PARENT_CLASS_MASTER_ID": parent_id, "COLLEGE_MASTER_ID": college}


class ClassroomAPITest(unittest.TestCase):
    def test_nsec_odd_section_scopes_duplicate_subject_names_by_erp_ids(self):
        extracted = RoutineExtraction.model_validate({
            "section": "CSE.2A", "semester": "ODD", "year": "2026-27",
            "slots": [{"day": "Monday", "start_time": "09:20", "end_time": "10:10",
                       "slot_type": "class", "activities": [
                           {"subject_raw": "Analog & / Digital / Electronics"},
                           {"subject_raw": "ANA DIGI LAB"},
                           {"subject_raw": "IT Workshop"},
                           {"subject_raw": "IT Workshop (Sci Lab/Matlab/Python/R)"},
                           {"subject_raw": "IT Workshop (Sci Lab/Matlab/Python/R) / OOP & Python LAB"},
                       ]}],
        })
        subjects = [{"CourseMasterId": 2, "SemesterMasterId": 3, "Course": "B.Tech",
                     "Semester": "3rd", "Name": "Analog and Digital Electronics", "Code": "ESC301",
                     "SubjectMasterId": 926, "StreamMasterId": 8, "Stream": "CSE", "SubjectType": "Theory"},
                    {"CourseMasterId": 2, "SemesterMasterId": 3, "Course": "B.Tech",
                     "Semester": "3rd", "Name": "Analog and Digital Electronics", "Code": "ESC391",
                     "SubjectMasterId": 931, "StreamMasterId": 8, "Stream": "CSE", "SubjectType": "Lab"},
                    {"CourseMasterId": 2, "SemesterMasterId": 3, "Course": "B.Tech",
                     "Semester": "3rd", "Name": "Analog & Digital Electronics", "Code": "ESECS301",
                     "SubjectMasterId": 2240, "StreamMasterId": 37, "Stream": "EECE", "SubjectType": "Theory"},
                    {"CourseMasterId": 2, "SemesterMasterId": 3, "Course": "B.Tech",
                     "Semester": "3rd", "Name": "IT Workshop", "Code": "PCCCS393",
                     "SubjectMasterId": 934, "StreamMasterId": 8, "Stream": "CSE", "SubjectType": "Lab"}]

        def respond(request):
            if request.url.path == "/subjects":
                return httpx.Response(200, json={"data": subjects})
            if request.url.path == "/employees":
                return httpx.Response(200, json={"data": []})
            if request.url.path == "/parent":
                self.assertEqual(request.url.params["semesterId"], "3")
                self.assertEqual(request.url.params["streamId"], "8")
                return httpx.Response(200, json={"data": [parent(978, 884, "CSE A: All", 1, 27, 2, 8)]})
            if request.url.path == "/child":
                return httpx.Response(200, json={"data": []})
            raise AssertionError(str(request.url))

        settings = Settings(subject_api_base_url="https://example.test/subjects",
                            faculty_api_base_url="https://example.test/employees",
                            parent_class_api_url="https://example.test/parent",
                            child_class_api_url="https://example.test/child",
                            subject_embedding_backend="off")
        master = MasterAPI(settings)
        master.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

        async def check():
            try:
                with patch("app.services.routine_processor.is_excel_workbook", return_value=True), patch(
                    "app.services.routine_processor.TINTProfile.extract", return_value=[extracted],
                ):
                    result = await process_routine(b"workbook", settings, master, 1, 27)
                item = result.routines[0]
                self.assertEqual((item.course_master_id, item.stream_master_id,
                                  item.semester_master_id), (2, 8, 3))
                self.assertEqual(item.section.section_id, 978)
                activities = item.slots[0].activities
                self.assertEqual((activities[0].subject.subject_master_id,
                                  activities[0].subject.code), (926, "ESC301"))
                self.assertEqual((activities[1].subject.subject_master_id,
                                  activities[1].subject.code), (931, "ESC391"))
                for activity in activities[2:4]:
                    self.assertEqual((activity.subject.subject_master_id,
                                      activity.subject.code), (934, "PCCCS393"))
                self.assertIsNone(activities[4].subject.subject_master_id)
            finally:
                await master.aclose()

        asyncio.run(check())

    def test_nsec_missing_semester_uses_only_active_parent_scope(self):
        extracted = routine("AIML.2A", "AIML")
        extracted.semester = None
        catalog = [SubjectRecord(id=725, name="Analog and Digital Electronics",
                                 course="B.Tech", stream="AIML", semester="3rd",
                                 course_master_id=2, stream_master_id=3, semester_master_id=3),
                   SubjectRecord(id=306, name="Discrete Mathematics",
                                 course="B.Tech", stream="AIML", semester="4th",
                                 course_master_id=2, stream_master_id=3, semester_master_id=4)]
        self.assertEqual(query_scopes(extracted, catalog), {(2, 3, 3), (2, 3, 4)})

        def respond(request):
            if request.url.path == "/parent":
                if request.url.params["semesterId"] == "3":
                    return httpx.Response(200, json={"data": [parent(772, 678, "AIML A: All", 1, 27, 2, 3)]})
                return httpx.Response(200, json={"data": []})
            if request.url.path == "/child":
                return httpx.Response(200, json={"data": []})
            raise AssertionError(str(request.url))

        settings = Settings(parent_class_api_url="https://example.test/parent",
                            child_class_api_url="https://example.test/child")
        master = MasterAPI(settings)
        master.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        base = RoutineContext(subjects=catalog, faculty=[], sections=[], groups=[], college_id=1)

        async def check():
            try:
                context = (await master.load_classrooms([extracted], base, 1, 27))[0]
                self.assertEqual((context.course_master_id, context.stream_master_id,
                                  context.semester_master_id), (2, 3, 3))
                self.assertEqual(context.sections[0].id, 772)
            finally:
                await master.aclose()

        asyncio.run(check())
        fourth_year = routine("AIML.4", "AIML")
        self.assertEqual(match_parent(fourth_year, [SectionRecord(id=822, name="AIML: All")],
                                      {"aiml"}).id, 822)

    def test_catalog_scope_handles_workbook_stream_names(self):
        catalog = [SubjectRecord(id=1, name="Subject", course="B.Tech", stream="CS",
                                 semester="3rd", course_master_id=2, stream_master_id=19,
                                 semester_master_id=3),
                   SubjectRecord(id=2, name="Subject", course="B.Tech", stream="DS",
                                 semester="3rd", course_master_id=2, stream_master_id=20,
                                 semester_master_id=3)]
        self.assertEqual(query_scopes(routine(None, "CyS"), catalog), {(2, 19, 3)})
        self.assertEqual(query_scopes(routine(None, "CSE(Data Science)"), catalog), {(2, 20, 3)})

    def test_pipeline_resolves_two_tint_sections_and_only_their_groups(self):
        extracted = [routine("1"), routine("2")]
        calls = Counter()

        def respond(request):
            calls[(request.url.path, str(request.url.query))] += 1
            path, params = request.url.path, request.url.params
            if path == "/subjects":
                return httpx.Response(200, json={"ok": True, "data": [{
                    "SubjectMasterId": 11, "Name": "Algorithms", "CourseMasterId": 2,
                    "StreamMasterId": 8, "SemesterMasterId": 3,
                    "Course": "B.Tech", "Stream": "CSE", "Semester": "3rd",
                }, {
                    "SubjectMasterId": 12, "Name": "Other", "CourseMasterId": 3,
                    "StreamMasterId": 8, "SemesterMasterId": 3,
                    "Course": "M.Tech", "Stream": "CSE", "Semester": "3rd",
                }]})
            if path == "/employees":
                return httpx.Response(200, json={"ok": True, "data": []})
            if path == "/parent":
                self.assertEqual(params["sessionId"], "28")
                self.assertEqual(params["streamId"], "8")
                self.assertEqual(params["semesterId"], "3")
                data = ([parent(857, 763, "CSE 1: All", 2, 28, 2, 8),
                         parent(860, 766, "CSE 2: All", 2, 28, 2, 8)]
                        if params["courseId"] == "2" else
                        [parent(1020, 926, "CSE: All", 2, 28, 3, 8)])
                return httpx.Response(200, json={"ok": True, "data": data})
            if path == "/child":
                parent_id = int(params["parentClassId"])
                self.assertIn(parent_id, (857, 860))
                child_id = 858 if parent_id == 857 else 861
                return httpx.Response(200, json={"ok": True, "data": [
                    child(child_id, child_id - 94, f"CSE {1 if parent_id == 857 else 2}: Group A", parent_id, 2),
                ]})
            raise AssertionError(f"Unexpected API call: {request.url}")

        settings = Settings(subject_api_base_url="https://example.test/subjects",
                            faculty_api_base_url="https://example.test/employees",
                            parent_class_api_url="https://example.test/parent",
                            child_class_api_url="https://example.test/child",
                            subject_embedding_backend="off")
        master = MasterAPI(settings)
        master.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

        async def check():
            try:
                with patch("app.services.routine_processor.is_excel_workbook", return_value=True), patch(
                    "app.services.routine_processor.TINTProfile.extract", return_value=extracted,
                ):
                    first = await process_routine(b"workbook", settings, master, 2, 28)
                    await process_routine(b"workbook", settings, master, 2, 28)
                one, two = first.routines
                self.assertEqual((one.section.section_id, one.section.class_id), (857, 763))
                self.assertEqual((two.section.section_id, two.section.class_id), (860, 766))
                self.assertEqual(first.session_id, 28)
                for item, section_id, class_id in ((one, 857, 763), (two, 860, 766)):
                    self.assertEqual((item.course_master_id, item.stream_master_id,
                                      item.semester_master_id), (2, 8, 3))
                    for slot in item.slots:
                        self.assertEqual((slot.college_id, slot.session_id,
                                          slot.course_master_id, slot.stream_master_id,
                                          slot.semester_master_id), (2, 28, 2, 8, 3))
                        self.assertEqual((slot.section.section_id, slot.section.class_id),
                                         (section_id, class_id))
                self.assertEqual((one.slots[0].activities[0].group.group_id,
                                  two.slots[0].activities[0].group.group_id), (858, 861))
                self.assertEqual(one.slots[0].activities[0].group.class_id, 764)
                self.assertEqual(one.slots[0].activities[0].group.parent_class_master_id, 857)
                self.assertIsNone(one.slots[0].activities[1].group)
                self.assertEqual(sum(count for (path, _), count in calls.items() if path == "/parent"), 2)
                self.assertEqual(sum(count for (path, _), count in calls.items() if path == "/child"), 2)
            finally:
                await master.aclose()

        asyncio.run(check())

    def test_nsec_dotted_section_and_missing_section(self):
        settings = Settings(subject_api_base_url="https://example.test/subjects",
                            faculty_api_base_url="https://example.test/employees",
                            parent_class_api_url="https://example.test/parent",
                            child_class_api_url="https://example.test/child",
                            subject_embedding_backend="off")
        calls = []

        def respond(request):
            calls.append(request.url.path)
            if request.url.path == "/subjects":
                return httpx.Response(200, json={"data": [{
                    "SubjectMasterId": 3, "Name": "Algorithms", "CourseMasterId": 2,
                    "StreamMasterId": 3, "SemesterMasterId": 3,
                    "Course": "B.Tech", "Stream": "AIML", "Semester": "3rd",
                }]})
            if request.url.path == "/employees":
                return httpx.Response(200, json={"data": []})
            if request.url.path == "/parent":
                self.assertEqual(request.url.params["sessionId"], "27")
                return httpx.Response(200, json={"data": [
                    parent(772, 678, "AIML A: All", 1, 27, 2, 3),
                    parent(773, 679, "AIML B: All", 1, 27, 2, 3),
                ]})
            if request.url.path == "/child":
                self.assertEqual(request.url.params["parentClassId"], "772")
                return httpx.Response(200, json={"data": []})
            raise AssertionError(str(request.url))

        master = MasterAPI(settings)
        master.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

        async def check():
            try:
                base = await master.load(routine("AIML.2A", "AIML"), 1)
                contexts = await master.load_classrooms(
                    [routine("AIML.2A", "AIML"), routine(None, "AIML")], base, 1, 27,
                )
                self.assertEqual(contexts[0].sections[0].id, 772)
                self.assertEqual(contexts[0].sections[0].class_id, 678)
                self.assertEqual(contexts[1].sections, [])
                self.assertEqual(calls.count("/parent"), 1)
                self.assertEqual(calls.count("/child"), 1)
            finally:
                await master.aclose()

        asyncio.run(check())

    def test_missing_section_uses_only_parent_when_scope_is_unique(self):
        settings = Settings(parent_class_api_url="https://example.test/parent",
                            child_class_api_url="https://example.test/child")

        def respond(request):
            if request.url.path == "/parent":
                return httpx.Response(200, json={"data": [
                    parent(999, 905, "AEIE: All", 1, 27, 2, 2),
                ]})
            if request.url.path == "/child":
                self.assertEqual(request.url.params["parentClassId"], "999")
                return httpx.Response(200, json={"data": []})
            raise AssertionError(str(request.url))

        master = MasterAPI(settings)
        master.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        base = RoutineContext(subjects=[SubjectRecord(
            id=1, name="Subject", course="B.Tech", stream="AEIE", semester="3rd",
            course_master_id=2, stream_master_id=2, semester_master_id=3,
        )], faculty=[], sections=[], groups=[], college_id=1)
        extracted = routine(None, "AEIE", None)

        async def check():
            try:
                context = (await master.load_classrooms([extracted], base, 1, 27))[0]
                result = _enrich(extracted, context, ({}, {}, {}))
                self.assertEqual((result.section.section_id, result.section.class_id), (999, 905))
                self.assertIsNone(result.slots[0].activities[0].group)
            finally:
                await master.aclose()

        asyncio.run(check())

    def test_session_id_is_supplied_by_caller(self):
        settings = Settings(parent_class_api_url="https://example.test/parent",
                            child_class_api_url="https://example.test/child")

        def respond(request):
            if request.url.path == "/parent":
                self.assertEqual(request.url.params["sessionId"], "31")
                return httpx.Response(200, json={"data": [
                    parent(1200, 1100, "AEIE: All", 1, 31, 2, 2),
                ]})
            if request.url.path == "/child":
                return httpx.Response(200, json={"data": []})
            raise AssertionError(str(request.url))

        master = MasterAPI(settings)
        master.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        base = RoutineContext(subjects=[SubjectRecord(
            id=1, name="Subject", course="B.Tech", stream="AEIE", semester="3rd",
            course_master_id=2, stream_master_id=2, semester_master_id=3,
        )], faculty=[], sections=[], groups=[], college_id=1)

        async def check():
            try:
                context = (await master.load_classrooms([routine(None, "AEIE")], base, 1, 31))[0]
                self.assertEqual(context.session_id, 31)
                self.assertEqual(context.sections[0].id, 1200)
            finally:
                await master.aclose()

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
