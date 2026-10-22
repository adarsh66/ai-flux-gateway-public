import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../session";
import { BrandMark } from "./ui";

export interface NavItem {
  to: string;
  label: string;
}

type ThemeId = "daylight" | "obsidian" | "crimson" | "emerald";

const THEMES: { id: ThemeId; label: string; color: string }[] = [
  { id: "daylight", label: "Daylight", color: "#2563eb" },
  { id: "obsidian", label: "Obsidian", color: "#6366f1" },
  { id: "crimson", label: "Crimson", color: "#e11d48" },
  { id: "emerald", label: "Emerald", color: "#059669" },
];

function navIconFor(path: string): ReactNode {
  if (path.includes("garden") || path.includes("router")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
      </svg>
    );
  }
  if (path.includes("credit") || path.includes("budget") || path.includes("price")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <line x1="2" y1="10" x2="22" y2="10" />
      </svg>
    );
  }
  if (path.includes("key") || path.includes("subscription")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="7.5" cy="15.5" r="5.5" />
        <path d="m21 2-9.6 9.6" />
        <path d="m15.5 7.5 3 3L22 7l-3-3" />
      </svg>
    );
  }
  if (path.includes("playground")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="4 17 10 11 4 5" />
        <line x1="12" y1="19" x2="20" y2="19" />
      </svg>
    );
  }
  if (path.includes("safety")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    );
  }
  if (path.includes("user") || path.includes("member") || path.includes("organization")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
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
          {!collapsed && <span className="side-section-label">Workspace</span>}
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} title={n.label} onClick={() => setOpen(false)}>
              {navIconFor(n.to)}
              {!collapsed && <span>{n.label}</span>}
            </NavLink>
          ))}
        </nav>
        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}