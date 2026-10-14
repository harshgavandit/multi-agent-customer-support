# Verification report

Verified on 2026-10-14 (Asia/Kolkata), using Windows and Python 3.14.6.

## Outcome

- **33 automated tests passed.** `unit_tests.txt` contains the final test output.
- **11 real-service checks passed; 0 failed.** `live_checks.json` contains timings and safe results.
- Real provider: `gpt-4o-mini` through LiteLLM. The model returned valid JSON and drove the information-gathering and compaction nodes.
- Real Upstash Redis: authenticated PING, atomic admission, concurrency, limit exhaustion, expiry, graph-entry rejection, and shared model-budget rejection verified.
- Dependency consistency passed (`python -m pip check`); modified source and test files compile successfully.
- Credential scan passed: configured secret values do not appear in source, documentation, test logs, or JSON reports. `.env` is ignored and `.env.example` uses placeholders.

## Real-service checks

| Check | Result | Duration |
|---|---|---|
| redis_ping | PASS | 0.083 s |
| redis_limit_and_expiry | PASS | 2.262 s |
| redis_concurrent_admission | PASS | 0.051 s |
| application_rate_limit_admission | PASS | 0.047 s |
| global_model_rate_limit_admission | PASS | 0.086 s |
| real_model_json_completion | PASS | 2.765 s |
| multi_turn_billing_resume_isolation | PASS | 4.25 s |
| refund_approval_and_duplicate_protection | PASS | 5.098 s |
| refund_denial | PASS | 2.153 s |
| ineligible_refund | PASS | 2.213 s |
| general_support | PASS | 2.632 s |

The concurrency probe sent 8 concurrent requests with a limit of 3. Redis
admitted exactly 3 and blocked 5. A separate 2-request / 2-second window
blocked the third request, then admitted a request after expiry. The live
model-budget rejection primed a separate Redis namespace and verified the
provider was never called after admission was denied.

## Automated coverage

The tests run the actual LangGraph workflows and SQLite reference tools with
model responses replaced by deterministic fixtures. They cover clarification,
billing, unknown orders, refund eligibility, human approval/denial, resuming a
session, independent new sessions, duplicated requests and decisions,
concurrent approval clicks, rollback after model errors, malformed JSON,
invalid ticket fields and non-positive/non-finite amounts. Rate-limit tests
cover safe Redis error handling, hashed session keys, request rejection and
global model gating.

Three Streamlit AppTest tests exercise the rendered Customer Chat and Approver
Queue views, including Approve, Deny, New Session, Resume, and safe provider /
Redis / rate-limit messages. The initial sandboxed UI run stalled; the final
suite was run outside the sandbox and passed in the retained test output.

## Live browser evidence

The final code was verified in the running Streamlit app with the real model
and Redis. A synthetic ORD-1006 / INR 2,200 refund was submitted in Customer
Chat, displayed in Approver Queue, and resolved with Approve. The pending
queue became empty. New Session produced a new ID and empty history; Resume
restored the original session and its approval outcome. The screenshot is
`browser_refund_resumed.jpg`; the approval confirmation is simulated.

The browser's narrow viewport initially hid the sidebar, and attempted
Resume clicks did not submit. Opening the sidebar made the controls reachable.
The final resume UI uses a Streamlit form and a callback that consumes the
submitted ID before the render. Both AppTest and the actual browser restore
flow pass. No further workaround or additional service is required.

## Codebase and changes

This is a Streamlit teaching POC, with two LangGraph flows. The customer flow
uses a model to gather information, another model call to compact the ticket,
and deterministic routing to SQLite-backed billing/refund tools. The separate
approval graph updates the same process's session store after a human decision.

The supplied credentials were in `.env.example`, but configuration loaded
`.env`; there was no Redis integration. The credentials are now in `.env`, the
example is sanitized, and configuration paths resolve relative to the project.
Atomic Upstash limits enforce 10 customer turns per session and 60 model calls
across all sessions per 60-second window by default.

Failed turns previously modified shared conversation lists before successful
completion. Session access now returns copies and customer/approval operations
serialize per session. Pending refund requests are not duplicated, and only a
pending approval can be resolved. Provider exceptions are replaced with safe
messages in the UI. Ticket and positive refund amount validation guard tools.

The first real-model billing test failed because the model kept seeking more
context after an explicit order/invoice/payment lookup request. The prompt was
clarified and the complete real-service run then passed. LiteLLM uses its bundled
model-cost map at startup to avoid an unnecessary remote metadata fetch.

## Scope and limits

- Session and approval data remain in memory in one server process. Restarting
  the server loses these records; separate server processes do not share them.
- Redis stores expiring rate-limit counters only, not conversations or approvals.
- Limits apply to sessions and the shared configured model budget, not
  authenticated users. There is no login or protected approver role.
- Refund eligibility is seeded demo data. It uses the stored eligibility flag
  rather than today's date; there is no integration with an order platform.
- Approval produces a simulated confirmation message; no funds are transferred.
- General support follow-up is a demo message, not an external support queue.
- The existing reference SQLite database was inspected without resetting it.
- This report records the local functional verification. GitHub publication and its commit are verified separately when the repository is created.
- The original `documentation.pdf` predates these changes; current operational
  instructions are in `README.md` and this report.
- Actual secrets appeared in the initial inspection output before the example
  was sanitized. Rotate the OpenAI key and Redis token, then update `.env`.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.verify_live
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

The real-service script makes small billable model requests. It uses unique,
expiring Redis namespaces and never flushes the database. Exact installed
package versions are retained in `requirements-lock.txt`.
