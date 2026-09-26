# Routine Standardizer --- LLM-First Implementation Plan

> Architecture update: the implemented service uses input profiles. NSEC PDFs/images
> use a profile prompt and validated model output; TINT Department-block workbooks
> use a local parser; other workbooks use the generic model profile. Each path
> adapts to the canonical raw routine in `app/schemas/canonical_raw.py` before
> context loading and enrichment. The diagram below is the original plan;
> [FLOWCHART.md](FLOWCHART.md) describes the implemented flow.

## 1. Goal

Build a Python service that accepts a complete college routine/timetable
document (PDF or image), sends the document to a multimodal LLM, and
receives **raw structured JSON for the whole routine**.

The LLM is responsible for understanding the visual document: table
layout, merged cells, handwritten changes, multiple subjects in the same
time slot, group divisions, faculty initials, rooms, subject codes,
days, and times.

The backend is responsible for everything that depends on trusted
application data:

-   Resolve the section to its master ID.
-   Resolve Group A / Group B / other groups to group IDs.
-   Resolve faculty initials to faculty IDs.
-   Resolve subject abbreviations/names/codes to canonical subject
    master IDs.
-   Cache API data so APIs are **not called once per timetable block**.
-   Validate and enrich the raw LLM JSON.
-   Flag unresolved or ambiguous values instead of silently guessing.
-   Produce the final standardized routine JSON.

The core rule is:

> **LLM reads what the routine says. Backend code resolves what those
> values mean inside our system.**

------------------------------------------------------------------------

# 2. High-Level Architecture

``` text
                    ROUTINE
                 PDF / IMAGE
                      │
                      ▼
             LANGCHAIN / LLM LAYER
                      │
          Multimodal document analysis
                      │
                      ▼
                RAW ROUTINE JSON
                      │
                      ▼
              PYDANTIC VALIDATION
                      │
                      ▼
             ROUTINE CONTEXT LOADER
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      Subject API  Faculty API   Group API
          │           │           │
          └───────────┼───────────┘
                      ▼
                 LOCAL CACHE
                      │
                      ▼
               RESOLVER ENGINE
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Subject      Faculty      Group
       Resolver     Resolver     Resolver
          │           │           │
          └───────────┼───────────┘
                      ▼
               ENRICHED ROUTINE
                      │
                      ▼
                VALIDATION
                 /        \
             resolved    ambiguous
                │           │
                ▼           ▼
              accept     review
                │           │
                └─────┬─────┘
                      ▼
             FINAL ROUTINE JSON
```

------------------------------------------------------------------------

# 3. Phase 1 --- LangChain + Multimodal LLM Extraction

This is the first implementation phase.

The system should send the **complete routine document** to a multimodal
model rather than processing every timetable block with separate
OCR/model calls.

LangChain can be used as the model abstraction/orchestration layer. The
rest of the application should not depend directly on LangChain.

Suggested structure:

``` text
app/
├── llm/
│   ├── client.py
│   ├── extractor.py
│   ├── prompts.py
│   └── schemas.py
```

The model should receive:

``` text
Routine PDF/Image
        +
Master extraction prompt
        +
Strict structured-output schema
        ↓
Multimodal LLM
        ↓
Raw Routine JSON
```

The extraction prompt must instruct the model to:

-   Read the complete routine.
-   Extract routine-level metadata.
-   Understand days and time ranges.
-   Understand merged timetable cells.
-   Understand parallel classes.
-   Detect section group divisions such as Group A and Group B.
-   Extract subject text exactly as visible.
-   Extract subject codes when visible.
-   Extract faculty initials exactly as visible.
-   Extract room information.
-   Understand handwritten additions/corrections when clearly visible.
-   Understand crossed-out/replaced values when the replacement is
    visually clear.
-   Never invent database IDs.
-   Never invent full subject names from abbreviations.
-   Never invent faculty identities.
-   Return `null` when information is not available.
-   Return structured JSON only.

The LLM output is **raw document data**, not the final database-ready
routine.

------------------------------------------------------------------------

# 4. Raw Data the LLM Should Extract

From a routine like the provided example, the model should be able to
extract routine-level information such as:

``` text
college
course
department
year
semester
section
default room
routine date/version (if present)
```

For each timetable slot:

``` text
day
start_time
end_time
slot_type
activities[]
```

For each activity:

``` text
group_raw
subject_raw
subject_code_raw
subject_type_raw
faculty_raw[]
room_raw
notes
```

