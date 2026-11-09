import { useEffect, useState } from "react";
import "flag-icons/css/flag-icons.min.css";
import { displayOrganizationName } from "../../utils/organization";
import { countryFlagCode } from "../../utils/country";

type VictimItem = {
  id: string;
  organization: string;
  country: string | null;
  domain: string | null;
  leak_date: string | null;
  ransomware_group: string | null;
  status: "new" | "updated";
};

const ransomwareColors: Record<string, string> = {
  inc: "#00BFFF",
  lockbit: "#FF4545",
  qilin: "#A855F7",
  play: "#F59E0B",
  akira: "#22C55E",
};

const getRansomwareColor = (group: string | null) => {
  if (!group) {
    return "#5F7D91";
  }

  return (
    ransomwareColors[group.toLowerCase()] ||
    "#00A9DF"
  );
};

export default function RecentVictims({ group = "all", range = "30", onViewAll }: { group?: string; range?: string; onViewAll?: () => void }) {
  const [victims, setVictims] = useState<VictimItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const query = new URLSearchParams({ limit: "5", range });
    if (group !== "all") query.set("group", group);
    fetch(`http://127.0.0.1:8000/api/v1/victims/recent?${query.toString()}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch recent victims");
        }

        return response.json();
      })
      .then((data: VictimItem[]) => {
        setVictims(data);
      })
      .catch((error) => {
        console.error(
          "Failed to load recent victims:",
          error
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
          <h3>RECENT VICTIMS</h3>
          <p>Latest victim entries</p>
        </div>

        <button className="view-all-button" onClick={onViewAll}>
          View all
        </button>
      </div>

      <div className="victims-table">
        <div className="victims-table-header">
          <span>ORGANIZATION</span>
          <span>COUNTRY</span>
          <span>RANSOMWARE</span>
          <span>DOMAIN</span>
          <span>LEAK DATE</span>
          <span>STATUS</span>
        </div>

        {loading ? (
          <div className="recent-empty">
            Loading recent victims...
          </div>
        ) : victims.length === 0 ? (
          <div className="recent-empty">
            No recent victims detected
          </div>
        ) : (
          victims.map((victim) => (
            <div
              className="victim-row"
              key={victim.id}
            >
              <span className="victim-organization">
                {displayOrganizationName(victim.organization, victim.ransomware_group)}
              </span>

              <span className="victim-country">
                {countryFlagCode(victim.country) ? (
                  <span
                    className={`fi fi-${countryFlagCode(victim.country)} victim-flag`}
                    role="img"
                    aria-label={`${victim.country} flag`}
                  />
                ) : "—"}
              </span>

              <span className="victim-ransomware">
                {victim.ransomware_group ? (
                  <>
                    <span
                      className="ransomware-beacon"
                      style={{
                        backgroundColor:
                          getRansomwareColor(
                            victim.ransomware_group
                          ),
                      }}
                    />

                    <span>
                      {victim.ransomware_group}
                    </span>
                  </>
                ) : (
                  "—"
                )}
              </span>

              <span className="victim-domain">
                {victim.domain || "—"}
              </span>

              <span className="victim-date">
                {victim.leak_date
                  ? new Date(
                      victim.leak_date
                    ).toLocaleDateString()
                  : "—"}
              </span>

              <span>
                <span
                  className={`victim-status ${victim.status}`}
                >
                  {victim.status === "new"
                    ? "New"
                    : "Updated"}
                </span>
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
