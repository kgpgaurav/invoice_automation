# Five-minute invoice-to-decision demonstration

Prepared 18 November 2026 against SPEC §§4.3, 5.1 and 5.3, the current README and the implemented synthetic fixtures. This is a recording plan, not a report that new live runs have been executed.

Show **H1 live → E2 live with finance handoff → E1 live → history/overview**. These demonstrate straight-through processing, a recoverable business exception and a hard financial boundary. Keep E3 and E4 ready for the interview. The assignment requires at least one live edge case; do not rush through four at the expense of an understandable end-to-end run.

## Prepare before recording

1. Use a dedicated demonstration workspace with synthetic vendor/PO masters. Rehearse in a different disposable workspace: approving H1 consumes its invoice identity and PO balance. Do not reset shared, hosted or personal history to prepare a recording. The fixture generator is `backend/scripts/demo_fixtures.py`; see [RUNNING.md](RUNNING.md) for workspace creation and separate API/worker startup.
2. Confirm the **worker is active**, the API and worker use the same database/configuration, and real OpenAI extraction succeeds in a complete rehearsal. A deployed entry page or successful readiness check alone does not establish this. Current deployment documentation leaves hosted worker/master-data acceptance open. If hosted processing is not ready, record the genuinely executing local version and describe it as local.
3. Use the personal-key role workspace (`--mode reviewer --roles`), not `--mode mock`, for the submission video. Open two tabs: **submitter**, already authenticated with OpenAI connected and a supported model selected; **financial reviewer**, already authenticated with the reviewer token. Finance does not need an OpenAI key. Avoid refreshing these tabs because their capabilities are held in tab memory.
4. Before recording, genuinely process `E1-prior.pdf` to approval in the recording workspace. Confirm `PO-PARTIAL` has a ₹100,000 cap, ₹70,000 committed and ₹30,000 available. Clearly describe this as an earlier invoice, not processing occurring during the video. Do not process H1, E2 or E1 in that recording workspace yet.
5. Have `H1.pdf`, `E2.pdf` and `E1.pdf` from that workspace ready in a convenient folder. They are synthetic inputs; the extraction and workflow should execute live. Use the app's displayed PDF limits: the Vercel profile is 4 MiB, one to five pages, unencrypted. Local defaults allow 12 MiB.
6. For E2, prepare the procurement context that tells finance which PO really supports the invoice. The generated two candidates both fit; a larger balance alone cannot establish the correct PO. Any supplemental demo confirmation must be clearly synthetic. If no supporting information exists, demonstrate **Request source information & stop** instead of guessing a PO.
7. Hide notifications, developer tools, environment files and credentials. Show the connected state/model without exposing the key or access tokens. Keep the cursor visible and browser zoom readable. Record one continuous take with narration during real processing waits; do not accelerate, conceal a failure or relabel mock/cached extraction as live.

## 0:00–0:25 — Explain the business outcome

**Show:** submitter tab, **Submit invoice**, then the synthetic H1 PDF in the picker or preview.

**Say:**

> “This is an accounts-payable workflow that turns a vendor PDF into an approval, a review request or a rejection, with a reason and a processing record. I'll show a clean invoice and two exceptions. These invoices and purchase orders are synthetic; OpenAI extraction and the workflow execute live.”

Only use the last sentence when the recording really uses live extraction.

## 0:25–1:35 — H1: a genuine clean approval

**Show:** choose `H1.pdf` → **Submit invoice** → processing timeline → extracted information and decision. Briefly switch to finance → **Purchase orders** → `PO-001` and its approved allocation.

**Say while it runs:**

> “The API stores the original PDF and queues the work. A separate background process extracts the fields with OpenAI, checks the source evidence, then checks the vendor, invoice identity, purchase order, line arithmetic, tax and available funds. These progress updates come from saved processing events.”
>
> “Here, ten units at ₹1,000 give ₹10,000 net. The printed 18% tax is ₹1,800, making ₹11,800. The supporting PO starts with ₹50,000 available. The approved allocation is ₹11,800, leaving ₹38,200.”
>
> “The model extracts information; deterministic Python rules authorize the decision. Approved means ready for downstream payment processing. No money has moved.”

