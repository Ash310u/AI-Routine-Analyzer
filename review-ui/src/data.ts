export type Id = string | number | null;

export interface Faculty {
  raw?: string | null;
  faculty_id?: Id;
  name?: string | null;
}

export interface Activity {
  group?: { raw?: string | null; group_id?: Id; name?: string | null } | null;
  subject?: {
    raw?: string | null;
    code_raw?: string | null;
    subject_master_id?: Id;
    code?: string | null;
    name?: string | null;
    category?: string | null;
    match_method?: string | null;
  } | null;
  faculty?: Faculty[];
  room?: { raw?: string | null; room_id?: Id } | null;
  subject_type_raw?: string | null;
  notes?: string | null;
  confidence?: number | null;
  requires_review?: boolean;
  review_reasons?: string[];
}

export interface Slot {
  day?: string | null;
  start_period?: number | null;
  end_period?: number | null;
  start_time?: string | null;
  end_time?: string | null;
  slot_type?: string | null;
  activities?: Activity[];
  review_reasons?: string[];
}

export interface Routine {
  college_id?: number | null;
  college?: string | null;
  course?: string | null;
  department?: string | null;
  year?: string | null;
  semester?: string | null;
  section?: {
    raw?: string | null;
    section_id?: Id;
    name?: string | null;
  } | null;
  default_room?: string | null;
  routine_version?: string | null;
  slots: Slot[];
  requires_review?: boolean;
  review_reasons?: string[];
}

export interface RoutineRow {
  key: string;
  routine: Routine;
  slot: Slot;
  activity: Activity | null;
  routineIndex: number;
  slotIndex: number;
  activityIndex: number | null;
  reasons: string[];
  requiresReview: boolean;
}

export interface Dataset {
  raw: unknown;
  label: string;
  sourceType: string;
  collegeId: number | null;
  routines: Routine[];
  rows: RoutineRow[];
}

export type FieldState = "any" | "present" | "missing";
export type ActualFieldState = Exclude<FieldState, "any"> | "na";

export interface FieldSpec {
  id: string;
  label: string;
  section: "Routine" | "Schedule" | "Activity" | "Master IDs";
  get: (row: RoutineRow) => unknown;
  applies?: (row: RoutineRow) => boolean;
  description?: string;
}

const hasActivity = (row: RoutineRow) => row.activity !== null;
const hasGroup = (row: RoutineRow) => row.activity?.group != null;
const hasFaculty = (row: RoutineRow) => Boolean(row.activity?.faculty?.length);

