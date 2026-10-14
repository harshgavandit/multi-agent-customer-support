"""Concept: Asynchronous Human-in-the-Loop, resolution side (Section 5).

This is a second, completely independent LangGraph — it shares no live
execution with the customer-turn graph in pipeline/graph.py. The only thing
connecting the two is shared storage (session/session_store.py): this graph
reads a session's history, appends an outcome message to it, and writes it
back. The next time that session's chat is opened, the message is just...
there, like an async notification arrived while the customer was away.

Kept as a tiny graph (rather than a plain if/else function) deliberately,
so a student can see the same StateGraph/conditional-edge primitives reused
for a second, unrelated flow.
"""
import uuid
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from pipeline.state import now_iso
from errors import SupportError
from session import session_store


class ApprovalState(TypedDict):
    session_id: str
    conversation_history: List[Dict[str, Any]]
    order_id: str
    refund_amount: float
    decision: str  # "approved" | "denied"


def _approve_node(state: ApprovalState) -> ApprovalState:
    """Issuing a refund is now purely a human-approved outcome — there is no
    `issue_refund` tool for an agent to call. The confirmation reference is
    just message text, not a DB write or a tool invocation."""
    confirmation_id = f"REF-{state['order_id']}-{uuid.uuid4().hex[:6].upper()}"
    reply = (
        f"Update on your refund request for order {state['order_id']}: it's been approved. "
        f"₹{state['refund_amount']:,.2f} has been refunded (confirmation {confirmation_id})."
    )
    state["conversation_history"].append({"role": "assistant", "content": reply, "timestamp": now_iso()})
    return state


def _deny_node(state: ApprovalState) -> ApprovalState:
    reply = (
        f"Update on your refund request for order {state['order_id']}: after review, we're unable to "
        f"approve this refund of ₹{state['refund_amount']:,.2f}."
    )
    state["conversation_history"].append({"role": "assistant", "content": reply, "timestamp": now_iso()})
    return state


def _route_by_decision(state: ApprovalState) -> str:
    return "approve" if state["decision"] == "approved" else "deny"


def _build_approval_graph():
    graph = StateGraph(ApprovalState)
    graph.add_node("approve", _approve_node)
    graph.add_node("deny", _deny_node)
    graph.set_conditional_entry_point(_route_by_decision, {"approve": "approve", "deny": "deny"})
    graph.add_edge("approve", END)
    graph.add_edge("deny", END)
    return graph.compile()


_compiled_approval_graph = _build_approval_graph()


def resolve_approval(approval_id: str, decision: str) -> None:
    """Entry point used by the Approver View. `decision` is "approved" or
    "denied". Runs a brand-new graph invocation for the target session,
    independent of any customer-turn graph run, and persists the result."""
    if decision not in {"approved", "denied"}:
        raise SupportError("Choose Approve or Deny.")
    approval = session_store.get_pending_approval(approval_id)
    if approval is None:
        raise KeyError(f"No pending approval with id {approval_id}")

    with session_store.session_transaction(approval["session_id"]):
        _resolve_locked(approval_id, decision)


def _resolve_locked(approval_id: str, decision: str) -> None:
    approval = session_store.get_pending_approval(approval_id)
    if approval["status"] != "pending":
        raise SupportError("This refund request has already been resolved. Refresh the queue.")

    session = session_store.get_session(approval["session_id"])
    if session is None:
        raise KeyError(f"No session with id {approval['session_id']}")

    initial_state: ApprovalState = {
        "session_id": approval["session_id"],
        "conversation_history": session["conversation_history"],
        "order_id": approval["order_id"],
        "refund_amount": approval["refund_amount"],
        "decision": decision,
    }
    result = _compiled_approval_graph.invoke(initial_state)

    session["conversation_history"] = result["conversation_history"]
    session_store.save_session(approval["session_id"], session)
    session_store.update_pending_approval(
        approval_id, status=decision, resolved_at=session_store.resolved_at_now()
    )
