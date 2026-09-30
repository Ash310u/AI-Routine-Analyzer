import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from app.clients.classroom_api import _stream_names, match_parent, query_scopes
from app.config import Settings
from app.resolvers.matching import normalize_department
from app.schemas.context import FacultyRecord, GroupRecord, RoutineContext, SectionRecord, SubjectRecord
from app.schemas.extraction import RoutineExtraction


logger = logging.getLogger("uvicorn.error")


class MasterDataError(ValueError):
    pass


T = TypeVar("T")


def _rows(payload: Any, kind: str) -> list[dict]:
    """Unwrap common public API envelopes without silently accepting unknown ones."""
    for _ in range(3):
        if isinstance(payload, list):
            if not all(isinstance(row, dict) for row in payload):
                raise MasterDataError(f"{kind} API returned non-object rows")
            return payload
        if not isinstance(payload, dict):
            break
        key = next((key for key in ("data", "items", "results", "employees", "subjects", "groups", "sections") if key in payload), None)
        if key is None:
            break
        payload = payload[key]
    raise MasterDataError(f"{kind} API response needs a JSON array or a known data envelope")


def _field(row: dict, *names: str, required: bool = False):
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    if required:
        raise MasterDataError(f"Missing field; expected one of: {', '.join(names)}")
    return None


def _subjects(payload: Any) -> list[SubjectRecord]:
    result = []
    for row in _rows(payload, "Subject"):
        aliases = _field(row, "aliases", "Aliases", "alias", "Alias") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        result.append(SubjectRecord.model_validate({
            "id": _field(row, "SubjectMasterId", "id", "subject_id", "subject_master_id", required=True),
            "code": _field(row, "Code", "code", "subject_code", "paper_code"),
            "name": _field(row, "Name", "name", "subject_name", "paper_name", required=True),
            "aliases": aliases,
            "category": _field(row, "SubjectType", "category", "subject_category", "category_name", "type"),
            "course": _field(row, "Course", "course"),
            "stream": _field(row, "Stream", "stream", "department"),
            "semester": _field(row, "Semester", "semester"),
            "course_master_id": _field(row, "CourseMasterId", "course_master_id"),
            "stream_master_id": _field(row, "StreamMasterId", "stream_master_id"),
            "semester_master_id": _field(row, "SemesterMasterId", "semester_master_id"),
        }))
    return result


def _faculty(payload: Any) -> list[FacultyRecord]:
    result = []
    for row in _rows(payload, "Employee"):
        aliases = _field(row, "aliases", "Aliases", "alias") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        result.append(FacultyRecord.model_validate({
            "id": _field(row, "EmployeeId", "id", "employee_id", "faculty_id", required=True),
            "initials": _field(row, "Abbreviation", "initials", "faculty_initials", "short_name", "employee_code"),
            "name": _field(row, "EmployeeName", "name", "employee_name", "faculty_name", "full_name"),
            "aliases": aliases,
            # Employee "Department" is an HR category (e.g. Academics/Admin);
            # Stream is the teaching department used by timetable routines.
            "department": _field(row, "Stream", "stream", "department_name"),
            "category": _field(row, "Department", "department"),
        }))
    return result


def _groups(payload: Any) -> list[GroupRecord]:
    return [GroupRecord.model_validate({
        "id": _field(row, "GroupId", "id", "group_id", required=True),
        "name": _field(row, "Name", "name", "group_name", required=True),
        "section_id": _field(row, "SectionId", "section_id"),
    }) for row in _rows(payload, "Group")]


def _sections(payload: Any) -> list[SectionRecord]:
    return [SectionRecord.model_validate({
        "id": _field(row, "SectionId", "id", "section_id", required=True),
        "name": _field(row, "Name", "name", "section_name", required=True),
    }) for row in _rows(payload, "Section")]


def _parent_classes(payload: Any, college_id: int, session_id: int,
                    scope: tuple[int, int, int]) -> list[SectionRecord]:
    result = []
    for row in _rows(payload, "Parent class"):
        if (row.get("COLLEGE_MASTER_ID") != college_id
                or row.get("SESSION_MASTER_ID") != session_id
                or tuple(row.get(key) for key in (
                    "COURSE_MASTER_ID", "STREAM_MASTER_ID", "SEMESTER_MASTER_ID")) != scope):
            continue
        result.append(SectionRecord.model_validate({
            "id": _field(row, "ID", required=True),
            "class_id": _field(row, "ClassId", required=True),
            "name": _field(row, "ClassName", required=True),
        }))
    return result


def _child_classes(payload: Any, parent_id: str | int, college_id: int) -> list[GroupRecord]:
    result = []
    for row in _rows(payload, "Child class"):
        if (str(row.get("PARENT_CLASS_MASTER_ID")) != str(parent_id)
                or row.get("COLLEGE_MASTER_ID") != college_id):
            continue
        result.append(GroupRecord.model_validate({
            "id": _field(row, "ID", required=True),
            "class_id": _field(row, "ClassId", required=True),
            "name": _field(row, "ClassName", required=True),
            "section_id": parent_id,
        }))
    return result


