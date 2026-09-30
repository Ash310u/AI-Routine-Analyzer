"""Match extracted routine sections to ERP parent classes and their child groups."""

import re

from app.resolvers.matching import normalize, normalize_department, normalize_semester
from app.schemas.context import SectionRecord, SubjectRecord
from app.schemas.extraction import RoutineExtraction


def _stream_names(routine: RoutineExtraction) -> set[str]:
    names = set()
    for value in (routine.department, routine.section):
        if not value:
            continue
        names.add(normalize_department(value))
        prefix = re.split(r"[._]", value, maxsplit=1)[0]
        names.add(normalize_department(prefix))
        for part in re.findall(r"\(([^)]+)\)", value):
            names.add(normalize_department(part))
            words = re.findall(r"[A-Za-z]+", part)
            if len(words) > 1:
                names.add(normalize_department("".join(word[0] for word in words)))
        if re.match(r"^CSE[-/ ]", value, re.I):
            names.add(normalize_department(re.split(r"[-/ ]", value, maxsplit=1)[1]))
    names = {name for name in names if name}
    # The TINT workbook labels Cyber Security as CyS; the ERP catalog uses CS.
    if "cys" in names:
        names.add("cs")
    return names


def query_scopes(routine: RoutineExtraction, subjects: list[SubjectRecord]) -> set[tuple[int, int, int]]:
    """Find catalog scopes; the session's parent classes decide among candidates."""
    streams = _stream_names(routine)
    semester = normalize_semester(routine.semester)
    if not streams:
        return set()
    year_match = (re.search(r"[._]\s*([1-4])(?:\s*[A-Za-z])?\s*$", routine.section or "")
                  or re.fullmatch(r"\s*([1-4])(?:st|nd|rd|th)\s*", routine.year or "", re.I))
    year = int(year_match.group(1)) if year_match else None
    term = semester if semester in {"odd", "even"} else None
    if not year and (not semester or term):
        return set()
    course = normalize(routine.course)
    return {
        (item.course_master_id, item.stream_master_id, item.semester_master_id)
        for item in subjects
        if item.course_master_id and item.stream_master_id and item.semester_master_id
        and item.stream and normalize_department(item.stream) in streams
        and item.semester_master_id
        and (item.semester_master_id in (2 * year - 1, 2 * year) if year else True)
        and (item.semester_master_id % 2 == (1 if term == "odd" else 0) if term else True)
        and (normalize_semester(item.semester) == semester if semester and not term else True)
        and (not course or item.course and normalize(item.course) == course)
    }


def section_token(raw: str | None) -> str:
    if not raw:
        return ""
    tail = re.split(r"[._]", raw.strip())[-1].strip()
    year_and_letter = re.fullmatch(r"\d+\s*([A-Za-z])", tail)
    return normalize(year_and_letter.group(1) if year_and_letter else tail)


def match_parent(routine: RoutineExtraction, parents: list[SectionRecord],
                 stream_names: set[str]) -> SectionRecord | None:
    token = section_token(routine.section)
    if not token:
        return None
    matches = []
    for parent in parents:
        base, marker, kind = parent.name.partition(":")
        if not marker or normalize(kind) != "all":
            continue
        for stream in stream_names:
            normalized_base = normalize_department(base)
            year_only = bool(re.search(r"[._]\s*[1-4]\s*$", routine.section or ""))
            if normalized_base.startswith(stream) and normalized_base[len(stream):] == ("" if year_only else token):
                matches.append(parent)
                break
    return matches[0] if len(matches) == 1 else None
