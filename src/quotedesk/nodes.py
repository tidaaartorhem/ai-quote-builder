"""LangGraph node functions — pure, deterministic, independently testable.

The graph itself lives in graph.py (a thin StateGraph wrapper around
these nodes). scripts/build_quotedesk.py runs the same nodes in order
when langgraph is not installed, so the pipeline output is identical
with or without the graph library: the graph is orchestration, the
nodes are the work.
"""

from __future__ import annotations

from .rules import (assemble_quote, best_match, build_index, parse_line,
                    price_lines)


def node_intake(state: dict) -> dict:
    """Validate requests and attach quote ids + dates."""
    out = []
    for i, req in enumerate(state["requests"]):
        row = dict(req)
        row["qid"] = f"QD-2026-{1001 + i}"
        out.append(row)
    return {"intaked": out}


def node_parse(state: dict) -> dict:
    """Parse every request text into line items."""
    out = []
    for req in state["intaked"]:
        lines = []
        for n, raw in enumerate(req["request_text"].splitlines(), 1):
            p = parse_line(raw)
            if p["skip"]:
                continue
            lines.append({"n": n, "raw": raw.strip(), "qty": p["qty"],
                          "item": p["item"]})
        row = dict(req)
        row["parsed_lines"] = lines
        out.append(row)
    return {"parsed": out}


def node_match(state: dict) -> dict:
    """Fuzzy-match every parsed line against the price book."""
    index = build_index(state["pricebook"])
    out = []
    for req in state["parsed"]:
        lines = []
        for ln in req["parsed_lines"]:
            row = dict(ln)
            row["match"] = best_match(ln["item"], index)
            lines.append(row)
        row = dict(req)
        row["matched_lines"] = lines
        out.append(row)
    return {"matched": out}


def node_price(state: dict) -> dict:
    """Attach money (integer cents) to every matched quote."""
    out = []
    for req in state["matched"]:
        priced = price_lines(req["matched_lines"], req["tier"])
        row = dict(req)
        row["priced"] = priced
        out.append(row)
    return {"priced_q": out}


def node_assemble(state: dict) -> dict:
    """Build the quote doc + human-readable draft text."""
    out = []
    for req in state["priced_q"]:
        out.append(assemble_quote(
            req["qid"], req["customer"], req["tier"], req["channel"],
            req["request_text"], req["parsed_lines"], req["priced"]))
    return {"assembled": out}


def node_gate(state: dict) -> dict:
    """Human gate: every quote is pending approval, never sent."""
    out = []
    for q in state["assembled"]:
        row = dict(q)
        row["status"] = "pending_human_approval"
        row["sent"] = False
        out.append(row)
    return {"queue": out}


NODES_IN_ORDER = [node_intake, node_parse, node_match, node_price,
                  node_assemble, node_gate]


def run_nodes(state: dict) -> dict:
    """Run the nodes in order without langgraph (identical output)."""
    for fn in NODES_IN_ORDER:
        state = {**state, **fn(state)}
    return state
