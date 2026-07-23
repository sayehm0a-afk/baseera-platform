# Legacy Reports — Historical Archive, Not Evidence of Implementation Status

The 42 documents in this directory are preserved for historical record
only. They were written during an earlier phase of this project and
assert things like "100% success," "production ready," "final
certification," "production quality gate passed," or that specific
modules (including the AI agent layer and Module 5) were complete,
validated, and ready for production deployment.

**A code-level engineering audit found these claims were not supported by
the actual repository state at the time they were written or since.**
Specifically, and as of the M0 milestone (see
`docs/architecture/m0-build-status.md`) and this M1 restructuring (see
`docs/architecture/current-status.md`): no Saudi stock-analysis engine,
technical indicator, market-data provider, or expert agent existed in
executable code; the "autonomous intelligence layer" these reports
describe as complete is generic orchestration scaffolding not connected
to the application's actual runtime; and the repository could not be
installed, imported, or fully tested in a clean environment until M0.

Do not cite anything in this directory as evidence that a feature,
module, or the platform as a whole is implemented, tested, or
production-ready. The only current, authoritative status document is
`docs/architecture/current-status.md`. Where these reports contain
genuinely useful historical context (design rationale, past decisions,
what was attempted and when), that context may still be useful — but
every completion, readiness, or certification claim in this directory
should be treated as unverified and, based on the evidence available at
the time of the M0/M1 audits, contradicted by the actual code.

These files are kept verbatim, with their original content and history
intact via `git mv`. Nothing has been deleted or edited.
