"""Approver-facing pending-approvals UI (Section 8).

Deliberately has no notion of "the customer's live session" — it only ever
talks to session_store and pipeline/approval_graph.py. That's the point:
this view and the customer chat view never share a live execution, only
storage.
"""
import streamlit as st

from pipeline.approval_graph import resolve_approval
from session import session_store
from errors import SupportError


def render() -> None:
    st.header("Approver Queue")

    pending = session_store.list_pending_approvals()
    if not pending:
        st.info("No pending refund approvals.")
        return

    for approval in pending:
        title = f"Order {approval['order_id']} — ₹{approval['refund_amount']:,.2f} (session {approval['session_id']})"
        with st.expander(title):
            session = session_store.get_session(approval["session_id"])
            compacted_info = session["compacted_info"] if session else None

            st.write(f"**Reason for review:** {approval['reason']}")
            st.write(f"**Submitted:** {approval['created_at']}")

            st.caption("Compacted Ticket Info")
            if compacted_info is not None:
                st.json(compacted_info.model_dump())
            else:
                st.caption("No compacted info found for this session.")

            approve_col, deny_col = st.columns(2)
            if approve_col.button("Approve", key=f"approve_{approval['approval_id']}"):
                try:
                    resolve_approval(approval["approval_id"], "approved")
                except (SupportError, KeyError):
                    st.error("This request could not be approved. Refresh the queue and try again.")
                else:
                    st.rerun()
            if deny_col.button("Deny", key=f"deny_{approval['approval_id']}"):
                try:
                    resolve_approval(approval["approval_id"], "denied")
                except (SupportError, KeyError):
                    st.error("This request could not be denied. Refresh the queue and try again.")
                else:
                    st.rerun()
