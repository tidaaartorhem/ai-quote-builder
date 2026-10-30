"""QuoteDesk tests: parse determinism, match tier boundaries, quote math,
graph-vs-nodes parity, test-vector agreement. Run with:
python3 -m pytest tests/ -q (from repo root)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

from quotedesk import nodes, rules
from quotedesk.nodes import run_nodes
from quotedesk.rules import (assemble_quote, best_match, build_index,
                             draft_quote, match_score, match_tier, parse_line,
                             price_lines)


def test_parse_qty_forms():
    assert parse_line("3x WHITE MUG") == {"skip": False, "qty": 3,
                                          "item": "WHITE MUG"}
    assert parse_line("12 RED RETROSPOT MUG")["qty"] == 12
    assert parse_line("2 × RED LANTERN")["qty"] == 2
    assert parse_line("3.5x BLUE BUNTING")["qty"] == 3.5


def test_parse_couple_and_default_qty():
    p = parse_line("a couple of white hanging heart t-light holders")
    assert (p["qty"], p["item"]) == (2, "white hanging heart t-light holders")
    p = parse_line("WHITE HANGING HEART T-LIGHT HOLDER")
    assert (p["qty"], p["item"]) == (1, "WHITE HANGING HEART T-LIGHT HOLDER")


def test_parse_skips_headers():
    assert parse_line("Hi team, here's what we need:")["skip"] is True
    assert parse_line("Site visit notes - Maple St reno:")["skip"] is True
    assert parse_line("Thanks - Dave")["skip"] is True
    assert parse_line("   ")["skip"] is True


def test_parse_labor_line_kept():
    p = parse_line("2 hours on-site labor")
    assert p["skip"] is False
    assert (p["qty"], p["item"]) == (2, "hours on-site labor")


def test_match_tier_boundaries():
    assert match_tier(100.0) == "AUTO"
    assert match_tier(75.0) == "AUTO"
    assert match_tier(74.99) == "REVIEW"
    assert match_tier(50.0) == "REVIEW"
    assert match_tier(49.99) == "MANUAL"
    assert match_tier(0.0) == "MANUAL"


def test_match_verbatim_is_auto():
    idx = build_index([{"stock_code": "A", "description": "RED RETROSPOT MUG",
                        "unit_cents": 195}])
    m = best_match("RED RETROSPOT MUG", idx)
    assert m["tier"] == "AUTO" and m["score"] == 100.0
    assert m["stock_code"] == "A"


def test_match_manual_tie_break_deterministic():
    idx = build_index([
        {"stock_code": "B", "description": "RED RETROSPOT MUG",
         "unit_cents": 1},
        {"stock_code": "A", "description": "BLUE BUNTING", "unit_cents": 1},
    ])
    once = best_match("gift wrap and ribbon", idx)
    twice = best_match("gift wrap and ribbon", idx)
    assert once == twice
    assert once["tier"] == "MANUAL" and once["score"] == 0.0
    assert once["stock_code"] == "A"  # lowest stock_code wins ties


def test_quote_math_trade():
    lines = [{"qty": 3, "item": "x",
              "match": {"tier": "AUTO", "unit_cents": 250}}]
    p = price_lines(lines, "Trade")
    assert p["subtotal_cents"] == 750
    assert p["discount_rate"] == "12%" and p["discount_cents"] == 90
    assert p["hst_cents"] == 86 and p["total_cents"] == 746


def test_quote_math_preferred_rounding():
    # 948 subtotal, 20% -> 189.6 rounds half-up to 190; hst 98.54 -> 99.
    lines = [{"qty": 2, "item": "x",
              "match": {"tier": "AUTO", "unit_cents": 199}},
             {"qty": 1, "item": "x",
              "match": {"tier": "AUTO", "unit_cents": 550}}]
    p = price_lines(lines, "Preferred")
    assert (p["subtotal_cents"], p["discount_cents"], p["hst_cents"],
            p["total_cents"]) == (948, 190, 99, 857)


def test_quote_math_manual_lines_unpriced():
    lines = [{"qty": 1, "item": "x",
              "match": {"tier": "AUTO", "unit_cents": 200}},
             {"qty": 2, "item": "hours on-site labor",
              "match": {"tier": "MANUAL", "unit_cents": 250}}]
    p = price_lines(lines, "Retail")
    assert p["lines"][1]["unit_cents"] is None
    assert p["lines"][1]["line_total_cents"] is None
    assert p["subtotal_cents"] == 200 and p["total_cents"] == 226


def test_nodes_parity_and_gate():
    raw = [{
        "request_id": "req-001", "customer": "Test Customer",
        "tier": "Trade", "channel": "parts list",
        "request_text": "2x WHITE MUG\nThanks - Dave",
    }]
    book = [{"stock_code": "X", "description": "WHITE MUG",
             "median_price": 2.0, "unit_cents": 200, "transactions": 9}]
    once = run_nodes({"requests": raw, "pricebook": book})["queue"]
    twice = run_nodes({"requests": raw, "pricebook": book})["queue"]
    assert once == twice
    q = once[0]
    assert q["id"] == "QD-2026-1001"
    assert len(q["lines"]) == 1  # the thanks line was skipped
    assert q["lines"][0]["match"]["tier"] == "AUTO"
    assert q["total_cents"] == 398
    assert q["status"] == "pending_human_approval"
    assert q["sent"] is False
    assert "PENDING HUMAN APPROVAL" in q["draft"]
    try:
        from quotedesk.graph import run_graph
        assert run_graph(raw, book) == once
    except ImportError:
        pytest.skip("langgraph not installed; nodes are the work")


def _vectors():
    return json.loads((ROOT / "data" / "test-vectors.json").read_text())


def test_vectors_parse_agreement():
    for v in _vectors()["parse"]:
        p = parse_line(v["line"])
        assert p["skip"] == v["expected_skip"], v["name"]
        if not p["skip"]:
            assert p["qty"] == v["expected_qty"], v["name"]
            assert p["item"] == v["expected_item"], v["name"]


def test_vectors_match_agreement():
    vec = _vectors()
    index = build_index(vec["fixture_catalog"])
    assert len(vec["match"]) >= 10
    for v in vec["match"]:
        m = best_match(v["item"], index)
        assert m["stock_code"] == v["expected_stock_code"], v["name"]
        assert m["tier"] == v["expected_tier"], v["name"]
        assert m["score"] == v["expected_score"], v["name"]
        if v["expected_tier"] == "REVIEW":
            assert m["alternates"] == v["expected_alternates"], v["name"]
            assert len(m["alternates"]) == 3


def test_vectors_math_and_draft_agreement():
    vec = _vectors()
    assert len(vec["math"]) >= 3
    for v in vec["math"]:
        lines = [{"qty": ln["qty"], "item": "x",
                  "match": {"tier": "AUTO",
                            "unit_cents": ln["unit_cents"]}}
                 for ln in v["lines"]]
        got = price_lines(lines, v["tier"])
        for k, want in v["expected"].items():
            assert got[k] == want, (v["name"], k)
    assert len(vec["drafts"]) >= 2
    for v in vec["drafts"]:
        assert draft_quote(v["quote"]) == v["expected_draft"], v["name"]


def test_pricebook_bundled_and_real_shaped():
    book = json.loads(
        (ROOT / "data" / "outputs" / "pricebook.json").read_text())
    assert len(book) >= 1000, f"price book looks truncated: {len(book)}"
    for e in book[:50]:
        assert e["transactions"] >= 5
        assert e["unit_cents"] > 0
    xlsx = ROOT / "data" / "raw" / "Online Retail.xlsx"
    assert xlsx.exists() and xlsx.stat().st_size > 10_000_000


def test_quotes_all_gated():
    quotes = json.loads(
        (ROOT / "data" / "outputs" / "quotes.json").read_text())
    assert 130 <= len(quotes) <= 150
    for q in quotes:
        assert q["status"] == "pending_human_approval"
        assert q["sent"] is False
        assert q["created"] == "2026-10-30"
        assert q["valid_until"] == "2026-11-29"
