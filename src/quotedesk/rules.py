r"""QuoteDesk — deterministic quote-building rules, no LLM calls.

Everything the UI shows comes from these functions (Python) or their
exact TypeScript mirror (web/src/rules.ts). The shared contract is
data/test-vectors.json, asserted by both pytest and vitest.

Pipeline: intake -> parse -> match -> price -> assemble -> gate -> queue.

Parse (per line of a pasted request):
  blank lines and header/intro/outro lines are skipped;
  `^(\d+(?:\.\d+)?)\s*[x×]\s*(.+)$` -> qty x item   ("3x WHITE MUG")
  `^(\d+)\s+(.+)$`                -> qty, item      ("12 WHITE MUG")
  `^a? couple of\s+(.+)$`         -> qty 2          ("a couple of white mugs")
  anything else                   -> qty 1.

Match (score 0-100, fully disclosed):
  tokenize: lowercase, punctuation -> space, split on whitespace,
      drop stopwords and pure-number tokens.
  score = keyword token recall x 55
        + exact-phrase substring x 25
        + bigram Jaccard x 20
  token recall = |line tokens & catalog tokens| / |line tokens|
  exact-phrase = 25 if the normalized line is a substring of the
      normalized catalog description, or vice versa, else 0
      (normalized = lowercase, punctuation -> space, single spaces)
  bigram Jaccard = |bigrams &| / |bigrams OR| over token bigram sets
      (0.0 when both are empty)
  tiers: score >= 75 -> AUTO; 50 <= score < 75 -> REVIEW (top-3
      alternates stored); score < 50 -> MANUAL (no price-book match).

Price (integer cents everywhere, half-up rounding — identical in
Python and TypeScript):
  unit = matched SKU median_price, in cents (AUTO and REVIEW lines are
      priced at the best match; MANUAL lines are UNPRICED, unit None).
  line_total = qty x unit.
  discount off subtotal by customer tier:
      Retail 0%, Trade 12%, Preferred 20%.
  HST 13% on the discounted subtotal.
  total = discounted subtotal + HST, all in cents.

Assemble: quote doc {id, customer, tier, created 2026-10-30,
valid_until +30d, lines, subtotal/discount/hst/total, match_health
(% of lines AUTO), needs_review (any line not AUTO), status
pending_human_approval, draft (human-readable quote text), sent False}.
Zero LLM calls — no API key needed anywhere.

Gate: every quote is pending_human_approval; sent is always False.
Nothing is ever sent by this pipeline.
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------- parse

_QTY_X = re.compile(r"^(\d+(?:\.\d+)?)\s*[x×]\s*(.+)$", re.IGNORECASE)
_QTY_N = re.compile(r"^(\d+)\s+(.+)$")
_COUPLE = re.compile(r"^a?\s*couple of\s+(.+)$", re.IGNORECASE)

_HEADER_RES = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"^\s*(hi|hello|hey|dear|good morning|good afternoon)\b",
    r"^\s*(thanks|thank you|regards|cheers|sincerely|best)\b",
    r"^\s*site visit\b",
    r"^\s*walked\b",
    r"^\s*here'?s what\b",
    r"^\s*here is what\b",
    r"^\s*(please|could you|kindly)\b",
    r"^\s*let me know\b",
    r"^\s*need this\b",
    r"^\s*(from|date|subject|re|customer|attn|job|project|site|"
    r"estimate|pricing)\s*:",
    r"^\s*(quote request|parts list|price list|site notes)\b",
])


def _qty_num(text: str):
    n = float(text)
    return int(n) if n.is_integer() else n


def parse_line(line: str) -> dict:
    """Parse one request line -> {skip, qty, item}."""
    raw = line.strip()
    if not raw:
        return {"skip": True, "qty": 0, "item": ""}
    if any(p.match(raw) for p in _HEADER_RES):
        return {"skip": True, "qty": 0, "item": ""}
    m = _QTY_X.match(raw)
    if m:
        return {"skip": False, "qty": _qty_num(m.group(1)),
                "item": m.group(2).strip()}
    m = _COUPLE.match(raw)
    if m:
        return {"skip": False, "qty": 2, "item": m.group(1).strip()}
    m = _QTY_N.match(raw)
    if m:
        return {"skip": False, "qty": int(m.group(1)),
                "item": m.group(2).strip()}
    return {"skip": False, "qty": 1, "item": raw}


# ---------------------------------------------------------------- match

STOPWORDS = frozenset(
    "a an the and or of for to in on with by from at as is are was were "
    "be been it its this that these those your you we our their".split()
)


def tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return [t for t in cleaned.split()
            if t not in STOPWORDS and not t.isdigit()]


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())


def bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return set(zip(tokens, tokens[1:]))


def match_score(line_text: str, sku_tokens: list[str],
                sku_bigrams: set[tuple[str, str]],
                sku_norm: str) -> float:
    """0-100 match score; identical arithmetic in the TS mirror."""
    lt = tokenize(line_text)
    st = set(sku_tokens)
    if lt:
        recall = len(set(lt) & st) / len(lt)
    else:
        recall = 0.0
    lnorm = normalize(line_text)
    phrase = 1.0 if (lnorm and sku_norm and
                     (lnorm in sku_norm or sku_norm in lnorm)) else 0.0
    lb = bigrams(lt)
    if lb or sku_bigrams:
        jacc = len(lb & sku_bigrams) / len(lb | sku_bigrams)
    else:
        jacc = 0.0
    return recall * 55.0 + phrase * 25.0 + jacc * 20.0


def match_tier(score: float) -> str:
    if score >= 75:
        return "AUTO"
    if score >= 50:
        return "REVIEW"
    return "MANUAL"


def build_index(entries: list[dict]) -> list[dict]:
    """Precompute token/bigram/normalized views of the price book."""
    idx = []
    for e in entries:
        toks = tokenize(e["description"])
        idx.append({
            "stock_code": e["stock_code"],
            "description": e["description"],
            "unit_cents": e["unit_cents"],
            "tokens": toks,
            "bigrams": bigrams(toks),
            "norm": normalize(e["description"]),
        })
    return idx


def best_match(item: str, index: list[dict]) -> dict:
    """Best catalog match + tier + top-3 alternates (deterministic)."""
    scored = []
    for sku in index:
        s = match_score(item, sku["tokens"], sku["bigrams"], sku["norm"])
        scored.append((s, sku))
    # sort: score desc, stock_code asc — first entry wins ties.
    scored.sort(key=lambda p: (-p[0], p[1]["stock_code"]))
    best_s, best = scored[0]
    tier = match_tier(best_s)
    alternates = [
        {"stock_code": sku["stock_code"], "description": sku["description"],
         "score": s}
        for s, sku in scored[1:4]
    ]
    return {
        "stock_code": best["stock_code"],
        "description": best["description"],
        "unit_cents": best["unit_cents"],
        "score": best_s,
        "tier": tier,
        "alternates": alternates if tier == "REVIEW" else [],
    }


# ---------------------------------------------------------------- price

DISCOUNT_RATE = {"Retail": (0, 100), "Trade": (12, 100),
                 "Preferred": (20, 100)}
HST_RATE = (13, 100)


def _half_up_mul(cents: int, num: int, den: int) -> int:
    return (cents * num + den // 2) // den


def fmt_money(cents: int) -> str:
    return f"${cents / 100:.2f}"


def price_lines(lines: list[dict], customer_tier: str) -> dict:
    """Money for one quote, in integer cents. MANUAL lines are UNPRICED."""
    priced = []
    subtotal = 0
    for ln in lines:
        m = ln["match"]
        if m is not None and m["tier"] in ("AUTO", "REVIEW"):
            unit = m["unit_cents"]
            total = int(ln["qty"] * unit)
        else:
            unit, total = None, None
        row = dict(ln)
        row["unit_cents"] = unit
        row["line_total_cents"] = total
        if total is not None:
            subtotal += total
        priced.append(row)
    dnum, dden = DISCOUNT_RATE[customer_tier]
    discount = _half_up_mul(subtotal, dnum, dden)
    discounted = subtotal - discount
    hst = _half_up_mul(discounted, *HST_RATE)
    total = discounted + hst
    return {
        "lines": priced,
        "subtotal_cents": subtotal,
        "discount_rate": f"{dnum}%",
        "discount_cents": discount,
        "hst_cents": hst,
        "total_cents": total,
    }


# ------------------------------------------------------------- assemble

CREATED = "2026-10-30"
VALID_UNTIL = "2026-11-29"


def match_health(lines: list[dict]) -> float:
    auto = sum(1 for ln in lines
               if ln["match"] is not None and ln["match"]["tier"] == "AUTO")
    return round(100.0 * auto / len(lines), 1) if lines else 0.0


def draft_quote(quote: dict) -> str:
    """Human-readable quote text. Mirrored character-for-character in TS."""
    q = quote
    out = [
        f"QUOTATION {q['id']}",
        f"Date: {q['created']} - Valid until: {q['valid_until']}",
        f"Customer: {q['customer']} - {q['tier']} tier "
        f"({q['discount_rate']} discount)",
        "",
        "Lines:",
    ]
    for ln in q["lines"]:
        m = ln["match"]
        qty = ln["qty"]
        if isinstance(qty, float) and qty.is_integer():
            qty = int(qty)
        if m is None or m["tier"] == "MANUAL":
            out.append(f"  {qty} x {ln['item']} = UNPRICED  "
                       f"[MANUAL - no price-book match]")
        else:
            out.append(f"  {qty} x {ln['item']} @ "
                       f"{fmt_money(m['unit_cents'])} = "
                       f"{fmt_money(ln['line_total_cents'])}  "
                       f"[{m['tier']} {m['score']:.1f}]")
    out += [
        "",
        f"Subtotal: {fmt_money(q['subtotal_cents'])}",
        f"Discount ({q['tier']}, {q['discount_rate']}): "
        f"-{fmt_money(q['discount_cents'])}",
        f"HST (13%): {fmt_money(q['hst_cents'])}",
        f"TOTAL: {fmt_money(q['total_cents'])}",
        "",
    ]
    unpriced = sum(1 for ln in q["lines"] if ln["line_total_cents"] is None)
    health = f"{q['match_health']:.1f}"
    if q["needs_review"]:
        out.append(f"Match health: {health}% of lines AUTO - NEEDS REVIEW "
                   f"({unpriced} line(s) unpriced).")
    else:
        out.append(f"Match health: {health}% of lines AUTO.")
    out.append("Status: PENDING HUMAN APPROVAL. Nothing has been sent.")
    return "\n".join(out)


def assemble_quote(qid: str, customer: str, tier: str, channel: str,
                   request_text: str, parsed: list[dict],
                   priced: dict) -> dict:
    lines = priced["lines"]
    needs_review = any(
        ln["match"] is None or ln["match"]["tier"] != "AUTO"
        for ln in lines)
    quote = {
        "id": qid,
        "customer": customer,
        "tier": tier,
        "channel": channel,
        "request_text": request_text,
        "created": CREATED,
        "valid_until": VALID_UNTIL,
        "lines": lines,
        "subtotal_cents": priced["subtotal_cents"],
        "discount_rate": priced["discount_rate"],
        "discount_cents": priced["discount_cents"],
        "hst_cents": priced["hst_cents"],
        "total_cents": priced["total_cents"],
        "match_health": match_health(lines),
        "needs_review": needs_review,
        "status": "pending_human_approval",
        "sent": False,
    }
    quote["draft"] = draft_quote(quote)
    return quote


def median_to_cents(median_price: float) -> int:
    """Half-up dollars->cents, so the TS mirror can reuse the stored int."""
    return int((Decimal(str(median_price)) * 100)
               .to_integral_value(rounding=ROUND_HALF_UP))
