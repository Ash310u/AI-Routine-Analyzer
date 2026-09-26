"""End-to-end local check for the supplied TINT workbook, without external calls."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.config import Settings
from app.main import app
from app.schemas.context import RoutineContext


WORKBOOK = Path(__file__).resolve().parents[1] / "Routines" / "TINT" / "tint.xlsx"


class FakeMaster:
    def __init__(self):
        self.calls = 0

    async def load(self, routine):
        self.calls += 1
        return RoutineContext(subjects=[], faculty=[], groups=[], sections=[])


class TintWorkbookTest(unittest.TestCase):
    def test_upload_returns_and_saves_all_routines_without_llm(self):
        master = FakeMaster()
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=directory)
            app.state.master_api = master
            with patch("app.main.Settings", return_value=settings), patch(
                "app.services.routine_processor.RoutineExtractor.extract",
                side_effect=AssertionError("TINT workbook must not call the LLM"),
            ):
                async def request():
                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        with WORKBOOK.open("rb") as stream:
                            return await client.post(
                                "/routines/standardize",
                                files={"file": (WORKBOOK.name, stream,
                                                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                            )
                response = asyncio.run(request())

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["source_type"], "workbook")
            self.assertEqual(payload["routine_count"], 30)
            self.assertEqual(len(payload["routines"]), 30)
            self.assertEqual(sum(len(r["slots"]) for r in payload["routines"]), 1084)
            self.assertEqual(master.calls, 1)

            first = payload["routines"][0]
            self.assertEqual(first["department"], "CSE")
            self.assertEqual(first["section"]["raw"], "1")
            lab = next(slot for slot in first["slots"] if len(slot["activities"]) == 2)
            self.assertEqual({item["group"]["raw"] for item in lab["activities"]},
                             {"Gr-A", "Gr-B"})
            self.assertTrue(all(slot["start_time"] < slot["end_time"]
                                for routine in payload["routines"] for slot in routine["slots"]))
            self.assertTrue(all(slot["start_period"] is None and slot["end_period"] is None
                                for routine in payload["routines"] for slot in routine["slots"]))
            saved = Path(payload["output_file"])
            self.assertTrue(saved.is_file())
            self.assertEqual(json.loads(saved.read_text(encoding="utf-8")), payload)


if __name__ == "__main__":
    unittest.main()
