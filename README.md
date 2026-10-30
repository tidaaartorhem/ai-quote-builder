# QuoteDesk — the quote desk for contractors and distributors

**Live:** https://ai-quote-builder-app.web.app · **Repo:** https://github.com/tidaaartorhem/ai-quote-builder

## The problem

Contractors and distributors build quotes in spreadsheets from
site-visit notes or emailed parts lists. Pricing comes from memory or
a stale price sheet, margin math is inconsistent across the team, and
the quote goes out days late. Slow quotes lose jobs — the customer who
asked three suppliers buys from the one who answered first.

The failure is not effort, it is plumbing. Somebody has to read the
notes, type each line into a sheet, look up a price for every item,
apply the right customer discount, add tax, and format the whole thing
— for every request, by hand, while the next request is already
waiting.

## What this is

QuoteDesk is the desk that sits between the request and the quote. A
LangGraph workflow —
`intake → parse → match → price → assemble → gate → queue` —
turns pasted site-visit notes or parts lists into priced, formatted
quotes. It never sends anything.

- **Parse:** per-line quantity forms (`3x …`, `12 …`, "a couple of" →
  2, else 1); blank and header lines skipped.
- **Match:** every line is fuzzy-matched against a distributor price
  book of real historical sell prices — score 0–100, fully disclosed
  (keyword token recall × 55 + exact-phrase substring 25 + bigram
  Jaccard × 20). ≥75 auto-prices, 50–75 keeps the top-3 alternates for
  review, <50 is manual (labor, delivery fees, and anything with no
  catalog match are unpriced, never guessed).
- **Price:** unit = the SKU's median historical sell price; customer
  tier discounts (Retail 0% / Trade 12% / Preferred 20%) off subtotal;
  Ontario HST 13% on the discounted subtotal. Integer cents, half-up
  rounding — identical in Python and the browser.
- **Assemble:** one formatted quote per request — line items with match
  tiers, subtotal, discount, HST, total, match health, valid-until date.
- **Gate:** every quote is `pending_human_approval`; `sent` is always
  false. Zero LLM calls — no API key needed anywhere.

## Headline numbers (fixed replay: Fri 2026-10-30)

- 140 quote requests priced against a **3,610-SKU price book** built
  from 528,936 real transactions.
- Line tiers: **AUTO 209** · **REVIEW 58** · **MANUAL 106** —
  103 of 140 quotes flagged needs-review (any line not AUTO).
- Median quote total **$11.22**; median match health **50.0%** AUTO.
- Biggest quote: QD-2026-1097, **$1,421.80** for Scarborough Storage.

## What is real and what is seeded

**Real.** The price book is measured from the UCI Online Retail corpus
— 541,909 invoice rows (Chen, Clément, Das; CC BY 4.0), bundled in
`data/raw/Online Retail.xlsx`. Cancelled invoices excluded, quantity
and unit price positive, grouped by stock code + description; the
median unit price of SKUs with 5+ transactions becomes the sell price.
The build script refuses to run on fewer than 1,000 SKUs.

**2010–11 vintage.** The corpus records 2010–11 invoices, so these are
real historical sell prices, not current distributor prices. The
vintage is disclosed here, in `data/README-data.md`, and in the UI's
Data honesty tab.

**Seeded.** The corpus records retail invoices, not quote requests, so
customer names, tiers, channels, request texts, and the ~200 catalog
paraphrases are seeded as a stand-in for a distributor's quote feed.
All seeded values come from `random.Random(20261030)` — re-running the
script reproduces byte-identical output. Nothing seeded is presented
as a real company's record.

## Running it

```bash
python3 scripts/build_quotedesk.py        # rebuilds data/outputs/*.json + web/public/data/*.json
python3 -m pytest tests/ -q                # 15 passed, 1 skipped (langgraph not installed → nodes are the work)
cd web && npm install && npm run build     # rebuilds the payloads, then Vite
cd web && npm test                         # vitest: contract parity + boundaries
```

`scripts/build_quotedesk.py` runs the compiled LangGraph StateGraph
when `langgraph` is installed, otherwise the same node functions in
order — identical output either way, so the pipeline never stalls.

`data/test-vectors.json` is the shared contract: the Python engine and
the in-browser TypeScript mirror (`web/src/rules.ts`) must agree on
every vector exactly (parse, match, quote math, and character-exact
quote drafts). The "Paste a request" tab runs that mirror against the
full price book.

## Deploy

Firebase Hosting (`ai-quote-builder-app.web.app`); data endpoints at
`data/pricebook.json`, `data/quotes.json`, `data/summary.json`,
`data/test-vectors.json`, `data/stamp.json`.

## Files

- `src/quotedesk/rules.py` — disclosed parse/match/price/assemble rules
- `src/quotedesk/nodes.py`, `graph.py` — the workflow (nodes are the work)
- `scripts/build_quotedesk.py` — corpus ingest, price book, seeded inbox, pipeline runner
- `web/` — React + TypeScript UI (light mode), TS mirror of the rules