The LLM should preserve the original visible values because those raw
values are needed by the resolver layer.

Example:

``` text
Visible document:

PCC-CS301
(MB2)

LLM:

subject_raw = "PCC-CS301"
subject_code_raw = "PCC-CS301"
faculty_raw = ["MB2"]
```

The LLM must NOT decide that `MB2` belongs to a particular faculty
database record. That happens later.

------------------------------------------------------------------------

# 5. JSON Scenario A --- Whole Section Activity

If there is no group division, the timetable slot still contains an
`activities` array.

`group_raw = null` means the activity applies to the complete section.

Example raw LLM output:

``` json
{
  "day": "Monday",
  "start_time": "09:30",
  "end_time": "10:25",
  "slot_type": "class",
  "activities": [
    {
      "group_raw": null,
      "subject_raw": "PCC-CS301",
      "subject_code_raw": "PCC-CS301",
      "subject_type_raw": null,
      "faculty_raw": ["MB2"],
      "room_raw": "305",
      "notes": null
    }
  ]
}
```

Meaning:

``` text
Section 1
   │
   └── PCC-CS301
       Faculty: MB2
       Room: 305

group_raw = null
→ activity applies to the entire section
```

------------------------------------------------------------------------

# 6. JSON Scenario B --- Group-Divided Parallel Activities

One timetable slot can contain multiple simultaneous activities for
different groups of the same section.

Example:

``` text
Monday 13:40–15:20
Section 1

Group A
→ ESC-391 Analog and Digital Lab
→ Room R-318

Group B
→ PCC-CS392 H/W Lab
→ TD + SC
```

The raw LLM output should represent this as:

``` json
{
  "day": "Monday",
  "start_time": "13:40",
  "end_time": "15:20",
  "slot_type": "class",
  "activities": [
    {
      "group_raw": "Gr-A",
      "subject_raw": "ESC-391 Analog and digital lab",
      "subject_code_raw": "ESC-391",
      "subject_type_raw": "Lab",
      "faculty_raw": [],
      "room_raw": "R-318",
      "notes": null
    },
    {
      "group_raw": "Gr-B",
      "subject_raw": "PCC-CS392 H/W Lab",
      "subject_code_raw": "PCC-CS392",
      "subject_type_raw": "Lab",
      "faculty_raw": ["TD", "SC"],
      "room_raw": null,
      "notes": null
    }
  ]
}
```

This same structure supports:

``` text
No group
→ one activity with group_raw = null

Group A + Group B
→ two activities

Group A + Group B + Group C
→ three activities
```

Do not create different schemas for grouped and non-grouped routines.

------------------------------------------------------------------------

# 7. Break / Non-Class Slots

Breaks should not be represented as fake subjects.

Example:

``` json
{
  "day": "Monday",
  "start_time": "13:10",
  "end_time": "13:40",
  "slot_type": "break",
  "activities": []
}
```

Other special values such as research hours or college activities can
use an appropriate `slot_type` or activity note according to the final
application requirements.

------------------------------------------------------------------------

# 8. Phase 2 --- Validate the LLM JSON

Use Pydantic models immediately after receiving the LLM response.

Suggested structure:

``` text
app/
└── schemas/
    ├── extraction.py
    └── routine.py
```

Conceptually:

``` python
RoutineExtraction
    metadata
    slots[]
        day
        start_time
        end_time
        slot_type
        activities[]
            group_raw
            subject_raw
            subject_code_raw
            subject_type_raw
            faculty_raw[]
            room_raw
```

Pydantic should verify structure and data types.

Malformed model output should never directly enter the resolver/database
layer.

------------------------------------------------------------------------

# 9. Phase 3 --- Load Routine Context Once

This is a major optimization.

Do **not** call the faculty, subject, or group API separately for every
timetable block.

After the LLM extracts routine metadata:

``` text
college
department
course
year
semester
section
```

use this information to load all relevant master data once.

Example:

``` text
LLM JSON
   ↓
Department = CSE
Semester = 3
Section = 1
College = TINT
   ↓
Context Loader
```

Then make a small number of API requests:

``` text
Subject API
→ fetch subjects relevant to CSE / Semester 3

Faculty API
→ fetch faculty relevant to the college/department

Group API
→ fetch groups belonging to Section 1
```

Store all responses in memory/cache for processing the entire routine.

------------------------------------------------------------------------

# 10. API Context Cache

Example:

