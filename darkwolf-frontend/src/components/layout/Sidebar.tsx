import "./Sidebar.css";

type SidebarProps = {
  currentPage: string;
  onNavigate: (page: string) => void;
};

export default function Sidebar({
  currentPage,
  onNavigate,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">DARKWOLF</div>
        <div className="sidebar-subtitle">
          Ransomware Intelligence
        </div>
      </div>

      <nav className="sidebar-nav">
        <div
          className={`nav-item ${
            currentPage === "dashboard" ? "active" : ""
          }`}
          onClick={() => onNavigate("dashboard")}
        >
          Dashboard
        </div>

        <div
          className={`nav-item ${currentPage === "victims" ? "active" : ""}`}
          onClick={() => onNavigate("victims")}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") onNavigate("victims");
          }}
        >
          Victims
        </div>
        <div className="nav-item">Threat Actors</div>
        <div className="nav-item">Domains</div>
        <div
          className={`nav-item ${currentPage === "sources" ? "active" : ""}`}
          onClick={() => onNavigate("sources")}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") onNavigate("sources");
          }}
        >
          Sources
        </div>

        <div
          className={`nav-item ${
            currentPage === "changes" ? "active" : ""
          }`}
          onClick={() => onNavigate("changes")}
        >
          Changes
        </div>

        <div className="nav-item">Reports</div>
      </nav>

      <div className="sidebar-bottom">
        <div className="nav-item">Alerts</div>
        <div className="nav-item">Settings</div>
      </div>
    </aside>
  );
}
