"""Persist successful standardized routines as private JSON files."""

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.schemas.routine import StandardizedDocument, StandardizedWorkbook


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def save_routine(routine: StandardizedWorkbook | StandardizedDocument, source_name: str | None, settings: Settings) -> Path:
    directory = Path(settings.output_dir)
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    directory.mkdir(parents=True, exist_ok=True)

    source = (source_name or "routine").replace("\\", "/").split("/")[-1]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(source).stem).strip("_")[:80] or "routine"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"{stem}-{timestamp}-{uuid4().hex[:8]}.json"

    routine.output_file = str(target)
    payload = json.dumps(routine.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".routine-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target
