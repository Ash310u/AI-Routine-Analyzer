import asyncio
import logging
import re
import time
from contextlib import contextmanager
from uuid import uuid4

from app.clients.master_api import MasterAPI
from app.config import Settings
from app.ingestion.document import DocumentError, image_data_urls
from app.ingestion.spreadsheet import is_excel_workbook, workbook_text
from app.ingestion.spreadsheet_routines import NoRoutineBlocks
from app.ingestion.visual_workbook import VisualWorkbook, VisualWorkbookExtractor, build_workbook
from app.ingestion.workbook_evidence import keep_visible_values
from app.llm.extractor import RoutineExtractor
from app.profiles.converted_workbook import ConvertedWorkbookProfile
from app.profiles.generic import GenericProfile
from app.profiles.tint import TINTProfile
from app.resolvers import resolve
from app.resolvers.subject_embeddings import embedding_subject_matches
from app.schemas.context import RoutineContext
from app.schemas.extraction import RoutineExtraction
from app.schemas.routine import (
    ResolvedActivity, ResolvedRoom, ResolvedSlot, StandardizedDocument, StandardizedRoutine, StandardizedWorkbook,
)
from app.services.output_store import save_converted_workbook


logger = logging.getLogger("uvicorn.error")


@contextmanager
def _stage(run_id: str, name: str):
    started = time.perf_counter()
    logger.info("▶ [%s] %s", run_id, name)
    try:
        yield
    except Exception:
        logger.exception("✗ [%s] %s failed after %.1fs", run_id, name, time.perf_counter() - started)
        raise
    else:
        logger.info("✓ [%s] %s completed in %.1fs", run_id, name, time.perf_counter() - started)


async def process_routine(
    data: bytes, settings: Settings, master_api: MasterAPI, college_id: int, session_id: int,
    source_name: str | None = None,
) -> StandardizedWorkbook | StandardizedDocument:
    run_id = uuid4().hex[:8]
    logger.info("▶ [%s] Routine upload: file=%s college_id=%s session_id=%s",
                run_id, source_name or "<unknown>", college_id, session_id)
    converted_workbook = None
    conversion_reasons = []
    if is_excel_workbook(data):
        with _stage(run_id, "Read workbook and extract routines"):
            try:
                extracted_routines = [TINTProfile.adapt(raw) for raw in TINTProfile.extract(data, settings)]
            except NoRoutineBlocks:
                logger.info("▶ [%s] Workbook needs model-based routine extraction", run_id)
                extracted_routines = await RoutineExtractor(settings, GenericProfile()).extract(
                    [], workbook_text(data, settings),
                )
        result_type = StandardizedWorkbook
    else:
        with _stage(run_id, "Render PDF or image pages"):
            pages = image_data_urls(data, settings)
        parser = RoutineExtractor(settings, ConvertedWorkbookProfile())
        with _stage(run_id, f"Transcribe {len(pages)} page(s) with the model"):
            transcription = await VisualWorkbookExtractor(parser.model).extract(pages)
        with _stage(run_id, "Build and verify converted workbook"):
            converted_workbook = build_workbook(transcription, settings)
        with _stage(run_id, f"Extract routines from {len(transcription.sheets)} transcribed sheet(s)"):
            extracted_routines, conversion_reasons = await _extract_visual_sheets(
                transcription, parser, settings, run_id,
            )
        result_type = StandardizedDocument

    if not extracted_routines:
        raise DocumentError("No routines found in the uploaded document")
    logger.info("✓ [%s] Extracted %d routine(s)", run_id, len(extracted_routines))
    with _stage(run_id, "Load ERP subject and faculty catalogs"):
        context = await master_api.load(extracted_routines[0], college_id)
    context = context.model_copy(update={"session_id": session_id})
    with _stage(run_id, "Resolve ERP parent sections and child groups"):
        classroom_contexts = (await master_api.load_classrooms(extracted_routines, context, college_id, session_id)
                              if hasattr(master_api, "load_classrooms") else [context] * len(extracted_routines))
    with _stage(run_id, "Match remaining subjects with embeddings"):
        embedding_subject_cache = await embedding_subject_matches(
            extracted_routines, context, settings, contexts=classroom_contexts,
        )
    caches = (embedding_subject_cache, {}, {})
    with _stage(run_id, "Resolve section, group, subject, and faculty IDs"):
        routines = [_enrich(item, item_context, caches)
                    for item, item_context in zip(extracted_routines, classroom_contexts, strict=True)]
    result = result_type(
        college_id=college_id, session_id=session_id,
        routine_count=len(routines), routines=routines,
        requires_review=bool(conversion_reasons or any(routine.requires_review for routine in routines)),
    )
    if converted_workbook is not None:
        result.conversion_review_reasons = conversion_reasons
    if converted_workbook is not None and source_name is not None:
        with _stage(run_id, "Save converted workbook"):
            result.converted_workbook_file = str(save_converted_workbook(converted_workbook, source_name, settings))
    logger.info("✓ [%s] Routine processing complete: %d routine(s), requires_review=%s",
                run_id, len(routines), result.requires_review)
    return result


