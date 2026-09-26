import re
from difflib import SequenceMatcher

from app.resolvers.matching import normalize, normalize_group, normalize_section
from app.schemas.context import RoutineContext
from app.schemas.routine import ResolvedFaculty, ResolvedGroup, ResolvedSection, ResolvedSubject


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
    result = []
    for raw in raw_values:
        key = normalize(raw)
        scoped = [item for item in context.faculty if not item.department or not context.department
                  or normalize(item.department) == normalize(context.department)]
        matches = [item for item in scoped if item.initials and normalize(item.initials) == key]
        if not matches:
            matches = [item for item in scoped if any(normalize(alias) == key for alias in item.aliases)]
        if not matches:
            matches = [item for item in scoped if key in _faculty_identifiers(item, context.department)]
        item = matches[0] if len(matches) == 1 else None
        result.append(ResolvedFaculty(raw=raw, faculty_id=item.id if item else None, name=item.name if item else None))
    return result


def _faculty_identifiers(item, department: str | None) -> set[str]:
    identifiers = set()
    if item.name:
        words = re.findall(r"[A-Za-z]+", item.name)
        if len(words) >= 2:
            identifiers.add(normalize("".join(word[0] for word in words)))
    if item.initials:
        identifiers.add(normalize(item.initials))
    if department:
        identifiers.update(normalize(department + value) for value in tuple(identifiers))
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

    if code_raw:
        matches = [item for item in context.subjects if item.code and normalize(item.code) == normalize(code_raw)]
        if len(matches) == 1:
            return output(matches[0], "code")
        if len(matches) > 1:
            return output(method="ambiguous")
    if raw:
        for field, method in (("aliases", "alias"), ("name", "exact_name")):
            matches = [item for item in context.subjects if (
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
                         for item in context.subjects), key=lambda pair: pair[0], reverse=True)
        if scored and scored[0][0] >= 0.92 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08):
            return output(scored[0][1], "fuzzy")
    return output()
