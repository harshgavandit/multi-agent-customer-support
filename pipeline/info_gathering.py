"""Concept: Info-Gathering Node — the first LLM call in the customer-turn
graph (Section 4).

Job of this node, and *only* this node: look at the full conversation and
decide whether there's enough information to act. If not, produce a single
clarifying question and stop the turn there. It deliberately does NOT
produce the structured `CompactedTicketInfo` — that's the Context
Compaction node's job (pipeline/compaction.py). Keeping these separate is
the teaching point: "enough info to proceed?" and "what exactly is the
structured ticket?" are different questions, and conflating them into one
LLM call makes both harder to prompt for and to test.
"""
from llm.client import complete_json
from pipeline.state import SessionState, now_iso
from errors import ModelUnavailable

SYSTEM_PROMPT = """You are the info-gathering step of a customer support bot.

Read the full conversation so far and decide whether enough information has
been gathered to route this ticket to a specialist team. Do not solve the
issue yourself — only judge completeness and, if incomplete, ask ONE
clarifying question.

Minimum information required, depending on what the issue seems to be about:
- Billing issues: what the issue is about, and an order ID.
- Refund requests: what the issue is about, an order ID, and the rupee
  amount the customer wants refunded.
- Technical/account issues or anything else: a clear description of the
  issue is enough on its own.

Judge the customer's latest request using facts from their previous messages.
An invoice lookup or payment-status check IS a complete billing request
when an explicit order ID is present; a complaint or explanation is not
required for these lookups. Never keep asking about an earlier vague
problem once the customer has clarified what they want.
A vague statement such as "I have a problem with my order" is incomplete;
ask what the issue is and which order it concerns.
Never guess an order ID or refund amount. Refund amounts must be positive.
Example: "My order is ORD-1003. Please check the invoice amount and payment
status for this order." -> info_complete=true, clarifying_question=null.

Respond with ONLY a JSON object, no markdown fences, no commentary:
{
  "info_complete": true | false,
  "clarifying_question": string | null   // required if info_complete is false, else null
}
"""


def _format_transcript(history: list) -> str:
    lines = [f"{m['role']}: {m['content']}" for m in history]
    return "\n".join(lines)


def run(state: SessionState) -> SessionState:
    transcript = _format_transcript(state["conversation_history"])
    result = complete_json(SYSTEM_PROMPT, transcript)

    info_complete = result.get("info_complete")
    if type(info_complete) is not bool:
        raise ModelUnavailable("The model returned an invalid completeness decision. Please try again.")

    if not info_complete:
        question = result.get("clarifying_question") or (
            "Could you share a bit more detail so I can help with that?"
        )
        if not isinstance(question, str):
            raise ModelUnavailable("The model returned an invalid clarifying question. Please try again.")
        state["conversation_history"].append(
            {"role": "assistant", "content": question, "timestamp": now_iso()}
        )

    state["awaiting_clarification"] = not info_complete
    return state
