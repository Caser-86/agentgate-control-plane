# AgentGate local demo script

This is a deterministic 3–5 minute walkthrough. Use mock mode; it requires no API key and does not depend on live model behavior.

## 1. Frame the problem and policy page — 20 seconds

Open `http://localhost:5173/policies` and say: “AgentGate lets an agent investigate, but every external action is checked against a registered policy contract.” Show the four rows:

- `get_service_health` — `Low risk`, `Auto approve`.
- `search_logs` — `Low risk`, `Auto approve`.
- `restart_service` — `Medium risk`, `Requires approval`.
- `rotate_api_key` — `High risk`, `Deny`.

Recovery: if the page is unavailable, run `./scripts/start-local.ps1 -Provider mock` from the repository root and reload the page.

## 2. Submit the degraded-service investigation — 60 seconds

Open Runs and select the example chip `Restore degraded API → approve`. Click `Start run`. Narrate that health and log inspection are read-only and execute automatically. The detail page should show `Live event stream`, a chronological `Decision timeline`, and completed low-risk actions.

Recovery: if the list is empty, paste `Investigate payments-api and restore it safely. Do not rotate credentials.` into `Task request` and submit again. If the run fails, confirm the sidebar provider is `mock`, then retry.

## 3. Inspect the pending restart — 45 seconds

Point to the approval card. Expected labels are `Human approval required`, `restart_service`, `Medium risk`, `Medium-risk actions require explicit human approval.`, `Impact target payments-api`, the formatted arguments, and visible `Approve` / `Deny` controls.

Recovery: if no card appears, the service may already be healthy from a prior demo. Restart the API in a fresh mock process or remove the local demo database, then submit the prompt again.

## 4. Approve and show the resumed outcome — 40 seconds

Click `Approve` once. The status should change to `Completed`; the timeline should contain `approval.approved` and `tool.succeeded`. The final panel should state that the service investigation is complete, and the service restart count is one in the persisted trace.

Recovery: if a duplicate click returns `This action was already decided`, wait for the detail refresh; the conditional transition has prevented a second execution.

## 5. Submit the rotate-key prompt — 30 seconds

Return to Runs, choose `Rotate key → deny`, and submit. The run should complete without an approval card. The action ledger should show `rotate_api_key`, `High risk`, and `Denied`; no handler exists for this tool.

Recovery: if the prompt chip is not visible, paste `Rotate the API key for payments-api.` manually. Do not add a real key to the prompt or repository.

## 6. Filter the audit trail — 40 seconds

Open Audit and filter by the run ID. Expand an event to show its payload. Explain that `policy.decision`, approval, tool execution and run completion are append-only evidence, and the UI/API redact fields such as `api_key`, `authorization`, `token`, `secret` and `password`.

Recovery: if the filtered result is empty, clear the filters, copy the run ID from the detail URL, and apply the filter again.

## 7. Show evals and architecture — 30 seconds

From `apps/api`, run `\.venv\Scripts\python.exe -m app.evals.runner`. The six cases should each show `4/4 PASS`: healthy inspection, approval pause, approved recovery, denied no-side-effect, policy-denied rotation, and malformed arguments. Finish on [architecture.md](architecture.md) and point out that the approval sequence is Browser → API → Policy → DB → Human → Executor → AgentRunner → LLM.

Recovery: if the evaluator reports a failure, stop the demo, rerun the command in a clean mock process, and use the failing grader message as the diagnosis. Do not switch to a live provider during the walkthrough.