``` python
RoutineContext(
    subjects=[...],
    faculty=[...],
    groups=[...]
)
```

Conceptually:

``` text
Process Routine
      │
      ├── Subject API ── ONE contextual fetch
      │
      ├── Faculty API ── ONE contextual fetch
      │
      └── Group API ──── ONE contextual fetch
              │
              ▼
          Local Cache
              │
      reused for every slot
```

Then 40 timetable blocks do NOT produce:

``` text
40 subject API calls
40 faculty API calls
40 group API calls
```

Instead:

``` text
~1 contextual subject fetch
~1 contextual faculty fetch
~1 contextual group fetch

then local matching for all timetable activities
```

The exact number depends on the APIs, but the principle is to **fetch
collections/context once and resolve locally**.

------------------------------------------------------------------------

# 11. Optional Persistent Cache

If many routines belong to the same college/department/semester, add
Redis or an application-level cache later.

Cache keys can look conceptually like:

``` text
subjects:{college_id}:{course_id}:{department_id}:{semester}
faculty:{college_id}:{department_id}
groups:{section_id}
```

Example:

``` text
Routine A
CSE Semester 3
      ↓
API fetch
      ↓
CACHE


Routine B
CSE Semester 3
      ↓
CACHE HIT
      ↓
No repeated subject API fetch
```

Start with an in-process cache if deployment is simple. Add Redis when
multiple workers/servers need to share the cache.

------------------------------------------------------------------------

# 12. Phase 4 --- Subject Resolver

The LLM may extract:

``` text
DSA
D.S.A
Data Structure
Data Structures
DS & Algo
PCC-CS301
```

while the master API may contain:

``` text
ID: 931
Code: PCC-CS301
Name: Data Structures and Algorithms
```

The backend must standardize these values.

The matching order should be:

``` text
subject_code_raw
      ↓
Exact code match
      ↓
if unavailable

Normalized exact name/alias
      ↓
if unavailable

RapidFuzz
      ↓
if still ambiguous

Embedding similarity
      ↓
Best candidates
      ↓
Confidence / ambiguity check
```

Always prefer a reliable exact subject-code match over semantic
matching.

------------------------------------------------------------------------

# 13. Subject Normalization

Before matching:

``` text
"D.S.A"
"DSA"
" dsa "
```

can be normalized for comparison.

Keep the original raw value separately.

Example:

``` json
{
  "raw": "D.S.A",
  "normalized": "dsa"
}
```

Normalization may include:

-   lowercase
-   trim whitespace
-   collapse repeated spaces
-   remove safe punctuation differences
-   normalize common code formatting

Do not destroy the original extracted text.

------------------------------------------------------------------------

# 14. Subject Embedding Matching

Use embeddings when code/alias/fuzzy matching cannot confidently resolve
the subject.

Example:

``` text
LLM:
"Data Structure"

API candidates:

PCC-CS301
Data Structures and Algorithms

PCC-CS302
Computer Organization

PCC-CS303
Discrete Mathematics
```

Create embeddings for the canonical subject names and known aliases.

``` text
"Data Structure"
       ↓
Embedding model
       ↓
Vector
       ↓
Compare with cached subject vectors
       ↓
Data Structures and Algorithms
```

Possible tools:

``` text
SentenceTransformers
FAISS or direct cosine similarity
```

At the small candidate sizes expected after department/semester
filtering, direct cosine similarity may be sufficient. FAISS is
optional.

Do not embed the entire college database for every timetable block.

Precompute/cache canonical subject embeddings whenever possible.

------------------------------------------------------------------------

# 15. Subject Resolver Output

Raw:

``` json
{
  "subject_raw": "DSA",
  "subject_code_raw": null
}
```

Resolved:

``` json
{
  "subject": {
    "raw": "DSA",
    "subject_master_id": 931,
    "code": "PCC-CS301",
    "name": "Data Structures and Algorithms",
    "match_method": "embedding",
    "match_score": 0.94
  }
}
```

Possible `match_method` values:

``` text
code
alias
exact_name
fuzzy
embedding
unresolved
```

------------------------------------------------------------------------

# 16. Phase 5 --- Faculty Resolver

The LLM only extracts visible faculty initials.

Example:

``` json
{
  "faculty_raw": ["TD", "SC"]
}
```

The Faculty API data has already been loaded into the routine context.

Example cached data:

``` text
faculty_id     initials
201            TD
207            SC
208            MB2
...
```

