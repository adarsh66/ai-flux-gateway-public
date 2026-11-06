import { describe, expect, it } from "vitest";
import { customerModelDescriptions, customerModelPresentation, isCatalogDeployed } from "./modelPresentation";

const model = {
  id: "unknown-model", display_name: "Future model", capabilities: ["chat"],
  enabled: true, coming_soon: false,
};

describe("customer model presentation", () => {
  it("labels Decision-1 scoring independently of disabled chat eligibility", () => {
    const scoring = { ...model, id: "Decision-1", model_kind: "scoring" as const, enabled: false };
    expect(customerModelPresentation(scoring).displayName).toBe("Microsoft Decision-1");
    expect(customerModelPresentation(scoring).description).toContain("Scoring-only model used by Auto");
    expect(customerModelPresentation(scoring).description).not.toContain("future availability");
    expect(isCatalogDeployed({ ...scoring, scoring_available: true })).toBe(true);
    for (const scoring_available of [false, null, undefined]) {
      expect(isCatalogDeployed({ ...scoring, enabled: true, scoring_available })).toBe(false);
    }
    expect(isCatalogDeployed(model)).toBe(true);
    expect(isCatalogDeployed({ ...model, enabled: false })).toBe(false);
    expect(isCatalogDeployed({ ...model, coming_soon: true })).toBe(false);
  });

  it("provides concise copy for every current chat model without operational details", () => {
    expect(Object.keys(customerModelDescriptions).sort()).toEqual([
      "gpt-5.6-luna", "gpt-6.1-sol", "gpt-5.4-mini", "gpt-4o",
      "DeepSeek-V4-Flash", "DeepSeek-V4-Pro", "Kimi-K2.7-Code",
      "grok-4.3", "grok-4-20-reasoning", "grok-4-1-fast-reasoning",
      "FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3",
    ].sort());
    for (const [id, description] of Object.entries(customerModelDescriptions)) {
      expect(customerModelPresentation({ ...model, id }).description).toBe(description);
      expect(description.length).toBeGreaterThan(20);
      expect(description.length).toBeLessThanOrEqual(160);
      expect(description).not.toMatch(/APIM|verified|Persistent POC|RPM|TPM|quota|expiry|retries|project-demo|2026-/i);
    }
  });

  it("renames only Luna without mutating its identity or inventory metadata", () => {
    const luna = { ...model, id: "gpt-5.6-luna", display_name: "Luna — bounded demo (2026-07-09)" };
    expect(customerModelPresentation(luna).displayName).toBe("gpt-5.6-luna");
    expect(luna.display_name).toBe("Luna — bounded demo (2026-07-09)");
    expect(customerModelPresentation(model).displayName).toBe(model.display_name);
  });

  it("never falls back to inventory diagnostics, even for unexpected IDs", () => {
    for (const id of ["future-model", "toString", "__proto__"]) {
      expect(customerModelPresentation({ ...model, id }).description).toContain("conversational AI");
    }
    expect(customerModelPresentation({ ...model, capabilities: [] }).description).toContain("capabilities");
  });

  it("does not imply routing-only or onboarding models are callable chat models", () => {
    expect(customerModelPresentation({ ...model, id: "auto" }).description).toContain("rather than a standalone chat model");
    expect(customerModelPresentation({ ...model, capabilities: ["routing-only"] }).description).toContain("model-routing");
    for (const state of [{ coming_soon: true }, { enabled: false }]) {
      expect(customerModelPresentation({ ...model, id: "gpt-4o", ...state }).description).toContain("future availability");
    }
  });
});