// Direct installed TypeScript only: no npm, esbuild, Vite, Vitest or network.
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const directory = resolve(".validation/admin-archival-20261104");
const receipt = process.argv[2] ?? "typecheck01.json";
if (!/^typecheck[0-9]+\.json$/.test(receipt)) throw new Error("Use a new local typecheck receipt name");
mkdirSync(directory, { recursive: true });
// Fail before any compiler execution if this one-shot stage was consumed.
writeFileSync(resolve(directory, `${receipt}.started`), new Date().toISOString() + "\n", { flag: "wx" });
const results = [];
for (const project of ["packages/ui", "apps/admin-portal", "apps/customer-portal"]) {
  const run = spawnSync(process.execPath, ["node_modules/typescript/bin/tsc", "-p", `${project}/tsconfig.json`, "--noEmit"], {
    encoding: "utf8", timeout: 60000, windowsHide: true,
  });
  const item = { project, exit: run.status, error: run.error?.message ?? null, output: (run.stdout ?? "") + (run.stderr ?? "") };
  results.push(item);
  console.log(JSON.stringify(item));
}
writeFileSync(resolve(directory, receipt), JSON.stringify({ at: new Date().toISOString(), results }, null, 2) + "\n", { flag: "wx" });
process.exitCode = results.every(result => result.exit === 0) ? 0 : 1;