Resolution becomes a local lookup:

``` text
TD
 ↓
cached faculty map
 ↓
faculty_id = 201


SC
 ↓
cached faculty map
 ↓
faculty_id = 207
```

Final activity:

``` json
{
  "faculty": [
    {
      "raw": "TD",
      "faculty_id": 201
    },
    {
      "raw": "SC",
      "faculty_id": 207
    }
  ]
}
```

If the same initials map to multiple faculty records, do not guess. Use
available department/context rules or flag the value for review.

------------------------------------------------------------------------

# 17. Phase 6 --- Group Resolver

If:

``` json
"group_raw": null
```

the activity applies to the complete section and no group lookup is
required.

If:

``` json
"group_raw": "Gr-A"
```

use the groups already fetched for that section.

Example:

``` text
Section ID = 123

Group API cache:

501 → Group A
502 → Group B
```

Resolve:

``` text
Gr-A
 ↓
normalize
 ↓
Group A
 ↓
group_id = 501
```

Result:

``` json
{
  "group": {
    "raw": "Gr-A",
    "group_id": 501,
    "name": "Group A"
  }
}
```

Group matching should normally be deterministic after section filtering.

------------------------------------------------------------------------

# 18. Phase 7 --- Section / Master Context Resolution

Routine-level metadata should also be resolved to trusted master IDs.

For example:

``` text
College
Course
Department
Year
Semester
Section
```

The final JSON should preferably contain both readable values and
application IDs.

Example:

``` json
{
  "section": {
    "raw": "1",
    "section_id": 123,
    "name": "Section 1"
  }
}
```

Do not ask the LLM to invent these IDs.

------------------------------------------------------------------------

# 19. Phase 8 --- Enrichment Loop

Once context is loaded, enrichment is simple local processing.

Conceptually:

``` python
for slot in routine.slots:

    for activity in slot.activities:

        activity.subject = subject_resolver.resolve(
            activity.subject_raw,
            activity.subject_code_raw,
            context.subjects
        )

        activity.faculty = faculty_resolver.resolve_many(
            activity.faculty_raw,
            context.faculty
        )

        if activity.group_raw is not None:
            activity.group = group_resolver.resolve(
                activity.group_raw,
                context.groups
            )
        else:
            activity.group = None
```

The important part is that these loops use **already-fetched data**.

They should not repeatedly call remote APIs.

------------------------------------------------------------------------

# 20. Phase 9 --- Validation

After enrichment, validate every slot/activity.

Examples of validation rules:

``` text
Subject resolved?
Faculty initials resolved?
Group exists under this section?
Subject belongs to expected department/semester?
Duplicate group activity?
Two conflicting activities for the same group/time?
Start time < end time?
Required IDs available?
```

Validation should occur at the activity level.

Example:

``` text
Slot
Monday 13:40–15:20

Group A → completely resolved
Group B → faculty "SC4" unresolved
```

Only Group B should require review.

------------------------------------------------------------------------

# 21. Confidence / Review

Example final activity:

``` json
{
  "group": {
    "raw": "Gr-B",
    "group_id": 502
  },
  "subject": {
    "raw": "PCC-CS392",
    "subject_master_id": 932,
    "match_method": "code"
  },
  "faculty": [
    {
      "raw": "TD",
      "faculty_id": 201
    },
    {
      "raw": "SC",
      "faculty_id": 207
    }
  ],
  "confidence": 0.98,
  "requires_review": false,
  "review_reasons": []
}
```

Unresolved example:

``` json
{
  "faculty": [
    {
      "raw": "SC4",
      "faculty_id": null
    }
  ],
  "confidence": 0.71,
  "requires_review": true,
  "review_reasons": [
    "Faculty initials could not be uniquely resolved"
  ]
}
```

------------------------------------------------------------------------

# 22. Optional LLM Verification

Do not automatically make another large-model call for every timetable
block.

Only use a second model call when deterministic resolution/validation
finds an important ambiguity.

Example:

``` text
Initial document extraction
        ↓
Raw JSON
        ↓
Resolvers
        ↓
Validation
        ↓
Everything resolved?
    /          \
  YES           NO
   ↓             ↓
 DONE      targeted verification
```

For verification, send the original routine/page/crop plus the specific
ambiguous value and ask the model to compare against the visible
document.

The model should not be allowed to invent master IDs.

------------------------------------------------------------------------

# 23. Final JSON Model

The final model should conceptually be:

