# Project documentation

[Application guide and complete navigation](../README.md) · [Live app](https://invoiceautomation-seven.vercel.app/)

## Public guides

| Document                                       | Read it for                                                                                                   |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| [Main README](../README.md)                    | Project purpose, role-based walkthrough, screenshots, PO balance explanation, scenarios and deployment status |
| [Run locally](RUNNING.md)                      | Windows CMD prerequisites, dependencies, database setup, API/worker/frontend and generated PDFs               |
| [Manual invoices and reset](DEMO_INVOICES.md)  | Exact fields for nine manual PDFs, matching PO/GSTIN data, reset steps, expected outcomes and balances |
| [Development and verification](DEVELOPMENT.md) | Repository map, regression/build/migration commands and dated measured results                                |
| [Role access](ROLE_ACCESS.md)                  | Submitter ownership, reviewer permissions and public assignment identities                                    |
| [Security](SECURITY.md)                        | Credential types, encrypted expiring OpenAI sessions and public-demo boundaries                               |
| [Extraction prompt and storage](EXTRACTION.md) | Exact instructions, PDF request shape, example fields, private storage and review comparisons |
| [SPEC](../SPEC.md)                             | Canonical product, financial, API and workflow contract; planned features are not implementation claims       |
| [Decisions](DECISIONS.md)                      | Agreed architecture/policy choices and unresolved details                                                     |
| [Benchmark evidence](benchmarks/README.md)     | Sanitized model/extraction measurements and dated token-rate assumptions                                      |
| [Historical plans](archive/README.md)          | Earlier planning references; follow SPEC when documents disagree                                              |

The implementation uses only OpenAI, deterministic financial rules, a persistent worker and PostgreSQL. Actual credentials, invoices, private database contents and owner-specific deployment instructions are not dependencies of these public documents.

## Local owner notes

Personal operating material lives under **docs/local/**, which is ignored by Git and Docker. It is intentionally absent from a fresh clone. Existing local copies include predeployment reports, key/deployment runbooks, the demo recording script, phase handoff, and original README/setup/security/role/build/visual-QA journals. Public guides above replace any dependency on those notes.

Put future personal notes in that ignored folder. Keep canonical contracts, runnable setup, source-linked API documentation, required benchmark data and selected synthetic screenshots public. Ignore rules do not hide already tracked files or erase Git history; moved owner-only files must also be removed from the index.
