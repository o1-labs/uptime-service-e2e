# uptime-service-e2e

End-to-end tests for the Mina Delegation Program uptime service.

## Scope

Tests the contract: **BP submission → backend ingest → storage (S3 + Postgres) → validation cronjob → verified record**.

In scope:
- [`uptime-service-backend`](https://github.com/o1-labs/uptime-service-backend) — REST ingest
- [`uptime-service-validation`](https://github.com/o1-labs/uptime-service-validation) — verify cronjob *(coming next)*
- [`delegation-program-leaderboard`](https://github.com/o1-labs/delegation-program-leaderboard) — Postgres reader *(coming next)*

Out of scope:
- `mina-payout-reports` — covered separately via golden-fixture tests against published e2e dumps (see [Golden Fixtures](#golden-fixtures))
- GCP Pub/Sub replicator — migration scaffolding, not a production correctness boundary

## Layout

```
.
├── compose/
│   ├── docker-compose.yaml   # postgres + minio + backend + validation + leaderboard
│   └── config/
│       ├── backend.json      # CONFIG_FILE for the backend
│       └── postgres-init.sql # fetched at `make schema` from validation@VALIDATION_TAG
                              # (gitignored — never vendored, never drifts)
├── fixtures/                 # canned submission payloads
├── tests/                    # pytest harness
├── Makefile
├── pyproject.toml
└── .env.example              # copy to .env and tweak
```

## Prerequisites

- Docker + Docker Compose
- Python ≥ 3.10

The harness pulls every component as a published image — no source clones needed.

## Getting started

```bash
make install   # pip install -e .
make up        # pull images, start postgres + minio + backend
make test      # run pytest
make down      # stop and wipe volumes
```

## Decisions baked in (v1)

1. **S3 emulation** — MinIO. Backend is pointed at it via `AWS_ENDPOINT_URL_S3` + `AWS_S3_FORCE_PATH_STYLE=1`.
2. **Signing** — disabled in the backend (`verify_signature_disabled: true`); canned `req-no-snark.json` from upstream test data is replayed as-is. Signature verification is unit-tested in `signer_test.go` upstream and doesn't need re-coverage here.
3. **Whitelist** — disabled (`delegation_whitelist_disabled: true`). Google Sheets path is out of e2e scope.
4. **Service version pinning** — components are consumed as published GHCR images, pinned via `BACKEND_TAG` (and future `VALIDATION_TAG` etc.) in `.env`. Tests run against production-ready artifacts, not local working trees. Avoid `latest` — pin to a release tag so failures are reproducible and bumps are intentional.
5. **Leaderboard** — deferred to next iteration.

## Golden fixtures

A separate weekly job will run the full e2e flow and publish the resulting Postgres dump + S3 contents as a versioned artifact (`dumps/YYYY-MM-DD/`). `mina-payout-reports` consumes a *pinned* version of that artifact in its own test suite.

**Contract rule:** if the reports test goes red, do *not* refresh the dump version to make it pass — investigate whether the report generator still works on the new schema first. Bumping the dump version is an explicit decision, not a fix.
