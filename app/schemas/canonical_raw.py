from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ActivityExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_raw: str | None = None
    subject_raw: str | None = None
    subject_code_raw: str | None = None
    subject_type_raw: str | None = None
    faculty_raw: list[str] = Field(default_factory=list)
    room_raw: str | None = None
    notes: str | None = None


class SlotExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str | None = Field(default=None, min_length=1)
    start_period: int | None = Field(default=None, ge=1)
    end_period: int | None = Field(default=None, ge=1)
    start_time: time | None = None
    end_time: time | None = None
    slot_type: Literal["class", "break", "other"] | None = None
    activities: list[ActivityExtraction] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_slot(self):
        if (self.start_period is not None and self.end_period is not None
                and self.start_period > self.end_period):
            raise ValueError("start_period must be before or equal to end_period")
        if (self.start_time is not None and self.end_time is not None
                and self.start_time >= self.end_time):
            raise ValueError("start_time must be before end_time")
        if self.slot_type == "break" and self.activities:
            raise ValueError("break slots cannot have activities")
        return self


class RoutineExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    college: str | None = None
    course: str | None = None
    department: str | None = None
    year: str | None = None
    semester: str | None = None
    section: str | None = None
    default_room: str | None = None
    routine_version: str | None = None
    slots: list[SlotExtraction] = Field(min_length=1)

    @field_validator("college", "course", "department", "year", "semester", "section", mode="before")
    @classmethod
    def metadata_to_string(cls, value):
        return str(value) if isinstance(value, int) else value


class RoutineCollectionExtraction(BaseModel):
    """One document with one or more independently described routines."""

    model_config = ConfigDict(extra="forbid")
    routines: list[RoutineExtraction] = Field(min_length=1)
