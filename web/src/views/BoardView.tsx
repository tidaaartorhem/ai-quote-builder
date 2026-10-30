import { useState } from "react";
import { fmtMoney, type QuoteDeskData } from "../data";
import type { QuoteRow } from "../types";
import { MatchBar, ReviewFlag, TierBadge } from "./shared";

function QuoteCard({ quote, onOpen }: { quote: QuoteRow; onOpen: () => void }) {
  return (
    <div className="card lead-card">
      <div className="lead-head">
        <div>
          <b className="mono">{quote.id}</b>
          <span className="muted small"> · {quote.customer} · {quote.tier} tier · {quote.channel}</span>
        </div>
        {quote.needs_review && <ReviewFlag />}
      </div>
      <div className="lead-meta small muted">
        {quote.lines.length} lines · match health {quote.match_health.toFixed(1)}% AUTO ·
        total <b>{fmtMoney(quote.total_cents)}</b>
      </div>
      <p className="small">
        {quote.lines.slice(0, 3).map((l) => (
          <span key={l.n} style={{ marginRight: 8 }}>
            <TierBadge tier={l.match?.tier ?? "MANUAL"} />
          </span>
        ))}
        {quote.lines.length > 3 && <span className="muted">+{quote.lines.length - 3} more</span>}
      </p>
      <button className="btn" onClick={onOpen}>Open quote</button>
    </div>
  );
}

function QuoteDetail({ quote, onBack }: { quote: QuoteRow; onBack: () => void }) {
  const [approved, setApproved] = useState(false);
  return (
    <div>
      <button className="btn" onClick={onBack}>← Back to board</button>
      <div className="card">
        <div className="lead-head">
          <div>
            <h2 className="mono" style={{ margin: 0 }}>{quote.id}</h2>
            <p className="muted small" style={{ margin: "4px 0" }}>
              {quote.customer} · {quote.tier} tier ({quote.discount_rate} discount) ·
              {quote.channel} · valid until {quote.valid_until}
            </p>
          </div>
          {quote.needs_review && <ReviewFlag />}
        </div>
        <h3>Request</h3>
        <pre className="small msg" style={{ whiteSpace: "pre-wrap" }}>{quote.request_text}</pre>
        <h3>Lines</h3>
        <table className="table">
          <thead>
            <tr><th>Qty</th><th>Item</th><th>Match</th><th>Score</th><th>Unit</th><th>Total</th></tr>
          </thead>
          <tbody>
            {quote.lines.map((l) => (
              <tr key={l.n}>
                <td className="mono">{String(l.qty)}</td>
                <td>{l.item}</td>
                <td>
                  <TierBadge tier={l.match?.tier ?? "MANUAL"} />
                  <div className="small muted">{l.match ? `${l.match.stock_code} · ${l.match.description}` : "no price-book match"}</div>
                  {l.match?.tier === "REVIEW" && l.match.alternates.length > 0 && (
                    <details className="small">
                      <summary>alternates</summary>
                      <ul>
                        {l.match.alternates.map((a) => (
                          <li key={a.stock_code} className="mono">
                            {a.stock_code} · {a.description} · {a.score.toFixed(1)}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </td>
                <td>{l.match ? <MatchBar value={l.match.score} /> : "—"}</td>
                <td className="mono">{l.unit_cents !== null ? fmtMoney(l.unit_cents) : "—"}</td>
                <td className="mono">{l.line_total_cents !== null ? fmtMoney(l.line_total_cents) : "UNPRICED"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3>Pricing</h3>
        <table className="table narrow">
          <tbody>
            <tr><td>Subtotal</td><td className="mono">{fmtMoney(quote.subtotal_cents)}</td></tr>
            <tr><td>Discount ({quote.tier}, {quote.discount_rate})</td><td className="mono">-{fmtMoney(quote.discount_cents)}</td></tr>
            <tr><td>HST (13%)</td><td className="mono">{fmtMoney(quote.hst_cents)}</td></tr>
            <tr><td><b>Total</b></td><td className="mono"><b>{fmtMoney(quote.total_cents)}</b></td></tr>
          </tbody>
        </table>
        <div className="draft">
          <div className="small muted">
            Draft quote · <b className="gate">pending human approval</b> · never auto-sent
          </div>
          <pre className="small draft-body" style={{ whiteSpace: "pre-wrap" }}>{quote.draft}</pre>
          <button
            className={approved ? "btn approved" : "btn"}
            onClick={() => setApproved(!approved)}
            disabled={approved}
          >
            {approved ? "Approved (in your head — nothing sent)" : "Approve quote"}
          </button>
          <span className="muted small"> Approval is a UI affordance only; this page cannot send anything.</span>
        </div>
      </div>
    </div>
  );
}

/** Quote board: quotes ranked by total, needs-review flags, drill-down detail. */
export default function BoardView({ data }: { data: QuoteDeskData }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = openId ? data.quotes.find((q) => q.id === openId) ?? null : null;
  if (open) return <QuoteDetail quote={open} onBack={() => setOpenId(null)} />;
  return (
    <div>
      <p className="muted small">
        Ranked by quote total, biggest first. Every quote sits behind a hard
        human gate — nothing is sent automatically.
      </p>
      {data.quotes.map((q) => (
        <QuoteCard key={q.id} quote={q} onOpen={() => setOpenId(q.id)} />
      ))}
    </div>
  );
}
