import { describe, expect, it } from "vitest";
import { customerModelDescriptions, customerModelPresentation } from "./modelPresentation";

const model = {
  id: "unknown-model", display_name: "Future model", capabilities: ["chat"],
  enabled: true, coming_soon: false,
};

describe("customer model presentation", () => {
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