"""LangGraph wiring for a single customer turn (Section 4 of the spec).

    info_gathering --(complete?)--> compaction --> route --(team?)--> billing_agent
          |                                                       |--> refunds_agent
          |                                                       |--> general_support
          '--(incomplete)--> END

Every path through this graph ends at END within one `invoke()` call —
including the "refund needs approval" path. There is no `interrupt()` /
pause-and-resume anywhere in this module: "pending approval" is represented
purely as a PendingApproval record in session_store, a state *value*, not a
suspended graph. Resuming that story later is a completely separate graph
(pipeline/approval_graph.py), invoked independently from the Approver View.
"""
from langgraph.graph import END, StateGraph

from agents import billing_agent, refunds_agent
from pipeline import compaction, info_gathering
from pipeline.state import SessionState, now_iso
from session import session_store
from rate_limit import check_customer_turn
from errors import SupportError


def _route_after_gathering(state: SessionState) -> str:
    return "end" if state["awaiting_clarification"] else "continue"


def _route_node(state: SessionState) -> SessionState:
    """The Routing Node: a plain conditional on issue_category, no LLM call."""
    category = state["compacted_info"].issue_category.value
    if category == "billing_issue":
        state["assigned_team"] = "payments_team"
    elif category == "refund_request":
        state["assigned_team"] = "refunds_team"
    else:
        state["assigned_team"] = "unassigned"
    return state


def _route_by_team(state: SessionState) -> str:
    return state["assigned_team"]


def _general_support_node(state: SessionState) -> SessionState:
    """Fallback for categories with no dedicated specialist agent
    (technical_issue, account_issue, other) — not one of the two core
    agents called out in the spec, kept intentionally minimal."""
    reply = "Thanks for the details — I've logged this and our support team will follow up with you soon."
    state["conversation_history"].append({"role": "assistant", "content": reply, "timestamp": now_iso()})
    return state


def _build_graph():
    graph = StateGraph(SessionState)

    graph.add_node("info_gathering", info_gathering.run)
    graph.add_node("compaction", compaction.run)
    graph.add_node("route", _route_node)
    graph.add_node("billing_agent", billing_agent.run)
    graph.add_node("refunds_agent", refunds_agent.run)
    graph.add_node("general_support", _general_support_node)

    graph.set_entry_point("info_gathering")
    graph.add_conditional_edges(
        "info_gathering",
        _route_after_gathering,
        {"end": END, "continue": "compaction"},
    )
    graph.add_edge("compaction", "route")
    graph.add_conditional_edges(
        "route",
        _route_by_team,
        {
            "payments_team": "billing_agent",
            "refunds_team": "refunds_agent",
            "unassigned": "general_support",
        },
    )
    graph.add_edge("billing_agent", END)
    graph.add_edge("refunds_agent", END)
    graph.add_edge("general_support", END)

    return graph.compile()


_compiled_graph = _build_graph()


def run_customer_turn(session_id: str, user_message: str) -> SessionState:
    """Entry point used by the Streamlit customer chat view.

    Loads (or creates) the session, appends the user's message, runs the
    graph start-to-finish, and persists the result. Always returns fully
    resolved — the caller never needs to poll or wait.
    """
    if not session_id.strip() or not user_message.strip():
        raise SupportError("Please enter a session ID and a non-empty message.")
    if len(user_message) > 8000:
        raise SupportError("Please keep each message under 8,000 characters.")
    check_customer_turn(session_id)
    with session_store.session_transaction(session_id):
        state = session_store.get_or_create_session(session_id)
        state["conversation_history"].append({"role": "user", "content": user_message, "timestamp": now_iso()})
        state["turn_count"] += 1
        state["tool_result"] = None
        result_state = _compiled_graph.invoke(state)
        session_store.save_session(session_id, result_state)
        return result_state
