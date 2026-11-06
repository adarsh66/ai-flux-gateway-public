// R5-only offline exports. Historical proposals, BEFORE spans and storage stay frozen.
import { renderProposal } from "../proposals/auto_global_path_exception.mjs";
import { SOURCE as original } from "./auto_path_diagnostic_browser.mjs";
import { SOURCE as oct30 } from "./auto_path_oct30_browser.mjs";

const current = 'r.IP === "167.103.66.248"';
const historical = 'r.IP === "167.103.67.80"';
if (original.split(current).length !== 2 || original.includes(historical)
    || oct30.replace(historical, current) !== original) throw new Error("r5 finite browser IP guard");
export const SOURCE = original;

if (process.argv[1]?.replaceAll("\\", "/").endsWith("/auto_path_oct30_r5_bridge.mjs")) {
  if (process.argv[2] === "--source") process.stdout.write(SOURCE);
  else {
    let text = "";
    for await (const part of process.stdin) text += part;
    const input = JSON.parse(text);
    const out = renderProposal({ globalOriginal: Buffer.from(input.global, "base64"),
      diagnosticOriginal: Buffer.from(input.revision, "base64"), window: input.window });
    process.stdout.write(JSON.stringify({ expression: out.expression, diffs: out.diffs,
      global: out.global.toString("base64"), revision: out.diagnostic.toString("base64") }));
  }
}