import re
from difflib import SequenceMatcher

from app.resolvers.matching import normalize, normalize_department, normalize_group, normalize_section, normalize_semester
from app.schemas.context import RoutineContext
from app.schemas.routine import ResolvedFaculty, ResolvedGroup, ResolvedSection, ResolvedSubject


SECTION_DEPARTMENT = re.compile(r"^\s*([A-Za-z][A-Za-z0-9&+ /-]*?)\s*[._]\s*\d")


def section(raw: str | None, context: RoutineContext) -> ResolvedSection:
    matches = [item for item in context.sections if normalize_section(item.name) == normalize_section(raw)] if raw else []
    if not matches and len(context.sections) == 1 and context.sections[0].class_id is not None:
        # The classroom client already matched this parent using routine scope.
        matches = context.sections
    item = matches[0] if len(matches) == 1 else None
    return ResolvedSection(raw=raw, section_id=item.id if item else None,
                           name=item.name if item else None, class_id=item.class_id if item else None)


def group(raw: str | None, context: RoutineContext) -> ResolvedGroup | None:
    if raw is None:
        return None
    section_ids = {str(item.id) for item in context.sections
                   if normalize_section(item.name) == normalize_section(context.section)}
    if not section_ids and len(context.sections) == 1 and context.sections[0].class_id is not None:
        section_ids = {str(context.sections[0].id)}
    matches = [item for item in context.groups if normalize_group(item.name.rsplit(":", 1)[-1]) == normalize_group(raw)
               and (item.section_id is None or str(item.section_id) in section_ids)]
    item = matches[0] if len(matches) == 1 else None
    return ResolvedGroup(raw=raw, group_id=item.id if item else None,
                         parent_class_master_id=item.section_id if item and item.class_id is not None else None,
                         name=item.name if item else None, class_id=item.class_id if item else None)


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
            same_department = [item for item in matches if _faculty_teaches_department(item.department, department)]
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
    if any(_faculty_teaches_department(item.department, candidate) for item in context.faculty):
        return candidate
    return None


def _faculty_teaches_department(stream: str | None, department: str) -> bool:
    """Match a whole department within an ERP multi-stream value such as AIML + CSE."""
    target = normalize_department(department)
    return bool(target) and any(normalize_department(part) == target for part in (stream or "").split("+"))


def _faculty_identifiers(item) -> set[str]:
    identifiers = {normalize(alias) for alias in item.aliases}
    if item.initial:
        identifiers.add(normalize(item.initial))
    if item.initials:
        identifiers.add(normalize(item.initials))
    if item.department:
        identifiers.update(normalize_department(item.department) + value for value in tuple(identifiers))
    return identifiers


def subject(raw: str | None, code_raw: str | None, context: RoutineContext,
            subject_type_raw: str | None = None) -> ResolvedSubject:
    def output(item=None, method="unresolved"):
        return ResolvedSubject(
            raw=raw, code_raw=code_raw,
            subject_master_id=item.id if item else None,
            code=item.code if item else None,
            name=item.name if item else None,
            category=item.category if item else None,
            match_method=method,
        )

    def choose(matches, method):
        if not matches:
            return None
        if len(matches) == 1:
            return output(matches[0], method)
        # A visible lab label is already applied in scoped_subjects. Without
        # one, an otherwise identical theory row is the unique lecture match.
        if raw and not re.search(r"\b(?:lab|laboratory|practical)\b", f"{raw} {subject_type_raw or ''}", re.I):
            theory = [item for item in matches if not item.category or not
                      re.search(r"\b(?:lab|laboratory|practical)\b", item.category, re.I)]
            if len(theory) == 1:
                return output(theory[0], method)
        return output(method="ambiguous")

    scoped = scoped_subjects(context)
    if code_raw:
        matches = [item for item in scoped if item.code and normalize(item.code) == normalize(code_raw)]
        if result := choose(matches, "code"):
            return result
    if raw:
        scoped = scoped_subjects(context, raw, subject_type_raw)
        raw_name = _subject_name_key(raw)
        for field, method in (("aliases", "alias"), ("name", "exact_name")):
            matches = [item for item in scoped if (
                _subject_name_key(item.name) == raw_name if field == "name"
                else any(_subject_name_key(alias) == raw_name for alias in item.aliases)
            )]
            if result := choose(matches, method):
                return result
        matches = [item for item in scoped if normalize(raw) in _subject_acronyms(item)]
        if result := choose(matches, "acronym"):
            return result
        parenthetical = re.fullmatch(r"\s*(.+?)\s*\([^)]*\)\s*", raw)
        if parenthetical and len(parenthetical.group(1).split()) >= 2:
            prefix = _subject_name_key(parenthetical.group(1))
            matches = [item for item in scoped if _subject_name_key(item.name).startswith(prefix)]
            if result := choose(matches, "name_abbreviation"):
                return result
        if len(raw.split()) >= 2:
            matches = [item for item in scoped if _subject_name_key(item.name).startswith(raw_name)]
            if result := choose(matches, "name_abbreviation"):
                return result
        matches = [item for item in scoped if _abbreviated_name_match(raw, item.name)]
        if result := choose(matches, "name_abbreviation"):
            return result
        # Accept only a clearly unique, near-identical spelling; semantic matching
        # needs a configured embedding index and must never guess an ID.
        scored = sorted(((SequenceMatcher(None, normalize(raw), normalize(item.name)).ratio(), item)
                         for item in scoped), key=lambda pair: pair[0], reverse=True)
        if scored and scored[0][0] >= 0.92 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08):
            return output(scored[0][1], "fuzzy")
    return output()