``` text
Routine
│
├── College
├── Course
├── Department
├── Year
├── Semester
├── Section
│
└── Slots[]
     │
     ├── Day
     ├── Start Time
     ├── End Time
     ├── Slot Type
     │
     └── Activities[]
          │
          ├── Group
          │     └── null = whole section
          │
          ├── Subject
          │     ├── raw
          │     ├── master_id
          │     ├── code
          │     └── canonical name
          │
          ├── Faculty[]
          │     ├── raw initials
          │     └── faculty_id
          │
          ├── Room
          ├── Confidence
          └── Review State
```

------------------------------------------------------------------------

# 24. Example Final JSON --- Whole Section

``` json
{
  "day": "Monday",
  "start_time": "09:30",
  "end_time": "10:25",
  "slot_type": "class",
  "section": {
    "raw": "1",
    "section_id": 123
  },
  "activities": [
    {
      "group": null,
      "subject": {
        "raw": "PCC-CS301",
        "subject_master_id": 931,
        "code": "PCC-CS301",
        "name": "Data Structures and Algorithms",
        "match_method": "code"
      },
      "faculty": [
        {
          "raw": "MB2",
          "faculty_id": 208
        }
      ],
      "room": {
        "raw": "305",
        "room_id": null
      },
      "confidence": 0.99,
      "requires_review": false,
      "review_reasons": []
    }
  ]
}
```

IDs are illustrative placeholders.

------------------------------------------------------------------------

# 25. Example Final JSON --- Group Division

``` json
{
  "day": "Monday",
  "start_time": "13:40",
  "end_time": "15:20",
  "slot_type": "class",
  "section": {
    "raw": "1",
    "section_id": 123
  },
  "activities": [
    {
      "group": {
        "raw": "Gr-A",
        "group_id": 501
      },
      "subject": {
        "raw": "ESC-391 Analog and digital lab",
        "subject_master_id": 931,
        "code": "ESC-391",
        "name": "Analog and Digital Electronics",
        "match_method": "code"
      },
      "faculty": [],
      "room": {
        "raw": "R-318",
        "room_id": null
      },
      "confidence": 0.99,
      "requires_review": false,
      "review_reasons": []
    },
    {
      "group": {
        "raw": "Gr-B",
        "group_id": 502
      },
      "subject": {
        "raw": "PCC-CS392 H/W Lab",
        "subject_master_id": 932,
        "code": "PCC-CS392",
        "name": null,
        "match_method": "code"
      },
      "faculty": [
        {
          "raw": "TD",
          "faculty_id": 201
        },
        {
          "raw": "SC",
          "faculty_id": 207
        }
      ],
      "room": {
        "raw": null,
        "room_id": null
      },
      "confidence": 0.98,
      "requires_review": false,
      "review_reasons": []
    }
  ]
}
```

IDs are illustrative placeholders.

------------------------------------------------------------------------

# 26. Recommended Code Structure

``` text
routine-standardizer/
│
├── app/
│   ├── main.py
│   │
│   ├── schemas/
│   │   ├── extraction.py
│   │   ├── routine.py
│   │   └── context.py
│   │
│   ├── ingestion/
│   │   ├── pdf.py
│   │   └── image.py
│   │
│   ├── llm/
│   │   ├── client.py
│   │   ├── extractor.py
│   │   ├── verifier.py
│   │   └── prompts.py
│   │
│   ├── clients/
│   │   ├── subject_api.py
│   │   ├── faculty_api.py
│   │   └── group_api.py
│   │
│   ├── cache/
│   │   └── routine_context.py
│   │
│   ├── resolvers/
│   │   ├── subject.py
│   │   ├── faculty.py
│   │   └── group.py
│   │
│   ├── matching/
│   │   ├── normalize.py
│   │   ├── fuzzy.py
│   │   └── embeddings.py
│   │
│   ├── validation/
│   │   └── routine.py
│   │
│   └── services/
│       └── routine_processor.py
│
├── tests/
├── samples/
├── Dockerfile
└── requirements.txt
```

------------------------------------------------------------------------

# 27. Responsibility of Each Layer

``` text
ingestion/
→ prepare PDF/image for the LLM

llm/
→ extract raw visible routine data

schemas/
→ define and validate JSON contracts

clients/
→ communicate with Subject / Faculty / Group APIs

cache/
→ store API responses for the current routine / reusable context

matching/
→ normalization, fuzzy matching, embeddings

resolvers/
→ turn raw values into trusted master IDs

validation/
→ detect unresolved/conflicting data

services/
→ orchestrate the complete workflow
```

