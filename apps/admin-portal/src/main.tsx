import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import {
  AdminBudgetsAndFinOpsPage,
  AdminLocalUsersPage,
  AdminModelRouterPage,
  AuthGate,
  ContentSafetySettingsPage,
  GatewaySettingsPage,
  MembersPage,
  OrganizationsPage,
  PricesPage,
  SafetyPage,
  Shell,
  SubscriptionsPage,
  UsagePage,
  type NavItem,
} from "@aiflux/ui";

const nav: NavItem[] = [
  { to: "/budgets", label: "OpCo budgets & FinOps", section: "FinOps & Routing" },
  { to: "/model-router", label: "Model router & catalog", section: "FinOps & Routing" },
  { to: "/prices", label: "Rate card & pricing", section: "FinOps & Routing" },
  { to: "/usage", label: "Showback", section: "FinOps & Routing" },
  { to: "/content-safety", label: "Content safety", section: "Guardrails & Traffic" },
  { to: "/settings", label: "Gateway settings", section: "Guardrails & Traffic" },
  { to: "/safety", label: "Safety events", section: "Guardrails & Traffic" },
  { to: "/subscriptions", label: "Subscriptions", section: "Tenants & Access" },
  { to: "/organizations", label: "Organizations", section: "Tenants & Access" },
  { to: "/local-users", label: "Portal users (DB)", section: "Tenants & Access" },
  { to: "/members", label: "Entra directory", section: "Tenants & Access" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate portalName="IDS admin portal" allowedRoles={["ids_admin"]} env={import.meta.env}>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route element={<Shell portalName="IDS admin portal" nav={nav} />}>
            <Route index element={<Navigate to="/budgets" replace />} />
            <Route path="/budgets" element={<AdminBudgetsAndFinOpsPage />} />
            <Route path="/model-router" element={<AdminModelRouterPage />} />
            <Route path="/local-users" element={<AdminLocalUsersPage />} />
            <Route path="/usage" element={<UsagePage admin />} />
            <Route path="/safety" element={<SafetyPage />} />
            <Route path="/content-safety" element={<ContentSafetySettingsPage />} />
            <Route path="/settings" element={<GatewaySettingsPage />} />
            <Route path="/subscriptions" element={<SubscriptionsPage />} />
            <Route path="/organizations" element={<OrganizationsPage />} />
            <Route path="/members" element={<MembersPage />} />
            <Route path="/prices" element={<PricesPage />} />
            <Route path="*" element={<Navigate to="/budgets" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthGate>
  </StrictMode>,
);