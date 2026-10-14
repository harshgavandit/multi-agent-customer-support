-- Embedded database schema for the mocked tools (tools/mock_tools.py).
--
-- One table per remaining tool, joined through `orders` for shared
-- identity fields (customer_name, order_date):
--   invoices            -> lookup_invoice
--   payments            -> check_payment_status
--   refund_eligibility  -> check_refund_eligibility

DROP TABLE IF EXISTS refund_eligibility;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    order_id      TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    order_date    TEXT NOT NULL
);

CREATE TABLE invoices (
    order_id         TEXT PRIMARY KEY REFERENCES orders(order_id),
    amount           REAL NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'INR',
    item_description TEXT NOT NULL
);

CREATE TABLE payments (
    order_id   TEXT PRIMARY KEY REFERENCES orders(order_id),
    status     TEXT NOT NULL CHECK (status IN ('paid', 'pending', 'failed')),
    updated_at TEXT NOT NULL
);

CREATE TABLE refund_eligibility (
    order_id          TEXT PRIMARY KEY REFERENCES orders(order_id),
    eligible          INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    reason            TEXT NOT NULL,
    return_window_end TEXT NOT NULL
);
