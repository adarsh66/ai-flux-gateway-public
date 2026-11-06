// Offline stdin/stdout bridge; never imports a historical executor.
import { renderProposal } from "../proposals/auto_global_path_exception.mjs";
let input = "";
for await (const chunk of process.stdin) input += chunk;
const value = JSON.parse(input);
const p = renderProposal({ globalOriginal: Buffer.from(value.global, "base64"),
  diagnosticOriginal: Buffer.from(value.revision, "base64"), window: value.window });
process.stdout.write(JSON.stringify({ global: p.global.toString("base64"),
  revision: p.diagnostic.toString("base64"), expression: p.expression, diffs: p.diffs }));