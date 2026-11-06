// Only the reservation's exact fixed IP differs from the frozen browser source.
import { SOURCE as original } from "./auto_path_diagnostic_browser.mjs";
const before = 'r.IP === "167.103.66.248"';
const after = 'r.IP === "167.103.67.80"';
if (original.split(before).length !== 2 || original.split("167.103.66.248").length !== 2
    || original.includes("167.103.67.80")) throw new Error("finite browser IP guard");
export const SOURCE = original.replace(before, after);
if (SOURCE.replace(after, before) !== original) throw new Error("browser IP-only delta");
if (process.argv[1]?.replaceAll("\\", "/").endsWith("/auto_path_oct30_browser.mjs")
    && process.argv[2] === "--source") process.stdout.write(SOURCE);