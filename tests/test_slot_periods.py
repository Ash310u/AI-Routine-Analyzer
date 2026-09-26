"""Period labels survive extraction and resolution without guessed values."""

import unittest

from pydantic import ValidationError

from app.ingestion.spreadsheet_routines import Grid, _extract_block
from app.schemas.context import RoutineContext
from app.schemas.extraction import RoutineExtraction
from app.services.routine_processor import _enrich


class SlotPeriodsTest(unittest.TestCase):
    def test_multi_period_slot_is_preserved_once_in_response(self):
        extracted = RoutineExtraction.model_validate({
            "section": "AIML.4",
            "slots": [{
                "day": "Monday", "start_period": 4, "end_period": 5,
                "start_time": "11:50:00", "end_time": "13:30:00",
                "slot_type": "class", "activities": [{
                    "group_raw": None, "subject_raw": "DSA Lab",
                    "faculty_raw": ["AIML_SC", "AIML_SS", "AIML_NF2", "AIML_NF5"],
                }],
            }],
        })
        context = RoutineContext(subjects=[], faculty=[], groups=[], sections=[])
        routine = _enrich(extracted, context, ({}, {}, {})).model_dump(mode="json")

        self.assertEqual(len(routine["slots"]), 1)
        slot = routine["slots"][0]
        self.assertEqual((slot["start_period"], slot["end_period"]), (4, 5))
        self.assertEqual((slot["start_time"], slot["end_time"]),
                         ("11:50:00", "13:30:00"))
        self.assertEqual(slot["activities"][0]["subject"]["raw"], "DSA Lab")
        self.assertEqual([person["raw"] for person in slot["activities"][0]["faculty"]],
                         ["AIML_SC", "AIML_SS", "AIML_NF2", "AIML_NF5"])

    def test_missing_periods_remain_null_and_reverse_range_is_rejected(self):
        slot = {
            "day": "Monday", "start_time": "11:50", "end_time": "12:40",
            "slot_type": "class", "activities": [],
        }
        extracted = RoutineExtraction.model_validate({"slots": [slot]})
        self.assertIsNone(extracted.slots[0].start_period)
        self.assertIsNone(extracted.slots[0].end_period)

        with self.assertRaises(ValidationError):
            RoutineExtraction.model_validate({
                "slots": [{**slot, "start_period": 5, "end_period": 4}],
            })

    def test_explicit_workbook_periods_follow_merged_cell(self):
        grid = Grid(title="Routine", rows=4, columns=4, values={
            (1, 1): "College",
            (2, 1): "Department: AIML Section: 1",
            (3, 2): "Period 4 11:50-12:40",
            (3, 3): "Period 5 12:40-13:30",
            (3, 4): "Period 6 13:30-14:20",
            (4, 1): "MON",
            (4, 2): "DSA Lab",
        }, merges=[(4, 4, 2, 3)])
        routine = _extract_block(grid, 2, 5)
        self.assertEqual(len(routine.slots), 1)
        self.assertEqual((routine.slots[0].start_period, routine.slots[0].end_period),
                         (4, 5))

    def test_unreadable_slot_fields_are_null_and_flagged(self):
        extracted = RoutineExtraction.model_validate({
            "slots": [{"activities": []}],
        })
        context = RoutineContext(subjects=[], faculty=[], groups=[], sections=[])
        routine = _enrich(extracted, context, ({}, {}, {})).model_dump(mode="json")
        slot = routine["slots"][0]
        self.assertIsNone(slot["day"])
        self.assertIsNone(slot["start_time"])
        self.assertIn("Slot time could not be read", slot["review_reasons"])
        self.assertTrue(routine["requires_review"])
