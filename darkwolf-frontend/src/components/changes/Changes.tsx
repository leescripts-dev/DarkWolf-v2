import { useEffect, useState } from "react";
import "flag-icons/css/flag-icons.min.css";
import { displayOrganizationName } from "../../utils/organization";
import { countryFlagCode } from "../../utils/country";
import "./Changes.css";

type Change = {
  event_id: string;
  source_id: string;
  event_type: string;
  detected_at: string;
  leak_date?: string | null;
  published_at?: string | null;
  organization: string;
  country: string | null;
  domains: string[];
  description: string[];
  ransomware_group: string | null;
  change_description: string;
  changed_fields: string[];
  changes: Record<
    string,
    {
      previous: unknown;
      current: unknown;
    }
  >;
  observation_id: string | null;
  previous_observation_id: string | null;
};

type ChangeDetails = {
  event: {
    event_id: string;
    source: string;
    source_id: string;
    collection_run_id: string;
    event_type: string;
    detected_at: string;
    changed_fields: string[];
    changes: Record<
      string,
      {
        previous: unknown;
        current: unknown;
      }
    >;
    details: Record<string, unknown>;
  };

  organization: {
    id?: string | null;
    name?: string | null;
    [key: string]: unknown;
  } | null;

  domains: string[];

  ransomware_group: string | null;

  previous_snapshot: Record<
    string,
    unknown
  > | null;

  current_snapshot: Record<
    string,
    unknown
  > | null;

  previous_raw_evidence: {
    content_type?: string;
    response_body?: unknown;
    screenshot_url?: string;
    endpoint?: string;
    [key: string]: unknown;
  } | null;

  current_raw_evidence: {
    content_type?: string;
    response_body?: unknown;
    screenshot_url?: string;
    endpoint?: string;
    [key: string]: unknown;
  } | null;
};

const getChangeLabel = (eventType: string) => {
  const labels: Record<string, string> = {
    VICTIM_DISCOVERED: "VICTIM DISCOVERED",
    VICTIM_DISCOVERED_AND_DISCLOSED: "VICTIM DISCOVERED · DATA DISCLOSED",
    DISCLOSURE_DISCOVERED: "DATA DISCLOSED",
    DISCLOSURE_SIZE_CHANGED: "DISCLOSURE SIZE CHANGED",
    DISCLOSURE_CONTENT_CHANGED: "DISCLOSURE CONTENT CHANGED",
    LEAK_DATE_CHANGED: "LEAK DATE CHANGED",
  };
  return labels[eventType] ?? eventType.replaceAll("_", " ");
};

const isDisclosureChange = (eventType: string) =>
  eventType === "DISCLOSURE_DISCOVERED" || eventType === "VICTIM_DISCOVERED_AND_DISCLOSED";

function formatValue(
  value: unknown,
) {
  if (value === null || value === undefined) {
    return "None";
  }

  if (Array.isArray(value)) {
    return value.join(", ");
  }

  if (
    typeof value === "object"
  ) {
    return JSON.stringify(
      value,
      null,
      2,
    );
  }

  return String(value);
}

function buildEvidenceHtml(
  evidence:
    | ChangeDetails["current_raw_evidence"]
    | ChangeDetails["previous_raw_evidence"],
) {
  if (!evidence) {
    return `
      <html>
        <body style="
          margin:0;
          padding:20px;
          background:#050b10;
          color:#8ba4b8;
          font-family:Arial,sans-serif;
        ">
          No captured evidence available.
        </body>
      </html>
    `;
  }

  const body =
    evidence.response_body;

  const content =
    typeof body === "string"
      ? body
      : JSON.stringify(
          body,
          null,
          2,
        );

  const escaped = content
    .replace(
      /&/g,
      "&amp;",
    )
    .replace(
      /</g,
      "&lt;",
    )
    .replace(
      />/g,
      "&gt;",
    );

  return `
    <html>
      <head>
        <style>
          body {
            margin: 0;
            padding: 20px;
            background: #050b10;
            color: #b7c9d6;
            font-family:
              Consolas,
              "Courier New",
              monospace;
            font-size: 12px;
            line-height: 1.6;
          }

          pre {
            white-space: pre-wrap;
            word-break: break-word;
            margin: 0;
          }
        </style>
      </head>

      <body>
        <pre>${escaped}</pre>
      </body>
    </html>
  `;
}

