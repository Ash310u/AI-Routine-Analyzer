import re

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubjectRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    code: str | None = None
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: str | None = None
    course: str | None = None
    stream: str | None = None
    semester: str | None = None
    course_master_id: int | None = None
    stream_master_id: int | None = None
    semester_master_id: int | None = None


class FacultyRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    initials: str | None = None
    initial: str | None = None
    name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    department: str | None = None
    category: str | None = None

    @model_validator(mode="after")
    def generate_initial(self):
        if self.initial is None and self.name:
            words = re.findall(r"[A-Za-z]+", self.name)
            if len(words) >= 2:
                self.initial = "".join(word[0].upper() for word in words)
        return self


class GroupRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    name: str
    section_id: str | int | None = None
    class_id: str | int | None = None


class SectionRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    name: str
    class_id: str | int | None = None


class RoutineContext(BaseModel):
    subjects: list[SubjectRecord]
    faculty: list[FacultyRecord]
    groups: list[GroupRecord]
    sections: list[SectionRecord]
    department: str | None = None
    section: str | None = None
    course: str | None = None
    semester: str | None = None
    college_id: int | None = None
    session_id: int | None = None
    course_master_id: int | None = None
    stream_master_id: int | None = None
    semester_master_id: int | None = None
