// Offline stdin/stdout bridge; never imports a release executor.
import { renderOct30 } from "../proposals/auto_path_oct30.mjs";
let text = "";
for await (const part of process.stdin) text += part;
const input = JSON.parse(text);
const out = renderOct30({ globalOriginal: Buffer.from(input.global, "base64"),
  diagnosticOriginal: Buffer.from(input.revision, "base64"), window: input.window });
process.stdout.write(JSON.stringify({ expression: out.expression, diffs: out.diffs,
  global: out.global.toString("base64"), revision: out.diagnostic.toString("base64") }));