# Data notes — what is real and what is seeded

## Real
- `data/raw/Online Retail.xlsx` — the UCI Online Retail dataset (Chen,
  Clément, Das; CC BY 4.0), bundled verbatim. It records 2010-11
  invoices from a UK-based online retailer.
- The price book (`data/outputs/pricebook.json`) is measured from the
  full corpus at build time: cancelled invoices excluded (InvoiceNo
  starting with 'C'), Quantity > 0, UnitPrice > 0; grouped by
  StockCode + Description; median UnitPrice becomes the SKU's sell
  price; SKUs with fewer than 5 transactions are dropped.
  3,610 SKUs, 528,936 transactions, median unit price $2.08, from 541,909 invoice rows.
- **Prices are a 2010-11 vintage.** They are real historical sell
  prices, not current distributor prices — disclosed here, in the
  README, and in the UI.

## Seeded (stands in for a distributor's quote-request feed)
- Customer names, tiers (Retail/Trade/Preferred), channels (parts
  list / site-visit note), request texts, and line-item paraphrases of
  ~200 real catalog descriptions — all from random.Random(20261030),
  so `python3 scripts/build_quotedesk.py` reproduces byte-identical
  output. The corpus records retail invoices, not quote requests;
  the mapping is disclosed, not hidden. Nothing seeded is presented
  as a real company's record.

## Generated
- `data/outputs/quotes.json` — the 140-quote priced work queue
  (fixed replay: Fri 2026-10-30).
- `data/outputs/summary.json` — headline counts and price-book stats.
- `data/test-vectors.json` — hand-checked shared contract asserted by
  both pytest (`tests/test_quotedesk.py`) and vitest
  (`web/src/rules.test.ts`): Python engine and TypeScript mirror must
  agree on every vector exactly.
