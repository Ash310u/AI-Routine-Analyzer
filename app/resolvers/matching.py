import re
import unicodedata


def normalize(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", "", value)


def normalize_group(value: str | None) -> str:
    normalized = normalize(value)
    return re.sub(r"^(group|grp|gr)", "", normalized)


def normalize_section(value: str | None) -> str:
    return re.sub(r"^(section|sec)", "", normalize(value))


def normalize_department(value: str | None) -> str:
    return re.sub(r"^(departmentof|deptof|department|dept)", "", normalize(value))


def normalize_semester(value: str | None) -> str:
    return re.sub(r"(semester|sem)$", "", normalize(value))
