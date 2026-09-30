# Routine Standardizer

The service accepts PDF, image, and Excel workbooks (`.xlsx`, `.xlsm`, `.xls`). PDF/image uploads use one model request to transcribe visible tables into a reviewable Excel workbook, followed by one extraction request per transcribed sheet. Every successful response has `source_type`, `routine_count`, and a `routines` array, including uploads with only one timetable. Each routine owns its course, department, year, semester, section, default room, and complete `slots` array. TINT workbooks with `Department:` timetable blocks use a local parser and return separate routines without a model request. Other Excel layouts use the generic model profile. Every profile adapts each entry to `RoutineExtraction` in `app/schemas/canonical_raw.py` before shared context loading, resolution, and validation. Unresolved values are returned with review reasons.

## Setup and commands

These are commands for a local run. A TINT-style workbook needs the public ERP subject, employee, parent-class, and child-class endpoints but does not need an LLM key; PDF, image, and other Excel layouts need the key.

| Stage | Command |
| --- | --- |
| Create environment | `python -m venv .venv` |
| Activate it | `source .venv/bin/activate` |
| Install dependencies | `pip install -r requirements.txt` |
| Create private config | `cp .env.example .env` |
| Start API | `.venv/bin/python -m uvicorn app.main:app --reload` |
| Open API docs | `http://127.0.0.1:8000/docs` |
| Submit an NSEC routine | `curl -F "file=@/path/to/routine.pdf" 'http://127.0.0.1:8000/routines/standardize?college_id=1&session_id=27'` |

For Excel, use the same command with an `.xlsx`, `.xlsm`, or `.xls` file. For the TINT block layout, the service reads visible sheets, department headers, time columns, day rows, merged cells, and group lab entries into a workbook response. That response has `source_type: "workbook"`, `routine_count`, and a `routines` array. The supplied `Routines/TINT/tint.xlsx` produces 30 routines. Other Excel layouts are converted to cell-addressed text for the model. Formula text is preserved but not calculated; embedded drawings/images are not included. Large or empty workbooks are rejected rather than silently truncated.

Each output slot includes `start_period` and `end_period`. A cell spanning multiple labeled periods becomes one slot covering that range. When the document shows times but no period numbers, both period fields are `null`. Unreadable day, time, or slot type values are also `null` and flagged for review.

For PDF/image uploads, the first model response contains only visible cell text, positions, and merged spans. The application writes an `.xlsx` without adding headings, IDs, or inferred content, then reads each sheet as cell-addressed text for routine extraction. Each sheet is extracted separately so a long multi-table response cannot silently omit later routines. When a sheet has one visible section heading, that full heading grounds its extracted section label. Raw metadata and activity values missing from the transcribed cells are cleared to `null` (or `[]` for faculty) and reported in `conversion_review_reasons`. The response includes `converted_workbook_file` so the transcription can be inspected. The source-to-cell transcription still needs visual review when the image is unclear; workbook round-trip checks verify that the written cells match the model's transcription, not the original image.

The JSON hierarchy is `routines[] → routine metadata + slots[] → day/period/time + activities[]`. Each slot repeats its routine's college ID, requested session ID, resolved course/stream/semester master IDs, and complete section object so it can be used independently. Group IDs and `ClassId` remain on each activity because parallel activities in one slot can belong to different groups; whole-section activities have `group: null`. Slots retain their type, review reasons, and parallel activities. Activities retain group, subject, faculty, room, subject type, notes, confidence, and review details. Different section/year/semester tables stay in separate routine objects. The model extraction prompt requires this hierarchy even for a single table; the TINT parser produces the same response hierarchy. Metadata that is not visible remains `null` for that routine.

Every successful request also saves the standardized JSON under `output/` by default. PDF/image uploads also save the transcribed `.xlsx` in that directory. The response includes absolute `output_file` and, for converted uploads, `converted_workbook_file` paths. Filenames contain the upload name, a UTC timestamp, and a short unique suffix, so repeated runs do not overwrite earlier results. Set `OUTPUT_DIR` in `.env` to choose another directory. The output directory is gitignored because routines may contain private timetable data.

Run the local TINT upload and save the HTTP response separately with:

```bash
curl -sS -F "file=@/home/ass/src/AI_routine_analyzer/Routines/TINT/tint.xlsx" \
  -o /tmp/tint-response.json -w 'HTTP %{http_code}\n' \
  'http://127.0.0.1:8000/routines/standardize?college_id=2&session_id=28'
```

The server saves another copy under `output/` and returns that file's absolute path in `output_file`. Run `.venv/bin/python -m unittest discover -s tests -v` to test the TINT upload without calling OpenAI or the ERP endpoints. Use the virtual environment interpreter for all app commands; the system Python may not have the packages from `requirements.txt`.

Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` for OpenAI or an OpenAI-compatible endpoint; change `LLM_BASE_URL` and `LLM_MODEL` for OpenRouter, Kimi, or another compatible gateway. Set `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and a Claude `LLM_MODEL` for native Anthropic access. Configure the public ERP base URLs in `.env`; the required `college_id` query parameter on each upload is added to those URLs for the fetch. `MASTER_API_KEY` stays empty for these public APIs. The `.env` file is gitignored.

