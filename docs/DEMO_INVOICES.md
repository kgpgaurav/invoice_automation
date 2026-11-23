# Create manual demo invoices and reset the workspace

[Application guide](../README.md) · [Runnable setup](RUNNING.md) · [Machine-readable inputs](fixtures/manual-invoices-v1.json)

Use this sheet to make your own PDFs in an invoice generator. These are synthetic assignment inputs and expected rule outcomes, not saved OpenAI responses or completed invoices. Use a real personal-key workspace for these manually created PDFs; the explicit mock workspace accepts only its own generated files.

## 1. Prepare the existing workspace

GitHub receives the source code and migration files. Database migrations/data operations run against Supabase; do not push your database, deployment.env, API keys or local configuration to GitHub.

A read-only check on **23 November 2026** found all four POs below already present in hosted schema **ps1_app**, each OPEN with zero allocated funds. Their suppliers, GSTINs, quantities, prices and tax rates matched the prepared baseline. The hosted schema was still at **0010_vendor_management**. No duplicate POs, database migration, reset or hosted write was performed for this guide.

To enable the new reset on that existing site:

1. Push/redeploy the reviewed source changes for the frontend, API and worker together. Pause new submissions during the schema/code update.
2. From backend in Windows CMD, apply the new migration using your existing ignored hosted configuration:

   ```cmd
   cd /d "C:\Users\KUMAR GAURAV PRAKASH\Desktop\zamp_submission\backend"
   uv run --locked --env-file ..\.local\deployment.env python -m scripts.hosted migrate
   ```

   This upgrades through **0011_demo_reset** and checks the checkpoint schema. It does **not** delete existing invoices or restore balances. Apply it close to the code deployment; readiness can report a version mismatch until code and database agree.
3. On the API service, set **DEMO_RESET_ENABLED=true**, retaining **ACCESS_MODE=roles**, the existing reviewer token and **DATABASE_SCHEMA=ps1_app**. Redeploy the API after changing its environment settings. Keep the worker's policy **policy-1.1-demo**.
4. Wait for active processing to finish. Sign in as **Financial reviewer → Overview → Reset demo data**. Review the counts, type **RESET DEMO**, then click **Clear data & restore demo**.
5. The reset removes all workspace PDFs, runs, review/approval history, custom vendors/POs and OpenAI connections. It restores the three vendors/four orders below with zero allocations. Login tokens and migration metadata remain; reset receipts are retained. A busy worker or changed preview stops the operation. Refresh the preview before a new confirmation; retry the same dialog after a lost response.
6. Verify an empty invoice history and the starting PO balances below. Ensure the persistent worker is running, then reconnect OpenAI and choose a model as the submitter before uploading anything.

New disposable role-demo workspaces enable the reset automatically. Older local workspaces need their business/checkpoint migrations updated and DEMO_RESET_ENABLED=true in **that workspace's** ignored backend.env, then an API restart. The environment file used for a generated demo is different from backend/.env. Do not use `scripts.demo reset` for this task: that separate local command removes a marked disposable workspace's schemas rather than resetting its data in place.

Reset is the operation that removes PDFs and restores numbers. Migration, deployment and the add-only `seed-demo` command do not do that. Do not manually delete individual ledger/run tables: the guarded reset keeps related records and worker ownership consistent. It cannot cancel a provider request already dispatched after a database connection was lost.

## 2. Matching vendors and purchase orders

All suppliers below are **Approved / ACTIVE**, with registered bank last-four **1234**. Use these exact synthetic supplier GSTINs; do not substitute a random GSTIN or the buyer's GSTIN.

| Vendor code | Supplier / From | Supplier GSTIN | Example city/state |
| --- | --- | --- | --- |
| A | Aster Office Supplies | **27ABCDE1234F1Z5** | Mumbai, Maharashtra, India |
| B | Aster Industrial Supplies | **29ABCDE1234F1Z5** | Bengaluru, Karnataka, India |
| C | Aster Technology Services | **07ABCDE1234F1Z5** | New Delhi, Delhi, India |

All four POs have **issue date 2026-10-01**, no expiry, currency **INR**, and one line: **Office paper**, SKU **PAPER**, quantity **100**, net unit price **1000.00**. They are already created in the hosted workspace and are recreated by reset; do not create duplicates.

| PO reference | Vendor | Line tax | Full line net / tax / gross | Authorized cap and available after reset |
| --- | --- | --- | --- | --- |
| **PO-001** | A | 18% | 100000.00 / 18000.00 / 118000.00 | **50000.00** |
| **PO-PARTIAL** | B | 0% | 100000.00 / 0.00 / 100000.00 | **100000.00** |
| **PO-SELECT-001** | C | 18% | 100000.00 / 18000.00 / 118000.00 | **25000.00** |
| **PO-SELECT-002** | C | 18% | 100000.00 / 18000.00 / 118000.00 | **40000.00** |

