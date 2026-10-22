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

  const initials = (me.organization_name || "OP")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <BrandMark />
        <span className="portal-name">{portalName}</span>
        <span className="live-pill">
          <span className="live-dot" aria-hidden="true" />
          Live · Azure Foundry
        </span>
        <button className="btn menu-btn" aria-expanded={open} aria-controls="sidenav" onClick={() => setOpen(!open)}>Menu</button>
        <div className="who">
          <div className="theme-switcher" role="group" aria-label="Color theme preset">
            {THEMES.map((t) => (
              <button
                key={t.id}
                type="button"
                className={theme === t.id ? "theme-chip active" : "theme-chip"}
                onClick={() => setTheme(t.id)}
              >
                <span className="theme-swatch" style={{ background: t.color }} aria-hidden="true" />
                {t.label}
              </button>
            ))}
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
        <nav id="sidenav" className={open ? "side open" : "side"} aria-label="Primary">
          <span className="side-section-label">Workspace Navigation</span>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} onClick={() => setOpen(false)}>
              {navIconFor(n.to)}
              <span>{n.label}</span>
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