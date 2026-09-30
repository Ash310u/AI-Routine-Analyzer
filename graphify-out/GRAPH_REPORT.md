# Graph Report - .  (2026-09-30)

## Corpus Check
- Corpus is ~21,149 words - fits in a single context window. You may not need a graph.

## Summary
- 330 nodes · 1047 edges · 34 communities (16 shown, 18 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 138 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Document Ingestion
- Visual Workbook Conversion
- Subject Matching Services
- Routine Enrichment
- Classroom Resolution
- TINT Grid Extraction
- Master API Parsing
- Engineering Routine Samples
- Processing Architecture
- ECE Routine Samples
- Application Entry Point
- Implementation Documentation
- LLM Dependencies
- AEIE Routine Versions
- AIML Routine Versions
- BME Routine Versions
- ECE Routine Versions
- NSEC Input Profile
- BBA Routine Sample
- BCA Routine Sample
- BESH Routine Sample
- Civil Routine Sample
- CSBS Routine Sample
- CSE Variant One
- CSE Variant Two
- CSE Variant Three
- CSE Variant Four
- CSE Base Routine

## God Nodes (most connected - your core abstractions)
1. `Settings` - 82 edges
2. `RoutineContext` - 57 edges
3. `RoutineExtraction` - 40 edges
4. `ProfilesAndResolutionTest` - 39 edges
5. `MasterAPI` - 35 edges
6. `process_routine()` - 32 edges
7. `SubjectRecord` - 31 edges
8. `_enrich()` - 25 edges
9. `ExtractionError` - 24 edges
10. `FakeModel` - 23 edges

## Surprising Connections (you probably didn't know these)
- `FakeModel` --uses--> `MasterAPI`  [INFERRED]
  tests/test_profiles_and_resolution.py → app/clients/master_api.py
- `ProfilesAndResolutionTest` --uses--> `MasterAPI`  [INFERRED]
  tests/test_profiles_and_resolution.py → app/clients/master_api.py
- `VisualWorkbookTest` --uses--> `MasterAPI`  [INFERRED]
  tests/test_visual_workbook.py → app/clients/master_api.py
- `FakeModel` --uses--> `Settings`  [INFERRED]
  tests/test_profiles_and_resolution.py → app/config.py
- `ProfilesAndResolutionTest` --uses--> `Settings`  [INFERRED]
  tests/test_profiles_and_resolution.py → app/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **NSEC Odd Semester Timetable Inputs** — routines_nsec_aeie_odd_sem_routine_aeie_v1_timetable, routines_nsec_aeie_routine_v3_aeie_timetable, routines_nsec_aiml_odd_sem_routine_aiml_v1_timetable, routines_nsec_aiml_routine_v2_aiml_timetable, routines_nsec_bba_odd_sem_routine_bba_v1_timetable, routines_nsec_bca_odd_sem_routine_bca_v1_timetable, routines_nsec_besh_routine_2026_27_v3_besh_sem1_timetable, routines_nsec_bme_odd_sem_routine_bme_v1_timetable, routines_nsec_bme_odd_sem_routine_bme_v3_timetable, routines_nsec_ce_odd_sem_routine_civil_v1_timetable, routines_nsec_csbs_odd_sem_routine_csbs_v1_timetable, routines_nsec_cse_odd_sem_routine_cse_2_v1_timetable, routines_nsec_cse_odd_sem_routine_cse_3_v1_timetable, routines_nsec_cse_odd_sem_routine_cse_4_v1_timetable, routines_nsec_cse_odd_sem_routine_cse_1_v1_timetable, routines_nsec_cse_odd_sem_routine_cse_v1_timetable, routines_nsec_ece_ece_routine_v_3_timetable, routines_nsec_ece_ecev_3_17_8_26_signed_timetable, readme_nsec_pdf_image_profile [INFERRED 0.85]
- **NSEC 2026 Odd Semester Academic Routines** — routines_nsec_ece_ece_non_dept_odd_2026_slots_v_2_academic_routine, routines_nsec_ece_ece_v2_academic_routine, routines_nsec_ece_odd_sem_routine_ece_v1_academic_routine, routines_nsec_ee_and_e_ce_odd_sem_routine_ee_and_e_ce_academic_routine, routines_nsec_me_odd_sem_routine_me_v1_academic_routine, routines_nsec_me_routine_me_v2_academic_routine [INFERRED 0.95]

## Communities (34 total, 18 thin omitted)

### Community 0 - "Document Ingestion"
Cohesion: 0.08
Nodes (40): DocumentError, image_data_urls(), ValueError, Prepare every PDF page or one image for a single model request., _url(), _column(), _finish(), is_excel_workbook() (+32 more)

### Community 1 - "Visual Workbook Conversion"
Cohesion: 0.11
Nodes (26): build_workbook(), BaseModel, Transcribe a visual timetable into literal Excel cells before routine parsing., Write only transcribed source text; sheet names and styling add no data., VisualCell, VisualSheet, VisualWorkbook, VisualWorkbookExtractor (+18 more)

### Community 2 - "Subject Matching Services"
Cohesion: 0.11
Nodes (19): MasterAPI, Shared server client: one fetch per URL on cache miss, then local matching., Settings, _build_index(), _catalog_key(), _catalog_texts(), embedding_subject_matches(), _LocalEmbeddings (+11 more)

### Community 3 - "Routine Enrichment"
Cohesion: 0.11
Nodes (11): _faculty(), NoRoutineBlocks, The workbook uses a layout other than the supported block grid., FacultyRecord, RoutineContext, _enrich(), Path, ProfilesAndResolutionTest (+3 more)

### Community 4 - "Classroom Resolution"
Cohesion: 0.14
Nodes (29): match_parent(), query_scopes(), Match extracted routine sections to ERP parent classes and their child groups., Find catalog scopes; the session's parent classes decide among candidates., section_token(), _stream_names(), Resolve each routine independently after the shared subject catalog is ready., time (+21 more)

### Community 5 - "TINT Grid Extraction"
Cohesion: 0.12
Nodes (21): _activity(), _clock_value(), _extract_block(), extract_workbook_routines(), Grid, _legacy_grids(), _metadata(), _modern_grids() (+13 more)

### Community 6 - "Master API Parsing"
Cohesion: 0.26
Nodes (15): Any, _child_classes(), _field(), _groups(), MasterDataError, _parent_classes(), ValueError, Unwrap common public API envelopes without silently accepting unknown ones. (+7 more)

### Community 7 - "Engineering Routine Samples"
Cohesion: 0.15
Nodes (13): ECE Non-Department Odd 2026 Slots Academic Routine, Electrical Engineering Second Year Schedule, Information Technology Second Year Schedule, Mechanical Engineering Second Year Schedule, Electrical Engineering and Electrical Computer Engineering Odd Semester Routine, Electrical and Computer Engineering Academic Schedule, Electrical Engineering Academic Schedule, Information Technology Version 1 Odd Semester Academic Routine (+5 more)

### Community 8 - "Processing Architecture"
Cohesion: 0.29
Nodes (7): Canonical Raw Routines Array, Deterministic Validation, Input Profile Selection, Review Reasons, Scoped Master Data Resolution, LLM Document Reading and Backend Resolution Separation, Routine Standardizer

### Community 9 - "ECE Routine Samples"
Cohesion: 0.50
Nodes (4): ECE Version 2 Academic Routine, ECE Second Year Schedule, ECE Version 1 Odd Semester Academic Routine, ECE Second Through Fourth Year Sections

## Knowledge Gaps
- **35 isolated node(s):** `Routine Standardizer`, `Routine Processing Flow`, `Review Reasons`, `LLM-First Implementation Plan`, `LangChain Multimodal Orchestration` (+30 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Subject Matching Services` to `Document Ingestion`, `Visual Workbook Conversion`, `Routine Enrichment`, `TINT Grid Extraction`, `Master API Parsing`?**
  _High betweenness centrality (0.166) - this node is a cross-community bridge._
- **Why does `RoutineContext` connect `Routine Enrichment` to `Document Ingestion`, `Visual Workbook Conversion`, `Subject Matching Services`, `Classroom Resolution`, `TINT Grid Extraction`, `Master API Parsing`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Why does `RoutineExtraction` connect `Classroom Resolution` to `Document Ingestion`, `Visual Workbook Conversion`, `Subject Matching Services`, `Routine Enrichment`, `TINT Grid Extraction`, `Master API Parsing`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `Settings` (e.g. with `MasterAPI` and `MasterDataError`) actually correct?**
  _`Settings` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `RoutineContext` (e.g. with `MasterAPI` and `MasterDataError`) actually correct?**
  _`RoutineContext` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `RoutineExtraction` (e.g. with `ExtractionError` and `ModelServiceError`) actually correct?**
  _`RoutineExtraction` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `ProfilesAndResolutionTest` (e.g. with `MasterAPI` and `Settings`) actually correct?**
  _`ProfilesAndResolutionTest` has 15 INFERRED edges - model-reasoned connections that need verification._