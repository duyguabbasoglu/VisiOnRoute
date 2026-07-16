# CLAUDE.md — VISiOnRoute

## Mission

VISiOnRoute is a fully Turkish transportation-safety SaaS: it analyzes driver
behavior and road conditions in near-real-time and makes risks visible before
they escalate. It never claims to prevent accidents and never replaces legal,
medical, occupational-safety, automotive, or human judgment.

## Architecture map

Modular monolith, one Python package, independently scalable processes:

- `src/visionroute/domain/` — pure domain logic (no framework imports)
- `src/visionroute/application/` — use cases, ports (Protocol interfaces)
- `src/visionroute/infrastructure/` — SQLAlchemy models/repos, adapters
- `src/visionroute/api/` — FastAPI app, routers, request/response schemas
- `src/visionroute/worker/` — Postgres outbox/job consumer (SKIP LOCKED)
- `src/visionroute/scheduler/` — periodic jobs
- `src/visionroute/cli/` — Typer CLI (`visionroute` command)
- `apps/web/` — Next.js Turkish frontend (pnpm)
- `infra/terraform/` — AWS IaC
- `tests/{unit,integration,contract,security,e2e}/`

Source of truth: PostgreSQL 17 + PostGIS. Redis: cache & rate limiting only.
Events flow through `outbox_events`; workers consume with FOR UPDATE SKIP LOCKED.

## Common commands

```bash
make bootstrap      # install backend+frontend deps, pre-commit
make dev            # start local stack (db, api, web, worker)
make db-up          # start local PostgreSQL (Homebrew fallback when no Docker)
make migrate        # alembic upgrade head
make fmt lint type  # ruff format, ruff+import-linter, mypy
make test           # unit + integration tests
make check          # full quality gate (fmt-check, lint, type, test, security)
poetry run visionroute admin bootstrap   # one-time first-admin creation
poetry run visionroute simulate ...      # telemetry simulator (demo only)
```

## Conventions

- Python 3.13, strict mypy, Ruff (line length 100). Pydantic v2 everywhere at
  boundaries; domain uses dataclasses/plain types.
- IDs are UUIDv7 (generated in `visionroute.domain.ids`).
- All timestamps UTC (`timestamptz`); UI renders Europe/Istanbul.
- Every tenant-bound table has `organization_id` + RLS policy.
- API: `/api/v1/`, error envelope `{"error": {"code", "message", "request_id"}}`,
  Turkish `message`, machine-readable `code`.
- Frontend: TypeScript strict, no `any`, TanStack Query, Zod-validated API
  responses, Turkish UI text only.

## Security rules

- No plaintext secrets anywhere; settings via pydantic-settings + AWS Secrets
  Manager in production. API keys and refresh tokens stored hashed.
- JWT: RS256 only, short expiry, `iss/aud/exp/nbf/jti/kid` enforced.
- Deny-by-default permissions; check in application layer, not UI.
- Evidence media: private buckets, short-lived signed URLs, access logged.
- SSRF guard (`visionroute.security.urlguard`) for all user-supplied URLs.

## AI/LLM restrictions

- Disabled by default (`AI_ASSIST_ENABLED=false`).
- Only bounded, schema-validated tasks (summaries, coaching drafts, note
  classification). Never: numerical telemetry classification, disciplinary
  decisions, SQL, arbitrary code, evidence invention.
- LLM output is untrusted: schema-validate, never render as HTML.

## Data-origin rules

Synthetic/simulator data must set `data_origin="synthetic"` and
`environment="demo"` and must never appear as production evidence.

## Definition of done (per change)

format ✓ lint ✓ types ✓ targeted tests ✓ docs updated ✓ migration created (if
schema changed) ✓ Turkish customer-facing text ✓

## Known limitations / current state

See `docs/PROGRESS.md` and `docs/HANDOVER.md`. Current milestone is tracked in
`docs/IMPLEMENTATION_PLAN.md`.
