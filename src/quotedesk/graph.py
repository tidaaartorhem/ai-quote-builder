"""The QuoteDesk workflow as a LangGraph StateGraph.

Nodes: intake -> parse -> match -> price -> assemble -> gate -> queue.
The gate node is the product's hard rule: quotes are produced, sending
is always a human action. No node calls an LLM and no node sends mail.

langgraph may not be installed in every environment; in that case
graph.py exposes the same node functions via run_nodes() so the
pipeline output is identical either way.
"""

from __future__ import annotations

from typing import TypedDict

from .nodes import (NODES_IN_ORDER, node_assemble, node_gate, node_intake,
                    node_match, node_parse, node_price, run_nodes)


class QuoteState(TypedDict, total=False):
    requests: list
    pricebook: list
    intaked: list
    parsed: list
    matched: list
    priced_q: list
    assembled: list
    queue: list


def build_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(QuoteState)
    graph.add_node("intake", node_intake)
    graph.add_node("parse", node_parse)
    graph.add_node("match", node_match)
    graph.add_node("price", node_price)
    graph.add_node("assemble", node_assemble)
    graph.add_node("gate", node_gate)
    graph.set_entry_point("intake")
    graph.add_edge("intake", "parse")
    graph.add_edge("parse", "match")
    graph.add_edge("match", "price")
    graph.add_edge("price", "assemble")
    graph.add_edge("assemble", "gate")
    graph.add_edge("gate", END)
    return graph.compile()


def run_graph(requests: list, pricebook: list) -> list:
    """Run the compiled graph over raw requests; return the gated queue."""
    app = build_graph()
    result = app.invoke({"requests": requests, "pricebook": pricebook})
    return result["queue"]
