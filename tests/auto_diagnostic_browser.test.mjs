import test from "node:test";
import assert from "node:assert/strict";
import { validBody, install, TEXT, NORMAL, REVISION } from "../scripts/deployment/auto_diagnostic_browser.mjs";

const body = () => ({ model: "gpt-5.4-mini", messages: [{ role: "user", content: TEXT }], stream: false, max_completion_tokens: 1024 });
test("fixed exact benign body only", () => {
  assert.equal(validBody(body()), true);
  for (const bad of [null, {}, { ...body(), messages: [null] }]) assert.equal(validBody(bad), false);
  for (const change of [b => b.stream = true, b => b.messages[0].content += "!", b => b.model = "auto",
    b => b.max_completion_tokens = 1025, b => b.messages.push({ role: "system", content: "other" }), b => b.tools = []]) {
    const b = body(); change(b); assert.equal(validBody(b), false);
  }
});
test("one POST URL only auth uninspected and repeat abort", async () => {
  let handler;
  const end = new Date(Date.now() + 120000).toISOString();
  const page = { route: async (_, h) => { handler = h; }, unroute: async () => {} };
  const intent = { manifest_sha256: "fixture", end, attempt_budget: 1, scoring_budget: 1, completion_budget: 0,
    retry_budget: 0, fixed_text: TEXT, model: "gpt-5.4-mini", path: "/dev/llm/v1;rev=2/chat/completions" };
  const installed = await install(page, intent, "fixture", end);
  const operations = [];
  const route = { request: () => ({ method: () => "POST", url: () => NORMAL, postDataJSON: body }),
    continue: async options => operations.push(options), abort: async reason => operations.push(reason) };
  await handler(route); await handler(route);
  assert.deepEqual(operations, [{ url: REVISION }, "blockedbyclient"]);
  assert.equal(installed.consumed(), true);
});
test("missing durable bound intent rejects", async () => {
  await assert.rejects(install({}, {}, "fixture", "expired"));
});