The spending cap is a separate authorization from the full line allowance. A lower cap is deliberate, not a missing-tax calculation. Both money and quantity limits apply. Recorded approvals/committed quantities start at **zero** after reset.

If a different empty workspace needs the masters, use the guarded preview/apply commands in [RUNNING.md](RUNNING.md#populate-hosted-demo-masters), after migrating it. Those commands insert the same three vendors/four POs; they preserve existing history and do not reset balances. For manual UI creation, copy this table, select the approved vendor, use the shared line/date values and enter an authorization rationale. Do not recreate orders that already exist.

## 3. Fields common to every manually created PDF

| Generator field | Enter |
| --- | --- |
| Document | Invoice / Tax invoice, with readable PDF text |
| From / Supplier name and GSTIN | Vendor A, B or C exactly as specified per case |
| Supplier country | India; use the matching example city/state above |
| Bill To | **PS-1 Demo Company**, Mumbai, Maharashtra, India |
| Buyer GSTIN | May be left blank for this application's demo; do not put it in the supplier field |
| Invoice date | **20 November 2026** (`2026-11-20`), including the duplicate case |
| Due date | **20 December 2026** (`2026-12-20`); optional to the current rules |
| Currency | **INR / Indian rupee**, not USD. If the generator prints only a symbol, also add **Currency: INR** in notes |
| Item description | **Office paper** exactly; quantity and rate from the case table |
| Price | Rate before tax; add the specified tax separately |
| SKU / PO line / HSN | SKU PAPER is optional; PO-line reference and HSN may be blank. Do not substitute an HSN code for the SKU |
| Bank note | **Bank account last four: 1234**, except E4 which uses **9876** |
| Discount / shipping / cess / amount paid | **0** or absent; no additional charges or manual rounding |
| Notes | “Synthetic assignment invoice — not payable.” The bank note can go here if there is no bank field |

For the 18% examples, a GST generator can print **CGST 9% + SGST 9%** for vendor A, or **IGST 18%** for vendor C. Their combined rate/amount must match the table. For vendor B, show the **0% rate and 0.00 tax explicitly**; a hidden/missing tax field is not evidence of zero tax. These rates are the existing synthetic PO terms.

Before downloading: remove unused blank item rows; check invoice number/date, supplier GSTIN, PO reference, currency, quantity, rate, printed tax, subtotal and grand total. Keep the PDF unencrypted, one to five pages, and below the active upload limit (the Vercel profile is **4 MiB**). Read the downloaded PDF once before uploading. Missing evidence or an unfamiliar layout can still require review; a schema-valid LLM response alone cannot authorize it.

## 4. Exact invoice inputs

All figures below are INR. Each row is **one separate PDF**, with one Office paper line. Use the common fields above unless the row explicitly changes one.

| Case / suggested filename | Invoice number | Vendor | PO printed on PDF | Qty | Net rate | Net subtotal | Tax | Grand total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **H1**, H1-manual.pdf | **DEMO-HAPPY-001** | A | **PO-001** | 10 | 1000.00 | 10000.00 | 18% = 1800.00 | **11800.00** |
| **E1-prior**, E1-prior-manual.pdf | **DEMO-PART-001** | B | **PO-PARTIAL** | 70 | 1000.00 | 70000.00 | 0% = 0.00 | **70000.00** |
| **E1**, E1-manual.pdf | **DEMO-PART-002** | B | **PO-PARTIAL** | 35 | 1000.00 | 35000.00 | 0% = 0.00 | **35000.00** |
| **E2**, E2-manual.pdf | **DEMO-PO-001** | C | **Leave blank everywhere** | 10 | 1000.00 | 10000.00 | 18% = 1800.00 | **11800.00** |
| **E3**, E3-manual.pdf | **DEMO HAPPY 001** | A | **PO-001** | 10 | 1000.00 | 10000.00 | 18% = 1800.00 | **11800.00** |
| **E4**, E4-manual.pdf | **DEMO-BANK-001** | A | **PO-001** | 5 | 1000.00 | 5000.00 | 18% = 900.00 | **5900.00** |
| **GST**, GST-manual.pdf | **DEMO-GST-001** | A | **PO-001** | 2 | 1000.00 | 2000.00 | 18% = 360.00 | **2360.00** |
| **PRICE**, PRICE-manual.pdf | **DEMO-PRICE-001** | A | **PO-001** | 2 | **1005.00** | 2010.00 | 18% = 361.80 | **2371.80** |
| **TAX**, TAX-manual.pdf | **DEMO-TAX-001** | A | **PO-001** | 2 | 1000.00 | 2000.00 | **12% = 240.00** | **2240.00** |

Make these two further changes **only** for their named cases:

- **E4:** replace the bank note with **Bank account last four: 9876**. All supplier/GSTIN/PO values remain correct.
- **GST:** replace supplier A's printed GSTIN with **27AAAAA0000A1Z5**. Keep the supplier name Aster Office Supplies and PO-001. This intentionally conflicts with registered GSTIN **27ABCDE1234F1Z5**; do not edit the master to match this erroneous invoice.

For E2, do not put either PO-SELECT reference in notes, addresses or payment terms. The invoice must genuinely have no printed PO. Keep vendor C's GSTIN: it lets the system establish the supplier before offering that supplier's two open orders.

## 5. Run order and what to inspect

1. **H1:** upload and wait for approval. Inspect 10 × 1000 = 10000, tax 1800, total 11800. PO-001 remaining becomes **38200.00**, with one ledger entry.
2. **E1-prior:** upload and wait for its actual **70000.00 approval**. PO-PARTIAL remaining becomes **30000.00**. Do not manually insert a prior approval or set its counter.
3. **E1:** upload the **35000.00** second invoice. Expect **Needs review / PO_CAP_EXCEEDED**, **5000.00 excess**, no new allocation, and PO-PARTIAL still at 30000.00 remaining. It also requests five more units than the remaining 30; the cap check stops the financial evaluation first.
4. **E2:** expect **Needs review / PO_AMBIGUOUS** and two offered POs. The intended synthetic supporting order is **PO-SELECT-001**. As reviewer, verify that supporting record, choose it, enter rationale, and resume. Selection alone is not approval. If all checks pass, the same run/thread approves **11800.00**, leaving **13200.00** on PO-SELECT-001. PO-SELECT-002 remains at 40000.00.
5. **E3:** run only after H1 approved. Keep the **same supplier, date, currency and amounts**, changing the visible invoice number to the spaced version **DEMO HAPPY 001**. Expect **Rejected / DUPLICATE_APPROVED**, with no second allocation. This tests the business identity across different PDF bytes/layouts, not merely a repeated file hash. An image-only scan is an optional harder variant; ungrounded scan identity must remain in review rather than be promised rejection.
6. **E4:** expect **Needs review / BANK_MISMATCH**. The invoice prints 9876 while the vendor record has 1234. No funds post; request independent supplier verification rather than accuse fraud.
7. **GST:** expect **Needs review / VENDOR_UNKNOWN**, with printed and registered GSTINs shown for comparison. Source text can be correctly extracted while the supplier identity is still wrong.
8. **PRICE:** expect **Needs review / PRICE_VARIANCE**. The arithmetic is correct, but 1005 differs from the PO's 1000 by 5 per unit. Automatic price variance is disabled; a small difference is not an automatic waiver.
9. **TAX:** expect **Needs review / TAX_UNCLEAR**. The invoice's 12% arithmetic is internally consistent but conflicts with the PO's 18% rate. This differs from a malformed invoice total.

These are expected outcomes when the source is successfully extracted and locally verified. A source-verification hold takes precedence; inspect its actual missing/unverified field instead of forcing the expected business code. Unknown source values must stay unresolved. No case executes a payment.

After all nine cases **and a successful E2 review/resume**, expect **nine runs: three approved, five awaiting review and one rejected**, assuming no technical/source failures or additional uploads. The ledger should contain **three approvals totalling 93600.00**:

| PO | Committed | Remaining funds | Remaining line quantity |
| --- | --- | --- | --- |
| PO-001 | 11800.00 | **38200.00** | 90 |
| PO-PARTIAL | 70000.00 | **30000.00** | 30 |
| PO-SELECT-001 | 11800.00 | **13200.00** | 90 |
| PO-SELECT-002 | 0.00 | **40000.00** | 100 |

If E2 has not been resolved yet, only H1 and E1-prior are approved: total **81800.00**, and both PO-SELECT balances remain unchanged. Waiting-review invoices reserve nothing. Do not repeatedly upload H1 to expect another approval; reset deliberately for a fresh rehearsal instead. The unresolved H2 ₹2-rounding example is excluded.

The JSON packet is a source-entry checklist, not a way to submit JSON instead of a PDF. The automated packet check uses explicit mock transport and isolated PostgreSQL to test these financial outcomes; it is not a live OpenAI accuracy claim for your chosen invoice generator.
