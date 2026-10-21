# Multi-Agent Customer Support

A customer support chat app for billing questions and refund requests.

[Try the app](https://harsh-multi-agent-customer-support.streamlit.app/)

Customers describe their problem in the chat. The app asks for missing details, such as an order ID or refund amount, then passes the request to the billing or refunds agent.

- **Billing:** looks up the order and shows its invoice details and payment status.
- **Refunds:** checks whether the order is eligible and sends eligible requests for manual review.
- **Approver Queue:** lets a reviewer approve or deny a refund. The decision appears in the customer's chat.

Customers can leave while a refund is being reviewed and return using their session ID. Starting a new session opens a separate conversation.

The app uses sample orders. Refund confirmations are simulated, and no money is transferred. Chat history and pending approvals are kept in memory and are lost when the app server restarts.
