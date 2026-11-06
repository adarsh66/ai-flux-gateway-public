// Offline stdin/stdout adapter only. No clock, filesystem, HTTP or mutations.
import { renderProposal } from "./auto_global_path_exception.mjs";
let text = "";
for await (const chunk of process.stdin) {
  text += chunk;
  if (text.length > 2000000) throw new Error("bounded input");
}
const input = JSON.parse(text);
if (Object.keys(input).sort().join() !== "diagnosticOriginal,globalOriginal,window") throw new Error("finite inputs");
const result = renderProposal({ ...input, globalOriginal: Buffer.from(input.globalOriginal),
  diagnosticOriginal: Buffer.from(input.diagnosticOriginal) });
process.stdout.write(JSON.stringify({ expression: result.expression, diffs: result.diffs,
  global: result.global.toString(), diagnostic: result.diagnostic.toString() }));