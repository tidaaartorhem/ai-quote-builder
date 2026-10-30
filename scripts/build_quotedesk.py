#!/usr/bin/env python3
"""Build QuoteDesk payloads.

Reads the real UCI Online Retail corpus (Chen, Clement, Das; CC BY 4.0)
bundled at data/raw/Online Retail.xlsx and derives the distributor
price book: for every SKU (StockCode + Description) with >= 5
non-cancelled, positive-quantity, positive-price transactions, the
median historical UnitPrice becomes the SKU's sell price.

Then it seeds a 140-request quote inbox (parts lists and site-visit
notes with line items paraphrased from ~200 real catalog descriptions)
and runs the LangGraph workflow
(intake -> parse -> match -> price -> assemble -> gate -> queue) over a
fixed replay: Fri 2026-10-30.

What is real and what is seeded (also stated in README + UI):
- REAL: the price book — SKU descriptions, median sell prices and
  transaction counts are measured from the 2010-11 Online Retail
  invoices. Prices are a 2010-11 vintage and are disclosed as such.
- SEEDED (standing in for a distributor's quote-request feed, which the
  public corpus does not contain): customer names, tiers, channels,
  request texts and line-item paraphrases. All seeded values come from
  random.Random(20261030), so re-running this script reproduces
  byte-identical output. Nothing seeded is presented as a real
  company's record.

Outputs: data/outputs/{pricebook,quotes,summary}.json,
data/test-vectors.json, copies under web/public/data/, and
data/README-data.md.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quotedesk import rules
from quotedesk.nodes import run_nodes
from quotedesk.rules import (assemble_quote, best_match, build_index,
                             draft_quote, match_tier, median_to_cents,
                             parse_line, price_lines)

SEED = 20261030
N_QUOTES = 140
RAW_XLSX = ROOT / "data" / "raw" / "Online Retail.xlsx"

CUSTOMERS = [
    "Bright Sparks Electrical", "Maple & Main Renovations",
    "Harbourview Contracting", "Northline Plumbing", "GTA Build Supply",
    "Elmwood Interiors", "Parkdale Property Group", "Lakeside Landscapes",
    "Danforth Design Co.", "Crosstown HVAC", "Union Supply Co.",
    "Front Street Builders", "Rosedale Restorations", "Junction Workshop",
    "Liberty Village Lofts", "Distillery District Events",
    "Queen West Retail", "Bloor Annex Realty", "Scarborough Storage",
    "Etobicoke Electric", "Vaughan Drywall", "Markham Millwork",
    "Mississauga Mechanical", "Toronto Tile & Stone",
]
FIRSTS = ["Dave", "Priya", "Marcus", "Sofia", "Daniel", "Aisha", "Liam",
          "Maya", "Ethan", "Nora", "Ravi", "Elena", "Omar", "Tara"]
JOBS = ["Maple St reno", "Elmwood kitchen", "Parkdale duplex",
        "Harbourfront office", "Danforth cafe", "Crosstown warehouse",
        "Lakeshore condo", "Unionville shop"]
INTROS = [
    "Site visit notes - {job}:",
    "Hi team, here's what we need for the {job} job:",
    "Walked the {job} site this morning, need pricing on:",
    "Good morning - please price the following for {job}:",
]
OUTROS = [
    "Thanks - {first}",
    "Let me know the total. - {first}",
    "Need this by Friday. - {first}",
    "Cheers, {first}",
]
# Lines with no catalog match at all -> MANUAL tier, unit None.
NO_MATCH_LINES = [
    "2 hours on-site labor",
    "1 same-day delivery fee",
    "1 weekend callout charge",
    "3 hours installation labor",
    "1 packaging and handling fee",
    "40 km mileage charge",
    "1 rush processing fee",
    "1 after-hours service call",
]

# Curated synonym swaps for medium paraphrases (longest key first).
SYNONYMS = {
    "CUSHION COVER": "pillow cover", "HOT WATER BOTTLE": "warming bottle",
    "WATER BOTTLE": "drink bottle", "TOOTHBRUSH HOLDER": "brush cup",
    "CANDLE HOLDER": "votive holder", "PICTURE FRAME": "photo frame",
    "LUNCH BOX": "lunch tote", "LUNCH BAG": "lunch tote",
    "PENCIL CASE": "pen case", "WALL ART": "wall print",
    "DRAFT EXCLUDER": "door snake", "TEA TOWEL": "kitchen towel",
    "T-LIGHTS": "tealights", "T-LIGHT": "tealight",
    "BAUBLES": "ornaments", "BAUBLE": "ornament",
    "BUNTING": "garland", "LANTERN": "lamp", "LANTERNS": "lamps",
    "DOORMAT": "door mat", "DOORSTOP": "door stop",
    "BACKPACK": "rucksack", "KEYRING": "keychain",
    "CHRISTMAS": "xmas", "BIRDHOUSE": "bird house",
    "NOTEBOOK": "notepad", "NOTEBOOKS": "notepads",
    "GIFT BAG": "present bag", "WRAPPING": "gift wrap",
    "MUG": "cup", "MUGS": "cups", "PLATE": "dish", "PLATES": "dishes",
    "JUMBO": "large", "PLANTER": "plant pot",
    "PHOTO ALBUM": "picture album", "CALENDAR": "planner",
    "DIARY": "journal", "POSTER": "print",
    "WATERING CAN": "watering jug", "TOOL BOX": "toolbox",
    "PINK": "rose", "RIBBON": "trim", "CARD": "greeting card",
    "NAPKINS": "serviettes", "CUTLERY": "flatware",
    "COASTERS": "drink coasters", "PLACEMATS": "table mats",
    "OVEN GLOVE": "oven mitt", "APRON": "smock",
    "MILK JUG": "creamer", "SUGAR BOWL": "sugar dish",
    "TEAPOT": "tea pot", "EGG CUP": "egg holder",
    "FLASK": "thermos", "BIN": "trash can", "RUG": "mat",
    "THROW": "blanket", "DUVET": "comforter",
    "PILLOWCASE": "pillow slip", "SOAP DISH": "soap tray",
    "BATH MAT": "tub mat", "LAUNDRY BASKET": "wash hamper",
    "MIRROR": "looking glass", "CLOCK": "timepiece",
    "CURTAIN": "drape", "JIGSAW": "puzzle",
    "BALLOON": "party balloon", "CONFETTI": "sprinkles",
    "DOLLS HOUSE": "dollhouse", "TEDDY": "plush bear",
}
_SYN_KEYS = sorted(SYNONYMS, key=len, reverse=True)
_GENERIC = ["decorations", "supplies", "items", "goods", "stock", "assorted"]


def load_pricebook(xlsx: Path) -> tuple[list[dict], int]:
    import pandas as pd

    df = pd.read_excel(xlsx, engine="openpyxl")
    n_rows = len(df)
    df = df.dropna(subset=["Description"])
    df["InvoiceNo"] = df["InvoiceNo"].astype(str)
    df["StockCode"] = df["StockCode"].astype(str).str.strip()
    df["Description"] = df["Description"].astype(str).str.strip()
    mask = (~df["InvoiceNo"].str.startswith("C")
            & (df["Quantity"] > 0) & (df["UnitPrice"] > 0))
    d = df.loc[mask]
    g = (d.groupby(["StockCode", "Description"], as_index=False)
           .agg(median_price=("UnitPrice", "median"),
                transactions=("UnitPrice", "size")))
    g = g[g["transactions"] >= 5].sort_values(
        ["StockCode", "Description"]).reset_index(drop=True)
    book = [{
        "stock_code": r.StockCode,
        "description": r.Description,
        "median_price": round(float(r.median_price), 4),
        "unit_cents": median_to_cents(float(r.median_price)),
        "transactions": int(r.transactions),
    } for r in g.itertuples()]
    if len(book) < 1000:
        raise SystemExit(f"quotedesk: price book too small ({len(book)} "
                         f"SKUs) — refusing to run on partial data")
    return book, n_rows


def _apply_synonyms(desc: str, rng: random.Random) -> str:
    out, n = desc, 0
    for key in _SYN_KEYS:
        if key in out and rng.random() < 0.6:
            out = out.replace(key, SYNONYMS[key])
            n += 1
            if n >= 2:
                break
    return out


def paraphrase(desc: str, style: str, rng: random.Random) -> str:
    """Hand-designed paraphrase transforms over real catalog text."""
    toks = desc.split()
    if style == "verbatim":
        return desc if rng.random() < 0.5 else desc.lower()
    if style == "light":
        d = desc.lower()
        if rng.random() < 0.5:
            d += " " + rng.choice(["pcs", "units"])
        return d
    if style == "medium":
        d = _apply_synonyms(desc, rng)
        if d == desc and len(toks) > 3:
            # drop one interior token to break the exact phrase
            drop = rng.randrange(1, len(toks) - 1)
            d = " ".join(t for i, t in enumerate(toks) if i != drop)
        return d.lower() if rng.random() < 0.5 else d
    # heavy: 1 real keyword + generic filler -> MANUAL tier
    content = [t for t in toks
               if t.lower() not in rules.STOPWORDS and not t.isdigit()]
    if len(content) < 2:
        return paraphrase(desc, "medium", rng)
    keep = rng.choice(content)
    filler = rng.sample(_GENERIC, 2)
    return " ".join([keep.lower()] + filler)


def _line_text(item: str, qty: int, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.40:
        return f"{qty}x {item}"
    if r < 0.75:
        return f"{qty} {item}"
    if r < 0.85 and qty == 2:
        return f"a couple of {item.lower()}"
    if r < 0.85:
        return f"{qty} × {item}"
    return item


def seed_requests(book: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    sampled = rng.sample(book, min(200, len(book)))
    descs = [s["description"] for s in sampled]
    requests = []
    for i in range(N_QUOTES):
        rid = f"req-{i + 1:03d}"
        customer = CUSTOMERS[rng.randrange(len(CUSTOMERS))]
        r = rng.random()
        tier = "Retail" if r < 0.40 else ("Trade" if r < 0.80 else "Preferred")
        channel = "parts list" if rng.random() < 0.60 else "site-visit note"
        n_lines = rng.choices([1, 2, 3, 4], weights=[15, 40, 30, 15])[0]
        raw_lines = []
        for _ in range(n_lines):
            desc = descs[rng.randrange(len(descs))]
            s = rng.random()
            style = ("verbatim" if s < 0.30 else
                     "light" if s < 0.60 else
                     "medium" if s < 0.85 else "heavy")
            item = paraphrase(desc, style, rng)
            qty = rng.choices([1, 2, 3, 4, 5, 6, 8, 10, 12],
                              weights=[30, 20, 15, 10, 8, 7, 4, 3, 3])[0]
            raw_lines.append(_line_text(item, qty, rng))
        if rng.random() < 0.25:
            raw_lines.append(rng.choice(NO_MATCH_LINES))
        rng.shuffle(raw_lines)
        if channel == "site-visit note":
            first = FIRSTS[rng.randrange(len(FIRSTS))]
            job = JOBS[rng.randrange(len(JOBS))]
            text = "\n".join(
                [rng.choice(INTROS).format(job=job)] + raw_lines +
                [rng.choice(OUTROS).format(first=first)])
        else:
            text = "\n".join(raw_lines)
        requests.append({
            "request_id": rid,
            "customer": customer,
            "tier": tier,
            "channel": channel,
            "request_text": text,
        })
    return requests


def build(xlsx: Path) -> dict:
    book, n_rows = load_pricebook(xlsx)
    raw = seed_requests(book)

    try:
        from quotedesk.graph import run_graph
        queue = run_graph(raw, book)
    except ImportError:
        # langgraph not installed: same nodes, same output, no graph lib.
        queue = run_nodes({"requests": raw, "pricebook": book})["queue"]

    # The desk works its biggest quotes first.
    queue.sort(key=lambda q: (-q["total_cents"], q["id"]))

    tiers = {"AUTO": 0, "REVIEW": 0, "MANUAL": 0}
    for q in queue:
        for ln in q["lines"]:
            m = ln["match"]
            tiers[m["tier"] if m else "MANUAL"] += 1

    def med(xs: list) -> float:
        s = sorted(xs)
        n = len(s)
        return (s[n // 2] + s[-(n // 2) - 1]) / 2 if n else 0.0

    summary = {
        "replay_date": "2026-10-30",
        "quotes": len(queue),
        "needs_review": sum(1 for q in queue if q["needs_review"]),
        "line_tiers": tiers,
        "median_total_cents": int(round(med([q["total_cents"]
                                             for q in queue]))),
        "median_match_health": round(med([q["match_health"]
                                          for q in queue]), 1),
        "pricebook": {
            "skus": len(book),
            "transactions": sum(b["transactions"] for b in book),
            "median_unit_cents": int(round(med([b["unit_cents"]
                                                for b in book]))),
            "rows_read": n_rows,
            "source": "UCI Online Retail (Chen, Clement, Das), CC BY 4.0",
            "vintage": "2010-11 invoices — prices are a 2010-11 vintage",
        },
        "seeded": ("customer names, tiers, channels, request texts and "
                   "line-item paraphrases — random.Random(20261030); the "
                   "corpus records retail invoices, not quote requests"),
        "graph": ("LangGraph StateGraph: intake -> parse -> match -> "
                  "price -> assemble -> gate"),
        "human_gate": "every quote pending_human_approval; nothing is sent",
    }
    return {"pricebook": book, "quotes": queue, "summary": summary}


# ------------------------------------------------------- test vectors

FIXTURE_CATALOG = [
    {"stock_code": "10001",
     "description": "WHITE HANGING HEART T-LIGHT HOLDER", "unit_cents": 250},
    {"stock_code": "10002", "description": "RED RETROSPOT MUG",
     "unit_cents": 195},
    {"stock_code": "10003", "description": "SET OF 6 T-LIGHTS SANTA",
     "unit_cents": 425},
    {"stock_code": "10004", "description": "JUMBO BAG PINK POLKADOT",
     "unit_cents": 195},
    {"stock_code": "10005", "description": "BLUE BUNTING", "unit_cents": 595},
    {"stock_code": "10006",
     "description": "VINTAGE UNION JACK CUSHION COVER", "unit_cents": 495},
    {"stock_code": "10007",
     "description": "WOODEN PICTURE FRAME WHITE FINISH", "unit_cents": 275},
    {"stock_code": "10008", "description": "CERAMIC CAKE STAND",
     "unit_cents": 1295},
    {"stock_code": "10009",
     "description": "DOORMAT UNION JACK GUNS AND ROSES", "unit_cents": 795},
    {"stock_code": "10010",
     "description": "HOT WATER BOTTLE TEA AND SYMPATHY", "unit_cents": 465},
]

PARSE_VECTORS = [
    ("qty-x-form", "3x WHITE HANGING HEART T-LIGHT HOLDER",
     False, 3, "WHITE HANGING HEART T-LIGHT HOLDER"),
    ("qty-n-form", "12 RED RETROSPOT MUG", False, 12, "RED RETROSPOT MUG"),
    ("couple-form", "a couple of white hanging heart t-light holders",
     False, 2, "white hanging heart t-light holders"),
    ("bare-couple-form", "Couple of red mugs", False, 2, "red mugs"),
    ("default-qty", "WHITE HANGING HEART T-LIGHT HOLDER",
     False, 1, "WHITE HANGING HEART T-LIGHT HOLDER"),
    ("multiply-sign", "2 × RED LANTERN", False, 2, "RED LANTERN"),
    ("decimal-qty", "3.5x BLUE BUNTING", False, 3.5, "BLUE BUNTING"),
    ("labor-line", "2 hours on-site labor", False, 2, "hours on-site labor"),
    ("no-space-x", "10xSET OF 6 T-LIGHTS SANTA",
     False, 10, "SET OF 6 T-LIGHTS SANTA"),
    ("skip-greeting", "Hi team, here's what we need for the Elmwood job:",
     True, 0, ""),
    ("skip-thanks", "Thanks - Dave", True, 0, ""),
    ("skip-site-visit", "Site visit notes - Maple St reno:", True, 0, ""),
    ("skip-blank", "   ", True, 0, ""),
    ("skip-please", "Please price the following:", True, 0, ""),
    ("skip-need-by", "Need this by Friday. - Dave", True, 0, ""),
]

MATCH_VECTORS = [
    ("verbatim-auto", "WHITE HANGING HEART T-LIGHT HOLDER", "10001", "AUTO"),
    ("lowercase-auto", "white hanging heart t-light holder", "10001", "AUTO"),
    ("retrospot-auto", "RED RETROSPOT MUG", "10002", "AUTO"),
    ("tealight-paraphrase-manual", "hanging heart tealight holder",
     "10001", "MANUAL"),
    ("dropped-word-review", "white heart t-light holder", "10001", "REVIEW"),
    ("reordered-review", "pink polkadot jumbo bag", "10004", "REVIEW"),
    ("synonym-cup-manual", "red retrospot cups", "10002", "MANUAL"),
    ("synonym-garland-manual", "blue garland", "10005", "MANUAL"),
    ("photo-frame-manual", "photo frame white", "10007", "MANUAL"),
    ("substring-auto", "union jack cushion cover", "10006", "AUTO"),
    ("cake-stand-auto", "cake stand", "10008", "AUTO"),
    ("doormat-review", "union jack doormat", "10009", "REVIEW"),
    ("bottle-review", "tea and sympathy hot water bottle", "10010", "REVIEW"),
    ("santa-manual", "set of 6 santa tealights", "10003", "MANUAL"),
    ("no-match-tie-break", "gift wrap and ribbon", "10001", "MANUAL"),
]

MATH_VECTORS = [
    {"name": "trade-discount-hst",
     "lines": [{"qty": 3, "unit_cents": 250}], "tier": "Trade",
     "expected": {"subtotal_cents": 750, "discount_rate": "12%",
                  "discount_cents": 90, "hst_cents": 86,
                  "total_cents": 746}},
    {"name": "preferred-multi-line",
     "lines": [{"qty": 2, "unit_cents": 199},
               {"qty": 1, "unit_cents": 550}], "tier": "Preferred",
     "expected": {"subtotal_cents": 948, "discount_rate": "20%",
                  "discount_cents": 190, "hst_cents": 99,
                  "total_cents": 857}},
    {"name": "retail-no-discount",
     "lines": [{"qty": 1, "unit_cents": 1000}], "tier": "Retail",
     "expected": {"subtotal_cents": 1000, "discount_rate": "0%",
                  "discount_cents": 0, "hst_cents": 130,
                  "total_cents": 1130}},
]

# Hand-written expected drafts (character-exact contract with TS mirror).
DRAFT_VECTORS = [
    {
        "name": "auto-quote-draft",
        "quote": {
            "id": "QD-2026-1001", "customer": "Test Customer",
            "tier": "Trade", "created": "2026-10-30",
            "valid_until": "2026-11-29",
            "lines": [{
                "n": 1, "raw": "2x WHITE MUG", "qty": 2, "item": "WHITE MUG",
                "match": {"stock_code": "X", "description": "WHITE MUG",
                          "unit_cents": 200, "score": 100.0, "tier": "AUTO",
                          "alternates": []},
                "unit_cents": 200, "line_total_cents": 400,
            }],
            "subtotal_cents": 400, "discount_rate": "12%",
            "discount_cents": 48, "hst_cents": 46, "total_cents": 398,
            "match_health": 100.0, "needs_review": False,
        },
        "expected_draft":
        "QUOTATION QD-2026-1001\n"
        "Date: 2026-10-30 - Valid until: 2026-11-29\n"
        "Customer: Test Customer - Trade tier (12% discount)\n"
        "\n"
        "Lines:\n"
        "  2 x WHITE MUG @ $2.00 = $4.00  [AUTO 100.0]\n"
        "\n"
        "Subtotal: $4.00\n"
        "Discount (Trade, 12%): -$0.48\n"
        "HST (13%): $0.46\n"
        "TOTAL: $3.98\n"
        "\n"
        "Match health: 100.0% of lines AUTO.\n"
        "Status: PENDING HUMAN APPROVAL. Nothing has been sent.",
    },
    {
        "name": "manual-line-draft",
        "quote": {
            "id": "QD-2026-1002", "customer": "Test Customer",
            "tier": "Retail", "created": "2026-10-30",
            "valid_until": "2026-11-29",
            "lines": [
                {
                    "n": 1, "raw": "WHITE MUG", "qty": 1, "item": "WHITE MUG",
                    "match": {"stock_code": "X", "description": "WHITE MUG",
                              "unit_cents": 200, "score": 100.0,
                              "tier": "AUTO", "alternates": []},
                    "unit_cents": 200, "line_total_cents": 200,
                },
                {
                    "n": 2, "raw": "2 hours on-site labor", "qty": 2,
                    "item": "hours on-site labor",
                    "match": {"stock_code": "X",
                              "description": "WHITE HANGING HEART",
                              "unit_cents": 250, "score": 0.0,
                              "tier": "MANUAL", "alternates": []},
                    "unit_cents": None, "line_total_cents": None,
                },
            ],
            "subtotal_cents": 200, "discount_rate": "0%",
            "discount_cents": 0, "hst_cents": 26, "total_cents": 226,
            "match_health": 50.0, "needs_review": True,
        },
        "expected_draft":
        "QUOTATION QD-2026-1002\n"
        "Date: 2026-10-30 - Valid until: 2026-11-29\n"
        "Customer: Test Customer - Retail tier (0% discount)\n"
        "\n"
        "Lines:\n"
        "  1 x WHITE MUG @ $2.00 = $2.00  [AUTO 100.0]\n"
        "  2 x hours on-site labor = UNPRICED  [MANUAL - no price-book match]\n"
        "\n"
        "Subtotal: $2.00\n"
        "Discount (Retail, 0%): -$0.00\n"
        "HST (13%): $0.26\n"
        "TOTAL: $2.26\n"
        "\n"
        "Match health: 50.0% of lines AUTO - NEEDS REVIEW (1 line(s) unpriced).\n"
        "Status: PENDING HUMAN APPROVAL. Nothing has been sent.",
    },
]


def build_vectors() -> dict:
    parse = []
    for name, line, skip, qty, item in PARSE_VECTORS:
        p = parse_line(line)
        assert p["skip"] == skip, name
        if not skip:
            assert p["qty"] == qty and p["item"] == item, name
        parse.append({"name": name, "line": line,
                      "expected_skip": skip, "expected_qty": qty,
                      "expected_item": item})

    index = build_index(FIXTURE_CATALOG)
    match = []
    for name, item, code, tier in MATCH_VECTORS:
        m = best_match(item, index)
        assert m["stock_code"] == code, (name, m)
        assert m["tier"] == tier, (name, m)
        row = {"name": name, "item": item,
               "expected_stock_code": code, "expected_tier": tier,
               "expected_score": m["score"]}
        if tier == "REVIEW":
            row["expected_alternates"] = m["alternates"]
        match.append(row)

    math = []
    for v in MATH_VECTORS:
        lines = [{"qty": ln["qty"], "item": "x",
                  "match": {"tier": "AUTO", "unit_cents": ln["unit_cents"]}}
                 for ln in v["lines"]]
        got = price_lines(lines, v["tier"])
        for k, want in v["expected"].items():
            assert got[k] == want, (v["name"], k, got[k], want)
        math.append({"name": v["name"], "lines": v["lines"],
                     "tier": v["tier"], "expected": v["expected"]})

    drafts = []
    for v in DRAFT_VECTORS:
        got = draft_quote(v["quote"])
        assert got == v["expected_draft"], v["name"]
        drafts.append({"name": v["name"], "quote": v["quote"],
                       "expected_draft": v["expected_draft"]})

    return {"fixture_catalog": FIXTURE_CATALOG, "parse": parse,
            "match": match, "math": math, "drafts": drafts}


README_DATA = """# Data notes — what is real and what is seeded