async def _extract_visual_sheets(
    transcription: VisualWorkbook, parser: RoutineExtractor, settings: Settings, run_id: str,
) -> tuple[list[RoutineExtraction], list[str]]:
    # One model request per sheet prevents a long multi-table response from
    # silently dropping the later NSEC sections. Bound concurrent requests.
    limit = asyncio.Semaphore(2)

    async def extract_one(number: int, sheet):
        async with limit:
            with _stage(run_id, f"Extract sheet {number}/{len(transcription.sheets)}"):
                sheet_data = build_workbook(VisualWorkbook(sheets=[sheet]), settings)
                routines = await parser.extract([], workbook_text(sheet_data, settings))
                visible_section = _visible_section(sheet)
                if visible_section and len(routines) == 1:
                    routine = routines[0]
                    stream = visible_section.split(".", 1)[0]
                    # The sheet heading is source evidence. A model may return
                    # only "2A" or mislabel the stream AIML as a course.
                    routines = [routine.model_copy(update={
                        "section": visible_section,
                        "department": routine.department or stream,
                        "course": (None if routine.course and routine.course.casefold() == stream.casefold()
                                   else routine.course),
                    })]
                corrected, reasons = keep_visible_values(routines, [
                    [cell.text for cell in sheet.cells],
                ])
                return corrected, [f"Sheet {number}: {reason}" for reason in reasons]

    results = await asyncio.gather(*(
        extract_one(number, sheet) for number, sheet in enumerate(transcription.sheets, start=1)
    ))
    return ([routine for routines, _ in results for routine in routines],
            [reason for _, reasons in results for reason in reasons])


def _visible_section(sheet) -> str | None:
    labels = {
        f"{match.group(1)}.{match.group(2)}"
        for cell in sheet.cells if cell.row <= 5
        for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9&+/-]*)[._]([1-4][A-Za-z]?)\b", cell.text)
    }
    return next(iter(labels)) if len(labels) == 1 else None


