from app.clients.master_api import MasterAPI
from app.config import Settings
from app.ingestion.document import image_data_urls
from app.ingestion.spreadsheet import is_excel_workbook, workbook_text
from app.ingestion.spreadsheet_routines import NoRoutineBlocks
from app.llm.extractor import RoutineExtractor
from app.profiles.generic import GenericProfile
from app.profiles.nsec import NSECProfile
from app.profiles.tint import TINTProfile
from app.resolvers import resolve
from app.schemas.context import RoutineContext
from app.schemas.extraction import RoutineExtraction
from app.schemas.routine import (
    ResolvedActivity, ResolvedRoom, ResolvedSlot, StandardizedDocument, StandardizedRoutine, StandardizedWorkbook,
)


async def process_routine(
    data: bytes, settings: Settings, master_api: MasterAPI,
) -> StandardizedRoutine | StandardizedWorkbook | StandardizedDocument:
    if is_excel_workbook(data):
        try:
            extracted_routines = [TINTProfile.adapt(raw) for raw in TINTProfile.extract(data, settings)]
        except NoRoutineBlocks:
            extracted = await RoutineExtractor(settings, GenericProfile()).extract([], workbook_text(data, settings))
        else:
            context = await master_api.load(extracted_routines[0])
            caches = ({}, {}, {})
            routines = [_enrich(item, context, caches) for item in extracted_routines]
            return StandardizedWorkbook(
                routine_count=len(routines), routines=routines,
                requires_review=any(routine.requires_review for routine in routines),
            )
        if isinstance(extracted, list):
            context = await master_api.load(extracted[0], profile="generic")
            routines = [_enrich(item, context, ({}, {}, {})) for item in extracted]
            return StandardizedWorkbook(routine_count=len(routines), routines=routines,
                                        requires_review=any(item.requires_review for item in routines))
        context = await master_api.load(extracted, profile="generic")
        return _enrich(extracted, context, ({}, {}, {}))
    pages = image_data_urls(data, settings)
    extracted = await RoutineExtractor(settings, NSECProfile()).extract(pages, None)
    if isinstance(extracted, list):
        context = await master_api.load(extracted[0], profile="nsec")
        caches = ({}, {}, {})
        routines = [_enrich(item, context, caches) for item in extracted]
        return StandardizedDocument(routine_count=len(routines), routines=routines,
                                    requires_review=any(item.requires_review for item in routines))
    context = await master_api.load(extracted, profile="nsec")
    return _enrich(extracted, context, ({}, {}, {}))


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
            group_key_raw = (extracted.section, activity.group_raw)
            subject_key = (extracted.department, extracted.course, extracted.semester,
                           activity.subject_raw, activity.subject_code_raw)
            faculty_key = (extracted.department, tuple(activity.faculty_raw))
            if group_key_raw not in group_cache:
                group_cache[group_key_raw] = resolve.group(activity.group_raw, context)
            if subject_key not in subject_cache:
                subject_cache[subject_key] = resolve.subject(activity.subject_raw, activity.subject_code_raw, context)
            if faculty_key not in faculty_cache:
                faculty_cache[faculty_key] = resolve.faculty(activity.faculty_raw, context)
            resolved_group = group_cache[group_key_raw]
            resolved_subject = subject_cache[subject_key]
            resolved_faculty = faculty_cache[faculty_key]
            reasons = []
            if resolved_subject.subject_master_id is None:
                reasons.append("Subject could not be uniquely resolved")
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
            day=slot.day, start_period=slot.start_period, end_period=slot.end_period,
            start_time=slot.start_time, end_time=slot.end_time,
            slot_type=slot.slot_type, activities=activities, review_reasons=slot_reasons,
        ))
    _flag_overlapping_activities(slots)
    return StandardizedRoutine(
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
