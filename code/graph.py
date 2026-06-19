"""LangGraph StateGraph builder: Parse -> Vision -> Circuit -> Adjudicate -> Clamp."""

from __future__ import annotations

from langgraph.graph import StateGraph
from nodes.adjudicate import adjudicate_node
from nodes.circuit import circuit_node
from nodes.clamp import clamp_node
from nodes.parse import parse_node
from nodes.vision import vision_node
from state import ClaimState


def build_graph():
    """Build and compile the LangGraph workflow."""
    graph = StateGraph(ClaimState)

    graph.add_node("parse", parse_node)
    graph.add_node("vision", vision_node)
    graph.add_node("circuit", circuit_node)
    graph.add_node("adjudicate", adjudicate_node)
    graph.add_node("clamp", clamp_node)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "vision")
    graph.add_edge("vision", "circuit")
    graph.add_edge("circuit", "adjudicate")
    graph.add_edge("adjudicate", "clamp")
    graph.set_finish_point("clamp")

    return graph.compile()
