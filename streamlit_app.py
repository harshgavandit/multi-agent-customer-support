"""Entry point: `streamlit run streamlit_app.py`.

Just routes to one of the two views (Section 8). All the actual logic —
graphs, agents, tools, storage — lives in the modules those views import.
"""
import streamlit as st

st.set_page_config(page_title="Multi-Agent Support POC", layout="wide")

try:
    from config import configuration_problems
    problems = configuration_problems()
except ValueError as exc:
    st.error(str(exc))
    st.stop()
if problems:
    for problem in problems:
        st.error(problem)
    st.stop()

from views import approver_queue, customer_chat

view = st.sidebar.radio("View", ["Customer Chat", "Approver Queue"])

st.sidebar.divider()

if view == "Customer Chat":
    customer_chat.render()
else:
    approver_queue.render()
