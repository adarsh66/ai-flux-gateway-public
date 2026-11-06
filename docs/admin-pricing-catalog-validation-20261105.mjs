import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";

const root = new URL("../", import.meta.url);
const focused = [
  "packages/ui/src/rate-card.test.tsx",
  "packages/ui/src/external-rate-card.test.tsx",
  "packages/ui/src/pricing-history.test.tsx",
  "packages/ui/src/display-pricing.test.tsx",
  "packages/ui/src/modelPresentation.test.ts",
  "packages/ui/src/admin-catalog-route.test.tsx",
  "packages/ui/src/pricing-revision-viewer.test.tsx",
  "packages/ui/src/model-catalog.test.tsx",
];
const mode = process.argv[2] ?? "types";
const checks = mode === "types" ? [
  ["UI_TYPECHECK", ["node_modules/typescript/bin/tsc", "--noEmit", "-p", "packages/ui/tsconfig.json"]],
  ["ADMIN_TYPECHECK", ["node_modules/typescript/bin/tsc", "--noEmit", "-p", "apps/admin-portal/tsconfig.json"]],
  ["CUSTOMER_TYPECHECK", ["node_modules/typescript/bin/tsc", "--noEmit", "-p", "apps/customer-portal/tsconfig.json"]],
] : mode === "focused" ? [["FOCUSED_VITEST", ["node_modules/vitest/vitest.mjs", "run", ...focused]]] : [];
if (!checks.length) throw new Error("Unsupported validation mode");
console.log(`VALIDATION_START mode=${mode} node=${process.version}`);
const receipts = [];
for (const [check, args] of checks) {
  const result = spawnSync(process.execPath, args, { cwd: root, encoding: "utf8", windowsHide: true });
  const receipt = { check, exit: result.status, signal: result.signal, error: result.error?.message, stdout: result.stdout, stderr: result.stderr };
  receipts.push(receipt);
  writeFileSync(new URL(`admin-pricing-catalog-${mode}-${process.pid}-${receipts.length}.json`, import.meta.url), JSON.stringify({ node: process.version, receipts }, null, 2), { flag: "wx" });
  console.log(JSON.stringify(receipt));
}
console.log(`VALIDATION_END mode=${mode}`);