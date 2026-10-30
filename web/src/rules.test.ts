import { describe, expect, it } from "vitest";
import {
  bestMatch,
  buildIndex,
  draftQuote,
  matchTier,
  parseLine,
  priceLines,
} from "./rules";
import type { TestVectors } from "./types";
import vectors from "../../data/test-vectors.json";

const V = vectors as TestVectors;

describe("shared contract (data/test-vectors.json)", () => {
  it.each(V.parse.map((v) => [v.name, v]))("parse: %s", (_name, v) => {
    const p = parseLine(v.line);
    expect(p.skip).toBe(v.expected_skip);
    if (!p.skip) {
      expect(p.qty).toBe(v.expected_qty);
      expect(p.item).toBe(v.expected_item);
    }
  });

  it.each(V.match.map((v) => [v.name, v]))("match: %s", (_name, v) => {
    const index = buildIndex(V.fixture_catalog);
    const m = bestMatch(v.item, index);
    expect(m.stock_code).toBe(v.expected_stock_code);
    expect(m.tier).toBe(v.expected_tier);
    expect(m.score).toBe(v.expected_score);
    if (v.expected_tier === "REVIEW") {
      expect(m.alternates).toEqual(v.expected_alternates);
    }
  });

  it.each(V.math.map((v) => [v.name, v]))("math: %s", (_name, v) => {
    const got = priceLines(
      v.lines.map((l) => ({
        qty: l.qty,
        match: { tier: "AUTO", unit_cents: l.unit_cents },
      })),
      v.tier,
    );
    expect(got).toMatchObject(v.expected);
  });

  it.each(V.drafts.map((v) => [v.name, v]))("draft: %s", (_name, v) => {
    expect(draftQuote(v.quote as never)).toBe(v.expected_draft);
  });

  it("match tier boundaries", () => {
    expect(matchTier(100)).toBe("AUTO");
    expect(matchTier(75)).toBe("AUTO");
    expect(matchTier(74.99)).toBe("REVIEW");
    expect(matchTier(50)).toBe("REVIEW");
    expect(matchTier(49.99)).toBe("MANUAL");
    expect(matchTier(0)).toBe("MANUAL");
  });

  it("manual lines stay unpriced", () => {
    const got = priceLines(
      [
        { qty: 1, match: { tier: "AUTO", unit_cents: 200 } },
        { qty: 2, match: { tier: "MANUAL", unit_cents: 250 } },
      ],
      "Retail",
    );
    expect(got.subtotal_cents).toBe(200);
    expect(got.total_cents).toBe(226);
  });
});
