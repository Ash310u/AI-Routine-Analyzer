import re
from difflib import SequenceMatcher

from app.resolvers.matching import normalize, normalize_department, normalize_group, normalize_section, normalize_semester
from app.schemas.context import RoutineContext
from app.schemas.routine import ResolvedFaculty, ResolvedGroup, ResolvedSection, ResolvedSubject


SECTION_DEPARTMENT = re.compile(r"^\s*([A-Za-z][A-Za-z0-9&+ /-]*?)\s*[._]\s*\d")


def section(raw: str | None, context: RoutineContext) -> ResolvedSection:
    matches = [item for item in context.sections if normalize_section(item.name) == normalize_section(raw)] if raw else []
    item = matches[0] if len(matches) == 1 else None
    return ResolvedSection(raw=raw, section_id=item.id if item else None, name=item.name if item else None)


def group(raw: str | None, context: RoutineContext) -> ResolvedGroup | None:
    if raw is None:
        return None
    section_ids = {str(item.id) for item in context.sections
                   if normalize_section(item.name) == normalize_section(context.section)}
    matches = [item for item in context.groups if normalize_group(item.name) == normalize_group(raw)
               and (item.section_id is None or str(item.section_id) in section_ids)]
    item = matches[0] if len(matches) == 1 else None
    return ResolvedGroup(raw=raw, group_id=item.id if item else None, name=item.name if item else None)


def faculty(raw_values: list[str], context: RoutineContext) -> list[ResolvedFaculty]:
    department = faculty_department(context)
    result = []
    for raw in raw_values:
        # Timetable prefixes identify a section/stream, not the employee.
        # Keep the original raw value in the result, but look up only its suffix.
        key = normalize(raw.rsplit("_", 1)[-1])
        eligible = [item for item in context.faculty
                    if not item.category or normalize(item.category) in {"academic", "academics"}]
        # The API's Abbreviation is authoritative. Name-derived initials are
        # only a fallback when no employee has that explicit abbreviation.
        matches = [item for item in eligible if key and item.initials and normalize(item.initials) == key]
        if not matches:
            matches = [item for item in eligible if key and key in _faculty_identifiers(item)]
        if len(matches) > 1 and department:
            same_department = [item for item in matches if item.department and
                               normalize_department(item.department) == normalize_department(department)]
            if same_department:
                matches = same_department
        item = matches[0] if len(matches) == 1 else None
        result.append(ResolvedFaculty(raw=raw, faculty_id=item.id if item else None, name=item.name if item else None))
    return result


def faculty_department(context: RoutineContext) -> str | None:
    if context.department:
        return context.department
    match = SECTION_DEPARTMENT.match(context.section or "")
    if not match:
        return None
    candidate = match.group(1).strip()
    key = normalize_department(candidate)
    if any(item.department and normalize_department(item.department) == key for item in context.faculty):
        return candidate
    return None


def _faculty_identifiers(item) -> set[str]:
    identifiers = {normalize(alias) for alias in item.aliases}
    if item.initial:
        identifiers.add(normalize(item.initial))
    if item.initials:
        identifiers.add(normalize(item.initials))
    if item.department:
        identifiers.update(normalize_department(item.department) + value for value in tuple(identifiers))
    return identifiers


def subject(raw: str | None, code_raw: str | None, context: RoutineContext) -> ResolvedSubject:
    def output(item=None, method="unresolved"):
        return ResolvedSubject(
            raw=raw, code_raw=code_raw,
            subject_master_id=item.id if item else None,
            code=item.code if item else None,
            name=item.name if item else None,
            category=item.category if item else None,
            match_method=method,
        )

    scoped = scoped_subjects(context)
    if code_raw:
        matches = [item for item in scoped if item.code and normalize(item.code) == normalize(code_raw)]
        if len(matches) == 1:
            return output(matches[0], "code")
        if len(matches) > 1:
            return output(method="ambiguous")
    if raw:
        for field, method in (("aliases", "alias"), ("name", "exact_name")):
            matches = [item for item in scoped if (
                normalize(item.name) == normalize(raw) if field == "name"
                else any(normalize(alias) == normalize(raw) for alias in item.aliases)
            )]
            if len(matches) == 1:
                return output(matches[0], method)
            if len(matches) > 1:
                return output(method="ambiguous")
        # Accept only a clearly unique, near-identical spelling; semantic matching
        # needs a configured embedding index and must never guess an ID.
        scored = sorted(((SequenceMatcher(None, normalize(raw), normalize(item.name)).ratio(), item)
                         for item in scoped), key=lambda pair: pair[0], reverse=True)
        if scored and scored[0][0] >= 0.92 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08):
            return output(scored[0][1], "fuzzy")
    return output()


def scoped_subjects(context: RoutineContext):
    return [item for item in context.subjects
            if (not context.department or not item.stream or normalize_department(context.department) == normalize_department(item.stream))
            and (not context.course or not item.course or normalize(context.course) == normalize(item.course))
            and (not context.semester or not item.semester or normalize_semester(context.semester) == normalize_semester(item.semester))]