## Real
- `data/raw/Online Retail.xlsx` — the UCI Online Retail dataset (Chen,
  Clément, Das; CC BY 4.0), bundled verbatim. It records 2010-11
  invoices from a UK-based online retailer.
- The price book (`data/outputs/pricebook.json`) is measured from the
  full corpus at build time: cancelled invoices excluded (InvoiceNo
  starting with 'C'), Quantity > 0, UnitPrice > 0; grouped by
  StockCode + Description; median UnitPrice becomes the SKU's sell
  price; SKUs with fewer than 5 transactions are dropped.
  {pb_stats}
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
- `data/outputs/quotes.json` — the {n_quotes}-quote priced work queue
  (fixed replay: Fri 2026-10-30).
- `data/outputs/summary.json` — headline counts and price-book stats.
- `data/test-vectors.json` — hand-checked shared contract asserted by
  both pytest (`tests/test_quotedesk.py`) and vitest
  (`web/src/rules.test.ts`): Python engine and TypeScript mirror must
  agree on every vector exactly.
"""


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


def main() -> None:
    if not RAW_XLSX.exists():
        print(f"quotedesk: corpus XLSX not found: {RAW_XLSX}",
              file=sys.stderr)
        raise SystemExit(1)
    result = build(RAW_XLSX)
    for name, payload in result.items():
        write_json(ROOT / "data" / "outputs" / f"{name}.json", payload)
        write_json(ROOT / "web" / "public" / "data" / f"{name}.json", payload)
    vectors = build_vectors()
    write_json(ROOT / "data" / "test-vectors.json", vectors)
    write_json(ROOT / "web" / "public" / "data" / "test-vectors.json",
               vectors)
    pb = result["summary"]["pricebook"]
    readme = README_DATA.format(
        pb_stats=(f"{pb['skus']:,} SKUs, {pb['transactions']:,} transactions, "
                  f"median unit price ${pb['median_unit_cents'] / 100:.2f}, "
                  f"from {pb['rows_read']:,} invoice rows."),
        n_quotes=result["summary"]["quotes"])
    (ROOT / "data" / "README-data.md").write_text(readme, encoding="utf-8")
    s = result["summary"]
    print(f"quotedesk: {s['quotes']} quotes over {pb['skus']:,} SKUs; "
          f"line tiers " +
          ", ".join(f"{t}={c}" for t, c in s["line_tiers"].items()) +
          f"; needs_review={s['needs_review']}")


if __name__ == "__main__":
    main()
