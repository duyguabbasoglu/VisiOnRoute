# AGENTS.md — Kurallar / Rules for coding agents

Read `CLAUDE.md` first. Then follow these non-negotiable rules:

1. **Inspect before editing.** Read the relevant files and existing patterns
   before changing anything.
2. **Preserve domain boundaries.** `visionroute.domain` must not import
   FastAPI, SQLAlchemy sessions, AWS SDKs, or UI code. Boundaries are enforced
   by import-linter (`make lint` runs it). Do not weaken the contracts in
   `pyproject.toml [tool.importlinter]`.
3. **Never introduce fake production data.** Synthetic data is allowed only in
   demo/dev mode and must carry `data_origin="synthetic"`, `environment="demo"`.
4. **Never bypass authentication or authorization.** No debug backdoors, no
   permission checks that only exist in the frontend.
5. **Never log secrets or sensitive evidence.** Use the structlog redaction
   processors; never print passwords, tokens, or media URLs.
6. **Never weaken tests to make CI pass.** Fix the code, not the assertion.
   Do not skip, xfail, or delete tests without a documented reason.
7. **Run targeted tests after edits**; run the full quality suite
   (`make check`) before declaring any milestone complete.
8. **Update documentation when behavior changes** (`docs/`, OpenAPI
   descriptions, `CLAUDE.md` if conventions change).
9. **Create Alembic migrations for every schema change.** No destructive
   migration shortcuts; separate data backfills from schema changes.
10. **Customer-facing language is Turkish.** UI text, validation messages,
    API error messages shown to customers, e-mails, reports. Code identifiers
    stay English.
11. **Use existing patterns before adding dependencies.** New dependencies
    need a written justification in `docs/DECISIONS.md`.
12. **Record significant decisions as ADRs** in `docs/adr/`.
13. **Leave the repository in a runnable state.** `make dev` and `make test`
    must work when you stop. If something is unavoidably broken, record it in
    `docs/HANDOVER.md` before ending the session.