**Verify on screen:** source/model and recorded requests identify the real extraction; the decision is approved; one ₹11,800 allocation exists. Read actual timing and estimated API cost if useful; never promise a fixed latency or claim the estimate is the billed amount. The balances above assume a fresh H1 PO.

## 1:35–3:15 — E2: ambiguous purchase order and human handoff

**Show:** submitter uploads `E2.pdf` → wait for **Needs review** → switch to finance **Review queue** → select `REVIEW-001` labelled **Choose purchase order** → inspect the PDF and both offered POs.

**Say:**

> “This invoice has no PO reference. Two open orders belong to the same vendor, and either has enough funds. Amount similarity does not prove which purchase it relates to, so automatic approval stops.”
>
> “The submitter sees the explanation, while finance sees the purchase-order choices. In this prepared scenario, procurement has confirmed PO-SELECT-001. I record that basis, select the supporting order and resume.”

Only claim procurement confirmation if the prepared context actually supplies it. Use a rationale that describes that context, not “it has enough money.”

**Do:** select `PO-SELECT-001`, enter the supported **Review rationale**, choose **Select PO & resume** where required, and click **Confirm selection & resume**. Watch the resumed result; keep the same run selected. Open the timeline or full invoice record if needed.

**Say:**

> “This resumes the saved workflow; selecting a PO does not itself approve the invoice. The system rechecks current vendor and PO state, duplicates and remaining funds before it commits. Here the checks pass, so ₹11,800 is allocated against the ₹25,000 order, leaving ₹13,200.”

If a current check fails, explain the actual result rather than forcing the scripted approval. Do not select a candidate automatically or imply finance can waive a spending limit.

## 3:15–4:20 — E1: partial invoicing exceeds the remaining balance

**Show:** finance **Purchase orders** → `PO-PARTIAL`, including the earlier ₹70,000 allocation. Switch to submitter → upload `E1.pdf`. Return to finance after it reaches review; show the explanation and unchanged allocation/balance.

**Say:**

> “This is a ₹100,000 purchase order, but an earlier invoice has already used ₹70,000. Only ₹30,000 remains. The new invoice requests ₹35,000.”
>
> “It looks acceptable if we compare it only with the original order value. Cumulative matching catches the ₹5,000 excess. The invoice needs review, and no additional funds are allocated or reserved.”
>
> “Finance cannot click through this cap. It needs a corrected invoice or an authorized upstream PO amendment; that amendment is outside this review screen.”

**Verify:** ₹100,000 − ₹70,000 = ₹30,000; ₹35,000 − ₹30,000 = ₹5,000 excess. The new run has no approval allocation, and committed spend stays ₹70,000. This invoice has zero tax in the fixture; do not reuse H1's 18% calculation here.

## 4:20–5:00 — Show visibility and close

**Show:** finance **Invoice history**, with approved and review outcomes → **Overview** → briefly expand **Evidence & audit metadata** on a real run if time remains. Keep extra technical detail secondary.

**Say:**

> “History keeps each invoice, its status and its explanation. The overview reports processing measures, review workload, estimated API costs where recorded, and potential PO overruns flagged. The ₹5,000 is an overrun detected, not a claim of money saved.”
>
> “The result is automation for clear invoices, a controlled handoff for ambiguity, and a hard stop before overspending. Every approval has a recorded allocation; the application does not execute payments or send vendor emails.”

Stop by five minutes. If rehearsed model latency leaves insufficient time for E1, complete H1 and E2 live and use the remaining time for history and a clearly identified earlier E1 record. Do not present that earlier run as a new live execution. Keep all four cases available for the follow-up interview.

## The four non-trivial edge cases to discuss

