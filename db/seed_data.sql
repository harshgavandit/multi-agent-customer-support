-- Sample dataset for demos. Deliberately memorable order IDs (ORD-1001..ORD-1012)
-- so a student can type one into the chat during a walkthrough.

INSERT INTO orders (order_id, customer_name, order_date) VALUES
    ('ORD-1001', 'Aditi Rao',     '2026-06-01'),
    ('ORD-1002', 'Rohan Mehta',   '2026-06-03'),
    ('ORD-1003', 'Priya Nair',    '2026-06-05'),
    ('ORD-1004', 'Karan Shah',    '2026-06-08'),
    ('ORD-1005', 'Sneha Iyer',    '2026-06-10'),
    ('ORD-1006', 'Vikram Singh',  '2026-06-13'),
    ('ORD-1007', 'Anjali Gupta',  '2026-06-16'),
    ('ORD-1008', 'Arjun Reddy',   '2026-06-19'),
    ('ORD-1009', 'Meera Joshi',   '2026-06-22'),
    ('ORD-1010', 'Rahul Verma',   '2026-06-25'),
    ('ORD-1011', 'Divya Kapoor',  '2026-06-28'),
    ('ORD-1012', 'Sanjay Kumar',  '2026-07-02');

INSERT INTO invoices (order_id, amount, currency, item_description) VALUES
    ('ORD-1001', 1200,  'INR', 'Wireless Headphones'),
    ('ORD-1002', 3400,  'INR', 'Office Chair'),
    ('ORD-1003', 5600,  'INR', 'Smartwatch'),
    ('ORD-1004', 850,   'INR', 'Phone Case'),
    ('ORD-1005', 12000, 'INR', 'Espresso Machine'),
    ('ORD-1006', 2200,  'INR', 'Bluetooth Speaker'),
    ('ORD-1007', 7600,  'INR', 'Air Purifier'),
    ('ORD-1008', 450,   'INR', 'USB-C Cable Pack'),
    ('ORD-1009', 9800,  'INR', 'Gaming Monitor'),
    ('ORD-1010', 3100,  'INR', 'Backpack'),
    ('ORD-1011', 6200,  'INR', 'Electric Kettle'),
    ('ORD-1012', 1800,  'INR', 'Desk Lamp');

INSERT INTO payments (order_id, status, updated_at) VALUES
    ('ORD-1001', 'paid',    '2026-06-01T10:15:00Z'),
    ('ORD-1002', 'paid',    '2026-06-03T09:40:00Z'),
    ('ORD-1003', 'pending', '2026-06-05T14:22:00Z'),
    ('ORD-1004', 'paid',    '2026-06-08T11:05:00Z'),
    ('ORD-1005', 'failed',  '2026-06-10T16:50:00Z'),
    ('ORD-1006', 'paid',    '2026-06-13T08:30:00Z'),
    ('ORD-1007', 'pending', '2026-06-16T13:10:00Z'),
    ('ORD-1008', 'paid',    '2026-06-19T12:00:00Z'),
    ('ORD-1009', 'paid',    '2026-06-22T17:45:00Z'),
    ('ORD-1010', 'failed',  '2026-06-25T09:15:00Z'),
    ('ORD-1011', 'paid',    '2026-06-28T15:35:00Z'),
    ('ORD-1012', 'pending', '2026-07-02T10:50:00Z');

INSERT INTO refund_eligibility (order_id, eligible, reason, return_window_end) VALUES
    ('ORD-1001', 1, 'Within the 30-day return window.',        '2026-07-01'),
    ('ORD-1002', 1, 'Within the 30-day return window.',        '2026-07-03'),
    ('ORD-1003', 1, 'Within the 30-day return window.',        '2026-07-05'),
    ('ORD-1004', 1, 'Within the 30-day return window.',        '2026-07-08'),
    ('ORD-1005', 0, 'Item marked as final sale.',               '2026-07-10'),
    ('ORD-1006', 1, 'Within the 30-day return window.',        '2026-07-13'),
    ('ORD-1007', 1, 'Within the 30-day return window.',        '2026-07-16'),
    ('ORD-1008', 0, 'Order is past the 30-day return window.', '2026-07-19'),
    ('ORD-1009', 1, 'Within the 30-day return window.',        '2026-07-22'),
    ('ORD-1010', 1, 'Within the 30-day return window.',        '2026-07-25'),
    ('ORD-1011', 0, 'Item marked as final sale.',               '2026-07-28'),
    ('ORD-1012', 1, 'Within the 30-day return window.',        '2026-08-01');
