"""Customer-facing chat UI (Section 8).

Note the split of responsibilities: `st.session_state` here is used only to
remember *which* session_id this browser tab is currently looking at — a
purely local UI cursor. The actual conversation data lives in
session/session_store.py, shared across tabs in the same server process, which is what lets
the approver's resolution show up here later without any direct connection
between the two views.
"""
import uuid

import streamlit as st

from pipeline.graph import run_customer_turn
from session import session_store
from errors import SupportError


def _new_session_id() -> str:
    return uuid.uuid4().hex[:8]


def _resume_session() -> None:
    # Runs before the render, after Streamlit receives the entire form payload.
    resume_id = st.session_state.get("resume_session_id", "").strip()
    if resume_id:
        st.session_state.active_session_id = resume_id


def render() -> None:
    st.header("Customer Chat")

    if "active_session_id" not in st.session_state:
        st.session_state.active_session_id = _new_session_id()

    with st.sidebar:
        st.subheader("Session")
        st.code(st.session_state.active_session_id, language=None)

        if st.button("New Session"):
            st.session_state.active_session_id = _new_session_id()
            st.rerun()

        st.divider()
        with st.form("resume_session"):
            st.text_input("Resume an existing session ID", key="resume_session_id")
            st.form_submit_button("Resume", on_click=_resume_session)

    session_id = st.session_state.active_session_id
    state = session_store.get_or_create_session(session_id)

    for message in state["conversation_history"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    with st.expander("Compacted Ticket Info (teaching view)", expanded=False):
        if state["compacted_info"] is not None:
            st.json(state["compacted_info"].model_dump())
        else:
            st.caption("Nothing compacted yet — still gathering information.")

    with st.expander("Tool call trace (teaching view)", expanded=False):
        if state["tool_calls"]:
            st.json(state["tool_calls"])
        else:
            st.caption("No tools called yet.")

    user_message = st.chat_input("Type your message...")
    if user_message:
        try:
            with st.spinner("Reviewing your request..."):
                run_customer_turn(session_id, user_message)
        except SupportError as exc:
            st.error(str(exc))
        except Exception:
            st.error("The request could not be completed. Please try again or contact the app administrator.")
        else:
            st.rerun()
