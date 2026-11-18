# Submitter and financial-reviewer access

[Project navigation](../README.md#complete-app-navigation) · [Documentation](README.md) · [Security](SECURITY.md)

In `ACCESS_MODE=roles`, the server authenticates each token and determines role/ownership. This is a single finance workspace with individually issued submitter identities and one reviewer role, not public signup or production multi-tenant authentication. The case-study profile provides three submitter slots and a reviewer.

| Feature                                    | Invoice submitter   | Financial reviewer                     |
| ------------------------------------------ | ------------------- | -------------------------------------- |
| Default landing                            | My invoices         | Review queue                           |
| Upload a PDF                               | Allowed             | Denied                                 |
| OpenAI key/model setup                     | Own connection only | Denied; no provider key needed         |
| Invoice history, PDF, events and status    | Own runs only       | Workspace runs                         |
| Decision/reason and usage                  | Own invoice         | Workspace invoice                      |
| Review candidates/actions                  | Denied              | Offered actions with rationale         |
| PO terms, balances and ledger              | Denied              | Allowed                                |
| Vendor registration / status changes       | Denied              | Allowed with rationale and idempotency |
| PO preview / creation                      | Denied              | Approved vendors only                  |
| Create PO for inactive/blacklisted vendor  | Denied              | Denied in UI and API                   |
| Edit/delete existing PO or vendor identity | Denied              | Not available                          |
| Company overview / internal audit          | Denied              | Allowed                                |
| Execute payment / waive hard cap           | Denied              | Not available                          |

## Individual identity and ownership

APP_API_TOKEN maps to the primary `submitter`; SUBMITTER_API_TOKENS maps other stable actor IDs to distinct secrets. REVIEWER_API_TOKEN authenticates finance. The operator generates/distributes app credentials and keeps identity mappings stable across restarts and token rotation. Sharing a submitter token shares that identity's history. Reusing an actor ID for a different person changes who can see its records and must not be done casually.

New runs and provider sessions receive immutable server-derived ownership. Intake idempotency and history queries are owner-scoped. Foreign or missing resources both return 404; forbidden features return 403. Legacy ownerless records stay reviewer-only. Hiding a link is not the authorization boundary: APIs enforce the same restrictions. Financial duplicate detection and PO allocations remain workspace-wide, so different submitters cannot approve the same business invoice twice.

Shared compatibility mode retains its older broad inspection behavior and is not person-level isolation. It does not gain new vendor/PO spending authority. The scenario gallery is hidden in role mode.

## Personal credentials after deployment

The operator configures distinct app tokens, the database and a stable API/worker encryption secret server-side. Submitters provide their own OpenAI key through the app; finance uses only its app token. The historical setting `OPENAI_CREDENTIAL_MODE=reviewer` refers to evaluator-supplied extraction credentials, not to the financial reviewer role.

A submitter connects once for multiple uploads in the same tab for up to 24 hours. Refresh, a new tab, expiry or disconnect requires reconnection for new uploads; it does not require a newly generated provider key if the old one remains valid. Submitted jobs retain their frozen model/connection binding. The persistent worker uses that binding to process queued/resumed work and must remain active after deployment. See [key lifecycle](SECURITY.md#provider-sessions).

## Public assignment option

With `PUBLIC_DEMO_ACCESS=true`, the signed-out **Get demo access** panel exposes only the designated primary submitter and reviewer app tokens. Use fills the normal login input; Connect verifies their actual roles. This intentionally shares synthetic assignment activity and reviewer master-data/financial-review authority with visitors. Additional submitter slots stay unpublished. The profile requires personal-key extraction and no operator OpenAI key; it does not start the worker.

Default false retains private token distribution. Stronger sign-in/invitation, expiry/revocation and public abuse controls are future work. Current hosted deployment/worker gates are described in [README](../README.md#deployment-status).