`LLM_TIMEOUT_SECONDS` defaults to 180 for each model request. PDF/image processing uses one transcription request plus one extraction request per sheet, with at most two sheet extractions running concurrently; requests are not automatically retried. `HTTP_TIMEOUT_SECONDS` remains 30 for master API requests. Restart the server after changing `.env`.

## Current ERP integration

The server has one reusable HTTP client. Subject and employee requests run concurrently on a cache miss. Successful parsed responses are cached in memory for `MASTER_CACHE_TTL_SECONDS` (default 300) using the full URL, including `college_id`, as the key. Concurrent requests for the same college share one fetch; different colleges do not share records. There is no API request per timetable cell. Each process has its own cache, so multiple server workers can each make a request when their cache expires.

The response adapter accepts arrays and common `data`, `items`, or `results` wrappers. The current public ERP responses use these fields:

| Endpoint | Required fields | Optional fields |
| --- | --- | --- |
| Subjects | `SubjectMasterId`, `Name` | `Code`, `SubjectType` |
| Employees | `EmployeeId` | `Abbreviation`, `EmployeeName` |

The adapter also accepts common snake-case alternatives. Cached faculty records contain the API abbreviation and aliases plus an `initial` generated from the person's name. The resolver matches these identifiers locally. If multiple people match, it selects a unique person whose `Stream` matches the routine department. When the extracted department is empty, it can use a department prefix from a section such as `AIML.2A`, provided that prefix exists among the fetched employee streams. Multiple matches in that department, or no match at all, leave `faculty_id` null for review. The client raises a clear error for unknown response shapes rather than treating missing data as an empty collection. The code never asks the model for IDs.

`SUBJECT_API_BASE_URL` and `FACULTY_API_BASE_URL` are required. `GROUP_API_BASE_URL` and `SECTION_API_BASE_URL` are optional legacy sources. These subject, faculty, and legacy flat endpoints receive the upload's `college_id` and no fixed `department_id`. Legacy group records need an ID and name, and may include `SectionId`; legacy section records need an ID and name. Matching uses the routine's section to scope groups. Student-to-group assignments must come from trusted records.

Each upload supplies `session_id` explicitly; use `27` for NSEC or `28` for TINT when those are the active ERP sessions. After loading the subject catalog, the pipeline uses its `CourseMasterId`, `StreamMasterId`, and `SemesterMasterId` to query the parent classroom API for each routine's requested session and scope. The selected scope IDs are included at routine level and in every slot; if multiple scopes remain possible, those IDs remain null until a unique parent match selects one. A uniquely matched parent class supplies `section.section_id` from ERP `ID`, `section.class_id` from `ClassId`, and its `ClassName`. The child API is called with the parent `ID`; each matched child supplies `group.group_id`, `group.class_id`, `group.parent_class_master_id`, and its `ClassName`. Whole-section activities keep `group: null`. When the timetable omits a section label, a parent is accepted only if the fully scoped ERP query has exactly one result. Missing metadata or ambiguous matches leave IDs null and mark the routine for review. The TINT workbook labels Cyber Security as `CyS` while the ERP catalog uses `CS`; the classroom lookup recognizes that alias. The two classroom URLs are configurable with `PARENT_CLASS_API_URL` and `CHILD_CLASS_API_URL`; repeated requests use the shared URL cache. For uploads using these classroom APIs, they replace the older flat section/group sources.

Faculty API records use `Stream` for the timetable department; their `Department` field is an HR category such as Academics or Admin. Admin records are excluded from teaching faculty matches.

## Current scope

Subject matching uses the ERP catalog fetched with the upload's `college_id`. It first filters records by the resolved `CourseMasterId`, `StreamMasterId`, and `SemesterMasterId`, then uses the printed subject code when present, followed by API aliases, exact names, unique acronyms or name abbreviations, and close spelling. A visible NSEC section such as `AIML.3A` supplies the stream and year; an `ODD` or `EVEN` heading narrows the semester, while the requested session's parent classroom records confirm it when the semester is absent. Theory and lab records with the same name are separated by the activity's visible lab label or subject type. The selected catalog row supplies both `subject_master_id` and `code` in the JSON. If the printed code is absent and text matching remains unresolved, the local CPU embedding model searches a FAISS index of that college's subject names and API aliases within the same resolved scope. Catalog vectors are cached in memory per college and catalog version; the model files are cached under `.cache/subject-embeddings/` after the first download. A semantic result needs a clear winner above the configured similarity and margin thresholds and is marked for review. Acronym and abbreviated-name matches are also marked for review. Activities with no catalog subject, or an extracted cell containing multiple subjects, remain unresolved instead of receiving an arbitrary ID. Set `SUBJECT_EMBEDDING_BACKEND=off` to disable the fallback, or `remote` to use `SUBJECT_EMBEDDING_MODEL` with an OpenAI-compatible endpoint. Faculty uses exact abbreviations and aliases before derived initials; short identifiers never use embeddings. Group and section matching is deterministic. Ambiguous or missing matches require review. Room text is preserved without a room ID. Confidence is a binary resolution indicator, not a calibrated probability.

The repository has an `origin` remote. Local commits are not pushed automatically.
