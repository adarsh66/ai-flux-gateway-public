import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import {
  AdminBudgetsAndFinOpsPage,
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
  { to: "/budgets", label: "OpCo budgets & FinOps" },
  { to: "/model-router", label: "Model router & garden" },
  { to: "/usage", label: "Showback" },
  { to: "/safety", label: "Safety events" },
  { to: "/content-safety", label: "Content safety" },
  { to: "/settings", label: "Gateway settings" },
  { to: "/subscriptions", label: "Subscriptions" },
  { to: "/organizations", label: "Organizations" },
  { to: "/members", label: "Members" },
  { to: "/prices", label: "Prices" },
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