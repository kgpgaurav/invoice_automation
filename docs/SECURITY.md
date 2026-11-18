# Credentials and security boundaries

[Project](../README.md) · [Documentation](README.md) · [Permissions](ROLE_ACCESS.md)

## Separate credentials

| Credential                                                       | Who uses it                                                  | Where it belongs                                                      |
| ---------------------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------- |
| App access token                                                 | Submitter or financial reviewer, with a server-assigned role | Workspace access input; tab memory                                    |
| Personal OpenAI API key                                          | Invoice submitter paying for real extraction                 | Authenticated OpenAI connection; temporary encrypted server storage   |
| Database URI / encryption secret / optional managed-provider key | Operator and backend processes                               | Ignored local environment or server secrets; never frontend variables |

Financial reviewers need no OpenAI key. The app does not create provider keys or grant a finance role based on a selected label, URL or OpenAI account. Tokens in generated local workspaces differ from unrelated backend/hosted configurations.

## Provider sessions

In personal-key mode, keys are authenticated-encrypted in PostgreSQL with access expiring within 24 hours or after explicit disconnect. Physical ciphertext cleanup can wait during downtime; authorization does not extend. The originating tab holds only an opaque capability, and each submitted run freezes its original connection/model. The API and worker share the stable encryption secret.

Browser storage, URLs, logs, events, checkpoints and public responses must contain no plaintext key. Refresh/new tab requires reconnecting for new uploads. Closing/refreshing a tab does not revoke submitted jobs' bound connection. Disconnect revokes access and erases active ciphertext; already dispatched calls can finish and be billed. Personal-key mode never falls back to an operator key.

## Roles and public assignment access

Private role mode derives ownership from individual server-authenticated submitter tokens. Submitters can read only their own runs, PDFs, events and provider sessions. Ownerless legacy records are reviewer-only; ownership is not guessed. Finance directories, vendor/PO writes, reviews and metrics require reviewer authorization; master writes require the actual reviewer rather than shared compatibility credentials.

Opt-in `PUBLIC_DEMO_ACCESS=true` intentionally publishes the primary submitter and reviewer app tokens through no-store `/api/v1/demo-access`. It requires role mode, personal-key mode, a reviewer token and no operator OpenAI key. Additional submitter tokens and all provider/database/encryption secrets stay private. Visitors using a published token share its identity and visible activity; use synthetic documents only. Default false retains the private profile. Static tokens and this assignment disclosure are not production authentication or private multi-tenant signup.

## Financial and document boundaries

PDFs are private authenticated PostgreSQL attachments, not public object links. Invoice content is untrusted data, including instructions embedded in a document. Structured schema compliance and model confidence do not establish factual correctness. Missing/unverifiable critical evidence requires review.

Vendor/PO authorization is deterministic and rechecked under locks. Immutable financial history, invoice uniqueness, queue ownership fencing and transactional event writes prevent duplicate financial posting. An approved invoice is not paid. Payment execution, automatic email and unrestricted financial override are outside scope.

Use HTTPS for hosted credentials and a private backend-only database schema. Keep connection poolers session-preserving where advisory locks/checkpoints require it. Verified sign-in/invitations, secure cookie sessions, MFA, public abuse controls, broader retention policies and hosted recovery testing remain separate work.

## Repository and local files

`.gitignore` excludes secrets/environments, local databases, uploads/PDFs, traces, editor state, archives/backups and personal docs/local notes. `.dockerignore` separately excludes private build-context artifacts. Public example configuration contains placeholders only. Sanitized synthetic screenshots and benchmark records are intentionally public.

Ignoring/untracking a file does not erase old commits, revoke a credential or sanitize an arbitrary ZIP. Never distribute an entire working directory assuming Git exclusions protect it. If a real secret is exposed, revoke/rotate it at the provider and update private configuration; history cleanup alone cannot invalidate it. Personal incident/deployment notes are local-only and are not required to run this project.
