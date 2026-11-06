// Execute the entire frozen six-test suite against the exact protocol12 adapter.
// No browser, HTTP, inference or production interaction occurs in these VM mocks.
import { readFileSync } from 'node:fs';
const path = new URL('./auto_resume11_browser.test.mjs', import.meta.url);
let suite = readFileSync(path, 'utf8');
const declaration = "const source = readFileSync(new URL('../scripts/deployment/auto_resume11_browser.js', import.meta.url), 'utf8');";
if (suite.split(declaration).length !== 2) throw Error('FROZEN11_TEST_SOURCE_GATE');
suite = suite.replace(declaration, declaration.replace('const source =', 'const template =') +
  "\nif (template.split('request.schema === 11').length !== 2) throw Error('FROZEN11_BROWSER_GATE');\n" +
  "const source = template.replace('request.schema === 11', 'request.schema === 12');");
suite = suite.replace('schema: 11, phase', 'schema: 12, phase');
// A local data module has no useful relative base; bind all file URLs to the
// actual frozen suite location before evaluating its unchanged six assertions.
suite = suite.replaceAll('import.meta.url', JSON.stringify(path.href));
await import('data:text/javascript;base64,' + Buffer.from(suite).toString('base64'));