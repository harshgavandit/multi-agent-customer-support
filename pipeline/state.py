"""Concept: Compacted State + Session State (Section 6 of the spec).

Two distinct schemas live here, and the distinction *is* the teaching point:

- `CompactedTicketInfo` is small, structured, and cheap to pass around. It's
  what routing, agents, and tools actually consume.
- `SessionState` is the full LangGraph graph state. It carries the raw
  conversation history (needed for the LLM nodes to reason over) *and* the
  compacted info (needed for everything downstream of routing). Nothing
  downstream of the Context Compaction node should need to re-read
  `conversation_history` — if you find yourself doing that, the compaction
  step isn't doing its job.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


def now_iso() -> str:
    """Single source of truth for message timestamps."""
    return datetime.now(timezone.utc).isoformat()


class IssueCategory(str, Enum):
    BILLING_ISSUE = "billing_issue"
    REFUND_REQUEST = "refund_request"
    TECHNICAL_ISSUE = "technical_issue"
    ACCOUNT_ISSUE = "account_issue"
    OTHER = "other"


class CustomerSentiment(str, Enum):
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class CompactedTicketInfo(BaseModel):
    """The output of the Context Compaction node. See pipeline/compaction.py."""

    issue_summary: str
    issue_category: IssueCategory
    order_id: Optional[str] = None
    refund_amount: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    customer_sentiment: CustomerSentiment
    info_complete: bool
    missing_fields: List[str] = Field(default_factory=list)


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class PendingApproval(BaseModel):
    """A record in the separate approval store (session/session_store.py).

    Deliberately NOT part of the LangGraph state — the approver flow reads
    and writes these independently of any customer-turn graph invocation.
    """

    approval_id: str
    session_id: str
    order_id: str
    refund_amount: float = Field(gt=0, allow_inf_nan=False)
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime
    resolved_at: Optional[datetime] = None


class SessionState(TypedDict):
    """The LangGraph graph state for a single customer-turn invocation.

    `awaiting_clarification` is graph-scoped routing signal only (it decides
    whether the info-gathering -> compaction edge fires this turn) — it is
    not one of the fields the spec calls out as persisted session data, but
    storing it alongside the rest is harmless for this in-memory POC.
    """

    session_id: str
    conversation_history: List[Dict[str, Any]]
    compacted_info: Optional[CompactedTicketInfo]
    assigned_team: Optional[str]  # "payments_team" | "refunds_team" | "unassigned"
    tool_calls: List[Dict[str, Any]]
    tool_result: Optional[Dict[str, Any]]
    turn_count: int
    awaiting_clarification: bool


def new_session_state(session_id: str) -> SessionState:
    """Factory for a brand-new, empty session."""
    return SessionState(
        session_id=session_id,
        conversation_history=[],
        compacted_info=None,
        assigned_team=None,
        tool_calls=[],
        tool_result=None,
        turn_count=0,
        awaiting_clarification=False,
    )
