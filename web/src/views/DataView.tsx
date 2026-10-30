import { fmtMoney, type QuoteDeskData } from "../data";

/** Data honesty: what is real, what is seeded, and the disclosed formulas. */
export default function DataView({ data }: { data: QuoteDeskData }) {
  const pb = data.summary.pricebook;
  return (
    <div>
      <div className="card">
        <h2>What is real, what is seeded</h2>
        <p>
          <b>Real.</b> The price book — {pb.skus.toLocaleString()} SKUs,
          {pb.transactions.toLocaleString()} transactions, median unit price{" "}
          <b className="mono">{fmtMoney(pb.median_unit_cents)}</b> — is measured
          from {pb.rows_read.toLocaleString()} rows of the UCI Online Retail
          corpus (Chen, Clément, Das; CC BY 4.0): cancelled invoices excluded,
          quantity and unit price positive, grouped by stock code and
          description, median price kept for SKUs with 5+ transactions.
        </p>
        <p>
          <b>2010–11 vintage.</b> The corpus records 2010–11 invoices from a
          UK online retailer. These are real historical sell prices, not
          current distributor prices — the quotes are priced honestly on old
          data, disclosed here and everywhere the numbers appear.
        </p>
        <p>
          <b>Seeded.</b> {data.summary.seeded} Deterministic
          (random.Random(20261030)), reproducible, and never presented as a
          real company's records.
        </p>
      </div>
      <div className="card">
        <h2>The disclosed rules</h2>
        <ul className="small">
          <li><b>Parse:</b> per-line qty forms — <span className="mono">3x …</span>, <span className="mono">12 …</span>, "a couple of" → 2, else 1; blank and header lines skipped.</li>
          <li><b>Match (0–100):</b> keyword token recall × 55 + exact-phrase substring 25 + bigram Jaccard × 20. Tiers: ≥75 AUTO, 50–75 REVIEW (top-3 alternates kept), &lt;50 MANUAL.</li>
          <li><b>Price:</b> unit = SKU median sell price; line total = qty × unit; tier discount off subtotal (Retail 0% / Trade 12% / Preferred 20%); HST 13% on the discounted subtotal. Integer cents, half-up rounding.</li>
          <li><b>Gate:</b> every quote is <span className="mono">pending_human_approval</span>; <span className="mono">sent</span> is always false. Zero LLM calls — no API key needed anywhere.</li>
        </ul>
      </div>
      <div className="card">
        <h2>Replay</h2>
        <p className="small">
          Fixed replay: <b className="mono">{data.summary.replay_date}</b> ·{" "}
          {data.summary.quotes} quotes · {data.summary.needs_review} flagged
          needs-review · line tiers AUTO {data.summary.line_tiers.AUTO} /
          REVIEW {data.summary.line_tiers.REVIEW} /
          MANUAL {data.summary.line_tiers.MANUAL} · median total{" "}
          <b className="mono">{fmtMoney(data.summary.median_total_cents)}</b> ·
          median match health <b className="mono">{data.summary.median_match_health.toFixed(1)}%</b>.
        </p>
        <p className="small muted">
          Workflow: {data.summary.graph} · {data.summary.human_gate}.
        </p>
      </div>
    </div>
  );
}
