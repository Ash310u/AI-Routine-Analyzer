from pydantic import BaseModel, ConfigDict, Field


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


class FacultyRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    initials: str | None = None
    name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    department: str | None = None


class GroupRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    name: str
    section_id: str | int | None = None


class SectionRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    name: str


class RoutineContext(BaseModel):
    subjects: list[SubjectRecord]
    faculty: list[FacultyRecord]
    groups: list[GroupRecord]
    sections: list[SectionRecord]
    department: str | None = None
    section: str | None = None
    course: str | None = None
    semester: str | None = None
