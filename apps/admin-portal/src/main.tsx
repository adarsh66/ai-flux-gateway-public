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
  OrganizationsPage,
  PricesPage,
  SafetyPage,
  Shell,
  SubscriptionsPage,
  type NavItem,
} from "@aiflux/ui";

const nav: NavItem[] = [
  { to: "/budgets", label: "Quotas & Chargeback", section: "Commercial & FinOps" },
  { to: "/prices", label: "Pricing & Margins", section: "Commercial & FinOps" },
  { to: "/model-router", label: "Models & Auto-Router", section: "AI Gateway & Routing" },
  { to: "/settings", label: "Traffic & Rate Limits", section: "AI Gateway & Routing" },
  { to: "/content-safety", label: "Content Guardrails", section: "AI Gateway & Routing" },
  { to: "/safety", label: "Guardrail Logs", section: "AI Gateway & Routing" },
  { to: "/organizations", label: "Customer Orgs", section: "Customers & Access" },
  { to: "/subscriptions", label: "Subscriptions", section: "Customers & Access" },
  { to: "/local-users", label: "User Access", section: "Customers & Access" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate portalName="IDS admin portal" allowedRoles={["ids_admin"]} env={{ VITE_AUTH_MODE: "local", ...import.meta.env }}>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route element={<Shell portalName="IDS admin portal" nav={nav} />}>
            <Route index element={<Navigate to="/budgets" replace />} />
            <Route path="/budgets" element={<AdminBudgetsAndFinOpsPage initialTab="quotas" />} />
            <Route path="/usage" element={<AdminBudgetsAndFinOpsPage initialTab="usage" />} />
            <Route path="/model-router" element={<AdminModelRouterPage />} />
            <Route path="/local-users" element={<AdminLocalUsersPage initialTab="portal" />} />
            <Route path="/members" element={<AdminLocalUsersPage initialTab="sso" />} />
            <Route path="/safety" element={<SafetyPage />} />
            <Route path="/content-safety" element={<ContentSafetySettingsPage />} />
            <Route path="/settings" element={<GatewaySettingsPage />} />
            <Route path="/subscriptions" element={<SubscriptionsPage />} />
            <Route path="/organizations" element={<OrganizationsPage />} />
            <Route path="/prices" element={<PricesPage />} />
            <Route path="*" element={<Navigate to="/budgets" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthGate>
  </StrictMode>,
);