| Case | Prepared input and dependency | Expected outcome | Business judgment demonstrated |
| --- | --- | --- | --- |
| **E1 — Cumulative partial-invoice overrun** | `E1-prior.pdf` approved for ₹70,000, then `E1.pdf` asks ₹35,000 against a ₹100,000 PO | `NEEDS_REVIEW`; ₹30,000 available, ₹5,000 excess, no new allocation | An invoice can be below the original PO value yet exceed its remaining funds. Check committed history, not just the face value. |
| **E2 — Missing reference with multiple plausible POs** | `E2.pdf`, ₹11,800, no printed reference; `PO-SELECT-001` and `PO-SELECT-002` both belong to the vendor | `NEEDS_REVIEW`; finance supplies a justified selection, then the same workflow revalidates before any approval | Ranking candidates is not evidence of authorization. Human context resolves ambiguity without bypassing financial checks. |
| **E3 — Same business invoice, different PDF/format** | Approve H1's `INV-001` first, then upload `E3-text.pdf` with `INV 001`, same verified vendor | `REJECTED` with `DUPLICATE_APPROVED` when identity is reliably grounded; no second allocation | File hashes alone miss resaved or reformatted duplicates. Normalize the invoice identifier conservatively and scope it to the verified vendor. |
| **E4 — Correct amounts, changed bank suffix** | `E4.pdf`, invoice `BANK-001`; printed suffix `9876`, verified vendor suffix `1234`; enough PO funds remain | `NEEDS_REVIEW` with `BANK_MISMATCH`; no approval allocation | Passing monetary checks does not establish safe payment details. Require independent verification; a discrepancy is not proof of fraud. |

### Optional interview demonstrations and honest boundaries

- **E3 scanned variant:** `E3-scan.pdf` is an image-only duplicate candidate. The current conservative path holds it for review when local evidence cannot corroborate identity. Say that clearly. Do not promise automatic rejection simply because the visual model read a plausible number.
- **E4 action:** where offered, request source information and stop. The app records that request; it does not email the vendor, amend bank details or provide a “bank verified, approve anyway” shortcut.
- **Concurrent approvals / crash recovery:** discuss the tested durable queue, ownership fencing and atomic PO/ledger transaction if asked. Explain that the current PO balance is re-read under a database lock, and invoice uniqueness prevents a second financial allocation. Do not claim that every external model call is exactly once or free of duplicate billing after a crash.
- **H2 rounding:** do not include the ₹2 rounding happy path. Its complete arithmetic justification is unresolved, and no valid implemented H2 demonstration exists.
- **Unbuilt functionality:** do not show or promise payment-ready CSV export, editable policy screens, re-evaluation, ERP writes or email delivery. Export/policy/re-evaluation are still planned; payments and actual emails are outside scope.
- **Impact:** explain what the workflow measures, without inventing percentage time savings, production accuracy, fraud prevented or audited ROI. Real-layout/scanned evaluation is still limited.

## Interview answers in one sentence

- **Why use an LLM?** “Vendor layouts vary, so it extracts a structured document; local verification and explicit rules control authorization.”
- **Why not auto-match the closest PO?** “Similarity suggests candidates, but it cannot establish which purchase was authorized.”
- **What does a reviewer approve?** “They supply an allowed business response, such as a substantiated PO selection; the workflow still rechecks the mandatory rules.”
- **What happens if it crashes?** “The PDF, queue and checkpoints are durable, and a retried financial commit cannot create a second approval allocation.”
- **What is the worker?** “A continuously running backend process that takes queued jobs and resumes saved work; it is separate from the web request.”
- **What remains before broader production use?** “Stronger authentication, broader document evaluation, hosted recovery acceptance and operator controls; this is a scoped private case-study application.”

## Document verification

Cross-checked amounts, invoice identifiers, PO caps and bank suffixes against `backend/scripts/demo_fixtures.py` and `backend/scripts/extraction_fixtures.py`; checked screen/action names against the current frontend and README. No application code or financial policy changed. No new processing, paid API calls, resets or deployment were performed to prepare this script.
