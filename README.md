# uptime-service-e2e

End-to-end tests for the Mina Delegation Program uptime service.

## Scope

Tests the contract: **block production → BP submission → backend ingest → storage (S3 + Postgres) → validation verifier → scored leaderboard**.

Real components, production-shape data:

- [`uptime-service-backend`](https://github.com/o1-labs/uptime-service-backend) — REST ingest, persists submissions + blocks
- [`uptime-service-validation`](https://github.com/o1-labs/uptime-service-validation) — batches submissions and spawns verifier workers
- [`submission-updater`](https://github.com/o1-labs/submission-updater) — bundles `delegation-verify` and orchestrates per-batch verification
- [`delegation-program-leaderboard`](https://github.com/o1-labs/delegation-program-leaderboard) — Postgres reader, exposes scoreboard via REST
- [`mina-daemon`](https://github.com/MinaProtocol/mina) — real block producers, run via [`minimina`](https://github.com/o1-labs/minimina) in a sibling docker-compose project

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  minimina (sibling docker-compose project)                      │
│   default-seed-e2e ─┬─ node-a-e2e (BP, real keypair)            │
│                     ├─ node-b-e2e (BP, real keypair)            │
│                     ├─ node-c-e2e (BP, real keypair)            │
│                     └─ snark-node-e2e + snark-worker            │
└───────────────────────────────┬─────────────────────────────────┘
                                │  POST /v1/submit
                                ▼  (resolves via shared `uptime-e2e-net`)
┌─────────────────────────────────────────────────────────────────┐
│  this compose stack                                             │
│   backend ──┬─→ Postgres (submissions table)                    │
│             └─→ MinIO    (e2e/blocks/<hash>.dat)                │
│                                                                 │
│   validation ───→ submission-updater (DinD worker, per batch)   │
│                  └─→ delegation-verify --config-file <genesis>  │
│                                                                 │
│   leaderboard-api ──→ Postgres (scoreboard)                     │
└─────────────────────────────────────────────────────────────────┘
```

The mina BPs target the hostname `uptime-service-backend-e2e` (baked into
their command line by minimina). Our backend exposes that name as an alias
on the shared external `uptime-e2e-net` network — see `compose/docker-compose.yaml`.

## Layout

```
.
├── compose/
│   ├── docker-compose.yaml      # postgres + minio + backend + validation + leaderboard
│   ├── config/
│   │   ├── backend.json
│   │   └── postgres-init.sql    # fetched at `make schema` from validation@VALIDATION_TAG
│   │                            # (gitignored — no vendoring, no drift)
│   └── worker/
│       ├── Dockerfile           # bakes our minimina genesis into submission-updater
│       └── genesis_ledger.json  # copied from fixtures at `make worker-image` (gitignored)
├── fixtures/
│   └── minimina/                # vendored topology, BP/libp2p keys, genesis ledger
├── scripts/
│   └── patch_minimina_compose.py
├── tests/                       # pytest harness
├── Makefile
├── pyproject.toml
└── .env.example                 # copy to .env and tweak
```

## Prerequisites

- Docker + Docker Compose
- Python ≥ 3.10
- `minimina` (installable from the o1test debian repo, see CI workflow for the apt line)

Every component except `minimina` is pulled as a published image — no source clones needed.

## Getting started

```bash
make install        # pip install -e .
make up             # network + images + minimina up + start
make test           # run pytest
make down           # stop and wipe everything
```

`make up` is slow on a cold cache (mina-daemon image is large and BPs need a few minutes to bootstrap before producing blocks). Tests poll for this; budget at least 15 minutes wall-clock for the full suite.

## Decisions baked in

1. **S3 emulation** — MinIO. Backend is pointed at it via `AWS_ENDPOINT_URL_S3` + `AWS_S3_FORCE_PATH_STYLE=1`.
2. **Signing** — real Schnorr signatures from minimina-managed BPs, verified by the backend. No bypass.
3. **Whitelist** — disabled (`delegation_whitelist_disabled: true`). Google Sheets path is out of e2e scope.
4. **Custom genesis** — minimina spins up its own genesis ledger; the verifier needs the same one to validate consensus, so it's baked into the worker image at build time (`compose/worker/Dockerfile`) and exposed via `GENESIS_LEDGER_FILE`.
5. **Service version pinning** — components are consumed as published images, pinned via `*_TAG` in `.env`. Avoid `latest` — pin to a release tag so failures are reproducible and bumps are intentional.
6. **Network era** — mina-daemon and the bundled `delegation-verify` in submission-updater are both Berkeley-era, matching the topology that ships with minimina. Mixing eras would risk bin_prot mismatch.

## Golden fixtures

A separate weekly job will run the full e2e flow and publish the resulting Postgres dump + S3 contents as a versioned artifact (`dumps/YYYY-MM-DD/`). `mina-payout-reports` consumes a *pinned* version of that artifact in its own test suite.

**Contract rule:** if the reports test goes red, do *not* refresh the dump version to make it pass — investigate whether the report generator still works on the new schema first. Bumping the dump version is an explicit decision, not a fix.