export const fields: FieldSpec[] = [
  {
    id: "college_id",
    label: "College ID",
    section: "Routine",
    get: (row) => row.routine.college_id,
  },
  {
    id: "college",
    label: "College name",
    section: "Routine",
    get: (row) => row.routine.college,
  },
  {
    id: "course",
    label: "Course",
    section: "Routine",
    get: (row) => row.routine.course,
  },
  {
    id: "department",
    label: "Department",
    section: "Routine",
    get: (row) => row.routine.department,
  },
  {
    id: "year",
    label: "Year",
    section: "Routine",
    get: (row) => row.routine.year,
  },
  {
    id: "semester",
    label: "Semester",
    section: "Routine",
    get: (row) => row.routine.semester,
  },
  {
    id: "section.raw",
    label: "Section raw",
    section: "Routine",
    get: (row) => row.routine.section?.raw,
  },
  {
    id: "section.id",
    label: "Section ID",
    section: "Master IDs",
    get: (row) => row.routine.section?.section_id,
  },
  {
    id: "section.name",
    label: "Section name",
    section: "Routine",
    get: (row) => row.routine.section?.name,
  },
  {
    id: "default_room",
    label: "Default room",
    section: "Routine",
    get: (row) => row.routine.default_room,
  },
  {
    id: "routine_version",
    label: "Routine version",
    section: "Routine",
    get: (row) => row.routine.routine_version,
  },
  {
    id: "routine.requires_review",
    label: "Routine review flag",
    section: "Routine",
    get: (row) => row.routine.requires_review,
  },
  {
    id: "routine.review_reasons",
    label: "Routine review reasons",
    section: "Routine",
    get: (row) => row.routine.review_reasons,
  },
  { id: "day", label: "Day", section: "Schedule", get: (row) => row.slot.day },
  {
    id: "start_period",
    label: "Start period",
    section: "Schedule",
    get: (row) => row.slot.start_period,
  },
  {
    id: "end_period",
    label: "End period",
    section: "Schedule",
    get: (row) => row.slot.end_period,
  },
  {
    id: "start_time",
    label: "Start time",
    section: "Schedule",
    get: (row) => row.slot.start_time,
  },
  {
    id: "end_time",
    label: "End time",
    section: "Schedule",
    get: (row) => row.slot.end_time,
  },
  {
    id: "slot_type",
    label: "Slot type",
    section: "Schedule",
    get: (row) => row.slot.slot_type,
  },
  {
    id: "slot.review_reasons",
    label: "Slot review reasons",
    section: "Schedule",
    get: (row) => row.slot.review_reasons,
  },
  {
    id: "group.raw",
    label: "Group raw",
    section: "Activity",
    get: (row) => row.activity?.group?.raw,
    applies: hasGroup,
    description:
      "Whole-section classes have no group; those rows are not counted as missing.",
  },
  {
    id: "group.id",
    label: "Group ID",
    section: "Master IDs",
    get: (row) => row.activity?.group?.group_id,
    applies: hasGroup,
  },
  {
    id: "group.name",
    label: "Group name",
    section: "Activity",
    get: (row) => row.activity?.group?.name,
    applies: hasGroup,
  },
  {
    id: "subject.raw",
    label: "Subject raw",
    section: "Activity",
    get: (row) => row.activity?.subject?.raw,
    applies: hasActivity,
  },
  {
    id: "subject.code_raw",
    label: "Subject code raw",
    section: "Activity",
    get: (row) => row.activity?.subject?.code_raw,
    applies: hasActivity,
  },
  {
    id: "subject.id",
    label: "Subject master ID",
    section: "Master IDs",
    get: (row) => row.activity?.subject?.subject_master_id,
    applies: hasActivity,
  },
  {
    id: "subject.code",
    label: "Subject code",
    section: "Activity",
    get: (row) => row.activity?.subject?.code,
    applies: hasActivity,
  },
  {
    id: "subject.name",
    label: "Subject name",
    section: "Activity",
    get: (row) => row.activity?.subject?.name,
    applies: hasActivity,
  },
  {
    id: "subject.category",
    label: "Subject category",
    section: "Activity",
    get: (row) => row.activity?.subject?.category,
    applies: hasActivity,
  },
  {
    id: "subject.match_method",
    label: "Subject match",
    section: "Activity",
    get: (row) => row.activity?.subject?.match_method,
    applies: hasActivity,
  },
  {
    id: "faculty.raw",
    label: "Faculty raw",
    section: "Activity",
    get: (row) => row.activity?.faculty?.map((person) => person.raw),
    applies: hasFaculty,
  },
  {
    id: "faculty.id",
    label: "Faculty ID",
    section: "Master IDs",
    get: (row) => row.activity?.faculty?.map((person) => person.faculty_id),
    applies: hasFaculty,
    description:
      "Counts faculty mentions. “Null” shows activities with at least one unresolved faculty mention.",
  },
  {
    id: "faculty.name",
    label: "Faculty name",
    section: "Activity",
    get: (row) => row.activity?.faculty?.map((person) => person.name),
    applies: hasFaculty,
  },
  {
    id: "room.raw",
    label: "Room raw",
    section: "Activity",
    get: (row) => row.activity?.room?.raw,
    applies: hasActivity,
  },
  {
    id: "room.id",
    label: "Room ID",
    section: "Master IDs",
    get: (row) => row.activity?.room?.room_id,
    applies: hasActivity,
  },
  {
    id: "subject_type_raw",
    label: "Subject type raw",
    section: "Activity",
    get: (row) => row.activity?.subject_type_raw,
    applies: hasActivity,
  },
  {
    id: "notes",
    label: "Notes",
    section: "Activity",
    get: (row) => row.activity?.notes,
    applies: hasActivity,
  },
  {
    id: "confidence",
    label: "Confidence",
    section: "Activity",
    get: (row) => row.activity?.confidence,
    applies: hasActivity,
  },
  {
    id: "activity.requires_review",
    label: "Activity review flag",
    section: "Activity",
    get: (row) => row.activity?.requires_review,
    applies: hasActivity,
  },
  {
    id: "activity.review_reasons",
    label: "Activity review reasons",
    section: "Activity",
    get: (row) => row.activity?.review_reasons,
    applies: hasActivity,
  },
];

