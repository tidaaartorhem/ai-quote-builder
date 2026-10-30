/** TypeScript mirror of src/quotedesk/rules.py — must agree exactly.
 * Money is integer cents everywhere (half-up rounding), so Python ints
 * and JS numbers agree bit-for-bit. Match-score arithmetic mirrors the
 * Python expression term-for-term (IEEE 754 doubles evaluate
 * identically). The shared contract is data/test-vectors.json, asserted
 * by both pytest and vitest. */

const QTY_X = /^(\d+(?:\.\d+)?)\s*[x×]\s*(.+)$/i;
const QTY_N = /^(\d+)\s+(.+)$/;
const COUPLE = /^a?\s*couple of\s+(.+)$/i;

const HEADER_RES: RegExp[] = [
  /^\s*(hi|hello|hey|dear|good morning|good afternoon)\b/i,
  /^\s*(thanks|thank you|regards|cheers|sincerely|best)\b/i,
  /^\s*site visit\b/i,
  /^\s*walked\b/i,
  /^\s*here'?s what\b/i,
  /^\s*here is what\b/i,
  /^\s*(please|could you|kindly)\b/i,
  /^\s*let me know\b/i,
  /^\s*need this\b/i,
  /^\s*(from|date|subject|re|customer|attn|job|project|site|estimate|pricing)\s*:/i,
  /^\s*(quote request|parts list|price list|site notes)\b/i,
];

export interface ParsedLine {
  skip: boolean;
  qty: number;
  item: string;
}

export function parseLine(line: string): ParsedLine {
  const raw = line.trim();
  if (!raw) return { skip: true, qty: 0, item: "" };
  if (HEADER_RES.some((p) => p.test(raw))) return { skip: true, qty: 0, item: "" };
  let m = raw.match(QTY_X);
  if (m) return { skip: false, qty: parseFloat(m[1]), item: m[2].trim() };
  m = raw.match(COUPLE);
  if (m) return { skip: false, qty: 2, item: m[1].trim() };
  m = raw.match(QTY_N);
  if (m) return { skip: false, qty: parseInt(m[1], 10), item: m[2].trim() };
  return { skip: false, qty: 1, item: raw };
}

const STOPWORDS = new Set(
  "a an the and or of for to in on with by from at as is are was were be been it its this that these those your you we our their".split(" "),
);

export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 0 && !STOPWORDS.has(t) && !/^\d+$/.test(t));
}

export function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 0)
    .join(" ");
}

/** Bigrams as joined strings (tokens are [a-z0-9]+, so \u0001 is a safe join). */
export function bigrams(tokens: string[]): Set<string> {
  const s = new Set<string>();
  for (let i = 0; i + 1 < tokens.length; i++) {
    s.add(tokens[i] + "\u0001" + tokens[i + 1]);
  }
  return s;
}

export function matchScore(
  lineText: string,
  skuTokens: string[],
  skuBigrams: Set<string>,
  skuNorm: string,
): number {
  const lt = tokenize(lineText);
  const st = new Set(skuTokens);
  // Python: len(set(lt) & st) / len(lt) — dedupe for the intersection,
  // divide by the raw token count.
  const lset = new Set(lt);
  let inter = 0;
  lset.forEach((t) => {
    if (st.has(t)) inter++;
  });
  const recall = lt.length > 0 ? inter / lt.length : 0;
  const lnorm = normalize(lineText);
  const phrase =
    lnorm && skuNorm && (skuNorm.includes(lnorm) || lnorm.includes(skuNorm)) ? 1 : 0;
  const lb = bigrams(lt);
  let jacc = 0;
  if (lb.size > 0 || skuBigrams.size > 0) {
    let bi = 0;
    lb.forEach((b) => {
      if (skuBigrams.has(b)) bi++;
    });
    jacc = bi / (lb.size + skuBigrams.size - bi);
  }
  return recall * 55 + phrase * 25 + jacc * 20;
}

export function matchTier(score: number): string {
  if (score >= 75) return "AUTO";
  if (score >= 50) return "REVIEW";
  return "MANUAL";
}

export interface PricebookEntry {
  stock_code: string;
  description: string;
  median_price: number;
  unit_cents: number;
  transactions: number;
}

export interface SkuIndex {
  stock_code: string;
  description: string;
  unit_cents: number;
  tokens: string[];
  bigrams: Set<string>;
  norm: string;
}

export function buildIndex(entries: PricebookEntry[]): SkuIndex[] {
  return entries.map((e) => {
    const tokens = tokenize(e.description);
    return {
      stock_code: e.stock_code,
      description: e.description,
      unit_cents: e.unit_cents,
      tokens,
      bigrams: bigrams(tokens),
      norm: normalize(e.description),
    };
  });
}

export interface MatchResult {
  stock_code: string;
  description: string;
  unit_cents: number;
  score: number;
  tier: string;
  alternates: { stock_code: string; description: string; score: number }[];
}

