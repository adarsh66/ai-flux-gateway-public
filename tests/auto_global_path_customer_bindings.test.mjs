/** Separate read-only check, so a historical diagnostic source mismatch cannot
 * prevent checking the current customer worker's retained input bindings.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

test("customer cm38 retained input hashes remain exact independently", () => {
  const root = new URL("../", import.meta.url);
  const read = path => readFileSync(new URL(path, root));
  const evidence = JSON.parse(read(".deployment/customer-send-independent-reconcile-20261029T113000Z/preflight.json"));
  assert.ok(Object.keys(evidence.input_hashes).length > 0);
  const drift = Object.entries(evidence.input_hashes).filter(([name, hash]) =>
    createHash("sha256").update(read(name)).digest("hex") !== hash).map(([name]) => name);
  assert.deepEqual(drift, []);
});