def _subject_acronyms(item) -> set[str]:
    words = re.findall(r"[A-Za-z]+", item.name)
    words = [word for word in words if word.casefold() not in {"and", "of", "the", "with", "for"}]
    is_lab = bool(item.category and re.search(r"\b(?:lab|laboratory|practical)\b", item.category, re.I))
    subject_words = [word for word in words if word.casefold() not in {"lab", "laboratory"}]
    if len(subject_words) < 2:
        return set()
    initialism = "".join(word[0] for word in subject_words)
    forms = {normalize(initialism)}
    forms.add(normalize("".join(word[0] for word in re.findall(r"[A-Za-z]+", item.name))))
    if len(subject_words) > 2 and subject_words[0].casefold() == "introduction":
        remainder = [word for word in subject_words[1:] if word.casefold() != "to"]
        if len(remainder) >= 2:
            forms.add(normalize("".join(word[0] for word in remainder)))
    if is_lab:
        forms.add(normalize(initialism + " Lab"))
    return forms


def _subject_name_key(value: str) -> str:
    return normalize(value.replace("&", " and "))


def _abbreviated_name_match(raw: str, name: str) -> bool:
    """Match visible word prefixes only when they identify one scoped catalog row."""
    ignored = {"and", "of", "the", "to", "for", "lab", "laboratory"}
    words = [word.casefold() for word in re.findall(r"[A-Za-z]+", raw.replace("&", " and "))
             if word.casefold() not in ignored]
    catalog = [word.casefold() for word in re.findall(r"[A-Za-z]+", name.replace("&", " and "))
               if word.casefold() not in ignored]
    if not words or any(len(word) < 3 for word in words):
        return False
    return any(all(candidate.startswith(word) for word, candidate in zip(words, catalog[start:], strict=False))
               for start in range(len(catalog) - len(words) + 1))


def scoped_subjects(context: RoutineContext, raw: str | None = None,
                    subject_type_raw: str | None = None):
    department = context.department
    if not department:
        match = SECTION_DEPARTMENT.match(context.section or "")
        if match and any(item.stream and normalize_department(item.stream) == normalize_department(match.group(1))
                         for item in context.subjects):
            department = match.group(1)
    candidates = [item for item in context.subjects
            if (item.stream_master_id == context.stream_master_id if context.stream_master_id is not None
                else not department or not item.stream or normalize_department(department) == normalize_department(item.stream))
            and (item.course_master_id == context.course_master_id if context.course_master_id is not None
                 else not context.course or not item.course or normalize(context.course) == normalize(item.course))
            and (item.semester_master_id == context.semester_master_id if context.semester_master_id is not None
                 else not context.semester or not item.semester or normalize_semester(context.semester) == normalize_semester(item.semester))]
    is_lab = bool(re.search(r"\b(?:lab|laboratory|practical)\b", f"{raw or ''} {subject_type_raw or ''}", re.I))
    if is_lab:
        labs = [item for item in candidates if item.category and
                re.search(r"\b(?:lab|laboratory|practical)\b", item.category, re.I)]
        if labs:
            return labs
    return candidates
