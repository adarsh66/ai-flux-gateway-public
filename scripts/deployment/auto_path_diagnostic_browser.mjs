// Separate finite successor; historical06 and its bound artifacts stay untouched.
// SOURCE is standalone in the browser sandbox (no timers, Node globals or imports).
import { SOURCE as original } from "./auto_diagnostic_browser06.mjs";

export const SOURCE = original.replaceAll("\r\n", "\n")
  .replace("diagnostic06Attempt", "autoPathDiagnosticAttempt")
  .replace("DIAGNOSTIC06_CORRECTION_ONE_USER_ATTEMPT", "AUTO_PATH_DIAGNOSTIC_ONE_NEW_ATTEMPT")
  .replace("DIAGNOSTIC05B_TIMER_GLOBAL_FAILURE", "GLOBAL_ORIGINAL_PATH_CONJUNCTION")
  .replace("binding.cleanup_complete === true", "binding.prerequisite_offline_verified === true")
  .replace("const r = binding?.reservation;", `const r = binding?.reservation;
    guard(typeof binding?.nonce === "string" && /^[a-f0-9]{32}$/.test(binding.nonce)
      && r?.nonce === binding.nonce && hex(binding.review_sha256) && hex(binding.claim_sha256)
      && r.review_sha256 === binding.review_sha256);`);

// Explicit offline export only. Importing the module never invokes a browser.
if (process.argv[1]?.replaceAll("\\", "/").endsWith("/auto_path_diagnostic_browser.mjs")
    && process.argv[2] === "--source") process.stdout.write(SOURCE);