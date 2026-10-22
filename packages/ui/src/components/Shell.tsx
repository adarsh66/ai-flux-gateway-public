import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../session";
import { BrandMark } from "./ui";

export interface NavItem {
  to: string;
  label: string;
  section?: string;
}

type ThemeId = "daylight" | "obsidian" | "crimson" | "emerald";

const THEMES: { id: ThemeId; label: string; color: string }[] = [
  { id: "daylight", label: "Daylight", color: "#2563eb" },
  { id: "obsidian", label: "Obsidian", color: "#6366f1" },
  { id: "crimson", label: "Crimson", color: "#e11d48" },
  { id: "emerald", label: "Emerald", color: "#059669" },
];

function navIconFor(path: string): ReactNode {
  if (path.includes("overview") || path.includes("credit")) {
    // LayoutDashboard icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="7" height="9" rx="1.5" />
        <rect x="14" y="3" width="7" height="5" rx="1.5" />
        <rect x="14" y="12" width="7" height="9" rx="1.5" />
        <rect x="3" y="16" width="7" height="5" rx="1.5" />
      </svg>
    );
  }
  if (path.includes("router")) {
    // GitFork / Decision Router icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="6" cy="6" r="3" />
        <circle cx="18" cy="6" r="3" />
        <circle cx="12" cy="18" r="3" />
        <path d="M6 9v2a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3V9" />
        <line x1="12" y1="14" x2="12" y2="15" />
      </svg>
    );
  }
  if (path.includes("models") || path.includes("garden")) {
    // 3D Cube / Model Catalog icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
        <line x1="12" y1="22.08" x2="12" y2="12" />
      </svg>
    );
  }
  if (path.includes("budget")) {
    // Wallet / Credit Allocation icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M20 12V8H6a2 2 0 0 1-2-2c0-1.1.9-2 2-2h12v4" />
        <path d="M4 6v12c0 1.1.9 2 2 2h14v-4" />
        <path d="M18 12a2 2 0 0 0-2 2c0 1.1.9 2 2 2h4v-4h-4z" />
      </svg>
    );
  }
  if (path.includes("price")) {
    // Dollar / Rate Card icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8" />
        <line x1="12" y1="6" x2="12" y2="18" />
      </svg>
    );
  }
  if (path.includes("key") || path.includes("subscription")) {
    // KeyRound icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="7.5" cy="15.5" r="5.5" />
        <path d="m21 2-9.6 9.6" />
        <path d="m15.5 7.5 3 3L22 7l-3-3" />
      </svg>
    );
  }
  if (path.includes("playground")) {
    // Terminal / Prompt Playground icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="4 17 10 11 4 5" />
        <line x1="12" y1="19" x2="20" y2="19" />
      </svg>
    );
  }
  if (path.includes("content-safety")) {
    // ShieldCheck Guardrail icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    );
  }
  if (path.includes("safety")) {
    // AlertTriangle / Safety Events log icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    );
  }
  if (path.includes("settings")) {
    // SlidersHorizontal / Traffic & Quotas icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="21" y1="4" x2="14" y2="4" />
        <line x1="10" y1="4" x2="3" y2="4" />
        <line x1="21" y1="12" x2="12" y2="12" />
        <line x1="8" y1="12" x2="3" y2="12" />
        <line x1="21" y1="20" x2="16" y2="20" />
        <line x1="12" y1="20" x2="3" y2="20" />
        <line x1="14" y1="2" x2="14" y2="6" />
        <line x1="8" y1="10" x2="8" y2="14" />
        <line x1="16" y1="18" x2="16" y2="22" />
      </svg>
    );
  }
  if (path.includes("organization")) {
    // Building2 / Tenant Organization icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="4" y="2" width="16" height="20" rx="2" />
        <path d="M9 22v-4h6v4" />
        <path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01" />
      </svg>
    );
  }
  if (path.includes("local-users")) {
    // UserCog / PostgreSQL Users icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <polyline points="16 11 18 13 22 9" />
      </svg>
    );
  }
  if (path.includes("member")) {
    // Users / Entra Directory Members icon
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <circle cx="9" cy="10" r="2" />
        <path d="M15 8h2M15 12h2M7 16h10" />
      </svg>
    );
  }
  // Activity / Usage & Telemetry pulse icon
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

