"""Refunds Agent — a graph node reached once routing assigns
`assigned_team = "refunds_team"` (see pipeline/graph.py).

Policy: no refund of any amount is ever issued by this agent. Every
eligible refund request is filed as a `PendingApproval` and goes to manual
review — there is no threshold-based "small refunds auto-issue" branch.
This node's only job for an eligible request is to file it and hand back a
reply; it never learns how the request is eventually resolved. That
happens later, in a completely separate graph invocation kicked off from
the Approver View (see pipeline/approval_graph.py) — nothing here waits or
blocks on that outcome.
"""
import uuid

from config import APPROVAL_TURNAROUND_HOURS
from pipeline.state import ApprovalStatus, PendingApproval, SessionState, now_iso
from session import session_store
from tools.mock_tools import check_refund_eligibility


def run(state: SessionState) -> SessionState:
    info = state["compacted_info"]
    order_id = info.order_id or "UNKNOWN"
    amount = info.refund_amount or 0.0

    eligible, reason = check_refund_eligibility(order_id)
    state["tool_calls"].append(
        {"tool": "check_refund_eligibility", "args": {"order_id": order_id}, "result": {"eligible": eligible, "reason": reason}}
    )

    if not eligible:
        reply = f"I'm sorry, but order {order_id} isn't eligible for a refund: {reason}"
    else:
        existing = next((record for record in session_store.list_pending_approvals()
                         if record["session_id"] == state["session_id"] and record["order_id"] == order_id), None)
        if existing:
            reply = (
                f"Your refund request of ₹{existing['refund_amount']:,.2f} for order {order_id} "
                "is already under manual review. We'll update this chat when it's decided."
            )
            state["conversation_history"].append({"role": "assistant", "content": reply, "timestamp": now_iso()})
            return state
        approval = PendingApproval(
            approval_id=str(uuid.uuid4()),
            session_id=state["session_id"],
            order_id=order_id,
            refund_amount=amount,
            reason="All refund requests require manual review before processing.",
            status=ApprovalStatus.PENDING,
            created_at=session_store.resolved_at_now(),
        )
        session_store.add_pending_approval(approval.model_dump())
        reply = (
            f"Your refund request of ₹{amount:,.2f} for order {order_id} has been sent for manual review. "
            f"Expect a resolution within about {APPROVAL_TURNAROUND_HOURS} hours — "
            f"we'll update this chat as soon as it's decided, no need to wait here."
        )

    state["conversation_history"].append({"role": "assistant", "content": reply, "timestamp": now_iso()})
    return state
