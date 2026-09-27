# Routine Standardizer

The service accepts PDF, image, and Excel workbooks (`.xlsx`, `.xlsm`, `.xls`). NSEC PDF/image routines use one model request with NSEC extraction rules. A PDF containing multiple independent routine tables returns `source_type: "document"`, `routine_count`, and a `routines` array. TINT workbooks with `Department:` timetable blocks use a local parser and return separate routines without a model request. Other Excel layouts use the generic model profile. Every profile adapts its output to `RoutineExtraction` in `app/schemas/canonical_raw.py` before shared context loading, resolution, and validation. Unresolved values are returned with review reasons.

## Setup and commands

These are commands for a local run. A TINT-style workbook needs the two public ERP endpoints but does not need an OpenAI key; PDF, image, and other Excel layouts need the key.

| Stage | Command |
| --- | --- |
| Create environment | `python -m venv .venv` |
| Activate it | `source .venv/bin/activate` |
| Install dependencies | `pip install -r requirements.txt` |
| Create private config | `cp .env.example .env` |
| Start API | `.venv/bin/python -m uvicorn app.main:app --reload` |
| Open API docs | `http://127.0.0.1:8000/docs` |
| Submit a routine | `curl -F "file=@/path/to/routine.pdf" 'http://127.0.0.1:8000/routines/standardize?college_id=1'` |

For Excel, use the same command with an `.xlsx`, `.xlsm`, or `.xls` file. For the TINT block layout, the service reads visible sheets, department headers, time columns, day rows, merged cells, and group lab entries into a workbook response. That response has `source_type: "workbook"`, `routine_count`, and a `routines` array. The supplied `Routines/TINT/tint.xlsx` produces 30 routines. Other Excel layouts are converted to cell-addressed text for the model. Formula text is preserved but not calculated; embedded drawings/images are not included. Large or empty workbooks are rejected rather than silently truncated.

Each output slot includes `start_period` and `end_period`. A cell spanning multiple labeled periods becomes one slot covering that range. When the document shows times but no period numbers, both period fields are `null`. Unreadable day, time, or slot type values are also `null` and flagged for review.

Every successful request also saves the standardized JSON under `output/` by default. The response includes its absolute `output_file` path. Filenames contain the upload name, a UTC timestamp, and a short unique suffix, so repeated runs do not overwrite earlier results. Set `OUTPUT_DIR` in `.env` to choose another directory. The output directory is gitignored because routines may contain private timetable data.

Run the local TINT upload and save the HTTP response separately with:

```bash
curl -sS -F "file=@/home/ass/src/AI_routine_analyzer/Routines/TINT/tint.xlsx" \
  -o /tmp/tint-response.json -w 'HTTP %{http_code}\n' \
  'http://127.0.0.1:8000/routines/standardize?college_id=2'
```

The server saves another copy under `output/` and returns that file's absolute path in `output_file`. Run `.venv/bin/python -m unittest discover -s tests -v` to test the TINT upload without calling OpenAI or the ERP endpoints. Use the virtual environment interpreter for all app commands; the system Python may not have the packages from `requirements.txt`.

Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` for OpenAI or an OpenAI-compatible endpoint; change `LLM_BASE_URL` and `LLM_MODEL` for OpenRouter, Kimi, or another compatible gateway. Set `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and a Claude `LLM_MODEL` for native Anthropic access. Configure the public ERP base URLs in `.env`; the required `college_id` query parameter on each upload is added to those URLs for the fetch. `MASTER_API_KEY` stays empty for these public APIs. The `.env` file is gitignored.

`LLM_TIMEOUT_SECONDS` defaults to 180 for complete multi-page routines. The model request is not automatically retried, so a slow response does not cause duplicate model calls. `HTTP_TIMEOUT_SECONDS` remains 30 for master API requests. Restart the server after changing `.env`.

## Current ERP integration

The server has one reusable HTTP client. Subject and employee requests run concurrently on a cache miss. Successful parsed responses are cached in memory for `MASTER_CACHE_TTL_SECONDS` (default 300) using the full URL, including `college_id`, as the key. Concurrent requests for the same college share one fetch; different colleges do not share records. There is no API request per timetable cell. Each process has its own cache, so multiple server workers can each make a request when their cache expires.

The response adapter accepts arrays and common `data`, `items`, or `results` wrappers. The current public ERP responses use these fields:

| Endpoint | Required fields | Optional fields |
| --- | --- | --- |
| Subjects | `SubjectMasterId`, `Name` | `Code`, `SubjectType` |
| Employees | `EmployeeId` | `Abbreviation`, `EmployeeName` |

The adapter also accepts common snake-case alternatives. Cached faculty records contain the API abbreviation and aliases plus an `initial` generated from the person's name. The resolver matches these identifiers locally. If multiple people match, it selects a unique person whose `Stream` matches the routine department. When the extracted department is empty, it can use a department prefix from a section such as `AIML.2A`, provided that prefix exists among the fetched employee streams. Multiple matches in that department, or no match at all, leave `faculty_id` null for review. The client raises a clear error for unknown response shapes rather than treating missing data as an empty collection. The code never asks the model for IDs.

`SUBJECT_API_BASE_URL` and `FACULTY_API_BASE_URL` are required. `GROUP_API_BASE_URL` and `SECTION_API_BASE_URL` are optional. All configured master endpoints receive the upload's `college_id` and no fixed `department_id`. Group records need an ID and name, and may include `SectionId`; section records need an ID and name. Matching uses the routine's section to scope groups. Student-to-group assignments must come from trusted records.

Faculty API records use `Stream` for the timetable department; their `Department` field is an HR category such as Academics or Admin. Admin records are excluded from teaching faculty matches.

## Current scope

Subject matching scopes ERP records by the routine's stream, course, and semester when those fields are available, then tries exact code, alias, and name before accepting only a uniquely close spelling. Raw punctuation is preserved in output while comparison keys ignore separators. Faculty uses exact abbreviations and aliases before derived initials; short identifiers never use embeddings. Group and section matching is deterministic. Ambiguous or missing matches require review. Room text is preserved without a room ID. Confidence is a binary resolution indicator, not a calibrated probability. There is no automatic second model call; semantic embeddings and optional visual rechecks are future extensions.

The repository has an `origin` remote. Local commits are not pushed automatically.