function Changes() {
  const [
    changes,
    setChanges,
  ] = useState<Change[]>([]);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState<string | null>(
    null,
  );

  const [
    selectedChange,
    setSelectedChange,
  ] = useState<ChangeDetails | null>(
    null,
  );

  const [
    inspectLoading,
    setInspectLoading,
  ] = useState(false);

  const [
    inspectError,
    setInspectError,
  ] = useState<string | null>(
    null,
  );

  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState("all");
  const [eventFilter, setEventFilter] = useState("all");
  const [dateSortOrder, setDateSortOrder] = useState<"desc" | "asc">("desc");

  const groups = [...new Set(changes.map((change) => change.ransomware_group).filter((group): group is string => Boolean(group)))].sort();
  const changeDate = (change: Change) =>
    Date.parse(change.leak_date || change.published_at || "") || Date.parse(change.detected_at) || 0;
  const newestFirst = (items: Change[]) => [...items].sort((left, right) => {
    const delta = changeDate(right) - changeDate(left);
    if (delta) return delta;
    const detectedDelta = (Date.parse(right.detected_at) || 0) - (Date.parse(left.detected_at) || 0);
    if (detectedDelta) return detectedDelta;
    return right.event_id.localeCompare(left.event_id);
  });
  const filteredChanges = changes.filter((change) => {
    const needle = search.trim().toLowerCase();
    const searchable = [change.organization, ...change.domains, change.ransomware_group ?? "", change.change_description];
    return (!needle || searchable.some((value) => value.toLowerCase().includes(needle)))
      && (groupFilter === "all" || change.ransomware_group === groupFilter)
      && (eventFilter === "all" || (eventFilter === "DISCLOSURE_DISCOVERED"
        ? isDisclosureChange(change.event_type)
        : change.event_type === eventFilter));
  });
  const eventTypes = [...new Set(changes.map((change) => change.event_type))]
    .filter((type) => type !== "VICTIM_DISCOVERED_AND_DISCLOSED");
  if (changes.some((change) => change.event_type === "VICTIM_DISCOVERED_AND_DISCLOSED")
    && !eventTypes.includes("DISCLOSURE_DISCOVERED")) {
    eventTypes.push("DISCLOSURE_DISCOVERED");
  }
  const orderedFilteredChanges = [...filteredChanges].sort((left, right) => {
    const delta = changeDate(right) - changeDate(left);
    if (delta) return dateSortOrder === "desc" ? delta : -delta;
    return (Date.parse(right.detected_at) || 0) - (Date.parse(left.detected_at) || 0);
  });

  useEffect(() => {
    const fetchChanges = async () => {
      const response = await fetch(
        "http://127.0.0.1:8000/api/v1/changes?limit=5000",
      );
      if (!response.ok) {
        throw new Error("Failed to fetch changes");
      }
      const recent = await response.json() as Change[];
      if (recent.length < 500) return newestFirst(recent);

      // Older backend builds cap unfiltered results at 500. Fetch by group in
      // that case so groups with older events (including Kazu) are not hidden.
      const groupResponse = await fetch("http://127.0.0.1:8000/api/v1/dashboard/groups", { cache: "no-store" });
      if (!groupResponse.ok) return newestFirst(recent);
      const groupNames = await groupResponse.json() as string[];
      const groupedResults: Change[][] = new Array(groupNames.length);
      let nextGroupIndex = 0;
      const workers = Array.from(
        { length: Math.min(6, groupNames.length) },
        async () => {
          while (nextGroupIndex < groupNames.length) {
            const index = nextGroupIndex++;
            const group = groupNames[index];
            const query = new URLSearchParams({ limit: "5000", group });
            const result = await fetch(`http://127.0.0.1:8000/api/v1/changes?${query.toString()}`);
            if (!result.ok) throw new Error(`Failed to fetch changes for ${group}`);
            groupedResults[index] = await result.json() as Change[];
          }
        },
      );
      await Promise.all(workers);
      const unique = new Map<string, Change>();
      for (const change of [...recent, ...groupedResults.flat()]) {
        unique.set(change.event_id, change);
      }
      return newestFirst([...unique.values()]);
    };

    fetchChanges()
      .then((data) => {
        setChanges(data);
      })
      .catch((error) => {
        console.error(
          "Failed to load changes:",
          error,
        );

        setError(
          "Failed to load changes",
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const inspectChange = async (
    eventId: string,
  ) => {
    setInspectLoading(true);
    setInspectError(null);

    try {
      const response =
        await fetch(
          `http://127.0.0.1:8000/api/v1/changes/${eventId}`,
        );

      if (!response.ok) {
        throw new Error(
          "Failed to fetch change details",
        );
      }

      const data: ChangeDetails =
        await response.json();

      setSelectedChange(data);
    } catch (error) {
      console.error(
        "Failed to load change details:",
        error,
      );

      setInspectError(
        "Failed to load change details",
      );
    } finally {
      setInspectLoading(false);
    }
  };

  const closeInspect = () => {
    setSelectedChange(null);
    setInspectError(null);
  };

  return (
    <div className="changes-page">
      <div className="changes-header">
        <div>
          <div className="changes-title">
            Changes{" "}
            <span>
              ({changes.length})
            </span>
          </div>

          <div className="changes-subtitle">
            Detected changes across
            monitored threat intelligence
          </div>
        </div>
      </div>

      <section className="changes-panel">
        <div className="changes-toolbar">
          <div className="changes-search">
            <span className="search-icon">
              ⌕
            </span>

            <input
              type="text"
              placeholder="Search organization, domain..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <select className="filter-button" aria-label="Filter by ransomware group" value={groupFilter} onChange={(event) => setGroupFilter(event.target.value)}>
            <option value="all">All ransomware groups</option>
            {groups.map((group) => <option key={group} value={group}>{group}</option>)}
          </select>

          <select className="filter-button" aria-label="Filter by change type" value={eventFilter} onChange={(event) => setEventFilter(event.target.value)}>
            <option value="all">All change types</option>
            {eventTypes.sort().map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
          </select>

          <button
            className="filter-button"
            aria-label={`Sort leak dates ${dateSortOrder === "desc" ? "newest first" : "oldest first"}`}
            title="Toggle leak date order"
            onClick={() => setDateSortOrder((order) => order === "desc" ? "asc" : "desc")}
          >
            Date: {dateSortOrder === "desc" ? "newest first" : "oldest first"}
            <span>{dateSortOrder === "desc" ? "↓" : "↑"}</span>
          </button>

          <button className="reset-button" onClick={() => { setSearch(""); setGroupFilter("all"); setEventFilter("all"); setDateSortOrder("desc"); }}>
            Reset
          </button>
        </div>

        <div className="changes-table-wrapper">
          <table className="changes-table">
            <thead>
              <tr>
                <th>
                  ORGANIZATION
                </th>

                <th>
                  DOMAIN
                </th>

                <th>
                  CHANGE DESCRIPTION
                </th>

                <th>
                  RANSOMWARE GROUP
                </th>

                <th>
                  CHANGE
                </th>

                <th>
                  LEAK DATE
                </th>

                <th></th>
              </tr>
            </thead>

            <tbody>
              {loading && (
                <tr>
                  <td
                    colSpan={7}
                    className="changes-empty"
                  >
                    Loading changes...
                  </td>
                </tr>
              )}

              {!loading &&
                error && (
                  <tr>
                    <td
                      colSpan={7}
                      className="changes-empty"
                    >
                      {error}
                    </td>
                  </tr>
                )}

              {!loading &&
                !error &&
                orderedFilteredChanges.length ===
                  0 && (
                  <tr>
                    <td
                      colSpan={7}
                      className="changes-empty"
                    >
                      {changes.length
                        ? "No changes match these filters"
                        : "No changes detected since the monitoring baseline. New changes will appear after the next successful scrape."}
                    </td>
                  </tr>
                )}

              {!loading &&
                !error &&
                orderedFilteredChanges.map(
                  (change) => (
                    <tr
                      key={
                        change.event_id
                      }
                    >
                      {/* Organization + Country */}
                      <td>
                        <div className="organization-cell">
                          {change.country && countryFlagCode(change.country) && (
                            <span
                              className={`fi fi-${countryFlagCode(change.country)} country-flag`}
                              role="img"
                              aria-label={`${change.country} flag`}
                              title={change.country}
                            />
                          )}

                          <span>
                            {
                              displayOrganizationName(change.organization, change.ransomware_group)
                            }
                          </span>
                        </div>
                      </td>

                      {/* Domain */}
                      <td>
                        {change.domains
                          .length >
                        0
                          ? change.domains.join(
                              ", ",
                            )
                          : "—"}
                      </td>

                      {/* Human-readable event summary */}
                      <td>
                        <div className="change-description">
                          {change.change_description || "Change details are not available."}
                        </div>
                      </td>

                      {/* Ransomware */}
                      <td>
                        <div className="ransomware-cell">
                          <span className="ransomware-beacon" />

                          <span>
                            {change.ransomware_group ??
                              "—"}
                          </span>
                        </div>
                      </td>

                      {/* Change */}
                      <td>
                        <span className="change-badge yes" title={change.change_description}>
                          {getChangeLabel(change.event_type)}
                        </span>
                      </td>

                      {/* Date */}
                      <td>
                        {new Date(changeDate(change)).toLocaleDateString()}
                      </td>

                      {/* Inspect */}
                      <td>
                        <button
                          className="inspect-button"
                          onClick={() =>
                            inspectChange(
                              change.event_id,
                            )
                          }
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ),
                )}
            </tbody>
          </table>
        </div>
      </section>

      {/* INSPECT OVERLAY */}
      {(inspectLoading ||
        selectedChange ||
        inspectError) && (
        <div
          className="inspect-overlay"
          onClick={closeInspect}
        >
          <div
            className="inspect-panel"
            onClick={(event) =>
              event.stopPropagation()
            }
          >
            <div className="inspect-header">
              <div>
                <div className="inspect-title">
                  Inspect Change
                </div>

                <div className="inspect-subtitle">
                  Detailed event and
                  evidence analysis
                </div>
              </div>

              <button
                className="inspect-close"
                onClick={closeInspect}
              >
                ×
              </button>
            </div>

            {inspectLoading && (
              <div className="inspect-loading">
                Loading change details...
              </div>
            )}

            {inspectError && (
              <div className="inspect-error">
                {inspectError}
              </div>
            )}

            {selectedChange &&
              !inspectLoading && (
                <div className="inspect-content">

                  {/* EVENT SUMMARY */}
                  <section className="inspect-section">
                    <div className="inspect-section-title">
                      EVENT
                    </div>

                    <div className="inspect-event-grid">
                      <div>
                        <span>
                          Event Type
                        </span>

                        <strong>
                          {
                            selectedChange
                              .event
                              .event_type
                          }
                        </strong>
                      </div>

                      <div>
                        <span>
                          Organization
                        </span>

                        <strong>
                          {selectedChange
                            .organization
                            ?.name ??
                            "Unknown"}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Ransomware Group
                        </span>

                        <strong>
                          {selectedChange.ransomware_group ??
                            "—"}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Detected
                        </span>

                        <strong>
                          {new Date(
                            selectedChange
                              .event
                              .detected_at,
                          ).toLocaleString()}
                        </strong>
                      </div>
                    </div>
                  </section>

                  {/* CHANGED FIELDS */}
                  <section className="inspect-section">
                    <div className="inspect-section-title">
                      CHANGES DETECTED
                    </div>

                    <div className="change-comparison">
                      {selectedChange.event.changed_fields.map(
                        (field) => {
                          const change =
                            selectedChange
                              .event
                              .changes[
                              field
                            ];

                          return (
                            <div
                              className="change-comparison-row"
                              key={field}
                            >
                              <div className="change-field">
                                {field
                                  .replace(
                                    /_/g,
                                    " ",
                                  )
                                  .toUpperCase()}
                              </div>

                              <div className="change-before">
                                <span>
                                  BEFORE
                                </span>

                                <pre>
                                  {formatValue(
                                    change
                                      ?.previous,
                                  )}
                                </pre>
                              </div>

                              <div className="change-arrow">
                                →
                              </div>

                              <div className="change-after">
                                <span>
                                  CURRENT
                                </span>

                                <pre>
                                  {formatValue(
                                    change
                                      ?.current,
                                  )}
                                </pre>
                              </div>
                            </div>
                          );
                        },
                      )}
                    </div>
                  </section>

                  {/* SNAPSHOTS */}
                  <section className="inspect-section">
                    <div className="inspect-section-title">
                      SNAPSHOTS
                    </div>

                    <div className="snapshot-grid">
                      <div className="snapshot-card">
                        <div className="snapshot-title">
                          PREVIOUS SNAPSHOT
                        </div>

                        <pre>
                          {JSON.stringify(
                            selectedChange.previous_snapshot,
                            null,
                            2,
                          )}
                        </pre>
                      </div>

                      <div className="snapshot-card">
                        <div className="snapshot-title">
                          CURRENT SNAPSHOT
                        </div>

                        <pre>
                          {JSON.stringify(
                            selectedChange.current_snapshot,
                            null,
                            2,
                          )}
                        </pre>
                      </div>
                    </div>
                  </section>

                  <section className="inspect-section">
                    <div className="inspect-section-title">SCREENSHOT CHANGE PROOF</div>
                    <div className="screenshot-proof-grid">
                      {([
                        ["PREVIOUS CAPTURE", selectedChange.previous_raw_evidence],
                        ["CURRENT CAPTURE", selectedChange.current_raw_evidence],
                      ] as const).map(([label, evidence]) => (
                        <div className="screenshot-proof-card" key={label}>
                          <div className="snapshot-title">{label}</div>
                          {evidence?.screenshot_url ? (
                            <a href={`http://127.0.0.1:8000${evidence.screenshot_url}`} target="_blank" rel="noreferrer">
                              <img src={`http://127.0.0.1:8000${evidence.screenshot_url}`} alt={`${label.toLowerCase()} of the source page`} />
                            </a>
                          ) : <div className="screenshot-missing">No screenshot was captured for this snapshot.</div>}
                          {evidence?.endpoint && <div className="evidence-endpoint">{evidence.endpoint}</div>}
                        </div>
                      ))}
                    </div>
                  </section>

                  {/* CAPTURED EVIDENCE */}
                  <section className="inspect-section">
                    <div className="inspect-section-title">
                      CAPTURED SOURCE EVIDENCE
                    </div>

                    <div className="evidence-frame">
                      <iframe
                        title="Captured source evidence"
                        srcDoc={buildEvidenceHtml(
                          selectedChange.current_raw_evidence,
                        )}
                      />
                    </div>
                  </section>

                </div>
              )}
          </div>
        </div>
      )}
    </div>
  );
}

export default Changes;
