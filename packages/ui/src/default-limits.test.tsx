import { describe, expect, it } from "vitest";
import { textChatRequest } from "./chat";
import { outcomeView } from "./pages/PlaygroundPage";
import { POC_DEFAULTS, pocEffective } from "./pages/PocControlsForm";

describe("default quotas and response allowance", () => {
  it("new unknown subscriptions inherit without initialization", () => {
    expect(pocEffective(POC_DEFAULTS, "new-org", "new-sub").limits).toEqual({
      rpm: 60, tpm: 300000, token_quota: 20000000, request_quota: 50000,
    });
  });
  it.each(["auto", "gpt-4o"])("uses authoritative output metadata for %s and honors a lower budget", (model) => {
    const messages = [{ role: "user" as const, content: "hello" }];
    expect(textChatRequest(model, messages, 4096).max_completion_tokens).toBe(4096);
    expect(textChatRequest(model, messages, 32).max_completion_tokens).toBe(32);
    expect(textChatRequest(model, messages, undefined)).not.toHaveProperty("max_completion_tokens");
  });
  it("length remains a warning, not a quota failure or completion guarantee", () => {
    expect(outcomeView({ outcome: "length", content: "partial", toolCalls: [],
      finishReason: "length", usage: null, sawDone: true })).toMatchObject({
      tone: "warn", label: "Length limit",
    });
  });
});