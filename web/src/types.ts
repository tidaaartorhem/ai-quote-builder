export interface QuoteLine {
  n: number;
  raw: string;
  qty: number;
  item: string;
  match: {
    stock_code: string;
    description: string;
    unit_cents: number;
    score: number;
    tier: string;
    alternates: { stock_code: string; description: string; score: number }[];
  } | null;
  unit_cents: number | null;
  line_total_cents: number | null;
}

export interface QuoteRow {
  id: string;
  customer: string;
  tier: string;
  channel: string;
  request_text: string;
  created: string;
  valid_until: string;
  lines: QuoteLine[];
  subtotal_cents: number;
  discount_rate: string;
  discount_cents: number;
  hst_cents: number;
  total_cents: number;
  match_health: number;
  needs_review: boolean;
  status: string;
  sent: boolean;
  draft: string;
}

export interface PricebookEntry {
  stock_code: string;
  description: string;
  median_price: number;
  unit_cents: number;
  transactions: number;
}

export interface Summary {
  replay_date: string;
  quotes: number;
  needs_review: number;
  line_tiers: Record<string, number>;
  median_total_cents: number;
  median_match_health: number;
  pricebook: {
    skus: number;
    transactions: number;
    median_unit_cents: number;
    rows_read: number;
    source: string;
    vintage: string;
  };
  seeded: string;
  graph: string;
  human_gate: string;
}

export interface TestVectors {
  fixture_catalog: PricebookEntry[];
  parse: {
    name: string;
    line: string;
    expected_skip: boolean;
    expected_qty: number;
    expected_item: string;
  }[];
  match: {
    name: string;
    item: string;
    expected_stock_code: string;
    expected_tier: string;
    expected_score: number;
    expected_alternates?: { stock_code: string; description: string; score: number }[];
  }[];
  math: {
    name: string;
    lines: { qty: number; unit_cents: number }[];
    tier: string;
    expected: {
      subtotal_cents: number;
      discount_rate: string;
      discount_cents: number;
      hst_cents: number;
      total_cents: number;
    };
  }[];
  drafts: {
    name: string;
    quote: {
      id: string;
      customer: string;
      tier: string;
      created: string;
      valid_until: string;
      lines: {
        qty: number;
        item: string;
        match: { tier: string; unit_cents: number; score: number } | null;
        unit_cents: number | null;
        line_total_cents: number | null;
      }[];
      subtotal_cents: number;
      discount_rate: string;
      discount_cents: number;
      hst_cents: number;
      total_cents: number;
      match_health: number;
      needs_review: boolean;
    };
    expected_draft: string;
  }[];
}