class MasterAPI:
    """Shared server client: one fetch per URL on cache miss, then local matching."""

    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {}
        if settings.master_api_key:
            prefix = settings.master_api_auth_scheme.strip()
            headers[settings.master_api_auth_header] = (
                f"{prefix} {settings.master_api_key}" if prefix else settings.master_api_key
            )
        self.client = httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=headers)
        self._cache: dict[str, tuple[float, list[Any]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _get(self, url: str, kind: str, parser: Callable[[Any], list[T]]) -> list[T]:
        entry = self._cache.get(url)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            entry = self._cache.get(url)
            if entry and entry[0] > time.monotonic():
                return entry[1]
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                records = parser(response.json())
            except (httpx.HTTPError, ValueError, ValidationError) as exc:
                raise MasterDataError(f"Unable to load {kind} from {url}: {exc}") from exc
            self._cache[url] = (time.monotonic() + self.settings.master_cache_ttl_seconds, records)
            return records

    @staticmethod
    def _college_url(base_url: str, college_id: int) -> str:
        # A base URL may contain stale query parameters from an older config.
        # Only the requested college ID is sent to the master-data API.
        return str(httpx.URL(base_url).copy_with(query=None).copy_merge_params({"college_id": college_id}))

    async def load(self, routine: RoutineExtraction, college_id: int) -> RoutineContext:
        if not self.settings.subject_api_base_url or not self.settings.faculty_api_base_url:
            raise MasterDataError("Set SUBJECT_API_BASE_URL and FACULTY_API_BASE_URL in .env")
        if college_id < 1:
            raise MasterDataError("college_id must be a positive integer")
        subject_url = self._college_url(self.settings.subject_api_base_url, college_id)
        faculty_url = self._college_url(self.settings.faculty_api_base_url, college_id)
        group_url = self._college_url(self.settings.group_api_base_url, college_id) if self.settings.group_api_base_url else ""
        section_url = self._college_url(self.settings.section_api_base_url, college_id) if self.settings.section_api_base_url else ""
        subjects, faculty, groups, sections = await asyncio.gather(
            self._get(subject_url, "subjects", _subjects),
            self._get(faculty_url, "employees", _faculty),
            self._get(group_url, "groups", _groups) if group_url else asyncio.sleep(0, result=[]),
            self._get(section_url, "sections", _sections) if section_url else asyncio.sleep(0, result=[]),
        )
        return RoutineContext(subjects=subjects, faculty=faculty, groups=groups, sections=sections,
                              department=routine.department, section=routine.section,
                              course=routine.course, semester=routine.semester, college_id=college_id)

    async def load_classrooms(self, routines: list[RoutineExtraction], base: RoutineContext,
                              college_id: int, session_id: int) -> list[RoutineContext]:
        """Resolve each routine independently after the shared subject catalog is ready."""
        if session_id < 1:
            raise MasterDataError("session_id must be a positive integer")
        if not self.settings.parent_class_api_url or not self.settings.child_class_api_url:
            raise MasterDataError("Set PARENT_CLASS_API_URL and CHILD_CLASS_API_URL in .env")
        base = base.model_copy(update={"session_id": session_id})
        return await asyncio.gather(*(
            self._classroom_context(routine, base, college_id, session_id) for routine in routines
        ))

    async def _classroom_context(self, routine: RoutineExtraction, base: RoutineContext,
                                 college_id: int, session_id: int) -> RoutineContext:
        scopes = query_scopes(routine, base.subjects)
        if len(scopes) == 1:
            scope = next(iter(scopes))
            base = base.model_copy(update={
                "course_master_id": scope[0], "stream_master_id": scope[1],
                "semester_master_id": scope[2],
            })
        if not scopes:
            logger.info("✓ ERP classrooms: no course/stream/semester scope for section=%s; lookup skipped",
                        routine.section)
            return base.model_copy(update={"sections": [], "groups": []})
        async def fetch_parent(scope: tuple[int, int, int]) -> list[SectionRecord]:
            url = str(httpx.URL(self.settings.parent_class_api_url).copy_with(query=None).copy_merge_params({
                "sessionId": session_id, "courseId": scope[0],
                "streamId": scope[1], "semesterId": scope[2],
            }))
            return await self._get(url, "parent classes", lambda payload: _parent_classes(
                payload, college_id, session_id, scope,
            ))
        ordered_scopes = sorted(scopes)
        logger.info("▶ ERP parent classes: section=%s session_id=%s scopes=%s",
                    routine.section, session_id, ordered_scopes)
        started = time.perf_counter()
        parent_lists = await asyncio.gather(*(fetch_parent(scope) for scope in ordered_scopes))
        logger.info("✓ ERP parent classes: section=%s candidates=%d elapsed=%.1fs",
                    routine.section, sum(map(len, parent_lists)), time.perf_counter() - started)
        candidates = [(scope, matched) for scope, parents in zip(ordered_scopes, parent_lists, strict=True)
                      if (matched := match_parent(routine, parents, _stream_names(routine))) is not None]
        if not candidates and (not routine.section
                               or normalize_department(routine.section) in _stream_names(routine)):
            # A timetable sometimes names only its stream. The sole parent in the
            # fully scoped ERP result then identifies its whole class unambiguously.
            all_parents = [(scope, parent) for scope, parents in zip(ordered_scopes, parent_lists, strict=True)
                           for parent in parents]
            if len(all_parents) == 1:
                candidates = all_parents
        if len(candidates) != 1:
            logger.info("✓ ERP child classes: section=%s skipped; matching parent count=%d",
                        routine.section, len(candidates))
            return base.model_copy(update={"sections": [], "groups": []})
        scope, parent = candidates[0]
        url = str(httpx.URL(self.settings.child_class_api_url).copy_with(query=None).copy_merge_params({
            "parentClassId": parent.id,
        }))
        logger.info("▶ ERP child classes: section=%s parent_id=%s", routine.section, parent.id)
        started = time.perf_counter()
        children = await self._get(url, "child classes", lambda payload: _child_classes(
            payload, parent.id, college_id,
        ))
        logger.info("✓ ERP child classes: section=%s groups=%d elapsed=%.1fs",
                    routine.section, len(children), time.perf_counter() - started)
        return base.model_copy(update={
            "sections": [parent], "groups": children,
            "course_master_id": scope[0], "stream_master_id": scope[1],
            "semester_master_id": scope[2],
        })
