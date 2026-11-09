import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, CircleOff, RefreshCw, Search, ShieldAlert, Workflow } from "lucide-react";
import "./Sources.css";

const API = "http://127.0.0.1:8000/api/v1";

type SourceGroup = {
  key: string;
  name: string;
  aliases: string[];
  urls: { url: string; network: string; availability: string[] }[];
  status: "scraped" | "active_not_scraped" | "captcha" | "inactive" | "manual_inspection" | "not_checked";
  scraper_configured: boolean;
  captcha_detected: boolean;
  last_scraped_at: string | null;
  category: string;
};

type SourcesResponse = {
  inventory_checked_at: string;
  summary: {
    total_unique_groups: number;
    active_sources: number;
    scraped_sources: number;
    not_scraped_sources: number;
    captcha_sites: number;
    inactive_sources: number;
    unverified_sources: number;
    manual_inspection?: number;
  };
  groups: SourceGroup[];
};

type Filter = "all" | "active" | "scraped" | "not_scraped" | "captcha" | "inactive";

const numberFormat = new Intl.NumberFormat();

function relativeTime(value: string | null) {
  if (!value) return "Not recorded";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Not recorded";
  const elapsed = Math.max(0, Date.now() - timestamp);
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} ${days === 1 ? "day" : "days"} ago`;
  return new Date(value).toLocaleDateString();
}

export default function Sources() {
  const [data, setData] = useState<SourcesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetch(`${API}/sources`, { signal: controller.signal, cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Could not load the source inventory");
        return response.json() as Promise<SourcesResponse>;
      })
      .then(async (result) => {
        // Older backend processes can retain the pre-scrape registry in
        // memory. Reconcile manual-inspection rows against saved observations
        // so a newly integrated source appears as scraped immediately.
        const candidates = result.groups.filter((group) => group.status === "manual_inspection");
        const checks = await Promise.all(candidates.map(async (group) => {
          try {
            const query = new URLSearchParams({ group: group.name, range: "all", page_size: "1" });
            const response = await fetch(`${API}/victims?${query.toString()}`, {
              signal: controller.signal,
              cache: "no-store",
            });
            if (!response.ok) return null;
            const victims = await response.json() as { total?: number; items?: { observed_at?: string | null }[] };
            return (victims.total ?? 0) > 0 ? { group, observedAt: victims.items?.[0]?.observed_at ?? null } : null;
          } catch (reason) {
            if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
            return null;
          }
        }));
        const recovered = checks.filter((item): item is NonNullable<typeof item> => item !== null);
        const recoveredKeys = new Set(recovered.map(({ group }) => group.key));
        const groups = result.groups.map((group) => recoveredKeys.has(group.key)
          ? { ...group, status: "scraped" as const, scraper_configured: true, manual_inspection: false,
            last_scraped_at: recovered.find((item) => item.group.key === group.key)?.observedAt ?? group.last_scraped_at }
          : group);
        const activeDelta = recovered.filter(({ group }) =>
          !["scraped", "captcha", "active_not_scraped"].includes(group.status)
          && group.urls.some((source) => source.availability.includes("active")),
        ).length;
        setData({
          ...result,
          groups,
          summary: {
            ...result.summary,
            active_sources: result.summary.active_sources + activeDelta,
            scraped_sources: result.summary.scraped_sources + recovered.length,
            not_scraped_sources: Math.max(0, result.summary.not_scraped_sources - recovered.length),
            manual_inspection: Math.max(0, (result.summary.manual_inspection ?? 0) - recovered.length),
          },
        });
        setError("");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Could not load the source inventory");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [refreshKey]);

  useEffect(() => {
    const refreshOnFocus = () => setRefreshKey((current) => current + 1);
    window.addEventListener("focus", refreshOnFocus);
    return () => window.removeEventListener("focus", refreshOnFocus);
  }, []);

  const visibleGroups = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return (data?.groups ?? []).filter((group) => {
      const matchesFilter = filter === "all"
        || (filter === "active" && group.status !== "inactive" && group.status !== "not_checked" && group.status !== "manual_inspection")
        || (filter === "scraped" && group.scraper_configured)
        || (filter === "not_scraped" && !group.scraper_configured)
        || (filter === "captcha" && group.captcha_detected)
        || (filter === "inactive" && group.status === "inactive");
      const matchesSearch = !needle || group.name.toLocaleLowerCase().includes(needle)
        || group.urls.some((source) => source.url.toLocaleLowerCase().includes(needle));
      return matchesFilter && matchesSearch;
    });
  }, [data, filter, search]);

  const summary = data?.summary;
  const cards: { id: Filter; label: string; value: number; note: string; icon: typeof Activity; tone: string }[] = [
    { id: "all", label: "TOTAL SOURCES", value: summary?.total_unique_groups ?? 0, note: "Unique groups in the clean sheet", icon: Workflow, tone: "cyan" },
    { id: "active", label: "ACTIVE SOURCES", value: summary?.active_sources ?? 0, note: "Integrated or recently reachable", icon: Activity, tone: "green" },
    { id: "scraped", label: "SCRAPED", value: summary?.scraped_sources ?? 0, note: "Configured groups, including INC outside the sheet", icon: CheckCircle2, tone: "blue" },
    { id: "not_scraped", label: "NOT SCRAPED", value: summary?.not_scraped_sources ?? 0, note: "Groups without an integrated scraper", icon: CircleOff, tone: "amber" },
    { id: "captcha", label: "CAPTCHA SITES", value: summary?.captcha_sites ?? 0, note: "Verification prevents automated collection", icon: ShieldAlert, tone: "purple" },
    { id: "inactive", label: "INACTIVE / DOWN", value: summary?.inactive_sources ?? 0, note: "Unreachable in the recorded availability check", icon: AlertTriangle, tone: "red" },
  ];

  return (
    <section className="sources-page">
      <header className="sources-heading">
        <div>
          <h1>Sources</h1>
          <p>Leak-site coverage, scraper integration, and availability</p>
        </div>
        <div className="sources-heading-actions">
          <div className="sources-asof">Inventory: Leak Sites - Clean.xlsx · {data?.inventory_checked_at ?? "—"}</div>
          <button className="sources-refresh" type="button" onClick={() => setRefreshKey((current) => current + 1)} disabled={loading}>
            <RefreshCw size={13} className={loading ? "spinning" : ""} /> Refresh sources
          </button>
        </div>
      </header>

      <div className="sources-metrics">
        {cards.map(({ id, label, value, note, icon: Icon, tone }) => (
          <button
            className={`sources-metric ${tone} ${filter === id ? "selected" : ""}`}
            type="button"
            key={id}
            onClick={() => setFilter((current) => current === id && id !== "all" ? "all" : id)}
            aria-pressed={filter === id}
          >
            <span className="sources-metric-label"><Icon size={14} />{label}</span>
            <strong>{loading ? "—" : numberFormat.format(value)}</strong>
            <small>{note}</small>
          </button>
        ))}
      </div>

      <div className="sources-table-panel">
        <div className="sources-table-toolbar">
          <div className="sources-table-title">
            <strong>Source inventory</strong>
            <span>{numberFormat.format(visibleGroups.length)} groups</span>
          </div>
          <label className="sources-search">
            <Search size={15} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search groups or URLs" />
          </label>
        </div>

        {error && <div className="sources-message error">{error}</div>}
        {loading && <div className="sources-message">Loading source inventory…</div>}
        {!loading && !error && visibleGroups.length === 0 && <div className="sources-message">No sources match this filter.</div>}

        {!loading && !error && visibleGroups.length > 0 && (
          <div className="sources-table-scroll">
            <table className="sources-table">
              <thead>
                <tr><th>Source name</th><th>Source URL</th><th>Category</th><th>Status</th><th>Last scraped</th></tr>
              </thead>
              <tbody>
                {visibleGroups.map((group) => {
                  const inactive = group.status === "inactive";
                  const unknown = group.status === "not_checked" || group.status === "manual_inspection";
                  const label = inactive ? "Inactive" : unknown ? "Not checked" : "Active";
                  return (
                    <tr key={group.key}>
                      <td className="source-name-cell" title={group.aliases.join(" · ")}>{group.name}</td>
                      <td className="source-url-cell">
                        {group.urls.map((source, index) => (
                          <a key={`${source.url}-${index}`} href={source.url} target="_blank" rel="noreferrer" title={source.url}>
                            {source.url}
                          </a>
                        ))}
                      </td>
                      <td>{group.category}</td>
                      <td>
                        <span className={`source-status ${inactive ? "inactive" : unknown ? "unknown" : "active"}`}>
                          <i aria-hidden="true" />{label}
                        </span>
                        {group.captcha_detected && <span className="source-tag captcha-tag">CAPTCHA</span>}
                        {group.scraper_configured && <span className="source-tag scraped-tag">Scraped</span>}
                      </td>
                      <td className="last-scraped-cell" title={group.last_scraped_at ? new Date(group.last_scraped_at).toLocaleString() : "No successful observation recorded"}>
                        {relativeTime(group.last_scraped_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <footer className="sources-table-footer">
          Availability comes from the recorded inventory check dated {data?.inventory_checked_at ?? "—"}. “Last scraped” uses the most recent saved observation.
        </footer>
      </div>
    </section>
  );
}
