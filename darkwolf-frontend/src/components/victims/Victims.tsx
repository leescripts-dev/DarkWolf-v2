import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Clock3,
  Download,
  FileText,
  FilterX,
  LoaderCircle,
  Search,
  ScanSearch,
  ShieldAlert,
  Users,
  UserPlus,
} from "lucide-react";
import "flag-icons/css/flag-icons.min.css";
import { countryFlagCode } from "../../utils/country";
import { displayOrganizationName } from "../../utils/organization";
import "./Victims.css";

const API = "http://127.0.0.1:8000/api/v1";

type VictimStatus = "yet_to_publish" | "awaiting_confirmation" | "published" | "listed";

type Victim = {
  id: string;
  source_id: string;
  source: string;
  source_name: string;
  source_url: string | null;
  organization: string;
  country: string | null;
  country_code: string | null;
  domain: string | null;
  ransomware_group: string | null;
  leak_date: string | null;
  observed_at: string | null;
  first_discovered_at: string | null;
  estimated_publish_at: string | null;
  countdown_captured_at: string | null;
  countdown_seconds_at_capture: number | null;
  countdown_raw: string | null;
  countdown_remaining_seconds: number | null;
  publication_status: VictimStatus;
  is_new: boolean;
};

type VictimResponse = {
  items: Victim[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  summary: {
    total_victims: number;
    new_victims: number;
    yet_to_publish: number;
    published_victims: number;
    active_groups: number;
    countries: number;
  };
};

type ScrapeStage = { name: string; status: "queued" | "running" | "completed" | "completed_with_errors" };
type ScrapeStatus = {
  status: "idle" | "starting" | "running" | "completed" | "completed_with_errors" | "failed";
  started_at: string | null;
  finished_at: string | null;
  current_stage: string | null;
  stages: ScrapeStage[];
  exit_code: number | null;
  log_path: string | null;
  message: string | null;
};

const idleScrapeStatus: ScrapeStatus = {
  status: "idle", started_at: null, finished_at: null, current_stage: null,
  stages: [], exit_code: null, log_path: null, message: null,
};

type SortField = "organization" | "ransomware_group" | "domain" | "leak_date" | "estimated_publish_at" | "publication_status";

const emptyResponse: VictimResponse = {
  items: [], total: 0, page: 1, page_size: 25, total_pages: 0,
  summary: { total_victims: 0, new_victims: 0, yet_to_publish: 0, published_victims: 0, active_groups: 0, countries: 0 },
};

const numberFormat = new Intl.NumberFormat();

function formatDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatCountdown(target: string | null, now: number) {
  if (!target) return null;
  const secondsLeft = Math.max(0, Math.floor((new Date(target).getTime() - now) / 1000));
  if (!Number.isFinite(secondsLeft)) return null;
  if (secondsLeft === 0) return "0m — awaiting confirmation";
  const days = Math.floor(secondsLeft / 86400);
  const hours = Math.floor((secondsLeft % 86400) / 3600);
  const minutes = Math.floor((secondsLeft % 3600) / 60);
  const seconds = secondsLeft % 60;
  return [days ? `${String(days).padStart(2, "0")}d` : "", `${String(hours).padStart(2, "0")}h`, `${String(minutes).padStart(2, "0")}m`, days ? "" : `${String(seconds).padStart(2, "0")}s`]
    .filter(Boolean).join(" ");
}

function statusLabel(status: VictimStatus, expired: boolean) {
  if (expired && status === "yet_to_publish") return "Awaiting confirmation";
  if (status === "yet_to_publish") return "Yet to publish";
  if (status === "awaiting_confirmation") return "Awaiting confirmation";
  if (status === "published") return "Published";
  return "Listed";
}

function csvCell(value: unknown) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

export default function Victims() {
  const [groups, setGroups] = useState<string[]>([]);
  const [group, setGroup] = useState("all");
  // The victims page is the full catalog; start with all observations so
  // undated baseline archives and older source listings are discoverable.
  const [range, setRange] = useState("all");
  const [status, setStatus] = useState("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sortBy, setSortBy] = useState<SortField>("leak_date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [result, setResult] = useState<VictimResponse>(emptyResponse);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const [exporting, setExporting] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState<ScrapeStatus>(idleScrapeStatus);
  const [startingScrape, setStartingScrape] = useState(false);
  const [scrapeError, setScrapeError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API}/dashboard/groups`, { signal: controller.signal, cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Could not load ransomware groups");
        return response.json();
      })
      .then((data: string[]) => setGroups(data))
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        console.error("Failed to load ransomware groups:", reason);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const refreshScrapeStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API}/scrape/status`);
      if (!response.ok) return;
      setScrapeStatus(await response.json() as ScrapeStatus);
    } catch (reason) {
      console.error("Failed to load scrape status:", reason);
    }
  }, []);

  useEffect(() => { void refreshScrapeStatus(); }, [refreshScrapeStatus]);

  useEffect(() => {
    if (scrapeStatus.status !== "starting" && scrapeStatus.status !== "running") return;
    const timer = window.setInterval(() => void refreshScrapeStatus(), 2000);
    return () => window.clearInterval(timer);
  }, [refreshScrapeStatus, scrapeStatus.status]);

  const loadVictims = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    const query = new URLSearchParams({
      page: String(page), page_size: String(pageSize), range, status,
      sort_by: sortBy, sort_order: sortOrder,
    });
    if (group !== "all") query.set("group", group);
    if (search) query.set("search", search);
    try {
      const response = await fetch(`${API}/victims?${query}`, { signal });
      if (!response.ok) throw new Error(`Victim request failed (${response.status})`);
      setResult(await response.json() as VictimResponse);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "Could not load victims");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [group, page, pageSize, range, search, sortBy, sortOrder, status]);

  useEffect(() => {
    if (scrapeStatus.status === "completed" || scrapeStatus.status === "completed_with_errors") {
      void loadVictims();
    }
  }, [loadVictims, scrapeStatus.finished_at, scrapeStatus.status]);

  const startFullScrape = async () => {
    setStartingScrape(true);
    setScrapeError(null);
    try {
      const response = await fetch(`${API}/scrape/start`, { method: "POST" });
      const payload = await response.json() as ScrapeStatus | { detail?: string };
      if (!response.ok) throw new Error("detail" in payload ? payload.detail || "Could not start scrape" : "Could not start scrape");
      setScrapeStatus(payload as ScrapeStatus);
    } catch (reason) {
      setScrapeError(reason instanceof Error ? reason.message : "Could not start full scrape");
    } finally {
      setStartingScrape(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void loadVictims(controller.signal);
    return () => controller.abort();
  }, [loadVictims]);

  const clearFilters = () => {
    setSearchInput("");
    setGroup("all");
    setRange("all");
    setStatus("all");
    setPage(1);
  };

  const changeSort = (field: SortField) => {
    setSortOrder((current) => field === sortBy ? (current === "desc" ? "asc" : "desc") : "desc");
    setSortBy(field);
    setPage(1);
  };

  const exportCsv = async () => {
    setExporting(true);
    try {
      const allRows: Victim[] = [];
      const firstParams = new URLSearchParams({ page: "1", page_size: "500", range, status, sort_by: sortBy, sort_order: sortOrder });
      if (group !== "all") firstParams.set("group", group);
      if (search) firstParams.set("search", search);
      const firstResponse = await fetch(`${API}/victims?${firstParams}`);
      if (!firstResponse.ok) throw new Error("Export request failed");
      const firstPage = await firstResponse.json() as VictimResponse;
      allRows.push(...firstPage.items);
      for (let nextPage = 2; nextPage <= firstPage.total_pages; nextPage += 1) {
        firstParams.set("page", String(nextPage));
        const response = await fetch(`${API}/victims?${firstParams}`);
        if (!response.ok) throw new Error("Could not fetch every row for export");
        const data = await response.json() as VictimResponse;
        allRows.push(...data.items);
      }
      const headers = ["Organization", "Country code", "Ransomware group", "Domain", "Leak date", "Estimated publish", "Status", "Source"];
      const lines = [headers, ...allRows.map((victim) => [
        displayOrganizationName(victim.organization, victim.ransomware_group), victim.country_code,
        victim.ransomware_group, victim.domain, victim.leak_date, victim.estimated_publish_at,
        statusLabel(victim.publication_status, Boolean(victim.estimated_publish_at && Date.parse(victim.estimated_publish_at) <= Date.now())), victim.source_name,
      ])].map((row) => row.map(csvCell).join(","));
      const blob = new Blob([`\uFEFF${lines.join("\r\n")}`], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "darkwolf-victims.csv";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not export victims");
    } finally {
      setExporting(false);
    }
  };

  const visiblePages = useMemo(() => {
    const total = result.total_pages;
    if (total <= 5) return Array.from({ length: total }, (_, index) => index + 1);
    const first = Math.max(1, Math.min(page - 2, total - 4));
    return Array.from({ length: 5 }, (_, index) => first + index);
  }, [page, result.total_pages]);

  const summary = result.summary;
  const startRow = result.total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endRow = Math.min(page * pageSize, result.total);

  return (
    <section className="victims-page">
      <header className="victims-heading">
        <div>
          <h1>Victims</h1>
          <p>Tracked victim disclosures across monitored ransomware groups.</p>
        </div>
        <div className="victims-heading-actions">
          <button className="victims-scan" onClick={() => void startFullScrape()} disabled={startingScrape || scrapeStatus.status === "starting" || scrapeStatus.status === "running"}>
            {startingScrape || scrapeStatus.status === "starting" || scrapeStatus.status === "running"
              ? <LoaderCircle size={15} className="victims-spin" />
              : <ScanSearch size={15} />}
            {startingScrape || scrapeStatus.status === "starting" || scrapeStatus.status === "running" ? "Scanning all sources…" : "Scan all sources"}
          </button>
          <button className="victims-export" onClick={() => void exportCsv()} disabled={exporting || result.total === 0}>
            {exporting ? <LoaderCircle size={15} className="victims-spin" /> : <Download size={15} />}
            {exporting ? "Exporting" : "Export CSV"}
          </button>
        </div>
      </header>

      {(scrapeError || scrapeStatus.status !== "idle") && <section className={`victims-scrape-status ${scrapeStatus.status}`} aria-live="polite">
        <div className="victims-scrape-status-heading">
          <strong>{scrapeError ? "Could not start scan" : scrapeStatus.status === "completed" ? "Full scrape complete" : scrapeStatus.status === "completed_with_errors" ? "Full scrape finished with site errors" : scrapeStatus.status === "failed" ? "Full scrape failed" : "Full scrape in progress"}</strong>
          <span>{scrapeError || scrapeStatus.message || (scrapeStatus.current_stage ? `Current stage: ${scrapeStatus.current_stage}` : "Checking services…")}</span>
        </div>
        {scrapeStatus.stages.length > 0 && <div className="victims-scrape-stages">
          {scrapeStatus.stages.map((stage) => <span key={stage.name} className={`scrape-stage ${stage.status}`}>
            {stage.name.replaceAll("-", " ")}
          </span>)}
        </div>}
      </section>}

      <div className="victims-toolbar">
        <label className="victims-search">
          <Search size={16} aria-hidden="true" />
          <input value={searchInput} onChange={(event) => { setSearchInput(event.target.value); setPage(1); }} placeholder="Search organization, domain, or group" aria-label="Search victims" />
        </label>
        <label className="victims-select-wrap">
          <span className="sr-only">Ransomware group</span>
          <select value={group} onChange={(event) => { setGroup(event.target.value); setPage(1); }}>
            <option value="all">All ransomware groups</option>
            {groups.map((item) => <option key={item} value={item}>{item}</option>)}
          </select><ChevronDown size={14} />
        </label>
        <label className="victims-select-wrap">
          <CalendarDays size={15} aria-hidden="true" />
          <span className="sr-only">Date range</span>
          <select value={range} onChange={(event) => { setRange(event.target.value); setPage(1); }}>
            <option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="all">All time</option>
          </select><ChevronDown size={14} />
        </label>
        <label className="victims-select-wrap">
          <span className="sr-only">Victim status</span>
          <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="all">All statuses</option><option value="new">New</option><option value="yet_to_publish">Yet to publish</option><option value="awaiting_confirmation">Awaiting confirmation</option><option value="published">Published</option><option value="listed">Listed</option>
          </select><ChevronDown size={14} />
        </label>
        <button className="victims-clear" onClick={clearFilters}><FilterX size={15} /> Clear</button>
      </div>

      <div className="victims-metrics">
        <article className="victim-metric total"><div><Users size={17} /><span>Total victims</span></div><strong>{numberFormat.format(summary.total_victims)}</strong><small>In selected date range</small></article>
        <article className="victim-metric fresh"><div><UserPlus size={17} /><span>New victims</span></div><strong>{numberFormat.format(summary.new_victims)}</strong><small>Discovered since baseline</small></article>
        <article className="victim-metric pending"><div><Clock3 size={17} /><span>Yet to publish</span></div><strong>{numberFormat.format(summary.yet_to_publish)}</strong><small>Countdown captured from source</small></article>
        <article className="victim-metric published"><div><FileText size={17} /><span>Published victims</span></div><strong>{numberFormat.format(summary.published_victims)}</strong><small>Confirmed leak date available</small></article>
      </div>

      <div className="victims-table-card">
        <div className="victims-table-topline">
          <div><h2>Victim records</h2><span>{numberFormat.format(result.total)} records · {summary.active_groups} groups · {summary.countries} countries</span></div>
          <label className="victims-page-size">Rows per page
            <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select>
          </label>
        </div>

        {error && <div className="victims-error"><AlertCircle size={17} /><span>{error}</span><button onClick={() => void loadVictims()}>Retry</button></div>}

        <div className="victims-table-scroll">
          <table className="victims-table-full">
            <thead><tr>
              <th><button onClick={() => changeSort("organization")}>Organization <ChevronsUpDown size={13} /></button></th>
              <th className="flag-column" aria-label="Country"><span className="sr-only">Country</span></th>
              <th><button onClick={() => changeSort("ransomware_group")}>Ransomware group <ChevronsUpDown size={13} /></button></th>
              <th><button onClick={() => changeSort("domain")}>Domain <ChevronsUpDown size={13} /></button></th>
              <th><button onClick={() => changeSort("leak_date")}>Leak date <ChevronsUpDown size={13} /></button></th>
              <th><button onClick={() => changeSort("estimated_publish_at")}>Est. publish <ChevronsUpDown size={13} /></button></th>
              <th><button onClick={() => changeSort("publication_status")}>Status <ChevronsUpDown size={13} /></button></th>
            </tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={7} className="victims-state"><LoaderCircle className="victims-spin" size={18} /> Loading victim records…</td></tr>
                : result.items.length === 0 ? <tr><td colSpan={7} className="victims-state"><ShieldAlert size={18} /> No victims match these filters.</td></tr>
                  : result.items.map((victim) => {
                    const code = victim.country_code?.toLowerCase() || countryFlagCode(victim.country);
                    const remaining = formatCountdown(victim.estimated_publish_at, now);
                    const expired = Boolean(victim.estimated_publish_at && new Date(victim.estimated_publish_at).getTime() <= now);
                    return <tr key={victim.id}>
                      <td className="victim-org-cell"><span title={victim.organization}>{displayOrganizationName(victim.organization, victim.ransomware_group)}</span>{victim.is_new && <i>New</i>}</td>
                      <td className="flag-column">{code ? <span className={`fi fi-${code} victim-page-flag`} role="img" aria-label={`${victim.country || code} flag`} /> : <span className="victim-no-flag">—</span>}</td>
                      <td><span className="victim-group-cell"><span className="victim-group-dot" />{victim.ransomware_group || "—"}</span></td>
                      <td className="victim-domain-cell" title={victim.domain || undefined}>{victim.domain || "—"}</td>
                      <td className="victim-leak-date">{formatDate(victim.leak_date)}</td>
                      <td className="victim-eta-cell">{remaining ? <><Clock3 size={14} /><span>{remaining}</span></> : "—"}</td>
                      <td><span className={`victim-status-badge ${expired ? "awaiting" : victim.publication_status}`}>{statusLabel(victim.publication_status, expired)}</span></td>
                    </tr>;
                  })}
            </tbody>
          </table>
        </div>

        <footer className="victims-pagination">
          <span>Showing {startRow}–{endRow} of {numberFormat.format(result.total)} victims</span>
          <div className="victims-page-buttons">
            <button aria-label="Previous page" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}><ChevronLeft size={16} /></button>
            {visiblePages[0] > 1 && <><button onClick={() => setPage(1)}>1</button><span>…</span></>}
            {visiblePages.map((pageNumber) => <button key={pageNumber} className={pageNumber === page ? "active" : ""} aria-current={pageNumber === page ? "page" : undefined} onClick={() => setPage(pageNumber)}>{pageNumber}</button>)}
            {result.total_pages > 5 && page < result.total_pages - 2 && <span>…</span>}
            {result.total_pages > 5 && page < result.total_pages - 2 && <button onClick={() => setPage(result.total_pages)}>{result.total_pages}</button>}
            <button aria-label="Next page" disabled={page >= result.total_pages || loading} onClick={() => setPage((current) => Math.min(result.total_pages, current + 1))}><ChevronRight size={16} /></button>
          </div>
        </footer>
      </div>

      <p className="victims-countdown-note"><Clock3 size={13} /> Countdown estimates use the last timer captured during scraping and continue locally. An elapsed timer means publication is awaiting source confirmation.</p>
    </section>
  );
}
