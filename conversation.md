# Example Conversations

Five walkthroughs showing every path through the system: multi-turn info
gathering, context compaction, both specialist agents, an ineligible
refund, both approver outcomes (approve/deny), the general fallback for
uncategorized issues, and session isolation. All order IDs are seeded rows
from `db/seed_data.sql` — run `python -m db.init_db` first, then these can
be replayed exactly in the Customer Chat view.

---

## 1. Billing Inquiry — multi-turn gathering → Billing Agent

Exercises: `pipeline/info_gathering.py`, `pipeline/compaction.py`,
`agents/billing_agent.py`, DB-backed `lookup_invoice` / `check_payment_status`.

Order used: **ORD-1003** (Priya Nair, Smartwatch, ₹5,600, payment `pending`)

```
Customer: Hi, I have a question about one of my orders.

Bot: Sure — could you tell me a bit more about the issue, and which
     order it concerns?

Customer: I was charged for my smartwatch order but I'm not sure the
          payment actually went through. Order ID is ORD-1003.
```

Compacted after turn 2:

```json
{
  "issue_summary": "Customer is unsure whether payment for their smartwatch order went through.",
  "issue_category": "billing_issue",
  "order_id": "ORD-1003",
  "refund_amount": null,
  "customer_sentiment": "neutral",
  "info_complete": true,
  "missing_fields": []
}
```

```
Bot: I looked into order ORD-1003. Invoice for order ORD-1003: INR
     5,600.00 — Smartwatch. Payment status: pending. Let me know if
     you'd like more detail.
```

Graph run ends here — one turn, no waiting.

---

## 2. Refund Request — eligible, approved by the human reviewer

Exercises: `agents/refunds_agent.py` (files the approval, no auto-issue),
`pipeline/approval_graph.py` approve path, async resolution on session
resume.

Order used: **ORD-1001** (Aditi Rao, Wireless Headphones, ₹1,200, eligible)

```
Customer: I want to return my headphones.

Bot: Sorry to hear that — could you share the order ID and the refund
     amount you're expecting?

Customer: Order ORD-1001, I'd like a refund of ₹1200, they arrived damaged.
```

Compacted after turn 2:

```json
{
  "issue_summary": "Headphones arrived damaged; customer wants a refund.",
  "issue_category": "refund_request",
  "order_id": "ORD-1001",
  "refund_amount": 1200,
  "customer_sentiment": "neutral",
  "info_complete": true,
  "missing_fields": []
}
```

```
Bot: Your refund request of ₹1,200.00 for order ORD-1001 has been sent
     for manual review. Expect a resolution within about 24 hours —
     we'll update this chat as soon as it's decided, no need to wait here.
```

The customer-turn graph run ends here — completely normally, nothing blocked.

**Approver View:** a pending entry appears — `ORD-1001 — ₹1,200.00`,
reason "All refund requests require manual review before processing."
The approver clicks **Approve**. This triggers a brand-new,
independent graph invocation (`pipeline/approval_graph.py`).

**Customer re-enters the same session ID later** and sees the new
message already sitting in the history, as if it arrived while they
were away:

```
Bot: Update on your refund request for order ORD-1001: it's been
     approved. ₹1,200.00 has been refunded (confirmation
     REF-ORD-1001-8F3C2A).
```

---

## 3. Refund Request — ineligible order (rejected immediately, no approval filed)

Exercises: `check_refund_eligibility` returning `eligible=False`; confirms
the ineligible branch never creates a `PendingApproval`.

Order used: **ORD-1011** (Divya Kapoor, Electric Kettle, ₹6,200, marked final sale)

```
Customer: I need a refund for my electric kettle, order ORD-1011,
          ₹6200 — it's way too loud.
```

Enough detail is present in a single message this time, so compaction
happens on the first turn:

```json
{
  "issue_summary": "Customer wants a refund for a noisy electric kettle.",
  "issue_category": "refund_request",
  "order_id": "ORD-1011",
  "refund_amount": 6200,
  "customer_sentiment": "frustrated",
  "info_complete": true,
  "missing_fields": []
}
```

```
Bot: I'm sorry, but order ORD-1011 isn't eligible for a refund: Item
     marked as final sale.
```

No `PendingApproval` record is created — the Approver Queue never sees
this one. Graph run ends in one turn.

---

## 4. Refund Request — eligible, denied by the human reviewer

Exercises the other approver outcome: `pipeline/approval_graph.py` deny path.

Order used: **ORD-1009** (Meera Joshi, Gaming Monitor, ₹9,800, eligible)

```
Customer: Hey, my gaming monitor arrived with a cracked screen.

Bot: I'm sorry to hear that. Could you confirm the order ID and how
     much you'd like refunded?

Customer: Order ORD-1009. I paid ₹9800 and want a full refund.
```

```json
{
  "issue_summary": "Gaming monitor arrived with a cracked screen; customer wants a full refund.",
  "issue_category": "refund_request",
  "order_id": "ORD-1009",
  "refund_amount": 9800,
  "customer_sentiment": "frustrated",
  "info_complete": true,
  "missing_fields": []
}
```

```
Bot: Your refund request of ₹9,800.00 for order ORD-1009 has been sent
     for manual review. Expect a resolution within about 24 hours —
     we'll update this chat as soon as it's decided, no need to wait here.
```

**Approver View:** the reviewer inspects the same compacted ticket info
and clicks **Deny** instead.

**Customer returns to the session:**

```
Bot: Update on your refund request for order ORD-1009: after review,
     we're unable to approve this refund of ₹9,800.00.
```

---

## 5. General/Other Issue — fallback path, then a fresh session

Exercises the `unassigned` routing branch (no dedicated specialist agent)
and confirms **New Session** leaves no leakage between sessions.

```
Customer: I can't log into my account — it keeps saying invalid
          password even though I reset it twice.
```

```json
{
  "issue_summary": "Customer is locked out of their account after two password resets.",
  "issue_category": "account_issue",
  "order_id": null,
  "refund_amount": null,
  "customer_sentiment": "frustrated",
  "info_complete": true,
  "missing_fields": []
}
```

```
Bot: Thanks for the details — I've logged this and our support team
     will follow up with you soon.
```

There's no Billing or Refunds Agent for `account_issue` — routing sends
this straight to the generic fallback reply (`_general_support_node` in
`pipeline/graph.py`), and the graph ends in one turn.

**Now click "New Session"** in the sidebar: a brand-new session ID is
generated, the chat history is empty, and the Compacted Ticket Info panel
shows nothing — confirming this session shares no state with the one
above.
