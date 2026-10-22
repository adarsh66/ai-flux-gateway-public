import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import {
  AuthGate,
  CustomerCreditsPage,
  CustomerKeysPage,
  ModelGardenPage,
  PlaygroundPage,
  Shell,
  UsagePage,
  type NavItem,
} from "@aiflux/ui";

const nav: NavItem[] = [
  { to: "/overview", label: "Overview & Credits", section: "FinOps & Catalog" },
  { to: "/models", label: "Model Catalog", section: "FinOps & Catalog" },
  { to: "/playground", label: "Playground", section: "Developer Workspace" },
  { to: "/keys", label: "API Keys & Access", section: "Developer Workspace" },
  { to: "/usage", label: "Usage & Telemetry", section: "Developer Workspace" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate portalName="Customer portal" allowedRoles={["customer", "ids_admin"]} env={import.meta.env}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell portalName="Customer portal" nav={nav} />}>
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<CustomerCreditsPage />} />
            <Route path="/credits" element={<CustomerCreditsPage />} />
            <Route path="/models" element={<ModelGardenPage />} />
            <Route path="/model-garden" element={<ModelGardenPage />} />
            <Route path="/keys" element={<CustomerKeysPage />} />
            <Route path="/subscriptions" element={<Navigate to="/models" replace />} />
            <Route path="/playground" element={<PlaygroundPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthGate>
  </StrictMode>,
);