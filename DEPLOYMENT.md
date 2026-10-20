# Streamlit Community Cloud deployment

## Deployment status

Deployed on 20 October 2026.

Live URL: https://harsh-multi-agent-customer-support.streamlit.app/

The app was started from the public GitHub repository with Python 3.14.8 and
Streamlit 1.66.0. Model and Redis secrets were configured through Advanced
settings; no credentials were added to Git. Hosted browser checks and their
scope are retained in `verification/HOSTED_VERIFICATION.md`.

## App settings

| Setting | Value |
|---|---|
| Hosting | Streamlit Community Cloud |
| Repository | `harshgavandit/multi-agent-customer-support` |
| Branch | `main` |
| Main file path | `streamlit_app.py` |
| Python | `3.14` (matches the verified local/CI runtime; select in Advanced settings) |
| Subdomain | `harsh-multi-agent-customer-support` |

Open https://share.streamlit.io/, sign in, and choose Create app. Select the
repository, branch and main file above. In Advanced settings, select Python
and supply the app secrets before deployment.

## Secrets

`.streamlit/secrets.toml` is an ignored local file prepared from the existing
`.env` credentials with the user's permission. Do not commit or share it. Paste
its contents into this app's Secrets field in Streamlit Advanced settings.
The hosted namespace is `customer-support-cloud` to separate its counters from
local development. `.streamlit/secrets.toml.example` contains placeholders only.

Root-level Streamlit secrets become environment variables, so the existing
configuration and LiteLLM wrapper can use them without application changes.
Never paste credential-bearing configuration into chat, issues or public docs.

## Verification checklist

1. Wait for installation and startup to finish and retain the actual app URL.
2. Submit a vague issue and verify a clarification response.
3. Request invoice/payment details for ORD-1003; expect INR 5,600 and pending.
4. Request an INR 2,200 refund for ORD-1006; verify manual review is queued.
5. Open Approver Queue and resolve the synthetic request.
6. Return to chat, start a new session and resume the original session ID.
7. Confirm the decision is restored and an ineligible ORD-1005 refund is rejected.
8. Verify Redis admission and safe error handling, and retain hosted evidence.

## Demo scope

The public app is a demonstration: no real money moves. Approver Queue has no
login/role protection; do not use real customer information. Sessions and
approvals live in one process and are lost when that process restarts or sleeps.
The SQLite reference database is bootstrapped from the committed seed scripts.

## Official documentation

- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