export function Shell({ portalName, nav }: { portalName: string; nav: NavItem[] }) {
  const { me, signOut } = useSession();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return typeof localStorage !== "undefined" && localStorage.getItem("aiflux_sidebar_collapsed") === "1";
    } catch {
      return false;
    }
  });
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeId>(() => {
    try {
      const saved = typeof localStorage !== "undefined" ? localStorage.getItem("aiflux_theme") : null;
      if (saved === "daylight" || saved === "obsidian" || saved === "crimson" || saved === "emerald") return saved;
    } catch {
      /* ignore */
    }
    return "daylight";
  });

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.dataset.theme = theme;
    }
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.setItem("aiflux_theme", theme);
      }
    } catch {
      /* ignore */
    }
  }, [theme]);

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        if (typeof localStorage !== "undefined") {
          localStorage.setItem("aiflux_sidebar_collapsed", next ? "1" : "0");
        }
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const activeTheme = THEMES.find((t) => t.id === theme) ?? THEMES[0]!;
  const initials = (me.organization_name || "CA")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <button
          type="button"
          className="sidebar-toggle-btn"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand navigation sidebar" : "Collapse navigation sidebar"}
          onClick={toggleSidebar}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="9" y1="3" x2="9" y2="21" />
          </svg>
        </button>
        <BrandMark />
        <span className="portal-name">{portalName}</span>
        <span className="live-pill">
          <span className="live-dot" aria-hidden="true" />
          Live · Azure Foundry
        </span>
        <button className="btn menu-btn" aria-expanded={open} aria-controls="sidenav" onClick={() => setOpen(!open)}>Menu</button>
        <div className="who">
          <div className="theme-dropdown-wrap">
            <button
              type="button"
              className="theme-dropdown-trigger"
              aria-haspopup="listbox"
              aria-expanded={themeMenuOpen}
              aria-label="Color theme"
              onClick={() => setThemeMenuOpen((o) => !o)}
            >
              <span className="theme-swatch" style={{ background: activeTheme.color }} aria-hidden="true" />
              <span>Theme: {activeTheme.label}</span>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            {themeMenuOpen && (
              <div className="theme-dropdown-menu" role="listbox" aria-label="Select color theme">
                {THEMES.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="option"
                    aria-selected={theme === t.id}
                    className={theme === t.id ? "theme-dropdown-item active" : "theme-dropdown-item"}
                    onClick={() => {
                      setTheme(t.id);
                      setThemeMenuOpen(false);
                    }}
                  >
                    <span className="theme-swatch" style={{ background: t.color }} aria-hidden="true" />
                    <span>{t.label}</span>
                    {theme === t.id && <span className="theme-check" aria-hidden="true">✓</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="who-profile">
            <div className="who-avatar" aria-hidden="true">{initials}</div>
            <span>
              <strong>{me.organization_name}</strong>
              <small>{me.role === "ids_admin" ? "IDS administrator" : "Customer"}</small>
            </span>
          </div>
          <button className="btn" onClick={signOut}>Sign out</button>
        </div>
      </header>
      <div className="body">
        <nav
          id="sidenav"
          className={`${open ? "side open" : "side"}${collapsed ? " collapsed" : ""}`}
          aria-label="Primary"
        >
          {nav.map((n, i) => {
            const showSection = !collapsed && n.section && (i === 0 || nav[i - 1]?.section !== n.section);
            return (
              <div key={n.to} style={{ display: "contents" }}>
                {showSection && <span className="side-section-label">{n.section}</span>}
                <NavLink to={n.to} title={n.label} onClick={() => setOpen(false)}>
                  {navIconFor(n.to)}
                  {!collapsed && <span>{n.label}</span>}
                </NavLink>
              </div>
            );
          })}
        </nav>
        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}