export function isNull(value: unknown): boolean {
  return value === null || value === undefined;
}

export function fieldState(
  row: RoutineRow,
  field: FieldSpec,
): ActualFieldState {
  if (field.applies && !field.applies(row)) return "na";
  const value = field.get(row);
  if (field.id.startsWith("faculty.")) {
    const values = value as unknown[] | undefined;
    return values?.some(isNull) ? "missing" : "present";
  }
  return isNull(value) ? "missing" : "present";
}

export function fieldCounts(
  rows: RoutineRow[],
  field: FieldSpec,
): { missing: number; present: number; total: number } {
  if (field.id.startsWith("faculty.")) {
    const values = rows.flatMap((row) =>
      field.applies?.(row) ? (field.get(row) as unknown[]) : [],
    );
    const missing = values.filter(isNull).length;
    return { missing, present: values.length - missing, total: values.length };
  }
  const applicable = rows.filter((row) => !field.applies || field.applies(row));
  const missing = applicable.filter(
    (row) => fieldState(row, field) === "missing",
  ).length;
  return {
    missing,
    present: applicable.length - missing,
    total: applicable.length,
  };
}

export function readDataset(input: unknown, label: string): Dataset {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Expected a standardized routine JSON object.");
  }
  const root = input as Record<string, unknown>;
  const sourceType =
    typeof root.source_type === "string" ? root.source_type : "routine";
  const routines = Array.isArray(root.routines) ? root.routines : [root];
  if (
    !routines.length ||
    !routines.every(
      (item) =>
        item &&
        typeof item === "object" &&
        Array.isArray((item as Routine).slots),
    )
  ) {
    throw new Error("No routines with slots were found in this JSON file.");
  }

  const rows: RoutineRow[] = [];
  routines.forEach((routineValue, routineIndex) => {
    const routine = routineValue as Routine;
    routine.slots.forEach((slot, slotIndex) => {
      const activities = slot.activities?.length ? slot.activities : [null];
      activities.forEach((activity, activityIndex) => {
        const reasons = [
          ...new Set([
            ...(routine.review_reasons ?? []),
            ...(slot.review_reasons ?? []),
            ...(activity?.review_reasons ?? []),
          ]),
        ];
        rows.push({
          key: `${routineIndex}-${slotIndex}-${activityIndex}`,
          routine,
          slot,
          activity,
          routineIndex,
          slotIndex,
          activityIndex: activity ? activityIndex : null,
          reasons,
          requiresReview: Boolean(reasons.length || activity?.requires_review),
        });
      });
    });
  });

  return {
    raw: input,
    label,
    sourceType,
    collegeId:
      typeof root.college_id === "number"
        ? root.college_id
        : ((routines[0] as Routine).college_id ?? null),
    routines: routines as Routine[],
    rows,
  };
}

export function formatValue(value: unknown): string {
  if (isNull(value)) return "Null";
  if (Array.isArray(value))
    return value.length ? value.map(formatValue).join(", ") : "Empty list";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function rowSearchText(row: RoutineRow): string {
  return [
    row.routine.college,
    row.routine.department,
    row.routine.year,
    row.routine.semester,
    row.routine.section?.raw,
    row.slot.day,
    row.slot.start_time,
    row.slot.end_time,
    row.activity?.group?.raw,
    row.activity?.subject?.raw,
    row.activity?.subject?.name,
    row.activity?.subject?.code_raw,
    row.activity?.room?.raw,
    ...(row.activity?.faculty?.flatMap((person) => [person.raw, person.name]) ??
      []),
    ...row.reasons,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function reasonCounts(
  rows: RoutineRow[],
): Array<{ reason: string; count: number }> {
  const counts = new Map<string, number>();
  rows.forEach((row) =>
    row.reasons.forEach((reason) =>
      counts.set(reason, (counts.get(reason) ?? 0) + 1),
    ),
  );
  return [...counts]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);
}
