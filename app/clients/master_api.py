import asyncio
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas.context import FacultyRecord, GroupRecord, RoutineContext, SectionRecord, SubjectRecord
from app.schemas.extraction import RoutineExtraction


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
        aliases = _field(row, "aliases", "alias") or []
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
