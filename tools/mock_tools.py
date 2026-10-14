"""Concept: Tool Usage (Section 3.4 of the spec).

Every function here does a real data lookup against the embedded SQLite
database (db/) — not a hardcoded fabrication. Each opens a read-only
connection (db.connection.get_read_only_connection): the connection itself
is opened via SQLite's `mode=ro` URI, so any attempted write through it
fails at the SQLite level, not just by convention. See db/connection.py
and the README for the full explanation of what "read-only" does and
doesn't guarantee on an embedded, single-file database.

There is no `issue_refund` tool. No refund is ever issued by an agent —
every eligible refund request goes to manual review (see
agents/refunds_agent.py and pipeline/approval_graph.py).
"""
from typing import Tuple

from db.connection import get_read_only_connection


def lookup_invoice(order_id: str) -> dict:
    """Mocked invoice lookup for the Billing Agent."""
    conn = get_read_only_connection()
    try:
        row = conn.execute(
            "SELECT amount, currency, item_description FROM invoices WHERE order_id = ?",
            (order_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"order_id": order_id, "found": False}

    return {
        "order_id": order_id,
        "found": True,
        "amount": row["amount"],
        "currency": row["currency"],
        "description": f"Invoice for order {order_id}: {row['currency']} {row['amount']:,.2f} — {row['item_description']}.",
    }


def check_payment_status(order_id: str) -> dict:
    """Mocked payment status lookup for the Billing Agent."""
    conn = get_read_only_connection()
    try:
        row = conn.execute(
            "SELECT status FROM payments WHERE order_id = ?",
            (order_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"order_id": order_id, "found": False, "status": "unknown"}

    return {"order_id": order_id, "found": True, "status": row["status"]}


def check_refund_eligibility(order_id: str) -> Tuple[bool, str]:
    """Mocked eligibility check for the Refunds Agent."""
    conn = get_read_only_connection()
    try:
        row = conn.execute(
            "SELECT eligible, reason FROM refund_eligibility WHERE order_id = ?",
            (order_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return False, "We couldn't find that order in our records."

    return bool(row["eligible"]), row["reason"]
