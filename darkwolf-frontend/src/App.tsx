import { useEffect, useState } from "react";
import {
  Users,
  UserPlus,
  Activity,
  Radio,
} from "lucide-react";

import "./App.css";
import Sidebar from "./components/layout/Sidebar";
import ThreatMap from "./components/dashboard/ThreatMap";
import CountryChart from "./components/dashboard/CountryChart";
import RecentChanges from "./components/dashboard/RecentChanges";
import RecentVictims from "./components/dashboard/RecentVictims";
import Changes from "./components/changes/Changes";
import Victims from "./components/victims/Victims";
import Sources from "./components/sources/Sources";

type DashboardMetrics = {
  total_victims: number;
  new_victims: number;
  changes_detected: number;
  active_sources: number;
};

function App() {
  const [metrics, setMetrics] =
    useState<DashboardMetrics | null>(null);

  const [selectedRange, setSelectedRange] =
    useState("30");

  const [currentPage, setCurrentPage] =
    useState("dashboard");

  const [ransomwareGroups, setRansomwareGroups] = useState<string[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("all");

  useEffect(() => {
    const loadGroups = () => {
      fetch("http://127.0.0.1:8000/api/v1/dashboard/groups", { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error("Failed to fetch ransomware groups");
          return response.json();
        })
        .then(async (groups: string[]) => {
          // Recover recently integrated sources when the backend process has
          // not yet reloaded its static registry but their observations exist.
          const inventoryResponse = await fetch("http://127.0.0.1:8000/api/v1/sources", { cache: "no-store" });
          if (!inventoryResponse.ok) return setRansomwareGroups(groups);
          const inventory = await inventoryResponse.json() as {
            groups?: { name: string; status: string }[];
          };
          const candidates = (inventory.groups ?? []).filter((source) => source.status === "manual_inspection");
          const recovered = await Promise.all(candidates.map(async (source) => {
            try {
              const query = new URLSearchParams({ group: source.name, range: "all", page_size: "1" });
              const response = await fetch(`http://127.0.0.1:8000/api/v1/victims?${query.toString()}`, { cache: "no-store" });
              if (!response.ok) return null;
              const result = await response.json() as { total?: number };
              return (result.total ?? 0) > 0 ? source.name : null;
            } catch {
              return null;
            }
          }));
          setRansomwareGroups([...new Set([...groups, ...recovered.filter((name): name is string => Boolean(name))])].sort());
        })
        .catch((error) => console.error("Failed to load ransomware groups:", error));
    };
    loadGroups();
    window.addEventListener("focus", loadGroups);
    return () => window.removeEventListener("focus", loadGroups);
  }, []);

  useEffect(() => {
    const query = new URLSearchParams({ range: selectedRange });
    if (selectedGroup !== "all") query.set("group", selectedGroup);

    fetch(
      `http://127.0.0.1:8000/api/v1/dashboard/metrics?${query.toString()}`,
      { cache: "no-store" },
    )
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            "Failed to fetch dashboard metrics",
          );
        }

        return response.json();
      })
      .then((data: DashboardMetrics) => {
        setMetrics(data);
      })
      .catch((error) => {
        console.error(
          "Failed to load dashboard metrics:",
          error,
        );
      });
  }, [selectedRange, selectedGroup]);

  return (
    <div className="app">
      <Sidebar
        currentPage={currentPage}
        onNavigate={setCurrentPage}
      />

      <main className="main-content">

        {currentPage === "changes" ? (
          <Changes />
        ) : currentPage === "victims" ? (
          <Victims />
        ) : currentPage === "sources" ? (
          <Sources />
        ) : (
          <>
            <header className="topbar">
              <div>
                <div className="page-title">
                  Dashboard
                </div>

                <div className="page-subtitle">
                  Dark Web Threat Intelligence
                </div>
              </div>

              <div className="topbar-actions">
                <select
                  className="date-button group-select"
                  aria-label="Filter dashboard by ransomware group"
                  value={selectedGroup}
                  onChange={(event) => setSelectedGroup(event.target.value)}
                >
                  <option value="all">All ransomware groups</option>
                  {ransomwareGroups.map((group) => <option key={group} value={group}>{group}</option>)}
                </select>
                <div className="date-select">
                  <select
                    className="date-button"
                    value={selectedRange}
                    onChange={(event) =>
                      setSelectedRange(
                        event.target.value,
                      )
                    }
                  >
                    <option value="1">
                      Last 24 Hours
                    </option>

                    <option value="7">
                      Last 7 Days
                    </option>

                    <option value="30">
                      Last 30 Days
                    </option>

                    <option value="90">
                      Last 90 Days
                    </option>

                    <option value="all">
                      All Time
                    </option>
                  </select>

                  <span className="date-select-arrow">
                    ⌄
                  </span>
                </div>
              </div>
            </header>

            <section className="kpi-section">
              <div className="kpi-card">
                <div className="kpi-label">
                  <Users size={14} />
                  <span>TOTAL VICTIMS</span>
                </div>

                <div className="kpi-value">
                  {metrics?.total_victims ?? "—"}
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">
                  <UserPlus size={14} />
                  <span>NEW VICTIMS</span>
                </div>

                <div className="kpi-value">
                  {metrics?.new_victims ?? "—"}
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">
                  <Activity size={14} />
                  <span>CHANGES DETECTED</span>
                </div>

                <div className="kpi-value">
                  {metrics?.changes_detected ?? "—"}
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-label">
                  <Radio size={14} />
                  <span>ACTIVE SOURCES</span>
                </div>

                <div className="kpi-value">
                  {metrics?.active_sources ?? "—"}
                </div>
              </div>
            </section>

            <section className="heatmap-section">
              <div className="threat-activity-grid">

                <div className="country-chart-panel">
                  <h3>VICTIMS BY COUNTRY</h3>

                  <p>
                    Top affected countries
                  </p>

                  <div className="chart-placeholder">
                  <CountryChart group={selectedGroup} range={selectedRange} />
                  </div>
                </div>

                <div className="map-panel">
                  <h3>GLOBAL THREAT MAP</h3>

                  <p>
                    Victim distribution by country
                  </p>

                  <div className="heatmap-container">
                  <ThreatMap group={selectedGroup} range={selectedRange} />
                  </div>
                </div>

              </div>
            </section>

            <section className="recent-data-section">
              <div className="recent-data-grid">
                <RecentChanges group={selectedGroup} range={selectedRange} />
                <RecentVictims group={selectedGroup} range={selectedRange} onViewAll={() => setCurrentPage("victims")} />
              </div>
            </section>
          </>
        )}

      </main>
    </div>
  );
}

export default App;