------------------------------------------------------------------------

# 28. Main Processing Flow

The central service should conceptually work like this:

``` python
async def process_routine(file):

    # PHASE 1
    raw = await llm_extractor.extract(file)

    # PHASE 2
    routine = RoutineExtraction.model_validate(raw)

    # PHASE 3
    context = await context_loader.load(
        college=routine.college,
        course=routine.course,
        department=routine.department,
        semester=routine.semester,
        section=routine.section,
    )

    # PHASE 4-6
    for slot in routine.slots:
        for activity in slot.activities:

            activity.subject = subject_resolver.resolve(
                raw_name=activity.subject_raw,
                raw_code=activity.subject_code_raw,
                candidates=context.subjects,
            )

            activity.faculty = faculty_resolver.resolve_many(
                initials=activity.faculty_raw,
                candidates=context.faculty,
            )

            activity.group = group_resolver.resolve(
                raw_group=activity.group_raw,
                candidates=context.groups,
            )

    # PHASE 9
    issues = validator.validate(routine)

    # Optional targeted verification
    if issues.requires_visual_verification:
        routine = await verifier.verify(file, routine, issues)

    return routine
```

This is conceptual pseudocode. Actual implementation should keep API
clients, cache, matching, and resolvers independently testable.

------------------------------------------------------------------------

# 29. Optimized API Strategy

Avoid:

``` text
Slot 1 → Subject API
Slot 1 → Faculty API
Slot 1 → Group API

Slot 2 → Subject API
Slot 2 → Faculty API
Slot 2 → Group API

...

Slot 40 → ...
```

Use:

``` text
                    ROUTINE
                       │
                       ▼
                  LLM JSON
                       │
                       ▼
              Identify Context
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
Subject API        Faculty API       Group API
   ONCE               ONCE             ONCE
       │               │               │
       └───────────────┼───────────────┘
                       ▼
                     CACHE
                       │
                       ▼
             All timetable slots
              resolve locally
```

This is especially important when the master system contains thousands
of records.

Always narrow remote queries by available context such as:

``` text
college
course
department
semester
section
```

before bringing data into the resolver.

------------------------------------------------------------------------

# 30. Implementation Order

## Phase 1

LangChain/model client + multimodal routine extraction + strict raw JSON
schema.

## Phase 2

Pydantic validation.

## Phase 3

Subject, Faculty, and Group API clients.

## Phase 4

Routine context loader + local caching.

## Phase 5

Exact subject-code matching.

## Phase 6

Faculty-initial resolution.

## Phase 7

Group resolution.

## Phase 8

Subject normalization + aliases + RapidFuzz.

## Phase 9

Subject embedding similarity for unresolved name variations.

## Phase 10

Final enrichment and standardized JSON generation.

## Phase 11

Validation + review reasons.

## Phase 12

Optional targeted LLM verification for ambiguous visual cases.

## Phase 13

Persistent Redis cache only if scale/multiple workers require it.

------------------------------------------------------------------------

# 31. First Version to Build

Do not implement everything simultaneously.

The first usable vertical slice should be:

``` text
1 routine image/PDF
        ↓
Multimodal LLM
        ↓
Raw JSON
        ↓
Pydantic
        ↓
Fetch Subject API
Fetch Faculty API
Fetch Group API
        ↓
Cache results
        ↓
Exact code / initials / group matching
        ↓
Final enriched JSON
```

Once this works reliably, add:

``` text
aliases
↓
RapidFuzz
↓
embeddings
↓
confidence/review
↓
optional verification
```

------------------------------------------------------------------------

# 32. Final Principle

The system should have three clearly separated responsibilities:

``` text
MULTIMODAL LLM
"What is visibly written in this routine?"

            ↓

DETERMINISTIC RESOLVERS
"What records in our APIs correspond to those values?"

            ↓

VALIDATION
"Did everything resolve safely, or does a human need to review it?"
```

Do not ask the LLM to generate trusted faculty IDs, group IDs, or
subject master IDs.

Do not make remote API calls for every timetable cell.

Extract the complete routine once, fetch the relevant master data once,
cache it, and resolve all timetable activities locally.

The final conceptual model is:

> **Routine → Time Slots → Activities → Group (optional) + Subject +
> Faculty + Room**

where:

> **`group = null` means the activity belongs to the entire section.**