export function bestMatch(item: string, index: SkuIndex[]): MatchResult {
  const scored = index.map((sku) => ({
    score: matchScore(item, sku.tokens, sku.bigrams, sku.norm),
    sku,
  }));
  scored.sort(
    (a, b) =>
      b.score - a.score ||
      (a.sku.stock_code < b.sku.stock_code
        ? -1
        : a.sku.stock_code > b.sku.stock_code
          ? 1
          : 0),
  );
  const best = scored[0];
  const tier = matchTier(best.score);
  return {
    stock_code: best.sku.stock_code,
    description: best.sku.description,
    unit_cents: best.sku.unit_cents,
    score: best.score,
    tier,
    alternates:
      tier === "REVIEW"
        ? scored.slice(1, 4).map((s) => ({
            stock_code: s.sku.stock_code,
            description: s.sku.description,
            score: s.score,
          }))
        : [],
  };
}

export const DISCOUNT_RATE: Record<string, [number, number]> = {
  Retail: [0, 100],
  Trade: [12, 100],
  Preferred: [20, 100],
};
const HST_NUM = 13;
const HST_DEN = 100;

function halfUpMul(cents: number, num: number, den: number): number {
  return Math.floor((cents * num + den / 2) / den);
}

export function fmtMoney(cents: number): string {
  return "$" + (cents / 100).toFixed(2);
}

export interface PricedLine {
  qty: number;
  item: string;
  tier: string;
  unit_cents: number | null;
  line_total_cents: number | null;
}

export function priceLines(
  lines: { qty: number; match: { tier: string; unit_cents: number } | null }[],
  customerTier: string,
): {
  subtotal_cents: number;
  discount_rate: string;
  discount_cents: number;
  hst_cents: number;
  total_cents: number;
} {
  let subtotal = 0;
  for (const ln of lines) {
    if (ln.match && (ln.match.tier === "AUTO" || ln.match.tier === "REVIEW")) {
      subtotal += Math.trunc(ln.qty * ln.match.unit_cents);
    }
  }
  const [dnum, dden] = DISCOUNT_RATE[customerTier] ?? [0, 100];
  const discount = halfUpMul(subtotal, dnum, dden);
  const discounted = subtotal - discount;
  const hst = halfUpMul(discounted, HST_NUM, HST_DEN);
  return {
    subtotal_cents: subtotal,
    discount_rate: `${dnum}%`,
    discount_cents: discount,
    hst_cents: hst,
    total_cents: discounted + hst,
  };
}

export interface DraftLine {
  qty: number;
  item: string;
  match: { tier: string; unit_cents: number; score: number } | null;
  unit_cents: number | null;
  line_total_cents: number | null;
}

export interface DraftQuote {
  id: string;
  customer: string;
  tier: string;
  created: string;
  valid_until: string;
  lines: DraftLine[];
  subtotal_cents: number;
  discount_rate: string;
  discount_cents: number;
  hst_cents: number;
  total_cents: number;
  match_health: number;
  needs_review: boolean;
}

export function matchHealth(lines: { match: { tier: string } | null }[]): number {
  if (lines.length === 0) return 0;
  const auto = lines.filter((l) => l.match && l.match.tier === "AUTO").length;
  return Math.round((100 * auto) / lines.length * 10) / 10;
}

export function draftQuote(q: DraftQuote): string {
  const out: string[] = [
    `QUOTATION ${q.id}`,
    `Date: ${q.created} - Valid until: ${q.valid_until}`,
    `Customer: ${q.customer} - ${q.tier} tier (${q.discount_rate} discount)`,
    ``,
    `Lines:`,
  ];
  for (const ln of q.lines) {
    const qty = String(ln.qty);
    if (!ln.match || ln.match.tier === "MANUAL") {
      out.push(`  ${qty} x ${ln.item} = UNPRICED  [MANUAL - no price-book match]`);
    } else {
      out.push(
        `  ${qty} x ${ln.item} @ ${fmtMoney(ln.match.unit_cents)} = ${fmtMoney(ln.line_total_cents ?? 0)}  [${ln.match.tier} ${ln.match.score.toFixed(1)}]`,
      );
    }
  }
  out.push(
    ``,
    `Subtotal: ${fmtMoney(q.subtotal_cents)}`,
    `Discount (${q.tier}, ${q.discount_rate}): -${fmtMoney(q.discount_cents)}`,
    `HST (13%): ${fmtMoney(q.hst_cents)}`,
    `TOTAL: ${fmtMoney(q.total_cents)}`,
    ``,
  );
  const health = q.match_health.toFixed(1);
  if (q.needs_review) {
    const unpriced = q.lines.filter((l) => l.line_total_cents === null).length;
    out.push(
      `Match health: ${health}% of lines AUTO - NEEDS REVIEW (${unpriced} line(s) unpriced).`,
    );
  } else {
    out.push(`Match health: ${health}% of lines AUTO.`);
  }
  out.push(`Status: PENDING HUMAN APPROVAL. Nothing has been sent.`);
  return out.join("\n");
}

export const TIER_LABEL: Record<string, string> = {
  AUTO: "Auto-priced",
  REVIEW: "Needs review",
  MANUAL: "Manual pricing",
};
