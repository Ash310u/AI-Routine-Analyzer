"""Discard raw values that the converted workbook does not actually contain."""

import re
from datetime import time

from app.resolvers.matching import normalize
from app.schemas.extraction import RoutineExtraction


ROUTINE_FIELDS = ("college", "course", "department", "year", "semester",
                  "section", "default_room", "routine_version")
ACTIVITY_FIELDS = ("group_raw", "subject_raw", "subject_code_raw",
                   "subject_type_raw", "room_raw", "notes")
DAY_KEYS = {
    "monday": ("mon", "monday"), "tuesday": ("tue", "tues", "tuesday"),
    "wednesday": ("wed", "wednesday"), "thursday": ("thu", "thur", "thursday"),
    "friday": ("fri", "friday"), "saturday": ("sat", "saturday"),
    "sunday": ("sun", "sunday"),
}
VISIBLE_TIME = re.compile(r"(?<!\d)(\d{1,2})[.:](\d{2})\s*(am|pm)?(?!\d)", re.I)


def _visible_times(cell_texts: list[str]) -> set[time]:
    found = set()
    for text in cell_texts:
        for hour_text, minute_text, suffix in VISIBLE_TIME.findall(text):
            hour, minute = int(hour_text), int(minute_text)
            if hour > 23 or minute > 59:
                continue
            if suffix:
                hour = hour % 12 + (12 if suffix.casefold() == "pm" else 0)
                found.add(time(hour, minute))
            else:
                found.add(time(hour, minute))
                if hour <= 12:
                    found.add(time(hour % 12 + 12, minute))
    return found


def keep_visible_values(routines: list[RoutineExtraction], cell_texts: list[str] | list[list[str]]):
    """Blank unsupported raw strings while keeping the parser's canonical shape."""
    tables = cell_texts if cell_texts and isinstance(cell_texts[0], list) else [cell_texts]
    all_texts = [text for table in tables for text in table]

    corrected = []
    reasons = []
    for routine_number, routine in enumerate(routines, start=1):
        # Use one table's evidence when the parser returned one routine per
        # transcribed sheet. If a table contains several routines, use all text.
        source_texts = tables[routine_number - 1] if len(tables) == len(routines) else all_texts
        visible = [normalize(text) for text in source_texts]
        visible_times = _visible_times(source_texts)

        def exists(value: str | None) -> bool:
            key = normalize(value)
            return bool(key) and any(key in text for text in visible)

        data = routine.model_dump(mode="python")
        for field in ROUTINE_FIELDS:
            if data[field] is not None and not exists(data[field]):
                data[field] = None
                reasons.append(f"Routine {routine_number}: {field} was not visible in the converted workbook")
        for slot_number, slot in enumerate(data["slots"], start=1):
            slot_prefix = f"Routine {routine_number}, slot {slot_number}"
            if slot["day"] is not None:
                day_keys = DAY_KEYS.get(normalize(slot["day"]), ())
                if not day_keys or not any(any(key in text for key in day_keys) for text in visible):
                    slot["day"] = None
                    reasons.append(f"{slot_prefix}: day was not visible in the converted workbook")
            for field in ("start_time", "end_time"):
                if slot[field] is not None and slot[field] not in visible_times:
                    slot[field] = None
                    reasons.append(f"{slot_prefix}: {field} was not visible in the converted workbook")
            for field in ("start_period", "end_period"):
                period = slot[field]
                if period is not None and not any(
                    re.search(rf"(?<!\d){period}(?!\d)", text) for text in source_texts
                ):
                    slot[field] = None
                    reasons.append(f"{slot_prefix}: {field} was not visible in the converted workbook")
            if slot["slot_type"] == "break" and not any(
                word in text for text in visible for word in ("break", "recess", "lunch")
            ):
                slot["slot_type"] = None
                reasons.append(f"{slot_prefix}: break label was not visible in the converted workbook")
            for activity_number, activity in enumerate(slot["activities"], start=1):
                prefix = f"Routine {routine_number}, slot {slot_number}, activity {activity_number}"
                for field in ACTIVITY_FIELDS:
                    if activity[field] is not None and not exists(activity[field]):
                        activity[field] = None
                        reasons.append(f"{prefix}: {field} was not visible in the converted workbook")
                kept = [value for value in activity["faculty_raw"] if exists(value)]
                if len(kept) != len(activity["faculty_raw"]):
                    reasons.append(f"{prefix}: some faculty identifiers were not visible in the converted workbook")
                activity["faculty_raw"] = kept
        corrected.append(RoutineExtraction.model_validate(data))
    return corrected, reasons
