"""Concept: Context Compaction (Section 3.3 of the spec) — arguably the
main teaching point of this whole project.

By the time this node runs, the conversation might be 10+ messages long.
Every downstream step (routing, the specialist agents, the tools they call)
only ever needs a handful of facts out of that — not the raw transcript.
This node is the one and only place that reads the full history and
distills it into `CompactedTicketInfo`. From here on, the rest of the graph
passes that small JSON object around instead of re-sending the whole
conversation to every LLM call.

Why this matters in practice: every additional turn makes the raw history
larger and more expensive to re-parse, and burying the actually-relevant
fields inside a wall of chat text makes routing logic and tool calls more
error prone. Compact once, reuse everywhere.
"""
from llm.client import complete_json
from pipeline.state import CompactedTicketInfo, SessionState
from errors import ModelUnavailable
from pydantic import ValidationError

SYSTEM_PROMPT = """You convert a customer support conversation into a compact,
structured ticket. Read the full conversation and extract exactly these
fields as a JSON object, no markdown fences, no commentary:

{
  "issue_summary": string,               // one or two sentences, plain language
  "issue_category": "billing_issue" | "refund_request" | "technical_issue" | "account_issue" | "other",
  "order_id": string | null,
  "refund_amount": number | null,        // rupees; null unless this is a refund_request
  "customer_sentiment": "neutral" | "frustrated" | "angry",
  "info_complete": boolean,              // true if enough info exists to act on this ticket
  "missing_fields": [string]              // names of any fields still missing; [] if none
}

Focus on the latest customer request, reusing explicitly supplied facts
from earlier customer messages. A request to check an invoice or payment
status belongs to billing_issue, even without a complaint. Never infer or
invent an order ID or refund amount. Only set "refund_amount" for refund_request tickets. Use your best judgement
on sentiment based on the customer's tone and word choice.
"""


def _format_transcript(history: list) -> str:
    lines = [f"{m['role']}: {m['content']}" for m in history]
    return "\n".join(lines)


def run(state: SessionState) -> SessionState:
    transcript = _format_transcript(state["conversation_history"])
    result = complete_json(SYSTEM_PROMPT, transcript)
    try:
        info = CompactedTicketInfo(**result)
    except ValidationError:
        raise ModelUnavailable("The model returned invalid ticket details. Please clarify the order ID and a positive refund amount.") from None
    category = info.issue_category.value
    if not info.info_complete or info.missing_fields:
        raise ModelUnavailable("More ticket details are needed. Please include the order ID and, for a refund, the amount.")
    if category in {"billing_issue", "refund_request"} and not (info.order_id and info.order_id.strip()):
        raise ModelUnavailable("Please include an explicit order ID so we can look up the correct order.")
    if category == "refund_request" and info.refund_amount is None:
        raise ModelUnavailable("Please include a positive refund amount.")
    if info.order_id:
        info.order_id = info.order_id.strip().upper()
    state["compacted_info"] = info
    return state
