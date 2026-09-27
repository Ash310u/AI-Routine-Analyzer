import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, ReactNode } from "react";
import {
  fieldCounts,
  fields,
  fieldState,
  formatValue,
  isNull,
  readDataset,
  reasonCounts,
  rowSearchText,
} from "./data";
import type { Dataset, FieldSpec, FieldState, RoutineRow } from "./data";
import "./styles.css";

const sampleSources = [
  {
    id: "nsec",
    label: "NSEC · AEIE",
    file: "nsec.json",
    subtitle: "PDF sample",
  },
  {
    id: "tint",
    label: "TINT · CSE",
    file: "tint.json",
    subtitle: "Workbook sample",
  },
] as const;

const number = (value: number) => new Intl.NumberFormat("en-IN").format(value);
const sections: FieldSpec["section"][] = [
  "Master IDs",
  "Routine",
  "Schedule",
  "Activity",
];

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V4m0 0-4 4m4-4 4 4" />
        <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
      </>
    ),
    search: (
      <>
        <circle cx="10.8" cy="10.8" r="6.8" />
        <path d="m16 16 4.5 4.5" />
      </>
    ),
    filter: (
      <>
        <path d="M4 5h16M7 12h10m-7 7h4" />
      </>
    ),
    close: (
      <>
        <path d="M5 5 19 19M19 5 5 19" />
      </>
    ),
    arrow: (
      <>
        <path d="m9 5 7 7-7 7" />
      </>
    ),
    check: (
      <>
        <path d="m5 12 4 4L19 6" />
      </>
    ),
    alert: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v6m0 4h.01" />
      </>
    ),
    file: (
      <>
        <path d="M6 3h9l4 4v14H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
        <path d="M15 3v5h4M8 13h8m-8 4h8" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function Value({
  value,
  className = "",
}: {
  value: unknown;
  className?: string;
}) {
  if (isNull(value))
    return <span className={`null-value ${className}`}>Null</span>;
  if (Array.isArray(value) && !value.length)
    return <span className={`na-value ${className}`}>Empty list</span>;
  return <span className={className}>{formatValue(value)}</span>;
}

function FieldValue({ row, field }: { row: RoutineRow; field: FieldSpec }) {
  const state = fieldState(row, field);
  if (state === "na") return <span className="na-value">Not applicable</span>;
  if (field.id.startsWith("faculty.")) {
    const faculty = row.activity?.faculty ?? [];
    return (
      <span className="faculty-list">
        {faculty.map((person, index) => (
          <span key={index} className="faculty-chip">
            <span>{person.raw || "Faculty"}</span>
            <Value
              value={
                field.id === "faculty.id"
                  ? person.faculty_id
                  : field.id === "faculty.name"
                    ? person.name
                    : person.raw
              }
            />
          </span>
        ))}
      </span>
    );
  }
  return <Value value={field.get(row)} />;
}

function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [source, setSource] = useState("nsec");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [fieldFilters, setFieldFilters] = useState<Record<string, FieldState>>(
    {},
  );
  const [reviewFilter, setReviewFilter] = useState<"all" | "review" | "clear">(
    "all",
  );
  const [reasonFilter, setReasonFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function resetFilters() {
    setFieldFilters({});
    setReviewFilter("all");
    setReasonFilter("all");
    setSearch("");
    setSelectedKey(null);
    setPage(0);
  }

  async function loadSample(id: "nsec" | "tint") {
    const sample = sampleSources.find((item) => item.id === id)!;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${import.meta.env.BASE_URL}samples/${sample.file}`,
      );
      if (!response.ok)
        throw new Error(`Could not load the ${sample.label} sample.`);
      setDataset(readDataset(await response.json(), sample.label));
      setSource(id);
      resetFilters();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not load this sample.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSample("nsec");
  }, []);

  async function loadFile(file?: File) {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      setDataset(readDataset(JSON.parse(await file.text()), file.name));
      setSource("custom");
      resetFilters();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not read this JSON file.",
      );
    } finally {
      setLoading(false);
    }
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    void loadFile(event.target.files?.[0]);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void loadFile(event.dataTransfer.files[0]);
  }

  const rows = dataset?.rows ?? [];
  const counts = useMemo(
    () => fields.map((field) => ({ field, ...fieldCounts(rows, field) })),
    [rows],
  );
  const reasons = useMemo(() => reasonCounts(rows), [rows]);
  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        if (reviewFilter === "review" && !row.requiresReview) return false;
        if (reviewFilter === "clear" && row.requiresReview) return false;
        if (reasonFilter !== "all" && !row.reasons.includes(reasonFilter))
          return false;
        if (
          search.trim() &&
          !rowSearchText(row).includes(search.trim().toLowerCase())
        )
          return false;
        return fields.every(
          (field) =>
            fieldFilters[field.id] === undefined ||
            fieldFilters[field.id] === "any" ||
            fieldState(row, field) === fieldFilters[field.id],
        );
      }),
    [rows, reviewFilter, reasonFilter, search, fieldFilters],
  );
  const selectedRow = rows.find((row) => row.key === selectedKey);
  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const visibleRows = filteredRows.slice(
    currentPage * pageSize,
    (currentPage + 1) * pageSize,
  );
  const reviewCount = rows.filter((row) => row.requiresReview).length;
  const missingIdCount = counts
    .filter((item) => item.field.section === "Master IDs")
    .reduce((sum, item) => sum + item.missing, 0);
  const topMissing = counts
    .filter((item) => item.missing > 0)
    .sort((a, b) => b.missing - a.missing)
    .slice(0, 6);
  const activeFieldCount = Object.values(fieldFilters).filter(
    (value) => value !== "any",
  ).length;

  function setFieldFilter(fieldId: string, state: FieldState) {
    setFieldFilters((current) => ({ ...current, [fieldId]: state }));
    setPage(0);
  }

  function filterToMissing(fieldId: string) {
    setFieldFilter(fieldId, "missing");
    document
      .getElementById("results")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div
      className={`app-shell ${dragging ? "is-dragging" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node))
          setDragging(false);
      }}
      onDrop={onDrop}
    >
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="grid" size={20} />
          </div>
          <div>
            <strong>Routine Review</strong>
            <span>Data inspection studio</span>
          </div>
        </div>
        <div className="sidebar-scroll">
          <div className="sidebar-label">DATA SOURCES</div>
          <div className="source-list">
            {sampleSources.map((item) => (
              <button
                key={item.id}
                className={`source-button ${source === item.id ? "active" : ""}`}
                onClick={() => void loadSample(item.id)}
              >
                <span className="source-icon">
                  <Icon name="file" size={18} />
                </span>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.subtitle}</small>
                </span>
                <Icon name="arrow" size={14} />
              </button>
            ))}
          </div>
          <button
            className={`upload-button ${source === "custom" ? "active" : ""}`}
            onClick={() => fileRef.current?.click()}
          >
            <Icon name="upload" size={17} />
            <span>Open routine JSON</span>
          </button>
          <input
            ref={fileRef}
            className="sr-only"
            type="file"
            accept=".json,application/json"
            onChange={onFileChange}
            aria-label="Open routine JSON"
          />
          <div className="sidebar-divider" />
          <div className="sidebar-heading">
            <div>
              <div className="sidebar-label">FIELD FILTERS</div>
              <span>Filter by value or null</span>
            </div>
            <span className="filter-count">{activeFieldCount}</span>
          </div>
          <div className="filter-note">
            Counts show applicable rows. Faculty ID counts individual faculty
            mentions.
          </div>
          {sections.map((section) => (
            <div className="field-group" key={section}>
              <h3>{section}</h3>
              {counts
                .filter((item) => item.field.section === section)
                .map((item) => (
                  <label
                    className="field-filter"
                    key={item.field.id}
                    title={item.field.description}
                  >
                    <span className="field-filter-top">
                      <span>{item.field.label}</span>
                      <span className="field-counts">
                        <b>{number(item.missing)}</b> null /{" "}
                        {number(item.total)}
                      </span>
                    </span>
                    <select
                      aria-label={`Filter ${item.field.label}`}
                      value={fieldFilters[item.field.id] ?? "any"}
                      onChange={(event) =>
                        setFieldFilter(
                          item.field.id,
                          event.target.value as FieldState,
                        )
                      }
                    >
                      <option value="any">All values</option>
                      <option value="present">Has value</option>
                      <option value="missing">Null only</option>
                    </select>
                  </label>
                ))}
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          <span className="footer-dot" /> Local preview · no upload to server
        </div>
      </aside>

      <main className="main-content">
        <div className="topbar">
          <span className="breadcrumb">
            Workspace <Icon name="arrow" size={14} />{" "}
            <strong>Routine review</strong>
          </span>
          <span className="topbar-pill">Standalone preview</span>
        </div>
        <div className="content-wrap">
          <header className="page-header">
            <div>
              <div className="eyebrow">ROUTINE INTELLIGENCE / REVIEW</div>
              <h1>See every gap in your routine data.</h1>
              <p>
                Inspect extracted values, unresolved IDs, and review reasons
                before using a routine.
              </p>
            </div>
            <button
              className="primary-button"
              onClick={() => fileRef.current?.click()}
            >
              <Icon name="upload" size={17} /> Open JSON
            </button>
          </header>
          {error && (
            <div className="error-banner" role="alert">
              <Icon name="alert" />
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {loading && (
            <div className="loading-banner">Loading routine data…</div>
          )}
          {dataset && (
            <>
              <div className="dataset-line">
                <span className="dataset-icon">
                  <Icon name="file" size={19} />
                </span>
                <div>
                  <strong>{dataset.label}</strong>
                  <span>
                    College ID {dataset.collegeId ?? "unknown"} ·{" "}
                    {dataset.sourceType.replaceAll("_", " ")} ·{" "}
                    {number(dataset.routines.length)} routine
                    {dataset.routines.length === 1 ? "" : "s"}
                  </span>
                </div>
                <span className="live-badge">
                  <span /> Data loaded
                </span>
              </div>
              <section className="summary-grid" aria-label="Summary">
                <div className="summary-card">
                  <div className="summary-label">
                    Activities & slots <Icon name="grid" />
                  </div>
                  <div className="summary-number">{number(rows.length)}</div>
                  <div className="summary-sub">
                    One row per activity; empty slots included
                  </div>
                </div>
                <div className="summary-card">
                  <div className="summary-label">
                    Needs review <Icon name="alert" />
                  </div>
                  <div className="summary-number amber">
                    {number(reviewCount)}
                  </div>
                  <div className="summary-sub">
                    {rows.length
                      ? Math.round((reviewCount / rows.length) * 100)
                      : 0}
                    % of displayed records
                  </div>
                </div>
                <div className="summary-card">
                  <div className="summary-label">
                    Null master IDs <Icon name="filter" />
                  </div>
                  <div className="summary-number red">
                    {number(missingIdCount)}
                  </div>
                  <div className="summary-sub">Across applicable ID fields</div>
                </div>
                <div className="summary-card">
                  <div className="summary-label">
                    Review reason types <Icon name="file" />
                  </div>
                  <div className="summary-number">{number(reasons.length)}</div>
                  <div className="summary-sub">
                    Distinct issues found in this sample
                  </div>
                </div>
              </section>
              <section className="insights-grid" aria-label="Data insights">
                <div className="panel">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">COMPLETENESS</span>
                      <h2>Fields with null values</h2>
                    </div>
                    <span className="panel-hint">Click a field to filter</span>
                  </div>
                  <div className="missing-bars">
                    {topMissing.length ? (
                      topMissing.map((item) => (
                        <button
                          key={item.field.id}
                          className="missing-bar-row"
                          onClick={() => filterToMissing(item.field.id)}
                          title={item.field.description}
                        >
                          <span className="bar-label">{item.field.label}</span>
                          <span className="bar-track">
                            <span
                              style={{
                                width: `${item.total ? Math.max(3, (item.missing / item.total) * 100) : 0}%`,
                              }}
                            />
                          </span>
                          <span className="bar-count">
                            {number(item.missing)}{" "}
                            <small>/ {number(item.total)}</small>
                          </span>
                        </button>
                      ))
                    ) : (
                      <div className="empty-small">
                        No null values in applicable fields.
                      </div>
                    )}
                  </div>
                </div>
                <div className="panel">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">REVIEW QUEUE</span>
                      <h2>Why rows need attention</h2>
                    </div>
                    <span className="panel-hint">Select a reason</span>
                  </div>
                  <div className="reason-list">
                    {reasons.length ? (
                      reasons.slice(0, 6).map((item) => (
                        <button
                          key={item.reason}
                          className={`reason-item ${reasonFilter === item.reason ? "selected" : ""}`}
                          onClick={() => {
                            setReasonFilter(
                              reasonFilter === item.reason
                                ? "all"
                                : item.reason,
                            );
                            setPage(0);
                            document
                              .getElementById("results")
                              ?.scrollIntoView({ behavior: "smooth" });
                          }}
                        >
                          <span className="reason-dot" />
                          <span title={item.reason}>{item.reason}</span>
                          <strong>{number(item.count)}</strong>
                        </button>
                      ))
                    ) : (
                      <div className="empty-small">
                        No review reasons were supplied.
                      </div>
                    )}
                  </div>
                </div>
              </section>
              <section className="results-panel" id="results">
                <div className="results-heading">
                  <div>
                    <span className="eyebrow">RECORD EXPLORER</span>
                    <h2>
                      Routine records <span>{number(filteredRows.length)}</span>
                    </h2>
                  </div>
                  <button
                    className="text-button"
                    onClick={resetFilters}
                    disabled={
                      !activeFieldCount &&
                      reviewFilter === "all" &&
                      reasonFilter === "all" &&
                      !search
                    }
                  >
                    Clear all filters
                  </button>
                </div>
                <div className="toolbar">
                  <div className="search-box">
                    <Icon name="search" size={18} />
                    <input
                      aria-label="Search routine records"
                      placeholder="Search subject, faculty, section, room…"
                      value={search}
                      onChange={(event) => {
                        setSearch(event.target.value);
                        setPage(0);
                      }}
                    />
                  </div>
                  <div
                    className="segmented"
                    role="group"
                    aria-label="Review status"
                  >
                    {(
                      [
                        ["all", "All"],
                        ["review", "Needs review"],
                        ["clear", "Clear"],
                      ] as const
                    ).map(([id, label]) => (
                      <button
                        key={id}
                        className={reviewFilter === id ? "selected" : ""}
                        onClick={() => {
                          setReviewFilter(id);
                          setPage(0);
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="reason-filter">
                    <Icon name="filter" size={16} />
                    <select
                      aria-label="Filter review reason"
                      value={reasonFilter}
                      onChange={(event) => {
                        setReasonFilter(event.target.value);
                        setPage(0);
                      }}
                    >
                      <option value="all">All reasons</option>
                      {reasons.map((item) => (
                        <option key={item.reason} value={item.reason}>
                          {item.reason}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                {activeFieldCount > 0 && (
                  <div className="active-filters">
                    {fields
                      .filter(
                        (field) =>
                          fieldFilters[field.id] &&
                          fieldFilters[field.id] !== "any",
                      )
                      .map((field) => (
                        <button
                          key={field.id}
                          onClick={() => setFieldFilter(field.id, "any")}
                        >
                          {field.label}:{" "}
                          {fieldFilters[field.id] === "missing"
                            ? "Null"
                            : "Has value"}{" "}
                          <Icon name="close" size={13} />
                        </button>
                      ))}
                  </div>
                )}
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Schedule</th>
                        <th>Section</th>
                        <th>Subject</th>
                        <th>Subject ID</th>
                        <th>Faculty</th>
                        <th>Faculty ID</th>
                        <th>Group</th>
                        <th>Room</th>
                        <th>Review</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRows.map((row) => (
                        <tr
                          key={row.key}
                          onClick={() => setSelectedKey(row.key)}
                          tabIndex={0}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") setSelectedKey(row.key);
                          }}
                          aria-label={`Open ${row.slot.day ?? "unknown day"} activity details`}
                        >
                          <td>
                            <div className="cell-strong">
                              <Value value={row.slot.day} />
                            </div>
                            <div className="cell-muted">
                              {row.slot.start_time ||
                                `Period ${row.slot.start_period ?? "—"}`}{" "}
                              –{" "}
                              {row.slot.end_time || row.slot.end_period || "—"}
                            </div>
                          </td>
                          <td>
                            <div className="cell-strong">
                              <Value value={row.routine.section?.raw} />
                            </div>
                            <div className="cell-muted">
                              {row.routine.department || "Department null"}
                            </div>
                          </td>
                          <td>
                            <div className="cell-strong">
                              <Value value={row.activity?.subject?.raw} />
                            </div>
                            <div className="cell-muted">
                              <Value value={row.activity?.subject?.code_raw} />
                            </div>
                          </td>
                          <td>
                            <Value
                              value={row.activity?.subject?.subject_master_id}
                            />
                          </td>
                          <td>
                            {row.activity?.faculty?.length ? (
                              row.activity.faculty
                                .map((person) => person.raw || "Null")
                                .join(", ")
                            ) : (
                              <span className="na-value">—</span>
                            )}
                          </td>
                          <td>
                            {row.activity?.faculty?.length ? (
                              row.activity.faculty.map((person, index) => (
                                <span key={index} className="table-faculty-id">
                                  <Value value={person.faculty_id} />
                                </span>
                              ))
                            ) : (
                              <span className="na-value">N/A</span>
                            )}
                          </td>
                          <td>
                            {row.activity?.group ? (
                              <Value value={row.activity.group.raw} />
                            ) : (
                              <span className="na-value">Whole section</span>
                            )}
                          </td>
                          <td>
                            <Value value={row.activity?.room?.raw} />
                          </td>
                          <td>
                            {row.requiresReview ? (
                              <span className="status-chip review">
                                Review · {row.reasons.length || 1}
                              </span>
                            ) : (
                              <span className="status-chip clear">Clear</span>
                            )}
                          </td>
                          <td>
                            <Icon name="arrow" size={16} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!filteredRows.length && (
                    <div className="empty-results">
                      <Icon name="search" size={26} />
                      <strong>No records match these filters</strong>
                      <span>
                        Try changing the field filters or search term.
                      </span>
                      <button onClick={resetFilters}>Clear filters</button>
                    </div>
                  )}
                </div>
                <div className="table-footer">
                  <span>
                    Showing{" "}
                    {filteredRows.length
                      ? number(currentPage * pageSize + 1)
                      : 0}
                    –
                    {number(
                      Math.min(
                        (currentPage + 1) * pageSize,
                        filteredRows.length,
                      ),
                    )}{" "}
                    of {number(filteredRows.length)}
                  </span>
                  <div>
                    <button
                      disabled={currentPage === 0}
                      onClick={() => setPage(currentPage - 1)}
                    >
                      Previous
                    </button>
                    <span>
                      Page {currentPage + 1} of {pageCount}
                    </span>
                    <button
                      disabled={currentPage >= pageCount - 1}
                      onClick={() => setPage(currentPage + 1)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </section>
              <p className="footnote">
                This standalone UI reads standardized JSON in your browser.
                Sample files are shortened excerpts of saved NSEC and TINT
                pipeline output. “Null” means an applicable value is absent;
                “N/A” means the field does not apply to that record.
              </p>
            </>
          )}
        </div>
      </main>
      {dragging && (
        <div className="drop-overlay">
          <Icon name="upload" size={34} />
          <strong>Drop your routine JSON here</strong>
        </div>
      )}
      {selectedRow && (
        <div
          className="drawer-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedKey(null);
          }}
        >
          <aside
            className="detail-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Routine record details"
          >
            <div className="drawer-header">
              <div>
                <span className="eyebrow">RECORD DETAILS</span>
                <h2>
                  {selectedRow.slot.day || "Unknown day"} ·{" "}
                  {selectedRow.activity?.subject?.raw ||
                    selectedRow.slot.slot_type ||
                    "Activity"}
                </h2>
                <p>
                  Routine {selectedRow.routineIndex + 1} · Slot{" "}
                  {selectedRow.slotIndex + 1}
                  {selectedRow.activityIndex !== null
                    ? ` · Activity ${selectedRow.activityIndex + 1}`
                    : ""}
                </p>
              </div>
              <button
                className="icon-button"
                aria-label="Close details"
                onClick={() => setSelectedKey(null)}
              >
                <Icon name="close" />
              </button>
            </div>
            <div className="drawer-body">
              <div
                className={`drawer-status ${selectedRow.requiresReview ? "needs-review" : ""}`}
              >
                <Icon name={selectedRow.requiresReview ? "alert" : "check"} />
                <div>
                  <strong>
                    {selectedRow.requiresReview
                      ? "Needs review"
                      : "No review flagged"}
                  </strong>
                  <span>
                    {selectedRow.reasons.length
                      ? selectedRow.reasons.join(" · ")
                      : "No review reasons were supplied for this record."}
                  </span>
                </div>
              </div>
              {sections.map((section) => (
                <section className="detail-section" key={section}>
                  <h3>{section}</h3>
                  <div className="detail-grid">
                    {fields
                      .filter((field) => field.section === section)
                      .map((field) => (
                        <div className="detail-field" key={field.id}>
                          <span>{field.label}</span>
                          <strong>
                            <FieldValue row={selectedRow} field={field} />
                          </strong>
                        </div>
                      ))}
                  </div>
                </section>
              ))}
              <details className="raw-details">
                <summary>View original record JSON</summary>
                <pre>
                  {JSON.stringify(
                    {
                      routine: selectedRow.routine,
                      slot: selectedRow.slot,
                      activity: selectedRow.activity,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export default App;
