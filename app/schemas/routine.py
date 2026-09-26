from datetime import time
from typing import Literal

from pydantic import BaseModel, Field


class ResolvedSection(BaseModel):
    raw: str | None
    section_id: str | int | None = None
    name: str | None = None


class ResolvedGroup(BaseModel):
    raw: str
    group_id: str | int | None = None
    name: str | None = None


class ResolvedSubject(BaseModel):
    raw: str | None
    code_raw: str | None = None
    subject_master_id: str | int | None = None
    code: str | None = None
    name: str | None = None
    category: str | None = None
    match_method: Literal["code", "alias", "exact_name", "fuzzy", "unresolved", "ambiguous"]


class ResolvedFaculty(BaseModel):
    raw: str
    faculty_id: str | int | None = None
    name: str | None = None


class ResolvedRoom(BaseModel):
    raw: str | None = None
    room_id: str | int | None = None


class ResolvedActivity(BaseModel):
    group: ResolvedGroup | None
    subject: ResolvedSubject
    faculty: list[ResolvedFaculty]
    room: ResolvedRoom
    subject_type_raw: str | None = None
    notes: str | None = None
    confidence: float = Field(ge=0, le=1)
    requires_review: bool
    review_reasons: list[str]


class ResolvedSlot(BaseModel):
    day: str | None
    start_period: int | None = Field(default=None, ge=1)
    end_period: int | None = Field(default=None, ge=1)
    start_time: time | None
    end_time: time | None
    slot_type: Literal["class", "break", "other"] | None
    activities: list[ResolvedActivity]
    review_reasons: list[str] = Field(default_factory=list)


class StandardizedRoutine(BaseModel):
    college: str | None
    course: str | None
    department: str | None
    year: str | None
    semester: str | None
    section: ResolvedSection
    default_room: str | None
    routine_version: str | None
    slots: list[ResolvedSlot]
    requires_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    output_file: str | None = None


class StandardizedWorkbook(BaseModel):
    source_type: Literal["workbook"] = "workbook"
    routine_count: int
    routines: list[StandardizedRoutine]
    requires_review: bool
    output_file: str | None = None
