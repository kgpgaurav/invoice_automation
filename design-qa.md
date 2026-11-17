# Selected invoice workspace — visual and interaction QA

Source visual truth: the user's **1487 × 1058 inline mockup** supplied after the Product Design brief (Review queue, INV-1048, Kaveri Office Supplies). It is available in the conversation, not as a standalone repository image. Comparison is a manual visual assessment against that exact attachment, not a claimed pixel-diff score or an independently identified font match.

Implementation layout baseline (before the later DM Sans selection): [desktop viewport](docs/screenshots/ui-2026-11-17/review-queue-viewport.png), [full queue/detail](docs/screenshots/ui-2026-11-17/review-queue.png). CSS viewport **1487 × 1058**, device scale factor 1, screenshot scale CSS; viewport capture is exactly 1487 × 1058. The full-page capture includes content below the viewport, without resizing it to manufacture a match. Source has no browser chrome. Same interaction: missing-PO exception selected, supporting PO selected, rationale entered, response not submitted. Actual local records differ from the reference's illustrative data and are explicitly marked MOCK EXTRACTION.

## Later user amendment: DM Sans and setup guidance

The user expressly selected **DM Sans** after the layout review, so the current typography intentionally updates the reference's earlier family. Latest evidence: [DM Sans review queue](docs/screenshots/ui-2026-11-17/dm-sans-review-queue.png), [phone detail](docs/screenshots/ui-2026-11-17/dm-sans-review-mobile.png), [OpenAI setup](docs/screenshots/ui-2026-11-17/dm-sans-key-setup.png), [phone setup](docs/screenshots/ui-2026-11-17/dm-sans-key-setup-mobile.png). Queue viewport 1487 × 1058 and setup viewport 1440 × 1000; phone viewport 390 × 844, all CSS-pixel full-page captures. Both source amendments (selected layout and explicit font choice) were used for this pass. Older images remain dated layout evidence, not current-font screenshots.

Verified the bundled Latin and extended DM Sans faces load successfully, including ₹, and the computed interface family is DM Sans Variable. Human-facing invoice/PO headings use the interface font; technical audit IDs keep mono. The UI guide explicitly orders key → connect → model → PDF in personal-key mode, while managed/mock mode stays key-free and financial-reviewer setup remains denied. The setup screenshots use mocked provider configuration in shared compatibility mode with an empty key field, not a real provider session. Reviewer screenshots use actual explicitly labelled mock runs.

Re-ran all **14 shared/provider/workflow** and **8 role** browser cases; frontend format/type/build checks pass. The manual font pass returned `consoleErrors: []` and `focusReturned: true`; 768/390 layouts and the actual private PDF/modal were inspected again. No new actionable P0/P1/P2 finding. No financial action was submitted during the manual capture and no user records were changed/reset. Font changes do not alter PDF source content, financial formatting or API contracts.

Additional evidence: [access](docs/screenshots/ui-2026-11-17/access.png), [tablet list](docs/screenshots/ui-2026-11-17/queue-tablet.png), [phone list](docs/screenshots/ui-2026-11-17/queue-mobile.png), [phone detail](docs/screenshots/ui-2026-11-17/review-mobile.png), [expanded PDF](docs/screenshots/ui-2026-11-17/expanded-document.png), [submitter](docs/screenshots/ui-2026-11-17/submitter.png). Tablet CSS viewport 768 × 1000; phone 390 × 844. Full-page captures retain their original CSS pixel width. Browser regressions additionally cover 1440 × 1000, 768 and 390 widths. No horizontal document overflow was observed.

## Findings and comparison history

| Severity | Evidence / impact | Fix and post-fix evidence |
| --- | --- | --- |
| P1, resolved | Live signed-out UI showed finance headings, queue filters and unknown counts before access was verified (`output/playwright/live-before.png`). | Dedicated access entry; private chrome mounts only after `/access` succeeds. Access screenshot and entry/invalid/pending-access browser cases pass. |
| P2, resolved | First queue pass placed a search row inside the table card, moving the rows below the selected composition. Sidebar/card positions also drifted. | Search/refresh moved to the page heading; 254px desktop sidebar, equal queue/detail tracks, 14px gutter. Final viewport matches the reference's principal regions, with queue/detail beginning around x276/x878 and y148. |
| P2, resolved | The earlier tablet capture inspected in the conversation inherited a tall stacked header from legacy CSS. The intermediate filename was later reused by the role runner. | Compact brand/account row and wrapping role navigation at ≤900px; list-to-detail presentation below 1100px. Final tablet/phone captures show no clipped navigation. |
| P2, resolved | Modal test found initial focus on the PDF link instead of the close control. The first expanded capture also inherited Tailwind's zero dialog margin. | Explicit close-button focus after `showModal()` and centered `margin:auto`. Browser test verifies Escape and restored trigger focus; final expanded screenshot verifies placement. |
| P2, resolved | Single-page disabled paging and a full-width action selector added unnecessary height to review. | Hide paging only for a known single-page PDF, retain multi-page controls, compact the action selector and field spacing, hide the ready-state helper visually while keeping it described for assistive technology. Final full-page review evidence shows an intact form, all candidates and clear revalidation language. |

