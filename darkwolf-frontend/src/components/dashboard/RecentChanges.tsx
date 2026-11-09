import { useEffect, useState } from "react";
import { displayOrganizationName } from "../../utils/organization";
import { countryFlagCode } from "../../utils/country";

type ChangeItem = {
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

const ransomwareColors: Record<string, string> = {
  inc: "#00BFFF",
  lockbit: "#FF4545",
  qilin: "#A855F7",
  play: "#F59E0B",
  akira: "#22C55E",
};

const getRansomwareColor = (
  group: string | null,
) => {
  if (!group) return "#5F7D91";

  return (
    ransomwareColors[group.toLowerCase()] ||
    "#00A9DF"
  );
};

const formatRelativeTime = (
  date: string,
) => {
  const diff =
    Date.now() -
    new Date(date).getTime();

  const minutes = Math.floor(
    diff / 60000,
  );

  if (minutes < 1) return "just now";

  if (minutes < 60) {
    return `${minutes}m ago`;
  }

  const hours = Math.floor(
    minutes / 60,
  );

  if (hours < 24) {
    return `${hours}h ago`;
  }

  const days = Math.floor(
    hours / 24,
  );

  return `${days}d ago`;
};

const formatEventType = (
  eventType: string,
) => {
  const formatted = eventType
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) =>
      char.toUpperCase(),
    );

  return formatted;
};

export default function RecentChanges({ group = "all", range = "30" }: { group?: string; range?: string }) {
  const [changes, setChanges] =
    useState<ChangeItem[]>([]);

  const [loading, setLoading] =
    useState(true);

  useEffect(() => {
    const query = new URLSearchParams({ limit: "5000", range });
    if (group !== "all") query.set("group", group);
    fetch(`http://127.0.0.1:8000/api/v1/changes?${query.toString()}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            "Failed to fetch recent changes",
          );
        }

        return response.json();
      })
      .then((data: ChangeItem[]) => {
        setChanges(
          data
          // First-time victim discoveries belong in Recent Victims. The
          // dashboard's Recent Changes panel is for updates to known victims
          // and disclosures; the full Changes page retains discovery history.
          .filter((change) => ![
            "VICTIM_DISCOVERED",
            "VICTIM_DISCOVERED_AND_DISCLOSED",
          ].includes(change.event_type))
          .sort((left, right) => {
            const leftDate = Date.parse(left.leak_date || left.published_at || "") || Date.parse(left.detected_at) || 0;
            const rightDate = Date.parse(right.leak_date || right.published_at || "") || Date.parse(right.detected_at) || 0;
            return rightDate - leftDate;
          }).slice(0, 3),
        );
      })
      .catch((error) => {
        console.error(
          "Failed to load recent changes:",
          error,
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }, [group, range]);

  return (
    <div className="recent-panel">
      <div className="recent-panel-header">
        <div>
          <h3>
            RECENT CHANGES
          </h3>

          <p>
            Latest updates from monitored sources
          </p>
        </div>

        <button className="view-all-button">
          View all
        </button>
      </div>

      <div className="changes-list">
        {loading ? (
          <div className="recent-empty">
            Loading recent changes...
          </div>
        ) : changes.length === 0 ? (
          <div className="recent-empty">
            No recent changes detected
          </div>
        ) : (
          changes.map(
            (change, index) => {
              const countryCode = countryFlagCode(change.country);

              return (
                <div
                  className="change-row"
                  key={`${change.event_id}-${index}`}
                >
                  {/* Time + Change Type */}
                  <div className="change-summary">
                    <span
                      className="change-dot"
                      style={{
                        backgroundColor:
                          getRansomwareColor(
                            change.ransomware_group,
                          ),
                      }}
                    />

                    <div className="change-event">
                      <span className="change-time">
                        {formatRelativeTime(
                          change.detected_at,
                        )}
                      </span>

                      <div className="change-type">
                        {formatEventType(
                          change.event_type,
                        )
                          .split(" ")
                          .map(
                            (
                              word,
                              wordIndex,
                            ) => (
                              <span
                                key={
                                  wordIndex
                                }
                              >
                                {word}
                              </span>
                            ),
                          )}
                      </div>
                    </div>
                  </div>

                  {/* Country Flag + Victim */}
                  <div className="change-organization">
                    {countryCode && (
                      <span
                        className={`fi fi-${countryCode} change-flag`}
                        role="img"
                        aria-label={`${change.country ?? "Country"} flag`}
                        title={change.country ?? undefined}
                      />
                    )}

                    <span>
                      {
                      displayOrganizationName(change.organization, change.ransomware_group)
                      }
                    </span>
                  </div>

                  {/* Ransomware */}
                  <div className="change-ransomware">
                    <span
                      className="ransomware-beacon"
                      style={{
                        backgroundColor:
                          getRansomwareColor(
                            change.ransomware_group,
                          ),
                      }}
                    />

                    <span>
                      {change.ransomware_group ||
                        "—"}
                    </span>
                  </div>

                  {/* Change Details */}
                  <div
                    className="change-value"
                    style={{
                      width: "70px",
                      minWidth: "70px",
                      maxWidth: "70px",
                      overflow: "hidden",
                      whiteSpace: "normal",
                      lineHeight: "16px",
                    }}
                  >
                    {change.changed_fields
                      .length > 0 ? (
                      <span
                        style={{
                          display: "block",
                          width: "100%",
                          whiteSpace:
                            "normal",
                          overflowWrap:
                            "break-word",
                          wordBreak:
                            "normal",
                        }}
                      >
                        {
                          change
                            .changed_fields
                            .length
                        }{" "}
                        field
                        {change
                          .changed_fields
                          .length !== 1
                          ? "s"
                          : ""}
                        <br />
                        changed
                      </span>
                    ) : (
                      <span
                        style={{
                          display: "block",
                          width: "100%",
                          whiteSpace:
                            "normal",
                        }}
                      >
                        Intelligence
                        <br />
                        updated
                      </span>
                    )}
                  </div>
                </div>
              );
            },
          )
        )}
      </div>
    </div>
  );
}
