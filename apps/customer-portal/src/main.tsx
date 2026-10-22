import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import {
  AuthGate,
  CustomerCreditsPage,
  CustomerKeysPage,
  ModelGardenPage,
  ModelsPage,
  PlaygroundPage,
  Shell,
  UsagePage,
  type NavItem,
} from "@aiflux/ui";

const nav: NavItem[] = [
  { to: "/model-garden", label: "Model garden & pricing" },
  { to: "/credits", label: "Credits & FinOps" },
  { to: "/keys", label: "API keys" },
  { to: "/playground", label: "Playground" },
  { to: "/usage", label: "Usage & cost" },
  { to: "/models", label: "Models" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate portalName="Customer portal" allowedRoles={["customer", "ids_admin"]} env={import.meta.env}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell portalName="Customer portal" nav={nav} />}>
            <Route index element={<Navigate to="/model-garden" replace />} />
            <Route path="/model-garden" element={<ModelGardenPage />} />
            <Route path="/credits" element={<CustomerCreditsPage />} />
            <Route path="/keys" element={<CustomerKeysPage />} />
            <Route path="/models" element={<ModelsPage />} />
            <Route path="/subscriptions" element={<Navigate to="/models" replace />} />
            <Route path="/playground" element={<PlaygroundPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="*" element={<Navigate to="/model-garden" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthGate>
  </StrictMode>,
);