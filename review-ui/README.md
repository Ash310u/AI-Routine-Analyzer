# Routine Review UI

Standalone React preview for inspecting standardized routine JSON. It does not call the routine API or modify the JSON it opens.

```bash
cd review-ui
npm install --include=dev
npm run dev
```

Open the URL printed by Vite. The NSEC AEIE and TINT CSE buttons load short excerpts of existing pipeline outputs. Use **Open JSON** or drag a `.json` file onto the page to inspect a full result locally in your browser. Current API responses use `routines[]`, with metadata and `slots[]` on each routine. The viewer also accepts older saved files containing a single bare routine object.

The left panel shows each field's null and applicable counts and offers **All values**, **Has value**, and **Null only** filters. The record table also supports text search, review status, and review reason filters. Select a row to see all available fields and its original JSON. A missing faculty ID count represents faculty mentions, while **Null only** selects activities with at least one unresolved faculty ID. Whole-section activities have no group, so group fields are marked **Not applicable** rather than null.

```bash
npm run build
```