No actionable P0/P1/P2 findings remain. These are expected product/data differences, not hidden fidelity defects:

- Product name is **Invoice operations**. The reference's P1/“Ledger Desk” branding, calendar/country banner and synthetic-design footer are not introduced. The user explicitly requested removal of assignment branding and the global footer.
- There are two actual open local exceptions and two offered POs for the selected invoice. Do not fabricate four invoices, discard a candidate or preselect a PO to imitate the reference. Extra candidates and permitted actions can require vertical scrolling; there is no promise that every variable-length financial review fits one viewport.
- Receipt timestamps and age derive from actual records. Money retains the existing precise two-decimal INR formatter. Missing values remain unknown.
- The original private PDF is a synthetic fixture rendered by PDF.js, rather than a picture of the reference invoice. Compact preview is scrollable; expansion provides readable document detail.
- A labelled action selector exposes all server-permitted actions. “Confirm selection & resume” is retained and explicitly does not imply approval. Evidence/audit details stay available in disclosures or the full record.

## Required fidelity surfaces

- **Typography:** current locally bundled DM Sans (Segoe UI/Arial fallback), 36px desktop queue heading, 25px invoice reference/amount, compact 12–15px operational labels and tabular monetary numerals. Hierarchy, wrapping, required labels and readable outcomes inspected. DM Sans is the user's later explicit choice; exact matching to the reference's earlier font is not claimed.
- **Spacing/layout:** warm full-height sidebar, equal desktop cards, clear selected row with olive rule, compact exception/document/PO/rationale sequence; tablet/phone list-to-detail rather than squeezed side-by-side cards. Full-view comparison and focused inspection of invoice header, PO choices, action form and PDF modal were performed.
- **Colors/tokens:** existing warm-neutral/olive system retained and refined; amber denotes review, other semantic outcomes remain distinct. Automated existing contrast checks meet 4.5:1 for tested text/status pairs; focus outlines and form labels remain visible.
- **Images/icons:** real authenticated PDF bytes, crisp PDF.js canvas, working expansion; [Phosphor regular icons](https://github.com/phosphor-icons/react) replace handwritten SVGs. Favicon is exported from the same library. No fabricated invoice image, generated logo or decorative raster is used.
- **Copy/content:** actual API values and counts only; explicit mock/replay labels; rationale required; missing/uncertain evidence remains reviewable. No marketing slogans, payment-execution claims or assignment footer. Submitters see their own tools and records only.

## Interaction evidence

All **14 shared/provider/workflow** and **8 role** browser cases pass. Coverage includes original upload/worker/decision flows, source links, stream reconnection and fallback, search/pagination, role denial and ownership, OpenAI model/disconnect/late-response cleanup, invalid/verifying access, correct default landing including empty review queue, error vs no-result states, mobile Back, browser Back/Forward, retained selected URL, required rationale, pending-submit guard and successful real local transaction after explicit mocked extraction.

The isolated manual screenshot pass returned `consoleErrors: []` and `focusReturned: true`. The final centering-only CSS correction was recaptured and inspected. No remote write or paid OpenAI call was performed. Existing old screenshots are historical and unchanged; accepted captures above contain synthetic local data.

## Implementation checklist and limits

- [x] Selected direction implemented in the existing React/TypeScript app.
- [x] Source/reference composition and focused regions inspected; P1/P2 findings corrected and recaptured.
- [x] Responsive and keyboard/review behavior verified in isolated Chrome.
- [x] Backend regression/migration suite, Ruff, generated API hash parity, frontend formatting/type/build checks pass.
- [x] Local preview retained; changes uncommitted, without push or deployment.

P3 follow-up: broaden visual testing to longer real invoice layouts and multi-page documents. The new modal was exercised with single-page synthetic PDFs; multi-page paging code and the server's existing page limits are preserved. Vite still reports its existing PDF.js chunk-size warning. This is a local UI review, not hosted extraction/worker activation or a live-provider accuracy benchmark.

final result: passed
