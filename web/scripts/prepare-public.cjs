/**
 * prepare-public.cjs — runs as part of `npm run build` (before `vite build`).
 *
 * 1. Runs the Python pipeline: python3 ../scripts/build_quotedesk.py
 *    Rebuilds web/public/data/*.json from the real UCI Online Retail
 *    corpus and the seeded quote-request inbox, proving the shipped
 *    payloads are pipeline-generated.
 * 2. Copies data/test-vectors.json into web/public/data/ (shared contract).
 * 3. Writes web/public/data/stamp.json with repo, git sha, UTC build time.
 * 4. Exits non-zero if the pipeline produced no quotes or no price book.
 */
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const WEB_DIR = path.resolve(__dirname, "..");
const ROOT_DIR = path.resolve(WEB_DIR, "..");
const PUBLIC_DATA = path.join(WEB_DIR, "public", "data");

function fail(msg) {
  console.error(`prepare-public: ${msg}`);
  process.exit(1);
}

function gitSha() {
  try {
    return execFileSync("git", ["-C", ROOT_DIR, "rev-parse", "--short", "HEAD"], {
      encoding: "utf8",
    }).trim();
  } catch {
    return "unknown";
  }
}

console.log("prepare-public: running python3 ../scripts/build_quotedesk.py ...");
try {
  execFileSync("python3", ["../scripts/build_quotedesk.py"], {
    cwd: WEB_DIR,
    stdio: "inherit",
  });
} catch (e) {
  fail(`pipeline script failed (${e && e.message ? e.message : e})`);
}

const quotesPath = path.join(PUBLIC_DATA, "quotes.json");
if (!fs.existsSync(quotesPath)) {
  fail("quotes.json missing after pipeline run");
}
const quotes = JSON.parse(fs.readFileSync(quotesPath, "utf8"));
if (!Array.isArray(quotes) || quotes.length === 0) {
  fail("quotes.json is empty");
}
console.log(`prepare-public: ${quotes.length} quotes shipped`);

const bookPath = path.join(PUBLIC_DATA, "pricebook.json");
if (!fs.existsSync(bookPath)) {
  fail("pricebook.json missing after pipeline run");
}
const book = JSON.parse(fs.readFileSync(bookPath, "utf8"));
if (!Array.isArray(book) || book.length < 1000) {
  fail("pricebook.json looks truncated");
}
console.log(`prepare-public: price book shipped (${book.length} SKUs)`);

const vectors = path.join(ROOT_DIR, "data", "test-vectors.json");
if (!fs.existsSync(vectors)) {
  fail("data/test-vectors.json missing");
}
fs.mkdirSync(PUBLIC_DATA, { recursive: true });
fs.copyFileSync(vectors, path.join(PUBLIC_DATA, "test-vectors.json"));
console.log("prepare-public: test-vectors.json copied");

const stamp = {
  repo: "tidaaartorhem/ai-quote-builder",
  sha: gitSha(),
  built_utc: new Date().toISOString(),
};
fs.writeFileSync(path.join(PUBLIC_DATA, "stamp.json"), JSON.stringify(stamp, null, 2) + "\n");
console.log(`prepare-public: stamp.json written (${stamp.sha})`);
