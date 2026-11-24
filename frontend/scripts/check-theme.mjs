import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendDir, "..");
const read = (path) => readFileSync(resolve(repoRoot, path), "utf8");

const theme = read("frontend/src/theme.css");
const main = read("frontend/src/main.tsx");
const app = read("frontend/src/App.tsx");
const prototype = read("prototype/GitScout_v0.8.1_DarkNeon_Prototype.html");

const tokens = {
  "--gs-bg": "#070c16",
  "--gs-text": "#edf4ff",
  "--gs-cyan": "#48d5ef",
  "--gs-blue": "#548dff",
  "--gs-violet": "#9673ff",
  "--gs-green": "#43d9a6",
};
for (const [name, value] of Object.entries(tokens)) {
  const pattern = new RegExp(name + "\\s*:\\s*" + value);
  assert.match(theme, pattern, "Missing React theme token " + name);
  assert.match(prototype, pattern, "Missing prototype theme token " + name);
}

const requiredOverrides = [
  "tbody td strong, .table-card td strong",
  ".job-summary-card > strong, .recommendation-summary-card > strong",
  ".job-detail-stats span",
  ".schedule-fields input, .schedule-fields select",
  ".stars-api-note",
  ".compare-selectors-row select",
  ".recommendation-warning span, .recommendation-warning small",
  ".recommendation-dimension-filter select",
  ".workspace-search",
  ".workspace-inline-editor input",
  ".research-note-item",
  ".research-project-row.active",
  ".system-token-instructions > code",
  ".button-workspace-active",
];
for (const selector of requiredOverrides) {
  assert.ok(theme.includes(selector), "Missing theme override: " + selector);
}

assert.ok(main.indexOf('import "./styles.css";') < main.indexOf('import "./theme.css";'), "theme.css must load after styles.css");
const routes = [...app.matchAll(/<Route path="([^"]+)" element={<([A-Za-z0-9]+) \/>} \/>/g)];
assert.equal(routes.length, 12, "Expected 12 React routes, including repository detail");
for (const route of routes) {
  const component = route[2];
  const file = resolve(frontendDir, "src", "pages", component + ".tsx");
  assert.ok(existsSync(file), "Missing page component: " + component);
}
const scriptStart = prototype.indexOf("<script>");
const scriptEnd = prototype.indexOf("</script>", scriptStart);
assert.ok(scriptStart >= 0 && scriptEnd > scriptStart, "Prototype inline script is missing");
const inlineScripts = [prototype.slice(scriptStart + 8, scriptEnd)];
assert.equal(inlineScripts.length, 1, "Expected one standalone prototype script");
new Script(inlineScripts[0]);
const functionNames = [...inlineScripts[0].matchAll(/function\s+([A-Za-z_$][\w$]*)\s*\(/g)].map((match) => match[1]);
const functionCounts = new Map();
for (const name of functionNames) functionCounts.set(name, (functionCounts.get(name) || 0) + 1);
const duplicateFunctions = [...functionCounts.entries()].filter(([, count]) => count > 1).map(([name]) => name);
assert.deepEqual(duplicateFunctions, [], "Prototype must not redeclare helper functions");
assert.ok(prototype.includes('"repository-detail":()=>repositoryDetailBody()'), "Prototype repository detail view is missing");
assert.ok(prototype.includes("function openRepository(repo)"), "Prototype repository detail entry point is missing");
assert.ok(prototype.includes("--ink:var(--gs-text)"), "Prototype legacy text token alias is missing");

console.log("GitScout design-system check passed: tokens, overrides, route files and prototype parity.");
