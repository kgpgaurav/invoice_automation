# PS-1 Invoice Automation

Invoice-PDF intake, source verification, purchase-order matching and recorded financial decisions for the Zamp AI Solutions Associate PS-1 case study. Submitters track their own invoices; financial reviewers resolve exceptions and inspect the supporting records. Approval authorizes downstream payment processing. The app never executes a payment or sends vendor emails.

**Live application:** [invoiceautomation-seven.vercel.app](https://invoiceautomation-seven.vercel.app/)

[Submit an invoice](https://invoiceautomation-seven.vercel.app/?view=upload) · [Financial review](https://invoiceautomation-seven.vercel.app/?view=review) · [GitHub repository](https://github.com/kgpgaurav/invoice_automation)

## Deployment status

The frontend and API are deployed on Vercel, with Supabase PostgreSQL. Public checks on **16 November 2026** returned HTTP 200 for the application and these endpoints:

| Link                                                                                    | What it checks                                                       |
| --------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| [API health](https://invoiceautomation-seven.vercel.app/api/v1/healthz)                 | The API responds.                                                    |
| [Database readiness](https://invoiceautomation-seven.vercel.app/api/v1/readyz)          | The configured database and business migrations are ready.           |
| [Upload configuration](https://invoiceautomation-seven.vercel.app/api/v1/openai/config) | Submitter-supplied OpenAI mode, 4-MiB maximum and five-page maximum. |

**Processing prerequisite:** the deployment configuration starts the separate worker at zero instances. The operator must provision reviewed vendor/PO master records and deliberately activate the worker before an invoice can complete processing. A guarded hosted master-data provisioning command remains pending. Health/readiness checks do not establish worker availability, OpenAI credit or a successful hosted invoice run. The tutorial below describes the implemented workflow once those prerequisites are met; see [deployment instructions](docs/DEPLOYMENT.md).

## Access and credentials

Ask the submission owner privately for your assigned **workspace access token**. The case-study profile has three individual submitter identities and one financial reviewer. There is no public signup; sharing a token shares that identity's permissions and invoice visibility.

| Role               | Available screens                                                       | OpenAI API key needed?             |
| ------------------ | ----------------------------------------------------------------------- | ---------------------------------- |
| Invoice submitter  | Process Invoice, My Invoices and their own invoice details/PDF/timeline | Yes, their own key for extraction. |
| Financial reviewer | Review Queue, Invoice History, Purchase Orders and Overview             | No.                                |

The workspace token identifies you inside this app. Your OpenAI API key authorizes extraction charges on your OpenAI account; it does not grant reviewer access. Access tokens, provider keys and database credentials are never published in this README.

## Tutorial: submit an invoice

1. Open the [live application](https://invoiceautomation-seven.vercel.app/). In **Workspace access token**, enter your assigned submitter token and click **Connect**. If needed, open **Connect workspace** in the top bar.
2. Open **Process Invoice**. In **Your OpenAI connection**, enter your own OpenAI API key and click **Connect OpenAI**. Choose an **Invoice extraction model** from the offered list. Only models both listed for your account and supported by the pipeline are offered; listing does not guarantee Responses permission or available credit.
3. Choose one invoice PDF: **at most 4 MiB (4,194,304 bytes), one to five pages, unencrypted**. The upload form displays the active server limit. The normal local API default is 12 MiB. Only INR invoices can authorize financial approval; other printed currencies are preserved for review.
4. Click **Process invoice**. The API stores the original PDF and queues a durable run. The separate worker performs extraction, evidence checks and financial validation. An upload receipt or queued status is not an approval.
5. Follow the invoice's **Processing timeline** and read its outcome and explanation. Its detail page includes the source PDF, extracted information and recorded usage where available. **My Invoices** shows only your own submissions and supports search and status/decision filters.
6. If the invoice **Needs review**, a financial reviewer handles the exception. Submitters cannot select review candidates, inspect company PO balances or approve an exception themselves.
7. Use **Disconnect OpenAI** when finished. Use the workspace access controls to disconnect from the app.

You can process multiple invoices with one OpenAI connection in the same tab for up to 24 hours; you do not need a new key for every invoice. Refreshing, opening a new tab, disconnecting or expiry requires reconnecting for new uploads. Reuse the same OpenAI key if it is still valid. Workspace access also needs reconnecting after refresh because credentials are held in tab memory.

OpenAI keys are temporarily encrypted on the server and are not saved in browser storage. Closing or refreshing a tab does not revoke the connection already bound to submitted jobs. Explicit disconnect revokes it and erases its active ciphertext; already dispatched calls can still finish and incur charges. Extraction charges can occur even when the final financial outcome is review or rejection.

## Tutorial: review an exception

1. Open [Financial review](https://invoiceautomation-seven.vercel.app/?view=review) and connect with your assigned **financial-reviewer token**. No OpenAI key is required. To test both roles, use separate browser tabs and each role's own token.
2. Open **Review Queue** and select an invoice. Inspect the PDF, recorded findings, decision explanation and purchase-order context. **Invoice History** includes workspace invoices; **Purchase Orders** exposes current balances and approved allocations; **Overview** summarizes recorded activity.
3. In the **Human review** panel, choose one of the actions actually offered for that exception. For a missing or ambiguous PO, choose **Select PO & resume**, compare the offered candidates, and select the supporting PO.
4. Enter a **Review rationale**, then click **Confirm selection & resume**. The action is saved and the same workflow thread resumes. Current vendor/PO state, duplicate identity and available funds are rechecked before any approval is posted. Observe the resulting decision rather than treating the selection itself as approval.
5. Where offered, **Reject invoice** records a rejection; **Request source information & stop** records the information request and stops that run. It does not send an email or automatically collect a corrected document.

A reviewer cannot waive a PO spending cap, price/quantity checks or missing critical evidence. An invoice may be submitted without a PO reference, but automatic approval requires a verified supporting PO. An unresolved match remains in review. Corrected source documents and authorized upstream master-data amendments are handled outside the review form; approved duplicates cannot receive another allocation.

## Understand the result

Job progress and financial decisions are separate:

| Display/state                 | Meaning                                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------------------- |
| Queued                        | The PDF is stored and waiting for a worker.                                                    |
| Running                       | A worker is processing the run.                                                                |
| Waiting review / Needs review | An exception needs an authorized financial response; no PO funds are reserved.                 |
| Completed                     | The run finished. Read its financial decision and reason for the outcome.                      |
| Approved                      | Validation succeeded and the approval ledger/PO allocation committed. No payment was executed. |
| Rejected                      | A recorded business-policy failure or authorized reviewer rejection.                           |
| Failed                        | A technical processing failure; this is not a financial rejection.                             |

Financial calculations use `Decimal` and typed tolerances. Source verification, vendor/PO matching, duplicate checks and the approval transaction determine authorization. Model-generated confidence or verification claims cannot grant approval. Approval rechecks and PO allocation occur atomically under PostgreSQL locks and uniqueness constraints.

## Guided case-study scenarios

Ask the submission owner for the synthetic PDFs and confirm that their matching masters are provisioned. These cases depend on prior records; they are not independent public one-click examples. Local PDFs are generated by the [disposable demo tool](docs/RUNNING.md). The shared-mode scenario gallery is explanatory; it is hidden in role mode and does not download, seed or execute cases.

| Case                         | Procedure and expected behavior with the prepared data                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| H1 — Clean invoice           | Process `H1.pdf`: approve INR 11,800 once against its supporting PO.                                                                                                                       |
| E1 — Partial-invoice overrun | Process and approve `E1-prior.pdf` for INR 70,000 first. Then submit `E1.pdf` for INR 35,000 against INR 30,000 remaining: hold the INR 5,000 excess.                                      |
| E2 — Missing/ambiguous PO    | Submit `E2.pdf`, switch to finance, select a substantiated offered PO and resume. Approval still depends on all current checks.                                                            |
| E3 — Duplicate               | Approve H1 first, then submit `E3-text.pdf`: reject the reliably grounded duplicate without a second allocation. `E3-scan.pdf` remains in review when its identity cannot be corroborated. |
| E4 — Bank mismatch           | Submit `E4.pdf`: require independent verification of the changed bank suffix. This is a change warning, not a fraud finding.                                                               |

H2's justified INR 2 rounding fixture remains unavailable. An unexplained discrepancy must not be forced into an approval. Mock local workspaces accept only their own generated PDFs and clearly label prepared extraction; they never call OpenAI or classify unrelated PDFs as invoices.

## Troubleshooting

| Symptom                                       | Next step                                                                                                                                                            |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Access rejected / HTTP 401                    | Re-enter your assigned workspace token. An OpenAI key is not a workspace token.                                                                                      |
| Screen unavailable / HTTP 403                 | Check your assigned role; submitters cannot use finance features.                                                                                                    |
| Run not found / HTTP 404                      | Confirm the run belongs to your identity. Other submitters' runs are deliberately hidden.                                                                            |
| Process button disabled                       | Wait for upload configuration, connect your OpenAI key, select a model and choose a valid PDF.                                                                       |
| HTTP 413 / HTTP 422                           | Follow the displayed upload error: reduce file size or check PDF validity, page count, encryption and required fields. No extraction is started for rejected intake. |
| Run stays Queued                              | Ask the operator to check worker activation, logs and database access. API readiness alone does not prove a worker is running.                                       |
| OpenAI connection expired / processing failed | Read the recorded reason. Reconnect for new uploads if needed; do not repeatedly submit paid runs without addressing the cause. Original PDFs remain stored.         |
| Empty review queue or PO register             | A new workspace starts empty. Confirm actual submissions and reviewed master-data provisioning with the operator.                                                    |

## Architecture and local development

| Component                       | Implementation                                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Frontend                        | React, TypeScript, Vite, Tailwind CSS, authenticated PDF preview                                        |
| API                             | FastAPI, Pydantic, SQLAlchemy and Alembic                                                               |
| Execution                       | Separate worker, PostgreSQL durable queue, leases/heartbeats and ownership fencing                      |
| Workflow                        | LangGraph with durable PostgreSQL checkpoints and human-review interrupts                               |
| Documents and financial history | Private PostgreSQL PDF attachments, persisted events and immutable approval records                     |
| Extraction                      | OpenAI Responses API and Structured Outputs; local PyMuPDF evidence checks                              |
| Hosting                         | Vercel frontend/API Services and worker Daemon; Supabase PostgreSQL with session-preserving connections |

The worker is a continuously running backend process, not a person or a one-time deployment step. It must remain active while queued uploads and review resumes need processing. The API and worker share the database and stable server encryption secret. Free hosting quotas and hosted recovery behavior require operator monitoring.

For local setup, prerequisites and the separate API/worker/frontend commands, follow [RUNNING.md](docs/RUNNING.md). Role mode uses `ACCESS_MODE=roles` and the compatibility setting `OPENAI_CREDENTIAL_MODE=reviewer`; that name refers to submitter-owned extraction credentials, not a requirement for finance to supply a key. Existing explicitly labelled server-key and mock workspaces are separate local configurations.

## Scope, verification and next work

The private demonstration uses three stable submitter slots and one reviewer. API permissions and invoice/provider-session ownership are enforced server-side. The operator assigns each token privately and retains its identity mapping across restarts. There is no public account-registration or token-delivery service.

Proposed stronger authentication is **not implemented**: verified individual sign-in and invitations through OIDC or email login, stable user IDs with server-assigned roles, secure HttpOnly/Secure/SameSite session cookies, expiry/revocation, CSRF protection for cookie writes, reviewer MFA, and authentication audit/rate-limit controls. These require a separate implementation while preserving existing ownership checks. See [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) and [session-management guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Remaining work includes the guarded hosted master-data provisioning command and hosted end-to-end/recovery rehearsal, broader real-layout/scanned invoice evaluation, and measured billed costs. Policy editing/endpoints, re-evaluation and payment-ready CSV export remain planned. H2 is not an implemented rounding demonstration. Payments, automated vendor emails, FX conversion and ERP writes are outside scope.

Prior backend, concurrency, migration, role/browser and explicitly authorized live-extraction results are recorded in [DEVELOPMENT.md](docs/DEVELOPMENT.md) and [PREDEPLOY.md](docs/PREDEPLOY.md). Those dated local/predeployment results are separate from the public HTTP checks above; they do not establish that every scenario has run on this hosted deployment.

## Project documentation

| Document                                  | Purpose                                                                                                                      |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| [SPEC.md](SPEC.md)                        | Canonical product, financial, data, workflow and API contract; historical draft status text is not an implementation report. |
| [PROGRESS.md](PROGRESS.md)                | Milestone history and remaining work.                                                                                        |
| [DECISIONS.md](docs/DECISIONS.md)         | Recorded implementation decisions and unresolved contracts.                                                                  |
| [RUNNING.md](docs/RUNNING.md)             | Local installation, demo commands and fixture order.                                                                         |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md)       | Operator configuration, database/worker activation gates and hosting limits.                                                 |
| [ROLE_ACCESS.md](docs/ROLE_ACCESS.md)     | Submitter/reviewer permissions and credential ownership.                                                                     |
| [REVIEWER_KEYS.md](docs/REVIEWER_KEYS.md) | Temporary OpenAI credential handling and per-run binding.                                                                    |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md)     | Exact verification commands, measurements and limitations.                                                                   |
| [PREDEPLOY.md](docs/PREDEPLOY.md)         | Earlier endpoint/role matrix, browser checks and controlled live smoke.                                                      |

Earlier design documents under [docs/archive](docs/archive/README.md) are historical references. Where contracts disagree, follow `SPEC.md`. Older progress/deployment records predate the live URL and retain their original measurements and scope.
