import { useState } from "react";
import { fmtMoney, useQuoteDeskData } from "./data";
import BoardView from "./views/BoardView";
import PasteView from "./views/PasteView";
import DataView from "./views/DataView";
import "./styles.css";

const REPO_URL = "https://github.com/tidaaartorhem/ai-quote-builder";
const LIVE_URL = "https://ai-quote-builder.web.app";

type Tab = "board" | "paste" | "data";

const TABS: { id: Tab; label: string }[] = [
  { id: "board", label: "Quote board" },
  { id: "paste", label: "Paste a request" },
  { id: "data", label: "Data honesty" },
];

export default function App() {
  const { data, error } = useQuoteDeskData();
  const [tab, setTab] = useState<Tab>("board");

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1><span className="mark">Qd</span>QuoteDesk</h1>
          <p className="sub">
            The quote desk for contractors and distributors: a LangGraph
            workflow — intake → parse → match → price → assemble → gate —
            that turns site-visit notes and parts lists into priced quotes
            from a real historical price book, behind a hard human gate.
            Nothing is ever sent automatically.
          </p>
          <div className="badges">
            <span className="badge neutral"><a href={REPO_URL} target="_blank" rel="noreferrer">GitHub repo</a></span>
            <span className="badge neutral"><a href={LIVE_URL} target="_blank" rel="noreferrer">Live site</a></span>
          </div>
        </div>
      </header>

      <div className="disclosure">
        <b>What is real, what is seeded.</b> SKU prices are real 2010–11
        sell prices from the UCI Online Retail corpus (CC BY 4.0) —
        disclosed as a 2010–11 vintage, not current prices. Customers,
        request texts and line-item paraphrases are a seeded stand-in for
        a distributor's quote feed — deterministic, disclosed, and never
        presented as a real company's records.
      </div>

      {error && <div className="card error">Failed to load data: {error}</div>}
      {!data && !error && <div className="card">Loading…</div>}

      {data && (
        <>
          <div className="stat-grid">
            <div className="stat"><div className="stat-num">{data.summary.quotes}</div><div className="stat-label">priced quotes</div></div>
            <div className="stat"><div className="stat-num">{data.summary.needs_review}</div><div className="stat-label">flagged needs-review</div></div>
            <div className="stat"><div className="stat-num">{data.summary.line_tiers.AUTO ?? 0}</div><div className="stat-label">auto-priced lines</div></div>
            <div className="stat"><div className="stat-num">{data.summary.pricebook.skus.toLocaleString()}</div><div className="stat-label">price-book SKUs</div></div>
            <div className="stat"><div className="stat-num">{fmtMoney(data.summary.median_total_cents)}</div><div className="stat-label">median quote total</div></div>
          </div>

          <div className="tabs">
            {TABS.map((t) => (
              <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === "board" && <BoardView data={data} />}
          {tab === "paste" && <PasteView pricebook={data.pricebook} />}
          {tab === "data" && <DataView data={data} />}

          <footer className="footer muted small">
            Replay Fri 2026-10-30 · Workflow:
            LangGraph StateGraph intake → parse → match → price → assemble → gate ·
            Deterministic rules, no LLM calls, no automatic sends.
          </footer>
        </>
      )}
    </div>
  );
}
