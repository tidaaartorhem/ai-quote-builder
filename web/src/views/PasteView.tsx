import { useMemo, useState } from "react";
import {
  bestMatch,
  buildIndex,
  draftQuote,
  fmtMoney,
  matchHealth,
  parseLine,
  priceLines,
} from "../rules";
import type { PricebookEntry } from "../types";
import { MatchBar, TierBadge } from "./shared";

const TIERS = ["Retail", "Trade", "Preferred"];

/** Paste-a-request: the same rules run in the browser, no server, no LLM. */
export default function PasteView({ pricebook }: { pricebook: PricebookEntry[] }) {
  const [text, setText] = useState(
    "Hi team, here's what we need for the Elmwood job:\n3x WHITE HANGING HEART T-LIGHT HOLDER\n12 RED RETROSPOT MUG\na couple of blue bunting\n2 hours on-site labor\nThanks - Dave",
  );
  const [tier, setTier] = useState("Trade");

  const result = useMemo(() => {
    const index = buildIndex(pricebook);
    const lines = text
      .split("\n")
      .map((raw, i) => ({ raw, n: i + 1, ...parseLine(raw) }))
      .filter((l) => !l.skip)
      .map((l) => ({ ...l, match: bestMatch(l.item, index) }));
    const money = priceLines(lines, tier);
    const priced = lines.map((l) => ({
      ...l,
      unit_cents:
        l.match.tier === "AUTO" || l.match.tier === "REVIEW" ? l.match.unit_cents : null,
      line_total_cents:
        l.match.tier === "AUTO" || l.match.tier === "REVIEW"
          ? Math.trunc(l.qty * l.match.unit_cents)
          : null,
    }));
    const health = matchHealth(lines);
    const needsReview = lines.some((l) => l.match.tier !== "AUTO");
    const draft = draftQuote({
      id: "DRAFT",
      customer: "Paste-a-request",
      tier,
      created: "2026-10-30",
      valid_until: "2026-11-29",
      lines: priced,
      ...money,
      match_health: health,
      needs_review: needsReview,
    });
    return { lines: priced, money, health, needsReview, draft };
  }, [text, tier, pricebook]);

  return (
    <div className="card">
      <h2>Paste a request — the same rules, in your browser</h2>
      <p className="muted small">
        The TypeScript mirror of the Python pipeline, matched live against
        the {pricebook.length.toLocaleString()}-SKU price book. Paste
        site-visit notes or a parts list; parse, match, price and draft
        update live.
      </p>
      <label className="block-label">Request text
        <textarea className="input textarea" rows={7} value={text}
          onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="paste-form">
        <label>Customer tier
          <select className="input" value={tier} onChange={(e) => setTier(e.target.value)}>
            {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
      </div>
      <h3>Lines</h3>
      <table className="table">
        <thead>
          <tr><th>Qty</th><th>Item</th><th>Match</th><th>Score</th><th>Unit</th><th>Total</th></tr>
        </thead>
        <tbody>
          {result.lines.map((l) => (
            <tr key={l.n}>
              <td className="mono">{String(l.qty)}</td>
              <td>{l.item}</td>
              <td>
                <TierBadge tier={l.match.tier} />
                <div className="small muted">{l.match.stock_code} · {l.match.description}</div>
              </td>
              <td><MatchBar value={l.match.score} /></td>
              <td className="mono">{l.unit_cents !== null ? fmtMoney(l.unit_cents) : "—"}</td>
              <td className="mono">{l.line_total_cents !== null ? fmtMoney(l.line_total_cents) : "UNPRICED"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        Subtotal <b className="mono">{fmtMoney(result.money.subtotal_cents)}</b> ·
        Discount ({tier}, {result.money.discount_rate}){" "}
        <b className="mono">-{fmtMoney(result.money.discount_cents)}</b> ·
        HST <b className="mono">{fmtMoney(result.money.hst_cents)}</b> ·
        Total <b className="mono">{fmtMoney(result.money.total_cents)}</b> ·
        Match health <b className="mono">{result.health.toFixed(1)}%</b>
        {result.needsReview && " · needs review"}
      </p>
      <div className="draft">
        <div className="small muted">
          Draft quote · <b className="gate">pending human approval</b> · never auto-sent
        </div>
        <pre className="small draft-body" style={{ whiteSpace: "pre-wrap" }}>{result.draft}</pre>
      </div>
      <p className="muted small">
        Match score = keyword token recall × 55 + exact-phrase substring 25 +
        bigram Jaccard × 20. Tiers: ≥75 auto-priced, 50–75 review,
        &lt;50 manual. Discounts: Retail 0% · Trade 12% · Preferred 20%.
        HST 13% on the discounted subtotal. All money in integer cents.
      </p>
    </div>
  );
}
