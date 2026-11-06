// Pure Oct30 successor. Never edit the historical proposal or its fixtures.
import { renderProposal, admissionExpression, sha256 } from "./auto_global_path_exception.mjs";

export const OLD_IP = "167.103.66.248";
export const IP = "167.103.67.80";
const require = (ok, label) => { if (!ok) throw new Error(label); };
const count = (value, needle) => value.split(needle).length - 1;

export function expression(window) {
  const old = admissionExpression(window);
  const literal = 'context.Request.IpAddress == "' + OLD_IP + '"';
  require(count(old, literal) === 1 && count(old, OLD_IP) === 1 && !old.includes(IP), "one fixed IP predicate");
  return old.replace(literal, 'context.Request.IpAddress == "' + IP + '"');
}

export function renderOct30(input) {
  const old = renderProposal(input), predicate = expression(input.window);
  const result = { ...old, expression: predicate };
  const diffs = {};
  for (const [name, spanName] of [["global", "global"], ["diagnostic", "diagnostic"]]) {
    const bytes = old[name], span = old.diffs[spanName];
    require(count(bytes.toString(), OLD_IP) === 1 && !bytes.includes(Buffer.from(IP))
      && count(span.after, OLD_IP) === 1, "finite single admission IP occurrence");
    // The immutable diagnostic06 BEFORE span also names OLD_IP. Preserve it
    // as historical provenance; only the candidate AFTER span is changed.
    const after = span.after.replace(OLD_IP, IP);
    const oldSpan = Buffer.from(span.after), newSpan = Buffer.from(after);
    require(bytes.subarray(span.offset, span.offset + oldSpan.length).equals(oldSpan), "known condition span");
    const candidate = Buffer.concat([bytes.subarray(0, span.offset), newSpan, bytes.subarray(span.offset + oldSpan.length)]);
    require(candidate.toString().replace(IP, OLD_IP) === bytes.toString(), "IP-only exact bytes delta");
    result[name] = candidate;
    diffs[spanName] = Object.freeze({ ...span, after, after_sha256: sha256(newSpan) });
  }
  result.diffs = Object.freeze(diffs);
  result.candidateHashes = Object.freeze({ global: sha256(result.global), diagnostic: sha256(result.diagnostic) });
  return result;
}