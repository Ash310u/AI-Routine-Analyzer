# Faculty recognition and admin review plan

Branch: `codex/faculty-context-review`

## Goal

Resolve faculty IDs for every college and routine profile using the employee API,
the extracted routine's department and section, and explicit admin decisions.
Keep one canonical routine schema after extraction. The API `college_id` selects
the employee list; the current per-URL cache remains the source for that upload.

## Proposed flow

1. **Prepare faculty records once per API cache fill.** Parse employee ID, name,
   API abbreviation, aliases, teaching department (`Stream`), and any available
   teaching or profile fields. Generate letter initials from names, but preserve
   explicit suffixes such as `DB1` or `DB12`. Keep raw API values alongside
   normalized search keys. Index records by college ID and employee ID.
2. **Resolve exact identifiers first.** For each `faculty_raw`, try the full
   identifier, then the suffix after the last underscore. Match API abbreviation,
   confirmed aliases, and generated name initials. If one employee matches,
   return that ID. For collisions, prefer an employee in the routine's teaching
   department. Keep the current section-based department fallback only when the
   routine department is absent and the section prefix is unambiguous.
3. **Retrieve candidates when exact resolution is insufficient.** Build a small
   embedding index from descriptive employee data supplied by the API (name,
   teaching department, known subjects or assignments, and confirmed aliases
   when available). Retrieve within the requested college, using the routine's
   department, section, subject, and raw faculty token as query context. Embedding
   scores only rank candidates; they do not prove that short initials refer to a
   particular person. Do not send unrelated personal fields to the model.
4. **Present evidence for admin review.** For unresolved or ambiguous mentions,
   return a review item containing the raw initial, routine and slot location,
   department and section, candidate IDs and names, matching abbreviation or
   alias, teaching department, and any relevant assignment evidence. Include
   explicit `unresolved` and `no suitable candidate` choices. Never silently
   choose an ID from vector similarity alone.
5. **Save decisions and revalidate.** An admin selects an employee ID or leaves
   it unresolved. Validate that the selected ID exists in the same college's
   cached or refreshed employee list. Persist a confirmed alias scoped to the
   college and, when necessary, department or section; record the raw token,
   chosen ID, reviewer, and timestamp. Subsequent uploads check these confirmed
   aliases before embeddings. Re-run routine validation after applying a choice.

## Integration points

- Extend `FacultyRecord` and `MasterAPI._faculty` only for fields actually
  present in the ERP response; keep the existing 300-second parsed-record cache.
- Put candidate retrieval and decision storage behind separate faculty services.
  Both NSEC LLM extraction and TINT workbook parsing call the same service after
  their profile adapters.
- Extend the final faculty result with resolution status and candidate evidence,
  while preserving `faculty_id: null` for unresolved mentions. Add review
  endpoints and a UI view for candidate selection.
- Make the embedding provider and index optional. Exact and alias matching must
  continue to work if the embedding service is unavailable.

## Acceptance checks

- One LLM response containing CSE and ECE routines with the same initial gives
  each routine its own department's faculty ID when each is unique.
- Numbered abbreviations match exactly; an unlisted number remains unresolved.
- Two employees with the same initial in the same department produce a review
  item, even when embeddings rank one higher.
- The admin's selected employee ID survives a new upload through a scoped alias;
  a conflicting college or department never inherits that decision.
- An invalid, missing, or cross-college employee ID is rejected at review time.
- Employee API calls remain per college/cache miss, not per faculty mention.

## Scope clarification

The phrase "certificate recognition and personal information" needs confirmation.
This plan treats it as relevant employee profile data from the ERP API. Recognition
of separate certificate documents would be a distinct input workflow and should
be specified before adding it to this branch.
