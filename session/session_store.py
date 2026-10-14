"""Concept: Session storage + async human-in-the-loop bridge (Sections 5 & 7).

Two module-level dicts, both guarded by a lock, are the *entire* persistence
layer for this POC:

- `_sessions`: session_id -> SessionState dict
- `_pending_approvals`: approval_id -> PendingApproval dict

Why a plain module-level dict and not `st.session_state`? `st.session_state`
is scoped per browser tab/session in Streamlit — it would give the customer
view and the approver view two disconnected copies of the world, which
breaks the entire async-approval story (Section 5 explicitly requires both
views to read/write the *same* underlying store). A module-level dict is
shared by every Streamlit rerun in the same process, which is exactly what
we need for a POC.

Everything else in the app talks to storage exclusively through the
functions below — not by touching `_sessions`/`_pending_approvals` directly.
That's what makes swapping this out for a real database later a one-file
change (see README).
"""
import threading
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.state import new_session_state

_lock = threading.Lock()
_sessions: Dict[str, Dict[str, Any]] = {}
_pending_approvals: Dict[str, Dict[str, Any]] = {}
_session_locks: Dict[str, Any] = {}


@contextmanager
def session_transaction(session_id: str):
    """Serialize customer turns and approval outcomes for one session."""
    with _lock:
        transaction_lock = _session_locks.setdefault(session_id, threading.RLock())
    with transaction_lock:
        yield


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return deepcopy(_sessions.get(session_id))


def get_or_create_session(session_id: str) -> Dict[str, Any]:
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = new_session_state(session_id)
        return deepcopy(_sessions[session_id])


def save_session(session_id: str, state: Dict[str, Any]) -> None:
    with _lock:
        _sessions[session_id] = deepcopy(state)


# --------------------------------------------------------------------------
# Pending approvals
# --------------------------------------------------------------------------

def add_pending_approval(record: Dict[str, Any]) -> None:
    with _lock:
        _pending_approvals[record["approval_id"]] = deepcopy(record)


def get_pending_approval(approval_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return deepcopy(_pending_approvals.get(approval_id))


def list_pending_approvals() -> List[Dict[str, Any]]:
    """Only records still awaiting a decision — used by the Approver View."""
    with _lock:
        return deepcopy([
            record
            for record in _pending_approvals.values()
            if record["status"] == "pending"
        ])


def update_pending_approval(approval_id: str, **fields: Any) -> None:
    with _lock:
        record = _pending_approvals.get(approval_id)
        if record is None:
            raise KeyError(f"No pending approval with id {approval_id}")
        record.update(fields)


def resolved_at_now() -> datetime:
    return datetime.now(timezone.utc)