def _enrich(extracted: RoutineExtraction, context: RoutineContext, caches: tuple[dict, dict, dict]) -> StandardizedRoutine:
    context = context.model_copy(update={
        "department": extracted.department, "section": extracted.section,
        "course": extracted.course, "semester": extracted.semester,
    })
    resolved_section = resolve.section(extracted.section, context)
    routine_reasons = []
    if resolved_section.section_id is None:
        routine_reasons.append("Section could not be uniquely resolved")
    subject_cache, faculty_cache, group_cache = caches
    slots = []
    for slot in extracted.slots:
        activities = []
        slot_reasons = []
        if slot.day is None:
            slot_reasons.append("Day could not be read")
        if slot.start_time is None or slot.end_time is None:
            slot_reasons.append("Slot time could not be read")
        if slot.slot_type is None:
            slot_reasons.append("Slot type could not be determined")
        seen_groups: set[str | int | None] = set()
        for activity in slot.activities:
            group_key_raw = (context.college_id, extracted.course, extracted.department,
                             extracted.semester, resolved_section.section_id,
                             extracted.section, activity.group_raw)
            subject_key = (extracted.department, extracted.course, extracted.semester,
                           extracted.section, activity.subject_raw, activity.subject_code_raw,
                           activity.subject_type_raw)
            faculty_key = (resolve.faculty_department(context), tuple(activity.faculty_raw))
            if group_key_raw not in group_cache:
                group_cache[group_key_raw] = resolve.group(activity.group_raw, context)
            if subject_key not in subject_cache:
                subject_cache[subject_key] = resolve.subject(
                    activity.subject_raw, activity.subject_code_raw, context, activity.subject_type_raw,
                )
            if faculty_key not in faculty_cache:
                faculty_cache[faculty_key] = resolve.faculty(activity.faculty_raw, context)
            resolved_group = group_cache[group_key_raw]
            resolved_subject = subject_cache[subject_key]
            resolved_faculty = faculty_cache[faculty_key]
            reasons = []
            if resolved_subject.subject_master_id is None:
                reasons.append("Subject could not be uniquely resolved")
            elif resolved_subject.match_method == "acronym":
                reasons.append("Subject matched by generated acronym; verify the suggested ID")
            elif resolved_subject.match_method == "name_abbreviation":
                reasons.append("Subject matched by abbreviated name; verify the suggested ID")
            elif resolved_subject.match_method == "embedding":
                reasons.append("Subject matched semantically; verify the suggested ID")
            if resolved_group is not None and resolved_group.group_id is None:
                reasons.append("Group could not be uniquely resolved")
            if any(item.faculty_id is None for item in resolved_faculty):
                reasons.append("Faculty initials could not be uniquely resolved")
            if resolved_section.section_id is None:
                reasons.append("Section could not be uniquely resolved")
            group_key = resolved_group.group_id if resolved_group else None
            if group_key is not None and group_key in seen_groups:
                reasons.append("Multiple activities for the same group in one slot")
            seen_groups.add(group_key)
            room = activity.room_raw or extracted.default_room
            activities.append(ResolvedActivity(
                group=resolved_group, subject=resolved_subject, faculty=resolved_faculty,
                room=ResolvedRoom(raw=room), subject_type_raw=activity.subject_type_raw,
                notes=activity.notes, confidence=1.0 if not reasons else 0.0,
                requires_review=bool(reasons), review_reasons=reasons,
            ))
        if slot.slot_type == "class" and not activities:
            slot_reasons.append("Class slot has no activities")
        if len(activities) > 1 and any(item.group is None for item in activities):
            slot_reasons.append("Whole-section activity overlaps another activity in the same slot")
        slots.append(ResolvedSlot(
            college_id=context.college_id, session_id=context.session_id,
            course_master_id=context.course_master_id,
            stream_master_id=context.stream_master_id,
            semester_master_id=context.semester_master_id,
            section=resolved_section,
            day=slot.day, start_period=slot.start_period, end_period=slot.end_period,
            start_time=slot.start_time, end_time=slot.end_time,
            slot_type=slot.slot_type, activities=activities, review_reasons=slot_reasons,
        ))
    _flag_overlapping_activities(slots)
    return StandardizedRoutine(
        college_id=context.college_id,
        session_id=context.session_id,
        course_master_id=context.course_master_id,
        stream_master_id=context.stream_master_id,
        semester_master_id=context.semester_master_id,
        college=extracted.college, course=extracted.course,
        department=extracted.department, year=extracted.year,
        semester=extracted.semester, section=resolved_section,
        default_room=extracted.default_room, routine_version=extracted.routine_version,
        slots=slots,
        requires_review=bool(routine_reasons or any(
            slot.review_reasons or any(activity.requires_review for activity in slot.activities)
            for slot in slots
        )),
        review_reasons=routine_reasons,
    )


def _flag_overlapping_activities(slots: list[ResolvedSlot]) -> None:
    by_day: dict[str, list[ResolvedSlot]] = {}
    for slot in slots:
        if not slot.day or not slot.start_time or not slot.end_time or slot.slot_type != "class":
            continue
        for previous in by_day.get(slot.day, []):
            if slot.start_time >= previous.end_time or previous.start_time >= slot.end_time:
                continue
            for activity in slot.activities:
                for earlier in previous.activities:
                    group = activity.group.group_id if activity.group else None
                    earlier_group = earlier.group.group_id if earlier.group else None
                    if group is not None and earlier_group is not None and group != earlier_group:
                        continue
                    for item in (activity, earlier):
                        reason = "Overlapping activity for the same group or whole section"
                        if reason not in item.review_reasons:
                            item.review_reasons.append(reason)
                        item.requires_review = True
                        item.confidence = 0.0
        by_day.setdefault(slot.day, []).append(slot)
